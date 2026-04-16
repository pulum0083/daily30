#!/usr/bin/env python3
"""
Generate HTML briefing pages from structured JSON data.
Called AFTER call_claude.py produces data/analysis_{type}.json.

This module replaces Claude's HTML generation step, saving ~4,000 output tokens/run.
Claude only outputs the analysis JSON; this script renders the full page.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import pytz
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
BRIEFINGS_DIR = WEB_DIR / "briefings"
TEMPLATES_DIR = Path(__file__).parent / "templates"
BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)

KST = pytz.timezone("Asia/Seoul")


# ─────────────────────────────────────────────────────────────────────────────
# Jinja2 environment
# ─────────────────────────────────────────────────────────────────────────────

def _acc_cls(p: int) -> str:
    if p >= 70:
        return "acc-good"
    if p >= 50:
        return "acc-mid"
    return "acc-bad"


def _make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
    )
    env.filters["acc_cls"] = _acc_cls
    return env


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def fmt_generated_time(generated_at: str) -> str:
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = KST.localize(dt)
        else:
            dt = dt.astimezone(KST)
        return dt.strftime("%H:%M")
    except Exception:
        return "08:30"


def load_data(data_file: str) -> dict:
    path = Path(data_file)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {data_file}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_analysis(briefing_type: str) -> dict:
    analysis_file = DATA_DIR / f"analysis_{briefing_type}.json"
    if analysis_file.exists():
        with open(analysis_file, encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_web_base_url() -> str:
    url = os.environ.get("WEB_BASE_URL")
    if url:
        return url.rstrip("/")
    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("web", {}).get("base_url", "").rstrip("/")
    return "https://pulum0083.github.io/daily30"


# ─────────────────────────────────────────────────────────────────────────────
# Stock chart data builder
# ─────────────────────────────────────────────────────────────────────────────

def build_stock_charts(stock_picks: list, candidates: list) -> list:
    """Build stockCharts array for MARKET_DATA by matching picks to candidates.

    picks.name 형식: "AAPL (애플)" 또는 "삼성전자" — 앞 토큰(공백 전)을 ticker로 추출해 매칭.
    candidates.name/ticker 형식: "AAPL" 또는 "005930" 등 순수 티커.
    """
    charts = []
    for i, pick in enumerate(stock_picks, 1):
        pick_name = pick.get("name", "")
        # "AAPL (애플)" → "AAPL" / "삼성전자" → "삼성전자"
        pick_ticker = pick_name.split(" ")[0].strip() if pick_name else ""

        candidate = next(
            (c for c in candidates
             if c.get("ticker") == pick_ticker
             or c.get("name") == pick_ticker
             or c.get("name") == pick_name),
            None,
        )
        if candidate:
            charts.append({
                "id": f"mc-{i}",
                "prices": candidate.get("sparkline", []),
                "ma20": candidate.get("ma20_sparkline", []),
                "ma200": candidate.get("ma200_sparkline", []),
            })
        else:
            charts.append({"id": f"mc-{i}", "prices": [], "ma20": [], "ma200": []})
    return charts


# ─────────────────────────────────────────────────────────────────────────────
# Data preparers (context builders)
# ─────────────────────────────────────────────────────────────────────────────

def compute_accuracy_stats(briefing_type: str) -> dict:
    """Read briefings.json and compute accuracy stats for the sidebar."""
    path = DATA_DIR / "briefings.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    # Only entries with a resolved actual result (is_correct is not None)
    entries = [
        b for b in data.get("briefings", [])
        if b.get("type") == briefing_type and b.get("is_correct") is not None
    ]
    if not entries:
        return {}

    entries = sorted(entries, key=lambda x: x["date"])

    last7  = entries[-7:]
    last30 = entries[-30:]

    def pct(correct, total):
        return round(correct / total * 100) if total else 0

    correct7  = sum(1 for e in last7  if e["is_correct"])
    correct30 = sum(1 for e in last30 if e["is_correct"])

    return {
        "last7_correct":  correct7,
        "last7_total":    len(last7),
        "last7_pct":      pct(correct7, len(last7)),
        "last30_correct": correct30,
        "last30_total":   len(last30),
        "last30_pct":     pct(correct30, len(last30)),
        "recent_dots":    [{"correct": e["is_correct"], "date": e["date"]} for e in last7],
    }


def build_sidebar_data(briefing_type: str) -> list:
    """Return sidebar items list. Order differs per briefing type."""
    if briefing_type == "kospi":
        return [
            {"type": "market", "name": "나스닥",            "val_id": "nasdaq-val", "badge_id": "nasdaq-badge", "canvas_id": "c-nasdaq"},
            {"type": "market", "name": "다우존스",           "val_id": "dji-val",    "badge_id": "dji-badge",    "canvas_id": "c-dji"},
            {"type": "market", "name": "필라델피아 반도체",   "val_id": "sox-val",    "badge_id": "sox-badge",    "canvas_id": "c-sox"},
            {"type": "market", "name": "달러 인덱스 DXY",   "val_id": "dxy-val",    "badge_id": "dxy-badge",    "canvas_id": "c-dxy"},
            {"type": "market", "name": "WTI 국제유가",       "val_id": "oil-val",    "badge_id": "oil-badge",    "canvas_id": "c-oil"},
            {"type": "fg"},
        ]
    else:  # us
        return [
            {"type": "market", "name": "나스닥100 선물",     "val_id": "nq-val",  "badge_id": "nq-badge",  "canvas_id": "c-nq"},
            {"type": "market", "name": "WTI 국제유가",       "val_id": "oil-val", "badge_id": "oil-badge", "canvas_id": "c-oil"},
            {"type": "fg"},
        ]


def build_stock_picks_data(stock_picks: list) -> list:
    """Enrich raw stock_picks with pre-computed display fields."""
    result = []
    for i, pick in enumerate(stock_picks, 1):
        ma200_dist = pick.get("ma200_dist_pct", 0)
        ma200_cls = "up" if ma200_dist >= 0 else "down"
        ma200_w = min(abs(ma200_dist) * 10, 100)
        result.append({
            "rank": i,
            "name": pick.get("name", ""),
            "price": pick.get("price", ""),
            "change": pick.get("change", ""),
            "change_cls": pick.get("change_cls", "up"),
            "signal": pick.get("signal", "MA20 반등"),
            "golden": bool(pick.get("golden")),
            "scenario_tag": pick.get("scenario_tag", "단기 반등"),
            "scenario": pick.get("scenario", ""),
            "action_guide": pick.get("action_guide", ""),
            "ma200_dist": f"{abs(ma200_dist):.1f}",
            "ma200_cls": ma200_cls,
            "ma200_w": f"{ma200_w:.0f}",
            "ma200_sign": "+" if ma200_dist >= 0 else "-",
            "ma200_above_below": "상회" if ma200_dist >= 0 else "하회",
            "canvas_id": f"mc-{i}",
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main HTML builder
# ─────────────────────────────────────────────────────────────────────────────

def build_full_html(data: dict, analysis: dict, date_str: str,
                    briefing_type: str, asset_prefix: str = "../") -> str:
    """Build complete HTML page for KOSPI or US briefing."""

    market_data_js = dict(data.get("market_data_js", {}))
    candidates_key = "kospi_candidates" if briefing_type == "kospi" else "us_candidates"
    candidates = data.get(candidates_key, [])

    pred = analysis.get("prediction", {})
    up_pct = pred.get("up_pct", 50)
    down_pct = pred.get("down_pct", 50)
    direction = pred.get("direction", "중립")
    confidence = pred.get("confidence", 70)
    reasons = analysis.get("reasons", [])[:4]
    stock_picks_raw = analysis.get("stock_picks", [])

    # Dynamic reason section title (Claude-generated or fallback by direction)
    _fallback_title = {
        "상승 우위": "왜 오를까? — 오늘의 상승 시그널",
        "하락 우위": "왜 내릴까? — 오늘의 하락 시그널",
    }.get(direction, "오를까 내릴까? — 오늘의 핵심 변수")
    reason_title = analysis.get("reason_title") or _fallback_title
    generated_at = data.get("generated_at", datetime.now(KST).isoformat())
    gen_time = fmt_generated_time(generated_at)

    # Build stockCharts and inject into MARKET_DATA
    stock_charts = build_stock_charts(stock_picks_raw, candidates)
    market_data_js["stockCharts"] = stock_charts
    market_data_json = json.dumps(market_data_js, ensure_ascii=False, indent=2)

    # Direction badge class
    dir_cls = "up" if direction == "상승 우위" else ("down" if direction == "하락 우위" else "")

    # Confidence interval bar widths
    up_light = confidence
    down_light = round(down_pct * confidence / up_pct) if up_pct > 0 else confidence

    # Type-specific strings
    if briefing_type == "kospi":
        page_title = f"Daily30' — 코스피 시초가 브리핑 {date_str}"
        badge_text = "코스피"
        gnb_time = "08:30"
        section_title = "코스피 시초가 방향 예측"
    else:
        page_title = f"Daily30' — 미국 시장 브리핑 {date_str}"
        badge_text = "미국"
        gnb_time = "22:30"
        section_title = "S&P500 방향 예측"

    # Accuracy stats (None if unavailable)
    accuracy_stats = compute_accuracy_stats(briefing_type) or None

    ctx = {
        "page_title": page_title,
        "asset_prefix": asset_prefix,
        "date_str": date_str,
        "gen_time": gen_time,
        "generated_at": generated_at,
        "badge_text": badge_text,
        "gnb_time": gnb_time,
        "section_title": section_title,
        "briefing_type": briefing_type,
        # prediction
        "direction": direction,
        "dir_cls": dir_cls,
        "confidence": confidence,
        "up_pct": up_pct,
        "down_pct": down_pct,
        "up_light": up_light,
        "down_light": down_light,
        # reasons
        "reason_title": reason_title,
        "reasons": reasons,
        # stock picks (enriched)
        "stock_picks": build_stock_picks_data(stock_picks_raw),
        # accuracy
        "accuracy": accuracy_stats,
        # sidebar
        "sidebar_items": build_sidebar_data(briefing_type),
        # MARKET_DATA JSON (raw, no escaping)
        "market_data_json": market_data_json,
    }

    env = _make_env()
    template = env.get_template("briefing.html")
    return template.render(**ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate HTML briefing from analysis JSON")
    parser.add_argument("--type", choices=["kospi", "us", "weekly"], required=True)
    parser.add_argument("--data-file", required=True, help="Path to latest_{type}.json")
    parser.add_argument("--date", default=None, help="Date string (YYYY-MM-DD)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(KST).strftime("%Y-%m-%d")

    try:
        data = load_data(args.data_file)
        analysis = load_analysis(args.type)
    except FileNotFoundError as e:
        print(f"[generate_html] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.type == "weekly":
        html_briefing = f"<html><body><h1>Weekly Report {date_str}</h1></body></html>"
        html_index = html_briefing
    else:
        # briefings/*.html uses "../assets/" prefix
        html_briefing = build_full_html(data, analysis, date_str, args.type, asset_prefix="../")
        # index.html uses "assets/" prefix
        html_index = build_full_html(data, analysis, date_str, args.type, asset_prefix="")

    # Save to briefings archive
    filename = f"{date_str}-{args.type}.html"
    out_path = BRIEFINGS_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_briefing)
    print(f"[generate_html] Saved → {out_path}")

    # Update index.html
    index_path = WEB_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_index)
    print(f"[generate_html] index.html updated")


if __name__ == "__main__":
    main()
