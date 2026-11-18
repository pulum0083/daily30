# 종목·지수 시세 조회 — 일봉 교차 검증, 미국 연장시간대(야후→네이버), 200일선 위치, 피드 이상 알림

from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta
import pytz


# 한국·아시아 시장은 코스피 아침 브리핑이 나가는 07:25 KST엔 닫혀 있고 09:00부터 열린다.
# 그래서 장이 열린 뒤 브리핑을 수동 재생성하면(정정·재발행) 같은 스크립트가 **장중 값**을
# 수집해, "직전 종가 대비 예측"이어야 할 자리에 오늘 장중 지수·주가가 들어간다.
# DS_PIN_SESSION_DATE=YYYY-MM-DD(KST)를 주면 그 날짜 이후 데이터를 아직 없는 것으로 취급해
# 07:25 시점 전제(양 시장 휴장)를 그대로 재현한다. 미국·선물·환율은 그 시각에도 이미
# 열려 있었으므로 건드리지 않는다 — 전부 일괄로 되돌리면 오히려 07:25과 더 멀어진다.
_PIN_ASIA_TICKERS = {"^KS11", "^KQ11", "^N225", "^HSI", "^TWII", "000001.SS"}


def _pin_date_for(ticker: str):
    """이 티커에 적용할 pin 날짜(date) 또는 None."""
    raw = os.environ.get("DS_PIN_SESSION_DATE", "").strip()
    if not raw:
        return None
    t = (ticker or "").upper()
    if not (t.endswith(".KS") or t.endswith(".KQ") or t in _PIN_ASIA_TICKERS):
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        print(f"[fetch_data] DS_PIN_SESSION_DATE 형식 오류: {raw!r} — 무시", file=sys.stderr)
        return None


def _truncate_at_pin(ticker: str, hist):
    """pin 날짜 이후(당일 포함) 행을 잘라낸다. pin이 없으면 그대로 돌려준다."""
    pin = _pin_date_for(ticker)
    if pin is None or hist is None or len(hist) == 0:
        return hist
    try:
        kept = hist[[i.date() < pin for i in hist.index]]
    except Exception:
        return hist
    if len(kept) < len(hist):
        print(f"[fetch_data] {ticker}: pin {pin} — {len(hist) - len(kept)}행(당일분) 제외",
              file=sys.stderr)
    return kept


def _yf_history(ticker: str, retries: int = 3, **kwargs):
    """yfinance history() 호출을 최대 retries회 exponential backoff으로 재시도한다."""
    import yfinance as yf
    import pandas as pd
    last_exc = None
    for attempt in range(retries):
        try:
            hist = yf.Ticker(ticker).history(**kwargs)
            if not hist.empty:
                return _truncate_at_pin(ticker, hist)
        except Exception as e:
            last_exc = e
        if attempt < retries - 1:
            delay = 2 ** attempt
            print(f"[fetch_data] {ticker} fetch failed (attempt {attempt + 1}/{retries}), retry in {delay}s", file=sys.stderr)
            time.sleep(delay)
    if last_exc:
        print(f"[fetch_data] {ticker} all retries failed: {last_exc}", file=sys.stderr)
    return pd.DataFrame()



def _prev_close_from_daily(closes, price: float) -> float | None:
    """일봉 종가 시리즈에서 `price`가 속한 세션의 '직전 세션 종가'를 구한다.

    yfinance `fast_info.previous_close`는 직전 세션이 아닌 더 과거 세션의 종가를
    돌려주는 경우가 있다(2026-07-27 실사고: EWY previous_close=172.964 = 7/21 종가,
    실제 직전 종가는 173.86 = 7/23 → 등락률이 -6.27%가 아닌 -5.78%로 표시됨).
    실시간 가격 자체(last_price)는 정확하므로, 기준가만 일봉에서 다시 구해 교정한다.

    실패하거나 판별 불가하면 None → 호출부가 기존 값을 유지한다.
    """
    try:
        if closes is None or len(closes) < 2 or not price:
            return None
        last = float(closes.iloc[-1])
        if not last:
            return None

        # ① price가 마지막 일봉 종가와 같으면 장 마감 상태 → 그 직전 종가가 기준가
        if abs(price - last) / last < 1e-4:
            return float(closes.iloc[-2])

        # ② 세션 진행 중(또는 시간외) — 마지막 일봉이 '오늘' 바인지로 갈린다.
        #    거래소 현지 시각 기준으로 판별한다(yfinance 인덱스는 거래소 tz).
        ts = closes.index[-1]
        tzinfo = getattr(ts, "tzinfo", None)
        if tzinfo is None:
            return None
        if ts.date() >= datetime.now(tzinfo).date():
            return float(closes.iloc[-2])  # 마지막 바 = 오늘 진행 중 바
        return last                        # 마지막 바 = 직전 세션 종가
    except Exception:
        return None


