# 미국 이벤트 시각 표기('오늘/내일 새벽')를 KST 기준으로 고치는지 — 2026-10-28 FOMC 실사고 리플레이
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import event_when as ew
import validate_analysis as va
import call_claude as cc

CAL = {"today": [], "upcoming": [
    {"title": "FOMC Statement", "country": "USD", "date_kst": "2026-10-29 03:00 KST"},
    {"title": "Federal Funds Rate", "country": "USD", "date_kst": "2026-10-29 03:00 KST"},
    {"title": "Advance GDP q/q", "country": "USD", "date_kst": "2026-10-29 21:30 KST"},
    {"title": "BOJ Policy Rate", "country": "JPY", "date_kst": "2026-10-30 12:00 KST"},
]}
TODAY = date(2026, 10, 28)
EVS = ew.us_events(CAL)


def test_incident_sentence_becomes_tomorrow_dawn():
    s = "오늘 새벽 FOMC 결과 발표(기준금리 동결 전망, 예상 <b>4.00%</b>)가 예정돼 있어요 — 발표 전까지는 관망 심리가 상단을 누를 수 있어요."
    assert ew.fix_day_words(s, EVS, TODAY).startswith("내일 새벽 FOMC 결과 발표")


def test_correct_and_unrelated_words_are_kept():
    assert ew.fix_day_words("내일 새벽 FOMC를 봐요.", EVS, TODAY) == "내일 새벽 FOMC를 봐요."
    assert ew.fix_day_words("오늘 새벽 엔비디아가 올랐어요.", EVS, TODAY) == "오늘 새벽 엔비디아가 올랐어요."
    assert ew.fix_day_words("오늘 밤 FOMC 결과가 나와요.", EVS, TODAY) == "오늘 밤 FOMC 결과가 나와요."   # 내일 새벽 3시를 '오늘 밤'이라 부르는 건 자연스럽다


def test_evening_event_day_is_fixed_and_nearest_event_wins():
    assert ew.fix_day_words("오늘 밤 GDP 발표와 내일 새벽 FOMC를 봐요.", EVS, TODAY) == "내일 밤 GDP 발표와 내일 새벽 FOMC를 봐요."


def test_released_today_event_stays_today():
    cal = {"today": [{"title": "FOMC Statement", "country": "USD", "date_kst": "2026-10-28 03:00 KST", "status": "released"}]}
    assert ew.fix_day_words("오늘 새벽 FOMC는 동결했어요.", ew.us_events(cal), TODAY) == "오늘 새벽 FOMC는 동결했어요."


def test_non_us_events_are_ignored_and_labels():
    assert all(e["title"] != "BOJ Policy Rate" for e in EVS)
    assert ew.when_label("2026-10-29 03:00 KST", TODAY) == "내일 새벽 3시"
    assert ew.when_label("2026-10-29 21:30 KST", TODAY) == "내일 밤 9시 30분"
    assert ew.when_label("2026-11-02 03:00 KST", TODAY) == "11/2(월) 새벽 3시"


def test_gate_corrects_nested_outlook(monkeypatch):
    import datetime as _d

    class _Fixed(_d.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 28, 7, 25, tzinfo=tz)
    monkeypatch.setattr(_d, "datetime", _Fixed)
    a = {"todays_view": {"outlook": [{"tag": "event", "text": "오늘 새벽 FOMC 결과 발표가 예정돼 있어요."}]}}
    corrections = []
    assert va.fix_event_day_words(a, CAL, corrections) == 1
    assert a["todays_view"]["outlook"][0]["text"] == "내일 새벽 FOMC 결과 발표가 예정돼 있어요."
    assert corrections


def test_prompt_directive_lists_korean_time():
    d = cc._event_when_directive("2026-10-28", {"economic_calendar": CAL})
    assert "FOMC Statement (2026-10-29 03:00 KST) → '내일 새벽 3시'" in d
    assert "BOJ" not in d
    assert cc._event_when_directive("2026-10-28", {"economic_calendar": {}}) == ""
