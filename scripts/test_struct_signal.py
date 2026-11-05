# 미국 브리핑 구조 신호 테스트 — 종목 홈과 같은 눈금인지, 값이 없으면 줄이 빠지는지, PC·모바일 자리가 맞는지(2026-11-05)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh  # noqa: E402

A1105 = {"nasdaq_overheat": {"gap_pct": 48.76, "month": "2026-11"},
         "us_index_position": {"asof": "2026-11-04", "items": [
             {"name": "S&P500", "pct": 5.03}, {"name": "나스닥", "pct": 2.59},
             {"name": "다우", "pct": 5.33}, {"name": "반도체", "pct": -5.09}]}}


def _render(ctx, place="main"):
    return gh.make_env().get_template("sections/struct_signal.html").render(ssig_place=place, **ctx)


def test_real_values_match_home_scale():
    s = gh.build_struct_signal(A1105)["struct_sig"]
    n, p = s["nasdaq"], s["index"]
    assert (n["level"], n["x_gap"], n["x_caution"], n["x_warn"], n["w_caution"]) == ("ok", 60.9, 75.0, 87.5, 12.5)
    assert p["asof"] == "11/4(수)" and p["top"] == 10 and p["head"] == "S&P500 +5.03%"
    assert p["rows"][3] == {"name": "반도체", "text": "−5.09%", "up": False, "w": 25.4}


def test_gauge_widens_above_80():
    assert gh.build_struct_signal({"nasdaq_overheat": {"gap_pct": 84.0, "month": "2021-02"}})["struct_sig"]["nasdaq"]["x_gap"] == 93.3


def test_level_badges():
    for gap, level in ((59.9, "ok"), (60.0, "caution"), (70.0, "warn")):
        assert gh.build_struct_signal({"nasdaq_overheat": {"gap_pct": gap}})["struct_sig"]["nasdaq"]["level"] == level


def test_missing_data_drops_row_or_block():
    assert gh.build_struct_signal({}) == {}
    only_nq = gh.build_struct_signal({"nasdaq_overheat": {"gap_pct": 50.0}})
    assert "index" not in only_nq["struct_sig"]
    html = _render(only_nq)
    assert "나스닥 체크" in html and "200일선" not in html
    only_idx = gh.build_struct_signal({"us_index_position": A1105["us_index_position"]})
    assert "나스닥 체크" not in _render(only_idx) and "200일선" in _render(only_idx)
    assert "index" not in gh.build_struct_signal({"nasdaq_overheat": {"gap_pct": 50.0},
                                                  "us_index_position": {"asof": "2026-11-04", "items": [{"name": "S&P500", "pct": None}]}})["struct_sig"]


def test_render_links_and_place_class():
    html = _render(gh.build_struct_signal(A1105), "aside")
    assert "ssig--aside" in html and 'href="/stocks/nasdaq-check/"' in html and "+48.8%" in html and "−5.09%" in html
    assert "11/4(수) 종가" in html and "매일 업데이트" not in html      # 발행 뒤 굳는 페이지라 '매일 업데이트'를 쓰지 않는다


def test_template_places_body_end_and_above_market_panel():
    t = (gh.TEMPLATES_DIR / "briefings" / "us.html").read_text(encoding="utf-8")
    main_at, ad_at = t.index('ssig_place = "main"'), t.index("sections/_ad_multiplex.html")
    aside_at, market_at = t.index('ssig_place = "aside"'), t.index("sections/market_data.html")
    assert t.index("sections/monthly_ma5.html") < main_at < ad_at < aside_at < market_at


def test_css_shows_only_one_copy():
    css = (Path(__file__).resolve().parent.parent / "web" / "assets" / "style.css").read_text(encoding="utf-8")
    assert ".ssig--aside{display:none;}" in css
    assert "@media(max-width:900px){.ssig--main{display:none;}.ssig--aside{display:block;" in css
