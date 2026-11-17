# 발행 게이트의 실측 시세 조회 — 미국(토스→야후 프리마켓 포함)·국내(공식 종가) 일봉과 이격도

import os
import sys


def _closes_to_realdata(closes, ndigits, live_price=None):
    """일봉 종가 리스트(오래된→최신)로 실측 dict를 만든다.

    기본(live_price=None): '전일 등락률' = close[-1] vs close[-2] (실시간 장중가 아님).
    코스피 아침 브리핑처럼 **직전 완료 세션**이 기준인 경로가 이 동작을 쓴다.

    live_price 지정 시: 발행 시점의 실체결가(프리마켓·장중)를 현재가로 삼고
    **직전 정규장 종가(close[-1])를 기준가**로 등락률을 낸다. 미국 브리핑은
    21:15 KST = 프리마켓 한복판에 발행되므로 이 경로를 쓴다 — close[-1] vs close[-2]를
    쓰면 "지금"이 아니라 직전 세션의 등락이 실린다(2026-07-27 실사고, 운영 규칙 0).
    """
    if len(closes) < 2:
        return {"error": "insufficient data"}
    price, prev = closes[-1], closes[-2]
    if live_price:
        price, prev = float(live_price), closes[-1]
    r = (lambda v: round(v, ndigits))
    spark = closes[-20:] if not live_price else (closes[-19:] + [float(live_price)])
    out = {
        "price": r(price),
        "change_pct": round((price - prev) / prev * 100, 4),
        "sparkline": [r(x) for x in spark],
    }

    def _ma_series(window):
        # 마지막 20개 지점의 이동평균(데이터 부족 시 윈도우 clamp)
        return [sum(closes[max(0, i - window + 1):i + 1]) / len(closes[max(0, i - window + 1):i + 1])
                for i in range(len(closes) - 20, len(closes))]

    if len(closes) >= 20:
        ma20 = _ma_series(20)
        out["ma20_dist_pct"] = round((price - ma20[-1]) / ma20[-1] * 100, 2)
        out["ma20_sparkline"] = [r(v) for v in ma20]
        # 이격률뿐 아니라 **절대 수준**도 낸다 — 픽 카드가 손절 기준선을 실측으로 보여주고,
        # LLM이 "20일선 이탈 시"라고 쓴 손절가를 이 값으로 검증하기 위함(2026-09-02).
        out["ma20_level"] = r(ma20[-1])
    if len(closes) >= 200:
        ma200 = _ma_series(200)
        out["ma200_dist_pct"] = round((price - ma200[-1]) / ma200[-1] * 100, 2)
        out["ma200_level"] = r(ma200[-1])
        out["ma200_sparkline"] = [r(v) for v in ma200]
    return out


def _closes_from_toss_candles(candles: list, ndigits: int, live_price=None) -> dict:
    """Toss 캔들 리스트(오래된→최신)에서 실측 dict를 만든다."""
    closes = [float(c["closePrice"]) for c in candles if c.get("closePrice")]
    result = _closes_to_realdata(closes, ndigits, live_price=live_price)
    # vol_mult: 최신 거래량 / 직전 20일 평균 (tradingVolume 필드가 있을 때만)
    volumes = [float(c["tradingVolume"]) for c in candles if c.get("tradingVolume")]
    if len(volumes) >= 2:
        avg20 = sum(volumes[max(0, len(volumes) - 21):-1]) / min(20, len(volumes) - 1)
        if avg20 > 0:
            result["vol_mult"] = round(volumes[-1] / avg20, 1)
    return result


def _us_live_price(ticker):
    """발행 시점의 미국 종목 실체결가(프리마켓·장중 포함). 실패 시 None.

    yfinance fast_info는 연장시간대를 반영하지 않으므로 prepost intraday를 함께 본다
    (`fetch_data._extended_hours_price` 참조 — 2026-07-27 실사고).
    """
    try:
        try:
            from scripts.fetch_data import _get_realtime_price
        except ImportError:
            from fetch_data import _get_realtime_price
        rt = _get_realtime_price(ticker)
        return float(rt[0]) if rt and rt[0] else None
    except Exception:
        return None


