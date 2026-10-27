# 브리핑 <title>·description(검색어 + 날짜 + 헤드라인) 생성 테스트
from generate_html import briefing_head


def test_kospi_open_basis_title_and_description():
    a = {"prediction": {"basis": "open", "direction": "상승 우위", "up_pct": 83, "confidence": 74},
         "todays_view": {"view_title": "코스피 5500 붕괴 다음날", "dek": "간밤 뉴욕은 <b>반도체</b>부터 샀어요."}}
    h = briefing_head(a, "kospi", "2026-10-27")
    assert h["title"] == "코스피 시초가 예측 10월 27일 | 코스피 5500 붕괴 다음날"
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
    assert h["title"] == "코스피 마감 시황 10월 27일 | 개미만 팔았다"
    assert h["description"] == "외국인이 샀어요."


def test_no_headline_falls_back_without_inventing():
    h = briefing_head({}, "us", "2026-10-26")
    assert h["title"] == "미국 증시 전망 10월 26일 — Double-Shot"
    assert h["description"] == "2026-10-26 미국 시장 브리핑"


def test_values_are_html_escaped():
    a = {"todays_view": {"view_title": 'S&P500 "반등"', "dek": "a<b"}}
    h = briefing_head(a, "us", "2026-10-26")
    assert "S&amp;P500 &quot;반등&quot;" in h["title"]
    assert '"' not in h["description"] and "<" not in h["description"]
