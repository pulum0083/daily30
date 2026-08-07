# 국면 판정 코어 테스트 — 네트워크 없이 순수 함수만 검증한다.
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from market_regime_core import basket_cum  # noqa: E402


def test_basket_cum_simple_average():
    """구성 종목 누적수익률의 단순평균. 시총가중 아님."""
    dates = ["d1", "d2", "d3"]
    closes = {"A": {"d1": 100, "d2": 110, "d3": 120},
              "B": {"d1": 100, "d2": 100, "d3": 100}}
    cum, n = basket_cum(["A", "B"], closes, dates)
    assert n == 2
    assert cum[0] == 0.0
    assert cum[2] == 10.0          # (+20% + 0%) / 2


def test_basket_cum_excludes_ticker_missing_at_window_start():
    """창 시작에 없던 종목은 평균에서 제외한다 — DRAM(2026-04-02 상장) 케이스."""
    dates = ["d1", "d2"]
    closes = {"A": {"d1": 100, "d2": 120},
              "LATE": {"d2": 50}}          # d1에 없음
    cum, n = basket_cum(["A", "LATE"], closes, dates)
    assert n == 1
    assert cum[1] == 20.0                  # LATE는 통째로 빠짐


def test_basket_cum_forward_fills_missing_mid_series():
    """중간 결측(한국 휴장일)은 직전 종가로 채운다."""
    dates = ["d1", "d2", "d3"]
    closes = {"KR": {"d1": 100, "d3": 110}}   # d2 없음
    cum, n = basket_cum(["KR"], closes, dates)
    assert cum[1] == 0.0                      # d1 종가 유지
    assert cum[2] == 10.0


def test_basket_cum_returns_none_when_no_member_usable():
    dates = ["d1", "d2"]
    closes = {"LATE": {"d2": 50}}
    cum, n = basket_cum(["LATE"], closes, dates)
    assert cum is None and n == 0


def test_basket_cum_empty_dates_returns_none():
    """빈 창은 크래시가 아니라 (None, 0) — 다른 계산 불가 경로와 동작을 맞춘다."""
    cum, n = basket_cum(["A"], {"A": {"d1": 100}}, [])
    assert cum is None and n == 0


def test_basket_cum_treats_nan_as_missing():
    """NaN 종가는 없는 데이터다. 조용히 평균에 섞이면 바스켓 전체가 NaN이 된다(§0)."""
    nan = float("nan")
    dates = ["d1", "d2", "d3"]
    closes = {"A": {"d1": 100, "d2": nan, "d3": 120}}
    cum, n = basket_cum(["A"], closes, dates)
    assert n == 1
    assert cum[1] == 0.0      # NaN 대신 직전 종가(d1) 사용
    assert cum[2] == 20.0
    assert all(v == v for v in cum), f"NaN이 남아있다: {cum}"


from market_regime_core import daily_frames  # noqa: E402


def test_daily_frames_gap_from_running_peak():
    """gap은 '그 시점까지의 최고' 대비 거리다. 미래를 보지 않는다."""
    cums = {"a": [0.0, 10.0, 5.0]}
    fr = daily_frames(cums)
    assert fr[0]["a"]["gap"] == 0.0     # 첫날은 자기가 정점
    assert fr[1]["a"]["gap"] == 0.0     # 신고점
    assert fr[2]["a"]["gap"] == -5.0    # 정점 10에서 5 내려옴


def test_daily_frames_flags():
    cums = {"cooled": [0.0, 30.0, 10.0], "high": [0.0, 1.0, 2.0]}
    fr = daily_frames(cums)
    last = fr[2]
    assert last["cooled"]["is_cooled"] is True    # -20 <= -15
    assert last["cooled"]["is_high"] is False
    assert last["high"]["is_high"] is True        # gap 0 >= -3
    assert last["high"]["is_cooled"] is False


def test_daily_frames_threshold_boundaries():
    """경계값은 포함이다 — 정확히 -15.0이면 식음, -3.0이면 신고점."""
    fr = daily_frames({"x": [0.0, 100.0, 85.0]})   # gap = -15.0
    assert fr[2]["x"]["is_cooled"] is True
    fr2 = daily_frames({"y": [0.0, 100.0, 97.0]})  # gap = -3.0
    assert fr2[2]["y"]["is_high"] is True


def test_daily_frames_rejects_mismatched_lengths():
    """길이가 다른 시계열은 조용히 자르거나 죽지 않고 명시적으로 실패한다.
    딕셔너리 키 순서에 따라 크래시하거나 데이터가 사라지던 문제의 회귀 가드."""
    with pytest.raises(ValueError):
        daily_frames({"a": [0.0, 10.0, 5.0], "b": [0.0, 10.0]})


def test_daily_frames_rejects_nan():
    """NaN은 결측이다. 조용히 통과시키면 그날의 플래그가 '정상'으로 오판된다(§0)."""
    nan = float("nan")
    with pytest.raises(ValueError):
        daily_frames({"a": [0.0, nan, 5.0]})


def test_daily_frames_gap_matches_displayed_value_at_rounding_boundary():
    """gap 표시값과 is_cooled 판정이 같은 값에서 나와야 한다 — 이중 반올림으로 어긋나면 안 된다."""
    fr = daily_frames({"x": [0.0, 100.0, 85.04]})
    last = fr[2]["x"]
    assert last["gap"] == -15.0
    assert last["is_cooled"] is True   # gap이 -15.0으로 보이는데 플래그가 False면 모순
