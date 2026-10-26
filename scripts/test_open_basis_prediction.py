# 코스피 예측의 시초가 기준 전환(§57) 회귀 테스트 — 채점·기록·통계·화면 라벨
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_accuracy as ca  # noqa: E402
import prediction_basis as pb  # noqa: E402

# 2026-10-06 실측 모양: 위로 열리고(+0.58%) 장중에 밀려 종가는 −0.89%
ROWS = [
    {"localDate": "20261002", "openPrice": 6500.0, "closePrice": 6562.0},
    {"localDate": "20261006", "openPrice": 6600.06, "closePrice": 6503.6},
]


def test_open_gap_is_open_vs_previous_close():
    o, prev, gap = ca.open_gap_from_rows(ROWS, "2026-10-06")
    assert (o, prev) == (6600.06, 6562.0)
    assert round(gap, 2) == 0.58


def test_open_gap_none_when_bar_or_previous_bar_missing():
    assert ca.open_gap_from_rows(ROWS, "2026-10-07") is None      # 그 날짜 봉 없음 — 다른 날짜로 대신하지 않는다
    assert ca.open_gap_from_rows(ROWS, "2026-10-02") is None      # 직전 봉 없음
    assert ca.open_gap_from_rows([{"localDate": "20261002", "closePrice": 1.0},
                                  {"localDate": "20261006", "openPrice": 0, "closePrice": 1.0}], "2026-10-06") is None


def _run_check(tmp_path, monkeypatch, entry, gap, close=(6503.6, 6562.0, -0.89)):
    data = {"briefings": [entry]}
    monkeypatch.setattr(ca, "load_briefings", lambda: data)
    monkeypatch.setattr(ca, "save_briefings", lambda d: None)
    monkeypatch.setattr(ca, "get_kospi_close_vs_prev_close", lambda d: close)
    monkeypatch.setattr(ca, "get_kospi_open_gap", lambda d: gap)
    monkeypatch.setattr(ca, "_save_market_archive", lambda *a, **k: None)
    monkeypatch.setattr(ca, "BASE_DIR", tmp_path)
    ca.check_accuracy("2026-10-06", "kospi")
    return entry


def test_open_basis_is_scored_by_gap_even_when_close_reverses(tmp_path, monkeypatch):
    e = _run_check(tmp_path, monkeypatch,
                   {"date": "2026-10-06", "type": "kospi", "basis": "open", "predicted_direction": "상승 우위"},
                   gap=(6600.06, 6562.0, 0.58))
    assert e["is_correct"] is True                 # 종가는 −0.89%지만 시초가 예측은 맞았다
    assert e["actual_open_pct"] == 0.58
    assert e["actual_direction"] == "상승"
    assert e["actual_change_pct"] == -0.89         # 종가 대비 등락률은 그대로 남긴다


def test_close_basis_record_keeps_close_scoring(tmp_path, monkeypatch):
    e = _run_check(tmp_path, monkeypatch,
                   {"date": "2026-10-06", "type": "kospi", "predicted_direction": "상승 우위"},
                   gap=(6600.06, 6562.0, 0.58))
    assert e["is_correct"] is False
    assert "actual_open_pct" not in e


def test_open_basis_scoring_is_held_when_open_unavailable(tmp_path, monkeypatch):
    e = _run_check(tmp_path, monkeypatch,
                   {"date": "2026-10-06", "type": "kospi", "basis": "open", "predicted_direction": "상승 우위"},
                   gap=None)
    assert e.get("is_correct") is None             # 종가로 대신 채점하지 않는다(§0)
    assert e.get("actual_direction") is None


