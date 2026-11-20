# 중간선거 해 비교(2018 vs 2026) 수집·화면 테스트 — 네트워크 없음
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_testkit import gen_patch  # noqa: E402
import longterm_pages as lp  # noqa: E402
import midterm_compare as mc  # noqa: E402


def _days(start, n, f):
    """주말을 뺀 날짜 n개 [(날짜, 고, 저, 종)] — 종가는 f(i)."""
    out, d, i = [], date.fromisoformat(start), 0
    while len(out) < n:
        if d.weekday() < 5:
            c = f(i)
            out.append((d.isoformat(), c, c, c))
            i += 1
        d += timedelta(days=1)
    return out


def _spx():
    """2017-12 ~ 2019-12 와 2025-12 ~ 2026-11-13 — 단순 증가 곡선."""
    a = _days("2017-12-01", 540, lambda i: 100 + i * 0.05)
    b = _days("2025-12-01", 250, lambda i: 200 + i * 0.1)
    return [r for r in a if r[0] <= "2019-12-31"] + [r for r in b if r[0] <= "2026-11-13"]


def test_ytd_path_and_same_date():
    d = mc.build(_spx(), _spx(), [("2018-11-13", 0, 0, 3.14), ("2026-11-13", 0, 0, 5.15)], [], "2026-11-13")
    assert d["asof"] == "2026-11-13" and d["a"][0][2][:4] == "2018" and d["a"][-1][2] <= "2019-12-31"
    assert d["b"][-1][2] == "2026-11-13" and d["same"]["date"] == "2018-11-13"
    assert d["tnx"] == {"a": 3.14, "b": 5.15} and d["fed"] == {}          # FRED가 비면 기준금리 칸은 빠진다


def test_build_refuses_missing_session_bar():
    assert mc.build(_spx(), _spx(), [], [], "2026-11-16") is None      # 그 날짜 S&P 500 봉이 없으면 쓰지 않는다(§45)


def test_rate_changes_use_decision_day():
    """FRED는 결정 다음 날 바뀐다 — 하루 빼 결정일로(2019-08-01 → 7/31)."""
    fed = [("2019-07-31", 2.5), ("2019-08-01", 2.25), ("2019-09-19", 2.0)]
    assert mc.rate_changes(fed, "2019-01-01", "2019-12-31") == [["2019-07-31", 2.25, -1], ["2019-09-18", 2.0, -1]]
    fed = [("2026-09-16", 3.75), ("2026-09-17", 4.0)]
    assert mc.rate_changes(fed, "2026-01-01", "2026-09-16") == [["2026-09-16", 4.0, 1]]
    assert mc.rate_changes(fed, "2026-01-01", "2026-09-15") == []         # 결정일 전엔 아직 바뀌지 않았다
    assert lp._moves_short([["2018-03-21", 1.75, 1], ["2018-06-13", 2.0, 1], ["2018-09-26", 2.25, 1]]) == "3번 인상(3·6·9월)"
    assert lp._moves_short([]) == "동결" and lp._moves_text([["2026-09-16", 4.0, 1]]) == "9월에 올렸어요"


def test_midterm_stats_uses_finished_elections_only():
    daily = [(d, c) for d, _h, _l, c in _days("1949-12-01", 20000, lambda i: 10 + i * 0.01)]
    rows, base = mc.midterm_stats(daily, "2026-11-13")
    assert rows[0][0] == 1950 and rows[-1][0] == 2022 and len(rows) == 19   # 2026은 아직 12개월이 안 됐다
    assert all(v > 0 for _, v in rows) and base["up"] == 100.0
    assert mc.midterm_day(2026) == date(2026, 11, 3) and mc.midterm_day(2018) == date(2018, 11, 6)


