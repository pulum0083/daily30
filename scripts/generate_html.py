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
SCHEDULED_TIMES = {"kospi": "07:30", "close": "16:30", "us": "21:20"}
DAY_FULL = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
DAY_SHORT = ["월", "화", "수", "목", "금", "토", "일"]


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# 마감 수급 7일 흐름용 누적 저장 (벌크 7일 API가 막혀 있어 매일 단일일 수급을 쌓아 시계열 생성)
SUPPLY_HISTORY_FILE = DATA_DIR / "supply_history.json"
SUPPLY_KEYS = ("foreign", "institution", "individual")


def _load_supply_history() -> dict:
    try:
        return load_json(SUPPLY_HISTORY_FILE)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update_supply_history(date: str, inv: dict) -> dict:
    """당일 시장 수급(외국인/기관/개인 순매수)을 날짜별로 멱등 upsert하고 전체를 반환한다(억원 단위)."""
    rec = {}
    for key in SUPPLY_KEYS:
        d = inv.get(key)
        if isinstance(d, dict) and d.get("net") is not None:
            rec[key] = round(d["net"] / 100)  # 백만원 → 억원
    hist = _load_supply_history()
    if not rec:
        return hist
    hist[date] = rec
    hist = {k: hist[k] for k in sorted(hist)[-30:]}  # 최근 30일만 보관
    SUPPLY_HISTORY_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    return hist


