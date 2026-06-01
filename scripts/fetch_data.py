#!/usr/bin/env python3
"""
Market data fetcher for DailyB Investment Assistant.
Pre-collects ALL data needed for briefings so Claude makes ≤3 web searches per run.
"""

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")
UTC = pytz.utc

# Korean stock candidates for Kellogg strategy screening
KOSPI_CANDIDATES = [
    ("005930.KS", "삼성전자"),
    ("000660.KS", "SK하이닉스"),
    ("042700.KS", "한미반도체"),
    ("005490.KS", "POSCO홀딩스"),
    ("035420.KS", "NAVER"),
    ("000270.KS", "기아"),
    ("005380.KS", "현대차"),
    ("068270.KS", "셀트리온"),
    ("035720.KS", "카카오"),
    ("051910.KS", "LG화학"),
    ("207940.KS", "삼성바이오로직스"),
    ("373220.KS", "LG에너지솔루션"),
    ("066570.KS", "LG전자"),
    ("012330.KS", "현대모비스"),
    ("086790.KS", "하나금융지주"),
]

# US stock candidates for Kellogg strategy screening
US_CANDIDATES = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA",
    "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC",
    "JPM", "BAC", "GS", "MS",
    "XOM", "CVX",
]

# Sidebar ticker mapping: key → yfinance ticker
SIDEBAR_TICKERS_KOSPI = {
    "kospi":  "^KS11",
    "kosdaq": "^KQ11",
    "nasdaq": "^IXIC",
    "nq":     "NQ=F",
    "dji":    "^DJI",
    "sox":    "^SOX",
    "oil":    "CL=F",
    "usd":    "USDKRW=X",
    "dxy":    "DX-Y.NYB",
}

SIDEBAR_TICKERS_US = {
    "kospi":  "^KS11",
    "kosdaq": "^KQ11",
    "nasdaq": "^IXIC",
    "nq":     "NQ=F",
    "dji":    "^DJI",
    "sox":    "^SOX",
    "oil":    "CL=F",
    "usd":    "USDKRW=X",
    "dxy":    "DX-Y.NYB",
}


def fetch_economic_calendar() -> dict:
    """ForexFactory 주간 경제 캘린더에서 고영향 이벤트를 가져온다 (무료, API 키 불필요).

    Returns:
        {
          "today": [...],    # 오늘 KST 기준 고영향 이벤트
          "upcoming": [...], # 향후 5일 고영향 이벤트 (최대 10개)
        }
    """
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 DailyB/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read().decode("utf-8"))

        KEY_COUNTRIES = {"USD", "CNY", "KRW", "JPY", "EUR"}
        kst_now = datetime.now(KST)
        today_kst = kst_now.strftime("%Y-%m-%d")

        high_impact_events = []
        for ev in events:
            if ev.get("impact") not in ("High",):
                continue
            if ev.get("country") not in KEY_COUNTRIES:
                continue

            date_raw = ev.get("date", "")
            date_kst_str = ""
            date_kst_date = ""
            try:
                dt = datetime.fromisoformat(date_raw)
                dt_kst = dt.astimezone(KST)
                date_kst_str = dt_kst.strftime("%Y-%m-%d %H:%M KST")
                date_kst_date = dt_kst.strftime("%Y-%m-%d")
            except Exception:
                pass

            high_impact_events.append({
                "title":    ev.get("title", ""),
                "country":  ev.get("country", ""),
                "impact":   ev.get("impact", ""),
                "date_kst": date_kst_str,
                "date_kst_date": date_kst_date,
                "forecast": ev.get("forecast", ""),
                "previous": ev.get("previous", ""),
                "actual":   ev.get("actual", ""),
            })

        today_events    = [e for e in high_impact_events if e["date_kst_date"] == today_kst]
        upcoming_events = [e for e in high_impact_events if e["date_kst_date"] > today_kst]

        print(f"[fetch_data] Economic calendar: today={len(today_events)}, upcoming={len(upcoming_events[:10])}")
        return {"today": today_events, "upcoming": upcoming_events[:10]}

    except Exception as e:
        print(f"[fetch_data] Economic calendar error: {e}", file=sys.stderr)
        return {"today": [], "upcoming": []}


