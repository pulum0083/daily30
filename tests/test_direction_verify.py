# 마감 방향 예측 검증(build_close_direction_verify) 단위 테스트
import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
import generate_html as gh


def _write_briefings(tmp_path, entries):
    """임시 briefings.json을 만들고 DATA_DIR을 가리키게 한다."""
    (tmp_path / "briefings.json").write_text(
        json.dumps({"briefings": entries}, ensure_ascii=False), encoding="utf-8"
    )
    gh.DATA_DIR = tmp_path


def _market(change_pct, price=8801.49):
    return {"indices": {"kospi": {"change_pct": change_pct, "price": price}}}


def test_up_prediction_hit(tmp_path):
    _write_briefings(tmp_path, [
        {"date": "2026-06-02", "type": "kospi", "predicted_direction": "상승 우위",
         "up_pct": 82, "down_pct": 18, "confidence": 88, "is_correct": None},
    ])
    ctx = gh.build_close_direction_verify(_market(0.15), "KOSPI", "2026-06-02")
    assert ctx["dv_show"] is True
    assert ctx["dv_verdict_cls"] == "hit"
    assert ctx["dv_prob_label"] == "상승 확률"
    assert ctx["dv_prob_pct"] == 82
    assert ctx["dv_actual_cls"] == "up"


def test_up_prediction_miss(tmp_path):
    _write_briefings(tmp_path, [
        {"date": "2026-06-02", "type": "kospi", "predicted_direction": "상승 우위",
         "up_pct": 65, "down_pct": 35, "confidence": 70, "is_correct": None},
    ])
    ctx = gh.build_close_direction_verify(_market(-0.82), "KOSPI", "2026-06-02")
    assert ctx["dv_verdict_cls"] == "miss"
    assert ctx["dv_actual_cls"] == "down"


def test_down_prediction_hit(tmp_path):
    _write_briefings(tmp_path, [
        {"date": "2026-06-02", "type": "kospi", "predicted_direction": "하락 우위",
         "up_pct": 30, "down_pct": 70, "confidence": 60, "is_correct": None},
    ])
    ctx = gh.build_close_direction_verify(_market(-1.2), "KOSPI", "2026-06-02")
    assert ctx["dv_verdict_cls"] == "hit"
    assert ctx["dv_prob_label"] == "하락 확률"
    assert ctx["dv_prob_pct"] == 70
    assert ctx["dv_pred_cls"] == "down"


def test_no_prediction_returns_empty(tmp_path):
    # 당일 kospi 예측이 없으면 섹션을 렌더링하지 않는다
    _write_briefings(tmp_path, [
        {"date": "2026-06-01", "type": "kospi", "predicted_direction": "상승 우위",
         "up_pct": 60, "down_pct": 40, "confidence": 65, "is_correct": True},
    ])
    ctx = gh.build_close_direction_verify(_market(0.15), "KOSPI", "2026-06-02")
    assert ctx == {}


def test_streak_uses_recent_checked(tmp_path):
    entries = [
        {"date": "2026-04-08", "type": "kospi", "predicted_direction": "상승 우위",
         "up_pct": 60, "down_pct": 40, "confidence": 65, "is_correct": False},
        {"date": "2026-04-09", "type": "kospi", "predicted_direction": "상승 우위",
         "up_pct": 60, "down_pct": 40, "confidence": 65, "is_correct": True},
        {"date": "2026-06-02", "type": "kospi", "predicted_direction": "상승 우위",
         "up_pct": 82, "down_pct": 18, "confidence": 88, "is_correct": None},
    ]
    _write_briefings(tmp_path, entries)
    ctx = gh.build_close_direction_verify(_market(0.15), "KOSPI", "2026-06-02")
    # 검증 완료분(2건)만 집계, 오늘(pending)은 제외
    assert ctx["dv_streak_label"] == "최근 2회"
    assert ctx["dv_streak_text"] == "1/2 적중"


def test_streak_hidden_when_none_checked(tmp_path):
    _write_briefings(tmp_path, [
        {"date": "2026-06-02", "type": "kospi", "predicted_direction": "상승 우위",
         "up_pct": 82, "down_pct": 18, "confidence": 88, "is_correct": None},
    ])
    ctx = gh.build_close_direction_verify(_market(0.15), "KOSPI", "2026-06-02")
    assert ctx["dv_streak_text"] is None
