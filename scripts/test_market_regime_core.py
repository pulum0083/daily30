# 국면 판정 코어 테스트 — 네트워크 없이 순수 함수만 검증한다.
import sys
from pathlib import Path

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