def supply_flow(hist: dict, key: str, upto: str) -> list:
    """key 투자자의 최근 7거래일(upto 날짜 이하) 순매수 시계열(오래된→오늘, 억원)."""
    dates = sorted(d for d in hist if d <= upto)[-7:]
    return [hist[d].get(key, 0) for d in dates]


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
    band_color = "#E03131" if is_up else "#2775ED"
    dots = max(1, min(5, round(confidence / 20)))
    conf_label = "강함" if confidence >= 80 else ("보통" if confidence >= 60 else "약함")
    return {
        "pred_title": pred_title,
        "direction": direction,
        "dir_cls": dir_cls,
        "dir_arrow": "↑" if is_up else ("↓" if "하락" in direction else "→"),
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


def build_scenario_context(analysis: dict) -> dict:
    """시나리오 분기 형식용 컨텍스트. analysis_format == 'scenario' 일 때 사용."""
    return {
        "sc_summary": analysis.get("sc_summary", ""),
        "sc_left_label": analysis.get("sc_left_label", "하락 근거"),
        "sc_right_label": analysis.get("sc_right_label", "반등 가능성"),
        "sc_left_items": analysis.get("sc_left_items", [])[:3],
        "sc_right_items": analysis.get("sc_right_items", [])[:3],
        "sc_footer": analysis.get("sc_footer", ""),
    }


def build_why_what_so_context(analysis: dict) -> dict:
    """WHY/WHAT/SO WHAT 형식용 컨텍스트. analysis_format == 'why_what_so' 일 때 사용."""
    b_rows = []
    for label, key, sw in [("WHY", "why", False), ("WHAT", "what", False), ("SO?", "so_what", True)]:
        if analysis.get(key):
            b_rows.append({"label": label, "text": analysis[key], "so_what": sw})
    return {
        "reason_lead": analysis.get("reason_lead", ""),
        "b_rows": b_rows,
    }


def build_qa_context(analysis: dict) -> dict:
    """Q&A 문답 형식용 컨텍스트. analysis_format == 'qa' 일 때 사용."""
    items = []
    for it in analysis.get("qa_items", [])[:3]:
        if it.get("q") and it.get("a"):
            items.append({"q": it["q"], "a": it["a"]})
    return {"qa_items": items}


def build_signal_context(analysis: dict) -> dict:
    """신호등 스코어보드 형식용 컨텍스트. analysis_format == 'signal' 일 때 사용."""
    items = []
    for it in analysis.get("sig_items", [])[:5]:
        lvl = it.get("level", "neu")
        if lvl not in ("up", "neu", "down"):
            lvl = "neu"
        if it.get("label") and it.get("desc"):
            items.append({"level": lvl, "label": it["label"], "desc": it["desc"]})
    tone = analysis.get("sig_tone", "neu")
    if tone not in ("up", "neu", "down"):
        tone = "neu"
    return {
        "sig_verdict": analysis.get("sig_verdict", ""),
        "sig_tone": tone,
        "sig_items": items,
    }


def build_reasons(analysis: dict) -> dict:
    direction = analysis.get("prediction", {}).get("direction", "")
    fallback = {
        "상승 우위": "왜 오를까? — 오늘의 상승 시그널",
        "하락 우위": "왜 내릴까? — 오늘의 하락 시그널",
    }.get(direction, "오를까 내릴까? — 오늘의 핵심 변수")
    fmt = analysis.get("analysis_format", "bullet")
    ctx = {
        "analysis_format": fmt,
        "reason_title": analysis.get("reason_title") or fallback,
        "reasons": analysis.get("reasons", [])[:4],
        "comfort_line": analysis.get("comfort_line", ""),
    }
    if fmt == "scenario":
        ctx.update(build_scenario_context(analysis))
    elif fmt == "why_what_so":
        ctx.update(build_why_what_so_context(analysis))
    elif fmt == "qa":
        ctx.update(build_qa_context(analysis))
    elif fmt == "signal":
        ctx.update(build_signal_context(analysis))
    return ctx


def build_stock_picks(analysis: dict, market_data: dict, internal_type: str) -> list:
    """analysis.stock_picks → 카드 컨텍스트.
    price/change는 candidates 실데이터로 덮어쓴다 (Claude 할루시네이션 방지).
    """
    picks = analysis.get("stock_picks", [])
    if not picks:
        return []
    cand_key = "kospi_candidates" if internal_type == "kospi" else "us_candidates"
    candidates = market_data.get(cand_key, []) or []

    def find_candidate(pick):
        tk = pick.get("ticker", "")
        nm = pick.get("name", "")
        # "NVDA (엔비디아)" → "NVDA" 형태에서 티커 추출
        nm_prefix = nm.split("(")[0].strip() if nm else ""
        for c in candidates:
            ct = c.get("ticker", "")
            if ct and ct in (tk, nm, nm_prefix):
                return c
            if c.get("name") in (tk, nm):
                return c
        return {}

    result = []
    for i, p in enumerate(picks, 1):
        cand = find_candidate(p)

        # MA200 게이지: 실데이터 우선, 없으면 Claude 값 폴백
        dist = cand.get("ma200_dist_pct")
        if dist is None:
            dist = p.get("ma200_dist_pct", 0) or 0
        ma200_cls = "up" if dist >= 0 else "down"
        fill_w = min(abs(dist), 60) / 60 * 50

        # price/change: 실데이터 우선, 없으면 Claude 값 폴백
        actual_chg = cand.get("change_pct")
        actual_price = cand.get("price")
        if actual_chg is not None:
            change_str = f"{actual_chg:+.2f}%"
            # CSS: stock-pick-card__change.up / .down (음수는 'down' — 'dn' 미정의)
            change_cls = "up" if actual_chg >= 0 else "down"
        else:
            change_str = p.get("change", "")
            change_cls = p.get("change_cls", "up")
        if actual_price is not None:
            is_us = internal_type == "us"
            price_str = f"${actual_price:,.2f}" if is_us else f"{actual_price:,.0f}원"
        else:
            price_str = p.get("price", "")

        result.append({
            "name": p.get("name", ""),
            "ma20_badge": p.get("signal", ""),
            "price": price_str,
            "change": change_str,
            "change_cls": change_cls,
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
            "prices": cand.get("sparkline", []),
            "ma20": cand.get("ma20_sparkline", []),
            "ma200": cand.get("ma200_sparkline", []),
            "vol_mult": p.get("vol_mult"),
        })
    return result



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


def build_close_sections(analysis: dict, market: dict, index_name: str, target_date: str) -> dict:
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
            "vol_val": ta.get("formatted") or "—",
            "intraday_prices": prices,
            "prev_close": round(price - ca, 2),
            "intraday_axis": ["09:00", "10:30", "12:00", "13:30", "15:20"],
            "sub_indices": subs,
        })

    # close_reason 섹션
    if analysis.get("market_title") or analysis.get("reason_title"):
        fmt = analysis.get("analysis_format", "why_what_so")
        ctx["analysis_format"] = fmt
        ctx["reason_title"] = analysis.get("market_title") or analysis.get("reason_title", "")
        ctx["comfort_line"] = analysis.get("comfort_line", "")
        if fmt == "scenario":
            ctx.update(build_scenario_context(analysis))
        elif fmt == "bullet":
            ctx["reasons"] = analysis.get("reasons", [])[:4]
        elif fmt == "qa":
            ctx.update(build_qa_context(analysis))
        elif fmt == "signal":
            ctx.update(build_signal_context(analysis))
        else:  # why_what_so (default for close)
            ctx["reason_lead"] = analysis.get("market_summary", "")
            b_rows = []
            for label, key, sw in [("WHY", "why", False), ("WHAT", "what", False), ("SO?", "so_what", True)]:
                if analysis.get(key):
                    b_rows.append({"label": label, "text": analysis[key], "so_what": sw})
            ctx["b_rows"] = b_rows

    # close_breadth (market_breadth 있을 때만)
    mb = market.get("market_breadth", {})
    if mb:
        rows = []
        if any(k in mb for k in ("up", "down", "unchanged")):
            rows.append({"label": "등락", "cells": [
                {"lbl": "상승", "val": mb.get("up", 0), "cls": "up"},
                {"lbl": "하락", "val": mb.get("down", 0), "cls": "down"},
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
        hist = update_supply_history(target_date, inv)
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
                "flow": supply_flow(hist, key, target_date),  # 최근 7일 흐름(누적)
            })
        if cells:
            ctx["supply_cells"] = cells

    # 3일 수급 흐름 (supply_history.json → 투자자별 3일 트렌드)
    supply_hist_path = DATA_DIR / "supply_history.json"
    supply_hist = load_json(supply_hist_path) if supply_hist_path.exists() else {}
    if supply_hist:
        sorted_dates = sorted(supply_hist.keys(), reverse=True)[:3]  # 최신순
        sorted_dates_asc = list(reversed(sorted_dates))              # 오래된→최신

        investor_defs = [
            ("foreign",     "frgn",  "외국인"),
            ("institution", "inst",  "기관"),
            ("individual",  "indiv", "개인"),
        ]

        def _sflow_summary(vals):
            signs = [v >= 0 for v in vals]
            d = lambda pos: "순매수" if pos else "순매도"
            if all(signs):
                trend = ", 규모 감소 중" if vals[-1] < vals[-2] else (", 규모 확대 중" if vals[-1] > vals[-2] else "")
                return f"{len(vals)}일 연속 순매수{trend}"
            elif not any(signs):
                trend = ", 오늘 규모 축소" if abs(vals[-1]) < abs(vals[-2]) else (", 규모 확대 중" if abs(vals[-1]) > abs(vals[-2]) else "")
                return f"{len(vals)}일 연속 순매도{trend}"
            elif signs[-1] != signs[-2]:
                return f"어제 {d(signs[-2])}, 오늘 {d(signs[-1])} 전환"
            else:
                return f"혼조세"

        # 투자자별 최대 절대값으로 각자 스케일 정규화 (표시는 최신순)
        flow_rows = []
        for key, cls, label in investor_defs:
            vals_asc = [supply_hist[d].get(key, 0) for d in sorted_dates_asc]
            max_abs = max(abs(v) for v in vals_asc) or 1
            days = []
            for d, val in zip(sorted_dates, [supply_hist[d].get(key, 0) for d in sorted_dates]):
                mm_dd = d[5:]
                sign = "+" if val >= 0 else "−"
                days.append({
                    "date": mm_dd,
                    "width": max(4, round(abs(val) / max_abs * 88)),
                    "dn": val < 0,
                    "amt": f"{sign}{abs(val):,}억",
                })
            flow_rows.append({"investor": label, "cls": cls, "days": days,
                               "summary": _sflow_summary(vals_asc)})
        ctx["supply_flow_rows"] = flow_rows

    # close_dpick — 당일 데이터가 있을 때만 (없으면 섹션 자체 미표시)
    dpick_raw = market.get("dpick", [])
    if dpick_raw:
        dpick_rows = []
        for p in dpick_raw:
            frgn = p.get("frgn_eok", 0)
            inst = p.get("inst_eok", 0)
            total = frgn + inst or 1
            fw = max(4, round(frgn / total * 80))
            iw = max(4, round(inst / total * 80))
            chg = p.get("change_pct", 0)
            dpick_rows.append({
                "name": p.get("name", ""),
                "code": p.get("code", ""),
                "mult": p.get("trade_mult", 0),
                "vol":  f"{p.get('trade_value_eok', 0):,}억",
                "chg":  f"{'▲' if chg >= 0 else '▼'} {abs(chg):.2f}%",
                "segs": [
                    {"cls": "frgn", "width": fw, "label": f"외국인 {frgn:,}억"},
                    {"cls": "inst", "width": iw, "label": f"기관 {inst:,}억"},
                ],
            })
        ctx["dpick_rows"] = dpick_rows

    return ctx


def build_analyst_quotes(data: dict) -> dict:
    """월가 애널리스트 발언 섹션 컨텍스트 빌더."""
    from urllib.parse import quote_plus
    quotes_path = BASE_DIR / "data" / "analyst_quotes.json"
    if quotes_path.exists():
        with open(quotes_path, encoding="utf-8") as f:
            analyst_quotes = json.load(f)
    else:
        analyst_quotes = []
    for q in analyst_quotes:
        if q.get("url"):
            q["search_url"] = q["url"]
        else:
            query = f"{q.get('name', '')} {q.get('source', '')} {q.get('time_label', '')}"
            q["search_url"] = f"https://www.google.com/search?q={quote_plus(query.strip())}"
    return {"analyst_quotes": analyst_quotes}


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
        new_path = BRIEFINGS_DIR / d / btype / "index.html"
        ready = new_path.exists()
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
    past_dates = sorted({b["date"] for b in briefings if b.get("date") and b["date"] != today}, reverse=True)[:20]
    past_rows, prev_month = [], None
    for d in past_dates:
        if not any((BRIEFINGS_DIR / d / t / "index.html").exists() for t in types):
            continue
        if len(past_rows) >= 10:
            break
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
    # ── analysis 로드 우선순위 ──────────────────────────────────────────────────
    # 1순위: git에 커밋된 날짜별 snapshot (재생성 시 오염 방지)
    # 2순위: 임시 live 파일 — 반드시 날짜 검증 후 사용
    snapshot_path = BRIEFINGS_DIR / target_date / internal_type / "analysis_snapshot.json"
    analysis_path = DATA_DIR / f"analysis_{src_type}.json"

    if snapshot_path.exists():
        analysis = load_json(snapshot_path)
    elif analysis_path.exists():
        analysis = load_json(analysis_path)
        analysis_date = (analysis.get("generated_at") or "")[:10]
        if analysis_date and analysis_date != target_date:
            raise RuntimeError(
                f"[generate_html] ⛔ 분석 날짜 불일치 — "
                f"analysis_{src_type}.json 생성일({analysis_date}) ≠ 대상 날짜({target_date}).\n"
                f"다른 워크플로우 실행으로 덮어써진 파일입니다. 오염된 예측 발행을 차단합니다.\n"
                f"해결: web/briefings/{target_date}/{internal_type}/analysis_snapshot.json 이 있으면 자동 사용됩니다."
            )
    else:
        analysis = {}

    generated_at = market_data.get("generated_at") or analysis.get("generated_at") or datetime.now(KST).isoformat()
    gen_time = fmt_time(generated_at)
    index_name = config["index_name"]
    prev_url, next_url = find_adjacent(internal_type, target_date)

    canonical_url = f"https://doubleshot.space/briefings/{target_date}/{internal_type}/"
    _issue_slot_map = {"kospi": "MARKET", "close": "POST_MARKET", "us": "US_MARKET"}
    ctx = {
        "date_str": target_date,
        "generated_at": generated_at,
        "generated_time": gen_time,
        "gnb_date": f"{target_date} KST {gen_time}",
        "index_name": index_name,
        "prev_url": prev_url, "next_url": next_url,
        "css_path": "/assets/style.css", "js_path": "/assets/main.js",
        "canonical_url": canonical_url,
        "briefing_type": internal_type,
        "issue_slot": _issue_slot_map.get(internal_type, "MARKET"),
        **build_list_context(target_date, internal_type),
        **build_accuracy(internal_type),
    }
    ctx["accuracy"] = bool(ctx.get("acc_30d_pct") is not None and (ctx.get("hit", 0) + ctx.get("miss", 0)) > 0)

    if internal_type == "close":
        ctx.update(build_close_sections(analysis, market_data, index_name, target_date))
        ctx["og_description"] = analysis.get("market_title", f"{target_date} 코스피 마감")
    else:
        ctx.update(build_prediction(analysis, index_name, config["pred_title"], gen_time))
        ctx.update(build_reasons(analysis))
        ctx.update(build_analyst_quotes(market_data))
        ctx["stock_picks"] = build_stock_picks(analysis, market_data, internal_type)
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["watch_items"] = analysis.get("watch_items") or analysis.get("watchpoints") or []
        if internal_type == "kospi":
            sf = analysis.get("sector_focus") or analysis.get("sector_semicon") or {}
            if sf.get("signal"):
                ctx["sector_emoji"] = sf.get("emoji", "🏭")
                ctx["sector_name"] = sf.get("sector_name", "반도체")
                ctx["sector_signal"] = sf["signal"]
                ctx["sector_paragraphs"] = sf.get("paragraphs", [])
        d = ctx.get("direction", "")
        rp = ctx.get("readout_pct", "")
        ctx["og_description"] = f"{config['pred_title']}: {d} {rp}% · 신뢰도 {ctx.get('confidence','')}%"

    template = env.get_template(config["template"])
    return template.render(**ctx), analysis


def write_output(html: str, internal_type: str, target_date: str, analysis=None):
    out_dir = BRIEFINGS_DIR / target_date / internal_type
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate_html] wrote {out_dir.relative_to(BASE_DIR)}/index.html")
    # analysis snapshot 저장 — git에 커밋되어 재생성 시 날짜 오염을 방지함
    if analysis:
        import json as _json
        snap_path = out_dir / "analysis_snapshot.json"
        snap_path.write_text(_json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[generate_html] snapshot → {snap_path.relative_to(BASE_DIR)}")


def find_latest_ready():
    """파일 수정 시간 기준 가장 최근 생성된 ready 브리핑 (internal_type, date) 반환. 없으면 None."""
    best = None  # (mtime, internal_type, date)
    for d_dir in BRIEFINGS_DIR.iterdir():
        d = d_dir.name
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', d):
            continue
        for it in DATA_FILE:
            html = d_dir / it / "index.html"
            if not html.exists():
                continue
            mtime = html.stat().st_mtime
            if best is None or mtime > best[0]:
                best = (mtime, it, d)
    return (best[1], best[2]) if best else None


def update_vercel_briefings_route(internal_type: str, target_date: str):
    """vercel.json의 /briefings/ 라우팅을 최신 브리핑으로 업데이트."""
    import re
    vercel_path = BASE_DIR / "vercel.json"
    content = vercel_path.read_text(encoding="utf-8")
    dest = f"/briefings/{target_date}/{internal_type}/index.html"
    pattern = r'("src": "\^/briefings/\?\$",\s*"dest": ")[^"]*(")'
    if not re.search(pattern, content):
        print(f"[generate_html] vercel.json /briefings/ 패턴 미일치, 건너뜀")
        return
    updated = re.sub(pattern, lambda m: m.group(1) + dest + m.group(2), content)
    if updated == content:
        print(f"[generate_html] vercel.json /briefings/ 이미 최신 ({dest})")
        return
    vercel_path.write_text(updated, encoding="utf-8")
    print(f"[generate_html] vercel.json /briefings/ → {dest}")


def _parse_close_price(html_path):
    """close 브리핑 HTML에서 KOSPI 종가 추출 (신규/레거시 포맷 모두 지원)."""
    try:
        html = html_path.read_text(encoding="utf-8")
        m = re.search(r'class="a-hero__idx-val">([0-9,]+(?:\.\d+)?)<', html)
        if not m:
            m = re.search(r'close-idx__name">KOSPI.*?close-idx__val">([0-9,]+(?:\.\d+)?)<', html, re.DOTALL)
        return m.group(1) if m else None
    except Exception:
        return None


def write_briefings_list_json():
    """web/data/briefings-list.json 을 생성한다.

    브리핑 목록 today 카드를 JS가 동적으로 패치하는 데 사용한다.
    각 날짜별 kospi/close/us 슬롯 상태를 담는다.
    """
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []

    types = ["kospi", "close", "us"]

    # 최근 30일 분 날짜만 대상
    all_dates = sorted({b["date"] for b in briefings if b.get("date")}, reverse=True)[:30]
    today = datetime.now(KST).strftime("%Y-%m-%d")
    if today not in all_dates:
        all_dates = [today] + all_dates

    slots = {}
    for d in all_dates:
        day_slots = {}
        for btype in types:
            new_path = BRIEFINGS_DIR / d / btype / "index.html"
            ready = new_path.exists()
            match = next((b for b in briefings if b.get("date") == d and TYPE_MAP.get(b.get("type"), b.get("type")) == btype), None)

            if ready:
                entry = {"state": "ready", "url": f"/briefings/{d}/{btype}/"}
                if btype == "close":
                    price = _parse_close_price(new_path)
                    entry["title"] = price or "마감"
                    entry["price"] = price or ""
                    entry["time"] = fmt_time(match.get("generated_at", "")) if match else ""
                elif match:
                    direction = match.get("predicted_direction") or match.get("direction", "")
                    up = "상승" in direction
                    entry["pill_cls"] = "up" if up else "dn"
                    entry["pill_text"] = ("▲ 상승" if up else "▼ 하락") if direction else ""
                    entry["title"] = direction or "—"
                    entry["time"] = fmt_time(match.get("generated_at", ""))
                else:
                    entry["title"] = "—"
                    entry["time"] = ""
            else:
                entry = {"state": "pending", "scheduled_time": SCHEDULED_TIMES.get(btype, "")}
            day_slots[btype] = entry
        slots[d] = day_slots

    out_path = WEB_DIR / "data" / "briefings-list.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"slots": slots}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[generate_html] wrote web/data/briefings-list.json")


