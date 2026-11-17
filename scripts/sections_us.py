# 미국 브리핑 섹션 컨텍스트 — 프리마켓 띠·이슈·나스닥 체크·S&P 500 200일선·돌파 관찰 목록

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from briefing_data import read_dated_payload, read_snapshot_payload
from nasdaq_charts import _nasdaq_chart
from html_common import CONFIG_DIR, DATA_DIR, _dow, _market_data_is_for, _md
from sections_kospi import _strip_issue_numbers


_PM_FUTURES = [("sp500_fut", "S&P500 선물"), ("nasdaq_fut", "나스닥 선물"), ("dow_fut", "다우 선물")]
_PM_STOCKS = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]


def _pct_of(d):
    """수집 데이터의 등락률 — get_ticker_full은 change_pct, 사이드바 선물(NQ)은 chg."""
    if not isinstance(d, dict):
        return None
    v = d.get("change_pct", d.get("chg"))
    return float(v) if isinstance(v, (int, float)) else None


def build_premarket_strip(analysis: dict, market_data: dict, target_date: str, gen_time: str = "") -> dict:
    """미국 브리핑 맨 위 '프리마켓 실측' 띠 — 지수선물 3종 + 빅테크 6종의 발행 시점 실체결가 등락(§0 ①·§26).

    fetch_data가 연장시간 체결로 잡은 값을 그대로 쓴다. analysis에 넣어 스냅샷에 남기고, 시장 데이터가
    이 날짜 것이 아니면 만들지 않는다. 값이 하나도 없으면 띠를 뺀다.
    """
    saved = analysis.get("premarket")
    if not isinstance(saved, dict):
        if not _market_data_is_for(market_data, target_date):
            return {}
        fut = (market_data or {}).get("futures") or {}
        big = (market_data or {}).get("bigtech") or {}
        saved = {
            "asof": gen_time,
            "futures": [{"name": n, "pct": _pct_of(fut.get(k))} for k, n in _PM_FUTURES if _pct_of(fut.get(k)) is not None],
            "stocks": [{"name": t, "pct": _pct_of(big.get(t))} for t in _PM_STOCKS if _pct_of(big.get(t)) is not None],
        }
        if not saved["futures"] and not saved["stocks"]:
            return {}
        analysis["premarket"] = saved          # 스냅샷에 함께 저장된다
    if not saved.get("futures") and not saved.get("stocks"):
        return {}
    return {"premarket": saved}


def save_us_index_position(analysis: dict, market_data: dict, target_date: str) -> None:
    """종목 홈 구조 신호의 '미국 지수 · 200일선 대비'(§68 ⑤)를 스냅샷에 남긴다. 브리핑 페이지에는 그리지 않는다.

    다른 날 시장 데이터로 채우지 않고(§14), 한 줄에 다른 세션이 섞이지 않게 가장 최근 종가 날짜만 남긴다.
    """
    if isinstance(analysis.get("us_index_position"), dict) or not _market_data_is_for(market_data, target_date):
        return
    rows = (market_data or {}).get("index_ma200") or {}
    asof = max((str(v.get("date") or "") for v in rows.values()), default="")
    items = [{"name": n, "pct": v["pct"]} for n, v in rows.items() if v.get("date") == asof and v.get("pct") is not None]
    if asof and items:
        analysis["us_index_position"] = {"asof": asof, "items": items}


NASDAQ_BACKTEST_PATH = CONFIG_DIR / "nasdaq_overheat_backtest.json"
_NQ_BADGE = {"ok": "✓ 정상", "caution": "⚠️ 주의", "warn": "🚨 경고"}


def build_struct_signal(analysis: dict) -> dict:
    """미국 브리핑 '구조 신호' — 나스닥 체크 한 줄. 종목 홈 nasdaqRow(home-hero.js)와 같은 값·눈금이다(§68 ⑤).

    재료는 스냅샷의 nasdaq_overheat다. 값이 없으면 블록째 뺀다.
    60% 이상이면 페이지의 '나스닥 체크' 섹션(§65)이 같은 값을 그래프와 함께 보여주므로 템플릿이 이 블록을 뺀다.
    """
    import nasdaq_overheat as nq
    data = analysis.get("nasdaq_overheat") or {}
    if not isinstance(data.get("gap_pct"), (int, float)):
        return {}
    gap = float(data["gap_pct"])
    top = max(80, math.ceil((gap + 5) / 10) * 10)
    x = lambda v: round(max(0.0, min(v, top)) / top * 100, 1)
    level = nq.level_of(gap)
    month = str(data.get("month") or "")
    return {"struct_sig": {
        "gap": gap, "level": level, "badge": _NQ_BADGE[level],
        "x_gap": x(gap), "x_caution": x(nq.CAUTION), "x_warn": x(nq.WARN),
        "w_caution": round((nq.WARN - nq.CAUTION) / top * 100, 1),
        "caution": int(nq.CAUTION), "warn": int(nq.WARN),
        "month_label": f"{int(month[5:7])}월" if len(month) == 7 else "이번 달",
    }}


