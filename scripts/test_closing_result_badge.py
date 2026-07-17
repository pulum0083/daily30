# 마감 브리핑 텔레그램의 "오늘 아침 예측 → 실제 결과" 배지가 §16 방지 룰(옛 결과 대체 금지)을
# 지키는지 검증하는 테스트
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc


def _write_briefings(tmp_path, rows):
    (tmp_path / "briefings.json").write_text(
        json.dumps({"briefings": rows}, ensure_ascii=False), encoding="utf-8"
    )


def _analysis():
    return {"market_title": "테스트", "telegram_signals": []}


def _market_data(change_pct):
    return {"indices": {
        "kospi": {"price": 7000.0, "change_pct": change_pct},
        "kosdaq": {"price": 800.0, "change_pct": change_pct},
    }}


def test_badge_shows_hit_when_direction_matches(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-16", "predicted_direction": "하락 우위", "is_correct": None},
        {"type": "kospi", "date": "2026-07-10", "is_correct": True},
        {"type": "kospi", "date": "2026-07-13", "is_correct": False},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    cc.save_closing_telegram_message("2026-07-16", _analysis(), _market_data(-6.37))
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "✓ 적중" in text
    assert "하락 우위 → 실제 -6.37%" in text
    assert "누적 50%" in text  # 1승 1패 → 50%


def test_badge_shows_miss_when_direction_mismatches(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-16", "predicted_direction": "하락 우위", "is_correct": None},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    cc.save_closing_telegram_message("2026-07-16", _analysis(), _market_data(0.73))
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "✗ 빗나감" in text
    assert "하락 우위 → 실제 +0.73%" in text


def test_badge_omitted_when_no_today_prediction(tmp_path, monkeypatch):
    # §16: 오늘 예측이 briefings.json에 없으면 옛 결과로 대체하지 않고 배지 자체를 생략한다.
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-10", "predicted_direction": "상승 우위", "is_correct": True},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    cc.save_closing_telegram_message("2026-07-16", _analysis(), _market_data(-6.37))
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "🎯" not in text
    assert "실제" not in text


def test_badge_omitted_when_kospi_change_missing(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-16", "predicted_direction": "하락 우위", "is_correct": None},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    market_data = {"indices": {"kospi": {"error": "fetch failed"}, "kosdaq": {"price": 800.0, "change_pct": 1.0}}}
    cc.save_closing_telegram_message("2026-07-16", _analysis(), market_data)
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "🎯" not in text


def test_cumulative_accuracy_excludes_today_and_unscored(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-16", "predicted_direction": "하락 우위", "is_correct": None},
        {"type": "kospi", "date": "2026-07-10", "is_correct": True},
        {"type": "kospi", "date": "2026-07-13", "is_correct": True},
        {"type": "kospi", "date": "2026-07-14", "is_correct": False},
        {"type": "us", "date": "2026-07-13", "is_correct": True},  # 다른 타입은 제외
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    assert cc._cumulative_kospi_accuracy("2026-07-16") == (2, 3)
