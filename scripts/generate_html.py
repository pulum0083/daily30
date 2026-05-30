#!/usr/bin/env python3
# config-driven 섹션 조립으로 브리핑 HTML을 생성하는 조립기
"""브리핑 HTML 조립기.

call_claude.py가 다음 시그니처로 호출한다:
  generate_html.py --type {kospi|us|kospi-close} --data-file <latest_*.json> --date YYYY-MM-DD

analysis_{type}.json(Claude 분석) + data-file(시장 데이터)을 읽어
config/{internal}.json 선언에 따라 섹션 템플릿을 조립하고
web/briefings/{date}/{internal}/index.html 로 출력한다.

데이터가 없는 섹션은 조립 템플릿의 {% if %} 가드로 자동 생략된다(하이브리드).
"""

import argparse
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

import pytz
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
BRIEFINGS_DIR = WEB_DIR / "briefings"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
CONFIG_DIR = Path(__file__).resolve().parent / "config"
KST = pytz.timezone("Asia/Seoul")

# CLI type → 내부 type(URL·config·템플릿)
TYPE_MAP = {"kospi": "kospi", "us": "us", "kospi-close": "close", "close": "close"}
# 내부 type → analysis 파일명에 쓰는 source type
SRC_TYPE = {"kospi": "kospi", "us": "us", "close": "kospi-close"}
# 내부 type → 시장 데이터 파일명
DATA_FILE = {"kospi": "latest_kospi.json", "us": "latest_us.json", "close": "latest_kospi_close.json"}
BRIEFING_LABELS = {"kospi": "코스피 예측", "close": "코스피 마감", "us": "미국 시장"}
SCHEDULED_TIMES = {"kospi": "07:30", "close": "15:40", "us": "21:20"}
DAY_FULL = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
DAY_SHORT = ["월", "화", "수", "목", "금", "토", "일"]


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
    env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)
    env.filters["acc_cls"] = lambda p: "good" if p >= 70 else ("mid" if p >= 50 else "bad")
    return env


def fmt_time(generated_at: str) -> str:
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = KST.localize(dt)
        return dt.astimezone(KST).strftime("%H:%M")
    except Exception:
        return "--:--"


def day_label(d: str, full: bool = False) -> str:
    try:
        wd = date.fromisoformat(d).weekday()
        return (DAY_FULL if full else DAY_SHORT)[wd]
    except Exception:
        return ""


# ── 섹션 컨텍스트 빌더 ─────────────────────────────────────────────────────────
def build_prediction(analysis: dict, index_name: str, pred_title: str, gen_time: str) -> dict:
    pred = analysis.get("prediction", {})
    up_pct = pred.get("up_pct", 50)
    down_pct = pred.get("down_pct", 100 - up_pct)
    direction = pred.get("direction", "중립")
    confidence = pred.get("confidence", 70)
    is_up = "상승" in direction
    dir_cls = "up" if is_up else ("dn" if "하락" in direction else "")
    band_color = "rgba(224,49,49,.42)" if is_up else "rgba(39,117,237,.42)"
    dots = max(1, min(5, round(confidence / 20)))
    conf_label = "강함" if confidence >= 80 else ("보통" if confidence >= 60 else "약함")
    return {
        "pred_title": pred_title,
        "direction": direction,
        "dir_cls": dir_cls,
        "dir_arrow": "▲" if is_up else "▼",
        "dir_word": "상승" if is_up else "하락",
        "up_pct": up_pct,
        "down_pct": down_pct,
        "readout_pct": up_pct if is_up else down_pct,
        "band_left": max(0, min(86, (up_pct if is_up else up_pct) - 7)),
        "band_width": 14,
        "band_color": band_color,
        "confidence": confidence,
        "confidence_dots": dots,
        "confidence_label": conf_label,
        "generated_time": gen_time,
    }


def build_reasons(analysis: dict) -> dict:
    direction = analysis.get("prediction", {}).get("direction", "")
    fallback = {
        "상승 우위": "왜 오를까? — 오늘의 상승 시그널",
        "하락 우위": "왜 내릴까? — 오늘의 하락 시그널",
    }.get(direction, "오를까 내릴까? — 오늘의 핵심 변수")
    return {
        "reason_title": analysis.get("reason_title") or fallback,
        "reasons": analysis.get("reasons", [])[:4],
    }


