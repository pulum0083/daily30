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
    tpl = (Path(gh.__file__).parent / "templates" / "sections" / "prediction_strip.html").read_text(encoding="utf-8")
    html = gh.Environment(loader=gh.FileSystemLoader(str(Path(gh.__file__).parent / "templates"))).from_string(tpl)
    assert "시초가 방향 예측" in html.render(**new)
    assert "당일 방향 예측" in html.render(**old)
