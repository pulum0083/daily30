# 브리핑 밖 영구 페이지 작성기 — 나스닥 체크·S&P 500 200일선·중간선거 비교·예측 성적표·방법론

import json
from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nasdaq_charts import _nqp_ranges
try:
    from scripts.verify_publish_gate import gate_write
except ImportError:
    from verify_publish_gate import gate_write
from html_common import BRIEFINGS_DIR, CSS_PATH, DATA_DIR, GATE_BLOCKED, JS_PATH, SITE_BASE, WEB_DIR, _breadcrumb, _jsonld, load_json, make_env
from sections_us import NASDAQ_BACKTEST_PATH, _NQ_BADGE, _read_nasdaq_overheat, read_sp500_ma200


NASDAQ_PAGE_URL = f"{SITE_BASE}/stocks/nasdaq-check/"


def build_nasdaq_page(data: dict, bt: dict, target_date: str) -> dict:
    """/stocks/nasdaq-check/ 상세 페이지 컨텍스트. 숫자는 전부 수집 파일·백테스트 파일 그대로다(§0)."""
    import nasdaq_overheat as nq
    import longterm_pages as lp
    hist = [h for h in (data.get("history") or [])
            if isinstance(h, dict) and all(isinstance(h.get(k), (int, float)) for k in ("g", "h", "c", "ma"))]
    if len(hist) < 24 or not isinstance(data.get("gap_pct"), (int, float)):
        return {}
    gap = float(data["gap_pct"])
    level = nq.level_of(gap)
    month = str(data.get("month") or "")
    month_label = f"{int(month[:4])}년 {int(month[5:7])}월" if len(month) == 7 else "이번 달"
    last = str(data.get("last_date") or "")
    asof = f"{int(last[5:7])}월 {int(last[8:10])}일" if len(last) == 10 else ""
    brief = BRIEFINGS_DIR / target_date / "us" / "index.html"
    return {
        "nq": {
            "gap": gap, "level": level, "badge": _NQ_BADGE[level],
            "high": data.get("high"), "ma60": data.get("ma60"),
            "streak": int(data.get("streak") or 0), "pin": max(0.0, min(gap, 100.0)),
            "month_label": month_label, "asof": asof, "date": target_date,
            "caution": nq.CAUTION, "warn": nq.WARN, "bt": bt,
            "from_year": hist[0]["m"][:4],
            "ranges": _nqp_ranges(hist, nq.CAUTION, nq.WARN, lp),
            # 짚었을 때 띄울 월별 값 — [월, 이격률, 고점, 종가, 60개월선]
            "points": [[h["m"], h["g"], h["h"], h["c"], h["ma"]] for h in hist],
            "brief_url": f"/briefings/{target_date}/us/" if brief.exists() else "",
        },
        "canonical_url": NASDAQ_PAGE_URL,
        "seo_jsonld": [_jsonld(_breadcrumb([("홈", "/stocks/"), ("종목", "/stocks/"),
                                            ("나스닥 체크", "/stocks/nasdaq-check/")]))],
        "css_path": CSS_PATH, "js_path": JS_PATH,
    }


def write_nasdaq_page(target_date: str) -> bool:
    """그날 수집한 data/nasdaq_overheat.json으로 상세 페이지를 쓴다. 날짜가 다르거나 데이터·백테스트가
    없으면 쓰지 않는다 — 직전 페이지가 그대로 남는다(§14·§20)."""
    data = _read_nasdaq_overheat(target_date)
    if not data:
        return False
    try:
        bt = json.loads(NASDAQ_BACKTEST_PATH.read_text(encoding="utf-8"))
        bt["caution_band"]["fwd12_avg_pct"], bt["warn"]["dd20_pct"]
    except Exception as e:
        print(f"[generate_html] 나스닥 체크 상세 페이지 생략 — 백테스트 수치 없음({e})")
        return False
    ctx = build_nasdaq_page(data, bt, target_date)
    if not ctx:
        print("[generate_html] 나스닥 체크 상세 페이지 생략 — 1990년부터의 시계열(history)이 없음")
        return False
    html_out = make_env().get_template("pages/nasdaq_check.html").render(**ctx)
    out = WEB_DIR / "stocks" / "nasdaq-check" / "index.html"
    if gate_write(out, html_out, NASDAQ_PAGE_URL):
        GATE_BLOCKED.append(NASDAQ_PAGE_URL)
        return False
    write_nasdaq_home(data)
    print(f"[generate_html] 나스닥 체크 상세 페이지 → {out}")
    return True


