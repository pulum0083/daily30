# 미국 브리핑 구조 신호(나스닥 체크) 테스트 — 종목 홈과 같은 눈금인지, 값이 없으면 빠지는지, PC·모바일 자리가 맞는지(2026-11-05)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh  # noqa: E402

A1105 = {"nasdaq_overheat": {"gap_pct": 48.76, "month": "2026-11"},
         "us_index_position": {"asof": "2026-11-04", "items": [{"name": "S&P500", "pct": 5.03}]}}


def _render(ctx, place="main"):
    return gh.make_env().get_template("sections/struct_signal.html").render(ssig_place=place, **ctx)


def test_real_values_match_home_scale():
    n = gh.build_struct_signal(A1105)["struct_sig"]
    assert (n["level"], n["x_gap"], n["x_caution"], n["x_warn"], n["w_caution"]) == ("ok", 60.9, 75.0, 87.5, 12.5)


def test_gauge_widens_above_80():
    assert gh.build_struct_signal({"nasdaq_overheat": {"gap_pct": 84.0, "month": "2021-02"}})["struct_sig"]["x_gap"] == 93.3


def test_level_badges():
    for gap, level in ((59.9, "ok"), (60.0, "caution"), (70.0, "warn")):
        assert gh.build_struct_signal({"nasdaq_overheat": {"gap_pct": gap}})["struct_sig"]["level"] == level


def test_missing_data_drops_block():
    assert gh.build_struct_signal({}) == {}
    assert gh.build_struct_signal({"us_index_position": A1105["us_index_position"]}) == {}


def test_only_nasdaq_row_is_rendered():
    html = _render(gh.build_struct_signal(A1105), "aside")
    assert "ssig--aside" in html and 'href="/stocks/nasdaq-check/"' in html and "+48.8%" in html and "11월 월봉 고점" in html
    assert "200일선" not in html and "매일 업데이트" not in html


def test_template_places_body_end_and_above_market_panel():
    t = (gh.TEMPLATES_DIR / "briefings" / "us.html").read_text(encoding="utf-8")
    main_at, ad_at = t.index('ssig_place = "main"'), t.index("sections/_ad_multiplex.html")
    aside_at, market_at = t.index('ssig_place = "aside"'), t.index("sections/market_data.html")
    assert t.index("sections/monthly_ma5.html") < main_at < ad_at < aside_at < market_at


def test_hidden_when_nasdaq_section_is_shown():
    # 60% 이상이면 나스닥 체크 섹션이 같은 값을 보여준다 — 두 번 그리지 않는다
    t = (gh.TEMPLATES_DIR / "briefings" / "us.html").read_text(encoding="utf-8")
    assert t.count("{% if struct_sig and not nq %}") == 2


def test_css_shows_only_one_copy():
    css = (Path(__file__).resolve().parent.parent / "web" / "assets" / "style.css").read_text(encoding="utf-8")
    assert ".ssig--aside{display:none;}" in css
    assert "@media(max-width:900px){.ssig--main{display:none;}.ssig--aside{display:block;" in css
