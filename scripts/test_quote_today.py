# call_claude._save_todays_quote / _load_todays_quote_for_telegram 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 -m pytest scripts/test_quote_today.py -v"""
import json

import call_claude as cc


def test_save_todays_quote_writes_file(tmp_path, monkeypatch):
    quotes_file = tmp_path / "guru_quotes.json"
    quotes_file.write_text(
        json.dumps([{"quote": "테스트 명언", "author": "테스트 저자"}], ensure_ascii=False),
        encoding="utf-8",
    )
    out_file = tmp_path / "quote_today.json"
    monkeypatch.setattr(cc, "GURU_QUOTES_FILE", quotes_file)
    monkeypatch.setattr(cc, "QUOTE_TODAY_FILE", out_file)

    cc._save_todays_quote("2026-08-02")

    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved == {"date": "2026-08-02", "quote": "테스트 명언", "author": "테스트 저자"}


def test_save_todays_quote_missing_source_is_noop(tmp_path, monkeypatch):
    out_file = tmp_path / "quote_today.json"
    monkeypatch.setattr(cc, "GURU_QUOTES_FILE", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(cc, "QUOTE_TODAY_FILE", out_file)

    cc._save_todays_quote("2026-08-02")  # 예외 없이 조용히 아무 것도 안 함

    assert not out_file.exists()


def test_save_todays_quote_empty_list_is_noop(tmp_path, monkeypatch):
    quotes_file = tmp_path / "guru_quotes.json"
    quotes_file.write_text("[]", encoding="utf-8")
    out_file = tmp_path / "quote_today.json"
    monkeypatch.setattr(cc, "GURU_QUOTES_FILE", quotes_file)
    monkeypatch.setattr(cc, "QUOTE_TODAY_FILE", out_file)

    cc._save_todays_quote("2026-08-02")

    assert not out_file.exists()
