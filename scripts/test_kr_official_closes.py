# 한국 종목 정규장 공식 종가 회귀 테스트 — 애프터장·토스 가격이 종가로 들어가지 않는지(§48)
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kr_official_closes as koc  # noqa: E402

KST = koc.KST

# 2026-09-14 SK하이닉스 실측 — 16:54·17:10 네이버 일봉은 애프터장 가격, 15:30 1분봉이 공식 종가
DAY_ROWS = [
    {"localDate": "20260911", "closePrice": 1812000.0, "accumulatedTradingVolume": 2625165},
    {"localDate": "20260914", "closePrice": 1688000.0, "accumulatedTradingVolume": 3799906},
]
BAR_1530 = [{"localDateTime": "20260914153000", "currentPrice": 1697000.0}]


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch, tmp_path):
    """테스트끼리 공식 종가 저장소를 공유하지 않게 비운다(실제 data/ 파일도 건드리지 않는다)."""
    monkeypatch.setattr(koc, "_cache", {})
    monkeypatch.setattr(koc, "_dirty", False)
    monkeypatch.setattr(koc, "CACHE_PATH", tmp_path / "kr_official_closes.json")


def fake(day_rows=DAY_ROWS, minute=BAR_1530, calls=None):
    def _f(url):
        if calls is not None:
            calls.append(url)
        if "/day?" in url:
            return [dict(r) for r in day_rows]
        if "/minute?" in url:
            if isinstance(minute, Exception):
                raise minute
            return minute
        raise AssertionError(url)
    return _f


def at(hhmm, day="20260914"):
    return datetime.strptime(day + hhmm, "%Y%m%d%H%M").replace(tzinfo=KST)


def test_after_close_today_row_uses_1530_bar():
    rows = koc.official_day_rows("000660", now=at("1710"), fetch=fake())
    assert rows[-1]["closePrice"] == 1697000.0          # 애프터장 1,688,000이 아니라 공식 종가
    assert rows[-1]["accumulatedTradingVolume"] == 3799906  # 다른 필드는 그대로
    assert rows[0]["closePrice"] == 1812000.0             # 과거 봉은 건드리지 않는다


def test_missing_1530_bar_drops_today_instead_of_using_drifted_price():
    rows = koc.official_day_rows("000660", now=at("1710"), fetch=fake(minute=[]))
    assert [r["localDate"] for r in rows] == ["20260911"]
    rows = koc.official_day_rows("000660", now=at("1710"), fetch=fake(minute=OSError("timeout")))
    assert [r["localDate"] for r in rows] == ["20260911"]


def test_intraday_today_row_left_as_is():
    calls = []
    rows = koc.official_day_rows("000660", now=at("1400"), fetch=fake(calls=calls))
    assert rows[-1]["closePrice"] == 1688000.0
    assert not any("/minute?" in u for u in calls)


def test_no_today_row_means_no_minute_lookup():
    calls = []
    rows = koc.official_day_rows("000660", now=at("1000", day="20260913"), fetch=fake(calls=calls))
    assert rows == DAY_ROWS
    assert not any("/minute?" in u for u in calls)


def test_day_fetch_failure_returns_empty():
    def boom(url):
        raise OSError("down")
    assert koc.official_day_rows("000660", now=at("1710"), fetch=boom) == []
    assert koc.official_closes("000660", now=at("1710"), fetch=boom) == []


def test_official_closes_list():
    assert koc.official_closes("000660", now=at("1710"), fetch=fake()) == [1812000.0, 1697000.0]


def test_fetch_kospi_realdata_no_longer_uses_toss(monkeypatch):
    """토스 일봉은 과거 날짜도 공식 종가와 달랐다(9/11 SK하이닉스 토스 1,832,000 vs 공식 1,812,000).
    한국 종목 실측은 토스를 부르지 않고 공식 종가 일봉만 써야 한다."""
    import validate_analysis as va
    import toss_client

    def toss_must_not_be_called(*a, **k):
        raise AssertionError("토스 일봉을 한국 종목 종가로 쓰면 안 된다")
    monkeypatch.setattr(toss_client, "get_candles", toss_must_not_be_called)
    closes = [1800000.0 + i * 1000 for i in range(25)] + [1812000.0, 1697000.0]
    rows = [{"localDate": f"202608{i:02d}", "closePrice": c} for i, c in enumerate(closes, start=1)]
    monkeypatch.setattr(koc, "official_day_rows", lambda code, *a, **k: rows)
    monkeypatch.delenv("DS_PIN_SESSION_DATE", raising=False)
    r = va._fetch_kospi_realdata("000660")
    assert r["price"] == 1697000.0
    assert r["change_pct"] == pytest.approx((1697000 - 1812000) / 1812000 * 100, abs=1e-3)


# 9/14 20:12 실측 — 네이버 일봉 9/14 종가가 20:00 애프터장 가격으로 확정됐다(공식 1,697,000)
PAST_ROWS = [
    {"localDate": "20260911", "closePrice": 1812000.0},
    {"localDate": "20260914", "closePrice": 1683000.0},
    {"localDate": "20260915", "closePrice": 1700000.0},
]


def minute_by_date(prices, calls=None):
    def _f(url):
        if calls is not None:
            calls.append(url)
        if "/day?" in url:
            return [dict(r) for r in PAST_ROWS]
        d = url.split("startDateTime=")[1][:8]
        return [{"localDateTime": f"{d}153000", "currentPrice": prices[d]}] if d in prices else []
    return _f


def test_past_aftermarket_day_uses_1530_bar_not_daily_close():
    calls = []
    rows = koc.official_day_rows("000660", now=at("1700", day="20260915"),
                                 fetch=minute_by_date({"20260914": 1697000.0, "20260915": 1705000.0}, calls))
    assert [r["closePrice"] for r in rows] == [1812000.0, 1697000.0, 1705000.0]
    assert not any("startDateTime=20260911" in u for u in calls)   # 애프터마켓 전 날짜는 일봉 그대로


def test_saved_close_is_used_without_minute_lookup():
    koc._cache = {"000660": {"20260914": 1697000.0}}
    calls = []
    rows = koc.official_day_rows("000660", now=at("1000", day="20260915"),
                                 fetch=minute_by_date({}, calls))
    assert rows[1]["closePrice"] == 1697000.0
    assert not any("/minute?" in u for u in calls)                  # 9/15는 장중이라 조회하지 않는다
    assert rows[2]["closePrice"] == 1700000.0


def test_past_day_without_official_close_is_dropped():
    rows = koc.official_day_rows("000660", now=at("1700", day="20260915"),
                                 fetch=minute_by_date({"20260915": 1705000.0}))
    assert [r["localDate"] for r in rows] == ["20260911", "20260915"]


def test_save_cache_writes_only_new_closes():
    assert koc.save_cache() is False
    koc.official_day_rows("000660", now=at("1700", day="20260915"),
                          fetch=minute_by_date({"20260914": 1697000.0, "20260915": 1705000.0}))
    assert koc.save_cache() is True
    import json
    body = json.loads(koc.CACHE_PATH.read_text(encoding="utf-8"))
    assert body["closes"]["000660"] == {"20260914": 1697000.0, "20260915": 1705000.0}
    assert koc.save_cache() is False
