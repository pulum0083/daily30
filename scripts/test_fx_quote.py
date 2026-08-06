# 원/달러 등락률 수집 테스트 — 등락률을 못 구하는 소스가 0.0을 지어내던 사고 검증.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_data import (  # noqa: E402
    _fx_from_fawazahmed0,
    _fx_from_manana,
    _fx_from_naver_rows,
    _fx_from_price_only,
)


# --- 네이버 모바일 (유일하게 실측 전일 종가를 주는 소스) ---

def test_naver_rows_compute_real_change():
    """일별 종가 2건이면 실제 등락률을 계산한다."""
    rows = [{"closePrice": "1,424.10"}, {"closePrice": "1,423.50"}]
    q = _fx_from_naver_rows(rows)
    assert q["price"] == 1424.10
    assert q["change_pct"] == 0.04
    assert q["change_abs"] == 0.60


def test_naver_rows_matches_naver_own_ratio():
    """2026-08-06 실데이터. 네이버가 스스로 준 fluctuationsRatio(+0.04)와 일치해야 한다."""
    rows = [
        {"closePrice": "1,424.10", "fluctuationsRatio": "0.04"},
        {"closePrice": "1,423.50", "fluctuationsRatio": "-0.52"},
    ]
    q = _fx_from_naver_rows(rows)
    assert q["change_pct"] == float(rows[0]["fluctuationsRatio"])


def test_naver_rows_negative_change():
    """하락도 부호가 유지된다."""
    q = _fx_from_naver_rows([{"closePrice": "1,423.50"}, {"closePrice": "1,431.00"}])
    assert q["change_pct"] == -0.52
    assert q["change_abs"] == -7.50


def test_naver_single_row_has_no_change():
    """행이 1건이면 전일 종가가 없다 — 0.0을 지어내지 않고 None."""
    q = _fx_from_naver_rows([{"closePrice": "1,424.10"}])
    assert q["price"] == 1424.10
    assert q["change_pct"] is None
    assert q["change_abs"] is None


def test_naver_empty_rows_yields_nothing():
    assert _fx_from_naver_rows([]) == {}


# --- manana.kr (현재 응답이 1건이라 대부분 등락률을 못 준다) ---

def test_manana_single_row_has_no_change():
    """2026-08-06 실응답: 행이 1건이다. 이때 0.0을 채우면 '보합'이라는 거짓 주장이 된다."""
    q = _fx_from_manana([{"rate": 1423.8, "date": "2026-08-06 19:00:11"}])
    assert q["price"] == 1423.8
    assert q["change_pct"] is None


def test_manana_two_rows_compute_change():
    q = _fx_from_manana([{"rate": 1424.1}, {"rate": 1423.5}])
    assert q["change_pct"] == 0.04


# --- 가격만 주는 소스 (토스·fawazahmed0) ---

def test_price_only_never_fabricates_zero():
    """토스 /exchange-rate는 midRate만 준다 — 등락률은 만들 수 없으므로 None."""
    q = _fx_from_price_only(1427.25)
    assert q == {"price": 1427.25, "change_pct": None, "change_abs": None}


def test_fawazahmed0_has_no_change():
    q = _fx_from_fawazahmed0({"usd": {"krw": 1418.63761396}})
    assert q["price"] == 1418.64
    assert q["change_pct"] is None


def test_fawazahmed0_missing_key():
    assert _fx_from_fawazahmed0({"usd": {}}) == {}


# --- 회귀: 어떤 소스도 0.0을 지어내지 않는다 ---

def test_no_source_fabricates_zero_change():
    """2026-08-06 사고: 발행된 마감 브리핑 12건 전부가 '▲ +0.00%'였다.
    등락률을 모르는 소스는 전부 None을 반환해야 한다 — 0.0은 '보합'이라는 틀린 주장이다."""
    quotes = [
        _fx_from_price_only(1427.25),
        _fx_from_fawazahmed0({"usd": {"krw": 1418.63}}),
        _fx_from_manana([{"rate": 1423.8}]),
        _fx_from_naver_rows([{"closePrice": "1,424.10"}]),
    ]
    for q in quotes:
        assert q["change_pct"] is None, f"등락률을 지어냈다: {q}"


def test_genuine_flat_stays_zero_not_none():
    """진짜 보합(전일과 동일)은 0.0이다 — None과 구분돼야 한다."""
    q = _fx_from_naver_rows([{"closePrice": "1,424.10"}, {"closePrice": "1,424.10"}])
    assert q["change_pct"] == 0.0
    assert q["change_pct"] is not None
