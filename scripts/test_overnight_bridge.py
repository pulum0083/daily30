# fetch_data.fetch_overnight_bridge 순수함수 단위 테스트 (네트워크 없음).
"""실행: python3 -m pytest scripts/test_overnight_bridge.py -v"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_data as m  # noqa: E402
from session_label import prev_kospi_session  # noqa: E402

KST = m.KST

UNIVERSE_PATH = Path(__file__).resolve().parent / "config" / "stock_universe.json"
BRIDGE_SECTORS = ["semicon", "power", "defense", "battery", "auto", "bio", "finance"]

# 금요일 16:33 스냅샷을 월요일 07:25에 읽는 정상 시나리오(중간 공휴일 없음, 실제로 확인함).
_SNAP_DATE = date(2026, 7, 24)  # 금
_TODAY = date(2026, 7, 27)  # 월
assert prev_kospi_session(_TODAY) == _SNAP_DATE  # 테스트 날짜 자체가 틀리면 전체가 무의미하므로 방어적으로 확인

# §24 실사고(2026-07-15) 재현용 — 07-13(월) 스냅샷을 07-15(수)에 읽으면 화요일(07-14) 세션이
# 통째로 빠진다. prev_kospi_session(2026-07-15) == 2026-07-14로 실제 확인함.
_INCIDENT_SNAP_DATE = date(2026, 7, 13)
_INCIDENT_TODAY = date(2026, 7, 15)
assert prev_kospi_session(_INCIDENT_TODAY) == date(2026, 7, 14)


def _iso(d: date) -> str:
    return f"{d.isoformat()}T16:33:00+09:00"


# 반도체만 기존 예상값(삼성전자 28.38 / SK하이닉스 24.0 → kr_change 26.19)을 유지하고,
# 나머지 6개 섹터는 7개 섹터를 모두 실제로 돌리기 위한 임의의 고정값이다.
_FIXED_PCT = {
    "semicon": [28.38, 24.0],
    "power": [20.13, 18.0],
    "defense": [10.0, 8.0],
    "battery": [15.0, 12.0],
    "auto": [5.0, 3.0],
    "bio": [7.0, 6.0],
    "finance": [-2.0, -1.0],
}


def _snapshot(generated_at: str) -> dict:
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))["sectors"]
    stocks = {}
    for sector in BRIDGE_SECTORS:
        top2 = universe[sector]["stocks"][:2]
        for stock, pct in zip(top2, _FIXED_PCT[sector]):
            stocks[stock["code"]] = {"name": stock["name"], "change_pct": pct}
    return {"generated_at": generated_at, "stocks": stocks}


def _macro(**overrides) -> dict:
    base = {
        "SOXX": {"change_pct": 8.5},
        "GEV": {"change_pct": 6.0}, "VRT": {"change_pct": 5.08},
        "ITA": {"change_pct": 0.79},
        "LIT": {"change_pct": 4.6},
        "TSLA": {"change_pct": 0.5}, "F": {"change_pct": 0.28},
        "XBI": {"change_pct": 2.4},
        "JPM": {"change_pct": -0.1}, "KBE": {"change_pct": -0.38},
    }
    base.update(overrides)
    return base


def test_normal_case_returns_seven_sectors_no_ship():
    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(_SNAP_DATE)), today=_TODAY)

    assert rows is not None
    sectors = {r["sector"] for r in rows}
    assert "조선" not in sectors
    assert len(rows) == 7

    semicon = next(r for r in rows if r["sector"] == "반도체")
    assert semicon["us_change"] == 8.5
    assert semicon["kr_change"] == 26.19  # (28.38+24.0)/2
    assert semicon["gap_pp"] == 17.7
    assert semicon["kr_session_date"] == "2026-07-24"


def test_one_us_bellwether_missing_drops_only_that_sector():
    macro = _macro()
    del macro["SOXX"]  # 반도체 미국 측 결측

    rows = m.fetch_overnight_bridge(macro, _snapshot(_iso(_SNAP_DATE)), today=_TODAY)

    sectors = {r["sector"] for r in rows}
    assert "반도체" not in sectors
    assert "전력기기" in sectors  # 나머지는 정상


def test_us_label_drops_missing_ticker_name():
    """Fix 2 — VRT가 결측이면 라벨도 GEV 하나만 남아야 한다(§20, 데이터 없는 티커를 계속 가리키지 않음)."""
    macro = _macro()
    del macro["VRT"]

    rows = m.fetch_overnight_bridge(macro, _snapshot(_iso(_SNAP_DATE)), today=_TODAY)

    power = next(r for r in rows if r["sector"] == "전력기기")
    assert power["us_label"] == "GE Vernova"
    assert power["us_change"] == 6.0  # GEV 단독


def test_us_label_full_multi_ticker_sectors_unchanged():
    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(_SNAP_DATE)), today=_TODAY)

    power = next(r for r in rows if r["sector"] == "전력기기")
    auto = next(r for r in rows if r["sector"] == "자동차")
    finance = next(r for r in rows if r["sector"] == "금융")
    assert power["us_label"] == "GE Vernova·Vertiv"
    assert auto["us_label"] == "테슬라·포드"
    assert finance["us_label"] == "JP모건·은행 ETF"


def test_monday_case_not_treated_as_stale():
    # 금요일 16:33 생성 스냅샷을 월요일 07:25에 읽는 상황(3일 벌어져 있지만 직전 개장일과 정확히 일치).
    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(_SNAP_DATE)), today=_TODAY)

    assert rows is not None
    assert len(rows) > 0


def test_incident_2026_07_15_session_mismatch_returns_none():
    """2026-07-15 실사고 재현 — 화요일(07-14) 세션이 빠진 채 월요일(07-13) 스냅샷을 읽으면 안 된다."""
    rows = m.fetch_overnight_bridge(
        _macro(), _snapshot(_iso(_INCIDENT_SNAP_DATE)), today=_INCIDENT_TODAY
    )

    assert rows is None


def test_all_sectors_fail_returns_none():
    rows = m.fetch_overnight_bridge({}, _snapshot(_iso(_SNAP_DATE)), today=_TODAY)

    assert rows is None


def test_2026_07_27_incident_replay_shows_double_count():
    """§24 실사고 리플레이 — EWY -6.27%는 같은 날 코스피 -5.72% 급락을 이미 반영한 값이었다.
    반도체 섹터로 근사 재현: 미국이 크게 밀렸는데 한국도 비슷하게 밀리면 gap이 0에 가까워야
    '이미 반영됨'이 드러난다(선반영이 거의 없다는 뜻)."""
    macro = _macro(SOXX={"change_pct": -4.25})
    snapshot = _snapshot(_iso(_SNAP_DATE))
    snapshot["stocks"]["005930"] = {"name": "삼성전자", "change_pct": -5.72}
    snapshot["stocks"]["000660"] = {"name": "SK하이닉스", "change_pct": -5.72}

    rows = m.fetch_overnight_bridge(macro, snapshot, today=_TODAY)

    semicon = next(r for r in rows if r["sector"] == "반도체")
    assert semicon["us_change"] == -4.25
    assert semicon["kr_change"] == -5.72
    assert semicon["gap_pp"] == -1.5  # round(-5.72 - (-4.25), 1) — 정확한 값으로 고정(부호까지)


def test_non_dict_macro_returns_none():
    rows = m.fetch_overnight_bridge("not-a-dict", _snapshot(_iso(_SNAP_DATE)), today=_TODAY)
    assert rows is None


def test_non_dict_snapshot_returns_none():
    rows = m.fetch_overnight_bridge(_macro(), "not-a-dict", today=_TODAY)
    assert rows is None


def test_universe_load_failure_returns_none(monkeypatch, tmp_path):
    # BASE_DIR을 stock_universe.json이 없는 경로로 바꿔 로드 실패를 강제한다.
    monkeypatch.setattr(m, "BASE_DIR", tmp_path)

    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(_SNAP_DATE)), today=_TODAY)

    assert rows is None


def test_snapshot_stocks_as_list_returns_none():
    snapshot = _snapshot(_iso(_SNAP_DATE))
    snapshot["stocks"] = ["005930", "000660"]  # 딕셔너리가 아니라 리스트

    rows = m.fetch_overnight_bridge(_macro(), snapshot, today=_TODAY)

    assert rows is None