def write_sitemap_xml():
    """web/sitemap.xml 을 생성한다. generate_html 실행마다 자동 갱신."""
    BASE = "https://doubleshot.space"
    today = datetime.now(KST).strftime("%Y-%m-%d")

    urls = [
        {"loc": f"{BASE}/",                              "changefreq": "daily",   "priority": "1.0"},
        {"loc": f"{BASE}/briefings/",                    "changefreq": "daily",   "priority": "0.9"},
        {"loc": f"{BASE}/stocks/income-designer/",       "changefreq": "monthly", "priority": "0.8"},
    ]

    # ready 상태인 브리핑 페이지만 포함
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []
    ready_dates = sorted({b["date"] for b in briefings if b.get("date")}, reverse=True)

    type_order = ["kospi", "close", "us"]
    for d in ready_dates:
        for btype in type_order:
            page = BRIEFINGS_DIR / d / btype / "index.html"
            if page.exists():
                lastmod = d if d <= today else today
                urls.append({
                    "loc": f"{BASE}/briefings/{d}/{btype}/",
                    "lastmod": lastmod,
                    "changefreq": "monthly",
                    "priority": "0.7",
                })

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{u['loc']}</loc>")
        if "lastmod" in u:
            lines.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        lines.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        lines.append(f"    <priority>{u['priority']}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")

    out_path = WEB_DIR / "sitemap.xml"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[generate_html] wrote web/sitemap.xml ({len(urls)} urls)")


