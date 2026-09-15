# 한국 종목 정규장 공식 종가·거래량 일봉 — 애프터장·넥스트레이드 체결이 섞이지 않은 단일 소스(SERVICE_RULES §48)
"""
2026-09-14 KRX 애프터마켓(16:00~20:00) 개장 뒤 확인한 사실.

- 네이버 일봉의 **9/13 이전** 종가는 KRX 공식 종가(야후 .KS)와 30거래일 전부 일치한다.
- **9/14부터는 일봉 종가가 20:00 애프터장 가격으로 확정된다.** 9/14 20:12 실측 — 삼성전자 일봉 248,500 /
  공식 249,000, SK하이닉스 1,683,000 / 1,697,000, 현대차 367,500 / 371,500. 장 마감 직후뿐 아니라
  **지난 날짜 봉도 공식 종가가 아니다.**
- **일봉 거래량도 9/14부터 애프터장 체결을 포함한다.** 9/14 SK하이닉스 일봉 4,001,549 = 정규장 1분봉 합
  3,742,905 + 애프터장 256,370 + 그 사이 957. 애프터장 비중은 종목마다 1.9~20.1%(한미반도체)였다. 네이버 fchart·
  siseJson·pykrx·야후 거래량도 같은 값이라 정규장 거래량을 주는 일봉 소스는 없다.
  9/11(애프터장 이전) 일봉 거래량과 정규장 1분봉 합의 차이는 0.04~0.2%(시간외 거래)라, 정규장 1분봉 합으로
  바꿔도 과거 봉과 정의가 사실상 같다.
- 일봉 시가·고가·저가도 애프터장이 섞였지만(9/14 저가 1,678,000 / 정규장 1,686,000) 이 행을 읽는 곳이 없어 고치지 않는다.
- 토스 일봉은 과거 날짜도 공식 종가와 26~29/30일 달랐다(최대 8.27%). 거래소·세션 옵션이 없어 쓰지 않는다.
- 공식 종가는 네이버 **15:30 1분봉** currentPrice가 준다(야후 종가와 일치). 1분봉은 최근 약 7거래일만 조회된다.

그래서 9/14 이후 봉은 정규장 1분봉의 공식 종가·거래량으로 바꾸고, 그 값을 `data/kr_official_closes.json`에 쌓아
1분봉 조회 기한이 지난 뒤에도 쓴다. 저장은 마감 잡(build_stocks_snapshot)만 한다(§18 파일 소유권).
공식 종가를 구하지 못한 봉은 틀린 값을 쓰지 않고 뺀다. 거래량만 못 구하면 거래량을 비운다(운영 규칙 0).
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
              "?startDateTime={d}0900&endDateTime={d}1530")
CLOSE_BAR_URL = ("https://api.stock.naver.com/chart/domestic/item/{code}/minute"
                 "?startDateTime={d}1530&endDateTime={d}1530")
REGULAR_OPEN_HHMM = "0900"
REGULAR_CLOSE_HHMM = "1530"
# KRX 애프터마켓 첫날. 이날부터 네이버 일봉 종가·거래량이 애프터장을 포함한다(9/14 20:12 실측).
AFTERMARKET_START = "20260914"
CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "kr_official_closes.json"

_cache = None      # {code: {YYYYMMDD: close}}
_vcache = None     # {code: {YYYYMMDD: 정규장 거래량}}
_dirty = False


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _load():
    global _cache, _vcache
    if _cache is not None and _vcache is not None:
        return
    try:
        body = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        body = {}
    if _cache is None:
        _cache = body.get("closes", {})
    if _vcache is None:
        _vcache = body.get("volumes", {})


def _store():
    _load()
    return _cache


def _vstore():
    _load()
    return _vcache


def save_cache(path=None):
    """이번 실행에서 새로 확인한 공식 종가·거래량을 파일에 합쳐 쓴다. 새 값이 없으면 쓰지 않는다."""
    global _dirty
    if not _dirty:
        return False
    path = path or CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "note": "KRX 정규장 공식 종가(15:30 1분봉)·정규장 거래량(09:00~15:30 1분봉 합) — 네이버 일봉이 애프터장을 포함하는 2026-09-14 이후 날짜만 쌓는다(SERVICE_RULES §48).",
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "closes": {c: dict(sorted(v.items())) for c, v in sorted(_store().items())},
        "volumes": {c: dict(sorted(v.items())) for c, v in sorted(_vstore().items())},
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _dirty = False
    return True


def regular_session(code, yyyymmdd, fetch=_get_json):
    """그날 정규장(09:00~15:30) 1분봉 → {"close": 15:30 공식 종가, "volume": 정규장 거래량}. 종가가 없거나 실패하면 None.

    1분봉의 accumulatedTradingVolume은 이름과 달리 봉 하나의 거래량이다(9/14 실측 — 합이 일봉과 맞는다).
    거래량 필드가 하나도 없으면 volume은 None이다.
    """
    try:
        bars = fetch(MINUTE_URL.format(code=code, d=yyyymmdd))
    except Exception as e:
        print(f"[official_closes] {code} {yyyymmdd} 정규장 1분봉 조회 실패: {e}", file=sys.stderr)
        return None
    close, volume, seen = None, 0, False
    for b in bars if isinstance(bars, list) else []:
        if not isinstance(b, dict):
            continue
        ts = str(b.get("localDateTime") or "")
        if ts[:8] != yyyymmdd or not (REGULAR_OPEN_HHMM <= ts[8:12] <= REGULAR_CLOSE_HHMM):
            continue
        if b.get("accumulatedTradingVolume") is not None:
            volume += int(b["accumulatedTradingVolume"])
            seen = True
        if ts[8:12] == REGULAR_CLOSE_HHMM and b.get("currentPrice"):
            close = float(b["currentPrice"])
    if close is None:
        return None
    return {"close": close, "volume": volume if seen else None}


def regular_close(code, yyyymmdd, fetch=_get_json):
    """그날 정규장 공식 종가(15:30 1분봉 한 개만 조회). 없거나 실패하면 None. 거래량이 필요 없을 때 쓴다."""
    try:
        bars = fetch(CLOSE_BAR_URL.format(code=code, d=yyyymmdd))
    except Exception as e:
        print(f"[official_closes] {code} {yyyymmdd} 15:30 1분봉 조회 실패: {e}", file=sys.stderr)
        return None
    for b in bars if isinstance(bars, list) else []:
        if isinstance(b, dict) and str(b.get("localDateTime")) == f"{yyyymmdd}153000" and b.get("currentPrice"):
            return float(b["currentPrice"])
    return None


def last_closed_session(now=None):
    """정규장이 끝난 마지막 거래일(YYYYMMDD). 오늘이 거래일이고 15:30이 지났으면 오늘, 아니면 그 전 거래일.

    holiday_check(pytz)는 이 함수를 부를 때만 불러온다 — 종가만 쓰는 소비처가 의존성을 떠안지 않게.
    """
    try:
        from scripts.holiday_check import check_kospi_open
    except ImportError:
        from holiday_check import check_kospi_open
    now = now or datetime.now(KST)
    d = now.date()
    if not (check_kospi_open(d) and now.strftime("%H%M") > REGULAR_CLOSE_HHMM):
        d -= timedelta(days=1)
        for _ in range(15):
            if check_kospi_open(d):
                break
            d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def official_session(code, yyyymmdd, fetch=_get_json):
    """(공식 종가, 정규장 거래량). 저장된 값을 먼저 쓰고 없는 것만 1분봉으로 채운다. 못 구한 값은 None."""
    global _dirty
    close = _store().get(code, {}).get(yyyymmdd)
    volume = _vstore().get(code, {}).get(yyyymmdd)
    if close is None or volume is None:
        s = regular_session(code, yyyymmdd, fetch)
        if s:
            if close is None:
                close = s["close"]
                _store().setdefault(code, {})[yyyymmdd] = close
                _dirty = True
            if volume is None and s["volume"] is not None:
                volume = s["volume"]
                _vstore().setdefault(code, {})[yyyymmdd] = volume
                _dirty = True
    return (float(close) if close is not None else None,
            int(volume) if volume is not None else None)


def official_close(code, yyyymmdd, fetch=_get_json):
    """저장된 공식 종가, 없으면 15:30 1분봉. 둘 다 없으면 None."""
    return official_session(code, yyyymmdd, fetch)[0]


def official_day_rows(code, now=None, days=420, fetch=_get_json):
    """네이버 일봉 행(오래된→최신)을 정규장 공식 종가·거래량 기준으로 돌려준다. 실패 시 [].

    행 모양은 네이버 원본 그대로(localDate·closePrice·accumulatedTradingVolume·foreignRetentionRate…)라
    기존 소비처를 바꾸지 않고 끼울 수 있다. 2026-09-14 이후 봉의 closePrice·accumulatedTradingVolume만 바뀐다
    (거래량을 못 구하면 None — 애프터장이 섞인 원본 값을 남기지 않는다).
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
        close, volume = official_session(code, d, fetch)
        if close is None:
            print(f"[official_closes] {code} {d} 공식 종가 없음 — 그 봉을 뺀다"
                  f"(일봉 {r.get('closePrice')}은 애프터장 가격일 수 있다)", file=sys.stderr)
            continue
        drifted = r.get("closePrice")
        if drifted is not None and abs(float(drifted) - close) > 0.5:
            print(f"[official_closes] {code} {d} 일봉 종가 {drifted} → 정규장 종가 {close} 로 교정", file=sys.stderr)
        if volume is None:
            print(f"[official_closes] {code} {d} 정규장 거래량 없음 — 거래량을 비운다", file=sys.stderr)
        out.append({**r, "closePrice": close, "accumulatedTradingVolume": volume})
    return out


