# 뉴스 수집 프롬프트의 중복 방지 주입(_load_prev_catalysts)이 올바르게 동작하는지 검증하는 테스트.
# 2026-07-15~17 실사고: ASML·모건스탠리 실적 촉매가 사흘 연속 "오늘의 이슈"로 재포장됨.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn


def test_returns_empty_when_no_prev_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    assert fn._load_prev_catalysts("us") == []


def test_returns_empty_on_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    (tmp_path / "news_summary_us.json").write_text("{not valid json", encoding="utf-8")
    assert fn._load_prev_catalysts("us") == []


def test_combines_catalysts_and_headlines(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    (tmp_path / "news_summary_us.json").write_text(json.dumps({
        "catalysts": ["ASML 실적 서프라이즈 → 반도체 장비주 강세"],
        "headlines": ["ASML 호실적에 반도체 장비주 강세 전망"],
    }, ensure_ascii=False), encoding="utf-8")
    items = fn._load_prev_catalysts("us")
    assert "ASML 실적 서프라이즈 → 반도체 장비주 강세" in items
    assert "ASML 호실적에 반도체 장비주 강세 전망" in items


def test_respects_max_items_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    (tmp_path / "news_summary_us.json").write_text(json.dumps({
        "catalysts": [f"c{i}" for i in range(5)],
        "headlines": [f"h{i}" for i in range(5)],
    }), encoding="utf-8")
    assert len(fn._load_prev_catalysts("us", max_items=6)) == 6


def test_isolated_per_briefing_type(tmp_path, monkeypatch):
    # kospi 파일만 있고 us 파일은 없으면 us 조회는 빈 리스트여야 한다(타입 간 혼선 금지)
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    (tmp_path / "news_summary_kospi.json").write_text(json.dumps({
        "catalysts": ["코스피 전용 이슈"],
    }), encoding="utf-8")
    assert fn._load_prev_catalysts("us") == []
    assert fn._load_prev_catalysts("kospi") == ["코스피 전용 이슈"]
