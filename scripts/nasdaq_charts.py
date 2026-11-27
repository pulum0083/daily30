"""나스닥 브리핑·상세 페이지 그래프 좌표 계산. 파일 저장과 HTML 조립은 호출자가 담당한다."""
import math


_NQ_W, _NQ_H, _NQ_PADR, _NQ_PADT, _NQ_PADB = 640, 190, 8, 10, 22   # 그래프 SVG 좌표(프로토타입과 같다)


def _nasdaq_chart(series: list, peak, caution: float, warn: float) -> dict:
    """2014년 이후 월별 위치 그래프 — SVG는 선·면·기준선만, 글자·점은 HTML로 겹친다(모바일에서 SVG가 가로로 눌려
    글자가 찌그러졌다). 좌표는 HTML용 퍼센트(top)·calc(left)로 같이 돌려준다."""
    pts = [s for s in series if isinstance(s, dict) and isinstance(s.get("g"), (int, float))]
    if len(pts) < 2:
        return {}
    W, H = _NQ_W, _NQ_H
    def Y(v):
        v = min(max(v, 0), 100)
        return _NQ_PADT + (H - _NQ_PADT - _NQ_PADB) * (1 - v / 100)
    xs = [i * (W - _NQ_PADR) / (len(pts) - 1) for i in range(len(pts))]
    line = " ".join(f"{x:.1f},{Y(p['g']):.1f}" for x, p in zip(xs, pts))
    left = lambda x: f"calc(34px + (100% - 34px) * {x / W:.4f})"
    top = lambda v: f"{Y(v) / H * 100:.2f}%"
    pi = max(range(len(pts)), key=lambda i: pts[i]["g"])
    pk = peak if isinstance(peak, dict) and peak.get("m") else pts[pi]
    return {
        "w": W, "h": H, "x1": W - _NQ_PADR, "line": line,
        "area": f"{xs[0]:.1f},{Y(0):.1f} {line} {xs[-1]:.1f},{Y(0):.1f}",
        "y100": f"{Y(100):.1f}", "y_warn": f"{Y(warn):.1f}", "y_caution": f"{Y(caution):.1f}",
        "h_warn": f"{Y(warn) - Y(100):.1f}", "h_caution": f"{Y(caution) - Y(warn):.1f}",
        "dot": {"left": left(xs[-1]), "top": top(pts[-1]["g"])},
        "peak_dot": {"left": left(xs[pi]), "top": top(pts[pi]["g"])},
        "axes": [{"v": int(v), "top": top(v)} for v in (warn, caution, 0)],
        "years": [{"y": p["m"][:4], "left": left(x)} for x, p in zip(xs, pts)
                  if p["m"].endswith("-01") and int(p["m"][:4]) % 2 == 0],
        "from_year": pts[0]["m"][:4],
        "peak_label": f"{int(pk['m'][:4])}년 {int(pk['m'][5:7])}월 {pk['g']:.0f}%",
    }


_NQP_W, _NQP_H = 1000, 300        # 상세 페이지 그래프 SVG 좌표 — 늘려 그리고 글자·점은 HTML로 겹친다(_nasdaq_chart와 같은 방식)


_NQP_LOG_TICKS = (500, 1000, 2000, 5000, 10000, 20000, 50000)


_NQP_RANGES = (("all", "전체", None), ("10y", "최근 10년", 120), ("5y", "최근 5년", 60),
               ("1y", "최근 1년", 13))   # 기간 버튼(2026-11-12 사용자 결정, 1년은 2026-11-27 추가 — 13개월 = 1년 전 같은 달부터)


_NQP_SUB_LOG_TICKS = (2000, 3000, 5000, 7000, 10000, 15000, 20000, 30000, 50000)   # 짧은 기간은 눈금을 촘촘히


def _nqp_years(hist: list, every: int = 5) -> list:
    """every년마다 연도 눈금(1월 위치). every=0(최근 1년)이면 분기마다 월 눈금 — 1월은 연도를 붙인다."""
    n = len(hist)
    if every == 0:
        return [{"y": (f"{h['m'][2:4]}년 1월" if h["m"].endswith("-01") else f"{int(h['m'][5:7])}월"),
                 "left": f"{i / (n - 1) * 100:.2f}%"}
                for i, h in enumerate(hist) if int(h["m"][5:7]) in (1, 4, 7, 10)]
    return [{"y": h["m"][:4], "left": f"{i / (n - 1) * 100:.2f}%"}
            for i, h in enumerate(hist) if h["m"].endswith("-01") and int(h["m"][:4]) % every == 0]


