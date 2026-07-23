# 발행 게이트(verify_publish_gate)가 실제로 위반을 잡는지 검증하는 회귀 테스트
"""게이트 자체가 조용히 통과시키면 게이트가 없는 것과 같다. 항목별로 하나씩 빼서
반드시 검출되는지 확인하고, 차단 시 기존 파일이 보존되는지도 함께 본다.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_publish_gate as g  # noqa: E402

URL = "https://doubleshot.space/stocks/005930/"

_JSONLD = (
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[]}'
    "</script>"
)


def _page(**over):
    """게이트를 통과하는 최소 페이지. over로 특정 조각을 빈 문자열로 바꿔 누락을 만든다."""
    parts = {
        "title": "<title>삼성전자(005930) · 종목 분석 — 더블샷</title>",
        "desc": '<meta name="description" content="삼성전자 시세와 기술 신호를 실측 데이터로 정리했어요.">',
        "robots": '<meta name="robots" content="index,follow">',
        "canonical": f'<link rel="canonical" href="{URL}">',
        "og_url": f'<meta property="og:url" content="{URL}">',
        "og_title": '<meta property="og:title" content="삼성전자(005930)">',
        "og_desc": '<meta property="og:description" content="삼성전자 시세와 기술 신호를 실측으로 정리했어요.">',
        "og_image": '<meta property="og:image" content="https://doubleshot.space/assets/og-image.png">',
        "tw": '<meta name="twitter:card" content="summary_large_image">',
        "jsonld": _JSONLD,
    }
    parts.update(over)
    return "<html><head>" + "".join(parts.values()) + "</head><body>본문</body></html>"


def test_valid_page_passes():
    assert g.check_html(_page(), URL) == []


@pytest.mark.parametrize("key", [
    "title", "desc", "robots", "canonical", "og_url",
    "og_title", "og_desc", "og_image", "tw", "jsonld",
])
def test_each_missing_element_is_caught(key):
    """필수 요소를 하나씩 빼면 반드시 위반으로 잡혀야 한다."""
    assert g.check_html(_page(**{key: ""}), URL), f"{key} 누락이 검출되지 않음"


def test_short_description_is_caught():
    assert any("짧" in e for e in g.check_html(_page(desc='<meta name="description" content="짧음">'), URL))


def test_canonical_mismatch_is_caught():
    other = '<link rel="canonical" href="https://doubleshot.space/stocks/000660/">'
    assert any("canonical 불일치" in e for e in g.check_html(_page(canonical=other), URL))


def test_broken_jsonld_is_caught():
    broken = '<script type="application/ld+json">{"@type":"BreadcrumbList",}</script>'
    assert any("파싱 실패" in e for e in g.check_html(_page(jsonld=broken), URL))


def test_jsonld_without_breadcrumb_is_caught():
    only_corp = ('<script type="application/ld+json">'
                 '{"@context":"https://schema.org","@type":"Corporation","name":"삼성전자"}</script>')
    assert any("BreadcrumbList" in e for e in g.check_html(_page(jsonld=only_corp), URL))


def test_escaped_jsonld_still_parses():
    """_jsonld()가 '</' → '<\\/'로 이스케이프한 실제 출력 형태도 통과해야 한다."""
    esc = ('<script type="application/ld+json">'
           '{"@type":"BreadcrumbList","name":"a<\\/b"}</script>')
    assert g.check_html(_page(jsonld=esc), URL) == []


def test_v2_path_is_caught():
    """SERVICE_RULES §3 — /v2/ 경로는 완전 삭제됨."""
    html = _page().replace("<body>본문", '<body><link href="/v2/assets/style.css">')
    assert any("/v2/" in e for e in g.check_html(html, URL))


def test_gate_write_blocks_and_preserves_previous(tmp_path):
    """위반 시 쓰지 않고, 직전 정상본이 그대로 남아야 한다."""
    out = tmp_path / "index.html"
    out.write_text("직전 정상본", encoding="utf-8")
    errs = g.gate_write(out, _page(canonical=""), URL)
    assert errs
    assert out.read_text(encoding="utf-8") == "직전 정상본"


def test_gate_write_writes_on_pass(tmp_path):
    out = tmp_path / "sub" / "index.html"
    assert g.gate_write(out, _page(), URL) == []
    assert "삼성전자" in out.read_text(encoding="utf-8")


def test_check_sitemap_detects_missing(monkeypatch, tmp_path):
    sm = tmp_path / "sitemap.xml"
    sm.write_text("<urlset><url><loc>%s</loc></url></urlset>" % URL, encoding="utf-8")
    monkeypatch.setattr(g, "WEB_DIR", tmp_path)
    missing = "https://doubleshot.space/stocks/sector/semicon/"
    assert g.check_sitemap([URL]) == []
    assert any(missing in e for e in g.check_sitemap([URL, missing]))


def test_audit_flags_page_that_was_never_generated(monkeypatch, tmp_path):
    """설정에 있는데 생성된 적 없는 페이지는 404다 — 조용히 통과하면 안 된다(QA 발견, 2026-07-21)."""
    monkeypatch.setattr(g, "WEB_DIR", tmp_path)
    monkeypatch.setattr(g, "expected_pages", lambda: [
        (tmp_path / "stocks" / "999999" / "index.html", "https://doubleshot.space/stocks/999999/"),
    ])
    assert g.audit() == 1


def test_published_output_passes_gate():
    """실제 발행본 전수 감사 — 이 테스트가 깨지면 지금 라이브가 위반 상태다."""
    assert g.audit() == 0