def _is_futures_like(ticker: str) -> bool:
    """선물·지수·금리 심볼인가 (롤오버 가드 적용 대상).

    개별 주식·ETF는 롤오버가 없다. 가드를 개별주에 적용하면 프리마켓 실체결가를
    '롤오버 갭'으로 오인해 정규장 종가로 되돌린다(2026-07-27: XOM 프리마켓 -3.19%가
    +4.15%로 부호까지 반전). 가드가 쓰는 1시간봉은 prepost를 포함하지 않기 때문이다.
    """
    t = (ticker or "").upper()
    return t.endswith("=F") or t.startswith("^") or t.endswith("=X")


def _extended_hours_price(intraday, fast_last: float | None, now=None,
                          max_age_hours: float = 12.0) -> float | None:
    """프리마켓·애프터마켓을 포함한 '지금 이 시점'의 최근 체결가를 돌려준다.

    yfinance `fast_info.last_price`는 **연장시간대(프리·애프터) 체결을 반영하지 않는다** —
    프리마켓 한복판에도 직전 정규장 종가를 그대로 준다(2026-07-27 실측: 프리마켓에서
    MU가 938.18에 거래되는데 fast_info는 금요일 종가 920.95를 반환).
    미국 브리핑은 21:15 KST = 프리마켓 한복판에 발행되므로, 이 값을 그대로 쓰면
    "발행 시점 데이터"가 아니라 항상 직전 세션 종가가 실린다(운영 규칙 0 위반).

    판정은 **값이 아니라 타임스탬프**로 한다 — fast_info 값을 5분봉에서 되찾는 방식은
    공식 종가와 봉 종가가 미세하게 달라 자주 빗나간다(실측에서 10종목 중 4종목 실패).
    `prepost=True` intraday의 마지막 바가 `max_age_hours` 이내로 신선하면 그 값을 쓰고,
    비어 있거나 오래됐으면(주말·휴장·데이터 지연) fast_last를 유지한다(fail-open).
    """
    if intraday is None or len(intraday) == 0:
        return float(fast_last) if fast_last else None
    closes = intraday["Close"].dropna()
    if not len(closes):
        return float(fast_last) if fast_last else None

    last_ts = closes.index[-1]
    if now is None:
        now = datetime.now(last_ts.tzinfo) if last_ts.tzinfo else datetime.now()
    age_h = (now - last_ts).total_seconds() / 3600.0
    if age_h > max_age_hours:
        # 마지막 체결이 너무 오래됨 — 주말·휴장 구간이라 연장시간대가 아니다.
        return float(fast_last) if fast_last else float(closes.iloc[-1])
    last = float(closes.iloc[-1])
    # 정규장 종가에서 25% 넘게 벌어진 연장시간대 값은 쓰지 않는다 — 2026-11-05 SOXX 144달러 vs 종가 450달러(§79)
    if fast_last and abs(last / float(fast_last) - 1) > 0.25:
        print(f"[fetch_data] 연장시간대 값 무시: {last} vs 종가 {fast_last}", file=sys.stderr)
        return float(fast_last)
    return last


# ── 네이버 프리·애프터장 체결가 — 야후가 오늘 연장시간대 봉을 비워 줄 때의 대신(2026-11-11 실사고) ──
# 그날 야후는 나스닥 상장 종목 전부(NVDA·AAPL·MSFT…)의 1분·5분봉을 비워 줬다(NYSE·Arca는 정상).
# 5분봉 이틀치에서 '마지막 봉'은 어제 애프터장 체결이었고, 12시간 신선도 검사를 통과해 그 값이
# '지금 프리마켓'으로 쓰일 뻔했다. 홈 API(api/stocks-live.mjs naverExtendedQuote)와 같은 규칙이다(§30).
_NAVER_US_SUFFIX: dict = {}
_ET = pytz.timezone("America/New_York")


