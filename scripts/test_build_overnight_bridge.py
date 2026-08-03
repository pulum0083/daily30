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
    # _row 기본값(2026-07-31)과 다른 값을 넣어야 패스스루가 실제로 값을 옮기는지 검증된다 —
    # 기본값과 같은 값을 넣으면 하드코딩된 리터럴을 반환해도 테스트가 통과해버린다.
    result = g.build_overnight_bridge({"overnight_bridge": [_row(kr_session_date="2026-08-01")]})

    assert result["overnight_bridge_date"] == "2026-08-01"


# ── Important 1: 행 하나가 깨져 있어도 예외 없이 그 행만 건너뛴다 ────────────────


def test_row_with_none_numeric_field_is_skipped_not_raised():
    good = _row()
    bad = _row(sector="깨진섹터", us_change=None)
    result = g.build_overnight_bridge({"overnight_bridge": [bad, good]})

    sectors = [row["sector"] for row in result["overnight_bridge"]]
    assert sectors == ["반도체"]


def test_row_with_string_numeric_field_is_skipped_not_raised():
    good = _row()
    bad = _row(sector="깨진섹터", us_change="8.5")
    result = g.build_overnight_bridge({"overnight_bridge": [bad, good]})

    sectors = [row["sector"] for row in result["overnight_bridge"]]
    assert sectors == ["반도체"]


def test_non_dict_row_is_skipped_not_raised():
    good = _row()
    result = g.build_overnight_bridge({"overnight_bridge": ["not-a-dict", good]})

    sectors = [row["sector"] for row in result["overnight_bridge"]]
    assert sectors == ["반도체"]


def test_all_rows_malformed_returns_empty_result():
    result = g.build_overnight_bridge({"overnight_bridge": [_row(us_change=None)]})

    assert result == {"overnight_bridge": [], "overnight_bridge_date": ""}


# ── Important 2: 경계값 뮤테이션 고정 ──────────────────────────────────────────


def test_kr_change_exactly_zero_is_up_boundary():
    row = _row(kr_change=0.0)
    result = g.build_overnight_bridge({"overnight_bridge": [row]})
    out = result["overnight_bridge"][0]

    assert out["kr_change_fmt"] == "+0.00%"
    assert out["kr_cls"] == "up"


# ── Minor 3: 행 간 날짜 불일치는 첫 값을 유지하고 조용히 넘어가지 않는다 ──────────


def test_date_mismatch_across_rows_keeps_first_value(capsys):
    rows = [
        _row(sector="반도체", kr_session_date="2026-07-31"),
        _row(sector="방산", kr_session_date="2026-07-30"),
    ]
    result = g.build_overnight_bridge({"overnight_bridge": rows})

    assert result["overnight_bridge_date"] == "2026-07-31"
    err = capsys.readouterr().err
    assert "kr_session_date" in err and "불일치" in err


# ── Minor 4: 음의 0 정규화 — 표시 문자열과 색상 클래스가 항상 일치해야 한다 ────────


def test_negative_zero_us_change_renders_positive_zero_and_up():
    row = _row(us_change=-0.0)
    result = g.build_overnight_bridge({"overnight_bridge": [row]})
    out = result["overnight_bridge"][0]

    assert out["us_change_fmt"] == "+0.00%"
    assert out["us_cls"] == "up"


def test_tiny_negative_us_change_rounds_to_positive_zero_and_up():
    # -0.001은 2자리 반올림하면 -0.0이 되므로, 반올림 이전 원값으로 up/dn을 판정하면
    # 화면엔 "0.00%"인데 파란색(dn)이 뜨는 모순이 생긴다.
    row = _row(us_change=-0.001)
    result = g.build_overnight_bridge({"overnight_bridge": [row]})
    out = result["overnight_bridge"][0]

    assert out["us_change_fmt"] == "+0.00%"
    assert out["us_cls"] == "up"


def test_tiny_negative_gap_rounds_to_dongjo_not_mibanyeong():
    # round(-0.04, 1) == -0.0. 반올림 전 원값(-0.04)으로 판정하면 "-0.0%p"인데
    # "미반영"/dn으로 표시되는 모순이 생긴다 — 반올림 후 값으로 판정해야 일치한다.
    row = _row(gap_pp=-0.04)
    result = g.build_overnight_bridge({"overnight_bridge": [row]})
    out = result["overnight_bridge"][0]

    assert out["gap_fmt"] == "+0.0%p"
    assert out["gap_cls"] == ""
    assert out["gap_word"] == "동조"


# ── Minor 5: 날짜 없는 행은 표시하지 않는다(§0 — 없으면 비운다) ───────────────────


def test_row_without_session_date_is_skipped():
    row = _row()
    del row["kr_session_date"]
    result = g.build_overnight_bridge({"overnight_bridge": [row]})

    assert result == {"overnight_bridge": [], "overnight_bridge_date": ""}


def test_row_with_empty_session_date_is_skipped():
    row = _row(kr_session_date="")
    result = g.build_overnight_bridge({"overnight_bridge": [row]})

    assert result == {"overnight_bridge": [], "overnight_bridge_date": ""}
