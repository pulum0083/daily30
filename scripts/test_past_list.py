# 브리핑 하단 '지난 장' 목록(2026-11-12 A안) — 헤드라인·예측 채점·마감 등락
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generate_html as g  # noqa: E402


def _page(root, date, btype, close=None, snap=None):
    d = root / date / btype
    d.mkdir(parents=True)
    body = f'<div class="a-hero__idx-val">{close}</div>' if close else ""
    (d / "index.html").write_text(f"<html>{body}</html>", encoding="utf-8")
    if snap:
        (d / "analysis_snapshot.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")


def _setup(tmp_path, monkeypatch, briefings):
    bdir, ddir = tmp_path / "b", tmp_path / "d"
    bdir.mkdir(); ddir.mkdir()
    (ddir / "briefings.json").write_text(json.dumps({"briefings": briefings}), encoding="utf-8")
    monkeypatch.setattr(g, "BRIEFINGS_DIR", bdir)
    monkeypatch.setattr(g, "DATA_DIR", ddir)
    return bdir


def test_close_changes_uses_previous_close_page(tmp_path, monkeypatch):
    bdir = _setup(tmp_path, monkeypatch, [])
    _page(bdir, "2026-11-10", "close", "5,239.13")
    _page(bdir, "2026-11-11", "close", "5,375.36")
    m = g._close_changes(["2026-11-11", "2026-11-10"])
    assert "chg" not in m["2026-11-10"]          # 전 거래일 발행본이 없으면 등락을 만들지 않는다
    assert m["2026-11-11"] == {"price": "5,375.36", "chg": 2.6}


def test_list_context_has_headline_hit_and_change(tmp_path, monkeypatch):
    bdir = _setup(tmp_path, monkeypatch, [
        {"date": "2026-11-10", "type": "kospi", "predicted_direction": "상승 우위", "is_correct": True},
        {"date": "2026-11-11", "type": "kospi", "predicted_direction": "하락 우위", "is_correct": False},
        {"date": "2026-11-11", "type": "us", "predicted_direction": "상승 우위", "is_correct": None},
    ])
    _page(bdir, "2026-11-10", "close", "5,239.13")
    _page(bdir, "2026-11-11", "kospi", snap={"todays_view": {"view_title": "숨 고르기"}, "reason_title": "옛 제목"})
    _page(bdir, "2026-11-11", "close", "5,375.36", snap={"market_title": "쌍끌이 랠리"})
    _page(bdir, "2026-11-11", "us", snap={"todays_view": {"view_title": "CPI 쇼크"}})
    ctx = g.build_list_context("2026-11-12", "close")
    row = next(r for r in ctx["past_rows"] if r["date"] == "2026-11-11")
    cells = {c["type"]: c for c in row["cells"]}
    assert row["chg"] == 2.6 and row["date_long"] == "11월 11일"
    assert cells["kospi"]["headline"] == "숨 고르기"   # 페이지·아카이브와 같은 문장(view_title 우선)
    assert cells["kospi"]["hit"] is False
    assert "hit" not in cells["us"]                     # 채점 전이면 표시하지 않는다
    assert cells["close"]["price"] == "5,375.36"
    html = g.make_env().get_template("sections/briefing_list.html").render(**ctx)
    assert 'class="bl-day"' in html and "숨 고르기" in html and "bl-ng" in html
    assert "코스피 +2.60%" in html


def test_list_json_has_hit_and_change(tmp_path, monkeypatch):
    bdir = _setup(tmp_path, monkeypatch, [
        {"date": "2026-11-10", "type": "us", "predicted_direction": "상승 우위", "is_correct": True},
        {"date": "2026-11-11", "type": "us", "predicted_direction": "상승 우위", "is_correct": True},
    ])
    web = tmp_path / "w"
    monkeypatch.setattr(g, "WEB_DIR", web)
    _page(bdir, "2026-11-10", "close", "5,239.13")
    _page(bdir, "2026-11-11", "close", "5,375.36")
    _page(bdir, "2026-11-11", "us", snap={"todays_view": {"view_title": "CPI 쇼크"}})
    g.write_briefings_list_json()
    s = json.loads((web / "data" / "briefings-list.json").read_text())["slots"]
    assert s["2026-11-11"]["close"]["chg"] == 2.6
    assert s["2026-11-11"]["us"]["hit"] is True and s["2026-11-11"]["us"]["headline"] == "CPI 쇼크"