def _naver_us_basic(ticker: str):
    """네이버 해외 시세 basic. 거래소 접미사(.O 나스닥 · 없음 NYSE · .N · .K Arca)를 차례로 시도하고 맞은 것을 기억한다."""
    sufs = [_NAVER_US_SUFFIX[ticker]] if ticker in _NAVER_US_SUFFIX else [".O", "", ".N", ".K"]
    for suf in sufs:
        try:
            req = urllib.request.Request(f"https://api.stock.naver.com/stock/{ticker}{suf}/basic",
                                         headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read().decode())
            if d.get("closePrice") is None:
                continue
            _NAVER_US_SUFFIX[ticker] = suf
            return d
        except Exception:
            continue
    return None


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def naver_extended_quote(d: dict, now=None):
    """네이버 basic 응답에서 (현재가, 기준가)를 꺼낸다. 프리·애프터장이 열려 있고 오늘(뉴욕 날짜) 체결일 때만.

    '3시간 안'이 아니라 '오늘'로 본다(2026-11-16) — NYSE 은행주는 이른 프리마켓에 04:00 체결 하나 뒤
    07:05까지 체결이 없어(MS) 3시간 기준이면 오늘 체결가를 버렸다. 11/11 사고는 어제 체결을 오늘로 쓴 것이라
    날짜만 보면 막힌다.

    기준가는 closePrice — 프리장엔 직전 정규장 종가, 애프터장엔 그날 정규장 종가다(§30).
    정규장 종가에서 25% 넘게 벌어지면 시세가 아니라 데이터 문제로 본다(§79). 아니면 None.
    """
    o = (d or {}).get("overMarketPriceInfo") or {}
    if o.get("tradingSessionType") not in ("PRE_MARKET", "AFTER_MARKET") or o.get("overMarketStatus") != "OPEN":
        return None
    price, base = _num(o.get("overPrice")), _num((d or {}).get("closePrice"))
    if not price or not base or price <= 0 or base <= 0:
        return None
    try:
        at = datetime.fromisoformat(str(o.get("localTradedAt")))
    except ValueError:
        return None
    if at.tzinfo is None:
        return None
    now = now or datetime.now(pytz.utc)
    if at.astimezone(_ET).date() != now.astimezone(_ET).date() or at > now + timedelta(minutes=5):
        return None
    if abs(price / base - 1) > 0.25:
        return None
    return price, base


def _yahoo_extended_fresh(intraday, now=None) -> bool:
    """야후 연장시간대 시계열에 '오늘(뉴욕 날짜)' 체결이 있는가. 어제 애프터장 봉은 오늘 프리마켓이 아니다.
    몇 시간 전 체결이어도 오늘 것이면 그게 지금 값이다(2026-11-16 MS — 04:00 체결 뒤 07:05까지 거래 없음)."""
    if intraday is None or len(intraday) == 0:
        return False
    closes = intraday["Close"].dropna()
    if not len(closes):
        return False
    last = closes.index[-1]
    if last.tzinfo is None:
        return False
    now_et = (now or datetime.now(pytz.utc)).astimezone(_ET)
    last_et = last.tz_convert(_ET) if hasattr(last, "tz_convert") else last.astimezone(_ET)
    return last_et.date() == now_et.date()


def _is_us_equity(ticker: str) -> bool:
    return not any(c in ticker for c in "=^.")


# 야후가 연장시간대 체결을 못 준 종목 — 실행이 끝나면 관리자에게 한 번에 알린다(2026-11-11 사용자 요청).
# {"ticker": ..., "how": "naver"(네이버로 대신) | "missing"(둘 다 없어 비움)}
FEED_ISSUES: list = []


FEED_ALERT_MIN_SUB = 3   # 네이버로 대신한 종목이 이만큼 넘을 때만 알린다 — 한두 종목은 체결이 드물거나 야후 봉이 늦게 올라온 것


