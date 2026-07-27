# 미국 픽 실측이 프리마켓 실체결가를 기준으로 주입되는지 검증하는 테스트.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_analysis import _closes_to_realdata  # noqa: E402

# 오래된→최신. 마지막이 금요일(7/24) 종가.
CLOSES = [900.0] * 198 + [990.21, 920.95]


def test_without_live_uses_last_session():
    """live_price 없으면 기존대로 직전 완료 세션 등락률(코스피 아침 경로)."""
    r = _closes_to_realdata(CLOSES, ndigits=4)
    assert r["price"] == 920.95
    assert round(r["change_pct"], 2) == -6.99


def test_live_price_rebases_to_last_close():
    """실사고(MU): 프리마켓 940.24는 금요일 종가 920.95 대비 +2.09%로 나와야 한다.

    금요일 등락(-6.99%)을 그대로 싣거나, 목요일 종가(990.21) 대비로 계산하면 안 된다.
    """
    r = _closes_to_realdata(CLOSES, ndigits=4, live_price=940.24)
    assert r["price"] == 940.24
    assert round(r["change_pct"], 2) == 2.09, r["change_pct"]


def test_live_price_appended_to_sparkline():
    """스파크라인 마지막 점도 프리마켓 가격이어야 한다(길이 유지)."""
    base = _closes_to_realdata(CLOSES, ndigits=4)
    r = _closes_to_realdata(CLOSES, ndigits=4, live_price=940.24)
    assert len(r["sparkline"]) == len(base["sparkline"]) == 20
    assert r["sparkline"][-1] == 940.24   # 프리마켓 점이 맨 뒤에 붙고
    assert r["sparkline"][-2] == 920.95   # 금요일 종가가 그 앞으로 밀린다
    assert r["sparkline"][-3] == 990.21


def test_ma_distance_uses_live_price():
    """MA 이격도 프리마켓 가격 기준으로 재계산된다."""
    r = _closes_to_realdata(CLOSES, ndigits=4, live_price=940.24)
    base = _closes_to_realdata(CLOSES, ndigits=4)
    assert r["ma20_dist_pct"] > base["ma20_dist_pct"]
    assert r["ma200_dist_pct"] > base["ma200_dist_pct"]


def test_live_price_none_is_noop():
    """live_price=None은 기존 동작과 완전히 동일해야 한다(회귀 방지)."""
    assert _closes_to_realdata(CLOSES, 4, live_price=None) == _closes_to_realdata(CLOSES, 4)


def test_insufficient_data_still_errors():
    assert "error" in _closes_to_realdata([100.0], 4, live_price=101.0)


if __name__ == "__main__":
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            fn_()
            print(f"✅ {name}")
    print("모든 테스트 통과")