def build_nasdaq_check(analysis: dict, target_date: str = "") -> dict:
    """미국 브리핑 '나스닥 체크' 섹션의 컨텍스트(§65).

    월봉 5개월선 코너와 같은 구조다 — 스냅샷이 1순위고, 데이터 파일은 브리핑 날짜와 같을 때만 쓴다(§14·§45).
    데이터가 없거나 하단 설명의 출처인 백테스트 파일이 없으면 빈 dict → 섹션 생략.
    텔레그램(call_claude._nasdaq_change_lines)은 주의·경고에 처음 닿은 날과 전달 고점을 넘은 날에만 싣는다.
    """
    import nasdaq_overheat as nq
    data = analysis.get("nasdaq_overheat")
    if not isinstance(data, dict):
        data = _read_nasdaq_overheat(target_date)
        if data is not None:
            # 스냅샷에 함께 저장된다. 1990년부터의 긴 시계열(history)은 상세 페이지 전용이라 뺀다 —
            # 브리핑마다 수십 KB가 쌓인다(/stocks/nasdaq-check/, 2026-10-28).
            data = {k: v for k, v in data.items() if k != "history"}
            analysis["nasdaq_overheat"] = data
    if not data or not isinstance(data.get("gap_pct"), (int, float)):
        return {}
    try:
        bt = json.loads(NASDAQ_BACKTEST_PATH.read_text(encoding="utf-8"))
        bt["caution_band"]["fwd12_avg_pct"], bt["warn"]["dd20_pct"]          # 필수 키 확인
    except Exception as e:
        print(f"[generate_html] 나스닥 체크 백테스트 수치 없음({e}) — 섹션 생략")
        return {}
    gap = float(data["gap_pct"])
    level = nq.level_of(gap)                     # 저장된 level이 아니라 같은 판정 함수로 다시 정한다
    if level == "ok":
        # 정상 구간엔 섹션을 숨긴다 — 매일 같은 '정상'이 반복돼 뜻이 없었다(2026-10-26 사용자 결정).
        # 데이터는 위에서 analysis에 이미 넣었으므로 스냅샷·종목 홈 구조 신호에는 그대로 남는다.
        return {}
    month = str(data.get("month") or "")
    month_label = ("이번 달" if target_date and month == target_date[:7]
                   else (f"{int(month[5:7])}월" if len(month) == 7 else "이번 달"))
    return {"nq": {
        "gap": gap, "level": level, "badge": _NQ_BADGE[level],
        "high": data.get("high"), "ma60": data.get("ma60"),
        "streak": int(data.get("streak") or 0) if level != "ok" else 0,
        "pin": max(0.0, min(gap, 100.0)), "month_label": month_label,
        "chart": _nasdaq_chart(data.get("series") or [], data.get("peak"), nq.CAUTION, nq.WARN),
        "bt": bt, "caution": nq.CAUTION, "warn": nq.WARN,
    }}


def _read_nasdaq_overheat(target_date: str):
    """data/nasdaq_overheat.json 을 읽되 브리핑 날짜가 같을 때만 돌려준다."""
    return read_dated_payload(DATA_DIR / "nasdaq_overheat.json", target_date)


SP500_CHIPS = 8        # 아래로·위로 칩은 시가총액 순 8개까지, 나머지는 '더 보기'(2026-11-08 시안 A안)


def read_sp500_ma200(analysis: dict, target_date: str = ""):
    """S&P 500 200일선 — 스냅샷 우선, 새 파일은 날짜 확인 후 스냅샷에 남긴다."""
    return read_snapshot_payload(analysis, "sp500_ma200", DATA_DIR, target_date)