def fetch_investor_trading_kospi(date_str: str = None) -> dict:
    """pykrx(KRX 공식 데이터)에서 코스피 투자자별 순매수를 가져온다.

    코스피 조회 기준일: 당일 시장 개장 전이므로 전 거래일 데이터 사용.
    휴장일·주말이면 직전 거래일까지 최대 7일 역행한다.

    Returns:
        {
          "date": "YYYYMMDD",
          "foreign":     {"net": int},  # 외국인 순매수 (단위: 백만원)
          "institution": {"net": int},  # 기관합계 순매수
          "individual":  {"net": int},  # 개인 순매수
        }
        실패 시 빈 dict.
    """
    try:
        from pykrx import stock
    except ImportError as e:
        print(f"[fetch_data] Investor trading: pykrx import 실패 ({e})", file=sys.stderr)
        return {}

    # 조회 시작점: 명시 date 또는 전일
    if date_str:
        cursor = datetime.strptime(date_str, "%Y%m%d")
    else:
        cursor = datetime.now(KST) - timedelta(days=1)

    for _ in range(7):  # 휴장일 감안해 직전 거래일까지 역행
        d = cursor.strftime("%Y%m%d")
        try:
            df = stock.get_market_trading_value_by_investor(d, d, "KOSPI")
        except Exception as e:
            print(f"[fetch_data] Investor trading pykrx error ({d}): {e}", file=sys.stderr)
            df = None

        if df is not None and not df.empty and "순매수" in df.columns:
            def net_of(label: str) -> int:
                # pykrx는 원 단위 반환 → 백만원으로 변환
                return int(df.loc[label, "순매수"]) // 1_000_000 if label in df.index else 0

            result = {
                "date":        d,
                "foreign":     {"net": net_of("외국인")},
                "institution": {"net": net_of("기관합계")},
                "individual":  {"net": net_of("개인")},
            }
            print(f"[fetch_data] Investor trading ({d}): "
                  f"foreign={result['foreign']['net']:+,}, "
                  f"institution={result['institution']['net']:+,} (단위: 백만원)")
            return result

        cursor -= timedelta(days=1)

    print("[fetch_data] Investor trading: 최근 7일 내 데이터 없음", file=sys.stderr)
    return {}


def _yf_history(ticker: str, retries: int = 3, **kwargs):
    """yfinance history() 호출을 최대 retries회 exponential backoff으로 재시도한다."""
    import yfinance as yf
    import pandas as pd
    last_exc = None
    for attempt in range(retries):
        try:
            hist = yf.Ticker(ticker).history(**kwargs)
            if not hist.empty:
                return hist
        except Exception as e:
            last_exc = e
        if attempt < retries - 1:
            delay = 2 ** attempt
            print(f"[fetch_data] {ticker} fetch failed (attempt {attempt + 1}/{retries}), retry in {delay}s", file=sys.stderr)
            time.sleep(delay)
    if last_exc:
        print(f"[fetch_data] {ticker} all retries failed: {last_exc}", file=sys.stderr)
    return pd.DataFrame()


def get_fear_greed() -> dict:
    """Fetch CNN Fear & Greed Index from alternative.me (free, no auth)."""
    try:
        url = "https://api.alternative.me/fng/?limit=365"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode())
        entries = raw.get("data", [])
        if not entries:
            return {}

        def val_at(idx):
            return int(entries[idx]["value"]) if idx < len(entries) else None

        return {
            "value":          val_at(0),
            "prev":           val_at(1),
            "1w":             val_at(7),
            "1m":             val_at(30),
            "1y":             val_at(364),
            "timestamp":      entries[0].get("timestamp"),       # Unix timestamp (str)
            "classification": entries[0].get("value_classification"),  # e.g. "Extreme Fear"
        }
    except Exception as e:
        print(f"[fetch_data] Fear & Greed API error: {e}", file=sys.stderr)
        return {}


