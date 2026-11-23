# 장기 지표 영구 페이지(S&P 500 200일선)와 주간 장기 리포트의 화면 컨텍스트 — 결정론, LLM 없음
"""
숫자는 전부 수집 파일 그대로다(§0). 문장도 정해진 틀로 만든다 — 모델이 쓰는 문장은 없다.
그래프는 SVG를 가로로 늘려 그리고 글자·점은 HTML로 겹친다(나스닥 체크 상세 페이지와 같은 방식).
시안: docs/prototypes/2026-11-09-longterm-pages.html
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path


W, H = 1000, 300
DOW = "월화수목금토일"
EVENTS_PATH = Path(__file__).resolve().parent / "config" / "market_events.json"
SP_LOWS_PATH = Path(__file__).resolve().parent / "config" / "sp500_breadth_lows.json"


def market_events(market: str, months: list) -> list:
    """장기 지표 그래프에 찍을 큰 시장 사건(scripts/config/market_events.json, 2026-11-12).

    months = 그래프의 월(YYYY-MM) 목록(오래된 → 최근). 그 안에 있는 사건만, 가로 위치(%)와 함께 돌려준다.
    날짜와 짧은 이름만 쓴다(그래프에 숫자를 지어 붙이지 않는다). 파일이 없거나 깨졌으면 빈 목록.
    나스닥 체크 페이지가 쓴다(코스피 체크는 2026-11-15 제거)."""
    try:
        evs = json.loads(EVENTS_PATH.read_text(encoding="utf-8")).get(market) or []
    except Exception:
        return []
    out = []
    for e in evs:
        m = str(e.get("m") or "")
        if m not in months or len(months) < 2:
            continue
        i = months.index(m)
        out.append({"n": len(out) + 1, "label": e.get("label", ""), "row": int(e.get("row") or 0),
                    "pos": "top" if e.get("pos") == "top" else "bottom",
                    "left": f"{i / (len(months) - 1) * 100:.2f}%", "when": f"{int(m[:4])}.{int(m[5:7])}"})
    return out



def _left(i: int, n: int) -> str:
    return f"{i / (n - 1) * 100:.2f}%" if n > 1 else "100%"



def _md(d: str) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}"


def _md_dow(d: str) -> str:
    return f"{_md(d)}({DOW[date.fromisoformat(d).weekday()]})"


def _signed(v: float, digits: int = 1) -> str:
    return f"{v:+.{digits}f}".replace("-", "−")



def _years_every(labels: list) -> list:
    """해마다 첫 거래일 위치에 연도 눈금(일별 그래프)."""
    n = len(labels)
    out, prev = [], labels[0][:4] if labels else ""
    for i, s in enumerate(labels):
        if s[:4] != prev:
            out.append({"y": s[:4], "left": _left(i, n)})
        prev = s[:4]
    return out


def _median(xs: list) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ─────────────────────────── S&P 500 200일선 ───────────────────────────

LOW_MARK = 35.0     # 해마다 가장 낮았던 날 중 이 % 밑인 날만 그래프에 표시한다


def _at_or_before(rows: list, d: str):
    best = None
    for r in rows:
        if r[0] <= d:
            best = r
    return best


def _sp_low_notes() -> dict:
    """그래프 저점마다 무슨 일이 있었는지(scripts/config/sp500_breadth_lows.json, 월 키). 파일이 없으면 빈 dict — 목록만 빠진다."""
    try:
        raw = json.loads(SP_LOWS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict) and v.get("title") and v.get("text")}


def by_sector(items: list) -> list:
    """종목 목록을 섹터별로 묶는다(2026-11-23 사용자 요청 — 이슈 점검 표처럼 섹터 머리 + 줄).
    종목이 많은 섹터가 먼저, 같으면 목록에 먼저 나온 섹터가 먼저. 섹터 안 순서는 원래 목록 순서(시가총액·거리 순)를 지킨다."""
    groups: dict = {}
    for r in items:
        groups.setdefault(r.get("sec") or "기타", []).append(r)
    return [{"k": k, "rows": v} for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]


def sp500_context(data: dict, history: list) -> dict:
    """data/sp500_ma200.json(그날) + 누적 기록 → /stocks/sp500-200/ 컨텍스트. 기록이 1년치 미만이면 {}."""
    asof = str(data.get("asof") or "")
    rows = [r for r in history if isinstance(r, list) and len(r) == 6 and r[0] <= asof]
    if len(rows) < 250 or not rows or rows[-1][0] != asof or not data.get("dist") or not data.get("sectors"):
        return {}
    now = rows[-1]
    wk = _at_or_before(rows, (date.fromisoformat(asof) - timedelta(days=7)).isoformat())
    pcts = [r[1] for r in rows]
    yr = [r for r in rows if r[0][:4] == asof[:4]]
    ymin = min(yr, key=lambda r: r[1])
    lower = sum(1 for v in pcts if v < now[1]) / len(pcts) * 100

    labels = [r[0] for r in rows]
    n = len(rows)
    Y = lambda v: (100 - v) / 100 * H
    xs = [i * W / (n - 1) for i in range(n)]
    marks, lows = [], []
    notes = _sp_low_notes()
    for y in sorted({r[0][:4] for r in rows}):
        r = min((r for r in rows if r[0][:4] == y), key=lambda r: r[1])
        if r[1] < LOW_MARK and r is not now:
            i = labels.index(r[0])
            m = {"left": _left(i, n), "top": f"{100 - r[1]:.2f}%", "label": f"{r[0][:7]} {r[1]:.1f}%", "cls": "lo"}
            note = notes.get(r[0][:7])
            if note:                                     # 설명이 있는 저점은 번호로 찍고 아래 목록과 짝짓는다(2026-11-23, 중간선거 그래프처럼)
                m["n"] = len(lows) + 1
                after = rows[i + 63] if i + 63 < n else None
                lows.append({"n": m["n"], "d": r[0], "pct": f"{r[1]:.1f}", "title": note["title"], "text": note["text"],
                             "after": f"{after[1]:.1f}" if after else None})
            marks.append(m)
    marks.append({"left": "100%", "top": f"{100 - now[1]:.2f}%", "label": f"지금 {now[1]:.1f}%", "cls": "l lo now"})
    chart = {"w": W, "h": H, "line": " ".join(f"{x:.1f},{Y(v):.1f}" for x, v in zip(xs, pcts)),
             "y50": f"{Y(50):.1f}", "axes": [{"v": f"{v}%", "top": f"{100 - v:.2f}%"} for v in (0, 25, 50, 75, 100)],
             "marks": marks, "years": _years_every(labels), "lows": lows}

    dist = data["dist"]
    bins = dist["bins"]
    mx = max(c for _, c in bins) or 1
    cls = lambda a: "d2" if a < -20 else "d1" if a < 0 else "u1" if a < 20 else "u2" if a < 40 else "h"
    bars = [{"a": a, "c": c, "h": f"{c / mx * 92:.1f}%", "cls": cls(a),
             "title": (f"{-a - 5}~{-a}% 아래" if -50 <= a < 0 else f"{a}~{a + 5}% 위" if 0 <= a < 50
                       else "50% 넘게 아래" if a < -50 else "50% 넘게 위") + f" · {c}개"} for a, c in bins]
    nb = len(bins)
    pos0 = f"{[i for i, (a, _) in enumerate(bins) if a == 0][0] / nb * 100:.2f}%"
    hist_med = lambda j: _median([r[j] for r in rows])
    more = lambda j, v: sum(1 for r in rows if r[j] > v) / len(rows) * 100

    def tag(p, hi_word="많은 편", lo_word="적은 편"):
        return (hi_word, "hi") if p < 25 else (lo_word, "lo") if p > 75 else ("보통", "")
    cmp_rows = []
    for label, v, j, unit in (("🔥 과열 종목(200일선보다 40%↑)", dist["hot"], 3, "개"),
                              ("20% 넘게 빠진 종목", dist["deep"], 4, "개"),
                              ("가운데 종목의 거리", dist["median"], 2, "%")):
        m, p = hist_med(j), more(j, v)
        t = tag(p, "높은 편", "낮은 편") if unit == "%" else tag(p)
        fmt = (lambda x: f"{_signed(x)}%") if unit == "%" else (lambda x: f"{int(round(x))}개")
        cmp_rows.append({"label": label, "v": fmt(v), "m": fmt(m), "tag": t[0], "tcls": t[1],
                         "more": f"지금보다 {'높았던' if unit == '%' else '많았던'} 날 {p:.0f}%"})
    word = lambda t, a, b: {"많은 편": a, "적은 편": b}.get(t, "비슷")
    hot_t, deep_t = cmp_rows[0]["tag"], cmp_rows[1]["tag"]
    dsay = (f"500종목 중 <b>{dist['near']}개({dist['near'] / now[5] * 100:.0f}%)</b>가 200일선 ±20% 안에 모여 있어요. "
            f"과열 종목은 <b>{dist['hot']}개</b>로 평소({int(hist_med(3))}개)보다 "
            f"{'<b>적고</b>' if hot_t == '적은 편' else '<b>많고</b>' if hot_t == '많은 편' else '비슷하고'}, "
            f"20% 넘게 빠진 종목은 <b>{dist['deep']}개</b>로 평소({int(hist_med(4))}개)보다 "
            f"{'<b>많아요</b>' if deep_t == '많은 편' else '<b>적어요</b>' if deep_t == '적은 편' else '비슷해요'}.")
    dsay = dsay.replace("500종목", f"{now[5]}종목")
    tot = now[5]
    above = round(now[1] / 100 * tot)
    ctx = {"spx": {
        "asof": asof, "asof_label": _md_dow(asof), "pct": now[1], "above": data.get("above", above), "n": tot,
        "below_n": tot - data.get("above", above),
        "week": {"d": _md(wk[0]), "pct": wk[1]} if wk and wk is not now else None,
        "median_all": round(_median(pcts), 1), "lower": round(lower), "from": rows[0][0], "days": len(rows),
        "from_label": f"{int(rows[0][0][:4])}년 {int(rows[0][0][5:7])}월",
        "ymin": {"pct": ymin[1], "d": _md(ymin[0])}, "chart": chart,
        "sectors": [{"k": k, "a": a, "t": t, "p": a / t * 100} for k, (a, t) in data["sectors"].items()],
        "bars": bars, "pos0": pos0, "nb": nb,
        "axes_x": [{"v": f"{'+' if v > 0 else ''}{v}%", "left": f"{(v + 55) / 5 / nb * 100:.2f}%"}
                   for v in (-40, -20, 0, 20, 40)],
        "bands": [{"flex": 7, "c": "#5D97F1", "n": dist["deep"], "l": "20% 넘게 아래"},
                  {"flex": 8, "c": "#94A3B8", "n": dist["near"], "l": "±20% 안"},
                  {"flex": 4, "c": "#E86464", "n": dist["mid"], "l": "20~40% 위"},
                  {"flex": 3, "c": "#F59E0B", "n": dist["hot"], "l": "🔥 과열(40%↑)"}],
        "cmp": cmp_rows, "dsay": dsay,
        "hot": [{"t": r["t"], "n": r["n"], "sec": r.get("sec"), "gap": f"+{r['gap']}%", "x": f"{1 + r['gap'] / 100:.1f}"} for r in data.get("hot") or []],
        "up": [{"t": r["t"], "n": r["n"], "sec": r.get("sec"), "chg": _signed(r["chg"], 2), "cls": "up" if r["chg"] > 0 else "dn"} for r in data.get("up") or []],
        "below": [{"t": r["t"], "n": r["n"], "sec": r.get("sec"), "chg": _signed(r["chg"], 2), "cls": "up" if r["chg"] > 0 else "dn"} for r in data.get("below") or []],
        "points": [[r[0], r[1]] for r in rows],
    }}
    for k in ("hot", "up", "below"):
        ctx["spx"][k + "_sec"] = by_sector(ctx["spx"][k])
    return ctx


# ─────────────────────────── 주간 장기 리포트 ───────────────────────────

# 미국 지수 요일 계단(A안) 순서. 코스피는 따로 큰 계단 그림으로 그린다(종목 홈 주말 카드와 같은 그림, 2026-11-09 사용자 결정)
IDX_ORDER = (("^SOX", "반도체(SOX)"), ("^IXIC", "나스닥"), ("^GSPC", "S&P 500"), ("^DJI", "다우"))
MA200_ORDER = ("S&P500", "나스닥", "다우", "반도체")
NQ_LEVEL = {"ok": "정상", "caution": "주의", "warn": "경고"}
WEEK_NO = ("첫째", "둘째", "셋째", "넷째", "다섯째")


def _eun(word: str) -> str:
    ch = word[-1] if word else ""
    has = not ("가" <= ch <= "힣") or (ord(ch) - 0xAC00) % 28 != 0
    return word + ("은" if has else "는")


def _i_ga(word: str) -> str:
    ch = word[-1] if word else ""
    has = not ("가" <= ch <= "힣") or (ord(ch) - 0xAC00) % 28 != 0
    return word + ("이" if has else "가")


def _weekly_rows(idx: dict, monday: str) -> tuple:
    """지수별 요일 계단. 칸은 월~금 다섯 개, 그 요일에 거래가 없으면 None(휴장)."""
    rows, cums = [], [0.0]
    for key, name in IDX_ORDER:
        s = idx.get(key) or []
        if len(s) < 2:
            continue
        base = s[0][1]
        cells = [None] * 5
        row_cums = [0.0]
        prev = base
        for d, c in s[1:]:
            k = (date.fromisoformat(d) - date.fromisoformat(monday)).days
            if 0 <= k < 5:
                cells[k] = {"d": d, "pct": (c / prev - 1) * 100, "a": (prev / base - 1) * 100, "b": (c / base - 1) * 100}
                cums.append(cells[k]["b"])
                row_cums.append(cells[k]["b"])
            prev = c
        # 줄마다 그 지수의 최저·최고(지난주 종가 0% 포함)에 여유 12%를 둔다 — 한 눈금이면 반도체 옆에서
        # 나스닥·다우의 하루 ±0.5%가 납작해진다(2026-11-15 사용자 결정, 종목 홈 home-hero.js usWeekSteps와 같은 계산)
        rlo, rhi = min(row_cums), max(row_cums)
        pad = (rhi - rlo) * 0.12 or 0.5
        rows.append({"name": name, "key": key, "from": s[0][1], "to": s[-1][1], "wk": (s[-1][1] / base - 1) * 100, "cells": cells,
                     "lo": rlo - pad, "hi": rhi + pad})
    lo, hi = math.floor(min(cums) - 2), math.ceil(max(cums) + 2)
    for r in rows:
        Y = lambda v, r=r: (r["hi"] - v) / (r["hi"] - r["lo"]) * 100
        r["wk_s"] = _signed(r["wk"], 2)
        r["z"] = f"{Y(0):.2f}%"
        for c in r["cells"]:
            if c:
                top, bot = Y(max(c["a"], c["b"])), Y(min(c["a"], c["b"]))
                c.update({"top": f"{top:.2f}%", "h": f"{max(bot - top, 0.6):.2f}%", "up": c["pct"] >= 0,
                          "lab": _signed(c["pct"], 1), "lab_top": f"calc({top:.2f}% - 13px)" if c["pct"] >= 0 else f"calc({bot:.2f}% + 1px)",
                          "end": f"{Y(c['b']):.2f}%"})
    return rows, lo, hi


def _kospi_steps(s: list) -> dict:
    """코스피 큰 계단 — 지난주 종가에서 하루씩 쌓아 이번 주 종가까지(종목 홈 주말 카드 home-hero.js weekSteps와 같은 그림).
    s: [[날짜, 종가], ...] 첫 행이 지난주 마지막 종가. 거래한 날만 칸이 된다."""
    prev, week = s[0][1], s[1:]
    pts = [prev] + [c for _, c in week]
    lo, hi = min(pts), max(pts)
    pad = (hi - lo) * 0.12 or 1
    lo, hi = lo - pad, hi + pad
    y = lambda v: (hi - v) / (hi - lo) * 100
    cols, pv = [], prev
    for d, c in week:
        top, h = y(max(pv, c)), abs(c - pv) / (hi - lo) * 100
        p = (c / pv - 1) * 100
        cols.append({"cn": f"{y(pv):.1f}%", "top": f"{top:.1f}%", "h": f"{h:.1f}%", "up": c >= pv,
                     "lab": f"{_signed(p, 2)}%", "lab_top": f"{top if p >= 0 else top + h:.1f}%",
                     "dow": DOW[date.fromisoformat(d).weekday()], "md": _md(d)})
        pv = c
    bi = max(range(len(week)), key=lambda i: abs(week[i][1] / (week[i - 1][1] if i else prev) - 1))   # 가장 크게 움직인 날
    pt = week[bi][1] - (week[bi - 1][1] if bi else prev)
    return {"cols": cols, "n": len(week) + 2, "base": f"{y(prev):.1f}%", "last": f"{y(pv):.1f}%",
            "from": f"{prev:,.0f}", "to": f"{pv:,.0f}",
            "head_day": f"{cols[bi]['dow']}요일", "head_pt": f"{'+' if pt > 0 else '−' if pt < 0 else ''}{abs(pt):,.0f}p", "head_up": pt >= 0}


def weekly_context(d: dict, prev_url: str = "") -> dict:
    """weekly_report.py가 모은 값(web/weekly/{금요일}/data.json) → 주간 리포트 컨텍스트. 코스피 등락이 없으면 {}."""
    monday, end = d["monday"], d["end"]
    rows, _lo, _hi = _weekly_rows(d.get("idx") or {}, monday)
    s = (d.get("idx") or {}).get("KS") or []
    if len(s) < 2:
        return {}
    ks = {"from": s[0][1], "to": s[-1][1], "wk": (s[-1][1] / s[0][1] - 1) * 100}
    e = date.fromisoformat(end)
    first = date.fromisoformat(monday)
    tag = (f"{e.month}월 {WEEK_NO[min((e.day - 1) // 7, 4)]} 주 · {_md_dow(monday)} ~ "
           f"{_md_dow((first + timedelta(days=4)).isoformat())}")

    nq_d, sp_d, ma = d.get("nq") or {}, d.get("spx") or {}, d.get("ma200") or {}
    # 이번 주 '선을 넘은' 사건 — 미국 지수 200일선 교차 → 나스닥 체크 단계 변화 → S&P 비율 50% 교차
    events = []
    for k in MA200_ORDER:
        v = ma.get(k)
        if v and v[0] is not None and v[1] is not None and (v[0] < 0) != (v[1] < 0):
            events.append(f"{_eun(k)} 200일선 {'아래로' if v[0] < 0 else '위로'}")
    nq_now, nq_prev = nq_d.get("now") or {}, nq_d.get("prev") or {}
    if nq_now.get("level") and nq_prev.get("level") and nq_now["level"] != nq_prev["level"]:
        events.append(f"나스닥 체크는 {NQ_LEVEL[nq_now['level']]}으로")
    sp_now, sp_prev = sp_d.get("now"), sp_d.get("prev")
    if sp_now and sp_prev and (sp_now[1] < 50) != (sp_prev[1] < 50):
        events.append(f"S&P 500 200일선 위 비율은 50% {'아래로' if sp_now[1] < 50 else '위로'}")
    head = f"코스피 한 주 {_signed(ks['wk'], 1)}%" + (f", {events[0]}" if events else "")

    sub = f"코스피는 {ks['from']:,.0f}에서 {ks['to']:,.0f}으로 {'올라갔어요' if ks['to'] >= ks['from'] else '내려왔어요'}."
    crossed = [k for k in MA200_ORDER if ma.get(k) and None not in ma[k][:2] and (ma[k][0] < 0) != (ma[k][1] < 0)]
    for i, k in enumerate(crossed):
        sub += (" 미국에선 " if i == 0 else " ") + f"{_i_ga(k)} 200일선 {'아래로 내려왔어요' if ma[k][0] < 0 else '위로 올라왔어요'}."
    sox = ma.get("반도체")
    if sox and sox[0] is not None and sox[0] < -10:
        sub += f" 반도체 지수는 200일선보다 {abs(sox[0]):.1f}% 아래예요."

    cards = []
    if nq_now.get("gap") is not None and nq_prev.get("gap") is not None:
        if nq_now.get("month") != nq_prev.get("month"):
            txt = (f"달이 바뀌어 기준이 {int(nq_prev['month'][5:7])}월 고점({nq_prev['high']:,.0f})에서 "
                   f"{int(nq_now['month'][5:7])}월 고점({nq_now['high']:,.0f})으로 바뀌었어요.")
        else:
            dd = nq_now["gap"] - nq_prev["gap"]
            txt = f"한 주에 {abs(dd):.1f}%p {'올라갔어요' if dd > 0 else '내려갔어요'}." if abs(dd) >= 0.05 else "한 주 동안 그대로예요(이번 달 고점이 바뀌지 않았어요)."
        lv = nq_now.get("level")
        txt += {"ok": " 주의 기준 60%보다 아래예요.", "caution": " 주의 구간(60~70%)이에요.", "warn": " 경고 구간(70% 이상)이에요."}.get(lv, "")
        cards.append({"name": "나스닥 체크 · 60개월선 대비 월봉 고점", "url": "/stocks/nasdaq-check/",
                      "a": f"{nq_prev['gap']:.1f}%", "b": f"{nq_now['gap']:.1f}%", "txt": txt})
    if sp_now and sp_prev:
        med = sp_d.get("median_all")
        txt = ""
        if med is not None:
            txt = f"{sp_d.get('from_label', '')} 이후 중앙값({med:.1f}%)보다 {'위' if sp_now[1] > med else '아래'}예요."
        secs = sp_d.get("sectors") or []
        if len(secs) >= 2:
            txt += f" {_eun(secs[0][0])} {secs[0][1]:.0f}%, {_eun(secs[-1][0])} {secs[-1][1]:.0f}%만 선 위예요."
        cards.append({"name": "S&P 500 · 200일선 위 종목 비율", "url": "/stocks/sp500-200/",
                      "a": f"{sp_prev[1]:.1f}%", "b": f"{sp_now[1]:.1f}%", "txt": txt.strip()})
    ma_rows = []
    for k in MA200_ORDER:
        v = ma.get(k)
        if v and v[0] is not None:
            w = min(50.0, abs(v[0]) / 16 * 50)
            ma_rows.append({"k": k, "now": v[0], "prev": v[1], "s": _signed(v[0]), "ps": _signed(v[1]) if v[1] is not None else "—",
                            "w": f"{w:.1f}%", "pos": v[0] >= 0})
    ma5 = d.get("ma5") or {}
    sw = d.get("sectors_week") or []
    mx = max((abs(x["pct"]) for x in sw), default=1) or 1
    return {"wk": {
        "end": end, "monday": monday, "tag": tag, "head": head, "sub": sub, "rows": rows,
        "ks": dict(_kospi_steps(s), wk_s=_signed(ks["wk"], 2), wk=ks["wk"]),
        "cards": cards, "ma_rows": ma_rows, "ma_event": events[0] if events and "200일선" in events[0] else "",
        "ma_prev_label": _md(d.get("prev_end", "")) if d.get("prev_end") else "",
        "ma5": {k: v for k, v in ma5.items() if v and (v.get("items") or v.get("dropped"))},
        "sectors_week": [{"label": x["label"], "pct": x["pct"], "s": _signed(x["pct"], 2), "w": f"{abs(x['pct']) / mx * 50:.1f}%"} for x in sw],
        "prev_url": prev_url, "kr_last": d.get("kr_last", ""), "us_last": d.get("us_last", ""),
    }}


# ─────────────────────────── 중간선거 해 비교(2018 vs 2026) ───────────────────────────
# 시안 docs/prototypes/2026-11-15-midterm-2018.html · 기록 docs/plans/2026-11-15-midterm-2018/

MIDTERM_EVENTS_PATH = Path(__file__).resolve().parent / "config" / "midterm_events.json"
MT_RANGES = (("2y", "2년", 0, 730), ("y1", "선거 해", 0, 364), ("mid", "선거 전후", 243, 455))   # 1월 1일 = 0일
MONTHS_KO = "1월 2월 3월 4월 5월 6월 7월 8월 9월 10월 11월 12월".split()


def _sg(v: float, d: int = 1) -> str:
    return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.{d}f}"


def _mt_events(data: dict, tab: str = "2y", window: tuple | None = None) -> list:
    """설정 파일 사건 + 2026년 연중 고점(데이터에서 계산). 일(그해 1월 1일 = 0)·그날 값·예정 여부를 붙인다.
    tab — 'tabs'가 있는 사건은 그 탭에서만, 2026년 연중 저점은 확대 탭(2년이 아닌 탭)에서만 넣는다(2026-11-20).
    window — (S, E)를 주면 그 창 안의 사건만 남기고 번호를 다시 매긴다."""
    y0, y1 = data["years"]
    try:
        evs = json.loads(MIDTERM_EVENTS_PATH.read_text(encoding="utf-8")).get("events") or []
    except Exception:
        evs = []
    evs = [e for e in evs if not e.get("tabs") or tab in e["tabs"]]
    b_year = [p for p in data["b"] if p[2][:4] == str(y1)]
    if b_year:
        top = max(b_year, key=lambda p: p[1])
        evs = evs + [{"d": top[2], "label": "연중 고점"}]
        if tab != "2y":
            low = min(b_year, key=lambda p: p[1])
            if low[1] < 0:
                evs = evs + [{"d": low[2], "label": "연중 저점"}]
    out = []
    for e in sorted(evs, key=lambda e: e.get("d", "")):
        d = str(e.get("d") or "")
        yr = int(d[:4]) if d[:4].isdigit() else 0
        grp = y0 if yr in (y0, y0 + 1) else y1 if yr in (y1, y1 + 1) else None
        if grp is None:
            continue
        src = data["a"] if grp == y0 else data["b"]
        day = (date.fromisoformat(d) - date(grp, 1, 1)).days
        later = d > data["asof"]
        v = None if later else next((p[1] for p in src if p[2] >= d), None)
        out.append({"d": d, "day": day, "g": 18 if grp == y0 else 26, "label": e.get("label", "") + (" (예정)" if later else ""),
                    "v": v, "v_s": f"{_sg(v)}%" if v is not None else "아직",
                    "when": (f"{int(d[5:7])}/{int(d[8:10])}" if yr == grp else f"{d[2:4]}/{int(d[5:7])}/{int(d[8:10])}")})
    if window:
        out = [e for e in out if window[0] <= e["day"] <= window[1]]
    a_ev = [e for e in out if e["g"] == 18]
    b_ev = [e for e in out if e["g"] == 26]
    for i, e in enumerate(a_ev + b_ev, 1):
        e["n"] = i
    return a_ev + b_ev


def _mt_chart(data: dict, evs: list, S: int, E: int) -> dict:
    """창 [S, E]일만 그린다 — 세로 눈금·사건 번호·월 이름을 창에 맞춰 다시 잡는다(나스닥 체크 기간 버튼과 같은 방식)."""
    W = E - S
    pa = [p for p in data["a"] if S <= p[0] <= E]
    pb = [p for p in data["b"] if S <= p[0] <= E]
    vals = [p[1] for p in pa + pb] + [0]
    step = 5 if max(vals) - min(vals) < 26 else 10
    lo = math.floor((min(vals) - 1) / step) * step
    hi = math.ceil((max(vals) + 1) / step) * step
    xx = lambda d: (d - S) / W * 100
    yy = lambda v: (hi - v) / (hi - lo) * 100
    pl = lambda ps: " ".join(f"{xx(d) * 10:.1f},{yy(v) * 2:.1f}" for d, v, _ in ps)
    y0 = str(data["years"][0])
    a1 = [p for p in pa if p[2][:4] == y0]
    a2 = [p for p in pa if p[2][:4] != y0]
    if a1 and a2:
        a2 = [a1[-1]] + a2
    ticks = list(range(int(lo), int(hi) + 1, step))
    marks = []
    for e in evs:
        if S <= e["day"] <= E:
            marks.append(dict(e, x=xx(e["day"])))
    for g in (18, 26):                                   # 번호가 가까우면 줄을 바꿔 엇갈린다
        last = {}
        for m in [m for m in marks if m["g"] == g]:
            r = 0
            while r in last and m["x"] - last[r] < 5.2:
                r += 1
            m["row"], last[r] = r, m["x"]
            m["off"] = r * 17 if g == 18 else r * 17 - 8
    months = []
    every = 3 if W > 400 else 2 if W > 250 else 1
    for k, yr in ((0, 1), (365, 2)):
        for mi in range(12):
            d = (date(2001 + yr, mi + 1, 1) - date(2002, 1, 1)).days
            if S <= d <= E and mi % every == 0:
                months.append({"left": f"{xx(d):.1f}%", "label": MONTHS_KO[mi]})
    now = data["b"][-1]
    y0i, y1i = data["years"]
    return {
        "s": S, "e": E,
        "ticks": [{"top": f"{yy(v):.1f}%", "v": f"{_sg(v, 0)}%", "y": f"{yy(v) * 2:.1f}", "zero": v == 0} for v in ticks],
        "a1": pl(a1), "a2": pl(a2), "b": pl(pb),
        "yr": f"{xx(365) * 10:.1f}" if S < 365 < E else "",
        "labs": ([{"left": f"{xx((S + 365) / 2):.1f}%", "t": f"{y0i} · {y1i}"},
                  {"left": f"{xx((365 + E) / 2):.1f}%", "t": f"{y0i + 1} · {y1i + 1}"}] if S < 365 < E else []),
        "now": ({"left": f"{xx(now[0]):.2f}%", "top": f"{yy(now[1]):.2f}%", "s": _sg(now[1]), "flip": xx(now[0]) > 72} if S <= now[0] <= E else None),
        "marks": [{"left": f"{m['x']:.2f}%", "g": m["g"], "n": m["n"], "off": m["off"]} for m in marks],
        "months": months,
    }


# ── 트럼프 1기 vs 2기 — 취임 뒤 날수를 맞춰 겹친다(2026-11-19 사용자 요청) ─────────────────────────────
TERMS_EVENTS_PATH = Path(__file__).resolve().parent / "config" / "trump_terms_events.json"


def _tt_events(tt: dict, asof: str) -> list:
    """설정 파일 사건 + 2기 저점·고점(데이터에서 계산). 취임 뒤 날수·그날 값·예정 여부를 붙인다. 1기 먼저 번호를 매긴다."""
    try:
        evs = json.loads(TERMS_EVENTS_PATH.read_text(encoding="utf-8")).get("events") or []
    except Exception:
        evs = []
    t2 = tt["t2"]
    lo, hi = min(t2, key=lambda p: p[1]), max(t2, key=lambda p: p[1])
    for p, name in ((lo, "2기 저점"), (hi, "2기 고점")):
        if p is not t2[-1] and not any(e.get("d") == p[2] for e in evs):
            evs = evs + [{"d": p[2], "label": name}]
    s1, s2 = tt["starts"]
    out = []
    for e in sorted(evs, key=lambda e: e.get("d", "")):
        d = str(e.get("d") or "")
        if not d[:4].isdigit() or d < s1:
            continue
        g = 2 if d >= s2 else 1
        src = tt["t2"] if g == 2 else tt["t1"]
        if g == 1 and d > src[-1][2]:
            continue
        later = d > asof
        v = None if later else next((p[1] for p in src if p[2] >= d), None)
        out.append({"d": d, "day": (date.fromisoformat(d) - date.fromisoformat(s2 if g == 2 else s1)).days,
                    "g": 18 if g == 1 else 26, "label": e.get("label", "") + (" (예정)" if later else ""),
                    "v": v, "v_s": f"{_sg(v)}%" if v is not None else "아직",
                    "when": f"{d[2:4]}/{int(d[5:7])}/{int(d[8:10])}"})
    a_ev = [e for e in out if e["g"] == 18]
    b_ev = [e for e in out if e["g"] == 26]
    for i, e in enumerate(a_ev + b_ev, 1):
        e["n"] = i
    return a_ev + b_ev


def _tt_chart(tt: dict, evs: list, S: int, E: int) -> dict:
    """취임 뒤 [S, E]일만 그린다 — 중간선거 그래프(_mt_chart)와 같은 좌표·표시 규칙."""
    W = E - S
    pa = [p for p in tt["t1"] if S <= p[0] <= E]
    pb = [p for p in tt["t2"] if S <= p[0] <= E]
    vals = [p[1] for p in pa + pb] + [0]
    rng = max(vals) - min(vals)
    step = 5 if rng < 26 else 10 if rng < 60 else 20
    lo = math.floor((min(vals) - 1) / step) * step
    hi = math.ceil((max(vals) + 1) / step) * step
    xx = lambda d: (d - S) / W * 100
    yy = lambda v: (hi - v) / (hi - lo) * 100
    pl = lambda ps: " ".join(f"{xx(d) * 10:.1f},{yy(v) * 2:.1f}" for d, v, _ in ps)
    marks = [dict(e, x=xx(e["day"])) for e in evs if S <= e["day"] <= E]
    for g in (18, 26):                                   # 번호가 가까우면 줄을 바꿔 엇갈린다
        last = {}
        for m in [m for m in marks if m["g"] == g]:
            r = 0
            while r in last and m["x"] - last[r] < 5.2:
                r += 1
            m["row"], last[r] = r, m["x"]
            m["off"] = r * 17 if g == 18 else r * 17 - 8
    step_m = 2 if W <= 420 else 6 if W <= 900 else 12   # 1년 창은 2개월마다, 2년 창은 6개월마다, 4년 창은 1년마다
    xs = []
    for k in range(0, 49, step_m):
        d = round(k * 30.4375)
        if S <= d <= E:
            y, mo = divmod(k, 12)
            xs.append({"left": f"{xx(d):.1f}%", "label": "취임" if k == 0 else (f"{y}년" if y else "") + (f" {mo}개월" if mo else "")})
    yrs = [f"{xx(d) * 10:.1f}" for d in (365, 730, 1096) if S < d < E]
    now = tt["t2"][-1]
    return {
        "s": S, "e": E,
        "ticks": [{"top": f"{yy(v):.1f}%", "v": f"{_sg(v, 0)}%", "y": f"{yy(v) * 2:.1f}", "zero": v == 0}
                  for v in range(int(lo), int(hi) + 1, step)],
        "a1": pl(pa), "b": pl(pb), "yrs": yrs,
        "now": ({"left": f"{xx(now[0]):.2f}%", "top": f"{yy(now[1]):.2f}%", "s": _sg(now[1]), "flip": xx(now[0]) > 72} if S <= now[0] <= E else None),
        "marks": [{"left": f"{m['x']:.2f}%", "g": m["g"], "n": m["n"], "off": m["off"]} for m in marks],
        "months": [dict(x, label=x["label"].strip()) for x in xs],
    }


def terms_context(tt: dict, asof: str) -> dict:
    """data['terms'] → 트럼프 1기 vs 2기 그래프 컨텍스트. 없으면 {}. 문장은 정해진 틀(LLM 없음, §0)."""
    if not tt or not tt.get("t1") or not tt.get("t2") or not tt.get("same"):
        return {}
    now, same, end1 = tt["t2"][-1], tt["same"], tt["t1"][-1]
    days = now[0]
    evs = _tt_events(tt, asof)
    s1, s2 = tt["starts"]
    # 같은 기간 · 1~4년차 · 4년 전체(2026-11-21 3·4년차 추가). 2기가 아직 오지 않은 해는 1기 선만 보인다.
    ranges = [("same", "같은 기간", 0, days + 60), ("y1", "1년차", 0, 365), ("y2", "2년차", 365, max(730, days + 30)),
              ("y3", "3년차", 730, max(1096, days + 30)), ("y4", "4년차", 1096, max(end1[0], days) + 10),
              ("all", "4년 전체", 0, max(end1[0], days) + 10)]
    say = (f"취임 뒤 {days}일, 2기 S&amp;P 500은 취임 직전보다 <b>{_sg(now[1])}%</b>예요. "
           f"1기 같은 날({same['date'][2:4]}/{int(same['date'][5:7])}/{int(same['date'][8:10])})엔 <b>{_sg(same['pct'])}%</b>였어요.")
    if tt.get("corr") is not None:
        say += f" 두 곡선이 닮은 정도는 <b>{tt['corr']:.2f}</b>예요(1이면 똑같고 0이면 관계없어요)."
    say += f" 1기는 4년 끝({end1[2][:4]}년 1월)에 <b>{_sg(end1[1])}%</b>로 마쳤어요."
    return {"tt": {
        "say": say, "days": days, "now_s": _sg(now[1]), "same_s": _sg(same["pct"]),
        "start1": s1, "start2": s2, "events": evs,
        # 사건 목록은 탭마다 그 기간 사건만(번호는 모든 탭에서 같다, 2026-11-21)
        "ranges": [dict(_tt_chart(tt, evs, S, E), key=k, label=l, events=[e for e in evs if S <= e["day"] <= E],
                        ahead=(f"2기는 아직 {k[1]}년차에 들어서지 않았어요({int(s2[:4]) + int(k[1]) - 1}-01-20부터). 지금은 1기 선만 보여요."
                               if k in ("y3", "y4") and days < S else ""))
                   for k, l, S, E in ranges],
        "data_js": json.dumps({"a": tt["t1"], "b": tt["t2"]}, ensure_ascii=False, separators=(",", ":")),
    }}


# ── 트럼프 1기 vs 2기 S&P500 비교 페이지(/stocks/trump-terms/, 2026-11-21) ──────────────────────────────
SHORT = {"러셀 2000(소형주)": "소형주", "필라델피아 반도체": "반도체", "원/달러 환율": "원/달러", "WTI 유가": "유가"}


def _under(path: list) -> list:
    """[날수, %, 날짜] → 취임 뒤 가장 높았던 종가 대비 [날수, %, 날짜]."""
    peak, out = -1e9, []
    for d, v, ds in path:
        lvl = 1 + v / 100
        peak = max(peak, lvl)
        out.append([d, round((lvl / peak - 1) * 100, 2), ds])
    return out


def year_ends(path: list, limit_day: int | None = None) -> list:
    """취임 뒤 1·2·3·4년 끝(365·730·1096·1461일) 값. 그 날수에 닿지 않은 해는 넣지 않는다. 4년째는 마지막 점(퇴임 전날)."""
    out = []
    for k, d in enumerate((365, 730, 1096, 1461), 1):
        if path[-1][0] < d - 5 and not (k == 4 and path[-1][0] >= 1450):
            break
        p = [q for q in path if q[0] <= d][-1]
        out.append(p[1])
    return out


def _asset_table(rows: list) -> list:
    mx = max([abs(v) for r in rows for v in (r["t1"], r["t2"])] + [1])
    w = lambda v: f"{min(abs(v), mx) / mx * 50:.1f}"
    l = lambda v: f"{50 if v >= 0 else 50 - min(abs(v), mx) / mx * 50:.1f}"
    return [dict(r, t1_s=_sg(r["t1"]), t2_s=_sg(r["t2"]), end1_s=_sg(r["end1"]),
                 a_l=l(r["t1"]), a_w=w(r["t1"]), b_l=l(r["t2"]), b_w=w(r["t2"])) for r in rows]


def _ieyo(word: str) -> str:
    ch = word[-1] if word else ""
    has = not ("가" <= ch <= "힣") or (ord(ch) - 0xAC00) % 28 != 0
    return word + ("이에요" if has else "예요")


def _ymd(d: str) -> str:
    return f"{d[2:4]}/{int(d[5:7])}/{int(d[8:10])}"


def _us_say(rows: list) -> str:
    """미국 증시 표 위 문장 — S&P 500 비교 + 1기 같은 날보다 3%p 넘게 낮은·높은 지수."""
    sp = next((r for r in rows if r["k"] == "S&P 500"), None)
    out = []
    if sp:
        d = sp["t2"] - sp["t1"]
        word = "비슷해요" if abs(d) < 3 else "높아요" if d > 0 else "낮아요"
        out.append(f"지금 2기의 S&amp;P 500은 1기 같은 날과 {word}(<b>{_sg(sp['t2'])}%</b> vs {_sg(sp['t1'])}%).")
    rest = [r for r in rows if r["k"] != "S&P 500"]
    lo = "·".join(SHORT.get(r["k"], r["k"]) for r in rest if r["t2"] < r["t1"] - 3)
    hi_rows = [r for r in rest if r["t2"] > r["t1"] + 3]
    hi = "·".join(SHORT.get(r["k"], r["k"]) for r in hi_rows)
    gap = ""
    if hi_rows:
        top = max(hi_rows, key=lambda r: r["t2"] - r["t1"])
        gap = f"({SHORT.get(top['k'], top['k'])} <b>{_sg(top['t2'])}%</b> vs {_sg(top['t1'])}%)"
    if lo and hi:
        out.append(f"{_eun(lo)} 1기 같은 날보다 낮고, {_eun(hi)} 높아요{gap}.")
    elif lo:
        out.append(f"{_eun(lo)} 1기 같은 날보다 낮아요.")
    elif hi:
        out.append(f"{_eun(hi)} 1기 같은 날보다 높아요{gap}.")
    return " ".join(out)


def _kr_say(rows: list) -> str:
    """코스피·달러·금 표 위 문장 — 두 임기가 가장 크게 갈린 자산 + 달러 방향."""
    if not rows:
        return ""
    top = max(rows, key=lambda r: abs(r["t2"] - r["t1"]))
    out = (f"두 임기가 가장 크게 갈린 건 {_ieyo(SHORT.get(top['k'], top['k']))} — 1기 같은 날 {_sg(top['t1'])}%, "
           f"2기 지금 <b>{_sg(top['t2'])}%</b>.")
    dx = next((r for r in rows if r["k"] == "달러 지수"), None)
    if dx and dx["t1"] < 0 and dx["t2"] < 0:
        out += " 달러는 두 임기 모두 약해졌어요."
    elif dx and dx["t1"] > 0 and dx["t2"] > 0:
        out += " 달러는 두 임기 모두 강해졌어요."
    return out


def trump_context(data: dict) -> dict:
    """data/trump_terms.json → /stocks/trump-terms/ 컨텍스트. 없으면 {}. 문장은 정해진 틀(LLM 없음, §0)."""
    base = terms_context(data, data.get("asof", "")) if data else {}
    if not base:
        return {}
    tt = base["tt"]
    asof = data["asof"]
    t1, t2 = data["t1"], data["t2"]
    now, same = t2[-1], data["same"]
    days = now[0]
    # 고점에서 얼마나 빠졌나 — 취임 뒤 가장 높았던 종가 대비
    u1, u2 = _under(t1), _under(t2)
    E = max(t1[-1][0], days) + 10
    uw = _tt_chart({"t1": u1, "t2": u2}, [], 0, E)
    w2 = min(u2, key=lambda p: p[1])
    pk2 = max(t2, key=lambda p: p[1])
    u1s = [p for p in u1 if p[0] <= days][-1]
    after = [p for p in u1 if days < p[0] <= days + 92]
    deeper = min(after, key=lambda p: p[1]) if after else None
    w1 = min(u1, key=lambda p: p[1])
    uw_say = f"2기 지금은 취임 뒤 고점({_ymd(pk2[2])})보다 <b>{abs(u2[-1][1]):.1f}%</b> 아래예요." if u2[-1][1] < 0 else "2기 지금은 취임 뒤 가장 높은 곳이에요."
    if w2 is not u2[-1]:
        uw_say += f" 2기에서 가장 깊었던 건 {_ymd(w2[2])}의 <b>{_sg(w2[1])}%</b>예요."
    uw_say += f" 1기 같은 날엔 고점보다 {abs(u1s[1]):.1f}% 아래였고"
    uw_say += (f", 그 뒤 {_ymd(deeper[2])}까지 {abs(deeper[1]):.1f}% 아래로 더 깊어졌어요." if deeper and deeper[1] < u1s[1] - 1 else "요.").replace("였고요.", "였어요.")
    uw_say += f" 1기 4년 중 가장 깊었던 건 {_ymd(w1[2])}의 {_sg(w1[1])}%예요."
    # 역대 임기
    pres = [p for p in data.get("pres") or [] if p.get("same") is not None]
    pm = max([abs(p["same"]) for p in pres] + [1])
    prs = [dict(p, same_s=_sg(p["same"]), end_s=(_sg(p["end"]) + "%") if p.get("end") is not None else "진행 중",
                l=f"{50 if p['same'] >= 0 else 50 - abs(p['same']) / pm * 50:.1f}", w=f"{abs(p['same']) / pm * 50:.1f}",
                cls="t1" if p["y"] == 2017 else "t2" if p["y"] == 2025 else "")
           for p in sorted(pres, key=lambda p: -p["same"])]
    past = [p for p in pres if p["y"] != 2025]
    ends = [p["end"] for p in data.get("pres") or [] if p.get("end") is not None]
    assets = data.get("assets") or []
    us = _asset_table([a for a in assets if a["group"] == "us"])
    kr = _asset_table([a for a in assets if a["group"] == "kr"])
    fwd = data.get("fwd") or {}
    fwd_boxes = []
    for key, lab in (("low3m", "3개월 안 가장 낮았을 때"), ("m6", "6개월 뒤"), ("m12", "1년 뒤"), ("end", "4년 끝까지")):
        f = fwd.get(key)
        if f:
            fwd_boxes.append({"k": lab, "v": f["pct"], "v_s": _sg(f["pct"]), "when": _ymd(f["date"])})
    return {"tr": {
        **tt, "asof": asof, "asof_label": f"{int(asof[5:7])}/{int(asof[8:10])}", "dow": DOW[date.fromisoformat(asof).weekday()],
        "now_md": _ymd(now[2]), "same_md": _ymd(same["date"]), "corr": data.get("corr"),
        "us": us, "kr": kr, "us_say": _us_say(us), "kr_say": _kr_say(kr),
        "uw": uw, "uw_say": uw_say,
        "uw_js": json.dumps({"a": u1, "b": u2}, ensure_ascii=False, separators=(",", ":")),
        "fwd": fwd_boxes, "pres": prs, "pres_n": len(past),
        "pres_higher": sum(1 for p in past if p["same"] > now[1]),
        "ends_n": len(ends), "ends_up": sum(1 for e in ends if e > 0),
        "y1": year_ends(t1), "y2": year_ends(t2), "end1_s": _sg(t1[-1][1]),
    }}


def _moves_text(moves: list) -> str:
    """[[날짜, 값, ±1]] → '3번 올렸어요(3·6·9월)' 같은 짧은 문장. 바뀐 적이 없으면 '그대로 뒀어요'."""
    if not moves:
        return "그대로 뒀어요"
    ups = [m for m in moves if m[2] > 0]
    dns = [m for m in moves if m[2] < 0]
    mon = lambda ms: "·".join(str(int(m[0][5:7])) for m in ms) + "월"
    parts = []
    if ups:
        parts.append(f"{len(ups)}번 올렸어요({mon(ups)})" if len(ups) > 1 else f"{mon(ups)}에 올렸어요")
    if dns:
        parts.append(f"{len(dns)}번 내렸어요({mon(dns)})" if len(dns) > 1 else f"{mon(dns)}에 내렸어요")
    return ", ".join(parts)


def _moves_short(moves: list) -> str:
    """표 칸용 — '3번 인상(3·6·9월)' · '9월 인상' · '동결'."""
    if not moves:
        return "동결"
    out = []
    for sign, word in ((1, "인상"), (-1, "인하")):
        ms = [m for m in moves if m[2] == sign]
        if ms:
            mon = "·".join(str(int(m[0][5:7])) for m in ms) + "월"
            out.append(f"{len(ms)}번 {word}({mon})" if len(ms) > 1 else f"{mon} {word}")
    return ", ".join(out)


def midterm_context(data: dict) -> dict:
    """data/midterm_2018.json → /stocks/midterm-2018/ 컨텍스트. 2026년 기록이 없으면 {}. 문장은 정해진 틀(LLM 없음, §0)."""
    if not data or not data.get("b") or not data.get("a") or not data.get("same"):
        return {}
    y0, y1 = data["years"]
    now = data["b"][-1]
    asof = data["asof"]
    same = data["same"]
    evs = _mt_events(data)
    ranges = []
    for k, l, S, E in MT_RANGES:   # 2년 탭은 기본 사건 그대로, 확대 탭은 그 창의 사건을 더 자세히(2026-11-20)
        ev_k = evs if k == "2y" else _mt_events(data, k, (S, E))
        ranges.append(dict(_mt_chart(data, ev_k, S, E), key=k, label=l, events=ev_k))
    mid = data.get("midterms") or []
    base = data.get("base") or {}
    ups = sum(1 for _, v in mid if v > 0)
    m_avg = round(sum(v for _, v in mid) / len(mid), 1) if mid else None
    worst = min(mid, key=lambda r: r[1]) if mid else None
    live = data.get("midterm_live")
    BH = 40
    lowest = min([v for _, v in mid] + ([live["pct"]] if live else []), default=0)
    BL = math.floor(lowest / 10) * 10 if lowest < -2 else 0      # 조금 빠진 정도로 아래 칸을 늘리지 않는다
    by = lambda v: (BH - v) / (BH - BL) * 100
    bars = [{"y": y, "v": v, "v_s": _sg(v, 0), "hl": y == y0, "top": f"{by(max(v, 0)):.1f}%",
             "h": f"{abs(by(v) - by(0)):.1f}%"} for y, v in mid]
    if live:   # 진행 중 칸 — 선거일 종가 → 지금. 점선 막대로, 확정 통계(평균·오른 횟수)에는 넣지 않는다
        v = live["pct"]
        bars.append({"y": live["y"], "v": v, "v_s": _sg(v, 1), "live": True, "top": f"{by(max(v, 0)):.1f}%",
                     "h": f"{max(abs(by(v) - by(0)), 0.8):.1f}%",
                     "from_s": f"{int(live['from'][5:7])}/{int(live['from'][8:10])}"})
    say = (f"{y0}년 같은 날엔 <b>{_sg(same['pct'])}%</b>였어요.")
    if data.get("corr") is not None:
        say += f" 두 해 곡선이 닮은 정도는 <b>{data['corr']:.2f}</b>예요(1이면 똑같고 0이면 관계없어요)."
        if data.get("corr_daily") is not None and data["corr_daily"] < 0.3:
            say += " 큰 줄기는 비슷해도, 하루하루 움직임은 거의 관계가 없어요."
    dd, tnx, fed, ret, low = data.get("dd") or {}, data.get("tnx") or {}, data.get("fed") or {}, data.get("ret") or {}, data.get("low_a") or {}
    sd = same["date"]
    rows = [{"k": "연초 대비 S&P 500", "a": f"{_sg(same['pct'])}%", "b": f"{_sg(now[1])}%"}]
    if dd.get("a") is not None and dd.get("b") is not None:
        rows.append({"k": "그해 고점에서", "a": f"{_sg(dd['a'])}%", "b": f"{_sg(dd['b'])}%"})
    if tnx:
        rows.append({"k": "10년물 국채 금리", "a": f"{tnx['a']:.2f}%", "b": f"{tnx['b']:.2f}%"})
    if fed:
        rows.append({"k": "기준금리(상단)", "a": f"{fed['a']:.2f}% · {_moves_short(fed.get('a_moves'))}",
                     "b": f"{fed['b']:.2f}% · {_moves_short(fed.get('b_moves'))}", "hl": True})
    concl = []
    if fed:
        concl.append(f"<b>기준금리</b> — 그날까지 {y0}년엔 {_moves_text(fed.get('a_moves'))}, {y1}년엔 {_moves_text(fed.get('b_moves'))}.")
    if dd.get("a") is not None and dd.get("b") is not None:
        t = f"<b>고점에서</b> — {y0}년 같은 날엔 그해 고점보다 {abs(dd['a']):.1f}% 아래, 지금은 {abs(dd['b']):.1f}% 아래예요."
        if low and low.get("date", "") > sd:
            t += f" {y0}년엔 그 뒤 {int(low['date'][5:7])}/{int(low['date'][8:10])}까지 고점 대비 {_sg(low['dd'])}%로 깊어졌어요."
        concl.append(t)
    if tnx:
        diff = tnx["b"] - tnx["a"]
        concl.append(f"<b>10년물 금리</b> — {y1}년이 {abs(diff):.1f}%p {'높아요' if diff > 0 else '낮아요'}.")
    rest = [m for m in fed.get("after_a") or [] if m[0][:4] == str(y0) and m[0] > sd]
    after = [m for m in fed.get("after_a") or [] if m[0][:4] == str(y0 + 1)]
    r19, n19 = (ret.get("spx") or {}).get(str(y0 + 1)), (ret.get("ixic") or {}).get(str(y0 + 1))
    if r19 is not None:
        t = f"<b>{y0 + 1}년엔</b> — "
        if rest and after:
            t += f"연준이 {y0}년 {int(rest[-1][0][5:7])}월에 한 번 더 {'올린' if rest[-1][2] > 0 else '내린'} 뒤, {y0 + 1}년엔 {_moves_text(after)}. "
        elif after:
            t += f"연준이 {_moves_text(after)}. "
        t += (f"S&amp;P 500은 그해 {_sg(r19)}%" + (f"(나스닥 {_sg(n19)}%)" if n19 is not None else "")
              + (" 올랐어요." if r19 >= 0 else " 내렸어요."))
        concl.append(t)
    return {"mt": {
        "asof": asof, "asof_label": f"{int(asof[5:7])}/{int(asof[8:10])}", "dow": DOW[date.fromisoformat(asof).weekday()],
        "y0": y0, "y1": y1, "now_s": _sg(now[1]), "same_s": _sg(same["pct"]), "same_label": f"{int(sd[5:7])}/{int(sd[8:10])}",
        "say": say, "ranges": ranges, "events": evs, "rows": rows, "concl": concl,
        "bars": bars, "bar_axes": [{"top": f"{by(v):.1f}%", "v": _sg(v, 0) if v else "0"} for v in range(int(BL), BH + 1, 20)],
        "bar_base": {"top": f"{by(base['avg']):.1f}%", "avg": base["avg"], "up": base["up"]} if base else None,
        "live": bars[-1] if live else None,
        "n_mid": len(mid), "ups": ups, "m_avg": m_avg, "worst": worst,
        "first": mid[0][0] if mid else None, "last": mid[-1][0] if mid else None,
        "data_js": json.dumps({"a": [p[:2] + [p[2]] for p in data["a"]], "b": data["b"]}, ensure_ascii=False, separators=(",", ":")),
    }}
