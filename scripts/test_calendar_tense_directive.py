# 이미 끝난 경제 이벤트를 예고형으로 쓰지 않도록 프롬프트에 시제를 주입하는 지시문 테스트 (2026-07-30 실사고).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc  # noqa: E402

FOMC = {"title": "Federal Funds Rate", "date_kst": "2026-07-30 03:00 KST",
        "forecast": "3.75%", "status": "released"}
PCE = {"title": "Core PCE Price Index m/m", "date_kst": "2026-07-30 21:30 KST",
       "forecast": "0.2%", "status": "upcoming"}


def test_released_event_produces_directive():
    """이미 끝난 이벤트가 있으면 예고형 금지 지시가 주입된다."""
    out = cc._calendar_tense_directive({"economic_calendar": {"today": [FOMC]}})
    assert "Federal Funds Rate" in out
    assert "이미" in out and "예정" in out


def test_upcoming_event_is_listed_separately():
    """아직 안 나온 이벤트는 예고형으로 쓰라고 따로 안내한다."""
    out = cc._calendar_tense_directive({"economic_calendar": {"today": [FOMC, PCE]}})
    released_part, upcoming_part = out.split("아직 발표 전")
    assert "Federal Funds Rate" in released_part
    assert "Core PCE Price Index m/m" in upcoming_part


def test_no_released_event_produces_nothing():
    """끝난 이벤트가 없으면 지시를 주입하지 않는다 — 프롬프트를 불필요하게 늘리지 않는다."""
    assert cc._calendar_tense_directive({"economic_calendar": {"today": [PCE]}}) == ""


def test_empty_or_missing_calendar_is_safe():
    """캘린더 수집이 실패한 날에도 예외 없이 빈 문자열을 돌려준다."""
    assert cc._calendar_tense_directive({}) == ""
    assert cc._calendar_tense_directive({"economic_calendar": {}}) == ""
    assert cc._calendar_tense_directive(None) == ""


def test_directive_forbids_inventing_results():
    """결과 수치를 지어내지 말라는 §0 지시가 함께 들어간다."""
    out = cc._calendar_tense_directive({"economic_calendar": {"today": [FOMC]}})
    assert "뉴스 요약" in out
