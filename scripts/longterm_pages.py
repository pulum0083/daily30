# 장기 지표 영구 페이지(코스피 체크·S&P 500 200일선)와 주간 장기 리포트의 화면 컨텍스트 — 결정론, LLM 없음
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

import kospi_check as kc

W, H = 1000, 300
DOW = "월화수목금토일"
EVENTS_PATH = Path(__file__).resolve().parent / "config" / "market_events.json"


def market_events(market: str, months: list) -> list:
    """장기 지표 그래프에 찍을 큰 시장 사건(scripts/config/market_events.json, 2026-11-12).

    months = 그래프의 월(YYYY-MM) 목록(오래된 → 최근). 그 안에 있는 사건만, 가로 위치(%)와 함께 돌려준다.
    날짜와 짧은 이름만 쓴다(그래프에 숫자를 지어 붙이지 않는다). 파일이 없거나 깨졌으면 빈 목록.
    나스닥 체크·코스피 체크 두 페이지가 같이 쓴다."""
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


def _pct_top(v, lo, hi) -> str:
    return f"{(hi - v) / (hi - lo) * 100:.2f}%"


def _left(i: int, n: int) -> str:
    return f"{i / (n - 1) * 100:.2f}%" if n > 1 else "100%"


def _ym_label(m: str) -> str:
    return f"{int(m[:4])}년 {int(m[5:7])}월"


def _md(d: str) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}"


def _md_dow(d: str) -> str:
    return f"{_md(d)}({DOW[date.fromisoformat(d).weekday()]})"


def _signed(v: float, digits: int = 1) -> str:
    return f"{v:+.{digits}f}".replace("-", "−")


def _years(labels: list) -> list:
    """5년마다 1월 위치에 연도 눈금. labels: 'YYYY-MM…' 오래된→최신."""
    n = len(labels)
    out, seen = [], set()
    for i, s in enumerate(labels):
        y = s[:4]
        if s[5:7] == "01" and int(y) % 5 == 0 and y not in seen:
            seen.add(y)
            out.append({"y": y, "left": _left(i, n)})
    return out


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


# ─────────────────────────── 코스피 체크 ───────────────────────────

def _bucket_label(lo, hi) -> str:
    if lo is None:
        return f"{int(hi)}% 미만"
    if hi is None:
        return f"{int(lo)}% 이상"
    return f"{int(lo)}~{int(hi)}%"


def _kospi_gap_chart(hist: list, marks: list) -> dict:
    gs = [h[1] for h in hist]
    lo = min(-50.0, math.floor(min(gs) / 50) * 50)
    hi = max(100.0, math.ceil(max(gs) / 50) * 50)
    Y = lambda v: (hi - v) / (hi - lo) * H
    xs = [i * W / (len(hist) - 1) for i in range(len(hist))]
    line = " ".join(f"{x:.1f},{Y(g):.1f}" for x, g in zip(xs, gs))
    idx = {h[0]: i for i, h in enumerate(hist)}
    return {
        "w": W, "h": H, "line": line, "lo": lo, "hi": hi, "y0": f"{Y(0):.1f}",
        "area": f"0,{Y(0):.1f} {line} {W},{Y(0):.1f}",
        "axes": [{"v": f"{int(v)}%", "top": _pct_top(v, lo, hi)} for v in range(int(lo), int(hi) + 1, 50)],
        "marks": [{"left": _left(idx[m], len(hist)), "top": _pct_top(g, lo, hi), "label": t, "cls": c}
                  for m, g, t, c in marks if m in idx],
        "years": _years([h[0] for h in hist]),
    }


def _log_chart(labels: list, a: list, b: list, ticks=(500, 1000, 2000, 5000, 10000, 20000, 50000)) -> dict:
    vals = [v for v in a + b if v and v > 0]
    lo, hi = min(vals) * 0.85, max(vals) * 1.12
    llo, lhi = math.log10(lo), math.log10(hi)
    Y = lambda v: (lhi - math.log10(v)) / (lhi - llo) * H
    xs = [i * W / (len(labels) - 1) for i in range(len(labels))]
    pts = lambda vs: " ".join(f"{x:.1f},{Y(v):.1f}" for x, v in zip(xs, vs))
    return {"w": W, "h": H, "a": pts(a), "b": pts(b), "llo": round(llo, 6), "lhi": round(lhi, 6),
            "axes": [{"v": f"{t:,}", "top": f"{Y(t) / H * 100:.2f}%"} for t in ticks if lo <= t <= hi],
            "now": {"left": "100%", "top": f"{Y(a[-1]) / H * 100:.2f}%"},
            "years": _years(labels)}