def feed_alert_text(issues: list, btype: str) -> str:
    """수집 불가 알림 문구(평문, §37). 알릴 것이 없으면 빈 문자열.

    알리는 경우는 둘이다 — 오늘 체결가를 아무 데서도 못 구한 종목이 있거나(값이 직전 정규장 종가로 남는다),
    네이버로 대신한 종목이 FEED_ALERT_MIN_SUB개 이상이거나(11/11처럼 야후가 통째로 비운 날).
    2026-11-16 GS 한 종목 대신·MS 한 종목(실제로는 오늘 04:00 체결)으로 잘못 울렸다."""
    sub = sorted({i["ticker"] for i in issues if i["how"] == "naver"})
    gone = sorted({i["ticker"] for i in issues if i["how"] == "missing"})
    if not gone and len(sub) < FEED_ALERT_MIN_SUB:
        return ""
    label = {"kospi": "코스피 아침", "us": "미국"}.get(btype, btype)
    lines = [f"⚠️ 야후 미국 시세 수집 불가 — {label} 브리핑 수집 중", "야후가 오늘 프리·애프터장 체결을 주지 않았어요."]
    if sub:
        lines.append(f"네이버 체결가로 대신 {len(sub)}종목: {', '.join(sub)}")
    if gone:
        lines.append(f"네이버에도 오늘 체결이 없어 직전 정규장 종가로 남은 {len(gone)}종목: {', '.join(gone)} — 등락이 '지금'이 아니라 직전 정규장 것이에요.")
    lines.append("홈 '지금 미국'도 같은 원천이라 함께 영향을 받아요(§85).")
    return "\n".join(lines)


def alert_feed_issues(btype: str) -> None:
    msg = feed_alert_text(FEED_ISSUES, btype)
    if not msg:
        if FEED_ISSUES:      # 알릴 만큼은 아니어도 로그엔 남긴다
            print(f"[fetch_data] 네이버로 대신한 종목(알림 기준 미만): {sorted({i['ticker'] for i in FEED_ISSUES})}",
                  file=sys.stderr)
        return
    print(f"[fetch_data] {msg}", file=sys.stderr)
    try:
        from send_telegram import send_admin_alert
        send_admin_alert(msg)
    except Exception as e:      # 알림 실패가 수집을 막지 않는다
        print(f"[fetch_data] 관리자 알림 실패: {e}", file=sys.stderr)


def _get_realtime_price(ticker: str) -> tuple[float, float] | None:
    """장 중/프리마켓 현재가와 전일 종가를 반환한다.

    fast_info로 기준가(전일 종가)를 잡되, 현재가는 prepost intraday로 교차 검증해
    **연장시간대 체결을 반영한다**(fast_info는 프리·애프터를 반영하지 않는다 — 위 함수 참조).
    실패 시 None 반환 → 호출부에서 일봉 fallback 처리.
    """
    import yfinance as yf

    # pin이 걸린 티커는 "그 시각엔 아직 장이 안 열렸다"가 전제이므로 실시간가를 쓰지 않는다.
    # 호출부가 일봉 close[-1] vs close[-2] 폴백으로 내려간다(§0 코스피 아침 기준).
    if _pin_date_for(ticker) is not None:
        return None

    intraday = None
    try:
        intraday = _yf_history(ticker, period="2d", interval="5m", prepost=True)
    except Exception:
        intraday = None

    # 0순위: 미국 개별주·ETF가 프리·애프터장인데 야후에 오늘 체결이 없으면 네이버 체결가(2026-11-11).
    if _is_us_equity(ticker) and not _yahoo_extended_fresh(intraday):
        nb = _naver_us_basic(ticker)
        nq = naver_extended_quote(nb)
        if nq:
            print(f"[fetch_data] {ticker} 야후에 오늘 연장시간대 체결 없음 → 네이버 {nq[0]:.2f} (기준 {nq[1]:.2f})",
                  file=sys.stderr)
            FEED_ISSUES.append({"ticker": ticker, "how": "naver"})
            return nq
        o = (nb or {}).get("overMarketPriceInfo") or {}
        if o.get("tradingSessionType") in ("PRE_MARKET", "AFTER_MARKET") and o.get("overMarketStatus") == "OPEN":
            # 연장시간대가 열려 있는데 야후·네이버 모두 오늘 체결이 없다 — 직전 정규장 종가(fast_info)로 내려간다.
            # 야후 시계열의 마지막 봉은 어제 애프터장이라 '지금'으로 쓰지 않는다(11/11 사고와 같은 이유).
            FEED_ISSUES.append({"ticker": ticker, "how": "missing"})
            intraday = None

    # 1순위: fast_info (기준가) + intraday 교차 검증 (현재가)
    try:
        fi = yf.Ticker(ticker).fast_info
        last = fi.last_price
        prev = fi.previous_close
        if last and prev and float(last) > 0 and float(prev) > 0:
            live = _extended_hours_price(intraday, float(last))
            if live and live > 0 and abs(live - float(last)) > 0.005:
                print(
                    f"[fetch_data] {ticker} 연장시간대 체결 반영: "
                    f"{float(last):.2f} → {live:.2f}",
                    file=sys.stderr,
                )
            return float(live or last), float(prev)
    except Exception:
        pass

    # 2순위: fast_info 실패 시 intraday만으로 구성
    try:
        if intraday is not None and not intraday.empty:
            intraday_closes = intraday["Close"].dropna()
            if len(intraday_closes) > 0:
                # 전일 종가는 intraday에서 날짜 경계로 구분
                today = intraday_closes.index[-1].date()
                prev_closes = intraday_closes[intraday_closes.index.date < today]
                if not prev_closes.empty:
                    return float(intraday_closes.iloc[-1]), float(prev_closes.iloc[-1])
    except Exception:
        pass

    return None