def build_stock_picks(analysis: dict, market_data: dict, internal_type: str) -> list:
    """analysis.stock_picks → 카드 컨텍스트 (스파크라인은 candidates에서 매칭)."""
    picks = analysis.get("stock_picks", [])
    if not picks:
        return []
    cand_key = "kospi_candidates" if internal_type == "kospi" else "us_candidates"
    candidates = market_data.get(cand_key, []) or []

    def find_chart(pick):
        tk, nm = pick.get("ticker", ""), pick.get("name", "")
        for c in candidates:
            if c.get("ticker") in (tk, nm) or c.get("name") in (tk, nm):
                return c
        return {}

    result = []
    for i, p in enumerate(picks, 1):
        dist = p.get("ma200_dist_pct", 0) or 0
        ma200_cls = "up" if dist >= 0 else "down"
        fill_w = min(abs(dist), 60) / 60 * 50
        chart = find_chart(p)
        result.append({
            "name": p.get("name", ""),
            "ma20_badge": p.get("signal", ""),
            "price": p.get("price", ""),
            "change": p.get("change", ""),
            "change_cls": p.get("change_cls", "up"),
            "scenario": p.get("scenario", ""),
            "action_guide": p.get("action_guide", ""),
            "ma200_cls": ma200_cls,
            "ma200_fill_width": f"{fill_w:.1f}",
            "ma200_pct": f"{'+' if dist >= 0 else ''}{dist:.1f}%",
            "chart_id": f"mc-{i}",
            "entry": p.get("entry"),
            "target": p.get("target"),
            "target_pct": p.get("target_pct"),
            "stop": p.get("stop"),
            "stop_pct": p.get("stop_pct"),
            "prices": chart.get("sparkline", []),
            "ma20": chart.get("ma20_sparkline", []),
            "ma200": chart.get("ma200_sparkline", []),
        })
    return result


def build_nh_stocks(analysis: dict) -> list:
    """US 프리장 52주 신고가."""
    out = []
    for h in analysis.get("premarket_highs", [])[:5]:
        out.append({
            "ticker": h.get("ticker", ""),
            "name": h.get("name", ""),
            "tag": h.get("tag", "52주 신고가"),
            "alltime": bool(h.get("all_time") or h.get("alltime")),
            "break_note": h.get("break_note", ""),
            "reason": h.get("reason", ""),
            "price": h.get("price", ""),
            "chg": h.get("chg") or h.get("change") or h.get("change_pct", ""),
        })
    return out


def build_market_items(market_data: dict, internal_type: str, gen_time: str) -> list:
    """시장 지표 사이드바. market_data_js 키를 표시 항목으로 매핑(있는 것만)."""
    mdj = dict(market_data.get("market_data_js", {}))
    if "vix" not in mdj and market_data.get("vix"):
        mdj["vix"] = market_data["vix"]
    if internal_type == "kospi":
        spec = [("나스닥", "nasdaq"), ("필라델피아 반도체", "sox"),
                ("나스닥100 선물", "nq"), ("원/달러", "usdkrw")]
    else:
        spec = [("나스닥100 선물", "nq"), ("나스닥", "nasdaq"),
                ("필라델피아 반도체", "sox")]
    items = []
    for name, key in spec:
        d = mdj.get(key)
        if not isinstance(d, dict):
            continue
        val = d.get("base", d.get("price"))
        chg = d.get("chg", d.get("change_pct"))
        if val is None:
            continue
        chg_cls = "up" if (chg or 0) >= 0 else "down"
        items.append({
            "name": name,
            "val": f"{val:,.2f}" if isinstance(val, (int, float)) else str(val),
            "chg": f"{'+' if (chg or 0) >= 0 else ''}{chg:.2f}%" if isinstance(chg, (int, float)) else str(chg),
            "chg_cls": chg_cls,
            "spark_id": f"c-{key}",
            "spark_data": d.get("data", []),
            "spark_color": "#E03131" if chg_cls == "up" else "#2775ED",
        })
    # VIX (코스피·미국 공통 — 데이터 있을 때만)
    vix = mdj.get("vix")
    if internal_type in ("kospi", "us") and isinstance(vix, dict) and vix.get("price") is not None:
        p = vix["price"]
        lvls = [(15, "안정", "calm"), (20, "보통", "normal"), (30, "경계", "elevated"),
                (40, "불안", "high"), (10 ** 9, "극단", "high")]
        _, lbl, cls = next(x for x in lvls if p < x[0])
        cp = vix.get("change_pct", 0)
        items.append({
            "name": "VIX 공포지수", "info_modal": "vix-modal",
            "val": f"{p:.2f}",
            "chg": f"{'+' if cp >= 0 else ''}{cp:.2f}%",
            "chg_cls": "up" if cp >= 0 else "down",
            "vix_level": lbl, "vix_level_cls": cls,
        })
    return items


