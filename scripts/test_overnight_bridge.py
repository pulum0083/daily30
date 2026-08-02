# fetch_data.fetch_overnight_bridge 순수함수 단위 테스트 (네트워크 없음).
"""실행: python3 -m pytest scripts/test_overnight_bridge.py -v"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_data as m  # noqa: E402

KST = m.KST


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _snapshot(generated_at: str) -> dict:
    return {
        "generated_at": generated_at,
        "stocks": {
            "005930": {"name": "삼성전자", "change_pct": 28.38},
            "000660": {"name": "SK하이닉스", "change_pct": 24.0},
            "267260": {"name": "HD현대일렉트릭", "change_pct": 20.13},
            "010120": {"name": "LS일렉트릭", "change_pct": 18.0},
        },
    }


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
    today = datetime.now(KST)
    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(today)))

    assert rows is not None
    sectors = {r["sector"] for r in rows}
    assert "조선" not in sectors
    assert len(rows) <= 7

    semicon = next(r for r in rows if r["sector"] == "반도체")
    assert semicon["us_change"] == 8.5
    assert semicon["kr_change"] == 26.19  # (28.38+24.0)/2
    assert semicon["gap_pp"] == 17.7


def test_one_us_bellwether_missing_drops_only_that_sector():
    today = datetime.now(KST)
    macro = _macro()
    del macro["SOXX"]  # 반도체 미국 측 결측

    rows = m.fetch_overnight_bridge(macro, _snapshot(_iso(today)))

    sectors = {r["sector"] for r in rows}
    assert "반도체" not in sectors
    assert "전력기기" in sectors  # 나머지는 정상


def test_monday_case_not_treated_as_stale():
    # 금요일 16:33 생성 스냅샷을 월요일 07:25에 읽는 상황 (날짜 차이 3일)
    friday = datetime.now(KST) - timedelta(days=3)
    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(friday)))

    assert rows is not None
    assert len(rows) > 0


def test_stale_snapshot_returns_none():
    old = datetime.now(KST) - timedelta(days=6)
    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(old)))

    assert rows is None


def test_all_sectors_fail_returns_none():
    rows = m.fetch_overnight_bridge({}, _snapshot(_iso(datetime.now(KST))))

    assert rows is None


def test_2026_07_27_incident_replay_shows_double_count():
    """§24 실사고 리플레이 — EWY -6.27%는 같은 날 코스피 -5.72% 급락을 이미 반영한 값이었다.
    반도체 섹터로 근사 재현: 미국이 크게 밀렸는데 한국도 비슷하게 밀리면 gap이 0에 가까워야
    '이미 반영됨'이 드러난다(선반영이 거의 없다는 뜻)."""
    macro = _macro(SOXX={"change_pct": -4.25})
    snapshot = {
        "generated_at": _iso(datetime.now(KST)),
        "stocks": {
            "005930": {"name": "삼성전자", "change_pct": -5.72},
            "000660": {"name": "SK하이닉스", "change_pct": -5.72},
        },
    }

    rows = m.fetch_overnight_bridge(macro, snapshot)

    semicon = next(r for r in rows if r["sector"] == "반도체")
    assert semicon["gap_pp"] < 3.0  # 미국도 이미 밀렸으므로 갭이 크지 않아야 함(이중계상 아님을 확인)
