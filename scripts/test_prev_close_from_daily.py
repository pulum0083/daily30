# _prev_close_from_daily 테스트 — fast_info.previous_close 과거 종가 오류 교정 검증.
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from fetch_data import _prev_close_from_daily  # noqa: E402

TZ = "America/New_York"


def _series(values, last_date):
    """마지막 바 날짜가 last_date인 tz-aware 일봉 종가 시리즈."""
    idx = pd.date_range(end=pd.Timestamp(last_date, tz=TZ),
                        periods=len(values), freq="D")
    return pd.Series(values, index=idx)


def test_market_closed_uses_previous_daily_close():
    """장 마감 상태(price == 마지막 종가) → 그 직전 종가가 기준가."""
    closes = _series([170.43, 173.86, 162.96], "2026-07-24")
    assert _prev_close_from_daily(closes, 162.96) == 173.86


def test_real_incident_ewy():
    """2026-07-27 실사고: fast_info prev=172.964였으나 정답은 173.86."""
    closes = _series([172.90, 170.43, 173.86, 162.96], "2026-07-24")
    fixed = _prev_close_from_daily(closes, 162.96)
    assert fixed == 173.86
    assert round((162.96 / fixed - 1) * 100, 2) == -6.27


def _exchange_today():
    """거래소(뉴욕) 현지 날짜 — 서울 날짜와 다를 수 있어 테스트도 거래소 tz로 맞춘다."""
    return pd.Timestamp.now(tz=TZ).date()


def test_live_session_last_bar_is_today():
    """세션 진행 중이고 마지막 일봉이 오늘 바 → 그 직전 종가가 기준가."""
    closes = _series([100.0, 110.0, 105.0], _exchange_today())
    assert _prev_close_from_daily(closes, 104.5) == 110.0


def test_premarket_last_bar_is_prior_session():
    """프리마켓(오늘 바 아직 없음) → 마지막 종가가 곧 기준가."""
    closes = _series([100.0, 110.0, 105.0], _exchange_today() - timedelta(days=1))
    assert _prev_close_from_daily(closes, 107.0) == 105.0


def test_insufficient_or_naive_returns_none():
    """판별 불가하면 None → 호출부가 기존 값을 유지한다."""
    assert _prev_close_from_daily(pd.Series([100.0]), 100.0) is None
    assert _prev_close_from_daily(None, 100.0) is None
    naive = pd.Series([100.0, 105.0],
                      index=pd.date_range(end="2026-07-24", periods=2, freq="D"))
    assert _prev_close_from_daily(naive, 107.0) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("모든 테스트 통과")
