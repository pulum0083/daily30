#!/usr/bin/env python3
"""
Check prediction accuracy by comparing the predicted direction
to the actual KOSPI/S&P500 closing move.

Run at ~09:10 KST (00:10 UTC) — checks the previous day's close.
Updates data/briefings.json with the actual result.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
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

def get_kospi_close_vs_prev_close(date_str: str) -> tuple | None:
    """Returns (close_price, prev_close, change_pct) for the given date using ^KS11."""
    target = datetime.strptime(date_str, "%Y-%m-%d")
    start = (target - timedelta(days=7)).strftime("%Y-%m-%d")
    end = (target + timedelta(days=2)).strftime("%Y-%m-%d")
    hist = yf.Ticker("^KS11").history(start=start, end=end, interval="1d")
    if hist.empty or len(hist) < 2:
        return None
    rows = list(hist.iterrows())
    for i, (idx, row) in enumerate(rows):
        if (idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]) == date_str and i > 0:
            prev_close = float(rows[i - 1][1]["Close"])
            if prev_close == 0:
                return None
            close_price = float(row["Close"])
            return close_price, prev_close, (close_price - prev_close) / prev_close * 100
    return None


def get_sp500_close_vs_prev_close(date_str: str) -> tuple | None:
    """Same logic for S&P500 ^GSPC."""
    target = datetime.strptime(date_str, "%Y-%m-%d")
    start = (target - timedelta(days=7)).strftime("%Y-%m-%d")
    end = (target + timedelta(days=2)).strftime("%Y-%m-%d")
    hist = yf.Ticker("^GSPC").history(start=start, end=end, interval="1d")
    if hist.empty or len(hist) < 2:
        return None
    rows = list(hist.iterrows())
    for i, (idx, row) in enumerate(rows):
        if (idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]) == date_str and i > 0:
            prev_close = float(rows[i - 1][1]["Close"])
            if prev_close == 0:
                return None
            close_price = float(row["Close"])
            return close_price, prev_close, (close_price - prev_close) / prev_close * 100
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Core
# ─────────────────────────────────────────────────────────────────────────────

def _save_market_archive(date_str: str, kospi_close: float, kospi_chg_pct: float) -> None:
    """마감 시장 데이터를 web/data/market-{date}.json 으로 저장한다."""
    archive_path = BASE_DIR / "web" / "data" / f"market-{date_str}.json"
    if archive_path.exists():
        return  # 이미 존재하면 덮어쓰지 않음

    market: dict = {"kospi": {"price": round(kospi_close, 2), "changePct": round(kospi_chg_pct, 2)}}

    # 코스닥 / 코스피200 종가
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
        start = (target - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (target + timedelta(days=2)).strftime("%Y-%m-%d")
        for key, ticker in [("kosdaq", "^KQ11"), ("kospi200", "^KS200")]:
            hist = yf.Ticker(ticker).history(start=start, end=end, interval="1d")
            rows = list(hist.iterrows())
            for i, (idx, row) in enumerate(rows):
                d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                if d == date_str and i > 0:
                    prev = float(rows[i - 1][1]["Close"])
                    cur  = float(row["Close"])
                    if prev and cur and cur == cur:  # NaN 체크
                        market[key] = {"price": round(cur, 2), "changePct": round((cur - prev) / prev * 100, 2)}
                    break
    except Exception as e:
        print(f"[check_accuracy] market archive 지수 fetch 실패: {e}", file=sys.stderr)

    # 외국인·기관·개인 수급 (latest_kospi_close.json 에서 읽기)
    try:
        close_json = BASE_DIR / "data" / "latest_kospi_close.json"
        if close_json.exists():
            cdata = json.loads(close_json.read_text(encoding="utf-8"))
            it = cdata.get("investor_trading", {})
            market["investor"] = {
                "foreign":     round((it.get("foreign",     {}).get("net", 0) or 0) / 100),
                "institution": round((it.get("institution", {}).get("net", 0) or 0) / 100),
                "individual":  round((it.get("individual",  {}).get("net", 0) or 0) / 100),
            }
    except Exception as e:
        print(f"[check_accuracy] market archive 수급 읽기 실패: {e}", file=sys.stderr)

    archive_path.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[check_accuracy] 마켓 아카이브 저장: {archive_path.name}")


def check_accuracy(date_str: str, briefing_type: str = "kospi", force: bool = False) -> None:
    data = load_briefings()
    briefings = data.get("briefings", [])

    entry = next(
        (b for b in briefings if b["date"] == date_str and b["type"] == briefing_type),
        None,
    )
    if not entry:
        print(f"[check_accuracy] No prediction found for {date_str} ({briefing_type})", file=sys.stderr)
        return

    if entry.get("actual_direction") is not None and not force:
        print(f"[check_accuracy] Already checked for {date_str} ({briefing_type})")
        return

    # Fetch actual data
    fetch_fn = get_kospi_close_vs_prev_close if briefing_type == "kospi" else get_sp500_close_vs_prev_close
    result = fetch_fn(date_str)
    if result is None:
        print(f"[check_accuracy] Could not fetch market data for {date_str}", file=sys.stderr)
        return

    close_price, prev_close, change_pct = result
    actual_direction = "상승" if change_pct >= 0 else "하락"

    predicted = entry.get("predicted_direction", "")
    if "상승" in predicted:
        is_correct = actual_direction == "상승"
    elif "하락" in predicted:
        is_correct = actual_direction == "하락"
    else:
        # 중립 예측: 실제 변동폭 ±0.5% 이내면 정확으로 채점
        is_correct = abs(change_pct) <= 0.5

    entry["actual_direction"] = actual_direction
    entry["actual_change_pct"] = round(change_pct, 2)
    entry["is_correct"] = is_correct
    entry["checked_at"] = datetime.now(KST).isoformat()

    save_briefings(data)

    # KOSPI 브리핑 HTML에 실제 등락률 주입 — 과거 브리핑 스코어보드 표시용
    if briefing_type == "kospi" and not (change_pct != change_pct):  # NaN 체크
        import re
        html_path = BASE_DIR / "web" / "briefings" / date_str / "kospi" / "index.html"
        if html_path.exists():
            html = html_path.read_text(encoding="utf-8")
            if 'data-actual-pct=' in html:
                html = re.sub(r'data-actual-pct="[^"]*"', f'data-actual-pct="{change_pct:.2f}"', html)
            else:
                html = html.replace('id="live-scoreboard"', f'id="live-scoreboard" data-actual-pct="{change_pct:.2f}"', 1)
            html_path.write_text(html, encoding="utf-8")
            print(f"[check_accuracy] HTML 패치: kospi/{date_str} (actual_pct={change_pct:+.2f}%)")

    # 마감 시장 데이터 아카이브 — 과거 브리핑 시장 지표 패널 표시용
    if briefing_type == "kospi":
        _save_market_archive(date_str, close_price, change_pct)

    result_mark = "✓" if is_correct is True else ("?" if is_correct is None else "✗")
    print(
        f"[check_accuracy] {date_str} ({briefing_type}): "
        f"predicted={predicted}, actual={actual_direction}({change_pct:+.2f}%), {result_mark}"
    )


def backfill(briefing_type: str = "kospi", force: bool = False) -> None:
    """미검증(또는 force 시 전체) 과거 예측을 정산한다.

    09:10 실행 시점엔 당일 일봉이 아직 없으므로 오늘 이전 날짜만 대상으로 한다.
    force=True 이면 이미 검증된 항목도 종가 기준으로 재정산한다(기준 변경 마이그레이션용).
    """
    data = load_briefings()
    today = datetime.now(KST).strftime("%Y-%m-%d")
    pending = sorted({
        b["date"] for b in data.get("briefings", [])
        if b.get("type") == briefing_type
        and (b.get("is_correct") is None or force)
        and b.get("date", "") < today
    })
    if not pending:
        print(f"[check_accuracy] 백필 대상 없음 ({briefing_type})")
        return
    print(f"[check_accuracy] 백필 대상 {len(pending)}건: {pending}")
    for d in pending:
        check_accuracy(d, briefing_type, force=force)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Check prediction accuracy vs actual market close")
    parser.add_argument("--type", default="kospi", choices=["kospi", "us"])
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today KST)")
    parser.add_argument("--backfill", action="store_true",
                        help="미검증 과거 예측을 모두 정산 (--date 무시)")
    parser.add_argument("--force", action="store_true",
                        help="이미 검증된 항목도 재정산 (기준 변경 마이그레이션용)")
    args = parser.parse_args()

    if args.backfill:
        backfill(args.type, force=args.force)
    else:
        date_str = args.date or datetime.now(KST).strftime("%Y-%m-%d")
        check_accuracy(date_str, args.type)


if __name__ == "__main__":
    main()
