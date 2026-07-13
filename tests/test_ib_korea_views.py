# 외국계 IB 코멘트 수집기의 순수 헬퍼(하우스 매칭·24h 필터·라벨·감성·지수레벨·URL복원·실발행일 파싱) 단위 테스트
import sys, os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from fetch_ib_korea_views import (
    _match_house, _within_24h, _time_label, _normalize_sentiment, KST,
    _extract_index_levels, _is_stale_index_level,
    _extract_resolved_url, _parse_real_published_at,
)

def test_match_house_basic():
    h = _match_house("모건스탠리 삼성·SK하이닉스 비중 축소 권고")
    assert h is not None and h["name"] == "모건스탠리" and h["initials"] == "MS"

def test_match_house_alias():
    assert _match_house("JP모간, 코스피 목표 상향")["initials"] == "JPM"
    assert _match_house("골드만, 삼성전자 슈퍼사이클")["name"] == "골드만삭스"

def test_match_house_acronym_case_insensitive():
    assert _match_house("ubs, 한국 증시 비중확대")["initials"] == "UBS"

def test_match_house_none():
    assert _match_house("삼성전자 3분기 실적 발표") is None
    assert _match_house("국내 증권사 코스피 전망") is None

def test_within_24h():
    now = datetime(2026, 7, 8, 7, 20, tzinfo=KST)
    assert _within_24h(datetime(2026, 7, 8, 6, 0, tzinfo=KST), now) is True
    assert _within_24h(datetime(2026, 7, 7, 9, 51, tzinfo=KST), now) is True   # 21.5h 전
    assert _within_24h(datetime(2026, 7, 7, 6, 0, tzinfo=KST), now) is False   # 25.3h 전
    assert _within_24h(datetime(2026, 7, 9, 0, 0, tzinfo=KST), now) is False   # 미래

def test_time_label():
    now = datetime(2026, 7, 8, 7, 20, tzinfo=KST)
    assert _time_label(datetime(2026, 7, 8, 6, 0, tzinfo=KST), now) == "오늘 06:00"
    assert _time_label(datetime(2026, 7, 7, 9, 51, tzinfo=KST), now) == "어제 09:51"

def test_normalize_sentiment():
    assert _normalize_sentiment("bullish") == "bull"
    assert _normalize_sentiment("BEAR") == "bear"
    assert _normalize_sentiment("neutral") == "neu"
    assert _normalize_sentiment("긍정") == "neu"   # 알 수 없는 값 → neu

def test_extract_index_levels_man_suffix():
    # "1만2000선"의 "2000선" 부분이 _KOSPI_PLAIN_PAT에도 별도로 매칭되는 건 기존 동작(범위 밖) —
    # 여기서는 12000이 추출되는지만 확인한다.
    assert 12000 in _extract_index_levels("코스피 1만2000선 돌파")

def test_extract_index_levels_pointer_suffix():
    assert _extract_index_levels("코스피 8700포인트 부근") == [8700]

def test_extract_index_levels_comma_forecast_verb():
    # 2026-07-14 실사고: "15,000 간다" — 만/선/포인트 패턴 모두 놓쳤던 케이스
    assert _extract_index_levels("코스피, 강세장서 15,000 간다...JP모건 전망치 상향") == [15000]

def test_extract_index_levels_bare_forecast_verb():
    # 같은 사고의 두 번째 변형: 콤마도 없이 "15000 가능"
    assert _extract_index_levels('JP모건 "코스피, 강세장 시 15000 가능…강세 전망 유지"') == [15000]

def test_extract_index_levels_no_match_without_context():
    # 지수 레벨과 무관한 숫자(예: 그냥 큰 수)는 오탐하지 않는다
    assert _extract_index_levels("반도체 매출 15000억원 기록") == []

def test_is_stale_index_level_catches_15000_comma_variant():
    # 실제 코스피(~7480) 대비 15,000은 +30% 밴드를 벗어남 → 재노출 옛 기사로 판정
    assert _is_stale_index_level("코스피, 강세장서 15,000 간다...JP모건 전망치 상향", 7480) is True

def test_is_stale_index_level_within_band_ok():
    assert _is_stale_index_level("코스피 7800선 터치 시도", 7480) is False


def test_extract_resolved_url_unescapes_double_encoded_query():
    # 2026-07-14 실사고: batchexecute 응답의 \uXXXX 이중 이스케이프에서 역슬래시 직전에 잘려
    # "?no"·"?apiversion" 처럼 쿼리스트링이 통째로 사라졌던 문제의 재현 픽스처
    raw = (
        '\\",\\"https://www.theguru.co.kr/news/article.html?no'
        '\\\\u003d104294\\",1]",null,null,null,"generic"]'
    )
    seg = "garturlres" + raw
    assert _extract_resolved_url(seg) == "https://www.theguru.co.kr/news/article.html?no=104294"

def test_extract_resolved_url_no_marker_returns_none():
    assert _extract_resolved_url("no marker here") is None

def test_extract_resolved_url_decodes_ampersand():
    raw = 'x\\",\\"https://example.com/a?x\\\\u003d1\\\\u0026y\\\\u003d2\\",1]'
    seg = "garturlres" + raw
    assert _extract_resolved_url(seg) == "https://example.com/a?x=1&y=2"


def test_parse_real_published_at_jsonld():
    html = '<script type="application/ld+json">{"datePublished": "2026-07-13T10:28:28+09:00"}</script>'
    dt = _parse_real_published_at(html)
    assert dt is not None and dt.isoformat() == "2026-07-13T10:28:28+09:00"

def test_parse_real_published_at_meta_tag():
    html = '<meta property="article:published_time" content="2026-06-25T22:24:55Z">'
    dt = _parse_real_published_at(html)
    assert dt is not None and dt.year == 2026 and dt.month == 6 and dt.day == 25

def test_parse_real_published_at_missing_returns_none():
    # 구조화 데이터가 전혀 없으면(예: MSN의 JS 렌더링 셸) 신뢰 불가로 None — 상위에서 후보를 버린다
    assert _parse_real_published_at("<html><body>no structured date here</body></html>") is None