def _data():
    d = mc.build(_spx(), _spx(), [("2018-11-13", 0, 0, 3.14), ("2026-11-13", 0, 0, 5.15)],
                 [("2018-01-01", 1.5), ("2018-03-22", 1.75), ("2018-12-20", 2.5), ("2019-08-01", 2.25),
                  ("2026-01-01", 3.75), ("2026-09-17", 4.0)], "2026-11-13")
    d["midterms"], d["base"] = [[2014, 4.5], [2018, 11.7], [2022, 14.5]], {"up": 74.7, "avg": 9.4}
    return d


def test_context_sentences_events_and_ranges():
    c = lp.midterm_context(_data())["mt"]
    assert [r["key"] for r in c["ranges"]] == ["2y", "y1", "mid"]
    assert c["ranges"][2]["months"][0]["label"] == "9월"                        # 선거 전후는 9월부터
    evs = {e["label"]: e for e in c["events"]}
    assert evs["FOMC (예정)"]["v_s"] == "아직"                                  # 12/9는 아직 오지 않았다
    assert "연중 고점" in [e["label"] for e in c["events"] if e["g"] == 26]       # 데이터에서 계산
    assert [e["n"] for e in c["events"]] == list(range(1, len(c["events"]) + 1))
    assert c["rows"][-1]["b"].startswith("4.00% · 9월 인상")
    t = " ".join(c["concl"])
    assert "2019년엔" in t and "12월에 한 번 더 올린 뒤" in t and "7월에 내렸어요" in t and "올랐어요." in t
    assert c["ups"] == 3 and c["n_mid"] == 3 and "None" not in json.dumps(c["concl"], ensure_ascii=False)


def test_template_renders(tmp_path):
    import generate_html as gh
    html = gh.make_env().get_template("pages/midterm_2018.html").render(
        **lp.midterm_context(_data()), css_path="/a.css", js_path="/a.js", canonical_url="https://x/", seo_jsonld=[])
    assert "트럼프 1기 중간선거 뒤와 닮았을까?" in html and html.count('class="mtp-r"') == 3
    assert "None" not in html and "예측하는 선이 아니에요" in html


def test_write_page_refuses_other_session(tmp_path, monkeypatch):
    import generate_html as gh
    (tmp_path / "midterm_2018.json").write_text(json.dumps(_data()), encoding="utf-8")
    gen_patch(monkeypatch, "DATA_DIR", tmp_path)
    assert gh.write_midterm_page("2026-11-20") is False                     # 직전 미국장(11/19) ≠ 11/13


def test_page_in_publish_gate_and_sitemap():
    from verify_publish_gate import expected_pages
    assert "https://doubleshot.space/stocks/midterm-2018/" in {u for _, u in expected_pages()}
    sm = (Path(__file__).resolve().parents[1] / "web" / "sitemap.xml").read_text(encoding="utf-8")
    assert "/stocks/midterm-2018/" in sm


def test_live_midterm_column_is_separate_from_stats():
    """2026 칸 — 선거일(11/3) 종가 → 지금. 진행 중이라 평균·오른 횟수에 넣지 않는다(2026-11-15)."""
    d = _data()
    assert d["midterm_live"]["y"] == 2026 and d["midterm_live"]["from"] == "2026-11-03" and d["midterm_live"]["days"] == 8
    c = lp.midterm_context(d)["mt"]
    assert c["bars"][-1]["live"] and c["bars"][-1]["y"] == 2026 and c["live"]["from_s"] == "11/3"
    assert c["n_mid"] == 3 and c["ups"] == 3                                 # 확정 3번만 센다
    import generate_html as gh
    html = gh.make_env().get_template("pages/midterm_2018.html").render(
        **lp.midterm_context(d), css_path="/a.css", js_path="/a.js", canonical_url="https://x/", seo_jsonld=[])
    assert 'class="mtb live"' in html and "진행 중" in html and "평균에 넣지 않았고" in html


def test_no_live_column_before_election_day():
    d = mc.build(_spx(), _spx(), [], [], "2026-11-02")
    assert "midterm_live" not in d


# ── 트럼프 1기 vs 2기 — 취임 뒤 날수를 맞춰 겹친다(2026-11-19) ──────────────────────────────