def official_today(code, now=None, fetch=_get_json):
    """오늘 끝난 정규장의 {"close", "change_pct", "volume"} — 공식 종가끼리 비교한다. 15:30 전이거나 오늘 봉이 없으면 None.

    장이 닫힌 뒤 네이버 실시간·목록 API의 가격·등락률·거래량은 애프터장 체결을 따른다(2026-09-15 16:04 SK하이닉스
    실시간 1,688,000·-0.53% vs 공식 1,690,000·-0.41%). 마감 뒤 도는 잡이 '오늘 종가·등락률'이 필요하면 이 함수를 쓴다.
    """
    now = now or datetime.now(KST)
    if now.strftime("%H%M") <= REGULAR_CLOSE_HHMM:
        return None
    rows = official_day_rows(code, now=now, days=14, fetch=fetch)
    if len(rows) < 2 or str(rows[-1].get("localDate")) != now.strftime("%Y%m%d"):
        return None
    close, prev = rows[-1].get("closePrice"), rows[-2].get("closePrice")
    if not close or not prev:
        return None
    return {"close": float(close), "change_pct": round((close / prev - 1) * 100, 2),
            "volume": rows[-1].get("accumulatedTradingVolume")}


def official_closes(code, now=None, days=420, fetch=_get_json):
    """정규장 공식 종가 리스트(오래된→최신). 실패 시 []."""
    return [float(r["closePrice"]) for r in official_day_rows(code, now, days, fetch) if r.get("closePrice")]
