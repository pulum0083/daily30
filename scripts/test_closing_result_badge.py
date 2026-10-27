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
    assert "📝 아침 예측 하락 → 실제 -6.37% ✓" in text   # 종가 기준(전환 이전) 기록은 종가로 채점한다
    assert "누적" not in text                  # 누적은 시초가 기준 기록만 세고, 5건 미만이면 붙이지 않는다(§57)


def test_badge_shows_miss_when_direction_mismatches(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-16", "predicted_direction": "하락 우위", "is_correct": None},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    cc.save_closing_telegram_message("2026-07-16", _analysis(), _market_data(0.73))
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "📝 아침 예측 하락 → 실제 +0.73% ✗" in text


def test_badge_omitted_when_no_today_prediction(tmp_path, monkeypatch):
    # §16: 오늘 예측이 briefings.json에 없으면 옛 결과로 대체하지 않고 배지 자체를 생략한다.
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-10", "predicted_direction": "상승 우위", "is_correct": True},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    cc.save_closing_telegram_message("2026-07-16", _analysis(), _market_data(-6.37))
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "📝" not in text   # 채점 배지(📝) 없음 — 🎯는 타이틀 줄(2026-10-25)
    assert "실제" not in text


def test_badge_omitted_when_kospi_change_missing(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-16", "predicted_direction": "하락 우위", "is_correct": None},
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    market_data = {"indices": {"kospi": {"error": "fetch failed"}, "kosdaq": {"price": 800.0, "change_pct": 1.0}}}
    cc.save_closing_telegram_message("2026-07-16", _analysis(), market_data)
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "📝" not in text   # 채점 배지(📝) 없음 — 🎯는 타이틀 줄(2026-10-25)


def test_cumulative_accuracy_excludes_today_and_unscored(tmp_path, monkeypatch):
    _write_briefings(tmp_path, [
        {"type": "kospi", "date": "2026-07-16", "predicted_direction": "하락 우위", "is_correct": None},
        {"type": "kospi", "date": "2026-07-09", "is_correct": True},                    # 종가 기준 옛 기록은 제외(§57)
        {"type": "kospi", "date": "2026-07-10", "basis": "open", "is_correct": True},
        {"type": "kospi", "date": "2026-07-13", "basis": "open", "is_correct": True},
        {"type": "kospi", "date": "2026-07-14", "basis": "open", "is_correct": False},
        {"type": "us", "date": "2026-07-13", "is_correct": True},  # 다른 타입은 제외
    ])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    assert cc._cumulative_kospi_accuracy("2026-07-16") == (2, 3)


# ── 시초가 기준 예측(§57) — 마감 배지는 종가가 아니라 오늘 시가 갭으로 채점한다 ──
def _open_pred(direction="상승 우위"):
    return {"type": "kospi", "date": "2026-10-13", "basis": "open", "predicted_direction": direction, "is_correct": None}


def test_open_basis_badge_scores_by_open_gap_not_close(tmp_path, monkeypatch):
    # 위로 열리고(+0.58%) 밀려서 끝난 날(종가 -0.89%) — 2026-10-06 모양. 시초가 예측은 맞은 것이다.
    import check_accuracy as ca
    _write_briefings(tmp_path, [_open_pred("상승 우위")])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ca, "get_kospi_open_gap", lambda d: (6600.0, 6562.0, 0.58))
    cc.save_closing_telegram_message("2026-10-13", _analysis(), _market_data(-0.89))
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "📝 아침 예측 상승 → 시초가 +0.58% ✓" in text


def test_open_basis_badge_omitted_when_gap_unavailable(tmp_path, monkeypatch):
    # 시가를 못 구하면 종가로 대신 채점하지 않고 배지를 뺀다(§0).
    import check_accuracy as ca
    _write_briefings(tmp_path, [_open_pred("상승 우위")])
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ca, "get_kospi_open_gap", lambda d: None)
    cc.save_closing_telegram_message("2026-10-13", _analysis(), _market_data(1.5))
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "📝" not in text   # 채점 배지(📝) 없음 — 🎯는 타이틀 줄(2026-10-25)