def _nqp_gap_chart(hist: list, caution: float, warn: float, full: bool = True, every: int = 5) -> dict:
    """① 월별 이격률(월봉 고점 ÷ 60개월선 − 1). 주의·경고 구간을 칠하고 0·기준선을 긋는다.
    full=False(최근 10년·5년)는 그 기간에 맞춰 세로 눈금을 다시 잡는다 — 2000년 +182%에 눌리지 않게."""
    W, H = _NQP_W, _NQP_H
    gs = [h["g"] for h in hist]
    if full:
        lo = min(-50.0, math.floor(min(gs) / 50) * 50)
        hi = max(100.0, math.ceil(max(gs) / 50) * 50)
        step = 50
    else:
        lo = min(0.0, math.floor(min(gs) / 20) * 20)
        hi = max(warn + 10, math.ceil(max(gs) / 20) * 20)
        step = 20
    Y = lambda v: (hi - v) / (hi - lo) * H
    xs = [i * W / (len(hist) - 1) for i in range(len(hist))]
    line = " ".join(f"{x:.1f},{Y(g):.1f}" for x, g in zip(xs, gs))
    top = lambda v: f"{Y(v) / H * 100:.2f}%"
    pi = max(range(len(gs)), key=lambda i: gs[i])
    return {
        "w": W, "h": H, "line": line, "lo": lo, "hi": hi,   # 짚기 말풍선이 같은 눈금으로 점을 찍는다
        "area": f"0,{Y(0):.1f} {line} {W},{Y(0):.1f}",
        "y_hi": f"{Y(hi):.1f}", "y_warn": f"{Y(warn):.1f}", "y_caution": f"{Y(caution):.1f}", "y0": f"{Y(0):.1f}",
        "h_warn": f"{Y(warn) - Y(hi):.1f}", "h_caution": f"{Y(caution) - Y(warn):.1f}",
        "axes": [{"v": f"{int(v)}%", "top": top(v)} for v in range(int(lo), int(hi) + 1, step)],
        "th": [{"v": f"{int(caution)} 주의", "top": top(caution), "cls": "caution"},
               {"v": f"{int(warn)} 경고", "top": top(warn), "cls": "warn"}],
        "dot": {"left": "100%", "top": top(gs[-1])},
        # 최고점 이름표 — 기간 첫 달·끝 달 근처면 뺀다(최근 5년은 첫 달이 최고라 '최고'가 기간 시작일 뿐이고 이름표가 잘린다)
        "peak": ({"left": f"{xs[pi] / W * 100:.2f}%", "top": top(gs[pi]),
                  "label": f"{int(hist[pi]['m'][:4])}년 {int(hist[pi]['m'][5:7])}월 {gs[pi]:+.0f}%"}
                 if 0.05 <= pi / (len(gs) - 1) <= 0.95 else None),
        "years": _nqp_years(hist, every),
    }


def _nqp_level_chart(hist: list, full: bool = True, every: int = 5) -> dict:
    """② 나스닥 월봉 고점과 60개월선 — 1990년 ~400에서 2만 7천대까지라 로그 눈금으로 그린다."""
    W, H = _NQP_W, _NQP_H
    vals = [v for h in hist for v in (h["h"], h["ma"]) if v and v > 0]
    lo = min(vals) * 0.85
    hi = max(vals) * 1.12
    llo, lhi = math.log10(lo), math.log10(hi)
    Y = lambda v: (lhi - math.log10(v)) / (lhi - llo) * H
    xs = [i * W / (len(hist) - 1) for i in range(len(hist))]
    pts = lambda key: " ".join(f"{x:.1f},{Y(h[key]):.1f}" for x, h in zip(xs, hist))
    return {
        "w": W, "h": H, "high": pts("h"), "ma": pts("ma"), "llo": round(llo, 6), "lhi": round(lhi, 6),
        "axes": [{"v": f"{t:,}", "top": f"{Y(t) / H * 100:.2f}%"}
                 for t in (_NQP_LOG_TICKS if full else _NQP_SUB_LOG_TICKS) if lo <= t <= hi],
        "years": _nqp_years(hist, every),
    }


def _nqp_ranges(hist: list, caution: float, warn: float, lp) -> list:
    """기간 버튼별 그래프 — 전체·최근 10년·최근 5년·최근 1년(2026-11-12·11-27 사용자 결정). 서버가 셋 다 그려 두고
    버튼은 보이는 것만 바꾼다. off = 그 기간 첫 달의 전체 시계열 위치(짚기 말풍선이 같은 값을 쓴다)."""
    out = []
    for key, label, k in _NQP_RANGES:
        if k and len(hist) <= k:
            continue
        h = hist[-k:] if k else hist
        every = 5 if not k else (2 if k > 60 else 1 if k > 24 else 0)
        out.append({"key": key, "label": label, "off": len(hist) - len(h), "n": len(h),
                    "span": f"{int(h[0]['m'][:4])}년 {int(h[0]['m'][5:7])}월",
                    "gap": _nqp_gap_chart(h, caution, warn, full=not k, every=every),
                    "level": _nqp_level_chart(h, full=not k, every=every),
                    "events": lp.market_events("nasdaq", [x["m"] for x in h])})
    return out
