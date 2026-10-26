# 미국 대형주 월봉 5개월선 3개월 안착 종목 스크리닝 — 미국 브리핑 '월봉 5개월선 안착 종목' 코너(결정론, LLM 없음)
"""
코스피 코너(monthly_ma5.py, §61)와 같은 판정(`screen_one`)을 미국 대형주에 쓴다(사용자 결정 2026-10-26 —
AI가 진입·목표·손절을 제시하던 '상승 모멘텀 종목'을 대체).
대상은 미국 후보 목록(fetch_data.US_CANDIDATES). 일봉은 야후 차트 API 정규장 종가.
월말 봉 검사는 미국 거래일 달력(holiday_check.check_us_open)으로 한다.

출력: data/monthly_ma5_us.json(gitignore — generate_html이 analysis에 주입해 스냅샷에 흡수된다, §45)
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import monthly_ma5 as mm  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "monthly_ma5_us.json"
UA = {"User-Agent": "Mozilla/5.0"}


def universe() -> list:
    from fetch_data import US_CANDIDATES
    return [(t, t) for t in US_CANDIDATES]


def yahoo_day_rows(ticker: str, range_: str = "2y", period: str = "") -> list:
    """야후 일봉 → monthly_ma5가 읽는 행 모양 [{localDate: YYYYMMDD, closePrice, foreignRetentionRate: None}]."""
    q = period or f"range={range_}"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
           f"?{q}&interval=1d")
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read())
        res = r["chart"]["result"][0]
    except Exception as e:
        print(f"[monthly_ma5_us] {ticker} 조회 실패: {e}", file=sys.stderr)
        return []
    off = res["meta"].get("gmtoffset", 0)
    rows = []
    for t, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0].get("close") or []):
        if c is None:
            continue
        rows.append({"localDate": datetime.utcfromtimestamp(t + off).strftime("%Y%m%d"),
                     "closePrice": float(c), "foreignRetentionRate": None})
    return rows


def last_us_trading_day(yyyymm: str) -> str:
    """그 달의 마지막 미국 거래일(YYYYMMDD)."""
    from holiday_check import check_us_open
    y, mo = int(yyyymm[:4]), int(yyyymm[4:])
    d = date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1)
    for _ in range(15):
        if check_us_open(d):
            break
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def main():
    result = mm.run(fetch_rows=yahoo_day_rows, universe=universe(), last_trading_day=last_us_trading_day)
    if result is None:
        print("[monthly_ma5_us] 전부 판정 실패 — 파일을 쓰지 않는다(섹션 생략)", file=sys.stderr)
        sys.exit(1)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    names = ", ".join(f"{x['name']}({x['streak']}개월)" for x in result["items"]) or "없음"
    print(f"[monthly_ma5_us] {result['date']} 판정 {result['screened']}/{result['universe']} · 조건 충족: {names}")
    if result["failed"]:
        print(f"[monthly_ma5_us] 판정 못 한 종목: {result['failed']}", file=sys.stderr)


if __name__ == "__main__":
    main()
