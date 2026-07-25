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
from datetime import date, datetime, timedelta
from pathlib import Path

import urllib.request

import pytz
import yfinance as yf

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DATA_DIR = BASE_DIR / "web" / "data"
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
    """Returns (close_price, prev_close, change_pct) for the given date.
    1순위: 네이버 지수 일봉 API, 2순위: yfinance ^KS11.
    """
    result = _kospi_from_naver(date_str)
    if result is not None:
        return result
    # yfinance 폴백
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
        start = (target - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (target + timedelta(days=2)).strftime("%Y-%m-%d")
        hist = yf.Ticker("^KS11").history(start=start, end=end, interval="1d")
        if not hist.empty and len(hist) >= 2:
            rows = list(hist.iterrows())
            for i, (idx, row) in enumerate(rows):
                if (idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]) == date_str and i > 0:
                    prev_close = float(rows[i - 1][1]["Close"])
                    if prev_close == 0:
                        return None
                    close_price = float(row["Close"])
                    return close_price, prev_close, (close_price - prev_close) / prev_close * 100
    except Exception:
        pass
    return None


def _kospi_from_naver(date_str: str) -> tuple | None:
    """네이버 코스피 지수 일봉 API로 (close, prev_close, change_pct) 반환."""
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d")
        start_dt = (target - timedelta(days=10)).strftime("%Y%m%d") + "000000"
        end_dt = (target + timedelta(days=2)).strftime("%Y%m%d") + "235959"
        url = (
            f"https://api.stock.naver.com/chart/domestic/index/KOSPI/day"
            f"?startDateTime={start_dt}&endDateTime={end_dt}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        rows = json.loads(urllib.request.urlopen(req, timeout=10).read())
        rows = sorted(rows, key=lambda r: r["localDate"])
        for i, row in enumerate(rows):
            if row["localDate"] == date_str.replace("-", "") and i > 0:
                prev_close = float(rows[i - 1]["closePrice"])
                close_price = float(row["closePrice"])
                if prev_close == 0:
                    return None
                return close_price, prev_close, (close_price - prev_close) / prev_close * 100
    except Exception:
        pass
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


def classify_direction_correct(predicted_direction: str, change_pct: float) -> bool:
    """예측 방향 문자열과 실제 등락률로 적중 여부를 판정한다.
    상승/하락 예측은 실제 방향과 일치 여부로, 중립 예측은 실제 변동폭 ±0.5% 이내로 채점한다."""
    actual_direction = "상승" if change_pct >= 0 else "하락"
    if "상승" in predicted_direction:
        return actual_direction == "상승"
    if "하락" in predicted_direction:
        return actual_direction == "하락"
    return abs(change_pct) <= 0.5


def check_accuracy(date_str: str, briefing_type: str = "kospi", force: bool = False) -> None:
    if briefing_type == "us":
        print("[check_accuracy] US는 이슈 중심 전환(2026-07-14)으로 채점 대상이 아니에요 — skip", file=sys.stderr)
        return
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
    if change_pct != change_pct:  # NaN(미수집 행) → 가짜 '하락' 기록 방지, 채점 보류
        print(f"[check_accuracy] {date_str} ({briefing_type}): change_pct NaN — 채점 보류", file=sys.stderr)
        return
    actual_direction = "상승" if change_pct >= 0 else "하락"
    predicted = entry.get("predicted_direction", "")
    is_correct = classify_direction_correct(predicted, change_pct)

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
    if briefing_type == "us":
        print("[check_accuracy] US backfill skip — 채점 탈퇴", file=sys.stderr)
        return
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


def compute_publish_streak(briefings: list) -> dict:
    """코스피 브리핑의 **거래일 기준** 연속 발행 일수를 센다.

    주말·공휴일은 끊김이 아니다 — holiday_check로 거래일만 골라 세므로
    "주말에 왜 안 늘지?" 오해가 생기지 않도록 화면에는 항상 "거래일"을 붙인다.

    아직 발행되지 않은 오늘(07:25 브리핑 전)을 끊김으로 오판하지 않기 위해,
    가장 최근 발행일부터 거꾸로 센다.
    """
    from holiday_check import check_kospi_open

    dates = {b["date"] for b in briefings if b.get("type") == "kospi"}
    if not dates:
        return {"days": 0, "from": None, "to": None}

    last = max(dates)
    first = min(dates)
    cur = date.fromisoformat(last)
    floor = date.fromisoformat(first)
    days = 0
    start = last
    while cur >= floor:
        if check_kospi_open(cur):
            if cur.isoformat() in dates:
                days += 1
                start = cur.isoformat()
            else:
                break
        cur -= timedelta(days=1)

    return {"days": days, "from": start, "to": last}


def write_accuracy_summary() -> None:
    """누적 적중률 요약을 web/data/accuracy-summary.json에 기록한다.
    랜딩 등에서 fetch해 쓰며, 채점 실행 때마다 실데이터로 갱신 — 하드코딩 stale 방지."""
    data = load_briefings()
    # bucket: [scored, hit]
    buckets = {"cumulative": [0, 0], "kospi": [0, 0], "us": [0, 0]}
    for b in data.get("briefings", []):
        if b.get("is_correct") is None:
            continue
        hit = 1 if b.get("is_correct") else 0
        buckets["cumulative"][0] += 1
        buckets["cumulative"][1] += hit
        t = b.get("type")
        if t in ("kospi", "us"):
            buckets[t][0] += 1
            buckets[t][1] += hit

    out = {
        k: {"scored": s, "hit": h, "pct": (round(h / s * 100) if s else None)}
        for k, (s, h) in buckets.items()
    }
    # US는 2026-07-14 이슈 중심 전환으로 채점 탈퇴(call_claude.py / check_accuracy 상단 가드).
    # us 수치는 그 시점에 동결됐고 cumulative는 동결값이 섞인 혼합값이라, 새 소비자가
    # 무심코 "지금 성적"으로 쓰지 않도록 데이터에 명시한다. 살아 있는 지표는 kospi뿐이다.
    out["us"]["retired"] = True
    out["us"]["note"] = "2026-07-14 이슈 중심 전환으로 채점 탈퇴 — 수치 동결"
    out["cumulative"]["note"] = "kospi(진행) + us(동결) 혼합 — 현재 성적은 kospi를 쓸 것"
    out["live_key"] = "kospi"
    out["streak"] = compute_publish_streak(data.get("briefings", []))
    out["updated_at"] = datetime.now(KST).isoformat()

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = WEB_DATA_DIR / "accuracy-summary.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    k, st = out["kospi"], out["streak"]
    print(f"[check_accuracy] 적중률 요약 기록: 코스피 {k['hit']}/{k['scored']} ({k['pct']}%) "
          f"· 연속 발행 {st['days']} 거래일")


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

    # 채점 결과를 반영한 누적 요약을 갱신 (랜딩 fetch용)
    write_accuracy_summary()


if __name__ == "__main__":
    main()
