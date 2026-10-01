# 이미 발표된 실적을 '발표 임박'으로 쓴 예고 기사를 빼는 게이트 테스트 (2026-10-01 실사고).
# 사고: 마이크론 실적은 9/30 16:00 ET(= 10/1 05:00 KST)에 나왔는데, 21:17 미국 브리핑이
# 00:00에 발행된 예고 기사 "마이크론 실적 발표 임박…"을 골라 '오늘의 분수령'으로 서술했다.
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytz

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn

KST = pytz.timezone("Asia/Seoul")
ET = pytz.timezone("America/New_York")
NOW = KST.localize(datetime(2026, 10, 1, 21, 17))           # 미국 브리핑 발행 시각
MU_RELEASE = ET.localize(datetime(2026, 9, 30, 16, 0))      # = 10/1 05:00 KST

INCIDENT = "마이크론 실적 발표 임박, 월가 매출 508억달러대 전망 → HBM·D램이 실적 가를 것"


def _release(mapping):
    return lambda t, now: mapping.get(t)


def test_incident_preview_dropped():
    items = [{"text": INCIDENT, "ticker": "MU"}]
    assert fn._drop_preview_after_release(items, NOW, release_fn=_release({"MU": MU_RELEASE})) == []


def test_result_articles_survive():
    # 같은 날 풀에 있던 결과 기사 — 예고형 표현이 없으므로 통과해야 한다.
    items = [
        {"text": "마이크론 실적 호조 → 기술주 지지", "ticker": "MU",
         "article": {"title": "Bond markets slide again, Micron earnings help tech stocks"}},
        {"text": "마이크론 실적이 금리 부담 속 반도체를 받쳤다 → 다우 선물 반등", "ticker": "MU",
         "article": {"title": "Dow futures hit three-month low as yields surge, Micron earnings offer support"}},
    ]
    out = fn._drop_preview_after_release(items, NOW, release_fn=_release({"MU": MU_RELEASE}))
    assert out == items


def test_preview_before_release_is_kept():
    # 발표 6시간 전(=아직 안 나옴)이면 예고가 맞는 말이다.
    before = KST.localize(datetime(2026, 9, 30, 23, 0))
    items = [{"text": INCIDENT, "ticker": "MU"}]
    # 그 시점의 '최근 발표'는 석 달 전 분기 — 창(7일) 밖이라 판단하지 않는다.
    prev_q = ET.localize(datetime(2026, 6, 24, 16, 0))
    assert fn._drop_preview_after_release(items, before, release_fn=_release({"MU": prev_q})) == items


def test_old_release_outside_window_kept():
    # 다음 분기 실적을 앞둔 예고 — 직전 발표가 석 달 전이면 손대지 않는다.
    items = [{"text": "마이크론 실적 발표 앞두고 HBM 기대 → 메모리주 강세", "ticker": "MU"}]
    old = NOW - timedelta(days=90)
    assert fn._drop_preview_after_release(items, NOW, release_fn=_release({"MU": old})) == items


def test_llm_rewrite_without_preview_word_caught_by_article_title():
    # LLM이 '임박'을 빼고 다시 써도 원문 기사 제목이 예고형이면 잡는다.
    items = [{"text": "마이크론 실적에 월가 매출 508억달러대 전망 → HBM 관건", "ticker": "MU",
              "article": {"title": "마이크론 실적 발표 임박…월가 매출 508억달러대 전망"}}]
    assert fn._drop_preview_after_release(items, NOW, release_fn=_release({"MU": MU_RELEASE})) == []


def test_english_ahead_of_caught():
    items = ["Stock futures steady ahead of Micron earnings → chip stocks in focus"]
    assert fn._drop_preview_after_release(items, NOW, release_fn=_release({"MU": MU_RELEASE})) == []


def test_non_earnings_preview_untouched():
    # 실적이 아닌 예고(지표·FOMC)는 이 게이트 대상이 아니다(§29 validate_event_tense가 맡는다).
    items = [{"text": "FOMC 결과 발표 앞두고 관망 → 지수 혼조", "ticker": ""}]
    assert fn._drop_preview_after_release(items, NOW, release_fn=_release({})) == items


def test_lookup_failure_fails_open():
    items = [{"text": INCIDENT, "ticker": "MU"}]
    assert fn._drop_preview_after_release(items, NOW, release_fn=_release({})) == items


def test_only_subject_ticker_counts():
    # 영향 절의 종목(AMD)이 방금 실적을 냈어도, 주어(NVDA)의 예고는 건드리지 않는다(§31).
    items = [{"text": "엔비디아 실적 발표 앞두고 → AMD 등 반도체 관망", "ticker": "NVDA,AMD"}]
    rel = {"AMD": NOW - timedelta(hours=10), "NVDA": NOW - timedelta(days=60)}
    assert fn._drop_preview_after_release(items, NOW, release_fn=_release(rel)) == items


def test_preserves_string_shape():
    items = ["뉴욕증시 혼조 → 나스닥만 상승"]
    assert fn._drop_preview_after_release(items, NOW, release_fn=_release({})) == items


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
