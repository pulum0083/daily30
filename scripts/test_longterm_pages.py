# 장기 지표 영구 페이지(S&P 500 200일선)와 주간 장기 리포트 테스트 — 네트워크 없음
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_testkit import gen_patch  # noqa: E402
import longterm_pages as lp  # noqa: E402
import sp500_ma200 as sp  # noqa: E402
import weekly_report as wr  # noqa: E402


# ── S&P 500 200일선 ──

def test_dist_counts_unrounded_values():
    d = sp.dist_of([-0.04, 0.03, 45.0, -25.0, 60.0, -60.0])
    assert d["hot"] == 2 and d["deep"] == 2 and d["near"] == 2 and d["mid"] == 0
    assert sum(c for _, c in d["bins"]) == 6
    assert dict(d["bins"])[-5] == 1 and dict(d["bins"])[0] == 1       # −0.04는 아래 칸, 0.03은 위 칸


def test_upsert_history_overwrites_by_date(tmp_path):
    p = tmp_path / "h.json"
    sp.upsert_history([["2026-01-02", 50.0, 1, 1, 1, 500], ["2026-01-05", 51.0, 1, 1, 1, 500]], p)
    out = sp.upsert_history([["2026-01-05", 52.0, 1, 1, 1, 500], ["2026-01-06", 53.0, 1, 1, 1, 500]], p)
    assert [r[:2] for r in out] == [["2026-01-02", 50.0], ["2026-01-05", 52.0], ["2026-01-06", 53.0]]


def test_history_rows_from_gap_frame():
    idx = pd.to_datetime(["2026-01-02", "2026-01-05"])
    gap = pd.DataFrame([[1.0] * 450 + [-1.0] * 50, [45.0] * 10 + [-30.0] * 490], index=idx)
    rows = sp.history_rows(gap, 0)
    assert rows[0] == ["2026-01-02", 90.0, 1.0, 0, 0, 500]
    assert rows[1][3] == 10 and rows[1][4] == 490


def _sp_hist(n=400, last="2026-11-06"):
    days = pd.bdate_range(end=last, periods=n)
    return [[d.strftime("%Y-%m-%d"), 60.0 + (i % 7), 5.0, 10, 14, 500] for i, d in enumerate(days)]


def _sp_data(asof="2026-11-06"):
    return {"asof": asof, "above": 294, "n": 500,
            "sectors": {"헬스케어": [54, 60], "커뮤니케이션": [5, 22]},
            "dist": sp.dist_of([3.0] * 290 + [-25.0] * 40 + [-3.0] * 166 + [45.0] * 3 + [25.0]),
            "hot": [{"t": "MRNA", "n": "Moderna", "gap": 177.9}], "up": [{"t": "AMD", "n": "AMD", "chg": 11.04}],
            "below": [{"t": "IBM", "n": "IBM", "chg": -0.85}]}


def test_sp500_context_week_ago_and_compare():
    c = lp.sp500_context(_sp_data(), _sp_hist())["spx"]
    assert c["week"]["d"] == "10/30" and c["n"] == 500
    hot = c["cmp"][0]
    assert hot["v"] == "3개" and hot["m"] == "10개" and hot["tag"] == "적은 편"
    assert c["cmp"][1]["tag"] == "많은 편"                          # 20%↓ 40개 > 보통 14개
    assert c["pos0"] == "50.00%" and len(c["bars"]) == 22


def test_sp500_lows_get_notes_from_config(monkeypatch):
    """그래프 저점(연도별 35% 밑) 중 설명이 있는 달만 목록에 오고, 석 달 뒤 비율은 기록에서 잰다(2026-11-23)."""
    h = _sp_hist()
    i = next(k for k, r in enumerate(h) if r[0].startswith("2026-02"))
    h[i][1] = 12.0                                   # 2026-02 저점
    monkeypatch.setattr(lp, "_sp_low_notes", lambda: {"2026-02": {"title": "제목", "text": "본문"}, "2025-12": {"title": "x", "text": "y"}})
    ctx = lp.sp500_context(_sp_data(), h)
    lows = ctx["spx"]["chart"]["lows"]
    assert [l["d"] for l in lows] == [h[i][0]] and lows[0]["pct"] == "12.0" and lows[0]["title"] == "제목"
    assert lows[0]["after"] == f"{h[i + 63][1]:.1f}"


