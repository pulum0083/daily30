# 종목 유니버스 일봉 → 시세·52주·스파크라인·MA200 스냅샷 빌드
#!/usr/bin/env python3
"""실행: python3 scripts/build_stocks_snapshot.py
   stock_universe.json의 ~48 한국 종목 + 섹터 벨웨더를 토스 캔들로 수집해
   web/data/stocks-snapshot.json 으로 저장한다. SERVICE_RULES 0번 준수."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))


def change_pct(closes):
    """직전 완료 세션 대비 등락률(%). 데이터 부족 시 None."""
    if len(closes) < 2:
        return None
    return round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)


def wk52_high_low(closes):
    """최근 252거래일 고가/저가. (hi, lo). 데이터 부족 시 있는 만큼."""
    if not closes:
        return None, None
    window = closes[-252:]
    return max(window), min(window)


def sparkline(closes, n):
    """최근 n개 종가. 부족하면 있는 만큼."""
    return closes[-n:]


def ma200(closes):
    """최근 200거래일 단순이동평균. 200개 미만이면 None."""
    if len(closes) < 200:
        return None
    window = closes[-200:]
    return round(sum(window) / len(window), 2)
