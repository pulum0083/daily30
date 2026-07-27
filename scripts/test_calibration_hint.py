# up_pct 캘리브레이션 표 주입 테스트 — 미채점 항목이 섞이지 않는지 포함(§16).
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import call_claude as cc  # noqa: E402


def _write(tmp_rows, monkey_dir):
    (monkey_dir / "data").mkdir(parents=True, exist_ok=True)
    (monkey_dir / "data" / "briefings.json").write_text(
        json.dumps({"briefings": tmp_rows}, ensure_ascii=False), encoding="utf-8"
    )


def _with_fixture(tmp_path, rows, **kw):
    """BASE_DIR을 임시 경로로 갈아끼워 픽스처로 계산한다."""
    _write(rows, tmp_path)
    orig = cc.BASE_DIR
    cc.BASE_DIR = tmp_path
    try:
        return cc.build_calibration_hint("kospi", **kw)
    finally:
        cc.BASE_DIR = orig


def _row(up_pct, actual, type_="kospi"):
    return {"type": type_, "up_pct": up_pct, "actual_change_pct": actual}


def test_unscored_rows_are_excluded(tmp_path):
    """actual_change_pct가 None인 미채점 항목은 집계에서 빠진다(§16)."""
    rows = [_row(65, 1.0) for _ in range(20)]
    rows.append({"type": "kospi", "up_pct": 30, "actual_change_pct": None})
    out = _with_fixture(tmp_path, rows)
    assert "채점 완료 20건" in out


def test_other_briefing_types_excluded(tmp_path):
    """us 타입 예측은 코스피 표에 섞이지 않는다."""
    rows = [_row(65, 1.0) for _ in range(20)] + [_row(20, -1.0, "us") for _ in range(10)]
    out = _with_fixture(tmp_path, rows)
    assert "채점 완료 20건" in out
    assert "| 20~29 |" not in out


def test_bucket_rate_is_computed(tmp_path):
    """구간별 실제 상승률이 실제 데이터대로 나온다."""
    rows = [_row(65, 1.0) for _ in range(15)] + [_row(65, -1.0) for _ in range(5)]
    out = _with_fixture(tmp_path, rows)
    assert "| 60~69 | 20회 | 75% |" in out


def test_small_sample_returns_empty(tmp_path):
    """표본이 적으면 근거 없는 표를 만들지 않는다."""
    rows = [_row(65, 1.0) for _ in range(5)]
    assert _with_fixture(tmp_path, rows) == ""


def test_missing_file_returns_empty(tmp_path):
    """briefings.json이 없어도 터지지 않는다(파이프라인 보호)."""
    orig = cc.BASE_DIR
    cc.BASE_DIR = tmp_path
    try:
        assert cc.build_calibration_hint("kospi") == ""
    finally:
        cc.BASE_DIR = orig


def test_real_data_shape():
    """실데이터로 렌더했을 때 표 골격과 기저율이 들어간다."""
    out = cc.build_calibration_hint("kospi")
    if not out:  # 표본 부족 환경이면 스킵
        return
    assert "| up_pct 구간 | 예측 횟수 | 실제 상승률 |" in out
    assert "기저율" in out
