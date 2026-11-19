# 코스피 마감 브리핑 섹션 컨텍스트 — 수급 기록·요약 형식·어제와 비교·주도주

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from html_common import BASE_DIR, DATA_DIR, WEB_DIR, load_json
from sections_shared import _chg_cell


# 마감 수급 7일 흐름용 누적 저장 (벌크 7일 API가 막혀 있어 매일 단일일 수급을 쌓아 시계열 생성)
SUPPLY_HISTORY_FILE = DATA_DIR / "supply_history.json"
SUPPLY_KEYS = ("foreign", "institution", "individual")


def _load_supply_history() -> dict:
    try:
        return load_json(SUPPLY_HISTORY_FILE)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_supply_history_web(hist: dict) -> None:
    """수급 히스토리를 web/data/로 미러링한다 — 종목 대시보드 수급 행의 '10일 추이' 패널이 fetch한다.
    data/ 는 웹 루트 밖이라 브라우저에서 직접 읽을 수 없다. 이 파일의 소유 워크플로우는
    kospi-briefing 하나뿐이므로 다른 잡과 커밋이 겹치지 않는다(SERVICE_RULES §18)."""
    if not hist:
        return
    out = WEB_DIR / "data" / "supply-history.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")


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
    write_supply_history_web(hist)
    return hist


def supply_flow(hist: dict, key: str, upto: str) -> list:
    """key 투자자의 최근 7거래일(upto 날짜 이하) 순매수 시계열(오래된→오늘, 억원)."""
    dates = sorted(d for d in hist if d <= upto)[-7:]
    return [hist[d].get(key, 0) for d in dates]


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


def _shares_label(n) -> str:
    """주 수 → '66.9만주'·'2억 2,320만주'·'9,800주'(부호 없음)."""
    n = abs(int(n))
    if n >= 100_000_000:
        eok, man = divmod(n, 100_000_000)
        return f"{eok}억 {man // 10_000:,}만주" if man >= 10_000 else f"{eok}억주"
    if n >= 10_000:
        return f"{n / 10_000:,.1f}만주"
    return f"{n:,}주"


def build_close_vs(vs: dict) -> dict:
    """/api/intraday?vs=close 요약 → '어제와 비교' 한 줄 + 사이드바 섹터 막대(종목 홈 마감 카드와 같은 값)."""
    out = {}
    k, vol, amp = vs.get("kospi") or {}, vs.get("vol") or {}, vs.get("amp") or {}
    num = lambda x: isinstance(x, (int, float))
    rel = vs.get("prev_rel") or "어제"
    cells = []
    if num(k.get("t")):
        cells.append({"lbl": "코스피", "val": f"{k['t']:+.2f}%", "cls": "up" if k["t"] > 0 else "dn" if k["t"] < 0 else "",
                      "sub": f"{rel} {k['y']:+.2f}%" if num(k.get("y")) else ""})
    if num(vol.get("diff")):
        cells.append({"lbl": "거래량", "val": f"{vol['diff']:+.1f}%", "cls": "",
                      "sub": _shares_label(vol["t"] * 1000) if num(vol.get("t")) else ""})
    if num(amp.get("t")):
        cells.append({"lbl": "진폭", "val": f"{amp['t']:.2f}%", "cls": "",
                      "sub": f"{rel} {amp['y']:.2f}%" if num(amp.get("y")) else ""})
    if cells:
        pd = str(vs.get("prev_date") or "")
        out["vs_line"] = {"title": vs.get("verdict") or "", "tone": vs.get("tone") or "", "cells": cells,
                          "basis": (f"{int(pd[5:7])}/{int(pd[8:10])} vs " if len(pd) == 10 else "")
                                   + f"{int(vs['today'][5:7])}/{int(vs['today'][8:10])} · 15:30 확정"}
    secs = [x for x in vs.get("sectors") or [] if num(x.get("t"))]
    if secs:
        secs.sort(key=lambda x: -x["t"])
        mx = max(abs(x["t"]) for x in secs) or 1
        out["sector_bars"] = [{
            "name": x.get("label", ""), "pct": f"{x['t']:+.2f}%", "cls": "up" if x["t"] >= 0 else "dn",
            "w": round(abs(x["t"]) / mx * 50, 1), "neg": x["t"] < 0,
            "move": (f"▲{x['move']}" if x["move"] > 0 else f"▼{-x['move']}") if num(x.get("move")) and x["move"] else "",
            "partial": x.get("n") if num(x.get("n")) and x["n"] < 3 else None,
        } for x in secs]
    return out


def build_close_leaders(rows: list) -> list:
    """주도주 3종목 마감 — 공식 종가·등락·외국인 5일 순매수(주). 종가가 없는 종목은 빠져 있다."""
    out = []
    for r in rows:
        if not isinstance(r.get("close"), (int, float)) or not isinstance(r.get("change_pct"), (int, float)):
            continue
        cp = r["change_pct"]
        f5 = r.get("frgn5") or {}
        row = {"name": r.get("name", ""), "close": f"{int(r['close']):,}",
               "chg": f"{'▲' if cp > 0 else '▼' if cp < 0 else ''} {cp:+.2f}%".strip(),
               "cls": "up" if cp > 0 else "dn" if cp < 0 else ""}
        if isinstance(f5.get("sum"), (int, float)):
            row["frgn5"] = ("+" if f5["sum"] > 0 else "−" if f5["sum"] < 0 else "") + _shares_label(f5["sum"])
            row["frgn5_cls"] = "up" if f5["sum"] > 0 else "dn" if f5["sum"] < 0 else ""
            fr, to = str(f5.get("from", "")), str(f5.get("to", ""))
            if len(fr) == 8 and len(to) == 8:
                row["frgn5_range"] = f"{int(fr[4:6])}/{int(fr[6:])}~{int(to[4:6])}/{int(to[6:])}"
        out.append(row)
    return out