def test_stats_rows_drop_close_basis_kospi_only():
    rows = [
        {"type": "kospi", "date": "a", "is_correct": True},
        {"type": "kospi", "date": "b", "basis": "open", "is_correct": False},
        {"type": "us", "date": "c", "is_correct": True},
    ]
    assert [r["date"] for r in pb.stats_rows(rows)] == ["b", "c"]
    assert [r["date"] for r in pb.legacy_kospi_rows(rows)] == ["a"]
    assert pb.outcome_pct({"basis": "open", "actual_open_pct": 0.5, "actual_change_pct": -1}) == 0.5
    assert pb.outcome_pct({"actual_open_pct": 0.5, "actual_change_pct": -1}) == -1
    assert pb.outcome_pct({"basis": "open", "actual_change_pct": -1}) is None


def test_prediction_record_carries_basis_and_scored_record_keeps_its_own(tmp_path, monkeypatch):
    import call_claude as cc
    (tmp_path / "data").mkdir()
    path = tmp_path / "data" / "briefings.json"
    path.write_text(json.dumps({"briefings": [
        {"date": "2026-10-08", "type": "kospi", "predicted_direction": "하락 우위",
         "actual_direction": "하락", "actual_change_pct": -2.62, "is_correct": True},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(cc, "BASE_DIR", tmp_path)
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(cc, "_signal_snapshot", lambda t: {})
    pred = {"prediction": {"direction": "상승 우위", "up_pct": 62, "down_pct": 38, "confidence": 60, "basis": "open"}}
    cc.save_prediction_to_briefings("kospi", "2026-10-13", pred)     # 새 기록 → 시초가 기준
    cc.save_prediction_to_briefings("kospi", "2026-10-08", pred)     # 이미 종가로 채점된 날의 재실행 → 기준 유지
    rows = {b["date"]: b for b in json.loads(path.read_text(encoding="utf-8"))["briefings"]}
    assert rows["2026-10-13"]["basis"] == "open"
    assert "basis" not in rows["2026-10-08"]
    assert rows["2026-10-08"]["is_correct"] is True


def test_prompt_targets_the_open_not_the_close():
    import call_claude as cc
    p = cc.KOSPI_SYSTEM_PROMPT
    assert "시초가 방향" in p and "09:00" in p
    assert "당일 방향(종가 기준)" not in p
    assert "상승 마감할 확률" not in p


def test_page_label_follows_record_basis():
    import generate_html as gh
    new = gh.build_prediction({"prediction": {"direction": "상승 우위", "up_pct": 62, "basis": "open"}},
                              "KOSPI", "KOSPI 당일 방향 예측", "07:28")
    old = gh.build_prediction({"prediction": {"direction": "상승 우위", "up_pct": 62}},
                              "KOSPI", "KOSPI 당일 방향 예측", "07:28")
    assert new["pred_basis"] == "open" and new["pred_title"] == "KOSPI 시초가 방향 예측"
    assert old["pred_basis"] is None and old["pred_title"] == "KOSPI 당일 방향 예측"   # 옛 스냅샷 재생성은 옛 문구
    tpl = gh.make_env().get_template("sections/briefing_hero.html")   # 3단 구조 요약 카드(§63)
    assert "시초가 방향 예측" in tpl.render(**new) and "장중 흐름과 종가는 예측하지 않아요" in tpl.render(**new)
    assert "시초가" not in tpl.render(**old)


# ── prior 구속 게이트 — 발행 전 검증 단계에서 up_pct·방향을 prior에 묶는다 ──
def test_validate_clamps_up_pct_to_prior_range():
    import validate_analysis as va
    a = {"prediction": {"direction": "상승 우위", "up_pct": 60, "down_pct": 40}}
    fixes = []
    va.clamp_prediction_to_prior(a, {"up_pct": 76}, fixes)
    assert a["prediction"]["up_pct"] == 66 and a["prediction"]["down_pct"] == 34
    assert len(fixes) == 1 and "60% → 66%" in fixes[0]


def test_validate_leaves_in_range_and_unknown_prior_alone():
    import validate_analysis as va
    a = {"prediction": {"direction": "상승 우위", "up_pct": 70, "down_pct": 30}}
    fixes = []
    va.clamp_prediction_to_prior(a, {"up_pct": 76}, fixes)
    va.clamp_prediction_to_prior(a, {"up_pct": None}, fixes)
    assert a["prediction"]["up_pct"] == 70 and fixes == []


def test_validate_does_not_patch_number_when_direction_still_breaks_prior():
    # 방향 재생성이 실패해 AI 방향이 남은 경우 — '하락 우위'에 상승 확률 66%를 붙이지 않는다.
    import validate_analysis as va
    a = {"prediction": {"direction": "하락 우위", "up_pct": 30, "down_pct": 70}}
    fixes = []
    va.clamp_prediction_to_prior(a, {"up_pct": 76}, fixes)
    assert a["prediction"]["up_pct"] == 30 and fixes == []


def _run_gate(tmp_path, monkeypatch, direction, up_pct, sox, regen_direction=None):
    """validate_analysis.main()을 네트워크 없이 돌린다. 재생성 호출 인자와 저장된 분석을 돌려준다."""
    import validate_analysis as va
    apath = tmp_path / "analysis_kospi.json"
    apath.write_text(json.dumps({"prediction": {"direction": direction, "up_pct": up_pct, "down_pct": 100 - up_pct}},
                                ensure_ascii=False), encoding="utf-8")
    (tmp_path / va.LATEST_FILE["kospi"]).write_text(
        json.dumps({"market_data_js": {"sox": {"chg": sox}}}), encoding="utf-8")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if regen_direction:
            apath.write_text(json.dumps({"prediction": {"direction": regen_direction, "up_pct": 50, "down_pct": 50}},
                                        ensure_ascii=False), encoding="utf-8")
        return type("R", (), {"returncode": 0 if regen_direction else 1})()

    monkeypatch.setattr(va, "DATA_DIR", tmp_path)
    monkeypatch.setattr(va.subprocess, "run", fake_run)
    monkeypatch.setattr(va, "send_admin_alert", lambda *a, **k: None)
    monkeypatch.setattr(va, "enrich_picks_with_realdata", lambda *a, **k: False)
    monkeypatch.setattr(va, "validate", lambda a, l, b: {"analysis": a, "corrections": [], "warnings": [], "blocks": []})
    monkeypatch.setattr(sys, "argv", ["validate_analysis.py", "--type", "kospi"])
    rc = va.main()
    return rc, calls, json.loads(apath.read_text(encoding="utf-8"))["prediction"]


def test_gate_regenerates_when_ai_flips_a_non_strong_prior(tmp_path, monkeypatch):
    # SOX +2.0 → score 3.0, 시초가 상승 확률 76%(strong 아님 — EWY 없음). AI가 '하락 우위'를 내면 상승으로 다시 쓰게 한다.
    rc, calls, pred = _run_gate(tmp_path, monkeypatch, "하락 우위", 35, sox=2.0, regen_direction="상승 우위")
    assert rc == 0 and len(calls) == 1
    assert calls[0][-2:] == ["--force-direction", "상승"]
    assert pred["direction"] == "상승 우위" and pred["up_pct"] == 66      # 재생성본의 50%도 76±10 안으로 당긴다


def test_gate_leaves_direction_to_ai_in_the_coin_flip_zone(tmp_path, monkeypatch):
    # SOX -0.9 → score -1.35, 확률 52% — 45~55 구간은 방향을 강제하지 않는다. 숫자만 범위 안으로.
    rc, calls, pred = _run_gate(tmp_path, monkeypatch, "하락 우위", 30, sox=-0.9)
    assert rc == 0 and calls == []
    assert pred["direction"] == "하락 우위" and pred["up_pct"] == 42


def test_gate_keeps_ai_output_untouched_when_regeneration_fails(tmp_path, monkeypatch):
    rc, calls, pred = _run_gate(tmp_path, monkeypatch, "하락 우위", 35, sox=2.0, regen_direction=None)
    assert rc == 0 and len(calls) == 1
    assert pred == {"direction": "하락 우위", "up_pct": 35, "down_pct": 65}   # 방향·숫자를 어긋나게 고치지 않는다