def build_close_sections(analysis: dict, market: dict, index_name: str) -> dict:
    """마감 전용 섹션 컨텍스트 (있는 데이터만)."""
    ctx = {}
    indices = market.get("indices", {})
    kospi = indices.get("kospi", {})
    intraday = market.get("intraday", {})

    # close_hero
    prices = intraday.get("prices", [])
    if prices and kospi:
        cp = kospi.get("change_pct", 0)
        ca = kospi.get("change_abs", 0)
        up = cp >= 0
        price = kospi.get("price", 0)
        ta = market.get("trade_amount", {})
        subs = []
        for name, key in [("KOSDAQ", "kosdaq"), ("원/달러", "usdkrw")]:
            d = indices.get(key)
            if isinstance(d, dict) and d.get("price") is not None:
                scp = d.get("change_pct", 0)
                subs.append({
                    "name": name,
                    "val": f"{d['price']:,.2f}",
                    "chg": f"{'▲' if scp >= 0 else '▼'} {scp:+.2f}%",
                    "chg_cls": "up" if scp >= 0 else "down",
                })
        ctx.update({
            "index_name": index_name,
            "close_val": f"{price:,.2f}",
            "close_chg": f"{'▲' if up else '▼'} {abs(ca):.2f} ({cp:+.2f}%)",
            "close_chg_cls": "up" if up else "down",
            "vol_label": "코스피 거래대금",
            "vol_val": ta.get("kospi_formatted") or ta.get("kospi") or "—",
            "intraday_prices": prices,
            "prev_close": round(price - ca, 2),
            "intraday_axis": ["09:00", "10:30", "12:00", "13:30", "15:20"],
            "sub_indices": subs,
        })

    # close_reason (항상 분석에 존재)
    if analysis.get("market_title"):
        b_rows = []
        for label, key, sw in [("WHY", "why", False), ("WHAT", "what", False), ("SO?", "so_what", True)]:
            if analysis.get(key):
                b_rows.append({"label": label, "text": analysis[key], "so_what": sw})
        ctx.update({
            "reason_title": analysis["market_title"],
            "reason_lead": analysis.get("market_summary", ""),
            "b_rows": b_rows,
        })

    # close_breadth (market_breadth 있을 때만)
    mb = market.get("market_breadth", {})
    if mb:
        rows = []
        if any(k in mb for k in ("advance", "decline", "unchanged")):
            rows.append({"label": "등락", "cells": [
                {"lbl": "상승", "val": mb.get("advance", 0), "cls": "up"},
                {"lbl": "하락", "val": mb.get("decline", 0), "cls": "down"},
                {"lbl": "보합", "val": mb.get("unchanged", 0), "cls": "neutral"},
            ]})
        if any(k in mb for k in ("upper_limit", "lower_limit", "new_high", "new_low")):
            rows.append({"label": "특이 종목", "cells": [
                {"lbl": "상한가", "val": mb.get("upper_limit", 0), "cls": "up"},
                {"lbl": "하한가", "val": mb.get("lower_limit", 0), "cls": "down"},
                {"lbl": "신고가", "val": mb.get("new_high", 0), "cls": "up"},
                {"lbl": "신저가", "val": mb.get("new_low", 0), "cls": "down"},
            ]})
        if rows:
            ctx["breadth_rows"] = rows

    # close_sector
    sectors = market.get("sectors", [])
    if sectors:
        ctx["sectors"] = [{
            "name": s.get("name", ""),
            "pct": f"{s.get('change_pct', 0):+.1f}%",
            "cls": "up" if s.get("change_pct", 0) >= 0 else "dn",
        } for s in sectors[:8]]

    # close_supply (수급) — fetch_investor_trading 구조: {player: {"net": 백만원}}
    inv = market.get("investor_trading", {})
    if isinstance(inv, dict) and inv:
        cells = []
        for label, key in [("외국인", "foreign"), ("기관", "institution"), ("개인", "individual")]:
            d = inv.get(key)
            if not isinstance(d, dict) or d.get("net") is None:
                continue
            eok = round(d["net"] / 100)  # 백만원 → 억원
            up = eok >= 0
            cells.append({
                "label": label,
                "amt": f"{eok:+,}억",
                "amt_cls": "up" if up else "down",
                "sub": "순매수" if up else "순매도",
                "flow": d.get("flow", []),  # 7일 흐름(있으면)
            })
        if cells:
            ctx["supply_cells"] = cells

    # close_dpick / pick_result: 종목별 거래대금·수급·전일픽 데이터 미수집 → 생략(하이브리드)
    return ctx


