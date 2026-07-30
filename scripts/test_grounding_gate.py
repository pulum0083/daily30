# 수집(Gemini)이 검색 대신 학습 지식으로 답했을 때 뉴스 요약을 통째로 폐기하는 게이트 테스트 (2026-07-30 실사고).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn  # noqa: E402

# 2026-07-30 미국 브리핑을 오염시킨 실제 수집 결과 (data/news_summary_us.json)
REAL_INCIDENT = {
    "key_indicators": [
        "오늘 발표될 주요 경제 지표는 예정되어 있지 않으나, 연준 위원의 발언이 예정되어 있어 "
        "금리 인하 시점에 대한 시장의 관심이 집중될 것으로 보입니다.",
        "빅테크 기업들의 개별 실적 발표 및 신제품 출시 관련 뉴스가 시장의 주요 관심사로 부각되고 있습니다.",
    ],
    "catalysts": [
        "C 은행, 예상치 하회하는 순이자마진 발표 → 금융 섹터 전반에 대한 우려감 확산",
        "국제 유가(WTI) 급락, 지정학적 긴장 완화 기대감 반영 → 에너지 섹터 약세",
    ],
    "headlines": ["미국 증시, 빅테크 실적 발표 및 연준 발언 주시하며 관망세"],
}

# 그날 실제로 잡혀 있던 고영향 일정
CAL_WITH_EVENTS = {"today": [
    {"title": "Federal Funds Rate", "date_kst": "2026-07-30 03:00 KST", "status": "released"},
    {"title": "Core PCE Price Index m/m", "date_kst": "2026-07-30 21:30 KST", "status": "upcoming"},
]}

HEALTHY = {
    "key_indicators": ["나스닥은 0.22% 내린 24,876.91에 마감했습니다."],
    "catalysts": [{"date": "2026-07-30", "text": "마이크론 실적 서프라이즈", "ticker": "MU"}],
    "headlines": ["마이크론, 시장 예상 웃도는 분기 실적"],
}


def test_real_incident_is_rejected():
    """실사고 데이터는 신호가 2개 이상이라 폐기 판정된다."""
    signals = fn._grounding_failure_signals(REAL_INCIDENT, CAL_WITH_EVENTS)
    assert len(signals) >= 2, signals
    assert fn._is_grounding_failure(REAL_INCIDENT, CAL_WITH_EVENTS)


def test_catalysts_schema_violation_detected():
    """catalysts가 객체가 아닌 문자열 배열이면 정상 경로를 타지 않았다는 신호다."""
    assert "catalysts_schema_violation" in fn._grounding_failure_signals(REAL_INCIDENT, None)


def test_denying_scheduled_events_detected():
    """캘린더에 고영향 일정이 있는데 '지표 없음'이라고 하면 오늘을 못 본 것이다."""
    assert "denies_scheduled_events" in fn._grounding_failure_signals(REAL_INCIDENT, CAL_WITH_EVENTS)


def test_no_scheduled_events_makes_the_claim_legitimate():
    """실제로 일정이 없는 날의 '지표 없음' 서술은 정상이므로 신호가 아니다."""
    assert "denies_scheduled_events" not in fn._grounding_failure_signals(
        REAL_INCIDENT, {"today": []})


def test_healthy_summary_passes():
    """정상 수집 결과는 폐기되지 않는다."""
    assert fn._grounding_failure_signals(HEALTHY, CAL_WITH_EVENTS) == []
    assert not fn._is_grounding_failure(HEALTHY, CAL_WITH_EVENTS)


def test_single_signal_does_not_reject():
    """신호 1개만으로는 폐기하지 않는다 — 정상 수집의 오제거를 막는다."""
    one = dict(HEALTHY, catalysts=["문자열로만 온 촉매"])
    signals = fn._grounding_failure_signals(one, CAL_WITH_EVENTS)
    assert signals == ["catalysts_schema_violation"]
    assert not fn._is_grounding_failure(one, CAL_WITH_EVENTS)


def test_placeholder_entity_is_a_signal():
    """익명 플레이스홀더 주어도 그라운딩 실패 신호로 함께 센다."""
    data = dict(HEALTHY, headlines=["B사 서비스 출시 지연으로 시간외 급락"])
    assert "placeholder_entities" in fn._grounding_failure_signals(data, CAL_WITH_EVENTS)
