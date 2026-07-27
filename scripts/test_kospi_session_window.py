# 코스피 아침 뉴스 검색의 '시점 기준' 블록 테스트 — 월요일 주말 공백 누락 방지.
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fetch_news as fn  # noqa: E402


def test_monday_labels_friday_not_overnight():
    """월요일엔 직전 미국장이 금요일이므로 '간밤'이 아니다."""
    window, label = fn._kospi_session_window(date(2026, 7, 27))  # 월
    assert label == "지난 금요일"
    assert "2026-07-24(금요일)" in window
    assert "'간밤'·'어젯밤'·'밤사이'라고 쓰지 마라" in window


def test_monday_asks_for_weekend_events():
    """월요일엔 주말 구간 이벤트를 함께 검색하라는 지시가 붙는다."""
    window, _ = fn._kospi_session_window(date(2026, 7, 27))
    assert "주말·휴일이 포함된다" in window
    assert "반드시 함께 검색한다" in window


def test_tuesday_is_overnight_and_omits_weekend_block():
    """화요일은 '간밤'이 맞고, 주말 블록을 붙이지 않는다(불필요한 지시 방지)."""
    window, label = fn._kospi_session_window(date(2026, 7, 28))  # 화
    assert label == "간밤"
    assert "주말·휴일이 포함된다" not in window
    assert "쓰지 마라" not in window


def test_window_always_states_search_range():
    """요일과 무관하게 검색 대상 구간은 항상 명시된다."""
    for d in (date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 31)):
        window, _ = fn._kospi_session_window(d)
        assert "검색 대상 구간" in window


def test_all_prompts_still_format():
    """새 포맷 키를 넣어도 세 프롬프트가 모두 정상 렌더된다."""
    window, label = fn._kospi_session_window(date(2026, 7, 27))
    for briefing_type, prompt in fn.PROMPT_MAP.items():
        out = prompt.format(today="2026-07-27", session_window=window, us_label=label)
        assert out, briefing_type
        # 치환되지 않은 플레이스홀더가 남으면 안 된다
        assert "{session_window}" not in out, briefing_type
        assert "{us_label}" not in out, briefing_type
        assert "{today}" not in out, briefing_type


def test_kospi_prompt_has_no_hardcoded_overnight():
    """'간밤'이 프롬프트에 상수로 남아 있으면 안 된다(§24 재발 방지)."""
    assert "간밤" not in fn.KOSPI_PROMPT
    assert "어제(현지 시각)" not in fn.KOSPI_PROMPT


if __name__ == "__main__":
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            fn_()
            print(f"✅ {name}")
    print("모든 테스트 통과")
