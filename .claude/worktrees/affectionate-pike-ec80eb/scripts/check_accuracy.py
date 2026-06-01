#!/usr/bin/env python3
"""
Check prediction accuracy by comparing the predicted direction
to the actual KOSPI opening move.

Run at ~09:10 KST (00:10 UTC) — after KOSPI opens at 09:00 KST.
Updates data/briefings.json with the actual result.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pytz
import yfinance as yf

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
KST = pytz.timezone("Asia/Seoul")


# ─────────────────────────────────────────────────────────────────────────────
# Briefings JSON helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_briefings() -> dict:
    path = DATA_DIR / "briefings.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"briefings": []}


def save_briefings(data: dict) -> None:
    path = DATA_DIR / "briefings.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Market data fetch
# ─────────────────────────────────────────────────────────────────────────────

def get_kospi_open_vs_prev_close(date_str: str) -> tuple | None:
    """
    Returns (open_price, prev_close, change_pct) for the given date.
    Uses yfinance ^KS11 daily data.
    Returns None if data is unavailable.
    """
    ticker = yf.Ticker("^KS11")
    hist = ticker.history(period="10d", interval="1d")
    if hist.empty or len(hist) < 2:
        return None

    rows = list(hist.iterrows())
    for i, (idx, row) in enumerate(rows):
        idx_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        if idx_str == date_str and i > 0:
            prev_close = float(rows[i - 1][1]["Close"])
            open_price = float(row["Open"])
            change_pct = (open_price - prev_close) / prev_close * 100
            return open_price, prev_close, change_pct

    return None


def get_sp500_open_vs_prev_close(date_str: str) -> tuple | None:
    """Same logic for S&P500 ^GSPC."""
    ticker = yf.Ticker("^GSPC")
    hist = ticker.history(period="10d", interval="1d")
    if hist.empty or len(hist) < 2:
        return None

    rows = list(hist.iterrows())
    for i, (idx, row) in enumerate(rows):
        idx_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        if idx_str == date_str and i > 0:
            prev_close = float(rows[i - 1][1]["Close"])
            open_price = float(row["Open"])
            change_pct = (open_price - prev_close) / prev_close * 100
            return open_price, prev_close, change_pct

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────────────────────────────────────

def check_accuracy(date_str: str, briefing_type: str = "kospi") -> None:
    data = load_briefings()
    briefings = data.get("briefings", [])

    entry = next(
        (b for b in briefings if b["date"] == date_str and b["type"] == briefing_type),
        None,
    )
    if not entry:
        print(f"[check_accuracy] No prediction found for {date_str} ({briefing_type})", file=sys.stderr)
        return

    if entry.get("actual_direction") is not None:
        print(f"[check_accuracy] Already checked for {date_str} ({briefing_type})")
        return

    # Fetch actual data
    fetch_fn = get_kospi_open_vs_prev_close if briefing_type == "kospi" else get_sp500_open_vs_prev_close
    result = fetch_fn(date_str)
    if result is None:
        print(f"[check_accuracy] Could not fetch market data for {date_str}", file=sys.stderr)
        return

    open_price, prev_close, change_pct = result
    actual_direction = "상승" if change_pct >= 0 else "하락"

    predicted = entry.get("predicted_direction", "")
    if "상승" in predicted:
        is_correct = actual_direction == "상승"
    elif "하락" in predicted:
        is_correct = actual_direction == "하락"
    else:
        # 중립 예측은 정오답 판단 보류 (None)
        is_correct = None

    entry["actual_direction"] = actual_direction
    entry["actual_change_pct"] = round(change_pct, 2)
    entry["is_correct"] = is_correct
    entry["checked_at"] = datetime.now(KST).isoformat()

    save_briefings(data)

    result_mark = "✓" if is_correct is True else ("?" if is_correct is None else "✗")
    print(
        f"[check_accuracy] {date_str} ({briefing_type}): "
        f"predicted={predicted}, actual={actual_direction}({change_pct:+.2f}%), {result_mark}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Check prediction accuracy vs actual market open")
    parser.add_argument("--type", default="kospi", choices=["kospi", "us"])
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today KST)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(KST).strftime("%Y-%m-%d")
    check_accuracy(date_str, args.type)


if __name__ == "__main__":
    main()
