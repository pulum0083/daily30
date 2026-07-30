# 이미 끝난 경제 이벤트를 예고형으로 서술하면 잡아내는 발행 직전 게이트 테스트 (2026-07-30 실사고).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_analysis as va  # noqa: E402

CAL = {"today": [
    {"title": "Federal Funds Rate", "date_kst": "2026-07-30 03:00 KST", "status": "released"},
    {"title": "FOMC Statement", "date_kst": "2026-07-30 03:00 KST", "status": "released"},
    {"title": "Core PCE Price Index m/m", "date_kst": "2026-07-30 21:30 KST", "status": "upcoming"},
]}


def _kws():
    return va._event_keywords(CAL)


def test_released_and_upcoming_keywords_split():
    rel, up = _kws()
    assert "FOMC" in rel
    assert "PCE" in up and "PCE" not in rel


def test_preview_wording_on_released_event_is_flagged():
    """실사고 원문 — 18시간 전에 끝난 FOMC를 '예정돼 있어요'로 썼다."""
    rel, up = _kws()
    assert va.find_event_tense_violations(
        "오늘 새벽 FOMC 결과와 파월 기자회견이 예정돼 있어요.", rel, up)


def test_waiting_wording_on_released_event_is_flagged():
    rel, up = _kws()
    assert va.find_event_tense_violations("FOMC 결과 발표를 앞두고 관망 심리가 커져요.", rel, up)


def test_result_wording_passes():
    """결과형 서술은 통과한다."""
    rel, up = _kws()
    assert not va.find_event_tense_violations(
        "FOMC는 기준금리를 3.50~3.75%로 동결했어요.", rel, up)


def test_upcoming_event_mentioned_after_released_is_not_flagged():
    """'FOMC 결과 뒤 PCE 발표가 예정'처럼 예고 대상이 upcoming이면 위반이 아니다."""
    rel, up = _kws()
    assert not va.find_event_tense_violations(
        "FOMC 결과가 나온 뒤 PCE 발표가 예정돼 있어요.", rel, up)


def test_preview_wording_far_from_keyword_is_not_flagged():
    """멀리 떨어진 예고 표현까지 끌어오지 않는다 — 오제거 방지."""
    rel, up = _kws()
    assert not va.find_event_tense_violations(
        "FOMC는 동결했어요. 삼성전자 시가 갭을 확인한 뒤 실적 발표가 예정된 종목을 봐요.", rel, up)


def test_list_items_are_removed():
    analysis = {"us_issues": [
        {"title": "FOMC 결과 발표 대기 속 국채금리 상승", "body": "긴장감이 높아지고 있어요."},
        {"title": "메모리 반등", "body": "저가 매수세가 유입돼요."},
    ]}
    corrections, warnings, blocks = [], [], []
    va.validate_event_tense(analysis, CAL, corrections, warnings, blocks)
    assert len(analysis["us_issues"]) == 1
    assert analysis["us_issues"][0]["title"] == "메모리 반등"
    assert corrections and not blocks


def test_scalar_prose_blocks_publication():
    """산문은 자동 교정이 불가능하므로 발행을 막는다(§28 선례)."""
    analysis = {"sc_footer": "오늘 밤 FOMC 결과 발표가 예정돼 있어요."}
    corrections, warnings, blocks = [], [], []
    va.validate_event_tense(analysis, CAL, corrections, warnings, blocks)
    assert blocks


def test_no_released_event_is_a_noop():
    """끝난 이벤트가 없으면 아무것도 하지 않는다."""
    analysis = {"sc_footer": "FOMC 발표가 예정돼 있어요."}
    corrections, warnings, blocks = [], [], []
    va.validate_event_tense(analysis, {"today": [
        {"title": "FOMC Statement", "status": "upcoming"}]}, corrections, warnings, blocks)
    assert not blocks and not corrections


def test_missing_calendar_is_safe():
    corrections, warnings, blocks = [], [], []
    va.validate_event_tense({"sc_footer": "FOMC 예정"}, None, corrections, warnings, blocks)
    va.validate_event_tense({"sc_footer": "FOMC 예정"}, {}, corrections, warnings, blocks)
    assert not blocks


# ── 실사고 원문 리플레이 — 이벤트명과 예고 표현이 수십 자 떨어져 있다 ──────────

def test_real_us_issue_card_is_flagged():
    """미국 브리핑 1번 이슈 — 제목의 FOMC와 본문의 '유력하지만'이 멀리 떨어져 있었다."""
    rel, up = _kws()
    card = ('{"title": "오늘 새벽 FOMC 결정 + 파월 기자회견 — 금리 경로의 분수령", '
            '"body": "기준금리 동결이 유력하지만 시장은 숫자보다 파월의 말투에 더 집중하고 있어요."}')
    assert va.find_event_tense_violations(card, rel, up)


def test_real_kospi_outlook_sentence_is_flagged():
    rel, up = _kws()
    assert va.find_event_tense_violations(
        "오늘 새벽 FOMC 결과와 파월 기자회견이 예정돼 있어요 — 금리는 동결 전망이지만 코멘트가 관건이에요.",
        rel, up)


def test_nested_prose_blocks_publication():
    """todays_view.outlook처럼 중첩된 산문도 차단 대상이다."""
    analysis = {"todays_view": {"outlook": [
        {"tag": "event", "text": "오늘 새벽 FOMC 결과와 파월 기자회견이 예정돼 있어요."}]}}
    corrections, warnings, blocks = [], [], []
    va.validate_event_tense(analysis, CAL, corrections, warnings, blocks)
    assert blocks


def test_corrected_text_passes():
    """정정본은 통과한다 — 게이트가 결과형 서술까지 막지 않는다."""
    rel, up = _kws()
    for ok in [
        "오늘 새벽 FOMC는 기준금리를 3.50~3.75%로 동결했어요(9-3 표결).",
        "FOMC 동결에도 국채금리 상승 — 매파적 점도표",
        "연준은 기준금리를 3.50~3.75%로 동결했지만 표결이 9-3으로 갈렸어요.",
    ]:
        assert not va.find_event_tense_violations(ok, rel, up), ok
