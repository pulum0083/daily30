# 성적표 '항상 상승' 기준선 계산·표시 회귀 테스트 (스펙 2026-08-11)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_html import _baseline_pct, _edge_cls  # noqa: E402


def _row(date, is_correct, up):
    """채점 완료된 코스피 항목 하나.

    up=실제 상승 여부. predicted_direction은 is_correct와 앞뒤가 맞게 역산한다
    (맞혔으면 실제와 같은 방향을 예측한 것).
    """
    return {
        "date": date,
        "type": "kospi",
        "predicted_direction": "상승 우위" if (up == is_correct) else "하락 우위",
        "actual_direction": "상승" if up else "하락",
        "actual_change_pct": 1.0 if up else -1.0,
        "is_correct": is_correct,
    }


def test_baseline_counts_actual_up_days():
    """기준선 = 실제 상승일 비율. 상승 3 / 하락 2 → 60%."""
    rows = [
        _row("2026-04-01", True, True),
        _row("2026-04-02", False, True),
        _row("2026-04-03", True, True),
        _row("2026-04-06", True, False),
        _row("2026-04-07", False, False),
    ]
    assert _baseline_pct(rows) == 60


def test_baseline_excludes_unscored():
    """미채점 항목은 우리 적중률 표본에 없으므로 기준선에서도 빠진다.

    같은 표본이 아니면 비교 자체가 무의미하다 — 이 불변식을 계산 지점에서 보장한다.
    """
    rows = [
        _row("2026-04-01", True, True),
        _row("2026-04-02", True, False),
        {"date": "2026-04-03", "type": "kospi", "actual_direction": None,
         "actual_change_pct": None, "is_correct": None},
    ]
    # 채점된 2건 중 상승 1건 → 50%. 미채점을 세면 33%가 되어 틀린다.
    assert _baseline_pct(rows) == 50


def test_baseline_empty_does_not_divide_by_zero():
    assert _baseline_pct([]) == 0
    assert _baseline_pct([{"is_correct": None}]) == 0


def test_edge_cls_boundaries():
    """±10%p 경계. 최근 15건 기준 1건이 6.7%p라 한 자릿수 차이는 노이즈다."""
    assert _edge_cls(10) == "good"
    assert _edge_cls(9) == "flat"
    assert _edge_cls(0) == "flat"
    assert _edge_cls(-9) == "flat"
    assert _edge_cls(-10) == "bad"
