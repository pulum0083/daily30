# generate_html.build_overnight_bridge 단위 테스트 (네트워크 없음)
"""실행: python3 -m pytest scripts/test_build_overnight_bridge.py -v"""
import generate_html as g


def _row(**overrides):
    row = {
        "sector": "반도체",
        "us_label": "엔비디아·AMD",
        "us_change": 8.5,
        "kr_label": "삼성전자·SK하이닉스",
        "kr_change": 28.4,
        "gap_pp": 19.9,
        "kr_session_date": "2026-07-31",
    }
    row.update(overrides)
    return row


def test_positive_gap_is_seonbanyeong_with_up_classes():
    result = g.build_overnight_bridge({"overnight_bridge": [_row()]})
    row = result["overnight_bridge"][0]

    assert row["sector"] == "반도체"
    assert row["us_label"] == "엔비디아·AMD"
    assert row["kr_label"] == "삼성전자·SK하이닉스"
    assert row["us_change_fmt"] == "+8.50%"
    assert row["kr_change_fmt"] == "+28.40%"
    assert row["us_cls"] == "up"
    assert row["kr_cls"] == "up"
    assert row["gap_fmt"] == "+19.9%p"
    assert row["gap_cls"] == "up"
    assert row["gap_word"] == "선반영"


def test_negative_gap_is_mibanyeong_with_dn_classes():
    row = _row(us_change=5.0, kr_change=-3.2, gap_pp=-8.2)
    result = g.build_overnight_bridge({"overnight_bridge": [row]})
    out = result["overnight_bridge"][0]

    assert out["us_change_fmt"] == "+5.00%"
    assert out["kr_change_fmt"] == "-3.20%"
    assert out["us_cls"] == "up"
    assert out["kr_cls"] == "dn"
    assert out["gap_fmt"] == "-8.2%p"
    assert out["gap_cls"] == "dn"
    assert out["gap_word"] == "미반영"


def test_exact_zero_gap_is_dongjo_with_neutral_class():
    row = _row(us_change=4.0, kr_change=4.0, gap_pp=0.0)
    result = g.build_overnight_bridge({"overnight_bridge": [row]})
    out = result["overnight_bridge"][0]

    assert out["gap_fmt"] == "+0.0%p"
    assert out["gap_cls"] == ""
    assert out["gap_word"] == "동조"


def test_us_change_exactly_zero_is_up_boundary():
    row = _row(us_change=0.0)
    result = g.build_overnight_bridge({"overnight_bridge": [row]})
    out = result["overnight_bridge"][0]

    assert out["us_change_fmt"] == "+0.00%"
    assert out["us_cls"] == "up"


def test_none_value_returns_empty_result():
    result = g.build_overnight_bridge({"overnight_bridge": None})

    assert result["overnight_bridge"] == []
    assert result["overnight_bridge_date"] == ""


def test_missing_key_returns_empty_result():
    result = g.build_overnight_bridge({})

    assert result["overnight_bridge"] == []
    assert result["overnight_bridge_date"] == ""


def test_session_date_passthrough():
    result = g.build_overnight_bridge({"overnight_bridge": [_row(kr_session_date="2026-07-31")]})

    assert result["overnight_bridge_date"] == "2026-07-31"
