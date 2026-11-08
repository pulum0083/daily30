# 코스피 체크 — 코스피 종가가 60개월선보다 얼마나 위인지와 과거 위치를 계산한다(종목 홈 구조 신호, §68 ⑤)
"""
나스닥 체크(nasdaq_overheat)와 달리 두 가지가 다르다(2026-11-02 사용자 결정).
- 월봉 고점이 아니라 월말 종가를 쓴다. 고점으로 재면 새 달 첫 거래일에 값이 튄다(2026-11-02 +110% → +74%).
- 정상·주의·경고를 판정하지 않는다. 기준을 받칠 사례가 2005~2007년 하나뿐이고 70%를 넘은 채 11개월째다.
  지금 값과 과거 위치만 준다.
결과는 build_home_summary가 home-summary.json의 kospi_check로 쓴다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nasdaq_overheat as nq  # noqa: E402

SYMBOL = "^KS11"
MA_MONTHS = 60


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


def compute(daily: list, last_date: str, last_close: float) -> dict | None:
    """야후 일봉에 네이버 마지막 종가를 맞춰 계산한다 — 화면의 다른 코스피 숫자와 갈리지 않게 한다.
    daily: [(YYYY-MM-DD, high, low, close)] 오래된→최신. 계산할 달이 없으면 None."""
    rows = [r for r in daily if r[0] < last_date] + [(last_date, last_close, last_close, last_close)]
    series = gap_series(nq.monthly(rows))
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
        # 월별 흐름 — 종목 홈이 25년 그래프로 그린다(2026-11-08 B안). [월, 5년 평균 대비 %] 오래된→최신
        "series": [[x["m"], round(x["g"], 1)] for x in series],
    }


def fetch(last_date: str, last_close: float) -> dict | None:
    """네트워크 실패면 None — 줄이 빠질 뿐 마감 잡을 막지 않는다."""
    try:
        return compute(nq.fetch_daily(SYMBOL), last_date, last_close)
    except Exception as e:
        print(f"[kospi_check] 조회 실패: {e}", file=sys.stderr)
        return None
