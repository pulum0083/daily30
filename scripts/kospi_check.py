# 코스피 체크 — 코스피 종가가 60개월선보다 얼마나 위인지와 과거 위치를 계산한다(종목 홈 구조 신호, §68 ⑤)
"""
나스닥 체크(nasdaq_overheat)와 달리 두 가지가 다르다(2026-11-02 사용자 결정).
- 월봉 고점이 아니라 월말 종가를 쓴다. 고점으로 재면 새 달 첫 거래일에 값이 튄다(2026-11-02 +110% → +74%).
- 정상·주의·경고를 판정하지 않는다. 기준을 받칠 사례가 2005~2007년 하나뿐이고 70%를 넘은 채 11개월째다.
  지금 값과 과거 위치만 준다.
결과는 build_home_summary가 home-summary.json의 kospi_check로 쓴다. 월별 기록(history)은 home-summary에 넣지 않고
data/kospi_check.json에만 남긴다 — 상세 페이지(/stocks/kospi-check/, 2026-11-09)가 읽는다.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nasdaq_overheat as nq  # noqa: E402

SYMBOL = "^KS11"
MA_MONTHS = 60
# 야후 ^KS11은 1996-11부터라 5년 평균이 2001-11에야 시작한다. 그 앞은 네이버 지수 일봉(1990-01~)으로 채운다
# (2026-11-09 — 1999-12 같은 사례가 '지금과 비슷했던 때'에서 빠지지 않게). 네이버 일봉은 2006~2007년 저가가
# 0으로 비어 있는 날이 있어, 야후가 있는 기간은 야후를 그대로 쓰고 그 앞만 네이버로 잇는다.
NAVER_DAY_URL = ("https://api.stock.naver.com/chart/domestic/index/KOSPI/day"
                 "?startDateTime=199001010000&endDateTime={end}2359")


def gap_series(months: list) -> list:
    """월마다 (월말 종가 ÷ 60개월 평균 − 1)%. 60개월이 안 되는 달은 뺀다. [{m, g, ma60}] 오래된→최신."""
    closes = [x["close"] for x in months]
    out = []
    for i, x in enumerate(months):
        if i + 1 < MA_MONTHS:
            continue
        ma = sum(closes[i + 1 - MA_MONTHS:i + 1]) / MA_MONTHS
        out.append({"m": x["m"], "g": (x["close"] / ma - 1) * 100, "ma60": ma})
    return out


BUCKETS = ((None, 0.0), (0.0, 20.0), (20.0, 40.0), (40.0, 60.0), (60.0, None))   # 과거 비교 구간(%) — 상세 페이지
EPISODE_GAP = 3        # 같은 구간의 달이 이 개월 수 안에 이어지면 한 번의 사례로 묶는다


def forward(months: list, i: int):
    """i번째 달 종가에서 12개월 뒤 월말 종가까지의 등락과, 그 12개월 월 저가 중 가장 낮은 값까지의 하락(%).
    12개월 뒤가 마지막 달(진행 중인 이번 달)이거나 그보다 뒤면 (None, None) — 끝나지 않은 결과를 세지 않는다."""
    if i + 12 > len(months) - 2:
        return None, None
    c0 = months[i]["close"]
    low = min(months[j]["low"] for j in range(i + 1, i + 13))
    return (months[i + 12]["close"] / c0 - 1) * 100, (low / c0 - 1) * 100


def bucket_of(g: float) -> tuple:
    for lo, hi in BUCKETS:
        if (lo is None or g >= lo) and (hi is None or g < hi):
            return lo, hi
    return BUCKETS[-1]


def episodes(history: list, lo, hi) -> list:
    """history([월, 거리, 종가, 5년 평균, 1년 뒤 등락, 1년 안 최대 하락])에서 거리가 [lo, hi) 안이고 1년 뒤 결과가 있는 달을
    EPISODE_GAP 개월 안으로 이어진 것끼리 묶는다. [{months:[...], r12:[...], dd:[...]}] 오래된→최신."""
    key = lambda m: int(m[:4]) * 12 + int(m[5:7])
    out = []
    for m, g, _c, _ma, r, dd in history:
        if r is None or (lo is not None and g < lo) or (hi is not None and g >= hi):
            continue
        if out and key(m) - key(out[-1]["months"][-1]) <= EPISODE_GAP:
            out[-1]["months"].append(m)
            out[-1]["r12"].append(r)
            out[-1]["dd"].append(dd)
        else:
            out.append({"months": [m], "r12": [r], "dd": [dd]})
    return out


def compute(daily: list, last_date: str, last_close: float) -> dict | None:
    """야후 일봉에 네이버 마지막 종가를 맞춰 계산한다 — 화면의 다른 코스피 숫자와 갈리지 않게 한다.
    daily: [(YYYY-MM-DD, high, low, close)] 오래된→최신. 계산할 달이 없으면 None."""
    rows = [r for r in daily if r[0] < last_date] + [(last_date, last_close, last_close, last_close)]
    months = nq.monthly(rows)
    series = gap_series(months)
    if not series:
        return None
    cur = series[-1]
    year = cur["m"][:4]
    earlier = [x for x in series if x["m"][:4] < year]
    this_year = max((x for x in series if x["m"][:4] == year), key=lambda x: x["g"])
    prev = max(earlier, key=lambda x: x["g"]) if earlier else None
    return {
        "asof": last_date,
        "gap_pct": round(cur["g"], 1),
        "ma60": round(cur["ma60"], 1),
        "close": round(last_close, 2),
        "since": series[0]["m"],
        "months": len(series),
        "above": sum(1 for x in series[:-1] if x["g"] > cur["g"]),   # 지금보다 높았던 달 수
        "year_max": {"m": this_year["m"], "gap": round(this_year["g"], 1)},
        "prev_max": {"m": prev["m"], "gap": round(prev["g"], 1)} if prev else None,
        # 월별 흐름 — 종목 홈·상세 페이지가 그래프로 그린다(2026-11-08 B안). [월, 5년 평균 대비 %] 오래된→최신
        "series": [[x["m"], round(x["g"], 1)] for x in series],
        # 상세 페이지용 월별 기록 — home-summary에는 넣지 않는다(build_home_summary가 뺀다).
        # [월, 거리 %, 월말 종가, 5년 평균, 1년 뒤 등락 %, 1년 안 최대 하락 %] — 1년 뒤가 아직이면 마지막 둘은 None
        "history": [_hist_row(months, x) for x in series],
    }


def _hist_row(months: list, x: dict) -> list:
    i = next(k for k, m in enumerate(months) if m["m"] == x["m"])
    r, dd = forward(months, i)
    rd = lambda v: None if v is None else round(v, 1)
    return [x["m"], round(x["g"], 1), round(months[i]["close"], 2), round(x["ma60"], 1), rd(r), rd(dd)]


def naver_daily(end: str) -> list:
    """네이버 코스피 지수 일봉 → [(YYYY-MM-DD, high, low, close)] 오래된→최신. 값이 빈 날은 뺀다."""
    url = NAVER_DAY_URL.format(end=end.replace("-", ""))
    rows = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                             timeout=30).read())
    out = []
    for r in rows:
        try:
            d, h, lo, c = r["localDate"], float(r["highPrice"]), float(r["lowPrice"]), float(r["closePrice"])
        except (KeyError, TypeError, ValueError):
            continue
        if h > 0 and lo > 0 and c > 0:
            out.append((f"{d[:4]}-{d[4:6]}-{d[6:8]}", h, lo, c))
    return sorted(out)


def join_daily(yahoo: list, naver: list) -> list:
    """야후 일봉 앞에 야후 첫 날보다 이른 네이버 일봉을 붙인다. 겹치는 기간은 야후를 쓴다."""
    if not yahoo:
        return naver
    first = yahoo[0][0]
    return [r for r in naver if r[0] < first] + list(yahoo)


def fetch_daily(end: str) -> list:
    """코스피 체크용 일봉 — 야후 ^KS11 + 그 앞은 네이버. 네이버가 실패하면 야후만 쓴다(기록이 짧아질 뿐이다)."""
    yahoo = nq.fetch_daily(SYMBOL)
    try:
        naver = naver_daily(end)
    except Exception as e:
        print(f"[kospi_check] 네이버 지수 일봉 조회 실패 — 야후만 쓴다: {e}", file=sys.stderr)
        naver = []
    return join_daily(yahoo, naver)


def fetch(last_date: str, last_close: float) -> dict | None:
    """네트워크 실패면 None — 줄이 빠질 뿐 마감 잡을 막지 않는다."""
    try:
        return compute(fetch_daily(last_date), last_date, last_close)
    except Exception as e:
        print(f"[kospi_check] 조회 실패: {e}", file=sys.stderr)
        return None
