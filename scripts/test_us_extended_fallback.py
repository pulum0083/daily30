# 야후가 오늘 프리·애프터장 봉을 비워 줄 때 네이버 체결가로 대신하는지(2026-11-11 실사고 — 엔비디아 +4.36%가 −5.47%로 보였다)
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_data as fd  # noqa: E402

ET = timezone(timedelta(hours=-5))
NOW = datetime(2026, 11, 11, 5, 20, tzinfo=ET)
NVDA = {"closePrice": "168.89", "fluctuationsRatio": "-5.47", "marketStatus": "CLOSE",
        "overMarketPriceInfo": {"tradingSessionType": "PRE_MARKET", "overMarketStatus": "OPEN",
                                "overPrice": "176.25", "localTradedAt": "2026-11-11T05:17:36-05:00"}}


def test_naver_premarket_quote():
    price, base = fd.naver_extended_quote(NVDA, now=NOW)
    assert (price, base) == (176.25, 168.89)
    assert round((price / base - 1) * 100, 2) == 4.36            # 화면엔 −5.47%(어제 종가 등락)가 나갔다


def test_naver_quote_rejects_closed_stale_and_implausible():
    closed = dict(NVDA, overMarketPriceInfo=dict(NVDA["overMarketPriceInfo"], overMarketStatus="CLOSE"))
    assert fd.naver_extended_quote(closed, now=NOW) is None
    assert fd.naver_extended_quote(NVDA, now=NOW + timedelta(hours=4)) is None      # 3시간 넘은 체결
    wild = dict(NVDA, overMarketPriceInfo=dict(NVDA["overMarketPriceInfo"], overPrice="300"))
    assert fd.naver_extended_quote(wild, now=NOW) is None                          # ±25% 넘으면 데이터 문제
    assert fd.naver_extended_quote({"closePrice": "1"}, now=NOW) is None


def _bars(*ts):
    idx = pd.DatetimeIndex([pd.Timestamp(t) for t in ts])
    return pd.DataFrame({"Close": [1.0] * len(ts)}, index=idx)


def test_yahoo_fresh_needs_todays_bar():
    now = NOW.astimezone(timezone.utc)
    assert fd._yahoo_extended_fresh(_bars("2026-11-11 05:10-05:00"), now=now)
    assert not fd._yahoo_extended_fresh(_bars("2026-11-10 19:59-05:00"), now=now)   # 어제 애프터장 봉
    assert not fd._yahoo_extended_fresh(None, now=now)
    assert not fd._yahoo_extended_fresh(_bars(), now=now)


def test_realtime_price_uses_naver_when_yahoo_empty(monkeypatch):
    monkeypatch.setattr(fd, "_pin_date_for", lambda t: None)
    monkeypatch.setattr(fd, "_yf_history", lambda *a, **k: pd.DataFrame({"Close": []}))
    monkeypatch.setattr(fd, "_naver_us_basic", lambda t: NVDA)
    monkeypatch.setattr(fd, "naver_extended_quote", lambda d, now=None: (176.25, 168.89))
    assert fd._get_realtime_price("NVDA") == (176.25, 168.89)


def test_futures_and_indices_skip_naver():
    assert not fd._is_us_equity("ES=F") and not fd._is_us_equity("^IXIC") and not fd._is_us_equity("005930.KS")
    assert fd._is_us_equity("NVDA")


def test_feed_alert_text_and_recording(monkeypatch):
    fd.FEED_ISSUES.clear()
    monkeypatch.setattr(fd, "_pin_date_for", lambda t: None)
    monkeypatch.setattr(fd, "_yf_history", lambda *a, **k: pd.DataFrame({"Close": []}))
    monkeypatch.setattr(fd, "_naver_us_basic", lambda t: NVDA)
    monkeypatch.setattr(fd, "naver_extended_quote", lambda d, now=None: (176.25, 168.89))
    fd._get_realtime_price("NVDA")
    assert fd.FEED_ISSUES == [{"ticker": "NVDA", "how": "naver"}]
    fd.FEED_ISSUES.append({"ticker": "MU", "how": "missing"})
    msg = fd.feed_alert_text(fd.FEED_ISSUES, "us")
    assert "미국 브리핑" in msg and "네이버 체결가로 대신 1종목: NVDA" in msg and "MU" in msg
    assert fd.feed_alert_text([], "us") == ""
    sent = []
    import send_telegram
    monkeypatch.setattr(send_telegram, "send_admin_alert", lambda m: sent.append(m))
    fd.alert_feed_issues("us")
    assert len(sent) == 1
    fd.FEED_ISSUES.clear()
    fd.alert_feed_issues("us")
    assert len(sent) == 1                                       # 문제가 없으면 보내지 않는다