def write_nasdaq_home(data: dict) -> None:
    """종목 홈 '장기 신호' 나스닥 줄용 작은 파일(2026-11-09) — 상세 페이지와 같은 값·같은 기준일.
    홈은 이 파일과 최근 미국 브리핑 스냅샷 중 기준일이 더 최근인 것을 쓴다. 주인은 미국 잡과 주간 리포트 작업이다."""
    if not isinstance(data.get("gap_pct"), (int, float)) or not data.get("last_date"):
        return
    home = {"asof": data["last_date"], "gap_pct": data["gap_pct"], "level": data.get("level"),
            "month": data.get("month"), "high": data.get("high")}
    (WEB_DIR / "data").mkdir(parents=True, exist_ok=True)
    (WEB_DIR / "data" / "nasdaq-home.json").write_text(json.dumps(home, ensure_ascii=False) + "\n", encoding="utf-8")


SP500_PAGE_URL = f"{SITE_BASE}/stocks/sp500-200/"
MIDTERM_PAGE_URL = f"{SITE_BASE}/stocks/midterm-2018/"
TRUMP_PAGE_URL = f"{SITE_BASE}/stocks/trump-terms/"


def _write_lt_page(tpl: str, ctx: dict, rel: str, url: str, name: str) -> bool:
    ctx.update({"canonical_url": url, "css_path": CSS_PATH, "js_path": JS_PATH,
                "seo_jsonld": [_jsonld(_breadcrumb([("홈", "/stocks/"), ("종목", "/stocks/"), (name, rel)]))]})
    out = WEB_DIR / rel.strip("/") / "index.html"
    if gate_write(out, make_env().get_template(tpl).render(**ctx), url):
        GATE_BLOCKED.append(url)
        return False
    print(f"[generate_html] {name} 상세 페이지 → {out}")
    return True


def write_sp500_page(target_date: str) -> bool:
    """미국 잡이 쓴 data/sp500_ma200.json(그날)·data/sp500_breadth_history.json으로 /stocks/sp500-200/을 쓴다(2026-11-09)."""
    import longterm_pages as lp
    data = read_sp500_ma200({}, target_date)
    if not data:
        return False
    try:
        rows = json.loads((DATA_DIR / "sp500_breadth_history.json").read_text(encoding="utf-8"))["rows"]
    except Exception as e:
        print(f"[generate_html] S&P 500 200일선 상세 페이지 생략 — 누적 기록 없음({e})")
        return False
    ctx = lp.sp500_context(data, rows)
    if not ctx:
        print("[generate_html] S&P 500 200일선 상세 페이지 생략 — 누적 기록이 1년치 미만이거나 그날 값이 없음")
        return False
    # 종목 홈 '장기 신호' 줄용 작은 파일(2026-11-09) — 페이지와 같은 값. 이 파일의 주인은 미국 잡이다(§18).
    s = ctx["spx"]
    home = {"asof": s["asof"], "pct": s["pct"], "week": s["week"], "median_all": s["median_all"],
            "hot": data["dist"]["hot"], "deep": data["dist"]["deep"],
            "spark": [p[1] for p in s["points"][-120:]]}
    (WEB_DIR / "data" / "sp500-home.json").write_text(json.dumps(home, ensure_ascii=False) + "\n", encoding="utf-8")
    return _write_lt_page("pages/sp500_200.html", ctx, "/stocks/sp500-200/", SP500_PAGE_URL, "S&P 500 200일선")


