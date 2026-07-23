# _bump_latest_time('새 이슈 없으면 콘텐츠는 그대로, 시각만 갱신') 검증.
# 2026-07-23 실사고: 12:30 이후 신규 기사가 전부 기존과 동일해 3회 연속 스킵되면서
# '오늘 장중 이슈'가 몇 시간째 옛 시각에 멈춰 파이프라인이 죽은 것처럼 보였다.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news_live as m

SEED = {
    "date": "2026-07-23", "updated_at": "12:30", "slot": "MARKET",
    "seen_titles": ["코스피 장중 7000선 회복… 경기회복 기대에 투심 살아나"],
    "latest": {
        "market": {"title": "코스피 장중 7000선 회복… 경기회복 기대에 투심 살아나"},
        "stock": {"title": "삼성전자 강세"},
    },
    "history": [
        {"time": "12:30", "market": {"title": "코스피 장중 7000선 회복… 경기회복 기대에 투심 살아나"},
         "stock": {"title": "삼성전자 강세"}},
        {"time": "12:01", "market": {"title": "개미는 오늘도 팔자"}, "stock": {"title": "외국인 순매수"}},
    ],
}


def _seed(tmp_path, monkeypatch, data):
    live = tmp_path / "kospi-news-live.json"
    live.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(m, "OUT_PATH", live)
    return live


def test_no_existing_file_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "OUT_PATH", tmp_path / "kospi-news-live.json")
    assert m._bump_latest_time("2026-07-23", "15:31", "MARKET") is False
    assert not (tmp_path / "kospi-news-live.json").exists()


def test_same_content_bumps_time_only(tmp_path, monkeypatch):
    live = _seed(tmp_path, monkeypatch, dict(SEED))
    assert m._bump_latest_time("2026-07-23", "15:31", "MARKET") is True

    out = json.loads(live.read_text(encoding="utf-8"))
    assert out["history"][0]["time"] == "15:31"
    assert out["updated_at"] == "15:31"
    # 콘텐츠는 절대 바뀌지 않는다 — 시각만.
    assert out["history"][0]["market"]["title"] == "코스피 장중 7000선 회복… 경기회복 기대에 투심 살아나"
    assert out["history"][1]["time"] == "12:01"          # 다른 항목은 안 건드림
    assert len(out["history"]) == 2                        # 새 항목 추가 아님
    assert out["seen_titles"] == SEED["seen_titles"]        # seen_titles 불변


def test_archive_file_also_updated(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, dict(SEED))
    m._bump_latest_time("2026-07-23", "15:31", "MARKET")
    archive = tmp_path / "kospi-news-2026-07-23.json"
    assert archive.exists()
    out = json.loads(archive.read_text(encoding="utf-8"))
    assert out["history"][0]["time"] == "15:31"


def test_different_date_not_touched(tmp_path, monkeypatch):
    stale = dict(SEED); stale["date"] = "2026-07-22"
    live = _seed(tmp_path, monkeypatch, stale)
    assert m._bump_latest_time("2026-07-23", "09:05", "MARKET") is False
    out = json.loads(live.read_text(encoding="utf-8"))
    assert out["updated_at"] == "12:30"  # 어제 데이터는 그대로


def test_no_history_returns_false(tmp_path, monkeypatch):
    empty = dict(SEED); empty["history"] = []
    live = _seed(tmp_path, monkeypatch, empty)
    assert m._bump_latest_time("2026-07-23", "15:31", "MARKET") is False
