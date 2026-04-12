#!/usr/bin/env python3
"""
Market data fetcher for DailyB Investment Assistant.
Fetches data via yfinance for KOSPI morning, US evening, and weekly briefings.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")
UTC = pytz.utc


def get_yfinance_data(tickers: list[str]) -> dict:
    """Fetch latest data for a list of tickers via yfinance."""
    try:
        import yfinance as yf
        results = {}
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                info = t.fast_info
                hist = t.history(period="2d")
                if len(hist) >= 1:
                    latest = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
                    price = float(latest["Close"])
                    prev_price = float(prev["Close"])
                    change_pct = (price - prev_price) / prev_price * 100
                    results[ticker] = {
                        "price": round(price, 2),
                        "change_pct": round(change_pct, 2),
                        "volume": int(latest.get("Volume", 0)),
                    }
                    # Add MA20/MA200 if enough history
                    hist_long = t.history(period="1y")
                    if len(hist_long) >= 20:
                        ma20 = float(hist_long["Close"].rolling(20).mean().iloc[-1])
                        results[ticker]["ma20"] = round(ma20, 2)
                        results[ticker]["ma20_dist_pct"] = round(
                            (price - ma20) / ma20 * 100, 2
                        )
                    if len(hist_long) >= 200:
                        ma200 = float(hist_long["Close"].rolling(200).mean().iloc[-1])
                        results[ticker]["ma200"] = round(ma200, 2)
                        results[ticker]["ma200_dist_pct"] = round(
                            (price - ma200) / ma200 * 100, 2
                        )
            except Exception as e:
                results[ticker] = {"error": str(e)}
        return results
    except ImportError:
        return {"error": "yfinance not installed. Run: pip install yfinance"}


def fetch_kospi_data() -> dict:
    """Fetch all data needed for KOSPI morning briefing."""
    tickers = {
        "us_indices": ["^GSPC", "^IXIC", "^DJI"],  # S&P500, NASDAQ, Dow
        "semiconductor": ["^SOX"],                   # Philadelphia SOX
        "korea_etf": ["EWY"],                        # MSCI Korea ETF
        "volatility": ["^VIX"],
        "currency": ["DX-Y.NYB"],                    # Dollar Index
        "oil": ["CL=F", "BZ=F"],                    # WTI, Brent
        "rates": ["^TNX"],                           # US 10Y Treasury
        "gold": ["GC=F"],
        "bigtech": ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"],
    }

    all_tickers = []
    for group in tickers.values():
        all_tickers.extend(group)

    raw = get_yfinance_data(all_tickers)

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "kospi",
        "us_indices": {
            "sp500": raw.get("^GSPC", {}),
            "nasdaq": raw.get("^IXIC", {}),
            "dow": raw.get("^DJI", {}),
        },
        "sox": raw.get("^SOX", {}),
        "ewy": raw.get("EWY", {}),
        "vix": raw.get("^VIX", {}),
        "dxy": raw.get("DX-Y.NYB", {}),
        "oil": {
            "wti": raw.get("CL=F", {}),
            "brent": raw.get("BZ=F", {}),
        },
        "rates": {
            "us10y": raw.get("^TNX", {}),
        },
        "gold": raw.get("GC=F", {}),
        "bigtech": {
            "NVDA": raw.get("NVDA", {}),
            "AAPL": raw.get("AAPL", {}),
            "MSFT": raw.get("MSFT", {}),
            "AMZN": raw.get("AMZN", {}),
            "META": raw.get("META", {}),
            "GOOGL": raw.get("GOOGL", {}),
        },
    }

    out_path = DATA_DIR / "latest_kospi.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_data] KOSPI data saved → {out_path}")
    return data


def fetch_us_data() -> dict:
    """Fetch all data needed for US market evening briefing."""
    tickers_to_fetch = [
        "^GSPC", "^IXIC", "^DJI",          # Indices
        "ES=F", "NQ=F", "YM=F",             # Futures
        "^VIX",
        "DX-Y.NYB",                          # DXY
        "^TNX",                              # 10Y rate
        "CL=F", "BZ=F",                     # Oil
        "GC=F",                              # Gold
        "^N225", "^KS11", "^HSI",           # Asia
        "^GDAXI", "^FTSE", "^FCHI",         # Europe
        "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA",
    ]

    raw = get_yfinance_data(tickers_to_fetch)

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "us",
        "indices": {
            "sp500": raw.get("^GSPC", {}),
            "nasdaq": raw.get("^IXIC", {}),
            "dow": raw.get("^DJI", {}),
        },
        "futures": {
            "sp500_fut": raw.get("ES=F", {}),
            "nasdaq_fut": raw.get("NQ=F", {}),
            "dow_fut": raw.get("YM=F", {}),
        },
        "vix": raw.get("^VIX", {}),
        "dxy": raw.get("DX-Y.NYB", {}),
        "rates": {"us10y": raw.get("^TNX", {})},
        "oil": {
            "wti": raw.get("CL=F", {}),
            "brent": raw.get("BZ=F", {}),
        },
        "gold": raw.get("GC=F", {}),
        "asia": {
            "nikkei": raw.get("^N225", {}),
            "kospi": raw.get("^KS11", {}),
            "hangseng": raw.get("^HSI", {}),
        },
        "europe": {
            "dax": raw.get("^GDAXI", {}),
            "ftse": raw.get("^FTSE", {}),
            "cac": raw.get("^FCHI", {}),
        },
        "bigtech": {
            t: raw.get(t, {})
            for t in ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA"]
        },
    }

    out_path = DATA_DIR / "latest_us.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_data] US data saved → {out_path}")
    return data


def fetch_weekly_data() -> dict:
    """Fetch weekly summary data."""
    tickers_to_fetch = [
        "^GSPC", "^IXIC", "^DJI", "^KS11",
        "^VIX", "DX-Y.NYB", "^TNX",
        "CL=F", "GC=F",
        "^SOX", "EWY",
    ]

    raw = get_yfinance_data(tickers_to_fetch)

    # Weekly change calculation
    weekly_data = {}
    try:
        import yfinance as yf
        for ticker in tickers_to_fetch:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="10d")
                if len(hist) >= 5:
                    week_end = float(hist["Close"].iloc[-1])
                    week_start = float(hist["Close"].iloc[-5])
                    weekly_change = (week_end - week_start) / week_start * 100
                    weekly_data[ticker] = round(weekly_change, 2)
            except Exception:
                pass
    except ImportError:
        pass

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "weekly",
        "weekly_changes": weekly_data,
        "latest": raw,
    }

    out_path = DATA_DIR / "latest_weekly.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_data] Weekly data saved → {out_path}")
    return data


def main():
    parser = argparse.ArgumentParser(description="Fetch market data for DailyB")
    parser.add_argument(
        "--type",
        choices=["kospi", "us", "weekly"],
        required=True,
        help="Type of briefing data to fetch",
    )
    args = parser.parse_args()

    try:
        if args.type == "kospi":
            fetch_kospi_data()
        elif args.type == "us":
            fetch_us_data()
        elif args.type == "weekly":
            fetch_weekly_data()
        print(f"[fetch_data] Done — type={args.type}")
    except Exception as e:
        print(f"[fetch_data] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