def test_sp500_low_notes_file_months_are_marked_lows():
    """설정 파일의 달이 실제 기록에서 그래프에 찍히는 저점과 같아야 한다 — 어긋나면 설명이 조용히 빠진다."""
    import json
    rows = json.loads((lp.ROOT if hasattr(lp, "ROOT") else lp.SP_LOWS_PATH.parents[2]).joinpath("data", "sp500_breadth_history.json").read_text())["rows"]
    lows = {min((r for r in rows if r[0][:4] == y), key=lambda r: r[1])[0][:7]
            for y in {r[0][:4] for r in rows}}
    lows = {m for m in lows if min(r[1] for r in rows if r[0][:7] == m) < lp.LOW_MARK}
    assert set(lp._sp_low_notes()) <= lows


def test_sp500_context_needs_same_day_row():
    assert lp.sp500_context(_sp_data("2026-11-09"), _sp_hist()) == {}


# ── 주간 장기 리포트 ──

def test_week_of_and_series():
    assert wr.week_of(date(2026, 11, 7)) == date(2026, 11, 6)       # 토요일 → 어제
    assert wr.week_of(date(2026, 11, 6)) == date(2026, 10, 30)      # 금요일 당일엔 주가 안 끝났다
    rows = [("2026-10-30", 100.0), ("2026-11-02", 101.0), ("2026-11-06", 99.0), ("2026-11-09", 98.0)]
    assert wr.series_for_week(rows, "2026-11-02", "2026-11-06") == [["2026-10-30", 100.0], ["2026-11-02", 101.0], ["2026-11-06", 99.0]]
    assert wr.ma200_gap([("d%03d" % i, 100.0) for i in range(199)], "d999") is None


def _wk(ma=None):
    s = lambda vals: [["2026-10-30", 100.0]] + [[f"2026-11-0{i + 2}", v] for i, v in enumerate(vals) if v is not None]
    return {"monday": "2026-11-02", "end": "2026-11-06", "prev_end": "2026-10-30",
            "idx": {"KS": [["2026-10-30", 5730.74], ["2026-11-02", 5859.08], ["2026-11-03", 5648.79],
                           ["2026-11-05", 5383.8], ["2026-11-06", 5059.69]],             # 11/4 휴장
                    "^GSPC": s([99, 100, None, 98, 97])},
            "nq": {"now": {"gap": 48.9, "month": "2026-11", "high": 26048.8, "level": "ok"},
                   "prev": {"gap": 59.9, "month": "2026-10", "high": 27722.8, "level": "ok"}},
            "spx": {"now": ["2026-11-06", 58.8], "prev": ["2026-10-30", 61.6], "median_all": 66.3, "from_label": "2020년 8월",
                    "sectors": [["헬스케어", 90.0], ["커뮤니케이션", 22.7]]},
            "ma200": ma if ma is not None else {"S&P500": [0.71, 3.7], "나스닥": [-2.07, 1.52], "다우": [1.2, 2.3], "반도체": [-13.3, -0.86]},
            "ma5": {"kr": {"items": [{"name": "삼성화재", "streak": 6}], "dropped": []}}, "sectors_week": []}


def test_weekly_headline_uses_first_crossing_event():
    w = lp.weekly_context(_wk())["wk"]
    assert w["head"] == "코스피 한 주 −11.7%, 나스닥은 200일선 아래로"
    assert "나스닥이 200일선 아래로 내려왔어요" in w["sub"] and "반도체 지수는 200일선보다 13.3% 아래예요" in w["sub"]
    assert w["tag"] == "11월 첫째 주 · 11/2(월) ~ 11/6(금)"
    k = w["ks"]                                                         # 코스피는 큰 계단(거래한 날만 칸)
    assert [c["dow"] for c in k["cols"]] == ["월", "화", "목", "금"] and k["cols"][2]["lab"] == "−4.69%"   # 목요일 등락은 화요일 종가 대비
    assert k["head_day"] == "금요일" and k["head_pt"] == "−324p" and k["n"] == 6
    assert [r["name"] for r in w["rows"]] == ["S&P 500"]                # 미국 지수만 요일 계단(A안)
    assert "헬스케어는 90%, 커뮤니케이션은 23%만 선 위예요" in w["cards"][1]["txt"]
    assert [c["name"].split(" · ")[0] for c in w["cards"]] == ["나스닥 체크", "S&P 500"]   # 코스피 체크는 2026-11-15 제거
    assert w["sub"].startswith("코스피는 5,731에서 5,060으로 내려왔어요.")


def test_weekly_headline_without_event():
    w = lp.weekly_context(_wk({"S&P500": [1.0, 2.0]}))["wk"]
    assert w["head"] == "코스피 한 주 −11.7%" and "미국에선" not in w["sub"]