def intraday_axis(target_date: str) -> list:
    """장중 그래프 아래 시각 5개 — 그날 개장 ~ 마감 10분 전(수능일은 10:00 ~ 16:20, §91).
    가운데 세 칸은 30분 단위로 내린다(평일 09:00 · 10:30 · 12:00 · 13:30 · 15:20)."""
    try:
        from kr_official_closes import session_hours
    except ImportError:
        from scripts.kr_official_closes import session_hours
    o, c, _ = session_hours(target_date.replace("-", ""))
    start = int(o[:2]) * 60 + int(o[2:])
    end = int(c[:2]) * 60 + int(c[2:]) - 10
    marks = [start] + [start + (end - start) * k // 4 // 30 * 30 for k in (1, 2, 3)] + [end]
    return [f"{m // 60:02d}:{m % 60:02d}" for m in marks]


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
                scp = d.get("change_pct")
                subs.append({
                    "name": name,
                    "val": f"{d['price']:,.2f}",
                    # 등락률을 모르면(None) 셀을 비운다 — 0.00%로 채우면 '보합'이라는
                    # 틀린 주장이 된다. 진짜 보합은 화살표 없이 중립색으로 구분한다.
                    **_chg_cell(scp),
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
            "intraday_axis": intraday_axis(target_date),
            "sub_indices": subs,
        })

    # close_reason 섹션
    if analysis.get("market_title") or analysis.get("reason_title"):
        fmt = analysis.get("analysis_format", "why_what_so")
        ctx["analysis_format"] = fmt
        ctx["reason_title"] = analysis.get("market_title") or analysis.get("reason_title", "")
        ctx["close_dek"] = analysis.get("dek", "")   # 타이틀 아래 서브 한 문장 — 텔레그램과 같은 필드(§62)
        ctx["comfort_line"] = _split_comfort_line(analysis.get("comfort_line", ""))
        if fmt == "brief":   # 세 줄 요약(원인·주도·다음) — 2026-10-29부터 마감 고정 형식
            ctx["brief_lines"] = [{"k": str(it.get("k", "")), "text": str(it.get("text", ""))}
                                  for it in (analysis.get("brief_lines") or [])
                                  if isinstance(it, dict) and it.get("text")]
        elif fmt == "scenario":
            ctx.update(build_scenario_context(analysis))
        elif fmt == "qa":
            ctx.update(build_qa_context(analysis))
        elif fmt == "signal":
            ctx.update(build_signal_context(analysis))
        else:  # why_what_so (옛 발행본)
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
        # 신고가·신저가는 원천이 없어 0으로 채워진 값이었다 — 그리지 않는다(2026-10-28, §0). 옛 데이터 파일의 0도 무시한다.
        if any(k in mb for k in ("upper_limit", "lower_limit")):
            rows.append({"label": "특이 종목", "cells": [
                {"lbl": "상한가", "val": mb.get("upper_limit", 0), "cls": "up"},
                {"lbl": "하한가", "val": mb.get("lower_limit", 0), "cls": "down"},
            ]})
        if rows:
            ctx["breadth_rows"] = rows

    # 어제와 비교 · 섹터별 오늘 등락 · 주도주 3종목(2026-10-29) — 수집일이 브리핑 날짜와 같을 때만(§14)
    vs = market.get("vs_close") or {}
    if vs.get("today") == target_date:
        ctx.update(build_close_vs(vs))
    if str(market.get("generated_at", ""))[:10] == target_date:
        leaders = build_close_leaders(market.get("leaders") or [])
        if leaders:
            ctx["leaders"] = leaders

    # close_sector
    sectors = market.get("sectors", [])
    if sectors:
        ctx["sectors"] = [{
            "name": s.get("name", ""),
            "pct": f"{s.get('change_pct', 0):+.1f}%",
            "cls": "up" if s.get("change_pct", 0) >= 0 else "dn",
        } for s in sectors[:8]]
        if sectors[0].get("basis"):
            ctx["sector_basis"] = sectors[0]["basis"]   # 16시 뒤 대표 3종목 공식 종가로 채운 날(2026-10-28)

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
            chg = p.get("change_pct", 0)
            row = {
                "name": p.get("name", ""),
                "code": p.get("code", ""),
                "mult": p.get("trade_mult", 0),
                "vol":  f"{p.get('trade_value_eok', 0):,}억",
                "chg":  f"{'▲' if chg >= 0 else '▼'} {abs(chg):.2f}%",
                "chg_cls": "up" if chg > 0 else "down" if chg < 0 else "",
            }
            # 옛 데이터(수급 조건이 있던 시절)에 외국인·기관 금액이 있으면 그대로 보인다. 지금 수집분엔 없다(2026-10-28).
            frgn, inst = p.get("frgn_eok"), p.get("inst_eok")
            if isinstance(frgn, (int, float)) and isinstance(inst, (int, float)):
                total = frgn + inst or 1
                row["segs"] = [
                    {"cls": "frgn", "width": max(4, round(frgn / total * 80)), "label": f"외국인 {frgn:,}억"},
                    {"cls": "inst", "width": max(4, round(inst / total * 80)), "label": f"기관 {inst:,}억"},
                ]
            dpick_rows.append(row)
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
