#!/usr/bin/env python3
"""
Market data fetcher for DailyB Investment Assistant.
Pre-collects ALL data needed for briefings so Claude makes ≤3 web searches per run.
"""

import argparse
import json
import sys
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


def get_ticker_full(ticker: str) -> dict:
    """
    Fetch 1 year daily history for a ticker.
    Returns: price, change_pct, volume, sparkline (10 daily closes),
             ma20, ma20_dist_pct, ma20_sparkline (10 pts),
             ma200, ma200_dist_pct, ma200_sparkline (10 pts).
    """
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="1y")
        if len(hist) < 2:
            return {"error": "insufficient data"}

        closes = hist["Close"].dropna()
        price = float(closes.iloc[-1])
        prev_price = float(closes.iloc[-2])
        change_pct = (price - prev_price) / prev_price * 100

        result = {
            "price":      round(price, 4),
            "change_pct": round(change_pct, 4),
            "volume":     int(hist["Volume"].iloc[-1]),
            "sparkline":  [round(float(p), 4) for p in closes.iloc[-10:].tolist()],
        }

        if len(closes) >= 20:
            ma20_series = closes.rolling(20).mean().dropna()
            ma20 = float(ma20_series.iloc[-1])
            result["ma20"] = round(ma20, 4)
            result["ma20_dist_pct"] = round((price - ma20) / ma20 * 100, 2)
            result["ma20_sparkline"] = [round(float(v), 4) for v in ma20_series.iloc[-10:].tolist()]

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
            result["ma200_sparkline"] = [round(float(v), 4) for v in ma200_series.iloc[-10:].tolist()]

        return result
    except Exception as e:
        return {"error": str(e)}


def get_hourly_sparkline(ticker: str, n: int = 10) -> list:
    """Get last n hourly closing prices for sidebar sparklines."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="5d", interval="1h")
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
    import yfinance as yf

    market_data = {}
    for key, ticker in sidebar_map.items():
        try:
            # Price + change from daily history
            hist = yf.Ticker(ticker).history(period="5d")
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                continue
            price = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            chg = round((price - prev) / prev * 100, 2)

            # Hourly sparkline (last 10 hourly points)
            sparkline = get_hourly_sparkline(ticker, n=10)
            if not sparkline:
                sparkline = [round(float(p), 2) for p in closes.iloc[-10:].tolist()]

            market_data[key] = {
                "base": round(price, 2),
                "chg":  chg,
                "data": sparkline,
            }
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
                     "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "^SOX", "EWY"]
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

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "kospi",
        # Ready-to-inject MARKET_DATA (just add stockCharts from picked candidates)
        "market_data_js": market_data_js,
        # Macro data
        "sp500":  macro.get("^GSPC", {}),
        "vix":    macro.get("^VIX", {}),
        "ewy":    macro.get("EWY", {}),
        "oil": {
            "wti":   market_data_js.get("oil", {}),
            "brent": macro.get("BZ=F", {}),
        },
        "gold":   macro.get("GC=F", {}),
        "rates":  {"us10y": macro.get("^TNX", {})},
        "bigtech": {t: macro.get(t, {}) for t in ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]},
        "fearGreed": fg or {},
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