def test_ma5_lists_from_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(wr, "BRIEFINGS", tmp_path)
    def put(d, items, hidden):
        p = tmp_path / d / "kospi"
        p.mkdir(parents=True)
        (p / "analysis_snapshot.json").write_text(json.dumps({"monthly_ma5": {"items": items, "repeat_hidden": hidden}}))
    put("2026-11-02", [{"name": "A", "streak": 6}, {"name": "B", "streak": 3}], [])
    put("2026-11-03", [], ["A", "B"])
    put("2026-11-04", [], ["A"])
    out = wr.ma5_lists("kospi", "monthly_ma5", "2026-11-02", "2026-11-06", lambda d: date(2026, 11, 3))
    assert out["items"] == [{"name": "A", "streak": 6}]
    assert out["dropped"] == [{"name": "B", "when": "2026-11-03"}]


# ── 렌더 ──

def test_templates_render(tmp_path):
    import generate_html as gh
    env = gh.make_env()
    base = {"css_path": "/a.css", "js_path": "/a.js", "canonical_url": "https://x/", "seo_jsonld": []}
    html = env.get_template("pages/sp500_200.html").render(**lp.sp500_context(_sp_data(), _sp_hist()), **base)
    assert "빠진 종목은 없고" not in html and "빠진 종목은 계산에 들어 있지 않고" in html
    assert html.index("🔥 과열") < html.index("200일선 위로") < html.index("200일선 아래로") and "None" not in html
    html = env.get_template("pages/weekly_report.html").render(**lp.weekly_context(_wk()), **base)
    assert "휴장" in html and "코스피 한 주 −11.7%" in html and "None" not in html
    assert html.index("st-plot") < html.index("미국 지수")             # 코스피 큰 계단이 먼저, 미국 지수가 아래


def test_pages_are_in_publish_gate_and_sitemap():
    from verify_publish_gate import expected_pages
    urls = {u for _, u in expected_pages()}
    assert "https://doubleshot.space/stocks/sp500-200/" in urls
    assert not any("kospi-check" in u for u in urls)                     # 2026-11-15 제거
    sm = (Path(__file__).resolve().parents[1] / "web" / "sitemap.xml").read_text(encoding="utf-8")
    assert "/stocks/sp500-200/" in sm and "/weekly/" in sm and "kospi-check" not in sm


def test_write_sp500_page_also_writes_home_file(tmp_path, monkeypatch):
    import generate_html as gh
    (tmp_path / "data").mkdir()
    (tmp_path / "web" / "data").mkdir(parents=True)
    d = dict(_sp_data(), date="2026-11-09")
    (tmp_path / "data" / "sp500_ma200.json").write_text(json.dumps(d), encoding="utf-8")
    (tmp_path / "data" / "sp500_breadth_history.json").write_text(json.dumps({"rows": _sp_hist()}), encoding="utf-8")
    gen_patch(monkeypatch, "DATA_DIR", tmp_path / "data")
    gen_patch(monkeypatch, "WEB_DIR", tmp_path / "web")
    assert gh.write_sp500_page("2026-11-09")
    home = json.loads((tmp_path / "web" / "data" / "sp500-home.json").read_text(encoding="utf-8"))
    assert home["asof"] == "2026-11-06" and home["hot"] == 3 and home["deep"] == 40 and len(home["spark"]) == 120
    assert (tmp_path / "web" / "stocks" / "sp500-200" / "index.html").exists()


def test_recent_weekly_line(tmp_path, monkeypatch):
    import generate_html as gh
    gen_patch(monkeypatch, "WEB_DIR", tmp_path)
    assert gh.build_recent_weekly("2026-11-09") == {}                     # 리포트가 없으면 줄이 없다
    d = tmp_path / "weekly" / "2026-11-06"
    d.mkdir(parents=True)
    (d / "data.json").write_text(json.dumps(_wk()), encoding="utf-8")
    (d / "index.html").write_text("<html></html>", encoding="utf-8")
    it = gh.build_recent_weekly("2026-11-09")
    assert it == {"url": "/weekly/2026-11-06/", "label": "주간 장기 리포트", "end": "2026-11-06", "date": "11/2~11/6",
                  "headline": "코스피 한 주 −11.7%, 나스닥은 200일선 아래로"}
    assert gh.build_recent_weekly("2026-11-25") == {}                     # 14일 넘게 새 리포트가 없으면 싣지 않는다
    html = gh.render_recent_briefings([{"url": "/b/", "label": "미국 시장", "iso": "2026-11-06", "date": "11/6(금)", "headline": "h", "dek": ""}], it)
    assert html.index('rb-item feat wk') < html.index('href="/b/"') and "📅 11/2~11/6 · 주간 장기 리포트" in html   # 토요일 발행이라 금요일보다 위