def build_sp500_ma200(analysis: dict, target_date: str = "") -> dict:
    """미국 브리핑 'S&P 500 · 200일선 체크' 섹션(2026-11-08 사용자 결정, 시안 A안).

    맨 위 200일선 위 비율과 최근 60거래일 흐름, 과열 종목(200일선보다 40% 넘게 높음), 위로·아래로 넘은 종목 칩 순.
    특별한 날(50% 넘나듦·하루 5%p 넘게)에만 싣는다. 아니면 빈 dict → 섹션 생략. 묶음마다 종목이 없으면 그 묶음만 빠진다.
    """
    d = read_sp500_ma200(analysis, target_date)
    if not d or not isinstance(d.get("above_pct"), (int, float)) or not d.get("asof"):
        return {}
    # 특별한 날에만 브리핑에 싣는다 — 텔레그램과 같은 판정(2026-11-09 사용자 결정). 데이터는 위에서 analysis에 남아
    # 스냅샷·상세 페이지(/stocks/sp500-200/)는 매일 그대로다. 전날 비율이 없으면 판단할 수 없어 뺀다.
    from sp500_ma200 import event_of
    if not isinstance(d.get("above_pct_prev"), (int, float)) or not event_of(d["above_pct"], d["above_pct_prev"]):
        return {}
    br = [b for b in d.get("breadth") or [] if isinstance(b, list) and len(b) == 2 and isinstance(b[1], (int, float))]
    spark = {}
    if len(br) >= 2:
        vals = [b[1] for b in br]
        lo, hi = min(vals + [40.0]) - 3, max(vals + [70.0]) + 3
        Y = lambda v: (hi - v) / (hi - lo) * 100
        X = lambda i: i / (len(br) - 1) * 100
        spark = {"path": " ".join(f"{'L' if i else 'M'}{X(i):.2f} {Y(b[1]):.2f}" for i, b in enumerate(br)),
                 "y50": f"{Y(50):.2f}", "dot": f"{Y(br[-1][1]):.2f}",
                 "from": _md(br[0][0]), "to": _md(br[-1][0])}

    def sectors(rows):
        c = {}
        for r in rows:
            c[r.get("sec") or ""] = c.get(r.get("sec") or "", 0) + 1
        return " · ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda x: -x[1])[:4] if k)

    hot = [r for r in d.get("hot") or [] if isinstance(r.get("gap"), (int, float))]
    mx = max([r["gap"] for r in hot] + [1.0])
    asof = d["asof"]
    dp = round(d["above_pct"] - d["above_pct_prev"], 1) if isinstance(d.get("above_pct_prev"), (int, float)) else None
    return {"spx": {
        "asof_label": f"{_md(asof)}({_dow(asof)}) 종가 기준",
        "above_pct": d["above_pct"], "above": d.get("above"), "n": d.get("n"),
        "prev_pct": d.get("above_pct_prev"), "dp": dp, "spark": spark,
        "below": d.get("below") or [], "up": d.get("up") or [], "chips": SP500_CHIPS,
        "below_secs": sectors(d.get("below") or []),
        "hot": [dict(r, w=f"{r['gap'] / mx * 100:.1f}", x=f"{1 + r['gap'] / 100:.1f}") for r in hot],
        "hot_pct": 40,
    }}


BREAKOUT_BACKTEST_PATH = CONFIG_DIR / "breakout_watch_backtest.json"


def read_breakout_watch(analysis: dict, target_date: str = ""):
    """돌파 관찰 목록 — 스냅샷 우선, 새 파일은 날짜 확인 후 스냅샷에 남긴다."""
    return read_snapshot_payload(analysis, "breakout_watch", DATA_DIR, target_date)


def _cap_label(v) -> str:
    """시가총액 표기 — $1.2조 · $850억(달러 그대로, 원화로 바꾸지 않는다). 없으면 빈 문자열."""
    if not isinstance(v, (int, float)) or v <= 0:
        return ""
    return f"${v / 1e12:.1f}조" if v >= 1e12 else f"${v / 1e8:,.0f}억"


