# 성적표 '항상 상승' 기준선 계산·표시 회귀 테스트 (스펙 2026-08-11)
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_html  # noqa: E402
from generate_html import _baseline_pct, _edge_cls, build_scorecard  # noqa: E402


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


def _fixture_rows():
    """4월 10건 + 5월 10건 = 20건. 기대값은 손으로 계산해 아래 테스트에 박아둔다.

    4월 — 상승 8(1~8일차) / 적중 6(1~6일차)  → 우리 60%, 기준 80%, 우위 -20%p
    5월 — 상승 3(1~3일차) / 적중 8(1~8일차)  → 우리 80%, 기준 30%, 우위 +50%p
    누적 20건 — 적중 14(70%), 상승 11(55%)   → 우위 +15%p
    최근 15건(4월 6~10일차 + 5월 전체) — 적중 9(60%), 상승 6(40%) → 우위 +20%p
    """
    rows = []
    for i in range(1, 11):
        rows.append(_row(f"2026-04-{i:02d}", is_correct=(i <= 6), up=(i <= 8)))
    for i in range(1, 11):
        rows.append(_row(f"2026-05-{i:02d}", is_correct=(i <= 8), up=(i <= 3)))
    return rows


def _ctx(monkeypatch, tmp_path, rows):
    """briefings.json 픽스처를 주입하고 build_scorecard를 돌린다.

    실제 data/briefings.json을 읽으면 다음 채점 때 숫자가 바뀌어 테스트가 깨진다.
    """
    (tmp_path / "briefings.json").write_text(
        json.dumps({"briefings": rows}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(generate_html, "DATA_DIR", tmp_path)
    return build_scorecard("kospi")


def test_card_baseline_values(monkeypatch, tmp_path):
    ctx = _ctx(monkeypatch, tmp_path, _fixture_rows())
    assert ctx["sc_recent15_pct"] == 60
    assert ctx["sc_recent15_base"] == 40
    assert ctx["sc_cum_pct"] == 70
    assert ctx["sc_cum_base"] == 55


def test_displayed_edge_matches_displayed_numbers(monkeypatch, tmp_path):
    """사용자가 암산한 값과 표시된 우위가 어긋나면 안 된다 — 반올림값끼리 뺀다."""
    ctx = _ctx(monkeypatch, tmp_path, _fixture_rows())
    assert ctx["sc_recent15_edge"] == ctx["sc_recent15_pct"] - ctx["sc_recent15_base"]
    assert ctx["sc_cum_edge"] == ctx["sc_cum_pct"] - ctx["sc_cum_base"]
    assert ctx["sc_recent15_edge"] == 20
    assert ctx["sc_cum_edge"] == 15


def test_gauge_colors_follow_edge(monkeypatch, tmp_path):
    ctx = _ctx(monkeypatch, tmp_path, _fixture_rows())
    assert ctx["sc_recent15_gcls"] == "good"   # +20%p
    assert ctx["sc_cum_gcls"] == "good"        # +15%p


def test_monthly_rows_carry_baseline(monkeypatch, tmp_path):
    """기준선에 진 달이 그대로 드러나야 한다 — 4월은 우리 60% vs 기준 80%."""
    ctx = _ctx(monkeypatch, tmp_path, _fixture_rows())
    by_label = {m["label"]: m for m in ctx["sc_monthly"]}
    assert by_label["4월"]["pct"] == 60
    assert by_label["4월"]["base_pct"] == 80
    assert by_label["5월"]["pct"] == 80
    assert by_label["5월"]["base_pct"] == 30


def test_card_omitted_below_five_scored(monkeypatch, tmp_path):
    """표본 5건 미만이면 카드 자체를 생략하는 기존 가드가 유지된다."""
    rows = [_row(f"2026-04-{i:02d}", True, True) for i in range(1, 5)]
    assert _ctx(monkeypatch, tmp_path, rows) == {}