def _episode_rows(eps: list) -> list:
    rail_lo, rail_hi = -60.0, 60.0
    X = lambda v: (max(rail_lo, min(rail_hi, v)) - rail_lo) / (rail_hi - rail_lo) * 100
    rows = []
    for e in eps:
        a, b = e["months"][0], e["months"][-1]
        if a == b:
            when = _ym_label(a)
        elif a[:4] == b[:4]:
            when = f"{_ym_label(a)} ~ {int(b[5:7])}월"
        else:
            when = f"{_ym_label(a)} ~ {_ym_label(b)}"
        lo, hi, md = min(e["r12"]), max(e["r12"]), _median(e["r12"])
        dd = min(e["dd"])
        rows.append({
            "year": a[:4], "when": when, "n": len(e["months"]), "up": md > 0,
            "range": f"{_signed(lo)}%" if lo == hi else f"{_signed(lo, 0)} ~ {_signed(hi, 0)}%",
            "dd": "하락 없음" if dd >= 0 else f"{_signed(dd, 0)}%",
            "dd_v": dd, "left": f"{X(lo):.2f}%", "width": f"{X(hi) - X(lo):.2f}%",
        })
    return rows


def kospi_context(data: dict) -> dict:
    """data/kospi_check.json → /stocks/kospi-check/ 컨텍스트. 월별 기록이 2년치 미만이면 {}."""
    hist = [h for h in (data.get("history") or []) if isinstance(h, list) and len(h) == 6
            and all(isinstance(h[k], (int, float)) for k in (1, 2, 3))]
    asof = str(data.get("asof") or "")
    if len(hist) < 24 or len(asof) != 10 or not isinstance(data.get("gap_pct"), (int, float)):
        return {}
    gap = float(data["gap_pct"])
    ym, pm = data.get("year_max") or {}, data.get("prev_max")
    if ym.get("m") == hist[-1][0]:
        say = "올해 들어 가장 많이 벌어졌어요."
    else:
        say = (f"올해 {int(ym['m'][5:7])}월 <b>{_signed(ym['gap'])}%</b>(평균의 {1 + ym['gap'] / 100:.1f}배)까지 "
               f"벌어졌다가 지금은 <b>{_signed(gap)}%</b>로 {'좁혀졌어요' if gap < ym['gap'] else '벌어졌어요'}.")
    if pm:
        say += f" {int(pm['m'][:4])}년 꼭대기는 {_signed(pm['gap'])}%였어요."
    prev = hist[-2]
    marks = []
    if pm:
        marks.append((pm["m"], pm["gap"], f"{pm['m']} {_signed(pm['gap'])}%", ""))
    if ym.get("m") and ym["m"] != hist[-1][0]:
        marks.append((ym["m"], ym["gap"], f"{ym['m']} {_signed(ym['gap'])}%", "l"))
    marks.append((hist[-1][0], gap, f"지금 {_signed(gap)}%", "l lo now"))

    lo, hi = kc.bucket_of(gap)
    eps = _episode_rows(kc.episodes(hist, lo, hi))
    nu = sum(1 for e in eps if e["up"])
    nd = len(eps) - nu
    years = lambda up: "·".join(dict.fromkeys(e["year"] for e in eps if e["up"] == up))
    if nu and nd:
        concl = (f"<b>오른 때({years(True)})와 내린 때({years(False)})가 거리만으로는 갈리지 않았어요.</b> "
                 f"거리만으로 1년 뒤를 가르기 어려워서, 코스피 체크는 주의·경고 기준을 두지 않고 지금 위치만 보여줘요.")
    elif eps:
        concl = (f"<b>{len(eps)}번 모두 1년 뒤 {'올랐어요' if nu else '내렸어요'}.</b> 다만 사례가 {len(eps)}번뿐이라 "
                 f"이것만으로 1년 뒤를 말할 수는 없어요.")
    else:
        concl = ""
    table = []
    for b in kc.BUCKETS:
        rows = [h for h in hist if h[4] is not None and kc.bucket_of(h[1]) == b]
        if not rows:
            continue
        md = _median([h[4] for h in rows])
        table.append({"label": _bucket_label(*b), "now": b == (lo, hi), "months": len(rows),
                      "eps": len(kc.episodes(hist, *b)), "median": md, "median_s": _signed(md),
                      "up": round(sum(1 for h in rows if h[4] > 0) / len(rows) * 100)})
    done = [h for h in hist if h[4] is not None]
    return {"kc": {
        "gap": gap, "gap_s": _signed(gap), "close": data.get("close"), "ma60": data.get("ma60"),
        "asof": asof, "asof_label": f"{int(asof[5:7])}월 {int(asof[8:10])}일", "asof_dow": DOW[date.fromisoformat(asof).weekday()],
        "say": say, "prev": {"m": prev[0], "label": f"{int(prev[0][5:7])}월 말", "gap_s": _signed(prev[1]), "close": prev[2]},
        "year_max": ym, "year_max_s": _signed(ym["gap"]) if ym else "", "above": data.get("above"),
        "months": len(hist), "since": hist[0][0],
        "gap_chart": _kospi_gap_chart(hist, marks),
        "events": market_events("kospi", [h[0] for h in hist]),
        "level_chart": _log_chart([h[0] for h in hist], [h[2] for h in hist], [h[3] for h in hist]),
        "points": [[h[0], h[1], h[2], h[3]] for h in hist],
        "bucket": _bucket_label(lo, hi), "eps": eps, "nu": nu, "nd": nd, "concl": concl, "table": table,
        "done_from": done[0][0] if done else "", "done_to": done[-1][0] if done else "", "done_n": len(done),
    }}