def _bw_line(pts: list) -> dict:
    """가격 선 — 점 위치(%)·이름표 정렬·손절선~지금 구간. pts = [(키, 값, 이름표, 위/아래)]."""
    vs = [v for _, v, _, _ in pts]
    lo, hi = min(vs), max(vs)
    X = lambda v: 8 + (v - lo) / (hi - lo) * 84 if hi > lo else 50
    out = []
    for k, v, lab, pos in pts:
        x = X(v)
        out.append({"k": k, "v": v, "lab": lab, "pos": pos, "x": f"{x:.1f}",
                    "al": "l" if x < 15 else "r" if x > 85 else ""})
    xs = {p["k"]: float(p["x"]) for p in out}
    a, b = sorted((xs["stop"], xs["now"]))
    return {"pts": out, "zone_l": f"{a:.1f}", "zone_w": f"{b - a:.1f}"}


def build_breakout_watch(analysis: dict, target_date: str = "") -> dict:
    """미국 브리핑 '돌파 관찰 목록' 섹션(2026-11-16 사용자 결정, 시안 2026-11-16-breakout-watch-clear.html, §88).

    1 기다리는 종목 → 2 오늘 돌파한 종목 → 3 돌파한 뒤 결과. 숫자는 breakout_watch.py가 만든 그대로 — 새 숫자를 만들지 않는다.
    과거 성적 파일이 없으면 섹션째 뺀다(성적 없이 종목만 보이면 '사라'로 읽힌다). 세 묶음이 모두 비어도 뺀다.
    """
    d = read_breakout_watch(analysis, target_date)
    if not d or not d.get("asof"):
        return {}
    try:
        bt = json.loads(BREAKOUT_BACKTEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    today, wait, track = d.get("today") or [], d.get("wait") or [], d.get("track") or []
    if not (today or wait or track):
        return {}
    today, wait, track = ([dict(r, cap_label=_cap_label(r.get("cap"))) for r in x] for x in (today, wait, track))
    tcards = [dict(r, to_stop=round(abs(r["stop"] / r["close"] - 1) * 100, 1),
                   line=_bw_line([("stop", r["stop"], "손절선", "b"), ("now", r["close"], "지금", "t"),
                                  ("in", r["entry"], "돌파한 가격", "b")]))
              for r in today]
    wcards = [dict(r, line=_bw_line([("stop", r["stop"], "넘으면 손절선", "b"), ("now", r["close"], "지금", "t"),
                                     ("in", r["pivot"], "넘을 선", "b")]))
              for r in wait]
    lab = {"live": "진행 중 · {}거래일째", "stop": "손절로 끝 · {}거래일", "exit": "추세 끝(20일 최저가) · {}거래일"}
    rows = [dict(r, label=lab.get(r["state"], "{}").format(r["days"]), from_md=_md(r["from"])) for r in track]
    done = [r for r in track if r["state"] != "live"]
    asof = d["asof"]
    return {"bw": {
        "asof_label": f"{_md(asof)}({_dow(asof)}) 종가 기준",
        "today": tcards, "wait": wcards, "wait_more": d.get("wait_more") or 0, "track": rows,
        "n_wait": len(wcards) + (d.get("wait_more") or 0), "n_done": len(done),
        "win": sum(1 for r in done if r["pct"] > 0), "lose": sum(1 for r in done if r["pct"] <= 0),
        "n_live": len(track) - len(done), "bt": bt,
    }}


def build_issues(analysis: dict) -> dict:
    """analysis.issues → 렌더용 이슈 리스트. title 없는 항목 제외, title·body 숫자 가드 적용."""
    issues = []
    for it in (analysis.get("issues") or []):
        title = _strip_issue_numbers(it.get("title", ""))
        if not title:
            continue
        entry = {"title": title, "body": _strip_issue_numbers(it.get("body", ""))}
        for side in ("down", "up"):
            s = it.get(side)
            if isinstance(s, dict) and (s.get("label") or s.get("tickers")):
                entry[side] = {"label": s.get("label", ""), "tickers": list(s.get("tickers") or [])}
        issues.append(entry)
    return {"issues": issues}


def build_us_tone(market_data: dict) -> dict:
    """leading_signal.compute_prior_us() 방향(실측 프리마켓·SOX·VIX 기반)을
    '오늘의 관점' 배경색 CSS 클래스로 매핑한다. 숫자·점수는 절대 반환하지 않는다 —
    코스피 dir_cls와 동일한 방식으로 색만 동기화하되 채점 대상은 아니다."""
    from leading_signal import compute_prior_us
    prior = compute_prior_us(market_data)
    dir_map = {"상승": "up", "하락": "dn", "중립": "neutral"}
    return {"dir_cls": dir_map.get(prior["direction"], "neutral")}