def _fetch_us_realdata(ticker, live=False):
    """미국 종목 실측. Toss 캔들 우선, 실패 시 yfinance 폴백.

    live=True면 발행 시점 실체결가(프리마켓 포함)를 현재가로, 직전 정규장 종가를
    기준가로 삼는다. 미국 브리핑은 프리마켓 한복판에 나가므로 이 경로를 쓴다.
    """
    live_price = _us_live_price(ticker) if live else None

    # 1) 토스 API
    try:
        import scripts.toss_client as tc
    except ImportError:
        try:
            import toss_client as tc
        except ImportError:
            tc = None
    if tc:
        try:
            candles = tc.get_candles(ticker, interval="1d", count=300)
            if candles:
                return _closes_from_toss_candles(candles, ndigits=4, live_price=live_price)
        except Exception:
            pass

    # 2) yfinance 폴백
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="300d").dropna(subset=["Close"])
        closes = [float(x) for x in hist["Close"].tolist()]
        return _closes_to_realdata(closes, ndigits=4, live_price=live_price)
    except Exception as e:
        return {"error": str(e)}


def _pin_session_date():
    """DS_PIN_SESSION_DATE(KST)가 있으면 date, 없으면 None.

    코스피 아침 브리핑을 장 시작 후 수동 재생성할 때, 픽 실측이 **오늘 장중 값**으로
    주입되는 것을 막는다. 07:25 발행 시점엔 한국장이 닫혀 있어 §0가 "직전 완료 세션
    종가 대비"를 기준으로 삼는데, 09시 이후 재실행하면 토스·네이버 모두 당일 진행 중인
    (미완성) 일봉을 최신 캔들로 돌려주기 때문이다 — 실측 확인 결과 오늘 캔들의 거래량이
    전일의 1/6 수준이었다(장 초반 부분 데이터).
    """
    from datetime import datetime as _dt
    raw = os.environ.get("DS_PIN_SESSION_DATE", "").strip()
    if not raw:
        return None
    try:
        return _dt.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        print(f"[validate] DS_PIN_SESSION_DATE 형식 오류: {raw!r} — 무시", file=sys.stderr)
        return None


def _drop_rows_at_pin(rows, date_of):
    """pin 날짜 이후(당일 포함) 행 제거. pin이 없으면 그대로."""
    pin = _pin_session_date()
    if pin is None or not rows:
        return rows
    kept = []
    for r in rows:
        d = date_of(r)
        if d is None or d < pin:
            kept.append(r)
    if len(kept) < len(rows):
        print(f"[validate] pin {pin} — 당일 캔들 {len(rows) - len(kept)}건 제외", file=sys.stderr)
    return kept


def _toss_candle_date(c):
    from datetime import datetime as _dt
    try:
        return _dt.fromisoformat(str(c.get("timestamp"))).date()
    except Exception:
        return None


def _naver_row_date(r):
    from datetime import datetime as _dt
    try:
        return _dt.strptime(str(r.get("localDate"))[:8], "%Y%m%d").date()
    except Exception:
        return None


def _fetch_kospi_realdata(code):
    """한국 종목 실측 (6자리 코드). 정규장 공식 종가 일봉(kr_official_closes) 기준.

    토스 일봉은 쓰지 않는다 — 2026-09-14 대조에서 5종목 30거래일 중 26~29일이 KRX 공식 종가와
    달랐고(최대 8.27%, 넥스트레이드·시간외 체결이 섞인 값으로 보임) 거래소·세션을 고르는 옵션도 없다.
    §37에 미해결로 남았던 "토스·네이버 최대 4% 차이"의 원인이다(§48).
    """
    try:
        try:
            from scripts import kr_official_closes as koc
        except ImportError:
            import kr_official_closes as koc
        rows = _drop_rows_at_pin(koc.official_day_rows(code), _naver_row_date)
        closes = [float(rw["closePrice"]) for rw in rows if rw.get("closePrice")]
        return _closes_to_realdata(closes, ndigits=2)
    except Exception as e:
        return {"error": str(e)}
