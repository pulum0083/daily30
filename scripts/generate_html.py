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

try:
    from scripts.validate_analysis import _fetch_kospi_realdata
    import scripts.toss_client as tc
    import scripts.us_detail_data as ud
except ImportError:
    from validate_analysis import _fetch_kospi_realdata
    import toss_client as tc
    import us_detail_data as ud

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
BRIEFINGS_DIR = WEB_DIR / "briefings"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
CONFIG_DIR = Path(__file__).resolve().parent / "config"

# 정적 에셋 캐시 무효화용 버전 — style.css/main.js 변경 시 이 값을 올리면 브라우저가 새 파일을 받는다.
ASSET_VER = "20260703"
CSS_PATH = f"/assets/style.css?v={ASSET_VER}"
JS_PATH = f"/assets/main.js?v={ASSET_VER}"
US_STOCKS_PATH = CONFIG_DIR / "us_stocks.json"
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


def build_flow_context(analysis: dict) -> dict:
    """인과 흐름 체인 형식용 컨텍스트. analysis_format == 'flow' 일 때 사용."""
    steps = []
    for it in analysis.get("flow_steps", [])[:4]:
        d = it.get("dir", "neu")
        if d not in ("up", "neu", "down"):
            d = "neu"
        if it.get("title") and it.get("text"):
            steps.append({
                "stage": it.get("stage", ""),
                "dir": d,
                "title": it["title"],
                "text": it["text"],
            })
    return {"flow_lead": analysis.get("flow_lead", ""), "flow_steps": steps}


def build_keynum_context(analysis: dict) -> dict:
    """핵심 숫자 카드 형식용 컨텍스트. analysis_format == 'keynum' 일 때 사용."""
    cards = []
    for it in analysis.get("num_cards", [])[:4]:
        d = it.get("dir", "neu")
        if d not in ("up", "neu", "down"):
            d = "neu"
        if it.get("label") and it.get("value"):
            cards.append({
                "label": it["label"],
                "value": it["value"],
                "dir": d,
                "caption": it.get("caption", ""),
            })
    return {"num_cards": cards, "num_take": analysis.get("num_take", "")}