def _spx_terms():
    from datetime import date, timedelta
    out, d, v = [], date(2016, 12, 1), 100.0
    while d <= date(2026, 11, 18):
        if d.weekday() < 5 and d.isoformat() != "2025-01-20":       # 2025-01-20 휴장(MLK)
            v *= 1.0003
            out.append((d.isoformat(), round(v, 4)))
        d += timedelta(days=1)
    return out


def test_term_path_base_is_close_before_inauguration():
    spx = [("2025-01-16", 99.0), ("2025-01-17", 100.0), ("2025-01-21", 101.0), ("2025-01-22", 102.0)]
    p = mc.term_path(spx, "2025-01-20", "2025-12-31")
    assert p[0] == [1, 1.0, "2025-01-21"] and p[1] == [2, 2.0, "2025-01-22"]


def test_build_terms_same_day_and_context():
    t = mc.build_terms(_spx_terms(), "2026-11-18")
    assert t["t1"][-1][2] == "2021-01-19" and t["t2"][-1][2] == "2026-11-18"
    assert t["same"]["day"] <= t["t2"][-1][0] and t["same"]["date"][:4] == "2018"
    c = lp.terms_context(t, "2026-11-18")["tt"]
    assert "취임 뒤 667일" in c["say"] and [r["key"] for r in c["ranges"]] == ["same", "y1", "y2", "all"]
    g18 = [e for e in c["events"] if e["g"] == 18]
    g26 = [e for e in c["events"] if e["g"] == 26]
    assert g18[0]["n"] == 1 and g26[0]["n"] == len(g18) + 1                 # 1기 먼저 번호
    assert all(e["d"] >= "2025-01-20" for e in g26) and all(e["d"] < "2021-01-20" for e in g18)
    y1 = next(r for r in c["ranges"] if r["key"] == "y1")
    assert [m["label"] for m in y1["months"]] == ["취임", "2개월", "4개월", "6개월", "8개월", "10개월", "1년"]
    y2 = next(r for r in c["ranges"] if r["key"] == "y2")
    assert y2["s"] == 365 and y2["now"] and y2["months"][0]["label"] == "1년"
    assert lp.terms_context(None, "2026-11-18") == {}


def test_zoomed_tabs_show_more_events_and_2y_keeps_base():
    """2년 탭은 tabs 없는 기본 사건만, 선거 해·선거 전후는 그 창의 사건을 더 자세히(2026-11-20 사용자 요청)."""
    c = lp.midterm_context(_data())["mt"]
    r = {x["key"]: x for x in c["ranges"]}
    base = [e["label"] for e in c["events"]]
    assert [e["label"] for e in r["2y"]["events"]] == base
    assert "연중 저점" not in [e["label"] for e in r["2y"]["events"] if e["g"] == 26]
    assert "1월 고점 · 조정 직전" in [e["label"] for e in r["y1"]["events"]]
    assert "하루 +5.0% 반등" in [e["label"] for e in r["mid"]["events"]]
    assert "하루 +5.0% 반등" not in [e["label"] for e in r["y1"]["events"]]
    for k in ("y1", "mid"):
        evs = r[k]["events"]
        assert all(r[k]["s"] <= e["day"] <= r[k]["e"] for e in evs)             # 창 밖 사건은 목록에도 없다
        assert [e["n"] for e in evs] == list(range(1, len(evs) + 1))
        assert [m["n"] for m in r[k]["marks"]] == [e["n"] for e in evs]          # 그래프 번호 = 목록 번호
    assert all("%" not in x["now"]["s"] for x in c["ranges"] if x["now"])       # '지금 +4.8%%' 방지


def test_zoom_events_config_dates_are_real_days():
    cfg = json.loads(lp.MIDTERM_EVENTS_PATH.read_text(encoding="utf-8"))["events"]
    for e in cfg:
        date.fromisoformat(e["d"])
        assert set(e.get("tabs") or []) <= {"y1", "mid"}
