# generate_html._load_quote_today 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 -m pytest scripts/test_load_quote_today.py -v"""
import json

import generate_html as g


def test_load_quote_today_returns_dict_when_date_matches(tmp_path, monkeypatch):
    p = tmp_path / "quote_today.json"
    p.write_text(
        json.dumps({"date": "2026-08-02", "quote": "명언", "author": "저자"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(g, "QUOTE_TODAY_FILE", p)

    result = g._load_quote_today("2026-08-02")

    assert result == {"quote": "명언", "author": "저자"}


def test_load_quote_today_empty_when_date_mismatch(tmp_path, monkeypatch):
    p = tmp_path / "quote_today.json"
    p.write_text(
        json.dumps({"date": "2026-08-01", "quote": "명언", "author": "저자"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(g, "QUOTE_TODAY_FILE", p)

    assert g._load_quote_today("2026-08-02") == {}


def test_load_quote_today_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "QUOTE_TODAY_FILE", tmp_path / "does_not_exist.json")

    assert g._load_quote_today("2026-08-02") == {}


def test_load_quote_today_empty_when_malformed(tmp_path, monkeypatch):
    p = tmp_path / "quote_today.json"
    p.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(g, "QUOTE_TODAY_FILE", p)

    assert g._load_quote_today("2026-08-02") == {}