def _get_realtime_price(ticker: str) -> tuple[float, float] | None:
    """장 중/프리마켓 현재가와 전일 종가를 반환한다.

    1순위: yfinance fast_info (단일 속성, 빠름)
    2순위: intraday 5m + prepost=True
    실패 시 None 반환 → 호출부에서 일봉 fallback 처리.
    """
    import yfinance as yf

    # 1순위: fast_info
    try:
        fi = yf.Ticker(ticker).fast_info
        last = fi.last_price
        prev = fi.previous_close
        if last and prev and float(last) > 0 and float(prev) > 0:
            return float(last), float(prev)
    except Exception:
        pass

    # 2순위: intraday 5m (프리마켓 포함)
    try:
        intraday = _yf_history(ticker, period="2d", interval="5m", prepost=True)
        if not intraday.empty:
            intraday_closes = intraday["Close"].dropna()
            if len(intraday_closes) > 0:
                # 전일 종가는 intraday에서 날짜 경계로 구분
                import pandas as pd
                today = intraday_closes.index[-1].date()
                prev_closes = intraday_closes[intraday_closes.index.date < today]
                if not prev_closes.empty:
                    return float(intraday_closes.iloc[-1]), float(prev_closes.iloc[-1])
    except Exception:
        pass

    return None


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
        else:
            price = float(closes.iloc[-1])
            prev_price = float(closes.iloc[-2])
        change_pct = (price - prev_price) / prev_price * 100

        # Futures rollover guard: same as build_sidebar_market_data.
        # Applies to commodity/rate futures (BZ=F, CL=F, GC=F, ^TNX, etc.).
        try:
            h = _yf_history(ticker, period="5d", interval="1h")
            hc = h["Close"].dropna()
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

        # 가격 데이터 날짜 기록 — 발행 시점 데이터 검증용
        last_close_date = closes.index[-1]
        if hasattr(last_close_date, "date"):
            last_close_date = last_close_date.date()
        price_date = str(last_close_date)

        # 최신 거래일 대비 stale 여부 경고 (2 거래일 이상 차이 시)
        kst_today = datetime.now(KST).date()
        from datetime import date as date_type
        if isinstance(last_close_date, str):
            import datetime as _dt
            last_close_date = _dt.date.fromisoformat(last_close_date)
        days_old = (kst_today - last_close_date).days
        if days_old > 5:  # 주말+휴일 감안해 5일 초과면 경고
            print(
                f"[fetch_data] WARNING: {ticker} price data may be stale "
                f"(last close: {price_date}, today: {kst_today}, gap: {days_old}d)",
                file=sys.stderr,
            )

        result = {
            "price":      round(price, 4),
            "change_pct": round(change_pct, 4),
            "price_date": price_date,   # 데이터 신선도 검증용
            "volume":     int(hist["Volume"].iloc[-1]),
            "sparkline":  [round(float(p), 4) for p in closes.iloc[-20:].tolist()],
        }

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


