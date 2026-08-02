# send_telegram.pick_quote 동기화 로직 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 -m pytest scripts/test_pick_quote.py -v"""
import json
from datetime import datetime

import pytz

import send_telegram as st

KST = pytz.timezone("Asia/Seoul")


def _today_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def test_pick_quote_uses_quote_today_when_date_matches(tmp_path, monkeypatch):
    quote_today = tmp_path / "quote_today.json"
    quote_today.write_text(
        json.dumps({"date": _today_str(), "quote": "오늘의 명언", "author": "오늘 저자"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "QUOTE_TODAY_FILE", quote_today)
    monkeypatch.setattr(st, "GURU_QUOTES_FILE", tmp_path / "unused.json")  # 폴백 경로 안 타는지 확인용

    result = st.pick_quote()

    assert "오늘의 명언" in result
    assert "오늘 저자" in result


def test_pick_quote_falls_back_when_date_stale(tmp_path, monkeypatch):
    quote_today = tmp_path / "quote_today.json"
    quote_today.write_text(
        json.dumps({"date": "2000-01-01", "quote": "옛날 명언", "author": "옛날 저자"}, ensure_ascii=False),
        encoding="utf-8",
    )
    quotes_file = tmp_path / "guru_quotes.json"
    quotes_file.write_text(
        json.dumps([{"quote": "폴백 명언", "author": "폴백 저자"}], ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "QUOTE_TODAY_FILE", quote_today)
    monkeypatch.setattr(st, "GURU_QUOTES_FILE", quotes_file)

    result = st.pick_quote()

    assert "폴백 명언" in result
    assert "옛날 명언" not in result


def test_pick_quote_falls_back_when_quote_today_missing(tmp_path, monkeypatch):
    quotes_file = tmp_path / "guru_quotes.json"
    quotes_file.write_text(
        json.dumps([{"quote": "폴백 명언2", "author": "폴백 저자2"}], ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "QUOTE_TODAY_FILE", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(st, "GURU_QUOTES_FILE", quotes_file)

    result = st.pick_quote()

    assert "폴백 명언2" in result
