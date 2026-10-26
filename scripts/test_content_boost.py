# 콘텐츠 보강(2026-10-26) — 예측 근거 신호·전일 수급 카드·미국 프리마켓 띠 테스트(네트워크 없음)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh  # noqa: E402

KOSPI_MD = {
    "generated_at": "2026-10-23T07:26:00+09:00",
    "market_data_js": {"sox": {"chg": -6.72}, "nasdaq": {"chg": -2.59}, "nq": {"chg": -2.91}, "kospi": {"chg": -3.52}},
    "ewy": {"change_pct": -5.16}, "vix": {"change_pct": 14.09},
    "investor_trading": {"date": "20261022", "asof": "1540", "foreign": {"net": -1_971_200},
                         "institution": {"net": 2_545_600}, "individual": {"net": -673_400}},
}


def _env():
    return gh.make_env()


# ── 예측 근거 신호 ──
def test_prior_signals_from_market_data_and_stored():
    a = {}
    ctx = gh.build_prior_signals(a, KOSPI_MD, "2026-10-23")
    names = [r["name"] for r in ctx["prior_sig"]]
    assert names == ["SOX", "나스닥", "나스닥 선물", "EWY(코스피 반영분 제외)", "VIX"]
    assert round(a["prior_signals"]["ewy_resid"], 2) == -1.64          # EWY −5.16 − 코스피 −3.52
    html = _env().get_template("sections/briefing_hero.html").render(
        **gh.build_prediction({"prediction": {"direction": "하락 우위", "up_pct": 7, "down_pct": 93, "basis": "open"}},
                              "KOSPI", "x", "07:26"), **ctx)
    assert "예측 근거 신호" in html and 'SOX <b class="dn">−6.72%</b>' in html and 'VIX <b class="up">+14.09%</b>' in html


def test_prior_signals_skip_other_date_market_data():
    assert gh.build_prior_signals({}, KOSPI_MD, "2026-10-26") == {}


def test_prior_signals_snapshot_first():
    a = {"prior_signals": {"sox": 1.0}}
    assert gh.build_prior_signals(a, {}, "2026-10-23")["prior_sig"] == [{"name": "SOX", "pct": 1.0}]


# ── 전일 수급 ──
def test_prev_supply_card_order_and_units():
    a = {}
    ctx = gh.build_prev_supply(a, KOSPI_MD, "2026-10-23")
    assert ctx["prev_supply"]["label"] == "10월 22일"
    assert [(r["name"], r["eok"]) for r in ctx["prev_supply"]["rows"]] == [("개인", -6734), ("기관", 25456), ("외국인", -19712)]
    assert a["prev_supply"]["date"] == "20261022"
    html = _env().get_template("sections/issue_check.html").render(**ctx)
    assert "국내 · 실측" in html and "10월 22일 코스피 투자자별 순매수" in html
    assert html.index("개인") < html.index("기관") < html.index("외국인") and "+25,456억" in html


def test_prev_supply_rejects_same_day_or_missing():
    same = dict(KOSPI_MD, investor_trading=dict(KOSPI_MD["investor_trading"], date="20261023"))
    assert gh.build_prev_supply({}, same, "2026-10-23") == {}
    assert gh.build_prev_supply({}, dict(KOSPI_MD, investor_trading={}), "2026-10-23") == {}
    assert gh.build_prev_supply({}, KOSPI_MD, "2026-10-26") == {}       # 다른 날 시장 데이터


# ── 미국 프리마켓 띠 ──
US_MD = {
    "generated_at": "2026-10-23T21:15:30+09:00",
    "futures": {"sp500_fut": {"change_pct": -0.31}, "nasdaq_fut": {"chg": -0.52}, "dow_fut": {}},
    "bigtech": {"NVDA": {"change_pct": 1.2}, "AAPL": {"change_pct": -0.4}, "MSFT": {}},
}


def test_premarket_strip_builds_and_renders():
    a = {}
    ctx = gh.build_premarket_strip(a, US_MD, "2026-10-23", "21:15")
    pm = ctx["premarket"]
    assert [f["name"] for f in pm["futures"]] == ["S&P500 선물", "나스닥 선물"]   # 값 없는 다우 선물은 뺀다
    assert [s["name"] for s in pm["stocks"]] == ["NVDA", "AAPL"] and a["premarket"]["asof"] == "21:15"
    html = _env().get_template("sections/us_premarket.html").render(**ctx)
    assert "지금 프리마켓 · 실측" in html and "21:15 KST 기준" in html and 'NVDA</em><b class="up">+1.20%' in html


def test_premarket_strip_omitted_without_data_or_other_date():
    assert gh.build_premarket_strip({}, {"generated_at": "2026-10-23T21:15", "futures": {}, "bigtech": {}}, "2026-10-23") == {}
    assert gh.build_premarket_strip({}, US_MD, "2026-10-26") == {}


def test_us_template_puts_strip_on_top():
    t = (gh.TEMPLATES_DIR / "briefings" / "us.html").read_text(encoding="utf-8")
    assert t.index("sections/us_premarket.html") < t.index("tv-lead")