def build_accuracy(internal_type: str) -> dict:
    bpath = DATA_DIR / "briefings.json"
    if not bpath.exists():
        return {}
    data = load_json(bpath).get("briefings", [])
    src = SRC_TYPE.get(internal_type, internal_type)
    typed = [b for b in data if b.get("type") in (internal_type, src) and b.get("is_correct") is not None]
    if not typed:
        return {}
    r30, r7 = typed[-30:], typed[-7:]

    def pct(lst):
        return round(sum(1 for b in lst if b["is_correct"]) / len(lst) * 100) if lst else 0

    hit = sum(1 for b in r30 if b["is_correct"])
    miss = len(r30) - hit
    pending = sum(1 for b in data if b.get("type") in (internal_type, src) and b.get("is_correct") is None)
    total = max(hit + miss + pending, 1)
    return {
        "acc_7d_pct": pct(r7), "acc_30d_pct": pct(r30),
        "hit": hit, "miss": miss, "pending": pending,
        "hit_pct": round(hit / total * 100), "miss_pct": round(miss / total * 100),
        "pending_pct": round(pending / total * 100),
    }


# ── 인접 브리핑 + 목록 ─────────────────────────────────────────────────────────
def existing_dates(internal_type: str) -> list:
    if not BRIEFINGS_DIR.exists():
        return []
    return sorted(d.name for d in BRIEFINGS_DIR.iterdir()
                  if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}$", d.name)
                  and (d / internal_type / "index.html").exists())


def find_adjacent(internal_type: str, target: str) -> tuple:
    dirs = existing_dates(internal_type)
    if target not in dirs:
        # 아직 안 써졌으면 가상으로 끼워 계산
        dirs = sorted(set(dirs) | {target})
    idx = dirs.index(target)
    prev_url = f"/briefings/{dirs[idx-1]}/{internal_type}/" if idx > 0 else None
    next_url = f"/briefings/{dirs[idx+1]}/{internal_type}/" if idx < len(dirs) - 1 else None
    return prev_url, next_url


def build_list_context(target_date: str, active_type: str) -> dict:
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []
    today = datetime.now(KST).strftime("%Y-%m-%d")

    def norm_type(t):
        return TYPE_MAP.get(t, t)

    def cell_for(d: str, btype: str, today_card: bool) -> dict:
        ready = (BRIEFINGS_DIR / d / btype / "index.html").exists()
        match = next((b for b in briefings if b.get("date") == d and norm_type(b.get("type")) == btype), None)
        base = {"type": btype, "label": BRIEFING_LABELS[btype]}
        if d == target_date and btype == active_type:
            base["state"] = "current"
        elif ready:
            base["state"] = "ready"
            base["url"] = f"/briefings/{d}/{btype}/"
        elif today_card:
            base["state"] = "pending"
            base["scheduled_time"] = SCHEDULED_TIMES[btype]
            return base
        else:
            base["state"] = "empty"
            return base
        # ready/current 공통 표시
        if match:
            direction = match.get("predicted_direction") or match.get("direction", "")
            if btype == "close":
                chg = match.get("actual_change_pct")
                base["pill_cls"] = "neutral"
                base["pill_text"] = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else ""
                base["title"] = f"KOSPI {chg:+.2f}%" if isinstance(chg, (int, float)) else "마감"
            else:
                up = "상승" in direction
                base["pill_cls"] = "up" if up else "dn"
                base["pill_text"] = ("▲ 상승" if up else "▼ 하락") if direction else ""
                base["title"] = direction or "—"
            base["time"] = fmt_time(match.get("generated_at", ""))
        else:
            base["title"] = "—"
            base["time"] = ""
        return base

    types = ["kospi", "close", "us"]
    today_card = {
        "date": today, "day_label": day_label(today, full=True),
        "slots": [cell_for(today, t, True) for t in types],
    }
    past_dates = sorted({b["date"] for b in briefings if b.get("date") and b["date"] != today}, reverse=True)[:30]
    past_rows, prev_month = [], None
    for d in past_dates:
        try:
            dt = date.fromisoformat(d)
        except ValueError:
            continue
        month = f"{dt.year}년 {dt.month}월"
        past_rows.append({
            "date": d, "date_short": d[5:], "day_label": day_label(d),
            "month_label": month, "show_month": month != prev_month,
            "cells": [cell_for(d, t, False) for t in types],
        })
        prev_month = month
    return {"today_card": today_card, "past_rows": past_rows}


