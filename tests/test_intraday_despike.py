# 장중 5분봉 디스파이크(_despike_intraday) 순수 함수 단위 테스트
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
import fetch_closing_kospi as fc


def test_short_series_unchanged():
    # 3개 미만은 그대로 반환
    assert fc._despike_intraday([100.0, 101.0]) == [100.0, 101.0]


def test_no_spike_preserved():
    # 정상 시계열은 변형되지 않는다 (이웃 대비 1.5% 이내 변동)
    prices = [8600.0, 8620.0, 8610.0, 8635.0, 8650.0]
    assert fc._despike_intraday(prices) == prices


def test_leading_open_spike_removed():
    # 장 시작 첫 봉이 이웃 대비 크게 튀면 이웃값으로 보정
    prices = [8913.79, 8517.76, 8530.0, 8540.0]
    out = fc._despike_intraday(prices)
    assert out[0] == 8517.76          # 첫 봉 스파이크 제거
    assert max(out) < 8913.79         # 가짜 고점 사라짐


def test_interior_spike_averaged():
    # 내부 단일 봉이 양쪽 이웃 대비 같은 방향으로 튀면 이웃 평균으로 대체
    prices = [8600.0, 8605.0, 8800.0, 8610.0, 8615.0]
    out = fc._despike_intraday(prices)
    assert out[2] == round((8605.0 + 8610.0) / 2, 2)


def test_trailing_spike_removed():
    # 마지막 봉 스파이크도 직전 이웃값으로 보정
    prices = [8600.0, 8610.0, 8620.0, 8900.0]
    out = fc._despike_intraday(prices)
    assert out[-1] == 8620.0


def test_legit_trend_not_flattened():
    # 추세적 상승(이웃 대비 1.5% 이내 연속 상승)은 스파이크로 오인하지 않는다
    prices = [8600.0, 8650.0, 8700.0, 8750.0, 8800.0]
    assert fc._despike_intraday(prices) == prices
