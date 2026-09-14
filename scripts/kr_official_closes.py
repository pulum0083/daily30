# 한국 종목 정규장 공식 종가 일봉 — 애프터장·넥스트레이드 가격이 섞이지 않은 단일 소스(SERVICE_RULES §48)
"""
2026-09-14 KRX 애프터마켓(16:00~20:00) 개장 뒤 확인한 사실.

- 네이버 일봉의 **9/13 이전** 종가는 KRX 공식 종가(야후 .KS)와 30거래일 전부 일치한다.
- **9/14부터는 일봉 종가가 20:00 애프터장 가격으로 확정된다.** 9/14 20:12 실측 — 삼성전자 일봉 248,500 /
  공식 249,000, SK하이닉스 1,683,000 / 1,697,000, 현대차 367,500 / 371,500. 장 마감 직후뿐 아니라
  **지난 날짜 봉도 공식 종가가 아니다.**
- 토스 일봉은 과거 날짜도 공식 종가와 26~29/30일 달랐다(최대 8.27%). 거래소·세션 옵션이 없어 쓰지 않는다.
- 공식 종가는 네이버 **15:30 1분봉** currentPrice가 준다(야후 종가와 일치). 1분봉은 최근 약 7거래일만 조회된다.

그래서 9/14 이후 봉은 15:30 1분봉 공식 종가로 바꾸고, 그 값을 `data/kr_official_closes.json`에 쌓아
1분봉 조회 기한이 지난 뒤에도 쓴다. 저장은 마감 잡(build_stocks_snapshot)만 한다(§18 파일 소유권).
공식 종가를 구하지 못한 봉은 틀린 값을 쓰지 않고 뺀다(운영 규칙 0 — 없으면 비운다).
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
_UA = {"User-Agent": "Mozilla/5.0"}
DAY_URL = ("https://api.stock.naver.com/chart/domestic/item/{code}/day"
           "?startDateTime={start}&endDateTime={end}")
MINUTE_URL = ("https://api.stock.naver.com/chart/domestic/item/{code}/minute"
              "?startDateTime={d}1530&endDateTime={d}1530")
REGULAR_CLOSE_HHMM = "1530"
# KRX 애프터마켓 첫날. 이날부터 네이버 일봉 종가가 애프터장 가격으로 확정된다(9/14 20:12 실측).
AFTERMARKET_START = "20260914"
CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "kr_official_closes.json"

_cache = None      # {code: {YYYYMMDD: close}}
_dirty = False


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _store():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")).get("closes", {})
        except (OSError, ValueError):
            _cache = {}
    return _cache


def save_cache(path=None):
    """이번 실행에서 새로 확인한 공식 종가를 파일에 합쳐 쓴다. 새 값이 없으면 쓰지 않는다."""
    global _dirty
    if not _dirty:
        return False
    path = path or CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "note": "KRX 정규장 15:30 공식 종가 — 네이버 일봉이 애프터장 가격으로 확정되는 2026-09-14 이후 날짜만 쌓는다(SERVICE_RULES §48).",
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "closes": {c: dict(sorted(v.items())) for c, v in sorted(_store().items())},
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _dirty = False
    return True


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


def official_close(code, yyyymmdd, fetch=_get_json):
    """저장된 공식 종가, 없으면 15:30 1분봉. 둘 다 없으면 None."""
    global _dirty
    known = _store().get(code, {}).get(yyyymmdd)
    if known is not None:
        return float(known)
    close = regular_close(code, yyyymmdd, fetch)
    if close is not None:
        _store().setdefault(code, {})[yyyymmdd] = close
        _dirty = True
    return close


def official_day_rows(code, now=None, days=420, fetch=_get_json):
    """네이버 일봉 행(오래된→최신)을 정규장 공식 종가 기준으로 돌려준다. 실패 시 [].

    행 모양은 네이버 원본 그대로(localDate·closePrice·accumulatedTradingVolume·foreignRetentionRate…)라
    기존 소비처를 바꾸지 않고 끼울 수 있다. 2026-09-14 이후 봉의 closePrice만 바뀐다.
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
    intraday = now.strftime("%H%M") < REGULAR_CLOSE_HHMM
    out = []
    for r in rows:
        d = str(r.get("localDate"))
        if d < AFTERMARKET_START or d > today or (d == today and intraday):
            out.append(r)
            continue
        close = official_close(code, d, fetch)
        if close is None:
            print(f"[official_closes] {code} {d} 공식 종가 없음 — 그 봉을 뺀다"
                  f"(일봉 {r.get('closePrice')}은 애프터장 가격일 수 있다)", file=sys.stderr)
            continue
        drifted = r.get("closePrice")
        if drifted is not None and abs(float(drifted) - close) > 0.5:
            print(f"[official_closes] {code} {d} 일봉 종가 {drifted} → 정규장 종가 {close} 로 교정", file=sys.stderr)
        out.append({**r, "closePrice": close})
    return out


def official_closes(code, now=None, days=420, fetch=_get_json):
    """정규장 공식 종가 리스트(오래된→최신). 실패 시 []."""
    return [float(r["closePrice"]) for r in official_day_rows(code, now, days, fetch) if r.get("closePrice")]