# ── 렌더 ──────────────────────────────────────────────────────────────────────
def render_briefing(internal_type: str, target_date: str, market_data: dict) -> str:
    env = make_env()
    config = load_json(CONFIG_DIR / f"{internal_type}.json")
    src_type = SRC_TYPE[internal_type]
    analysis_path = DATA_DIR / f"analysis_{src_type}.json"
    analysis = load_json(analysis_path) if analysis_path.exists() else {}

    generated_at = market_data.get("generated_at") or analysis.get("generated_at") or datetime.now(KST).isoformat()
    gen_time = fmt_time(generated_at)
    index_name = config["index_name"]
    prev_url, next_url = find_adjacent(internal_type, target_date)

    ctx = {
        "date_str": target_date,
        "generated_at": generated_at,
        "generated_time": gen_time,
        "gnb_date": f"{target_date} KST {gen_time}",
        "index_name": index_name,
        "prev_url": prev_url, "next_url": next_url,
        "css_path": "/assets/style.css", "js_path": "/assets/main.js",
        **build_list_context(target_date, internal_type),
        **build_accuracy(internal_type),
    }
    ctx["accuracy"] = bool(ctx.get("acc_30d_pct") is not None and (ctx.get("hit", 0) + ctx.get("miss", 0)) > 0)

    if internal_type == "close":
        ctx.update(build_close_sections(analysis, market_data, index_name))
        ctx["og_description"] = analysis.get("market_title", f"{target_date} 코스피 마감")
    else:
        ctx.update(build_prediction(analysis, index_name, config["pred_title"], gen_time))
        ctx.update(build_reasons(analysis))
        ctx["stock_picks"] = build_stock_picks(analysis, market_data, internal_type)
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["watch_items"] = analysis.get("watch_items") or analysis.get("watchpoints") or []
        if internal_type == "us":
            ctx["nh_stocks"] = build_nh_stocks(analysis)
            ctx["spill_rows"] = analysis.get("spill") or analysis.get("spill_rows") or []
        d = ctx.get("direction", "")
        rp = ctx.get("readout_pct", "")
        ctx["og_description"] = f"{config['pred_title']}: {d} {rp}% · 신뢰도 {ctx.get('confidence','')}%"

    template = env.get_template(config["template"])
    return template.render(**ctx)


def write_output(html: str, internal_type: str, target_date: str):
    out_dir = BRIEFINGS_DIR / target_date / internal_type
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate_html] wrote {out_dir.relative_to(BASE_DIR)}/index.html")


def find_latest_ready():
    """generated_at 기준 가장 최근 생성된 ready 브리핑 (internal_type, date) 반환. 없으면 None."""
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []
    best = None  # (generated_at, internal_type, date)
    for b in briefings:
        it = TYPE_MAP.get(b.get("type"), b.get("type"))
        d = b.get("date")
        if it not in DATA_FILE or not d:
            continue
        if not (BRIEFINGS_DIR / d / it / "index.html").exists():
            continue
        ga = b.get("generated_at", "") or ""
        if best is None or ga > best[0]:
            best = (ga, it, d)
    return (best[1], best[2]) if best else None


def regenerate_index():
    """web/briefings/index.html = 가장 최근 브리핑(본문+목록). 브리핑이 없으면 목록 전용 폴백."""
    latest = find_latest_ready()
    if latest:
        internal_type, target_date = latest
        dpath = DATA_DIR / DATA_FILE[internal_type]
        market_data = load_json(dpath) if dpath.exists() else {}
        html = render_briefing(internal_type, target_date, market_data)
        (BRIEFINGS_DIR / "index.html").write_text(html, encoding="utf-8")
        print(f"[generate_html] wrote index = 최신 브리핑 {target_date}/{internal_type}")
        return
    tpl = TEMPLATES_DIR / "pages" / "briefings_index.html"
    if not tpl.exists():
        print("[generate_html] skip index (브리핑 0개 + 목록 템플릿 없음)")
        return
    env = make_env()
    ctx = {"css_path": "/assets/style.css", "js_path": "/assets/main.js",
           **build_list_context("", "")}
    html = env.get_template("pages/briefings_index.html").render(**ctx)
    (BRIEFINGS_DIR / "index.html").write_text(html, encoding="utf-8")
    print("[generate_html] wrote web/briefings/index.html (목록 전용)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=list(TYPE_MAP.keys()))
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--data-file", dest="data_file", required=True, help="시장 데이터 JSON 경로")
    args = parser.parse_args()

    internal_type = TYPE_MAP[args.type]
    data_path = Path(args.data_file)
    market_data = load_json(data_path) if data_path.exists() else {}

    html = render_briefing(internal_type, args.date, market_data)
    write_output(html, internal_type, args.date)
    regenerate_index()


if __name__ == "__main__":
    main()