def _recent_sessions(closes, n: int = 3) -> list:
    """일봉 종가에서 최근 n개 세션의 날짜별 등락률. 거래소 현지 날짜를 그대로 쓴다."""
    out = []
    vals = closes.dropna()
    for i in range(max(1, len(vals) - n), len(vals)):
        prev, cur = float(vals.iloc[i - 1]), float(vals.iloc[i])
        if prev > 0:
            out.append({"date": vals.index[i].strftime("%Y-%m-%d"), "pct": round((cur / prev - 1) * 100, 2)})
    return out


def _ma200_position(closes, now=None) -> dict:
    """정규장 종가의 200일선 이격 — 종목 홈 구조 신호(§68 ⑤). 진행 중인 오늘 봉은 종가가 아니라서 뺀다."""
    now = now or datetime.now(pytz.timezone("America/New_York"))
    vals = closes
    if len(vals) and vals.index[-1].strftime("%Y-%m-%d") == now.strftime("%Y-%m-%d") and now.hour < 16:
        vals = vals.iloc[:-1]
    if len(vals) < 200:
        return {}
    ma200 = float(vals.iloc[-200:].mean())
    if ma200 <= 0:
        return {}
    return {"close_date": vals.index[-1].strftime("%Y-%m-%d"),
            "ma200_close_pct": round((float(vals.iloc[-1]) / ma200 - 1) * 100, 2)}


