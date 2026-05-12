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
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
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
        return dt.strftime("%H:%M KST")
    except Exception:
        return "08:30 KST"


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


def normalize_ma_terms(text: str) -> str:
    """MA200 → 200일 이동평균선, MA20 → 20일 이동평균선 (MA200 먼저 처리)"""
    text = re.sub(r'\bMA200\b', '200일 이동평균선', text)
    text = re.sub(r'\bMA20\b', '20일 이동평균선', text)
    return text


def normalize_ma_list(items: list) -> list:
    return [normalize_ma_terms(s) if isinstance(s, str) else s for s in items]


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


def generate_og_image(
    date_str: str,
    briefing_type: str,
    direction: str,
    up_pct,
    down_pct,
    confidence,
    reason_title: str,
    reasons: list,
) -> str:
    """날짜·예측 방향이 반영된 OG 이미지 SVG를 동적으로 생성한다."""
    import html as _html
    def esc(s): return _html.escape(str(s))

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%Y.%m.%d")
        day_ko = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]
    except Exception:
        date_display = date_str
        day_ko = ""

    if "상승" in direction:
        badge_fill, badge_stroke, badge_color = "rgba(224,49,49,.18)", "rgba(224,49,49,.4)", "#FF6A6A"
        dir_emoji = "📈"
    elif "하락" in direction:
        badge_fill, badge_stroke, badge_color = "rgba(39,117,237,.18)", "rgba(39,117,237,.4)", "#60A3FF"
        dir_emoji = "📉"
    else:
        badge_fill, badge_stroke, badge_color = "rgba(100,100,100,.18)", "rgba(100,100,100,.4)", "#AAAAAA"
        dir_emoji = "📊"

    bar_total = 368
    down_w = round(bar_total * int(down_pct) / 100)
    up_w   = round(bar_total * int(up_pct) / 100)
    up_x   = 56 + (bar_total - up_w)

    type_label = "코스피 시초가 방향 예측" if briefing_type == "kospi" else "S&P500 방향 예측"
    rt = re.sub(r"<[^>]+>", "", str(reason_title))[:52]
    r_lines = [re.sub(r"<[^>]+>", "", str(r))[:76] for r in reasons[:3]]
    while len(r_lines) < 3:
        r_lines.append("")

    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#E03131"/><stop offset="100%" stop-color="#FF6A6A"/></linearGradient>
    <linearGradient id="bu" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#E03131"/><stop offset="100%" stop-color="#FF6A6A"/></linearGradient>
    <linearGradient id="bd" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#2775ED"/><stop offset="100%" stop-color="#60A3FF"/></linearGradient>
  </defs>
  <rect width="1200" height="630" fill="#111213"/>
  <rect width="1200" height="52" fill="#16181A"/>
  <rect x="0" y="51" width="1200" height="1" fill="rgba(255,255,255,.06)"/>
  <rect x="32" y="12" width="28" height="28" rx="7" fill="url(#lg)"/>
  <g transform="translate(32,12) scale(1.167)">
    <rect x="5" y="8" width="4" height="10" rx="1" fill="white"/>
    <line x1="7" y1="4" x2="7" y2="8" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
    <line x1="7" y1="18" x2="7" y2="21" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
    <rect x="15" y="5" width="4" height="8" rx="1" fill="white" fill-opacity=".55"/>
    <line x1="17" y1="3" x2="17" y2="5" stroke="white" stroke-opacity=".55" stroke-width="1.5" stroke-linecap="round"/>
    <line x1="17" y1="13" x2="17" y2="16" stroke="white" stroke-opacity=".55" stroke-width="1.5" stroke-linecap="round"/>
  </g>
  <text x="70" y="33" font-family="{font}" font-size="16" font-weight="700" fill="white">Double</text>
  <text x="126" y="33" font-family="{font}" font-size="16" font-weight="700" fill="rgba(255,255,255,.5)">-Shot</text>
  <text x="176" y="33" font-family="{font}" font-size="12" fill="rgba(255,255,255,.35)">  AI 투자 브리핑</text>
  <text x="1050" y="33" font-family="{font}" font-size="12" fill="rgba(255,255,255,.4)">{esc(date_display)} ({esc(day_ko)})</text>
  <text x="40" y="90" font-family="{font}" font-size="18" font-weight="700" fill="rgba(255,255,255,.9)">{esc(date_str)}</text>
  <rect x="310" y="72" width="88" height="26" rx="13" fill="{badge_fill}" stroke="{badge_stroke}" stroke-width="1"/>
  <text x="354" y="89" text-anchor="middle" font-family="{font}" font-size="12" font-weight="700" fill="{badge_color}">{esc(direction)}</text>
  <rect x="40" y="106" width="400" height="152" rx="12" fill="#1C1D1F"/>
  <text x="56" y="130" font-family="{font}" font-size="11" font-weight="600" fill="rgba(255,255,255,.4)" letter-spacing="0.05em">{esc(type_label)}</text>
  <text x="56" y="160" font-family="{font}" font-size="18" font-weight="800" fill="white">{dir_emoji} {esc(direction)} 예측</text>
  <text x="56" y="180" font-family="{font}" font-size="14" font-weight="500" fill="rgba(255,255,255,.5)">(신뢰도 {confidence}%)</text>
  <text x="56" y="208" font-family="{font}" font-size="12" fill="#60A3FF">하락 {down_pct}%</text>
  <text x="424" y="208" text-anchor="end" font-family="{font}" font-size="12" fill="#FF6A6A">상승 {up_pct}%</text>
  <rect x="56" y="214" width="368" height="22" rx="11" fill="#242628"/>
  <rect x="56" y="214" width="{down_w}" height="22" rx="11" fill="url(#bd)"/>
  <rect x="{up_x}" y="214" width="{up_w}" height="22" rx="11" fill="url(#bu)"/>
  <rect x="239" y="208" width="1" height="34" fill="rgba(255,255,255,.2)"/>
  <text x="40" y="292" font-family="{font}" font-size="14" font-weight="700" fill="rgba(255,255,255,.85)">💬 {esc(rt)}</text>
  <circle cx="50" cy="320" r="3" fill="rgba(255,255,255,.3)"/>
  <text x="62" y="324" font-family="{font}" font-size="12" fill="rgba(255,255,255,.6)">{esc(r_lines[0])}</text>
  <circle cx="50" cy="348" r="3" fill="rgba(255,255,255,.3)"/>
  <text x="62" y="352" font-family="{font}" font-size="12" fill="rgba(255,255,255,.6)">{esc(r_lines[1])}</text>
  <circle cx="50" cy="376" r="3" fill="rgba(255,255,255,.3)"/>
  <text x="62" y="380" font-family="{font}" font-size="12" fill="rgba(255,255,255,.6)">{esc(r_lines[2])}</text>
  <text x="40" y="598" font-family="{font}" font-size="12" fill="rgba(255,255,255,.2)">doubleshot.space</text>
  <rect x="476" y="68" width="1" height="530" fill="rgba(255,255,255,.07)"/>
  <text x="500" y="90" font-family="{font}" font-size="11" font-weight="700" fill="rgba(255,255,255,.35)" letter-spacing="0.1em">시장 지표</text>
  <rect x="0" y="508" width="1200" height="122" fill="#0D0D0F"/>
  <rect x="0" y="508" width="1200" height="1" fill="rgba(255,255,255,.06)"/>
  <text x="40" y="542" font-family="{font}" font-size="11" font-weight="700" fill="rgba(255,255,255,.3)" letter-spacing="0.1em">수신 채널</text>
  <rect x="40" y="554" width="140" height="36" rx="18" fill="rgba(0,136,204,.12)" stroke="rgba(0,136,204,.3)" stroke-width="1"/>
  <text x="110" y="576" text-anchor="middle" font-family="{font}" font-size="14" font-weight="600" fill="#5BAEFF">📱 텔레그램</text>
  <rect x="194" y="554" width="120" height="36" rx="18" fill="rgba(230,119,0,.12)" stroke="rgba(230,119,0,.3)" stroke-width="1"/>
  <text x="254" y="576" text-anchor="middle" font-family="{font}" font-size="14" font-weight="600" fill="#FFB246">📧 이메일</text>
  <text x="40" y="616" font-family="{font}" font-size="12" fill="rgba(255,255,255,.2)">무료 · 언제든 해지 가능 · doubleshot.space</text>
  <text x="900" y="556" font-family="{font}" font-size="11" font-weight="700" fill="rgba(255,255,255,.3)" letter-spacing="0.1em">브리핑 스케줄</text>
  <text x="900" y="582" font-family="{font}" font-size="15" font-weight="700" fill="rgba(255,255,255,.7)">08:30</text>
  <text x="950" y="582" font-family="{font}" font-size="12" fill="rgba(255,255,255,.35)">코스피 · 평일</text>
  <text x="900" y="604" font-family="{font}" font-size="15" font-weight="700" fill="rgba(255,255,255,.7)">21:30</text>
  <text x="950" y="604" font-family="{font}" font-size="12" fill="rgba(255,255,255,.35)">미국 · 평일</text>
