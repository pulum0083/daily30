"""날짜가 다른 잔존 파일·손상된 파일이 브리핑에 들어가지 않는지 검증한다."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from briefing_data import read_dated_payload, read_snapshot_payload
import generate_html as gh
from gen_testkit import gen_patch  # noqa: E402


@pytest.mark.parametrize("raw", ["{", "[]", "null", '"text"', "123", '{"date":"2026-11-16"}'])
def test_bad_or_stale_file_is_omitted_without_changing_snapshot(tmp_path, raw):
    path = tmp_path / "signal.json"
    path.write_text(raw, encoding="utf-8")
    analysis = {}
    assert read_snapshot_payload(analysis, "signal", tmp_path, "2026-11-17") is None
    assert analysis == {}


def test_missing_file_is_optional(tmp_path):
    assert read_dated_payload(tmp_path / "absent.json", "2026-11-17") is None


def test_matching_file_is_saved_once_and_snapshot_wins(tmp_path):
    path = tmp_path / "signal.json"
    data = {"date": "2026-11-17", "items": []}
    path.write_text(json.dumps(data), encoding="utf-8")
    analysis = {}
    assert read_snapshot_payload(analysis, "signal", tmp_path, data["date"]) == data
    path.write_text('{"date":"2026-11-18","items":[1]}', encoding="utf-8")
    assert read_snapshot_payload(analysis, "signal", tmp_path, "2026-11-17") is analysis["signal"]
    assert analysis["signal"] == data


def test_empty_snapshot_is_preserved(tmp_path):
    (tmp_path / "signal.json").write_text('{"date":"2026-11-17","items":[1]}', encoding="utf-8")
    assert read_snapshot_payload({"signal": {}}, "signal", tmp_path, "2026-11-17") == {}


@pytest.mark.parametrize("reader,filename", [
    (gh._read_monthly_ma5, "monthly_ma5.json"),
    (gh._read_nasdaq_overheat, "nasdaq_overheat.json"),
    (lambda date: gh.read_sp500_ma200({}, date), "sp500_ma200.json"),
    (lambda date: gh.read_breakout_watch({}, date), "breakout_watch.json"),
])
def test_section_readers_reject_non_object_json(tmp_path, monkeypatch, reader, filename):
    gen_patch(monkeypatch, "DATA_DIR", tmp_path)
    (tmp_path / filename).write_text("[]", encoding="utf-8")
    assert reader("2026-11-17") is None


@pytest.mark.parametrize("raw", ["{", "[]", "null"])
def test_optional_news_corruption_does_not_abort_render(tmp_path, monkeypatch, raw):
    gen_patch(monkeypatch, "BASE_DIR", tmp_path)
    (tmp_path / "data").mkdir()
    for filename in ("ib_korea_views.json", "domestic_issues.json"):
        (tmp_path / "data" / filename).write_text(raw, encoding="utf-8")
    assert gh.build_ib_korea_views("2026-11-17") == {"ib_korea_views": []}
    assert gh.build_domestic_issues("2026-11-17") == {"domestic_issues": [], "domestic_window_label": ""}
