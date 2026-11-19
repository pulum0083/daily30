# 장 시간이 바뀐 날(2026-11-19 수능일 10:00~16:30) — 15:30 장중 봉을 종가로 집지 않는지
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_closing_kospi as fc  # noqa: E402
import investor_flow as inv  # noqa: E402
import kr_official_closes as ko  # noqa: E402

D = "20261119"


def _bar(hhmm, price, vol=10, d=D):
    return {"localDateTime": f"{d}{hhmm}00", "currentPrice": price, "accumulatedTradingVolume": vol}


def test_session_hours():
    assert ko.session_hours(D) == ("1000", "1630", "1639")
    assert ko.session_hours("20261120") == ("0900", "1530", "1539")


def test_closing_bar_skips_midsession_1530():
    bars = [_bar("1530", 100), _bar("1629", 101), _bar("1630", 102), _bar("1645", 103)]
    assert ko.closing_bar(bars, D)["currentPrice"] == 102
    assert ko.closing_bar([_bar("1530", 100, d="20261120")], "20261120")["currentPrice"] == 100


def test_regular_session_requests_until_1639_and_sums_volume():
    urls = []

    def fetch(url):
        urls.append(url)
        return [_bar("1000", 99, 5), _bar("1530", 100, 7), _bar("1630", 102, 3), _bar("1700", 104, 50)]
    s = ko.regular_session("005930", D, fetch=fetch)
    assert urls[0].endswith(f"{D}0900&endDateTime={D}1639")
    assert s == {"close": 102.0, "volume": 15}
    urls.clear()
    ko.regular_close("005930", D, fetch=lambda u: urls.append(u) or [])
    assert f"startDateTime={D}1630&endDateTime={D}1639" in urls[0]


def test_today_before_shifted_close_is_intraday():
    tz = ko.KST
    assert ko.official_today("005930", now=datetime(2026, 11, 19, 16, 20, tzinfo=tz), fetch=lambda u: []) is None
    assert ko.last_closed_session(datetime(2026, 11, 19, 16, 0, tzinfo=tz)) == "20261118"
    assert ko.last_closed_session(datetime(2026, 11, 19, 17, 25, tzinfo=tz)) == D


def test_investor_window_shifts():
    assert inv.regular_window(D) == ("1631", "1640")
    assert inv.regular_window("20261120") == ("1531", "1540")


def test_close_job_skips_vs_close_and_list_prices():
    tz = ko.KST
    called = []
    assert fc.fetch_vs_close(now=datetime(2026, 11, 19, 17, 25, tzinfo=tz), fetch=lambda *a, **k: called.append(1)) == {}
    assert not called
    assert fc.list_prices_regular(datetime(2026, 11, 19, 16, 45, tzinfo=tz))       # 16:30 마감 + 30분까지는 정규장 값
    assert not fc.list_prices_regular(datetime(2026, 11, 19, 17, 25, tzinfo=tz))
    assert not fc.list_prices_regular(datetime(2026, 11, 20, 16, 5, tzinfo=tz))


def test_intraday_uses_naver_minutes_until_shifted_close(monkeypatch):
    tz = ko.KST
    urls = []

    def fetch(url):
        urls.append(url)
        return [{"localDateTime": f"{D}{h:02d}{m:02d}00", "currentPrice": 5000 + h + m / 100}
                for h in range(10, 17) for m in range(60) if "1000" <= f"{h:02d}{m:02d}" <= "1620"]
    r = fc.fetch_intraday_kospi(now=datetime(2026, 11, 19, 17, 30, tzinfo=tz), fetch=fetch)
    assert f"startDateTime={D}1000&endDateTime={D}1620" in urls[0]
    assert len(r["prices"]) == 77 and r["prices"][-1] == 5016.2          # 16:20까지 — 야후처럼 14:55에서 끊기지 않는다
    monkeypatch.setattr(fc, "_intraday_yahoo", lambda now: [1.0, 2.0])
    assert fc.fetch_intraday_kospi(now=datetime(2026, 11, 19, 17, 30, tzinfo=tz), fetch=lambda u: [])["prices"] == [1.0, 2.0]


def test_intraday_axis_follows_session():
    import sections_close as sc
    assert sc.intraday_axis("2026-11-18") == ["09:00", "10:30", "12:00", "13:30", "15:20"]
    assert sc.intraday_axis("2026-11-19") == ["10:00", "11:30", "13:00", "14:30", "16:20"]
