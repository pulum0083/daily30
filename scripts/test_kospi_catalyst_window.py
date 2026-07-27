# 코스피 catalysts 날짜 게이트가 주말 공백(월요일)을 삼키지 않는지 검증하는 테스트.
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_news import _catalyst_cutoff, _filter_stale_catalysts  # noqa: E402

MON = date(2026, 7, 27)   # 월요일 — 직전 미국장은 금요일 7/24
TUE = date(2026, 7, 28)   # 화요일 — 직전 미국장은 월요일 7/27


def test_monday_cutoff_reaches_friday():
    """월요일 코스피 브리핑의 검색 창은 금요일 미국장까지 열려 있어야 한다."""
    assert _catalyst_cutoff("kospi", MON) == date(2026, 7, 24)


def test_weekday_cutoff_is_yesterday():
    """평일에는 기존과 동일하게 어제까지."""
    assert _catalyst_cutoff("kospi", TUE) == date(2026, 7, 27)


def test_us_cutoff_unchanged():
    """미국 브리핑은 세션 창 확장 대상이 아니다 — 기존 오늘/어제 유지."""
    assert _catalyst_cutoff("us", MON) == date(2026, 7, 26)
    assert _catalyst_cutoff("kospi-close", MON) == date(2026, 7, 26)


def test_friday_event_survives_on_monday():
    """실사고 방지: 금요일 미국장 사건이 월요일 아침 브리핑에서 살아남아야 한다.

    기존 cutoff(today-1=일요일)로는 금요일 사건이 전부 잘려 월요일 브리핑이 빈다.
    """
    cats = [
        {"date": "2026-07-24", "text": "금요일 미국장 반도체 급락 → 국내 반도체주 하방 압력"},
        {"date": "2026-07-26", "text": "주말 AI 서밋 발표 → 관련주 관심"},
        {"date": "2026-07-20", "text": "지난주 월요일 사건 → 이미 다룸"},
    ]
    kept = _filter_stale_catalysts(cats, MON, cutoff=_catalyst_cutoff("kospi", MON))
    assert len(kept) == 2, kept
    assert "금요일 미국장 반도체 급락" in kept[0]
    assert "주말 AI 서밋" in kept[1]


def test_default_cutoff_backward_compatible():
    """cutoff 인자를 안 주면 기존 동작(today-1) 그대로."""
    cats = [{"date": "2026-07-24", "text": "금요일 사건"}]
    assert _filter_stale_catalysts(cats, MON) == []


def test_undated_still_kept():
    """날짜 미상 항목은 여전히 보존한다(거시 촉매 보호)."""
    cats = [{"text": "유가 급락 → 정유주 약세"}]
    assert _filter_stale_catalysts(cats, MON, cutoff=date(2026, 7, 24)) == [
        "유가 급락 → 정유주 약세"
    ]


if __name__ == "__main__":
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            fn_()
            print(f"✅ {name}")
    print("모든 테스트 통과")
