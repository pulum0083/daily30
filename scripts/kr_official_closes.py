# 한국 종목 정규장 공식 종가 일봉 — 애프터장·넥스트레이드 가격이 섞이지 않은 단일 소스(SERVICE_RULES §48)
"""
2026-09-14 KRX 애프터마켓(16:00~20:00) 개장 뒤 확인한 사실.

- 네이버 일봉의 **과거** 종가는 KRX 공식 종가(야후 .KS)와 30거래일 전부 일치한다.
- 네이버 일봉의 **오늘 봉**과 실시간 closePrice는 15:30 뒤 애프터장 체결가를 따라 계속 바뀐다
  (SK하이닉스 공식 1,697,000 → 17:10 일봉 1,688,000).
- 토스 일봉은 과거 날짜도 공식 종가와 26~29/30일 달랐다(최대 8.27%). 거래소·세션 옵션이 없어 쓰지 않는다.
- 공식 종가는 네이버 **15:30 1분봉** currentPrice가 준다(야후 종가와 일치). 1분봉은 최근 약 7거래일만 조회된다.

그래서 과거는 네이버 일봉, 15:30이 지난 오늘 봉만 15:30 1분봉으로 바꾼다.
1분봉을 못 구하면 틀린 값을 쓰지 않고 오늘 봉을 뺀다(운영 규칙 0 — 없으면 비운다).
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
_UA = {"User-Agent": "Mozilla/5.0"}
DAY_URL = ("https://api.stock.naver.com/chart/domestic/item/{code}/day"
           "?startDateTime={start}&endDateTime={end}")
MINUTE_URL = ("https://api.stock.naver.com/chart/domestic/item/{code}/minute"
              "?startDateTime={d}1530&endDateTime={d}1530")
REGULAR_CLOSE_HHMM = "1530"


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def regular_close(code, yyyymmdd, fetch=_get_json):
    """그날 정규장 공식 종가(15:30 1분봉). 없거나 실패하면 None."""
    try:
        bars = fetch(MINUTE_URL.format(code=code, d=yyyymmdd))
    except Exception as e:
        print(f"[official_closes] {code} {yyyymmdd} 15:30 1분봉 조회 실패: {e}", file=sys.stderr)
        return None
    for b in bars if isinstance(bars, list) else []:
        if isinstance(b, dict) and str(b.get("localDateTime")) == f"{yyyymmdd}153000" and b.get("currentPrice"):
            return float(b["currentPrice"])
    return None


def official_day_rows(code, now=None, days=420, fetch=_get_json):
    """네이버 일봉 행(오래된→최신)을 정규장 공식 종가 기준으로 돌려준다. 실패 시 [].

    행 모양은 네이버 원본 그대로(localDate·closePrice·accumulatedTradingVolume·foreignRetentionRate…)라
    기존 소비처를 바꾸지 않고 끼울 수 있다. 오늘 봉의 closePrice만 바뀐다.
    15:30 전(장중)의 오늘 봉은 건드리지 않는다 — 진행 중인 봉 처리는 호출부의 pin(§37)이 맡는다.
    """
    now = now or datetime.now(KST)
    end = now.strftime("%Y%m%d") + "0000"
    start = (now - timedelta(days=days)).strftime("%Y%m%d") + "0000"
    try:
        rows = fetch(DAY_URL.format(code=code, start=start, end=end))
    except Exception as e:
        print(f"[official_closes] {code} 일봉 조회 실패: {e}", file=sys.stderr)
        return []
    rows = [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    today = now.strftime("%Y%m%d")
    if not rows or str(rows[-1].get("localDate")) != today or now.strftime("%H%M") < REGULAR_CLOSE_HHMM:
        return rows
    close = regular_close(code, today, fetch)
    if close is None:
        print(f"[official_closes] {code} {today} 15:30 1분봉 없음 — 오늘 봉을 뺀다"
              f"(일봉 {rows[-1].get('closePrice')}은 애프터장 가격일 수 있다)", file=sys.stderr)
        return rows[:-1]
    drifted = rows[-1].get("closePrice")
    if drifted is not None and abs(float(drifted) - close) > 0.5:
        print(f"[official_closes] {code} {today} 일봉 종가 {drifted} → 정규장 종가 {close} 로 교정", file=sys.stderr)
    return rows[:-1] + [{**rows[-1], "closePrice": close}]


def official_closes(code, now=None, days=420, fetch=_get_json):
    """정규장 공식 종가 리스트(오래된→최신). 실패 시 []."""
    return [float(r["closePrice"]) for r in official_day_rows(code, now, days, fetch) if r.get("closePrice")]