</svg>"""


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
            {"type": "vix"},
        ]
    else:  # us
        return [
            {"type": "market", "name": "나스닥100 선물",     "val_id": "nq-val",  "badge_id": "nq-badge",  "canvas_id": "c-nq"},
            {"type": "market", "name": "WTI 국제유가",       "val_id": "oil-val", "badge_id": "oil-badge", "canvas_id": "c-oil"},
            {"type": "vix"},
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
            "signal": normalize_ma_terms(pick.get("signal", "20일 이동평균선 반등")),
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

    # VIX fallback: 구 데이터 파일은 market_data_js에 vix가 없고 최상위에만 있음
    if "vix" not in market_data_js and data.get("vix"):
        market_data_js["vix"] = data["vix"]
    market_data_js.pop("fearGreed", None)

    pred = analysis.get("prediction", {})
    up_pct = pred.get("up_pct", 50)
    down_pct = pred.get("down_pct", 50)
    direction = pred.get("direction", "중립")
    confidence = pred.get("confidence", 70)
    reasons = normalize_ma_list(analysis.get("reasons", [])[:4])
    stock_picks_raw = analysis.get("stock_picks", [])

    # Dynamic reason section title (Claude-generated or fallback by direction)
    _fallback_title = {
        "상승 우위": "왜 오를까? — 오늘의 상승 시그널",
        "하락 우위": "왜 내릴까? — 오늘의 하락 시그널",
    }.get(direction, "오를까 내릴까? — 오늘의 핵심 변수")
    reason_title = normalize_ma_terms(analysis.get("reason_title") or _fallback_title)
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
        page_title = f"Double-Shot — 코스피 시초가 브리핑 {date_str}"
        badge_text = "코스피"
        gnb_time = "08:30"
        section_title = "코스피 시초가 방향 예측"
    else:
        page_title = f"Double-Shot — 미국 시장 브리핑 {date_str}"
        badge_text = "미국"
        gnb_time = "22:30"
        section_title = "S&P500 방향 예측"

    # Accuracy stats (None if unavailable)
    accuracy_stats = compute_accuracy_stats(briefing_type) or None

    # OG image URL + description
    web_base = get_web_base_url()
    og_image_url = f"{web_base}/briefings/{date_str}-{briefing_type}-og.svg"
    og_description = f"{date_str} {section_title}: {direction} {up_pct if '상승' in direction else down_pct}% · 신뢰도 {confidence}%"

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
        # premarket highs (US only; empty list if absent)
        "premarket_highs": [
            {**h, "reason": normalize_ma_terms(h.get("reason", ""))}
            for h in analysis.get("premarket_highs", [])[:3]
        ] if briefing_type == "us" else [],
        # accuracy
        "accuracy": accuracy_stats,
        # sidebar
        "sidebar_items": build_sidebar_data(briefing_type),
        # MARKET_DATA JSON (raw, no escaping)
        "market_data_json": market_data_json,
        # OG
        "og_image_url": og_image_url,
        "og_description": og_description,
    }

    env = _make_env()
    template = env.get_template("briefing.html")
    return template.render(**ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Archive briefing summary extractor
# ─────────────────────────────────────────────────────────────────────────────

def extract_briefing_summary(html_path: Path) -> Optional[dict]:
    """
    web/briefings/YYYY-MM-DD-{type}.html 파일에서 아코디언 아카이브에 필요한
    핵심 데이터를 추출한다.
    반환: {date, type, badge_text, section_title, direction, dir_cls,
           up_pct, down_pct, confidence, up_light, down_light,
           reasons, gen_time, url}
    """
    try:
        name = html_path.name  # "2026-04-17-kospi.html"
        parts = name.replace(".html", "").split("-")
        date_str = "-".join(parts[:3])
        btype = parts[3] if len(parts) > 3 else "kospi"

        content = html_path.read_text(encoding="utf-8")

        # --- 예측 방향 ---
        dir_match = re.search(r'<span class="pred-badge[^"]*">\s*(.*?)\s*</span>', content)
        direction = dir_match.group(1).strip() if dir_match else "중립"
        dir_cls = "up" if direction == "상승 우위" else ("down" if direction == "하락 우위" else "")

        # --- 확률 ---
        up_match = re.search(r'pred-confbar__solid up[^"]*"\s*style="width:(\d+)%"', content)
        down_match = re.search(r'pred-confbar__solid down[^"]*"\s*style="width:(\d+)%"', content)
        up_pct = int(up_match.group(1)) if up_match else 50
        down_pct = int(down_match.group(1)) if down_match else 50

        # --- 신뢰도 ---
        conf_match = re.search(r'신뢰도\s*(\d+)%\)', content)
        confidence = int(conf_match.group(1)) if conf_match else 70

        # confidence interval light bar widths
        up_light = confidence
        down_light = round(down_pct * confidence / up_pct) if up_pct > 0 else confidence

        # --- 예측 근거 ---
        rb_match = re.search(
            r'<div class="reason-block">\s*<ul>([\s\S]*?)</ul>', content
        )
        reasons: list[str] = []
        if rb_match:
            li_matches = re.findall(r"<li>([\s\S]*?)</li>", rb_match.group(1))
            reasons = [li.strip() for li in li_matches]

        # --- 생성 시각 ---
        time_match = re.search(r'<span class="section-time">(\d+:\d+) 생성</span>', content)
        gen_time = time_match.group(1) if time_match else ""

        # --- reason_title ---
        rt_match = re.search(
            r'<div class="open-section__title reason-section-title">(.*?)</div>', content
        )
        reason_title = rt_match.group(1).strip() if rt_match else ""

        # type-specific labels
        if btype == "kospi":
            badge_text = "코스피"
            section_title = "코스피 시초가 방향 예측"
        else:
            badge_text = "미국"
            section_title = "S&amp;P500 방향 예측"

        return {
            "date": date_str,
            "type": btype,
            "badge_text": badge_text,
            "section_title": section_title,
            "direction": direction,
            "dir_cls": dir_cls,
            "up_pct": up_pct,
            "down_pct": down_pct,
            "confidence": confidence,
            "up_light": up_light,
            "down_light": down_light,
            "reasons": reasons,
            "reason_title": reason_title,
            "gen_time": gen_time,
            "url": f"/briefings/{'ko' if btype == 'kospi' else btype}/{date_str}/",
        }
    except Exception as e:
        print(f"[generate_html] extract_briefing_summary error ({html_path.name}): {e}",
              file=sys.stderr)
        return None


def load_briefing_summaries(current_date: str, current_type: str, n: int = 10) -> list[dict]:
    """
    web/briefings/ 폴더의 HTML 파일을 스캔하여 최신 n개 브리핑 요약을 반환한다.
    현재 브리핑(current_date-current_type)은 제외 (index에서 latest로 별도 렌더링).
    반환: 최신순 정렬 리스트
    """
    html_files = sorted(
        BRIEFINGS_DIR.glob("*-*.html"),
        reverse=True,  # 파일명이 YYYY-MM-DD 형식이라 역순 정렬이 최신순
    )

    summaries = []
    for path in html_files:
        name = path.stem  # "2026-04-17-kospi"
        parts = name.split("-")
        if len(parts) < 4:
            continue
        date_str = "-".join(parts[:3])
        btype = parts[3]

        # 현재 브리핑은 건너뜀 (latest로 별도 처리)
        if date_str == current_date and btype == current_type:
            continue

        summary = extract_briefing_summary(path)
        if summary:
            summaries.append(summary)

        if len(summaries) >= n - 1:  # latest 1개 + archive (n-1)개
            break

    return summaries


# ─────────────────────────────────────────────────────────────────────────────
# Multi-accordion index builder
# ─────────────────────────────────────────────────────────────────────────────

def build_index_html_multi(data: dict, analysis: dict, date_str: str,
                           briefing_type: str) -> str:
    """
    최신 브리핑 + 최근 N개 아카이브를 아코디언으로 합쳐 index.html 렌더링.
    최신 브리핑: 펼쳐진 상태, 완전한 시장 데이터 포함.
    아카이브 항목: 접힌 상태, 예측 바 + 예측 근거만 표시.
    """
    market_data_js = dict(data.get("market_data_js", {}))
    candidates_key = "kospi_candidates" if briefing_type == "kospi" else "us_candidates"
    candidates = data.get(candidates_key, [])

    if "vix" not in market_data_js and data.get("vix"):
        market_data_js["vix"] = data["vix"]
    market_data_js.pop("fearGreed", None)

    pred = analysis.get("prediction", {})
    up_pct = pred.get("up_pct", 50)
    down_pct = pred.get("down_pct", 50)
    direction = pred.get("direction", "중립")
    confidence = pred.get("confidence", 70)
    reasons = normalize_ma_list(analysis.get("reasons", [])[:4])
    stock_picks_raw = analysis.get("stock_picks", [])

    _fallback_title = {
        "상승 우위": "왜 오를까? — 오늘의 상승 시그널",
        "하락 우위": "왜 내릴까? — 오늘의 하락 시그널",
    }.get(direction, "오를까 내릴까? — 오늘의 핵심 변수")
    reason_title = normalize_ma_terms(analysis.get("reason_title") or _fallback_title)
    generated_at = data.get("generated_at", datetime.now(KST).isoformat())
    gen_time = fmt_generated_time(generated_at)

    stock_charts = build_stock_charts(stock_picks_raw, candidates)
    market_data_js["stockCharts"] = stock_charts
    market_data_json = json.dumps(market_data_js, ensure_ascii=False, indent=2)

    dir_cls = "up" if direction == "상승 우위" else ("down" if direction == "하락 우위" else "")
    up_light = confidence
    down_light = round(down_pct * confidence / up_pct) if up_pct > 0 else confidence

    if briefing_type == "kospi":
        page_title = f"Double-Shot — 코스피 시초가 브리핑 {date_str}"
        badge_text = "코스피"
        gnb_time = "08:30"
        section_title = "코스피 시초가 방향 예측"
    else:
        page_title = f"Double-Shot — 미국 시장 브리핑 {date_str}"
        badge_text = "미국"
        gnb_time = "22:30"
        section_title = "S&P500 방향 예측"

    accuracy_stats = compute_accuracy_stats(briefing_type) or None
    archive_items = load_briefing_summaries(date_str, briefing_type, n=10)

    web_base = get_web_base_url()
    og_image_url = f"{web_base}/briefings/{date_str}-{briefing_type}-og.svg"
    og_description = f"{date_str} {section_title}: {direction} {up_pct if '상승' in direction else down_pct}% · 신뢰도 {confidence}%"

    ctx = {
        "page_title": page_title,
        "asset_prefix": "/",
        "date_str": date_str,
        "gen_time": gen_time,
        "generated_at": generated_at,
        "badge_text": badge_text,
        "gnb_time": gnb_time,
        "section_title": section_title,
        "briefing_type": briefing_type,
        "direction": direction,
        "dir_cls": dir_cls,
        "confidence": confidence,
        "up_pct": up_pct,
        "down_pct": down_pct,
        "up_light": up_light,
        "down_light": down_light,
        "reason_title": reason_title,
        "reasons": reasons,
        "stock_picks": build_stock_picks_data(stock_picks_raw),
        "premarket_highs": [
            {**h, "reason": normalize_ma_terms(h.get("reason", ""))}
            for h in analysis.get("premarket_highs", [])[:3]
        ] if briefing_type == "us" else [],
        "accuracy": accuracy_stats,
        "sidebar_items": build_sidebar_data(briefing_type),
        "market_data_json": market_data_json,
        "archive_items": archive_items,
        "og_image_url": og_image_url,
        "og_description": og_description,
    }

    env = _make_env()
    template = env.get_template("index.html")
    return template.render(**ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Date page builder (clean URL: /briefings/YYYY-MM-DD/)
# ─────────────────────────────────────────────────────────────────────────────

def save_date_page(data: dict, analysis: dict, date_str: str, briefing_type: str) -> None:
    """Generate web/briefings/YYYY-MM-DD/index.html (served at /briefings/YYYY-MM-DD/)."""
    html = build_full_html(data, analysis, date_str, briefing_type, asset_prefix="/")
    date_dir = BRIEFINGS_DIR / date_str
    date_dir.mkdir(parents=True, exist_ok=True)
    out = date_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"[generate_html] Date page saved → {out}")


def backfill_date_pages() -> None:
    """
    For each existing YYYY-MM-DD-{type}.html, create/overwrite the date page at
    web/briefings/YYYY-MM-DD/index.html by reusing the briefing HTML with a
    corrected asset prefix (../ → ../../).
    On days with both kospi and us briefings, us (the later run) is used.
    """
    date_files: dict = {}
    for path in sorted(BRIEFINGS_DIR.glob("*-*.html"), reverse=True):
        name = path.stem
        parts = name.split("-")
        if len(parts) < 4:
            continue
        date_str = "-".join(parts[:3])
        btype = parts[3]
        date_files.setdefault(date_str, {})[btype] = path

    for date_str, type_files in sorted(date_files.items()):
        # Prefer us (runs later in the day); fall back to kospi
        source = type_files.get("us") or type_files.get("kospi")
        if not source:
            continue

        content = source.read_text(encoding="utf-8")
        # Fix asset references: one level deeper (../assets → ../../assets)
        content = content.replace('href="../assets/', 'href="../../assets/')
        content = content.replace('src="../assets/', 'src="../../assets/')

        date_dir = BRIEFINGS_DIR / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        out = date_dir / "index.html"
        out.write_text(content, encoding="utf-8")
        print(f"[generate_html] Backfilled date page → {out}")


# ─────────────────────────────────────────────────────────────────────────────
# KOSPI 마감 시황 HTML 빌더
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_idx(d: dict) -> dict:
    """지수 데이터를 템플릿용 문자열로 변환한다."""
    if not d or "error" in d:
        return {"price": "-", "chg_pct": "-", "chg_abs": "-", "arrow": "", "cls": "neutral"}
    price = d.get("price", 0)
    chg   = d.get("change_pct", 0)
    chg_abs = d.get("change_abs", 0)
    cls   = "up" if chg >= 0 else "down"
    arrow = "▲" if chg >= 0 else "▼"
    return {
        "price":   f"{price:,.2f}",
        "chg_pct": f"{chg:+.2f}",
        "chg_abs": f"{abs(chg_abs):,.2f}",
        "arrow":   arrow,
        "cls":     cls,
    }


def build_closing_html(data: dict, analysis: dict, date_str: str) -> str:
    """KOSPI 마감 시황 브리핑 HTML을 생성한다."""
    generated_at = data.get("generated_at", datetime.now(KST).isoformat())
    gen_time = fmt_generated_time(generated_at)

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        days_ko = ["월", "화", "수", "목", "금", "토", "일"]
        day_of_week = days_ko[dt.weekday()]
    except Exception:
        day_of_week = ""

    indices  = data.get("indices", {})
    futures  = data.get("futures", {})
    sectors  = data.get("sectors", [])
    top_gainers = data.get("top_gainers", [])

    kospi  = _fmt_idx(indices.get("kospi", {}))
    kosdaq = _fmt_idx(indices.get("kosdaq", {}))
    usdkrw = _fmt_idx(indices.get("usdkrw", {}))
    nq     = _fmt_idx(futures.get("nq", {}))
    sp     = _fmt_idx(futures.get("sp", {}))
    wti    = _fmt_idx(futures.get("wti", {}))

    # 원/달러 부가 설명
    usdkrw_note = "원화 강세 마감" if (indices.get("usdkrw") or {}).get("change_pct", 0) < 0 else "원화 약세 마감"

    web_base = get_web_base_url()
    page_title = f"Double-Shot — 코스피 마감 시황 {date_str}"
    og_image_url = f"{web_base}/briefings/{date_str}-kospi-close-og.svg"
    og_description = f"{date_str} 코스피 마감: {analysis.get('market_title', '')}"

    reasons = [r for r in analysis.get("reasons", []) if r]

    ctx = {
        "page_title":    page_title,
        "asset_prefix":  "/",
        "date_str":      date_str,
        "day_of_week":   day_of_week,
        "gen_time":      gen_time,
        "og_image_url":  og_image_url,
        "og_description": og_description,
        "market_title":  analysis.get("market_title", ""),
        "market_summary": analysis.get("market_summary", ""),
        "reasons":       reasons,
        "sectors":       sectors,
        "top_gainers":   top_gainers,
        # 지수
        "kospi_price":   kospi["price"],   "kospi_chg_pct":  kospi["chg_pct"],
        "kospi_chg_abs": kospi["chg_abs"], "kospi_arrow":    kospi["arrow"],
        "kospi_cls":     kospi["cls"],     "kospi_volume":   "",
        "kosdaq_price":  kosdaq["price"],  "kosdaq_chg_pct": kosdaq["chg_pct"],
        "kosdaq_chg_abs": kosdaq["chg_abs"], "kosdaq_arrow": kosdaq["arrow"],
        "kosdaq_cls":    kosdaq["cls"],
        "usdkrw_price":  usdkrw["price"],  "usdkrw_chg_pct": usdkrw["chg_pct"],
        "usdkrw_cls":    usdkrw["cls"],    "usdkrw_arrow":   usdkrw["arrow"],
        "usdkrw_note":   usdkrw_note,
        # 사이드바
        "nq_price":  nq["price"],  "nq_chg_pct":  nq["chg_pct"],  "nq_cls":  nq["cls"],
        "sp_price":  sp["price"],  "sp_chg_pct":  sp["chg_pct"],  "sp_cls":  sp["cls"],
        "wti_price": wti["price"], "wti_chg_pct": wti["chg_pct"], "wti_cls": wti["cls"],
    }

    env = _make_env()
    template = env.get_template("briefing_closing.html")
    return template.render(**ctx)


def save_closing_pages(data: dict, analysis: dict, date_str: str) -> None:
    """마감 시황 HTML을 flat 파일과 clean URL 경로 두 곳에 저장한다."""
    html = build_closing_html(data, analysis, date_str)

    # flat: briefings/YYYY-MM-DD-kospi-close.html
    flat_path = BRIEFINGS_DIR / f"{date_str}-kospi-close.html"
    flat_path.write_text(html, encoding="utf-8")
    print(f"[generate_html] Closing briefing saved → {flat_path}")

    # clean URL: briefings/ko-close/YYYY-MM-DD/index.html
    close_dir = BRIEFINGS_DIR / "ko-close" / date_str
    close_dir.mkdir(parents=True, exist_ok=True)
    (close_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate_html] Closing date page saved → {close_dir}/index.html")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate HTML briefing from analysis JSON")
    parser.add_argument("--type", choices=["kospi", "us", "weekly", "kospi-close"])
    parser.add_argument("--data-file", help="Path to latest_{type}.json")
    parser.add_argument("--date", default=None, help="Date string (YYYY-MM-DD)")
    parser.add_argument("--backfill-date-pages", action="store_true",
                        help="Backfill /briefings/YYYY-MM-DD/ pages from existing HTMLs and exit")
    args = parser.parse_args()

    if args.backfill_date_pages:
        backfill_date_pages()
        return

    if not args.type or not args.data_file:
        parser.error("--type and --data-file are required unless --backfill-date-pages is used")

    date_str = args.date or datetime.now(KST).strftime("%Y-%m-%d")

    try:
        data = load_data(args.data_file)
        analysis = load_analysis(args.type)
    except FileNotFoundError as e:
        print(f"[generate_html] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # ── KOSPI 마감 시황 ──
    if args.type == "kospi-close":
        save_closing_pages(data, analysis, date_str)
        return

    if args.type == "weekly":
        html_briefing = f"<html><body><h1>Weekly Report {date_str}</h1></body></html>"
        html_index = html_briefing
    else:
        # briefings/*.html: 개별 페이지 (변경 없음)
        html_briefing = build_full_html(data, analysis, date_str, args.type, asset_prefix="/")
        # index.html: 멀티 아코디언 (최신 + 아카이브)
        html_index = build_index_html_multi(data, analysis, date_str, args.type)

    # Save to briefings archive
    filename = f"{date_str}-{args.type}.html"
    out_path = BRIEFINGS_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_briefing)
    print(f"[generate_html] Saved → {out_path}")

    # Save OG image SVG
    if args.type != "weekly":
        pred = analysis.get("prediction", {})
        og_svg = generate_og_image(
            date_str=date_str,
            briefing_type=args.type,
            direction=pred.get("direction", "중립"),
            up_pct=pred.get("up_pct", 50),
            down_pct=pred.get("down_pct", 50),
            confidence=pred.get("confidence", 70),
            reason_title=analysis.get("reason_title", ""),
            reasons=analysis.get("reasons", []),
        )
        og_path = BRIEFINGS_DIR / f"{date_str}-{args.type}-og.svg"
        og_path.write_text(og_svg, encoding="utf-8")
        print(f"[generate_html] OG image saved → {og_path}")

    # Save date page (clean URL: /briefings/YYYY-MM-DD/)
    if args.type != "weekly":
        save_date_page(data, analysis, date_str, args.type)

    # Update briefings/index.html (serves at /briefings/)
    index_path = BRIEFINGS_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_index)
    print(f"[generate_html] briefings/index.html updated")


if __name__ == "__main__":
    main()
