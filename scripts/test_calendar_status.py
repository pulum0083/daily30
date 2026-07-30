# 이미 지난 경제 이벤트를 '오늘 예정'으로 넘기지 않는 캘린더 시각 게이트 테스트 (2026-07-30 실사고).
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_data as fd  # noqa: E402

KST = timezone(timedelta(hours=9))


def _ev(title, kst_iso, impact="High", country="USD"):
    """ForexFactory 원본 이벤트 형태. actual은 이 소스가 절대 채우지 않아 항상 빈 문자열이다."""
    return {"title": title, "country": country, "impact": impact,
            "date": kst_iso, "forecast": "3.75%", "previous": "3.75%", "actual": ""}


def test_past_event_today_is_released():
    """미국 브리핑(21:15 KST) 시점에 그날 03:00 FOMC는 18시간 전에 끝났다."""
    now = datetime(2026, 7, 30, 21, 15, tzinfo=KST)
    out = fd._bucket_calendar_events([_ev("Federal Funds Rate", "2026-07-30T03:00:00+09:00")], now)
    assert out["today"][0]["status"] == "released"


def test_kospi_morning_also_sees_dawn_event_as_released():
    """코스피 아침(07:25)에도 03:00 FOMC는 이미 끝났다 — 두 브리핑 모두 같은 버그를 겪었다."""
    now = datetime(2026, 7, 30, 7, 25, tzinfo=KST)
    out = fd._bucket_calendar_events([_ev("FOMC Statement", "2026-07-30T03:00:00+09:00")], now)
    assert out["today"][0]["status"] == "released"


def test_later_event_today_is_upcoming():
    """같은 날이라도 아직 오지 않은 21:30 지표는 upcoming이다."""
    now = datetime(2026, 7, 30, 21, 15, tzinfo=KST)
    out = fd._bucket_calendar_events([_ev("Core PCE Price Index m/m", "2026-07-30T21:30:00+09:00")], now)
    assert out["today"][0]["status"] == "upcoming"


def test_tomorrow_event_goes_to_upcoming_bucket():
    now = datetime(2026, 7, 30, 21, 15, tzinfo=KST)
    out = fd._bucket_calendar_events(
        [_ev("BOJ Policy Rate", "2026-07-31T11:30:00+09:00", country="JPY")], now)
    assert not out["today"]
    assert out["upcoming"][0]["status"] == "upcoming"


def test_low_impact_and_non_key_country_dropped():
    now = datetime(2026, 7, 30, 21, 15, tzinfo=KST)
    out = fd._bucket_calendar_events([
        _ev("Building Approvals m/m", "2026-07-30T10:30:00+09:00", impact="Low", country="AUD"),
        _ev("Official Bank Rate", "2026-07-30T20:00:00+09:00", country="GBP"),
    ], now)
    assert not out["today"] and not out["upcoming"]


def test_unparseable_date_dropped():
    """날짜 파싱 실패 이벤트는 시제를 판정할 수 없으므로 버린다."""
    now = datetime(2026, 7, 30, 21, 15, tzinfo=KST)
    out = fd._bucket_calendar_events([_ev("Broken", "not-a-date")], now)
    assert not out["today"] and not out["upcoming"]


def test_released_event_keeps_display_fields():
    """시제 판정을 붙여도 기존 표시 필드는 그대로 유지된다."""
    now = datetime(2026, 7, 30, 21, 15, tzinfo=KST)
    ev = fd._bucket_calendar_events(
        [_ev("Federal Funds Rate", "2026-07-30T03:00:00+09:00")], now)["today"][0]
    assert ev["date_kst"] == "2026-07-30 03:00 KST"
    assert ev["date_kst_date"] == "2026-07-30"
    assert ev["forecast"] == "3.75%"