def build_sidebar_market_data(sidebar_map: dict) -> dict:
    """
    Build the window.MARKET_DATA object for sidebar injection.
    Returns dict ready to be JSON-serialised as window.MARKET_DATA.
    """
    import math

    market_data = {}
    for key, ticker in sidebar_map.items():
        try:
            # Use 1mo period for reliability (5d can be too short after long weekends)
            hist = _yf_history(ticker, period="1mo")
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                print(f"[fetch_data] sidebar {key}/{ticker}: insufficient data ({len(closes)} closes)", file=sys.stderr)
                continue

            # 장 중/프리마켓 실시간 가격 우선, 실패 시 일봉 fallback
            rt = _get_realtime_price(ticker)
            if rt is not None:
                price, prev = rt
            else:
                price = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])

            if math.isnan(price) or math.isnan(prev) or prev == 0:
                print(f"[fetch_data] sidebar {key}/{ticker}: invalid price (price={price}, prev={prev})", file=sys.stderr)
                continue
            chg = round((price - prev) / prev * 100, 2)

            # Fetch hourly data: used for sparkline and futures rollover sanity check.
            # Futures contracts (CL=F, BZ=F, NQ=F, etc.) roll monthly — the "last daily close"
            # from yfinance can jump to the new contract's price, creating a 4-8% artificial gap.
            # If daily close deviates >3% from the latest hourly close, the daily data is stale
            # due to rollover; override with hourly-based price and 24h-ago comparison.
            hourly_hist = _yf_history(ticker, period="5d", interval="1h")
            hourly_closes = hourly_hist["Close"].dropna()

            if len(hourly_closes) >= 2:
                hourly_price = float(hourly_closes.iloc[-1])
                gap = abs(price - hourly_price) / hourly_price if hourly_price != 0 else 0
                if gap > 0.03:
                    # Rollover detected: switch to hourly-based price and 24h change
                    hourly_prev = float(hourly_closes.iloc[max(0, len(hourly_closes) - 25)])
                    price = round(hourly_price, 2)
                    chg = round((hourly_price - hourly_prev) / hourly_prev * 100, 2) if hourly_prev != 0 else 0
                    print(
                        f"[fetch_data] sidebar {key}/{ticker}: rollover detected "
                        f"(daily={closes.iloc[-1]:.2f}, hourly={hourly_price:.2f}, gap={gap:.1%}) "
                        f"→ switched to hourly data",
                        file=sys.stderr,
                    )
                sparkline = [round(float(p), 4) for p in hourly_closes.iloc[-10:].tolist()]
            else:
                sparkline = [round(float(p), 4) for p in closes.iloc[-10:].tolist()]

            market_data[key] = {
                "base": round(price, 2),
                "chg":  chg,
                "data": sparkline,
            }
            print(f"[fetch_data] sidebar {key}: {price:.2f} ({chg:+.2f}%) [{len(sparkline)} pts]")
        except Exception as e:
            print(f"[fetch_data] sidebar {key}/{ticker}: {e}", file=sys.stderr)

    return market_data


def build_stock_candidates(candidates: list[tuple]) -> list[dict]:
    """
    Fetch full data for stock candidates and sort by Kellogg signal quality.
    Returns list of candidate dicts including sparklines for stockCharts injection.
    """
    result = []
    for ticker, name in candidates:
        data = get_ticker_full(ticker)
        if "error" in data:
            print(f"[fetch_data] candidate {ticker} ({name}): {data['error']}", file=sys.stderr)
            continue

        entry = {
            "ticker":          ticker,
            "name":            name,
            "price":           data["price"],
            "change_pct":      data["change_pct"],
            "volume":          data.get("volume", 0),
            "ma20":            data.get("ma20"),
            "ma20_dist_pct":   data.get("ma20_dist_pct"),
            "ma20_signal":     data.get("ma20_signal", "unknown"),
            "ma200":           data.get("ma200"),
            "ma200_dist_pct":  data.get("ma200_dist_pct"),
            # stockCharts-ready arrays
            "sparkline":       data.get("sparkline", []),
            "ma20_sparkline":  data.get("ma20_sparkline", []),
            "ma200_sparkline": data.get("ma200_sparkline", []),
        }
        result.append(entry)

    # Sort: crossing_up first, then above with small distance, then rest
    signal_priority = {"crossing_up": 0, "above": 1, "crossing_down": 2, "below": 3, "unknown": 4}
    result.sort(key=lambda x: (
        signal_priority.get(x["ma20_signal"], 4),
        abs(x["ma20_dist_pct"] or 999),
    ))
    return result