def write_midterm_page(target_date: str) -> bool:
    """data/midterm_2018.json(midterm_compare.py)으로 /stocks/midterm-2018/과 홈 줄 파일을 쓴다(2026-11-15).
    기준일이 target_date(KST)의 직전 미국장이 아니면 쓰지 않는다 — 직전 페이지가 남는다(§14·§20)."""
    import longterm_pages as lp
    from session_label import prev_us_session
    try:
        data = json.loads((DATA_DIR / "midterm_2018.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[generate_html] 중간선거 비교 페이지 생략 — 데이터 없음({e})")
        return False
    want = prev_us_session(date.fromisoformat(target_date))
    if not want or data.get("asof") != want.isoformat():
        print(f"[generate_html] 중간선거 비교 페이지 생략 — 기준일 불일치({data.get('asof')} ≠ {want})")
        return False
    ctx = lp.midterm_context(data)
    if not ctx:
        print("[generate_html] 중간선거 비교 페이지 생략 — 비교할 기록이 없음")
        return False
    # 종목 홈 '장기 신호' 줄용 작은 파일 — 페이지와 같은 값. 작은 그래프는 사흘마다 한 점(2년치 두 선).
    mt = ctx["mt"]
    home = {"asof": data["asof"], "years": data["years"], "now": data["b"][-1][1], "same": data["same"],
            "ups": mt["ups"], "n_mid": mt["n_mid"],
            "a": [p[:2] for p in data["a"][::3]] + [data["a"][-1][:2]], "b": [p[:2] for p in data["b"][::3]] + [data["b"][-1][:2]]}
    (WEB_DIR / "data").mkdir(parents=True, exist_ok=True)
    (WEB_DIR / "data" / "midterm-home.json").write_text(json.dumps(home, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return _write_lt_page("pages/midterm_2018.html", ctx, "/stocks/midterm-2018/", MIDTERM_PAGE_URL, "중간선거 해 비교")


def write_trump_page(target_date: str) -> bool:
    """data/trump_terms.json(trump_terms.py)으로 /stocks/trump-terms/와 홈 줄 파일을 쓴다(2026-11-21).
    기준일이 target_date(KST)의 직전 미국장이 아니면 쓰지 않는다 — 직전 페이지가 남는다(§14·§20)."""
    import longterm_pages as lp
    from session_label import prev_us_session
    try:
        data = json.loads((DATA_DIR / "trump_terms.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[generate_html] 트럼프 1기 vs 2기 페이지 생략 — 데이터 없음({e})")
        return False
    want = prev_us_session(date.fromisoformat(target_date))
    if not want or data.get("asof") != want.isoformat():
        print(f"[generate_html] 트럼프 1기 vs 2기 페이지 생략 — 기준일 불일치({data.get('asof')} ≠ {want})")
        return False
    ctx = lp.trump_context(data)
    if not ctx:
        print("[generate_html] 트럼프 1기 vs 2기 페이지 생략 — 비교할 기록이 없음")
        return False
    # 종목 홈 '장기 신호' 넷째 줄용 작은 파일 — 페이지와 같은 값. 막대는 1기·2기의 해마다 끝 값과 2기 지금(C3안).
    tr = ctx["tr"]
    home = {"asof": data["asof"], "days": tr["days"], "now": data["t2"][-1][1], "same": data["same"],
            "end1": data["t1"][-1][1], "y1": tr["y1"], "y2": tr["y2"]}
    (WEB_DIR / "data").mkdir(parents=True, exist_ok=True)
    (WEB_DIR / "data" / "trump-home.json").write_text(json.dumps(home, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return _write_lt_page("pages/trump_terms.html", ctx, "/stocks/trump-terms/", TRUMP_PAGE_URL, "트럼프 1기 vs 2기")


RECORD_PAGES = (("accuracy", "pages/accuracy.html", "예측 성적표"),
                ("methodology", "pages/methodology.html", "어떻게 예측하나요"))


def write_record_pages() -> list:
    """예측 성적표(/accuracy/)·방법론(/methodology/)을 쓴다(2026-11-05, §80). 쓴 파일의 web/ 기준 경로 목록을 돌려준다.
    성적표는 채점 기록이 없으면 쓰지 않는다 — 직전 페이지가 남는다."""
    try:
        import scripts.record_pages as rp
    except ImportError:
        import record_pages as rp
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []
    ctxs = {"accuracy": rp.build_accuracy(briefings), "methodology": rp.build_methodology()}
    env, written = make_env(), []
    for slug, tpl, name in RECORD_PAGES:
        ctx = ctxs[slug]
        if not ctx:
            print(f"[generate_html] /{slug}/ 생략 — 데이터 없음")
            continue
        url = f"{SITE_BASE}/{slug}/"
        ctx.update({"canonical_url": url, "css_path": CSS_PATH, "js_path": JS_PATH,
                    "seo_jsonld": [_jsonld(_breadcrumb([("홈", "/stocks/"), (name, f"/{slug}/")]))]})
        out = WEB_DIR / slug / "index.html"
        if gate_write(out, env.get_template(tpl).render(**ctx), url):
            GATE_BLOCKED.append(url)
            continue
        written.append(f"{slug}/index.html")
        print(f"[generate_html] {name} → {out}")
    return written