def get_ticker_full(ticker: str) -> dict:
    """
    Fetch 1 year daily history for a ticker.
    Returns: price, change_pct, volume, sparkline (10 daily closes),
             ma20, ma20_dist_pct, ma20_sparkline (10 pts),
             ma200, ma200_dist_pct, ma200_sparkline (10 pts).
    """
    try:
        hist = _yf_history(ticker, period="1y")
        if len(hist) < 2:
            return {"error": "insufficient data"}

        closes = hist["Close"].dropna()

        # 장 중/프리마켓 실시간 가격 우선, 실패 시 일봉 fallback
        rt = _get_realtime_price(ticker)
        if rt is not None:
            price, prev_price = rt
            # fast_info.previous_close가 과거 세션 종가를 주는 경우가 있어 일봉으로 교정
            fixed = _prev_close_from_daily(closes, price)
            if fixed and abs(fixed - prev_price) / fixed > 1e-4:
                print(f"[fetch_data] {ticker}: previous_close 교정 {prev_price:.4f} → {fixed:.4f}",
                      file=sys.stderr)
                prev_price = fixed
        else:
            price = float(closes.iloc[-1])
            prev_price = float(closes.iloc[-2])
        change_pct = (price - prev_price) / prev_price * 100

        # Futures rollover guard: same as build_sidebar_market_data.
        # Applies to commodity/rate futures (BZ=F, CL=F, GC=F, ^TNX, etc.) ONLY —
        # 개별주에 적용하면 프리마켓 실체결가를 롤오버 갭으로 오인해 되돌린다.
        try:
            h = _yf_history(ticker, period="5d", interval="1h") \
                if _is_futures_like(ticker) else None
            hc = h["Close"].dropna() if h is not None else []
            if len(hc) >= 25:
                hp = float(hc.iloc[-1])
                gap = abs(price - hp) / hp if hp != 0 else 0
                if gap > 0.03:
                    hp_prev = float(hc.iloc[max(0, len(hc) - 25)])
                    price = hp
                    change_pct = (hp - hp_prev) / hp_prev * 100 if hp_prev != 0 else 0
                    print(
                        f"[fetch_data] {ticker}: rollover detected (gap={gap:.1%}) → hourly override",
                        file=sys.stderr,
                    )
        except Exception:
            pass

        result = {
            "price":      round(price, 4),
            "change_pct": round(change_pct, 4),
            "volume":     int(hist["Volume"].iloc[-1]),
            "sparkline":  [round(float(p), 4) for p in closes.iloc[-20:].tolist()],
        }

        # 미국 종목의 정규장 마감 뒤 움직임 — change_pct는 '어제 종가 대비 지금 시간외 가격'이라 정규장 등락과
        # 마감 뒤 실적 반응이 한 숫자에 섞인다(2026-11-18: 엔비디아 정규장 하락 + 06:20 실적 뒤 시간외 +3%가
        # 한 값으로 들어가 실적 반응이 전달되지 않았다). 지금 가격이 마지막 일봉(직전 정규장) 종가와 다를 때만 둔다.
        if rt is not None and _is_us_equity(ticker) and len(closes) >= 2:
            reg = float(closes.iloc[-1])
            if reg > 0 and abs(price / reg - 1) > 1e-4:
                result["regular_close"] = round(reg, 4)
                result["regular_change_pct"] = round((reg / float(closes.iloc[-2]) - 1) * 100, 2)
                result["since_close_pct"] = round((price / reg - 1) * 100, 2)

        # 최근 세션 일지 — 사건을 실제로 일어난 날짜에 붙이게 하는 근거(2026-10-26: 목요일 메타 충격을 '지난 금요일'로 씀).
        result["recent_sessions"] = _recent_sessions(closes)

        # 52주 고·저 — hist가 이미 1년치라 추가 조회 비용이 없다.
        # 모델이 "사상 최고" 같은 최상급을 쓰려면 지금 값이 고점 대비 어디인지를 알아야 한다.
        # 이 값이 없어서 2026-08-24·08-26 코스피 아침 브리핑이 S&P500을 "사상 최고"로 쓰고
        # §28 게이트에 걸려 발행이 통째로 막혔다(실측은 52주 고점 대비 -1.6%).
        # validate_analysis._index_extremes()가 발행 직전에 같은 값을 다시 재는 게 최종 방어선이고,
        # 여기 있는 값은 모델에게 미리 알려주는 1차 방어다.
        hi52 = float(closes.max())
        lo52 = float(closes.min())
        result["high_52w"] = round(hi52, 4)
        result["low_52w"] = round(lo52, 4)
        if hi52 > 0:
            result["pct_from_52w_high"] = round((price - hi52) / hi52 * 100, 2)
        if lo52 > 0:
            result["pct_from_52w_low"] = round((price - lo52) / lo52 * 100, 2)

        if len(closes) >= 20:
            ma20_series = closes.rolling(20).mean().dropna()
            ma20 = float(ma20_series.iloc[-1])
            result["ma20"] = round(ma20, 4)
            result["ma20_dist_pct"] = round((price - ma20) / ma20 * 100, 2)
            result["ma20_sparkline"] = [round(float(v), 4) for v in ma20_series.iloc[-20:].tolist()]

            # MA20 signal: crossing_up = previously below, now above
            if len(ma20_series) >= 2:
                prev_close = float(closes.iloc[-2])
                prev_ma20 = float(ma20_series.iloc[-2])
                if prev_close < prev_ma20 and price >= ma20:
                    result["ma20_signal"] = "crossing_up"
                elif prev_close >= prev_ma20 and price < ma20:
                    result["ma20_signal"] = "crossing_down"
                elif price >= ma20:
                    result["ma20_signal"] = "above"
                else:
                    result["ma20_signal"] = "below"

        if len(closes) >= 200:
            ma200_series = closes.rolling(200).mean().dropna()
            ma200 = float(ma200_series.iloc[-1])
            result["ma200"] = round(ma200, 4)
            result["ma200_dist_pct"] = round((price - ma200) / ma200 * 100, 2)
            result["ma200_sparkline"] = [round(float(v), 4) for v in ma200_series.iloc[-20:].tolist()]
            result.update(_ma200_position(closes))

        return result
    except Exception as e:
        return {"error": str(e)}


def get_hourly_sparkline(ticker: str, n: int = 10) -> list:
    """Get last n hourly closing prices for sidebar sparklines."""
    try:
        hist = _yf_history(ticker, period="5d", interval="1h")
        closes = hist["Close"].dropna()
        if len(closes) > 0:
            return [round(float(p), 4) for p in closes.iloc[-n:].tolist()]
    except Exception as e:
        print(f"[fetch_data] Hourly sparkline error {ticker}: {e}", file=sys.stderr)
    return []