def fetch_kospi_data() -> dict:
    """Fetch ALL data needed for KOSPI morning briefing."""
    print("[fetch_data] Fetching KOSPI data...")

    # 1. Sidebar market data (hourly sparklines + price)
    print("[fetch_data]   → sidebar market data")
    market_data_js = build_sidebar_market_data(SIDEBAR_TICKERS_KOSPI)

    # 2. Fear & Greed Index (Claude 분석용 — UI에서는 제거됨)
    print("[fetch_data]   → fear & greed index")
    fg = get_fear_greed()

    # 3. Additional macro tickers (not in sidebar)
    print("[fetch_data]   → macro tickers")
    macro_tickers = ["^GSPC", "^VIX", "BZ=F", "GC=F", "^TNX",
                     "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "^SOX", "EWY",
                     "DRAM",  # Roundhill Memory & HBM ETF (삼성·하이닉스 연동 선행 지표)
                     "^N225", "^HSI", "^TWII", "000001.SS"]  # 아시아 지역 지수 (catch-up 시그널)
    macro = {}
    for t in macro_tickers:
        d = get_ticker_full(t)
        if "error" not in d:
            macro[t] = d

    # VIX를 사이드바 market_data_js에 포함 (UI 표시용)
    if macro.get("^VIX"):
        market_data_js["vix"] = macro["^VIX"]

    # 4. Korean stock candidates (Kellogg strategy screening)
    print("[fetch_data]   → KOSPI candidates")
    kospi_candidates = build_stock_candidates(KOSPI_CANDIDATES)

    # 5. 경제 지표 캘린더 (ForexFactory)
    print("[fetch_data]   → economic calendar")
    economic_calendar = fetch_economic_calendar()

    # 6. 투자자별 순매수 (pykrx — 전 거래일)
    print("[fetch_data]   → investor trading (외국인/기관 순매수)")
    investor_trading = fetch_investor_trading_kospi()

    # 7. 휴장 직후(post-holiday catch-up) 플래그 — 한국만 단독 휴장한 다음날 판정
    print("[fetch_data]   → post-holiday catch-up flag")
    try:
        from holiday_check import was_kospi_only_closed_previous_session
        post_holiday_catchup = was_kospi_only_closed_previous_session(datetime.now(KST).date())
    except Exception as e:
        print(f"[fetch_data] post-holiday check error: {e}", file=sys.stderr)
        post_holiday_catchup = False
    print(f"[fetch_data]   post_holiday_catchup={post_holiday_catchup}")

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "kospi",
        # Ready-to-inject MARKET_DATA (just add stockCharts from picked candidates)
        "market_data_js": market_data_js,
        # Macro data
        "sp500":  macro.get("^GSPC", {}),
        "vix":    macro.get("^VIX", {}),
        "ewy":    macro.get("EWY", {}),
        "dram_etf": macro.get("DRAM", {}),  # Roundhill Memory ETF (HBM·DRAM 수요 선행)
        "oil": {
            "wti":   market_data_js.get("oil", {}),
            "brent": macro.get("BZ=F", {}),
        },
        "gold":   macro.get("GC=F", {}),
        "rates":  {"us10y": macro.get("^TNX", {})},
        "bigtech": {t: macro.get(t, {}) for t in ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]},
        "fearGreed": fg or {},
        # 경제 지표 캘린더 (오늘 + 이번주 고영향 이벤트)
        "economic_calendar": economic_calendar,
        # 투자자별 순매수 (외국인/기관/개인 — 전 거래일 KRX 기준)
        "investor_trading": investor_trading,
        # 아시아 지역 지수 (직전 거래일 종가) — 한국 단독 휴장 다음날 catch-up 시그널
        "asia_regional": {
            "nikkei":   macro.get("^N225", {}),
            "hangseng": macro.get("^HSI", {}),
            "taiwan":   macro.get("^TWII", {}),
            "shanghai": macro.get("000001.SS", {}),
        },
        # True면 어제 한국만 휴장 + 미국 개장 — EWY보다 asia_regional이 더 정확한 선행 지표
        "post_holiday_catchup": post_holiday_catchup,
        # Kellogg screening — sorted by signal quality
        # Claude picks 3-5 from this list; use sparkline/ma20_sparkline/ma200_sparkline for stockCharts
        "kospi_candidates": kospi_candidates,
    }

    out_path = DATA_DIR / "latest_kospi.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_data] KOSPI data saved → {out_path}")
    return data


