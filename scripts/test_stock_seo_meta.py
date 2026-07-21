# 종목·미국·섹터 상세 페이지의 SEO 메타 주입 회귀 테스트 (네트워크 없이 템플릿만 렌더)
"""2026-07-21: 종목 상세 46개가 <title> 외에 description·canonical·OG·JSON-LD를 하나도
갖지 않은 채 발행되던 것을 고치면서 추가. STOCKS_SERVICE_RULES §9 발행 게이트 4번이
문서상 체크리스트로만 있어 아무도 못 잡았으므로, 여기서 자동 검사로 고정한다.
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as g  # noqa: E402

BASE = "https://doubleshot.space"


def _env():
    env = g.make_env()
    env.filters["usd"] = g.ud.fmt_usd  # build_us_stock_page가 런타임에 등록하는 필터
    return env


def _head(html_text):
    return html_text.split("</head>")[0]


def _jsonld_types(head):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', head, re.S)
    return [json.loads(b)["@type"] for b in blocks]


def _assert_core_meta(head, url):
    """모든 페이지가 공통으로 가져야 할 메타. 하나라도 빠지면 실패."""
    assert re.search(r'<meta name="description" content="[^"]{20,}"', head), "description 없음/너무 짧음"
    assert re.search(r'<meta name="robots"', head), "robots 없음"
    assert f'<link rel="canonical" href="{url}">' in head, "canonical 없음/불일치"
    assert f'<meta property="og:url" content="{url}">' in head, "og:url 없음/불일치"
    assert re.search(r'<meta property="og:title" content="[^"]+"', head), "og:title 없음"
    assert re.search(r'<meta property="og:description" content="[^"]{20,}"', head), "og:description 없음"
    assert re.search(r'<meta property="og:image" content="https://', head), "og:image 없음"
    assert re.search(r'<meta name="twitter:card"', head), "twitter:card 없음"


# ── 목업 (템플릿이 요구하는 최소 필드) ──────────────────────────────────────

_RD = {
    "price": 244000, "change_pct": -4.31, "min": 60400,
    "sparkline": [240000, 244000], "sparkline_dates": ["7/17", "7/20"],
    "ma20_dist_pct": -5.0, "ma200_dist_pct": 31.2,
    "week52_high": 362500, "week52_low": 60400, "week52_pos_pct": 60.9,
}
_TARGETS = {
    "count": 14, "min_price": 460000, "avg_price": 508000, "max_price": 560000,
    "cur_pct": 10.0, "avg_pct": 48.0, "avg_upside": 95.0,
    "rows": [{"firm": "하나증권", "price": 480000, "op": "매수", "when": "1주 전", "upside": 96.7}],
}


def _stock_ctx(**over):
    stock = {"code": "005930", "name": "삼성전자", "sector": "반도체",
             "sector_key": "semicon", "market": "KOSPI", "badges": [], "cats": [], "why": ""}
    ctx = {
        "stock": stock, "rd": _RD, "peers": [], "generated_label": "07-20 종가",
        "chips_ticker": "", "bellwether": None,
        "foreign_rate": 46.56, "foreign_spark": [46.5, 46.6, 46.4],
        "supply5": [{"date": "7/20", "i": 1, "o": 2, "f": 3}],
        "financials": [{"q": "25Q2", "rev": 1, "op": 2, "est": False}],
        "picks": [], "broker_targets": _TARGETS, "acc": {"pct": 67},
        "today_str": "2026-07-21",
    }
    ctx.update(over)
    ctx.update(g._stock_seo(ctx["stock"], ctx))
    return ctx


# ── 테스트 ──────────────────────────────────────────────────────────────────

def test_korean_stock_detail_has_full_seo_meta():
    ctx = _stock_ctx()
    head = _head(_env().get_template("stocks/detail.html").render(**ctx))
    _assert_core_meta(head, f"{BASE}/stocks/005930/")
    assert _jsonld_types(head) == ["BreadcrumbList", "Corporation"]


def test_korean_stock_breadcrumb_points_to_real_paths():
    ctx = _stock_ctx()
    head = _head(_env().get_template("stocks/detail.html").render(**ctx))
    crumb = json.loads(re.findall(r'ld\+json">(.*?)</script>', head, re.S)[0])
    items = [e["name"] for e in crumb["itemListElement"]]
    assert items == ["홈", "종목", "반도체", "삼성전자"]
    # 섹터 링크가 실제 생성 경로와 같아야 한다(끊긴 브레드크럼 방지)
    assert crumb["itemListElement"][2]["item"] == f"{BASE}/stocks/sector/semicon/"


def test_description_omits_sections_the_page_does_not_have():
    """목표주가는 3종목만 수집된다 — 없는 종목의 description이 있다고 말하면 운영 규칙 0 위반."""
    import html as _h
    with_t = _h.unescape(g._stock_seo(_stock_ctx()["stock"], _stock_ctx())["seo_desc"])
    assert "증권사 목표주가" in with_t

    ctx = _stock_ctx(broker_targets=None, financials=None, supply5=None, foreign_rate=None)
    without = _h.unescape(ctx["seo_desc"])
    for absent in ("증권사 목표주가", "분기 실적", "수급", "외국인 보유율"):
        assert absent not in without, f"없는 섹션 '{absent}'이 description에 있음"


@pytest.mark.parametrize("ticker,kind,expected", [
    ("nvda", "stock", ["BreadcrumbList", "Corporation"]),
    ("soxx", "etf", ["BreadcrumbList"]),  # ETF에 Corporation 타입을 억지로 붙이지 않는다
])
def test_us_detail_has_full_seo_meta(ticker, kind, expected):
    stock = {"ticker": ticker.upper(), "name": ticker.upper(), "kind": kind, "peers": []}
    financials = [{"q": "25Q4", "rev": 1, "op": 2}] if kind == "stock" else []
    jsonld = [g._breadcrumb([
        ("홈", "/stocks/"), ("종목", "/stocks/"),
        ("미국 반도체", None), (stock["name"], f"/stocks/us/{ticker}/"),
    ])]
    if kind == "stock":
        jsonld.append({"@context": "https://schema.org", "@type": "Corporation",
                       "name": stock["name"], "tickerSymbol": stock["ticker"],
                       "url": f"{BASE}/stocks/us/{ticker}/"})
    seo = g._seo_ctx(title=f"{stock['name']} — 더블샷",
                     description="테스트 설명입니다. 실측 데이터로 정리했어요. 원화 환산도 봐요.",
                     path=f"/stocks/us/{ticker}/", jsonld=jsonld)
    rd = dict(_RD, price=1.0, change_pct=0.0, asof="2026-07-20", sparkline=[], sparkline_dates=[])
    head = _head(_env().get_template("stocks/us_detail.html").render(
        stock=stock, rd=rd, financials=financials, peers=[],
        generated_label="07-20 종가", acc={"pct": 67}, **seo))
    _assert_core_meta(head, f"{BASE}/stocks/us/{ticker}/")
    assert _jsonld_types(head) == expected


def test_sector_page_has_full_seo_meta():
    html_text = _env().get_template("pages/stock_sector.html").render(
        sector_label="반도체", sector_key="semicon", sector_emoji="🔧", sector_desc="설명",
        canonical_url=f"{BASE}/stocks/sector/semicon/",
        seo_jsonld=[g._jsonld(g._breadcrumb([
            ("홈", "/stocks/"), ("종목", "/stocks/"), ("반도체", "/stocks/sector/semicon/")]))],
        stocks=[], avg_pct=0, avg_pct_fmt="0.00%", avg_cls="flat",
        breadth={"up": 0, "down": 0, "flat": 0, "total": 0}, snapshot_date="2026-07-20",
        all_sectors=[{"key": "semicon", "label": "반도체", "emoji": "🔧"}],
        css_path="/assets/style.css", js_path="/assets/main.js")
    head = _head(html_text)
    _assert_core_meta(head, f"{BASE}/stocks/sector/semicon/")
    assert _jsonld_types(head) == ["BreadcrumbList"]


def test_meta_values_are_html_escaped():
    """make_env는 autoescape=False다. 따옴표가 섞이면 속성이 깨지므로 Python에서 이스케이프해야 한다."""
    seo = g._seo_ctx(title='따옴표 "테스트" & 앰퍼샌드', description="설명 " * 10, path="/stocks/000000/")
    assert "&quot;" in seo["seo_title"] and "&amp;" in seo["seo_title"]


def test_jsonld_cannot_break_out_of_script_tag():
    payload = g._jsonld({"@type": "Corporation", "name": "</script><script>alert(1)</script>"})
    assert "</script>" not in payload


def test_sitemap_includes_sector_pages():
    """섹터 8개가 생성되는데도 sitemap에 빠져 색인 경로가 없던 문제(2026-07-21)."""
    universe = g.load_json(g.CONFIG_DIR / "stock_universe.json")
    keys = [k for k in universe.get("sectors", {})
            if (g.WEB_DIR / "stocks" / "sector" / k / "index.html").exists()]
    if not keys:
        pytest.skip("생성된 섹터 페이지가 없음")
    sitemap = (g.WEB_DIR / "sitemap.xml").read_text(encoding="utf-8")
    for k in keys:
        assert f"{BASE}/stocks/sector/{k}/" in sitemap, f"섹터 {k}가 sitemap에 없음"
