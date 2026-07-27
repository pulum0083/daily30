# 프리마켓·애프터마켓 중 실제 연장시간대 가격을 쓰는지 검증하는 테스트.
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from fetch_data import _extended_hours_price  # noqa: E402

ET = timezone(timedelta(hours=-4))  # 미국 동부 서머타임


def _series(points):
    """(ET naive datetime, price) 목록을 tz-aware Close 프레임으로."""
    idx = pd.DatetimeIndex([p[0].replace(tzinfo=ET) for p in points])
    return pd.DataFrame({"Close": [p[1] for p in points]}, index=idx)


def _et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def test_premarket_beats_stale_fast_info():
    """실사고(2026-07-27 MU): fast_info는 금요일 종가, prepost엔 월요일 프리마켓이 있다."""
    bars = _series([
        (datetime(2026, 7, 24, 15, 55), 920.95),   # 금요일 정규장 마지막
        (datetime(2026, 7, 27, 8, 30), 935.10),    # 월요일 프리마켓
        (datetime(2026, 7, 27, 9, 2), 938.18),
    ])
    got = _extended_hours_price(bars, fast_last=920.95, now=_et(2026, 7, 27, 9, 5))
    assert got == 938.18, got


def test_value_mismatch_still_detected():
    """fast_info 값이 어떤 봉과도 일치하지 않아도(공식 종가 ≠ 봉 종가) 잡아낸다.

    값 매칭 방식이 실측 10종목 중 4종목에서 놓쳤던 케이스.
    """
    bars = _series([
        (datetime(2026, 7, 24, 15, 55), 920.87),   # 봉 종가 (공식 종가 920.95와 미세 차이)
        (datetime(2026, 7, 27, 9, 2), 938.18),
    ])
    got = _extended_hours_price(bars, fast_last=920.95, now=_et(2026, 7, 27, 9, 5))
    assert got == 938.18, got


def test_regular_session_price_kept():
    """정규장 중이면 intraday 마지막 바가 곧 현재가다."""
    bars = _series([
        (datetime(2026, 7, 27, 10, 0), 930.00),
        (datetime(2026, 7, 27, 11, 30), 941.25),
    ])
    assert _extended_hours_price(bars, 941.25, now=_et(2026, 7, 27, 11, 32)) == 941.25


def test_afterhours_price_used():
    """장 마감 후 애프터마켓 체결도 최신 가격으로 인정한다."""
    bars = _series([
        (datetime(2026, 7, 27, 15, 58), 500.00),   # 정규장 종가
        (datetime(2026, 7, 27, 17, 30), 512.40),   # 애프터마켓
    ])
    assert _extended_hours_price(bars, 500.00, now=_et(2026, 7, 27, 17, 35)) == 512.40


def test_weekend_stale_intraday_rejected():
    """주말이라 마지막 체결이 이틀 전이면 fast_info를 유지한다(fail-open)."""
    bars = _series([(datetime(2026, 7, 24, 15, 55), 920.95)])
    got = _extended_hours_price(bars, fast_last=930.00, now=_et(2026, 7, 26, 12, 0))
    assert got == 930.00, got


def test_empty_and_none_fall_back():
    """데이터가 없으면 fast_info 값을 그대로 돌려준다 — fail-open."""
    assert _extended_hours_price(pd.DataFrame(), 100.0, now=_et(2026, 7, 27, 9, 0)) == 100.0
    assert _extended_hours_price(None, 100.0, now=_et(2026, 7, 27, 9, 0)) == 100.0


def test_no_fast_last_uses_latest_bar():
    """fast_info 자체가 없으면 intraday 마지막 바를 쓴다."""
    bars = _series([(datetime(2026, 7, 27, 8, 30), 935.10)])
    assert _extended_hours_price(bars, None, now=_et(2026, 7, 27, 8, 35)) == 935.10


# ── 선물 롤오버 가드가 개별주 프리마켓 급등락을 덮지 않는지 ────────────────────
from fetch_data import _is_futures_like  # noqa: E402


def test_rollover_guard_scope():
    """롤오버 가드는 선물·지수·금리에만 적용된다 — 개별주엔 적용 금지.

    2026-07-27: XOM이 프리마켓 -3.19%였는데 가드가 정규장 종가로 되돌려 +4.15%로
    부호까지 뒤집었다. 가드가 쓰는 1시간봉은 prepost를 포함하지 않아, 연장시간대
    실체결가를 '롤오버 갭'으로 오인한다.
    """
    for t in ("CL=F", "BZ=F", "GC=F", "NQ=F", "^TNX", "^IXIC", "^SOX"):
        assert _is_futures_like(t), t
    for t in ("XOM", "CVX", "MU", "AAPL", "BRK-B", "SMH", "EWY"):
        assert not _is_futures_like(t), t


if __name__ == "__main__":
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            fn_()
            print(f"✅ {name}")
    print("모든 테스트 통과")