def fetch_us_data() -> dict:
    """Fetch ALL data needed for US market evening briefing."""
    print("[fetch_data] Fetching US data...")

    # 1. Sidebar market data
    print("[fetch_data]   → sidebar market data")
    market_data_js = build_sidebar_market_data(SIDEBAR_TICKERS_US)

    # 2. Fear & Greed (Claude 분석용 — UI에서는 제거됨)
    print("[fetch_data]   → fear & greed index")
    fg = get_fear_greed()

    # 3. Macro + futures
    print("[fetch_data]   → macro tickers")
    macro_tickers = [
        "^GSPC", "^VIX", "^TNX", "BZ=F", "GC=F",
        "ES=F", "YM=F",
        "^N225", "^HSI",
        "^GDAXI", "^FTSE", "^FCHI",
        "DRAM",   # Roundhill Memory & HBM ETF
    ]
    macro = {}
    for t in macro_tickers:
        d = get_ticker_full(t)
        if "error" not in d:
            macro[t] = d

    # VIX를 사이드바 market_data_js에 포함 (UI 표시용)
    if macro.get("^VIX"):
        market_data_js["vix"] = macro["^VIX"]

    # 4. US stock candidates
    print("[fetch_data]   → US candidates")
    us_candidate_pairs = [(t, t) for t in US_CANDIDATES]
    us_candidates = build_stock_candidates(us_candidate_pairs)
    # Overwrite name with ticker for US stocks
    for c in us_candidates:
        c["name"] = c["ticker"]

    # 5. 경제 지표 캘린더 (ForexFactory)
    print("[fetch_data]   → economic calendar")
    economic_calendar = fetch_economic_calendar()

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "us",
        "market_data_js": market_data_js,
        "sp500":    macro.get("^GSPC", {}),
        "vix":      macro.get("^VIX", {}),
        "rates":    {"us10y": macro.get("^TNX", {})},
        "oil": {
            "wti":   market_data_js.get("oil", {}),
            "brent": macro.get("BZ=F", {}),
        },
        "gold":     macro.get("GC=F", {}),
        "futures": {
            "sp500_fut":   macro.get("ES=F", {}),
            "nasdaq_fut":  market_data_js.get("nq", {}),
            "dow_fut":     macro.get("YM=F", {}),
        },
        "asia": {
            "nikkei":   macro.get("^N225", {}),
            "kospi":    market_data_js.get("kospi", {}),
            "hangseng": macro.get("^HSI", {}),
        },
        "europe": {
            "dax":  macro.get("^GDAXI", {}),
            "ftse": macro.get("^FTSE", {}),
            "cac":  macro.get("^FCHI", {}),
        },
        "bigtech": {
            t: next((c for c in us_candidates if c["ticker"] == t), {})
            for t in ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA"]
        },
        "fearGreed": fg or {},
        "dram_etf":  macro.get("DRAM", {}),  # Roundhill Memory ETF (HBM·DRAM 수요 선행)
        # 경제 지표 캘린더 (오늘 + 이번주 고영향 이벤트)
        "economic_calendar": economic_calendar,
        "us_candidates": us_candidates,
    }

    out_path = DATA_DIR / "latest_us.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_data] US data saved → {out_path}")
    return data



def main():
    parser = argparse.ArgumentParser(description="Fetch market data for DailyB")
    parser.add_argument(
        "--type",
        choices=["kospi", "us"],
        required=True,
        help="Type of briefing data to fetch",
    )
    args = parser.parse_args()

    try:
        if args.type == "kospi":
            fetch_kospi_data()
        elif args.type == "us":
            fetch_us_data()
        print(f"[fetch_data] Done — type={args.type}")
    except Exception as e:
        print(f"[fetch_data] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
