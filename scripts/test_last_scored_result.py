# 텔레그램 "지난 예측" 배지가 미채점 예측을 옛 채점 결과로 조용히 대체하지 않는지 검증하는 테스트
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc


def _write_briefings(tmp_path, rows):
    (tmp_path / "briefings.json").write_text(
        json.dumps({"briefings": rows}, ensure_ascii=False), encoding="utf-8"
    )


def test_returns_none_when_prior_day_unscored(tmp_path, monkeypatch):
    # 2026-07-13 실사고 재현: 어제(가장 최근) 예측이 아직 미채점인데 3일 전(7/10) 채점 결과로
    # 조용히 건너뛰면 안 된다 — 어제 예측이 실제로는 크게 틀렸어도 옛 적중 결과가 뜨는 사고.
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-10", "is_correct": True},
        {"type": "kospi", "date": "2026-07-13", "is_correct": None},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    assert cc._last_scored_result("kospi", "2026-07-14") is None


def test_returns_correct_value_when_prior_day_scored(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-13", "is_correct": False},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    assert cc._last_scored_result("kospi", "2026-07-14") is False


def test_returns_none_when_no_prior_entries(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-14", "is_correct": None},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    assert cc._last_scored_result("kospi", "2026-07-14") is None


def test_ignores_other_briefing_type(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "us", "date": "2026-07-13", "is_correct": True},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    assert cc._last_scored_result("kospi", "2026-07-14") is None
