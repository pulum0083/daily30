# 예측 시점 선행신호 아카이브 테스트 — prior 실전 성적을 사후 추적하기 위한 스냅샷.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import call_claude as cc  # noqa: E402


def _with_latest(tmp_path, latest):
    (tmp_path / "latest_kospi.json").write_text(
        json.dumps(latest, ensure_ascii=False), encoding="utf-8"
    )
    orig = cc.DATA_DIR
    cc.DATA_DIR = tmp_path
    try:
        return cc._signal_snapshot("kospi")
    finally:
        cc.DATA_DIR = orig


LATEST = {
    "market_data_js": {
        "sox": {"chg": -4.25}, "nasdaq": {"chg": -0.64},
        "kospi": {"chg": -5.72}, "nq": {"chg": 0.42}, "usd": {"chg": 0.3},
    },
    "ewy": {"change_pct": -6.27},
    "vix": {"change_pct": 1.2},
    "futures": {"sp500_fut": {"change_pct": 0.31}, "dow_fut": {"change_pct": 0.18}},
}


def test_snapshot_records_prior_and_signals(tmp_path):
    snap = _with_latest(tmp_path, LATEST)
    assert snap["prior_direction"] == "하락"
    assert isinstance(snap["prior_score"], float)
    assert snap["signals"]["sox"] == -4.25
    assert snap["signals"]["ewy"] == -6.27


def test_snapshot_records_futures_for_backtest(tmp_path):
    """선물은 과거 복원이 불가능하므로 예측 시점에 남겨두는 게 유일한 방법이다."""
    snap = _with_latest(tmp_path, LATEST)
    assert snap["signals"]["es"] == 0.31
    assert snap["signals"]["ym"] == 0.18
    assert snap["signals"]["nq"] == 0.42


def test_snapshot_records_ewy_residual(tmp_path):
    """원본과 잔차를 함께 남겨 어느 쪽이 잘 맞는지 사후 비교할 수 있게 한다."""
    snap = _with_latest(tmp_path, LATEST)
    assert snap["signals"]["ewy"] == -6.27
    assert snap["signals"]["ewy_resid"] == -0.55
    assert snap["signals"]["kospi"] == -5.72


def test_non_kospi_types_skipped():
    """채점 대상이 아닌 타입은 스냅샷을 만들지 않는다."""
    assert cc._signal_snapshot("us") == {}
    assert cc._signal_snapshot("kospi-close") == {}


def test_missing_file_is_silent(tmp_path):
    """latest_kospi.json이 없어도 발행을 막지 않는다."""
    orig = cc.DATA_DIR
    cc.DATA_DIR = tmp_path
    try:
        assert cc._signal_snapshot("kospi") == {}
    finally:
        cc.DATA_DIR = orig
