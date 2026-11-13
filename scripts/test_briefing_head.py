# 브리핑 <title>·description(검색어 + 날짜 + 헤드라인) 생성 테스트
from generate_html import briefing_head


def test_kospi_open_basis_title_and_description():
    a = {"prediction": {"basis": "open", "direction": "상승 우위", "up_pct": 83, "confidence": 74},
         "todays_view": {"view_title": "코스피 5500 붕괴 다음날", "dek": "간밤 뉴욕은 <b>반도체</b>부터 샀어요."}}
    h = briefing_head(a, "kospi", "2026-10-27")
    assert h["title"] == "코스피 시초가 예측 10월 27일 | 코스피 5500 붕괴 다음날 | 더블샷"
    assert h["description"] == "KOSPI 시초가 방향 예측: 상승 우위 83% · 신뢰도 74%. 간밤 뉴욕은 반도체부터 샀어요."


def test_kospi_old_basis_is_not_called_open():
    a = {"prediction": {"direction": "하락 우위", "up_pct": 30, "confidence": 60},
         "todays_view": {"view_title": "제목"}}
    h = briefing_head(a, "kospi", "2026-08-05")
    assert h["title"].startswith("코스피 방향 예측 8월 5일")
    assert "시초가" not in h["title"]


def test_close_uses_market_title_and_dek():
    a = {"market_title": "개미만 팔았다", "dek": "외국인이 샀어요."}
    h = briefing_head(a, "close", "2026-10-27")
    assert h["title"] == "코스피 마감 시황 10월 27일 | 개미만 팔았다 | 더블샷"
    assert h["description"] == "외국인이 샀어요."


def test_no_headline_falls_back_without_inventing():
    h = briefing_head({}, "us", "2026-10-26")
    assert h["title"] == "미국 증시 전망 10월 26일 | 더블샷"
    assert h["description"] == "2026-10-26 미국 시장 브리핑"


def test_values_are_html_escaped():
    a = {"todays_view": {"view_title": 'S&P500 "반등"', "dek": "a<b"}}
    h = briefing_head(a, "us", "2026-10-26")
    assert "S&amp;P500 &quot;반등&quot;" in h["title"]
    assert '"' not in h["description"] and "<" not in h["description"]


# ── 구조화 데이터·<h1>(2026-11-13) — 검색엔진이 '언제 쓴 무슨 글인지' 알게 한다 ──
import json
import re
from pathlib import Path as _P

from generate_html import briefing_jsonld, strip_og_image


def _ld(blocks):
    return [json.loads(b) for b in blocks]


def test_jsonld_is_news_article_with_kst_time_and_brand():
    a = {"todays_view": {"view_title": "코스피 5500 붕괴 다음날"}}
    head = briefing_head(a, "kospi", "2026-10-27")
    art, crumb = _ld(briefing_jsonld(head, "kospi", "2026-10-27", "2026-10-27T07:28:11+09:00",
                                     "https://doubleshot.space/briefings/2026-10-27/kospi/"))
    assert art["@type"] == "NewsArticle"
    assert art["headline"] == "코스피 5500 붕괴 다음날"
    assert art["datePublished"] == "2026-10-27T07:28:11+09:00"
    assert art["publisher"]["name"] == "더블샷"
    assert art["image"].endswith("/briefings/2026-10-27/kospi/og.png")
    assert crumb["@type"] == "BreadcrumbList" and crumb["itemListElement"][-1]["name"] == "코스피 방향 예측 10월 27일"


def test_jsonld_naive_time_is_read_as_kst_and_missing_time_falls_back():
    head = briefing_head({}, "us", "2026-10-26")
    art = _ld(briefing_jsonld(head, "us", "2026-10-26", "2026-10-26 21:17:00", "https://x/"))[0]
    assert art["datePublished"] == "2026-10-26T21:17:00+09:00"
    art = _ld(briefing_jsonld(head, "us", "2026-10-26", "", "https://x/"))[0]
    assert art["datePublished"] == "2026-10-26T00:00:00+09:00"
    assert art["headline"] == "미국 증시 전망 10월 26일"     # 헤드라인이 없으면 지어내지 않고 검색어+날짜


def test_jsonld_escapes_script_end():
    head = briefing_head({"todays_view": {"view_title": "a</script>b"}}, "us", "2026-10-26")
    for block in briefing_jsonld(head, "us", "2026-10-26", "", "https://x/"):
        assert "</script" not in block


def test_strip_og_image_also_drops_jsonld_image():
    head = briefing_head({"todays_view": {"view_title": "t"}}, "us", "2026-10-26")
    block = briefing_jsonld(head, "us", "2026-10-26", "", "https://x/b/")[0]
    out = strip_og_image(f'<script type="application/ld+json">{block}</script>')
    assert "og.png" not in out
    json.loads(re.search(r'>(.*)</script>', out).group(1))       # 지운 뒤에도 올바른 JSON


def test_each_briefing_headline_is_h1():
    t = _P(__file__).resolve().parent / "templates"
    assert '<h1 class="bx-head">' in (t / "sections/briefing_hero.html").read_text()
    assert '<h1 class="tv-title">' in (t / "briefings/us.html").read_text()
    assert '<h1 class="reason-title-bar">' in (t / "sections/close_brief.html").read_text()
