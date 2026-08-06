# 등락률 셀 표시 테스트 — 0.00%가 상승(▲·빨강)으로 나가던 사고 검증.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_html import _chg_cell  # noqa: E402


def test_unknown_renders_nothing():
    """등락률을 모르면 0.00%로 채우지 않고 셀을 비운다(운영 규칙 §0 ②)."""
    assert _chg_cell(None) == {"chg": "", "chg_cls": "unknown"}


def test_genuine_flat_is_neutral_not_up():
    """2026-08-06 사고: 0.00%가 ▲·상승색으로 나갔다. 보합은 중립이어야 한다."""
    cell = _chg_cell(0.0)
    assert cell["chg_cls"] == "flat"
    assert "▲" not in cell["chg"]
    assert cell["chg_cls"] != "up"


def test_up():
    assert _chg_cell(0.26) == {"chg": "▲ +0.26%", "chg_cls": "up"}


def test_down():
    assert _chg_cell(-4.58) == {"chg": "▼ -4.58%", "chg_cls": "down"}


def test_tiny_up_still_up():
    """반올림 전 아주 작은 상승도 상승으로 분류된다(0과 구분)."""
    assert _chg_cell(0.04)["chg_cls"] == "up"


def test_unknown_and_flat_are_distinct():
    """'모름'과 '보합'이 같은 모습이면 수집 실패가 정상 데이터로 보인다."""
    assert _chg_cell(None)["chg_cls"] != _chg_cell(0.0)["chg_cls"]


def test_no_input_renders_as_up():
    """어떤 입력도 0을 up으로 분류하지 않는다 — 회귀 가드."""
    for v in (None, 0, 0.0, -0.0):
        assert _chg_cell(v)["chg_cls"] != "up", f"{v!r}가 상승으로 분류됐다"
