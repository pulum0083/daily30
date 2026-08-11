# 미국 브리핑 뉴스 세션 라벨 — RSS 기사가 다루는 세션을 계산·주입하는지 검증 (계획 2.5단계)
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from call_claude import _session_label_directive  # noqa: E402
from fetch_news import _us_news_session  # noqa: E402


# ── 세션 계산 ────────────────────────────────────────────────────────────────

def test_weekday_points_to_previous_trading_day():
    """화요일 브리핑 → 직전 정규장은 월요일."""
    assert _us_news_session(date(2026, 8, 11)) == {
        "date": "2026-08-10", "label": "직전 정규장",
    }


def test_monday_points_back_to_friday():
    """월요일엔 '어제 미국장'이 없다 — 지난 금요일이 직전 정규장이다(§24와 같은 함정)."""
    assert _us_news_session(date(2026, 8, 10))["date"] == "2026-08-07"


def test_skips_us_holiday():
    """미국 공휴일은 건너뛴다. 2026-07-03(독립기념일 대체휴장) → 07-02."""
    assert _us_news_session(date(2026, 7, 6))["date"] == "2026-07-02"


def test_label_is_not_the_kospi_overnight_wording():
    """'간밤'은 코스피 아침 브리핑용 표현이다. 미국 브리핑은 프리마켓에 나가므로 쓰지 않는다."""
    assert "간밤" not in _us_news_session(date(2026, 8, 11))["label"]


# ── 프롬프트 지시문 ──────────────────────────────────────────────────────────

_NEWS = {"news_session": {"date": "2026-08-10", "label": "직전 정규장"}}


def test_us_directive_states_session_and_forbids_present_tense():
    """뉴스가 직전 정규장 것임을 못박고, '지금·프리마켓'으로 쓰지 말라고 지시해야 한다."""
    out = _session_label_directive("2026-08-11", "us", _NEWS)
    assert "2026-08-10" in out
    assert "직전 정규장" in out
    assert "프리마켓" in out


def test_us_directive_empty_without_news_session():
    """gemini 경로엔 news_session이 없다 — 근거 없는 지시를 만들어내지 않는다."""
    assert _session_label_directive("2026-08-11", "us", {"catalysts": []}) == ""
    assert _session_label_directive("2026-08-11", "us", None) == ""


def test_kospi_directive_unaffected():
    """코스피 분기는 기존 '간밤' 로직 그대로 — 미국 문구가 새어들면 안 된다."""
    out = _session_label_directive("2026-08-10", "kospi", _NEWS)
    assert "프리마켓" not in out


def test_close_briefing_gets_nothing():
    """마감 브리핑은 이 지시 대상이 아니다."""
    assert _session_label_directive("2026-08-11", "kospi-close", _NEWS) == ""