def _split_comfort_line(text: str) -> str:
    """comfort_line을 문장 단위(.!?)로 쪼개 <br>로 줄바꿈한다."""
    text = (text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return "<br>".join(p for p in parts if p)


def build_reasons(analysis: dict) -> dict:
    direction = analysis.get("prediction", {}).get("direction", "")
    fallback = {
        "상승 우위": "왜 오를까? — 오늘의 상승 시그널",
        "하락 우위": "왜 내릴까? — 오늘의 하락 시그널",
    }.get(direction, "오를까 내릴까? — 오늘의 핵심 변수")
    fmt = analysis.get("analysis_format", "why_what_so")
    ctx = {
        "analysis_format": fmt,
        "reason_title": analysis.get("reason_title") or fallback,
        "comfort_line": _split_comfort_line(analysis.get("comfort_line", "")),
    }
    if fmt == "scenario":
        ctx.update(build_scenario_context(analysis))
    elif fmt == "why_what_so":
        ctx.update(build_why_what_so_context(analysis))
    elif fmt == "qa":
        ctx.update(build_qa_context(analysis))
    elif fmt == "signal":
        ctx.update(build_signal_context(analysis))
    elif fmt == "flow":
        ctx.update(build_flow_context(analysis))
    elif fmt == "keynum":
        ctx.update(build_keynum_context(analysis))
    return ctx


def _pick_detail_url(ticker: str, internal_type: str) -> str:
    """종목 상세 영구 페이지가 실재할 때만 URL 반환 (없으면 빈 문자열 → 링크 생략).
    실재하지 않는 페이지로 링크해 '준비 중'/404를 노출하지 않기 위한 존재 게이트."""
    t = (ticker or "").strip()
    if not t:
        return ""
    if internal_type == "us":
        slug = t.lower()
        if (WEB_DIR / "stocks" / "us" / slug / "index.html").exists():
            return f"/stocks/us/{slug}/"
        return ""
    # 한국: 6자리 코드만
    if re.fullmatch(r"\d{6}", t) and (WEB_DIR / "stocks" / t / "index.html").exists():
        return f"/stocks/{t}/"
    return ""


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
            "detail_url": _pick_detail_url(p.get("ticker", ""), internal_type),
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
        ctx["comfort_line"] = _split_comfort_line(analysis.get("comfort_line", ""))
        if fmt == "scenario":
            ctx.update(build_scenario_context(analysis))
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

    # close_research — 오늘 증권가 시황 (data/research_reports.json). Gemini 요약이지만
    # 생성 시 숫자(지수·등락률) 잔존을 이미 걸러낸 원문 요약만 담고 있다.
    research_path = BASE_DIR / "data" / "research_reports.json"
    if research_path.exists():
        try:
            research_raw = json.loads(research_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            research_raw = {}
        if research_raw.get("date") == target_date:
            research_rows = [
                {"firm": r.get("firm", ""), "title": r.get("title", ""),
                 "summary": r.get("summary", ""), "url": r.get("url", "")}
                for r in research_raw.get("reports", [])
                if r.get("summary")
            ]
            if research_rows:
                ctx["research_rows"] = research_rows

    return ctx


def build_analyst_quotes(data: dict) -> dict:
    """월가 애널리스트 발언 섹션 컨텍스트 빌더.

    url(grounding에서 리졸브된 원본 기사 링크)이 없는 항목은 표시하지 않는다.
    구글 검색 폴백 링크는 실제 발언 근거를 확인할 수 없다는 뜻이라, 검증 안 된
    멘트를 노출하는 셈이 된다 — 차라리 그 항목만 조용히 제외한다(섹션 자체는
    나머지 검증된 발언이 있으면 유지).
    """
    quotes_path = BASE_DIR / "data" / "analyst_quotes.json"
    if quotes_path.exists():
        with open(quotes_path, encoding="utf-8") as f:
            raw_quotes = json.load(f)
    else:
        raw_quotes = []
    analyst_quotes = []
    for q in raw_quotes:
        if not q.get("url"):
            continue
        q["search_url"] = q["url"]
        analyst_quotes.append(q)
    return {"analyst_quotes": analyst_quotes}


def build_ib_korea_views() -> dict:
    """외국계 IB 코멘트 섹션 컨텍스트 빌더 (코스피 전용).

    url이 없는 항목은 표시하지 않는다(원본 링크 이동 보장). 데이터 없으면 빈 리스트 →
    템플릿에서 섹션 자체 생략.
    """
    views_path = BASE_DIR / "data" / "ib_korea_views.json"
    if not views_path.exists():
        return {"ib_korea_views": []}
    with open(views_path, encoding="utf-8") as f:
        payload = json.load(f)
    views = [v for v in payload.get("views", []) if v.get("url")]
    return {"ib_korea_views": views}


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
                base["pill_text"] = ("▲" if up else "▼") if direction else ""
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
def render_briefing(internal_type: str, target_date: str, market_data: dict, force: bool = False) -> str:
    env = make_env()
    config = load_json(CONFIG_DIR / f"{internal_type}.json")
    src_type = SRC_TYPE[internal_type]
    # ── analysis 로드 우선순위 ──────────────────────────────────────────────────
    # 1순위: git에 커밋된 날짜별 snapshot (재생성 시 오염 방지)
    # 2순위: 임시 live 파일 — 반드시 날짜 검증 후 사용
    # --force 시 snapshot을 무시하고 항상 최신 analysis_{type}.json을 사용 (의도적 정정 재생성용)
    snapshot_path = BRIEFINGS_DIR / target_date / internal_type / "analysis_snapshot.json"
    analysis_path = DATA_DIR / f"analysis_{src_type}.json"

    if snapshot_path.exists() and not force:
        print(f"[generate_html] ⚠️ 기존 snapshot 사용 → {snapshot_path.relative_to(BASE_DIR)} "
              f"(새로 생성된 analysis_{src_type}.json은 무시됨. 의도적 정정이면 --force 사용)")
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
    _issue_slot_map = {"kospi": "MARKET", "us": "US_MARKET"}
    ctx = {
        "date_str": target_date,
        "generated_at": generated_at,
        "generated_time": gen_time,
        "gnb_date": f"{target_date} KST {gen_time}",
        "index_name": index_name,
        "prev_url": prev_url, "next_url": next_url,
        "css_path": CSS_PATH, "js_path": JS_PATH,
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
        # 오늘의 관점(todays_view) — 코스피 오전 브리핑 전용. 없으면 None → 템플릿에서 섹션 생략.
        ctx["todays_view"] = analysis.get("todays_view") if internal_type == "kospi" else None
        if internal_type == "kospi":
            ctx.update(build_ib_korea_views())
            uls = analysis.get("us_linked_story") or {}
            if uls.get("title"):
                ctx["us_linked_title"] = uls["title"]
                ctx["us_linked_paragraphs"] = uls.get("paragraphs", [])
                ctx["us_linked_stocks"] = uls.get("related_stocks", [])
            else:
                # us_linked_story가 없으면(또는 폴백) 섹터 리뷰를 렌더한다 — 날짜 시드 랜덤으로 택1됨
                sf = analysis.get("sector_focus") or {}
                if sf.get("signal") and sf.get("paragraphs"):
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
                # 브리핑 헤드라인(reason_title/market_title) — 스트립에서 실제 타이틀 표시용
                snap_path = BRIEFINGS_DIR / d / btype / "analysis_snapshot.json"
                if snap_path.exists():
                    snap = load_json(snap_path)
                    headline = snap.get("reason_title") or snap.get("market_title")
                    if headline:
                        entry["headline"] = headline
                if btype == "close":
                    price = _parse_close_price(new_path)
                    entry["title"] = price or "마감"
                    entry["price"] = price or ""
                    entry["time"] = fmt_time(match.get("generated_at", "")) if match else ""
                elif match:
                    direction = match.get("predicted_direction") or match.get("direction", "")
                    up = "상승" in direction
                    entry["pill_cls"] = "up" if up else "dn"
                    entry["pill_text"] = ("▲" if up else "▼") if direction else ""
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


def _naver_daily_closes(code):
    """네이버 일봉 종가 리스트(오래된→최신). 토스 폴백용."""
    import urllib.request
    from datetime import timedelta
    end = datetime.now().strftime("%Y%m%d") + "0000"
    start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d") + "0000"
    url = (f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
           f"?startDateTime={start}&endDateTime={end}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        rows = json.loads(resp.read())
    return [float(r["closePrice"]) for r in rows if r.get("closePrice")]


def _naver_dated_rows(code, days=130):
    """네이버 일봉 [{localDate, closePrice}] 리스트 (오래된→최신)."""
    import urllib.request
    from datetime import timedelta
    end = datetime.now().strftime("%Y%m%d") + "0000"
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d") + "0000"
    url = (f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
           f"?startDateTime={start}&endDateTime={end}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        rows = json.loads(resp.read())
    return [r for r in rows if r.get("localDate") and r.get("closePrice")]


def _naver_sparkline_dates(code, n=20):
    """최근 N거래일의 'M/D' 날짜 리스트. sparkline hover용."""
    try:
        rows = _naver_dated_rows(code, days=60)
        recent = rows[-n:]
        return [f"{int(r['localDate'][4:6])}/{int(r['localDate'][6:8])}" for r in recent]
    except Exception:
        return []


def _parse_price(s):
    """'337,000원' 또는 '320,000~325,000원' → 숫자 (범위면 평균). 실패 시 None."""
    nums = re.findall(r'[\d,]+', str(s or ""))
    if not nums:
        return None
    vals = [float(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]
    return sum(vals) / len(vals) if vals else None


# 증권사 목표주가 정적 데이터 (2026-06-25 기준 수집)
BROKER_TARGETS = {
    "005930": {
        "count": 10,
        "min_price": 330000, "avg_price": 432000, "max_price": 560000,
        "rows": [
            {"firm": "대신증권",    "price": 560000, "op": "BUY", "when": "1일 전"},
            {"firm": "미래에셋증권", "price": 550000, "op": "BUY", "when": "2일 전"},
            {"firm": "iM증권",      "price": 480000, "op": "BUY", "when": "5일 전"},
            {"firm": "하나증권",    "price": 480000, "op": "BUY", "when": "1주 전"},
            {"firm": "신한투자증권", "price": 550000, "op": "BUY", "when": "1개월 전"},
            {"firm": "키움증권",    "price": 330000, "op": "BUY", "when": "1개월 전"},
            {"firm": "교보증권",    "price": 330000, "op": "BUY", "when": "1개월 전"},
            {"firm": "유진투자증권", "price": 360000, "op": "BUY", "when": "1개월 전"},
            {"firm": "IBK투자증권", "price": 350000, "op": "BUY", "when": "1개월 전"},
            {"firm": "한화투자증권", "price": 330000, "op": "BUY", "when": "1개월 전"},
        ],
    },
    "000660": {
        "count": 10,
        "min_price": 2500000, "avg_price": 3200000, "max_price": 4000000,
        "rows": [
            {"firm": "KB증권",      "price": 4000000, "op": "BUY", "when": "1일 전"},
            {"firm": "미래에셋증권", "price": 3800000, "op": "BUY", "when": "3일 전"},
            {"firm": "삼성증권",    "price": 3600000, "op": "BUY", "when": "5일 전"},
            {"firm": "NH투자증권",  "price": 3400000, "op": "BUY", "when": "1주 전"},
            {"firm": "한국투자증권", "price": 3200000, "op": "BUY", "when": "1주 전"},
            {"firm": "키움증권",    "price": 3000000, "op": "BUY", "when": "1주 전"},
            {"firm": "신한투자증권", "price": 2900000, "op": "BUY", "when": "1개월 전"},
            {"firm": "하나증권",    "price": 2800000, "op": "BUY", "when": "1개월 전"},
            {"firm": "대신증권",    "price": 2600000, "op": "BUY", "when": "1개월 전"},
            {"firm": "유진투자증권", "price": 2500000, "op": "BUY", "when": "1개월 전"},
        ],
    },
    "005380": {
        "count": 10,
        "min_price": 460000, "avg_price": 600000, "max_price": 750000,
        "rows": [
            {"firm": "KB증권",      "price": 750000, "op": "BUY", "when": "2일 전"},
            {"firm": "한국투자증권", "price": 700000, "op": "BUY", "when": "3일 전"},
            {"firm": "삼성증권",    "price": 680000, "op": "BUY", "when": "1주 전"},
            {"firm": "미래에셋증권", "price": 650000, "op": "BUY", "when": "1주 전"},
            {"firm": "NH투자증권",  "price": 600000, "op": "BUY", "when": "1주 전"},
            {"firm": "신한투자증권", "price": 560000, "op": "BUY", "when": "1개월 전"},
            {"firm": "하나증권",    "price": 530000, "op": "BUY", "when": "1개월 전"},
            {"firm": "키움증권",    "price": 510000, "op": "BUY", "when": "1개월 전"},
            {"firm": "대신증권",    "price": 480000, "op": "BUY", "when": "1개월 전"},
            {"firm": "유진투자증권", "price": 460000, "op": "BUY", "when": "1개월 전"},
        ],
    },
}


def _enrich_broker_targets(bt, current_price):
    """BROKER_TARGETS 항목에 현재가 기준 비율 정보를 추가해 반환."""
    if not bt or not current_price:
        return None
    min_p, max_p, avg_p = bt["min_price"], bt["max_price"], bt["avg_price"]
    span = max_p - min_p or 1
    rows = []
    for r in bt["rows"]:
        upside = round((r["price"] / current_price - 1) * 100, 1)
        rows.append({**r, "upside": upside})
    return {
        **bt,
        "rows": rows,
        "cur_pct": round((current_price - min_p) / span * 100, 1),
        "avg_pct": round((avg_p - min_p) / span * 100, 1),
        "avg_upside": round((avg_p / current_price - 1) * 100, 1),
    }


def extract_picks_for_code(code):
    """모든 analysis_snapshot.json에서 해당 종목 코드의 픽 이력 추출."""
    found = []
    for snap in sorted(BRIEFINGS_DIR.rglob("analysis_snapshot.json")):
        date_str = snap.parent.parent.name
        btype = snap.parent.name
        try:
            data = load_json(snap)
            for p in data.get("stock_picks", []):
                if p.get("ticker") == code:
                    found.append({"date": date_str, "briefing_type": btype, **p})
        except Exception:
            pass
    return found


def score_picks(code, raw_picks):
    """픽 이력에 배지(hit/run)와 수익률 추가. 데이터 부족 픽은 제외."""
    if not raw_picks:
        return []
    try:
        rows = _naver_dated_rows(code, days=130)
        dated_closes = {r["localDate"]: float(r["closePrice"]) for r in rows}
    except Exception:
        dated_closes = {}

    btype_map = {"kospi": "코스피", "us": "미국", "close": "마감"}
    scored = []
    for p in raw_picks:
        entry = _parse_price(p.get("entry"))
        target = _parse_price(p.get("target"))
        if not entry or not target:
            continue
        pick_date = p["date"].replace("-", "")
        closes_after = {d: v for d, v in dated_closes.items() if d >= pick_date}
        if not closes_after:
            continue
        max_close = max(closes_after.values())
        latest_d = max(closes_after.keys())
        latest_close = closes_after[latest_d]
        if max_close >= target:
            max_ret = round((max_close / entry - 1) * 100, 1)
            badge, badge_label = "hit", "목표 도달"
            ret_str = f"최대 +{max_ret}%"
        else:
            # 목표 미도달 — 마감 기한 개념이 없어 '진행 중'은 지난 픽에 오해를 준다.
            # 채점(hit/run 버킷)은 유지하되 표기만 중립적인 '미도달 / 최근 ±%'로 바꾼다.
            cur_ret = round((latest_close / entry - 1) * 100, 1)
            badge, badge_label = "run", "미도달"
            sign = "+" if cur_ret >= 0 else ""
            ret_str = f"최근 {sign}{cur_ret}%"

        d = p["date"]
        date_label = f"{int(d[5:7])}/{int(d[8:10])}"
        btype_label = btype_map.get(p.get("briefing_type", ""), "")
        reason = p.get("scenario_tag") or p.get("signal", "")
        scored.append({
            "date_str": f"{date_label} {btype_label}",
            "reason": reason,
            "entry_str": p.get("entry", ""),
            "target_str": p.get("target", ""),
            "badge": badge,
            "badge_label": badge_label,
            "ret_str": ret_str,
        })
    return scored


def build_trackrecord(code):
    """종목 코드 → 전체 트랙레코드 리스트 (최신순)."""
    raw = extract_picks_for_code(code)
    return list(reversed(score_picks(code, raw)))


def _briefing_accuracy():
    """briefings.json에서 코스피·미국 예측 적중률 계산."""
    bpath = DATA_DIR / "briefings.json"
    if not bpath.exists():
        return {"kospi": None, "us": None}
    records = load_json(bpath).get("briefings", [])
    result = {}
    for btype in ("kospi", "us"):
        subset = [b for b in records if b.get("type") == btype and b.get("is_correct") is not None]
        result[btype] = round(sum(1 for b in subset if b["is_correct"]) / len(subset) * 100) if subset else None
    return result


def _fetch_stock_closes(code):
    """일봉 종가 리스트(오래된→최신). 52주 범위 산출용. 토스 우선, 실패 시 네이버 폴백.

    _fetch_kospi_realdata가 캔들 원본을 반환하지 않아 부득이 재호출한다.
    sparkline은 20개뿐이라 52주 범위 산출에 부족하다.
    """
    try:
        candles = tc.get_candles(code, interval="1d", count=300)
        closes = [float(c["closePrice"]) for c in candles if c.get("closePrice")]
        if closes:
            return closes
    except Exception:
        pass
    return _naver_daily_closes(code)


def stock_realdata(code):
    """종목 상세용 실측 dict. 시세·sparkline·MA + 52주 범위 + sparkline_dates."""
    rd = _fetch_kospi_realdata(code)
    if rd.get("error"):
        return {"error": rd["error"], "price": None}
    rd["error"] = None
    rd.setdefault("ma20_dist_pct", None)
    rd.setdefault("ma200_dist_pct", None)
    try:
        closes = _fetch_stock_closes(code)
        if closes:
            lo, hi = min(closes), max(closes)
            rd["week52_low"] = round(lo, 2)
            rd["week52_high"] = round(hi, 2)
            rd["week52_pos_pct"] = round((rd["price"] - lo) / (hi - lo) * 100, 1) if hi > lo else 0
    except Exception:
        rd["week52_low"] = rd["week52_high"] = rd["week52_pos_pct"] = None
    rd["sparkline_dates"] = _naver_sparkline_dates(code)
    return rd


def sector_bellwether(snapshot: dict, sectors: dict, sector_key: str):
    """종목 섹터의 첫 미국 벨웨더 dict(t·name·change_pct) 반환. 없으면 None."""
    sec = (sectors or {}).get(sector_key) or {}
    bells = sec.get("bellwethers") or []
    if not bells:
        return None
    t = bells[0].get("t")
    info = (snapshot.get("bellwethers") or {}).get(t)
    if not info:
        return None
    return {"t": t, "name": info.get("name"), "change_pct": info.get("change_pct")}


_STOCK_SNAPSHOT_CACHE = None
_SECTORS_CACHE = None


def _load_stock_snapshot():
    global _STOCK_SNAPSHOT_CACHE
    if _STOCK_SNAPSHOT_CACHE is None:
        p = WEB_DIR / "data" / "stocks-snapshot.json"
        _STOCK_SNAPSHOT_CACHE = load_json(p) if p.exists() else {}
    return _STOCK_SNAPSHOT_CACHE


def _load_sectors():
    global _SECTORS_CACHE
    if _SECTORS_CACHE is None:
        p = CONFIG_DIR / "stock_universe.json"
        _SECTORS_CACHE = (load_json(p).get("sectors") or {}) if p.exists() else {}
    return _SECTORS_CACHE


def build_stock_page(stock, peers):
    """종목 1개의 상세 페이지를 생성·기록하고 출력 경로를 반환한다."""
    rd = stock_realdata(stock["code"])
    if rd.get("error") or rd.get("price") is None:
        raise RuntimeError(f"{stock['code']} 실측 실패: {rd.get('error')}")
    snap = _load_stock_snapshot()
    snap_stock = (snap.get("stocks") or {}).get(stock["code"], {})
    env = make_env()
    tmpl = env.get_template("stocks/detail.html")
    picks = build_trackrecord(stock["code"])
    bt_raw = BROKER_TARGETS.get(stock["code"])
    acc = _briefing_accuracy()
    # 종가 날짜는 실측 데이터의 실제 마지막 거래일 기준.
    # (스냅샷 generated_at은 생성일이라 주말·휴일에 생성하면 휴장일을 종가로 잘못 표기 — 예: 일요일 생성 시 "06-28 종가")
    spark_dates = rd.get("sparkline_dates") or []
    if spark_dates:
        mm, dd = spark_dates[-1].split("/")
        close_label = f"{int(mm):02d}-{int(dd):02d} 종가"
    else:
        snap_date = (snap.get("generated_at") or "")[:10]
        close_label = (
            f"{snap_date[5:7]}-{snap_date[8:10]} 종가" if len(snap_date) == 10
            else datetime.now().strftime("%m-%d") + " 종가"
        )
    ctx = {
        "stock": stock,
        "rd": rd,
        "peers": peers,
        "generated_label": close_label,
        "chips_ticker": stock.get("chips_ticker", ""),
        "bellwether": sector_bellwether(snap, _load_sectors(), stock.get("sector_key")),
        "foreign_rate": snap_stock.get("foreign_rate"),
        "foreign_spark": snap_stock.get("foreign_spark"),
        "supply5": snap_stock.get("supply5"),
        "financials": snap_stock.get("financials"),
        "picks": picks,
        "broker_targets": _enrich_broker_targets(bt_raw, rd.get("price")),
        "acc": acc,
        "today_str": datetime.now(KST).strftime("%Y-%m-%d"),
    }
    html = tmpl.render(**ctx)
    out_dir = WEB_DIR / "stocks" / stock["code"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return f"stocks/{stock['code']}/index.html"


def build_us_stock_page(stock, peers, env):
    """미국 종목 1개의 경량 상세 페이지를 생성·기록하고 출력 경로를 반환한다."""
    rd = ud.fetch_us_realdata(stock["ticker"])
    if rd.get("error") or rd.get("price") is None:
        raise RuntimeError(f"{stock['ticker']} 실측 실패: {rd.get('error')}")
    financials = ud.fetch_us_financials(stock["ticker"]) if stock.get("kind") == "stock" else []
    env.filters["usd"] = ud.fmt_usd
    tmpl = env.get_template("stocks/us_detail.html")
    asof = rd.get("asof") or datetime.now(KST).strftime("%Y-%m-%d")
    generated_label = f"{asof[5:7]}-{asof[8:10]} 종가"
    html = tmpl.render(
        stock=stock,
        rd=rd,
        financials=financials,
        peers=peers,
        generated_label=generated_label,
        acc=_briefing_accuracy(),
    )
    tk = stock["ticker"].lower()
    out_dir = WEB_DIR / "stocks" / "us" / tk
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    return f"stocks/us/{tk}/index.html"


def build_all_us_stocks():
    """us_stocks.json 전체를 순회 생성. peer 등락률은 실측에서 채운다(캐시 재사용, fail-fast)."""
    stocks = load_json(US_STOCKS_PATH)
    name_map = {s["ticker"]: s["name"] for s in stocks}
    rd_cache = {}

    def _peer_change(tk):
        if tk not in rd_cache:
            rd_cache[tk] = ud.fetch_us_realdata(tk)
        return rd_cache[tk].get("change_pct")

    results = []
    for s in stocks:
        peers = [
            {"ticker": pt, "name": name_map.get(pt, pt), "change_pct": _peer_change(pt)}
            for pt in s.get("peers", [])
        ]
        results.append(build_us_stock_page(s, peers, make_env()))
    return results


def build_all_stocks():
    """stocks.json 전체를 순회 생성. peer는 {code,name} 객체, 등락률은 실측에서 채운다.

    실측 호출 1회라도 실패하면 build_stock_page가 RuntimeError로 배치를 중단한다(fail-fast).
    """
    stocks = load_json(CONFIG_DIR / "stocks.json")
    reg_codes = {s["code"] for s in stocks}
    peer_rd_cache = {}  # peer 실측 중복 호출 방지 (여러 종목이 같은 peer를 공유)

    def _peer_change(code):
        if code not in peer_rd_cache:
            peer_rd_cache[code] = stock_realdata(code)
        prd = peer_rd_cache[code]
        return None if prd.get("error") else prd.get("change_pct")

    results = []
    for s in stocks:
        peers = [
            {"code": p["code"], "name": p["name"], "change_pct": _peer_change(p["code"]),
             "linked": p["code"] in reg_codes}
            for p in s.get("peers", [])
        ]
        results.append(build_stock_page(s, peers))
    return results


def write_sitemap_xml():
    """web/sitemap.xml 을 생성한다. generate_html 실행마다 자동 갱신."""
    BASE = "https://doubleshot.space"
    today = datetime.now(KST).strftime("%Y-%m-%d")

    urls = [
        {"loc": f"{BASE}/",                              "changefreq": "daily",   "priority": "1.0"},
        {"loc": f"{BASE}/briefings/",                    "changefreq": "daily",   "priority": "0.9"},
        {"loc": f"{BASE}/stocks/",                        "changefreq": "daily",   "priority": "0.9"},
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

    # 생성된 종목 상세 페이지만 포함
    for s in load_json(CONFIG_DIR / "stocks.json"):
        if (WEB_DIR / "stocks" / s["code"] / "index.html").exists():
            urls.append({
                "loc": f"{BASE}/stocks/{s['code']}/",
                "changefreq": "daily",
                "priority": "0.8",
            })

    # 생성된 미국 반도체 상세 페이지만 포함
    for s in load_json(US_STOCKS_PATH):
        tk = s["ticker"].lower()
        if (WEB_DIR / "stocks" / "us" / tk / "index.html").exists():
            urls.append({
                "loc": f"{BASE}/stocks/us/{tk}/",
                "changefreq": "weekly",
                "priority": "0.6",
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


def _fmt_krw(v: float) -> str:
    """정수 원화 천 단위 콤마 포맷."""
    return f"{int(v):,}"


def _fmt_pct(v: float) -> str:
    """부호 포함 등락률 포맷."""
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


def _pct_cls(v: float) -> str:
    if v > 0:
        return "up"
    elif v < 0:
        return "down"
    return "flat"


_SECTOR_EMOJI = {
    "semicon": "🔬", "battery": "🔋", "auto": "🚗", "defense": "🛡️",
    "ship": "🚢", "bio": "🧬", "finance": "🏦", "power": "⚡",
}

# 섹터별 한 줄 설명 — 검색 유입·체류를 위한 본문 텍스트
_SECTOR_DESC = {
    "semicon": "메모리·시스템반도체·장비를 아우르는 한국 증시 대표 섹터예요. HBM·파운드리 업황과 외국인 수급에 민감하게 움직여요.",
    "power": "변압기·전선·중전기 등 전력 인프라 종목이에요. AI 데이터센터와 노후 전력망 교체 수요로 구조적 성장 기대를 받아요.",
    "defense": "항공·미사일·지상장비 등 국방 수출 종목이에요. 글로벌 지정학 리스크와 대규모 수주 사이클에 따라 움직여요.",
    "ship": "상선·해양플랜트·특수선을 건조하는 조선 종목이에요. 친환경 선박 교체 수요와 수주 잔고, 선가 흐름이 핵심 변수예요.",
    "battery": "배터리 셀·소재·장비 종목이에요. 전기차 수요와 미국 IRA·유럽 정책, 원자재 가격 변동에 민감해요.",
    "auto": "완성차와 부품을 아우르는 자동차 종목이에요. 글로벌 판매·환율과 전동화 전환 속도가 실적을 좌우해요.",
    "bio": "제약·바이오시밀러·신약개발 종목이에요. 임상 결과와 기술수출, 금리 환경에 따라 변동성이 큰 섹터예요.",
    "finance": "은행·증권·보험 지주 종목이에요. 금리와 배당 정책, 정부 밸류업 정책의 영향을 크게 받아요.",
}


def build_sector_pages():
    """stock_universe.json + stocks-snapshot.json → 섹터별 정적 페이지 8개 생성."""
    universe_path = CONFIG_DIR / "stock_universe.json"
    snapshot_path = WEB_DIR / "data" / "stocks-snapshot.json"
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snap_stocks = snapshot.get("stocks", {})
    snapshot_date = snapshot.get("generated_at", "")[:10]

    env = make_env()
    tpl = env.get_template("pages/stock_sector.html")

    all_sectors = [
        {"key": k, "label": v["label"], "emoji": _SECTOR_EMOJI.get(k, "")}
        for k, v in universe["sectors"].items()
    ]

    for key, sector in universe["sectors"].items():
        stocks = []
        for s in sector["stocks"]:
            code = s["code"]
            measured = snap_stocks.get(code)
            if not measured:
                continue
            stocks.append({
                "code": code,
                "name": s["name"],
                "close": measured["close"],
                "close_fmt": _fmt_krw(measured["close"]),
                "change_pct": measured["change_pct"],
                "pct_fmt": _fmt_pct(measured["change_pct"]),
                "pct_cls": _pct_cls(measured["change_pct"]),
                "wk52_high": measured["wk52_high"],
                "wk52_low": measured["wk52_low"],
                "wk52_high_fmt": _fmt_krw(measured["wk52_high"]),
                "wk52_low_fmt": _fmt_krw(measured["wk52_low"]),
                "spark20": measured.get("spark20", []),
                "foreign_rate": measured.get("foreign_rate"),
            })

        # 등락률 높은 순 정렬 (None은 맨 뒤) — 섹터에서 지금 뭐가 움직이는지 우선 노출
        stocks.sort(key=lambda s: (s["change_pct"] is None, -(s["change_pct"] or 0)))

        pcts = [s["change_pct"] for s in stocks if s["change_pct"] is not None]
        avg_pct = sum(pcts) / len(pcts) if pcts else 0
        breadth = {
            "up": sum(1 for p in pcts if p > 0),
            "down": sum(1 for p in pcts if p < 0),
            "flat": sum(1 for p in pcts if p == 0),
            "total": len(pcts),
        }

        html = tpl.render(
            sector_label=sector["label"],
            sector_key=key,
            sector_emoji=_SECTOR_EMOJI.get(key, ""),
            sector_desc=_SECTOR_DESC.get(key, ""),
            stocks=stocks,
            avg_pct=avg_pct,
            avg_pct_fmt=_fmt_pct(avg_pct),
            avg_cls=_pct_cls(avg_pct),
            breadth=breadth,
            snapshot_date=snapshot_date,
            all_sectors=all_sectors,
            css_path=CSS_PATH,
            js_path=JS_PATH,
        )
        out_dir = WEB_DIR / "stocks" / "sector" / key
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "index.html"
        out_file.write_text(html, encoding="utf-8")
        print(f"섹터 페이지 {key} → {out_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=list(TYPE_MAP.keys()))
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--data-file", dest="data_file", help="시장 데이터 JSON 경로")
    parser.add_argument("--write-list-only", action="store_true",
                        help="briefings-list.json 만 갱신하고 HTML 재생성 없이 종료")
    parser.add_argument("--sync-index", action="store_true",
                        help="index.html + briefings-list.json 재동기화만 하고 종료 (수동 브리핑 수정 후 사용)")
    parser.add_argument("--sectors", action="store_true",
                        help="섹터별 종목 페이지 8개 생성하고 종료")
    parser.add_argument("--stocks", action="store_true",
                        help="stocks.json 종목 상세 페이지 일괄 생성하고 종료")
    parser.add_argument("--us-stocks", dest="us_stocks", action="store_true",
                        help="미국 반도체 종목 경량 상세 페이지 생성")
    parser.add_argument("--force", action="store_true",
                        help="기존 analysis_snapshot.json을 무시하고 최신 analysis_{type}.json으로 강제 재생성 (의도적 정정용)")
    args = parser.parse_args()

    if args.sectors:
        build_sector_pages()
        return

    if args.stocks:
        for path in build_all_stocks():
            print(f"생성: {path}")
        write_sitemap_xml()
        return

    if args.us_stocks:
        for path in build_all_us_stocks():
            print(f"생성: {path}")
        write_sitemap_xml()
        return

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

    html, analysis = render_briefing(internal_type, args.date, market_data, force=args.force)
    write_output(html, internal_type, args.date, analysis)
    if internal_type == "kospi":
        patch_landing_hero(analysis, args.date)
    update_vercel_briefings_route(internal_type, args.date)
    write_briefings_list_json()
    write_sitemap_xml()


if __name__ == "__main__":
    main()
