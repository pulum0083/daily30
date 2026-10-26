# 나스닥 종합지수 월봉 고점 vs 60개월선 — 미국 브리핑 '나스닥 체크' 섹션·텔레그램 경고 블록의 데이터(결정론, LLM 없음)
"""
지표(사용자 결정 2026-10-25, docs/plans/2026-10-25-us-nasdaq-overheat/plan.md):
  이번 달 월봉 고점 ÷ 월말 종가 60개월 평균(진행 중인 이번 달 종가 포함) − 1
  60% 미만 정상 · 60% 이상 주의 · 70% 이상 경고.

야후 일봉(1971~)을 받아 월별로 묶는다(고가 = 그 달 일봉 고가 최대, 종가 = 마지막 종가).
야후 월봉 API는 진행 중인 달의 고가를 틀리게 준다 — 2026-10 월봉 고가 26,111.6, 일봉 최대 27,722.8.

출력: data/nasdaq_overheat.json(gitignore — generate_html이 analysis에 주입해 스냅샷에 흡수된다, §45와 같은 구조)
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "nasdaq_overheat.json"

SYMBOL = "^IXIC"
MA_MONTHS = 60
CAUTION, WARN = 60.0, 70.0      # 주의·경고 기준(%)
CHART_FROM = "2014-01"          # 화면 그래프 시작 월
UA = {"User-Agent": "Mozilla/5.0"}


def level_of(gap_pct: float) -> str:
    """'ok' | 'caution' | 'warn'. 페이지 섹션과 텔레그램이 같은 판정을 쓴다."""
    if gap_pct >= WARN:
        return "warn"
    if gap_pct >= CAUTION:
        return "caution"
    return "ok"


def fetch_daily(symbol: str = SYMBOL) -> list:
    """야후 차트 API 일봉 → [(YYYY-MM-DD, high, low, close)] 오래된→최신. 거래소 현지 날짜."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(symbol)}"
           "?period1=0&period2=4102444800&interval=1d")
    r = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
    res = r["chart"]["result"][0]
    off = res["meta"].get("gmtoffset", 0)
    q = res["indicators"]["quote"][0]
    out = []
    for t, h, lo, c in zip(res["timestamp"], q["high"], q["low"], q["close"]):
        if None in (h, lo, c):
            continue
        out.append((datetime.utcfromtimestamp(t + off).strftime("%Y-%m-%d"), float(h), float(lo), float(c)))
    return out


def monthly(daily: list) -> list:
    """일봉 → 월봉 [{m: 'YYYY-MM', high, low, close, last_date}] 오래된→최신."""
    by_m = {}
    for d, h, lo, c in daily:
        m = d[:7]
        cur = by_m.get(m)
        if cur is None:
            by_m[m] = {"m": m, "high": h, "low": lo, "close": c, "last_date": d}
        else:
            cur["high"] = max(cur["high"], h)
            cur["low"] = min(cur["low"], lo)
            if d >= cur["last_date"]:
                cur["close"], cur["last_date"] = c, d
    return [by_m[k] for k in sorted(by_m)]


def gap_series(months: list) -> list:
    """월마다 (월봉 고점 ÷ 60개월 평균 − 1)%. 60개월이 안 되는 달은 None."""
    out = []
    closes = [x["close"] for x in months]
    for i, x in enumerate(months):
        if i + 1 < MA_MONTHS:
            out.append(None)
            continue
        ma = sum(closes[i + 1 - MA_MONTHS:i + 1]) / MA_MONTHS
        out.append({"m": x["m"], "g": (x["high"] / ma - 1) * 100, "ma60": ma})
    return out


def compute(months: list) -> dict | None:
    """화면·텔레그램에 쓰는 값. 60개월이 안 되면 None."""
    gs = gap_series(months)
    if not gs or gs[-1] is None:
        return None
    cur, last = gs[-1], months[-1]
    streak = 0
    for g in reversed(gs):
        if g is None or g["g"] < CAUTION:
            break
        streak += 1
    series = [{"m": g["m"], "g": round(g["g"], 2)} for g in gs if g and g["m"] >= CHART_FROM]
    peak = max(series, key=lambda s: s["g"]) if series else None
    return {
        "month": last["m"],
        "last_date": last["last_date"],
        "gap_pct": round(cur["g"], 2),
        "high": round(last["high"], 2),
        "ma60": round(cur["ma60"], 2),
        "streak": streak,
        "level": level_of(cur["g"]),
        "series": series,
        "peak": peak,
    }


def main():
    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    try:
        result = compute(monthly(fetch_daily()))
    except Exception as e:
        print(f"[nasdaq_overheat] 조회 실패 — 섹션 생략: {e}", file=sys.stderr)
        sys.exit(1)
    if result is None:
        print("[nasdaq_overheat] 60개월 데이터 부족 — 섹션 생략", file=sys.stderr)
        sys.exit(1)
    payload = {"date": date_str, "generated_at": datetime.now(KST).isoformat(timespec="seconds"), **result}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[nasdaq_overheat] {result['month']} 고점 {result['high']:,.1f} / 60개월선 {result['ma60']:,.1f} "
          f"→ {result['gap_pct']:+.1f}% ({result['level']}, 60% 위 {result['streak']}개월째) → {OUT_PATH}")


if __name__ == "__main__":
    main()