# ─────────────────────────── S&P 500 200일선 ───────────────────────────

LOW_MARK = 35.0     # 해마다 가장 낮았던 날 중 이 % 밑인 날만 그래프에 표시한다


def _at_or_before(rows: list, d: str):
    best = None
    for r in rows:
        if r[0] <= d:
            best = r
    return best


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
    marks = []
    for y in sorted({r[0][:4] for r in rows}):
        r = min((r for r in rows if r[0][:4] == y), key=lambda r: r[1])
        if r[1] < LOW_MARK and r is not now:
            marks.append({"left": _left(labels.index(r[0]), n), "top": f"{100 - r[1]:.2f}%",
                          "label": f"{r[0][:7]} {r[1]:.1f}%", "cls": "lo"})
    marks.append({"left": "100%", "top": f"{100 - now[1]:.2f}%", "label": f"지금 {now[1]:.1f}%", "cls": "l lo now"})
    chart = {"w": W, "h": H, "line": " ".join(f"{x:.1f},{Y(v):.1f}" for x, v in zip(xs, pcts)),
             "y50": f"{Y(50):.1f}", "axes": [{"v": f"{v}%", "top": f"{100 - v:.2f}%"} for v in (0, 25, 50, 75, 100)],
             "marks": marks, "years": _years_every(labels)}

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
    return {"spx": {
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
        "hot": [{"t": r["t"], "n": r["n"], "gap": f"+{r['gap']}%", "x": f"{1 + r['gap'] / 100:.1f}"} for r in data.get("hot") or []],
        "up": [{"t": r["t"], "n": r["n"], "chg": _signed(r["chg"], 2), "cls": "up" if r["chg"] > 0 else "dn"} for r in data.get("up") or []],
        "below": [{"t": r["t"], "n": r["n"], "chg": _signed(r["chg"], 2), "cls": "up" if r["chg"] > 0 else "dn"} for r in data.get("below") or []],
        "points": [[r[0], r[1]] for r in rows],
    }}


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
        prev = base
        for d, c in s[1:]:
            k = (date.fromisoformat(d) - date.fromisoformat(monday)).days
            if 0 <= k < 5:
                cells[k] = {"d": d, "pct": (c / prev - 1) * 100, "a": (prev / base - 1) * 100, "b": (c / base - 1) * 100}
                cums.append(cells[k]["b"])
            prev = c
        rows.append({"name": name, "key": key, "from": s[0][1], "to": s[-1][1], "wk": (s[-1][1] / base - 1) * 100, "cells": cells})
    lo, hi = math.floor(min(cums) - 2), math.ceil(max(cums) + 2)
    Y = lambda v: (hi - v) / (hi - lo) * 100
    for r in rows:
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

    kc_d, nq_d, sp_d, ma = d.get("kc") or {}, d.get("nq") or {}, d.get("spx") or {}, d.get("ma200") or {}
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

    sub = f"코스피는 {ks['from']:,.0f}에서 {ks['to']:,.0f}으로 {'올라갔고' if ks['to'] >= ks['from'] else '내려왔고'}"
    if kc_d.get("now") is not None and kc_d.get("prev") is not None:
        sub += (f", 5년 평균과의 거리는 {kc_d['prev']:.1f}%에서 {kc_d['now']:.1f}%로 "
                f"{'벌어졌어요' if kc_d['now'] > kc_d['prev'] else '좁혀졌어요'}.")
    else:
        sub += "어요."
    crossed = [k for k in MA200_ORDER if ma.get(k) and None not in ma[k][:2] and (ma[k][0] < 0) != (ma[k][1] < 0)]
    for i, k in enumerate(crossed):
        sub += (" 미국에선 " if i == 0 else " ") + f"{_i_ga(k)} 200일선 {'아래로 내려왔어요' if ma[k][0] < 0 else '위로 올라왔어요'}."
    sox = ma.get("반도체")
    if sox and sox[0] is not None and sox[0] < -10:
        sub += f" 반도체 지수는 200일선보다 {abs(sox[0]):.1f}% 아래예요."

    cards = []
    if kc_d.get("now") is not None and kc_d.get("prev") is not None:
        diff = kc_d["now"] - kc_d["prev"]
        txt = f"한 주에 {abs(diff):.1f}%p {'벌어졌어요' if diff > 0 else '좁혀졌어요'}."
        ym, pm = kc_d.get("year_max"), kc_d.get("prev_max")
        if ym:
            txt += f" 올해 {int(ym['m'][5:7])}월엔 {ym['gap']:.1f}%" + (f", {pm['m'][:4]}년 꼭대기는 {pm['gap']:.1f}%였어요." if pm else "였어요.")
        cards.append({"name": "코스피 체크 · 5년 평균과의 거리", "url": "/stocks/kospi-check/",
                      "a": f"{kc_d['prev']:.1f}%", "b": f"{kc_d['now']:.1f}%", "txt": txt})
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
