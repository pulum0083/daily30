# 첫 화면 요약(home-summary.json) 순수 함수 테스트 — 시초가 채점이 check_accuracy와 같은 규칙인지(§68)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_home_summary as hs  # noqa: E402

DAYS = [{"date": "2026-10-21", "open": 5700.0, "close": 5735.66},
        {"date": "2026-10-22", "open": 5670.27, "close": 5533.77},
        {"date": "2026-10-23", "open": 5403.17, "close": 5550.30}]
RECS = [{"type": "kospi", "date": "2026-10-22", "predicted_direction": "상승 우위", "basis": "open"},
        {"type": "kospi", "date": "2026-10-23", "predicted_direction": "하락 우위", "basis": "open"},
        {"type": "kospi", "date": "2026-10-23", "predicted_direction": "상승 우위"},          # 종가 기준 옛 기록 — 제외
        {"type": "us", "date": "2026-10-23", "predicted_direction": "상승 우위", "basis": "open"}]


def test_rows_and_open_gap_scoring():
    out = hs.build("2026-10-23", DAYS, RECS)
    assert [r["date"] for r in out["kospi_days"]] == ["2026-10-22", "2026-10-23"]
    assert out["kospi_days"][1]["pct"] == 0.3 and out["kospi_days"][1]["open_pct"] == -2.36
    assert out["scores"] == [
        {"date": "2026-10-22", "direction": "상승 우위", "open_pct": -1.14, "ok": False},
        {"date": "2026-10-23", "direction": "하락 우위", "open_pct": -2.36, "ok": True},
    ]


def test_future_days_ignored_and_too_few_days_none():
    assert hs.build("2026-10-22", DAYS, RECS)["kospi_days"][-1]["date"] == "2026-10-22"
    assert hs.build("2026-10-21", DAYS, RECS) is None


def test_week_dates_same_monday_to_sunday():
    rows = [{"date": d} for d in ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-23"]]
    assert hs.week_dates(rows) == ["2026-10-19", "2026-10-20", "2026-10-23"]   # 21·22일이 빠진 주도 그 주의 거래일만
    assert hs.week_dates([]) == []


UNI = {"sectors": {"semicon": {"label": "반도체", "stocks": [{"code": "A"}, {"code": "B"}]},
                   "bio": {"label": "바이오", "stocks": [{"code": "C"}]}}}


def test_sectors_week_uses_close_before_week_start():
    snap = {"session_date": "2026-10-23",
            "stocks": {"A": {"spark20": [90, 100, 101, 102, 110]},          # 이번 주 3거래일 → 기준은 100
                       "B": {"spark20": [50, 50, 49, 48, 45]},
                       "C": {"spark20": [10, 10, 10, 11, 11]}}}
    out = hs.sectors_week(snap, UNI, ["2026-10-21", "2026-10-22", "2026-10-23"])
    assert [r["key"] for r in out] == ["bio", "semicon"]
    assert out[0]["pct"] == 10.0 and out[1]["pct"] == 0.0 and out[1]["n"] == 2   # (10% + -10%) / 2


def test_sectors_week_skips_when_snapshot_is_another_session():
    snap = {"session_date": "2026-10-22", "stocks": {"A": {"spark20": [1, 2, 3, 4]}}}
    assert hs.sectors_week(snap, UNI, ["2026-10-21", "2026-10-22", "2026-10-23"]) == []
    assert hs.sectors_week({}, UNI, ["2026-10-23"]) == []