def test_recent_weekly_sits_between_monday_and_friday():
    """주간 리포트는 발행 순서대로 — 월요일 브리핑 아래, 금요일 브리핑 위. 파란 바(feat)는 가장 최근 1편(2026-11-09)."""
    import generate_html as gh
    items = [{"url": f"/b{k}/", "label": "x", "iso": d, "date": d, "headline": f"h{k}", "dek": "요약" if k == 0 else ""}
             for k, d in enumerate(["2026-11-09", "2026-11-09", "2026-11-06", "2026-11-06"])]
    wk = {"url": "/weekly/2026-11-06/", "label": "주간 장기 리포트", "end": "2026-11-06", "date": "11/2~11/6", "headline": "w"}
    html = gh.render_recent_briefings(items, wk)
    order = [html.index(u) for u in ('href="/b0/"', 'href="/b1/"', 'href="/weekly/', 'href="/b2/"', 'href="/b3/"')]
    assert order == sorted(order)
    assert html.count(" feat") == 1 and 'class="rb-item feat"><a href="/b0/"' in html and "요약" in html
    assert 'class="rb-item wk"' in html


def test_weekly_telegram_text():
    d = _wk()
    t = wr.telegram_text(d, lp.weekly_context(d), date(2026, 11, 7), "https://doubleshot.space")
    lines = t.splitlines()
    assert lines[0] == "📅 주간 장기 리포트 | 2026.11.07"                   # 보내는 날 — send_telegram 날짜 검사를 통과한다
    assert "🎯 <b>코스피 한 주 −11.7%" in t
    assert "코스피 5,731 → 5,060 (−11.71%)" in t
    assert "S&P 500 −3.00%" in t                                             # 99 → 97
    assert "나스닥 체크 59.9% → 48.9%" in t and "코스피 체크" not in t
    assert "S&P 500 200일선 위 61.6% → 58.8%" in t
    i = lines.index("📐 장기 지표 (지난주 → 이번 주)")                       # 나스닥 → S&P 500(홈과 같은 순서)
    assert [l.split(" ")[0] for l in lines[i + 1:i + 3]] == ["나스닥", "S&P"]
    assert lines[-1] == "🔗 주간 장기 리포트 → https://doubleshot.space/weekly/2026-11-06/"


def test_weekly_telegram_needs_published_page(tmp_path, monkeypatch):
    monkeypatch.setattr(wr, "WEEKLY", tmp_path)
    monkeypatch.setattr(wr, "TELEGRAM_PATH", tmp_path / "msg.txt")
    (tmp_path / "2026-11-06").mkdir()
    (tmp_path / "2026-11-06" / "data.json").write_text(json.dumps(_wk()), encoding="utf-8")
    assert wr.write_telegram("2026-11-06", date(2026, 11, 7)) is False       # 페이지가 없으면 보내지 않는다
    (tmp_path / "2026-11-06" / "index.html").write_text("x", encoding="utf-8")
    assert wr.write_telegram("2026-11-06", date(2026, 11, 7)) is True
    assert (tmp_path / "msg.txt").read_text(encoding="utf-8").startswith("📅 주간 장기 리포트 | 2026.11.07")


def test_weekly_refreshes_live_pages_only_for_this_week(tmp_path, monkeypatch):
    """지난 주를 채울 때(--week-end) 옛 종가로 상세 페이지를 덮지 않는다."""
    calls = []
    monkeypatch.setattr(wr, "WEEKLY", tmp_path)
    monkeypatch.setattr(wr, "collect", lambda end: _wk())
    monkeypatch.setattr(wr, "render", lambda end: True)
    monkeypatch.setattr(wr, "refresh_live_pages", lambda end: calls.append(end))
    monkeypatch.setattr(sys, "argv", ["weekly_report.py", "--week-end", "2026-10-30"])
    assert wr.main() == 0 and calls == []
    monkeypatch.setattr(wr, "week_of", lambda today: date(2026, 11, 6))
    monkeypatch.setattr(sys, "argv", ["weekly_report.py"])
    assert wr.main() == 0 and calls == [date(2026, 11, 6)]


def test_market_events_only_inside_chart_range():
    # 장기 지표 그래프의 큰 사건(2026-11-12) — 그래프 기간 안의 달만, 가로 위치와 함께. 번호는 남은 것끼리 1부터
    import longterm_pages as lp
    months = [f"{y}-{m:02d}" for y in range(2000, 2021) for m in range(1, 13)]
    ev = lp.market_events("nasdaq", months)
    assert [e["when"] for e in ev] == ["2000.3", "2008.9", "2020.3"]   # 2022.3은 기간 밖이라 빠진다
    assert [e["n"] for e in ev] == [1, 2, 3]
    assert ev[0]["left"] == f"{2 / (len(months) - 1) * 100:.2f}%"
    assert all(e["pos"] in ("top", "bottom") for e in ev)
    assert lp.market_events("nope", months) == []