def patch_landing_hero(analysis: dict, target_date: str):
    """랜딩 페이지 Hero 위젯을 최신 코스피 분석으로 갱신한다 (코스피 브리핑 생성 시에만 호출).

    NOTE: 랜딩 hero는 고정 예시(2026-06-22 실측 브리핑)로 운영한다 — 자동 갱신 비활성화.
    sig_items 필드가 스키마에 없어 reasons가 항상 비던 문제도 있었음. 되살리려면 아래 return을 제거하고
    sig_items 대신 telegram_signals를 쓰도록 reason_lines를 수정해야 한다.
    """
    return
    landing = WEB_DIR / "landing.html"
    if not landing.exists():
        return

    prediction = analysis.get("prediction", {})
    direction = prediction.get("direction", "상승 우위")
    up_pct = prediction.get("up_pct", 50)
    sig_items = (analysis.get("sig_items") or [])[:5]
    reason_title = analysis.get("reason_title", "")

    arrow = "↑" if "상승" in direction else "↓"
    up_count = sum(1 for s in sig_items if s.get("level") == "up")
    total = len(sig_items)
    tone = "강세" if "상승" in direction else "약세"
    conf_text = f"{tone} 우위 · 신호 {total}개 중 {up_count}개가 상승"

    reason_lines = []
    for item in sig_items:
        label = item.get("label", "")
        desc = re.sub(r"<[^>]+>", "", item.get("desc", ""))
        level = item.get("level", "neu")
        tag_cls = "brief-tag risk" if level == "dn" else "brief-tag"
        reason_lines.append(
            f'          <div class="brief-reason">'
            f'<span class="{tag_cls}">{label}</span>'
            f"<span>{desc}</span></div>"
        )

    widget = (
        "<!-- HERO-WIDGET:START -->\n"
        '      <div class="live">\n'
        '        <div class="live-top">\n'
        f'          <div class="lab"><span class="live-dot"></span>{target_date} · 코스피 당일 예측</div>\n'
        f'          <div class="live-dir">{arrow} {direction} <span class="prob mono">{up_pct}% 상승</span></div>\n'
        f'          <div class="brief-head">{reason_title}</div>\n'
        f'          <div class="brief-sub">{conf_text}</div>\n'
        "        </div>\n"
        '        <div class="brief-reasons">\n'
        + "\n".join(reason_lines) + "\n"
        "        </div>\n"
        f'        <a class="brief-more" href="/briefings/{target_date}/kospi/">이 브리핑 전체 읽기 →</a>\n'
        "      </div>\n"
        "      <!-- HERO-WIDGET:END -->"
    )

    html = landing.read_text(encoding="utf-8")
    updated = re.sub(
        r"<!-- HERO-WIDGET:START -->.*?<!-- HERO-WIDGET:END -->",
        widget,
        html,
        flags=re.DOTALL,
    )
    if updated == html:
        print("[generate_html] landing.html hero 마커 없음, 패치 생략")
        return
    landing.write_text(updated, encoding="utf-8")
    print(f"[generate_html] landing.html hero → {target_date} 패치 완료")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=list(TYPE_MAP.keys()))
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--data-file", dest="data_file", help="시장 데이터 JSON 경로")
    parser.add_argument("--write-list-only", action="store_true",
                        help="briefings-list.json 만 갱신하고 HTML 재생성 없이 종료")
    parser.add_argument("--sync-index", action="store_true",
                        help="index.html + briefings-list.json 재동기화만 하고 종료 (수동 브리핑 수정 후 사용)")
    args = parser.parse_args()

    if args.write_list_only:
        write_briefings_list_json()
        write_sitemap_xml()
        return

    if args.sync_index:
        latest = find_latest_ready()
        if latest:
            update_vercel_briefings_route(latest[0], latest[1])
        write_briefings_list_json()
        write_sitemap_xml()
        return

    if not args.type or not args.date or not args.data_file:
        parser.error("--type, --date, --data-file 은 필수입니다 (--write-list-only / --sync-index 사용 시 제외)")

    internal_type = TYPE_MAP[args.type]
    data_path = Path(args.data_file)
    market_data = load_json(data_path) if data_path.exists() else {}

    html, analysis = render_briefing(internal_type, args.date, market_data)
    write_output(html, internal_type, args.date, analysis)
    if internal_type == "kospi":
        patch_landing_hero(analysis, args.date)
    update_vercel_briefings_route(internal_type, args.date)
    write_briefings_list_json()
    write_sitemap_xml()


if __name__ == "__main__":
    main()
