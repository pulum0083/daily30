# 외국계 IB 코멘트 수집기의 순수 헬퍼(하우스 매칭·24h 필터·라벨·감성·중복제거) 단위 테스트
import sys, os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from fetch_ib_korea_views import (
    _match_house, _within_24h, _time_label, _normalize_sentiment, _dedup_by_house, KST,
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

def test_dedup_by_house_keeps_latest_max3():
    now = datetime(2026, 7, 8, 7, 20, tzinfo=KST)
    def cand(name, h, m):
        return {"house": name, "initials": "XX",
                "published_at": datetime(2026, 7, 8, h, m, tzinfo=KST)}
    cands = [
        cand("모건스탠리", 6, 0),
        cand("모건스탠리", 9, 51),   # 같은 하우스 더 최근 → 이게 남아야
        cand("JP모건", 5, 0),
        cand("골드만삭스", 4, 0),
        cand("UBS", 3, 0),           # 4번째 하우스 → 최대 3건 컷
    ]
    out = _dedup_by_house(cands, max_items=3)
    assert len(out) == 3
    ms = [c for c in out if c["house"] == "모건스탠리"]
    assert len(ms) == 1 and ms[0]["published_at"].hour == 9
    # 최신순 정렬
    assert [c["published_at"] for c in out] == sorted(
        [c["published_at"] for c in out], reverse=True)
