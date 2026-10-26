# 월봉 5개월선 안착 종목 렌더 테스트 — 스냅샷 1순위·날짜 대조·빈 목록·백테스트 파일 없음·템플릿 문구
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh


def item(name="메리츠금융지주", code="138040", streak=3, cur=True):
    strip = [{"m": f"2026{m:02d}", "label": f"{m}월", "close": 100.0 + m, "ma5": 100.0,
              "gap_pct": float(m) - 6, "run": m >= 7, "cur": False} for m in range(1, 10)]
    if cur:
        strip.append({"m": "202610", "label": "이번 달", "close": 120.0, "ma5": 110.0, "gap_pct": 9.09,
                      "run": False, "cur": True})
    return {"code": code, "name": name, "passed": True, "streak": streak, "run_label": "7월~9월",
            "last_complete": "202609", "month_end_close": 126300.0, "month_end_ma5": 116200.0,
            "month_end_gap_pct": 8.69, "now_date": "20261023" if cur else "20260930", "now_close": 127800.0,
            "now_gap_pct": 5.46, "mtd_pct": 1.19 if cur else None, "fr_now": 14.21, "fr_chg_3m": 0.17,
            "strip": strip}


def test_snapshot_first_builds_items_and_stats():
    a = {"monthly_ma5": {"date": "2026-10-26", "items": [item()]}}
    ctx = gh.build_monthly_ma5(a, "2026-10-26")
    x = ctx["ma5m_items"][0]
    assert x["name"] == "메리츠금융지주" and x["now_label"] == "10/23" and x["last_label"] == "9월"
    assert x["has_cur"] and x["n"] == 10
    assert x["cells"][-1]["cls"] == "up" and x["cells"][0]["cls"] == "dn"
    assert all(0 <= c["h"] <= 100 for c in x["cells"])
    st = ctx["ma5m_stats"]
    bt = json.loads(gh.MA5_BACKTEST_PATH.read_text(encoding="utf-8"))["horizons"]["12"]
    assert st["win_pct"] == bt["signal"]["win_pct"] and st["base_win_pct"] == bt["base"]["win_pct"]
    assert st["years"] == 15


def test_no_items_hides_section():
    assert gh.build_monthly_ma5({"monthly_ma5": {"date": "2026-10-26", "items": []}}, "2026-10-26") == {"ma5m_items": []}


def test_missing_backtest_file_hides_section(monkeypatch, tmp_path):
    # 상승 비율 문장 없이 종목만 보이면 '오른다'로 읽힌다 — 섹션째 뺀다
    monkeypatch.setattr(gh, "MA5_BACKTEST_PATH", tmp_path / "none.json")
    a = {"monthly_ma5": {"date": "2026-10-26", "items": [item()]}}
    assert gh.build_monthly_ma5(a, "2026-10-26") == {"ma5m_items": []}


def test_data_file_used_only_when_date_matches(monkeypatch, tmp_path):
    monkeypatch.setattr(gh, "DATA_DIR", tmp_path)
    (tmp_path / "monthly_ma5.json").write_text(json.dumps({"date": "2026-10-23", "items": [item()]}), encoding="utf-8")
    a = {}
    assert gh.build_monthly_ma5(a, "2026-10-26") == {"ma5m_items": []}
    assert "monthly_ma5" not in a
    a2 = {}
    ctx = gh.build_monthly_ma5(a2, "2026-10-23")
    assert ctx["ma5m_items"] and a2["monthly_ma5"]["date"] == "2026-10-23"   # 스냅샷에 실린다


def test_template_renders_strip_facts_and_footer():
    a = {"monthly_ma5": {"date": "2026-10-26", "items": [item()]}}
    ctx = gh.build_monthly_ma5(a, "2026-10-26")
    html = gh.make_env().get_template("sections/monthly_ma5.html").render(**ctx)
    assert "월봉 5개월선 안착 종목" in html and "메리츠금융지주" in html and "127,800원" in html
    assert html.count('class="m5a-cell') == 10 and html.count("is-run") == 3 and html.count("is-cur") == 1
    assert "9월 말 이격</em>+8.7%" in html and "지금 이격</em>+5.5%" in html and "+0.17%p" in html
    assert f"1년 뒤 오른 비율은 {ctx['ma5m_stats']['win_pct']}%" in html and "비슷했어요" in html
    assert "매매 신호가 아니에요" not in html
    assert 'data-modal-open="ma5m-modal"' in html and "추천" not in html


def test_month_start_hides_current_gap_chip():
    a = {"monthly_ma5": {"date": "2026-11-02", "items": [item(cur=False)]}}
    ctx = gh.build_monthly_ma5(a, "2026-11-02")
    html = gh.make_env().get_template("sections/monthly_ma5.html").render(**ctx)
    assert "지금 이격" not in html and "is-cur" not in html and "9/30 종가" in html


def test_kospi_template_uses_new_section_not_stock_picks():
    t = (gh.TEMPLATES_DIR / "briefings" / "kospi.html").read_text(encoding="utf-8")
    assert "sections/monthly_ma5.html" in t and "sections/stock_picks.html" not in t
    cfg = json.loads((gh.CONFIG_DIR / "kospi.json").read_text(encoding="utf-8"))
    assert "monthly_ma5" in cfg["sections_main"] and "stock_picks" not in cfg["sections_main"]


def test_modal_present_and_us_picks_modal_kept():
    m = (gh.TEMPLATES_DIR / "sections" / "_modals.html").read_text(encoding="utf-8")
    assert 'id="ma5m-modal"' in m and 'id="picks-modal"' in m
