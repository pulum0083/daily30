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
