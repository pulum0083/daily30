# US는 예측 채점 대상이 아님을 검증 — check_accuracy("...", "us")는 아무 것도 채점하지 않는다
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_accuracy as ca


def test_check_accuracy_us_is_noop(capsys):
    # US는 조기 반환. 예외 없이 안내 로그만 출력.
    ca.check_accuracy("2026-07-14", "us")
    err = capsys.readouterr().err
    assert "us" in err.lower()


def test_backfill_us_is_noop(capsys):
    ca.backfill("us")
    err = capsys.readouterr().err
    assert "us" in err.lower()
