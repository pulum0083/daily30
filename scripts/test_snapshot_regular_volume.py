# 종목 스냅샷 거래량 회귀 테스트 — 오늘 정규장 거래량을 못 구하면 전날 거래량을 오늘 값으로 쓰지 않는지(§48)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_stocks_snapshot as bss  # noqa: E402


def _rows(last_volume):
    rows = [{"localDate": f"202608{i:02d}", "closePrice": 1800000.0 + i, "accumulatedTradingVolume": 3000000,
             "foreignRetentionRate": 50.0} for i in range(1, 21)]
    rows.append({"localDate": "20260914", "closePrice": 1697000.0, "accumulatedTradingVolume": last_volume,
                 "foreignRetentionRate": 50.27})
    return rows


def _patch(monkeypatch, rows):
    monkeypatch.setattr(bss, "_naver_day_rows", lambda code: rows)
    monkeypatch.setattr(bss, "_naver_supply5", lambda code: None)
    monkeypatch.setattr(bss, "_naver_financials", lambda code: None)


def test_regular_session_volume_is_today_volume(monkeypatch):
    _patch(monkeypatch, _rows(3742905))       # 9/14 SK하이닉스 정규장 1분봉 합
    rec, bar_date = bss._build_one("000660", "SK하이닉스", "semicon", "kr")
    assert bar_date == "2026-09-14"
    assert rec["close"] == 1697000.0
    assert rec["vol"] == 3742905
    assert rec["vol_avg20"] == int((3000000 * 19 + 3742905) / 20)


def test_missing_today_volume_does_not_slide_to_previous_day(monkeypatch):
    _patch(monkeypatch, _rows(None))          # kr_official_closes가 정규장 거래량을 못 구해 비운 봉
    rec, _ = bss._build_one("000660", "SK하이닉스", "semicon", "kr")
    assert rec["close"] == 1697000.0
    assert "vol" not in rec                    # 8/20 거래량 3,000,000을 9/14 값으로 쓰지 않는다
    assert "vol_avg20" not in rec
