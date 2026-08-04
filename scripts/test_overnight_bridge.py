# fetch_data.fetch_overnight_bridge 순수함수 단위 테스트 (네트워크 없음).
"""실행: python3 -m pytest scripts/test_overnight_bridge.py -v"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_data as m  # noqa: E402
import session_label  # noqa: E402
from session_label import prev_kospi_session  # noqa: E402

UNIVERSE_PATH = Path(__file__).resolve().parent / "config" / "stock_universe.json"
BRIDGE_SECTORS = ["semicon", "power", "defense", "battery", "auto", "bio", "finance"]

# 금요일 스냅샷을 월요일 07:25에 읽는 정상 시나리오, §24 실사고(2026-07-15) 재현 시나리오에 쓰는
# 날짜 쌍. prev_kospi_session의 실제 반환값을 아래 test_fixture_dates_are_valid_kospi_sessions에서
# 검증한다 — "확인했다고 가정"하지 않는다.
_SNAP_DATE = date(2026, 7, 24)  # 금
_TODAY = date(2026, 7, 27)  # 월(중간 공휴일 없음)
_INCIDENT_SNAP_DATE = date(2026, 7, 13)  # 월 스냅샷
_INCIDENT_TODAY = date(2026, 7, 15)  # 수 — 화(07-14) 세션이 통째로 빠지는 실사고 시나리오


def test_fixture_dates_are_valid_kospi_sessions():
    """이 파일 전체가 기대는 날짜 전제 — 모듈 임포트 시 조용히 죽는 assert가 아니라
    이름 있는 테스트로 실패하도록 만든다(pytest -O 하에서도 사라지지 않음)."""
    assert prev_kospi_session(_TODAY) == _SNAP_DATE
    assert prev_kospi_session(_INCIDENT_TODAY) == date(2026, 7, 14)
    assert _INCIDENT_SNAP_DATE != date(2026, 7, 14)  # 스냅샷 날짜가 실제 직전 개장일과 달라야 사고가 재현됨


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


def _kr_top2_all_sectors() -> dict:
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))["sectors"]
    stocks = {}
    for sector in BRIDGE_SECTORS:
        top2 = universe[sector]["stocks"][:2]
        for stock, pct in zip(top2, _FIXED_PCT[sector]):
            stocks[stock["code"]] = {"name": stock["name"], "change_pct": pct}
    return stocks


def _snapshot(session_date, stocks: dict) -> dict:
    """session_date: date 또는 'YYYY-MM-DD' 문자열. build_stocks_snapshot.py가 실제로
    내보내는 형태(순수 날짜 문자열, 시각 없음)를 그대로 흉내낸다."""
    sd = session_date.isoformat() if isinstance(session_date, date) else session_date
    return {
        "generated_at": f"{sd}T16:33:00+09:00",
        "session_date": sd,
        "stocks": stocks,
    }


# 미국 레그는 fetch_bridge_us_changes()가 만드는 {change_pct, session_date} 형태다.
# session_date는 한국 레그(_SNAP_DATE)와 같은 세션이어야 채택된다 — 한국 세션 D의 종가가
# 02:30 ET에 확정된 뒤 같은 ET 날짜 D의 미국 정규장이 열리므로, 평일에는 두 날짜가 같다.
_US_SESSION = _SNAP_DATE.isoformat()


def _us(**overrides) -> dict:
    """미국 레그 픽스처. 값만 주면 session_date는 한국 레그와 같은 세션으로 채운다.
    overrides는 등락률(float) 또는 완전한 dict 둘 다 받는다."""
    base = {
        "SOXX": 8.5,
        "GEV": 6.0, "VRT": 5.08,
        "ITA": 0.79,
        "LIT": 4.6,
        "TSLA": 0.5, "F": 0.28,
        "XBI": 2.4,
        "JPM": -0.1, "KBE": -0.38,
    }
    out = {t: {"change_pct": v, "session_date": _US_SESSION} for t, v in base.items()}
    for t, v in overrides.items():
        out[t] = v if isinstance(v, dict) else {"change_pct": v, "session_date": _US_SESSION}
    return out


def test_normal_case_returns_seven_sectors_no_ship():
    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

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
    us = _us()
    del us["SOXX"]  # 반도체 미국 측 결측

    rows = m.fetch_overnight_bridge(us, _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    sectors = {r["sector"] for r in rows}
    assert "반도체" not in sectors
    assert "전력기기" in sectors  # 나머지는 정상


def test_us_label_drops_missing_ticker_name():
    """VRT가 결측이면 라벨도 GEV 하나만 남아야 한다(§20, 데이터 없는 티커를 계속 가리키지 않음)."""
    us = _us()
    del us["VRT"]

    rows = m.fetch_overnight_bridge(us, _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    power = next(r for r in rows if r["sector"] == "전력기기")
    assert power["us_label"] == "GE Vernova"
    assert power["us_change"] == 6.0  # GEV 단독


def test_us_label_full_multi_ticker_sectors_unchanged():
    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    power = next(r for r in rows if r["sector"] == "전력기기")
    auto = next(r for r in rows if r["sector"] == "자동차")
    finance = next(r for r in rows if r["sector"] == "금융")
    assert power["us_label"] == "GE Vernova·Vertiv"
    assert auto["us_label"] == "테슬라·포드"
    # 금융은 ETF 단독 섹터라 개별주(JPM)가 섞이지 않는다.
    assert finance["us_label"] == "은행 ETF"
    assert finance["us_change"] == -0.38  # KBE 단독


def test_us_label_name_change_in_universe_propagates(monkeypatch, tmp_path):
    """Important 2 — 표시 이름이 코드에 박혀 있지 않고 stock_universe.json에서 온다는 것을
    실제로 이름을 바꿔서 증명한다. 코드에 하드코딩돼 있었다면 이 테스트는 실패한다."""
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    for b in universe["sectors"]["defense"]["bellwethers"]:
        if b["t"] == "ITA":
            b["name"] = "테스트변경방산ETF"
    cfg_dir = tmp_path / "scripts" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "stock_universe.json").write_text(json.dumps(universe, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(m, "BASE_DIR", tmp_path)

    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    defense = next(r for r in rows if r["sector"] == "방산")
    assert defense["us_label"] == "테스트변경방산ETF"


def test_us_ticker_not_in_bellwethers_is_treated_as_missing(monkeypatch, tmp_path):
    """티커에 대응하는 이름을 bellwethers에서 못 찾으면 검증되지 않은 이름을 지어내지 않고
    결측 취급한다 — 섹터 전체가 아니라 그 티커만 빠진다(나머지 티커가 있으면 그걸로 계속됨)."""
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    universe["sectors"]["power"]["bellwethers"] = [
        b for b in universe["sectors"]["power"]["bellwethers"] if b["t"] != "VRT"
    ]
    cfg_dir = tmp_path / "scripts" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "stock_universe.json").write_text(json.dumps(universe, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(m, "BASE_DIR", tmp_path)

    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    power = next(r for r in rows if r["sector"] == "전력기기")
    assert power["us_label"] == "GE Vernova"  # VRT는 이름을 못 찾아 빠지고 GEV만 남음


def test_kr_label_uses_top2_only_even_with_more_stocks_available():
    """Important 3 — [:2] 슬라이스가 실제로 지켜지는지 3번째 종목까지 있는 픽스처로 검증한다.
    기존 픽스처는 섹터마다 종목을 정확히 2개만 담아서 [:2]→[:3] 같은 회귀를 통과시켰다."""
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))["sectors"]
    semicon_stocks = universe["semicon"]["stocks"]
    stocks = {
        semicon_stocks[0]["code"]: {"name": semicon_stocks[0]["name"], "change_pct": 10.0},
        semicon_stocks[1]["code"]: {"name": semicon_stocks[1]["name"], "change_pct": 8.0},
        # 3번째 종목 — 유효한 데이터가 있어도 top2 밖이라 절대 반영되면 안 됨
        semicon_stocks[2]["code"]: {"name": semicon_stocks[2]["name"], "change_pct": 999.0},
    }

    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, stocks), today=_TODAY)

    semicon = next(r for r in rows if r["sector"] == "반도체")
    assert semicon["kr_label"] == f"{semicon_stocks[0]['name']}·{semicon_stocks[1]['name']}"
    assert semicon["kr_change"] == 9.0  # (10.0+8.0)/2 — 999.0 포함되면 안 됨


def test_kr_label_reflects_only_stocks_with_data_not_full_universe_config():
    """Important 3 — 2번째 대표종목의 시세 데이터가 없으면 라벨도 1개만 남아야 한다.
    universe.json에 설정된 이름을 데이터 유무와 무관하게 전부 붙이는 회귀를 잡는다(§20의
    KR판 재발 방지 — US 쪽에서 고친 것과 정확히 같은 버그가 KR 쪽에서도 날 수 있음을 검증)."""
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))["sectors"]
    power_stocks = universe["power"]["stocks"]
    stocks = {
        power_stocks[0]["code"]: {"name": power_stocks[0]["name"], "change_pct": 5.0},
        # power_stocks[1](2번째 대표종목)은 의도적으로 누락 — 그날 수집 실패 시나리오
    }

    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, stocks), today=_TODAY)

    power = next(r for r in rows if r["sector"] == "전력기기")
    assert power["kr_label"] == power_stocks[0]["name"]
    assert power["kr_change"] == 5.0


def test_session_date_present_and_matching_returns_rows():
    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    assert rows is not None
    assert len(rows) > 0


def test_session_date_missing_returns_none():
    """generated_at은 있어도 session_date가 없으면 폴백하지 않고 섹션을 생략한다 — 구버전
    스냅샷(이번 수정 이전 형식)을 읽었을 때 §24 스큐를 그대로 재현하지 않기 위한 핵심 방어."""
    snap = _snapshot(_SNAP_DATE, _kr_top2_all_sectors())
    del snap["session_date"]

    rows = m.fetch_overnight_bridge(_us(), snap, today=_TODAY)

    assert rows is None


def test_session_date_unparseable_returns_none():
    snap = _snapshot(_SNAP_DATE, _kr_top2_all_sectors())
    snap["session_date"] = "not-a-date"

    rows = m.fetch_overnight_bridge(_us(), snap, today=_TODAY)

    assert rows is None


def test_session_date_mismatched_returns_none_incident_2026_07_15():
    """§24 실사고 재현 — 화요일(07-14) 세션이 빠진 채 월요일(07-13) session_date를 읽으면 안 된다."""
    rows = m.fetch_overnight_bridge(
        _us(), _snapshot(_INCIDENT_SNAP_DATE, _kr_top2_all_sectors()), today=_INCIDENT_TODAY
    )

    assert rows is None


def test_prev_kospi_session_none_returns_none(monkeypatch):
    """직전 코스피 개장일 자체를 못 찾는 방어적 분기 — 실제 날짜로는 재현되지 않으므로
    (holiday_check가 최소 주 5일 개장을 보장) prev_kospi_session을 직접 강제한다.
    fetch_data.py는 `scripts.session_label`을 먼저 시도하므로(house order) 두 임포트 경로
    ("session_label"과 "scripts.session_label")가 서로 다른 모듈 객체일 수 있어 둘 다 패치한다."""
    monkeypatch.setattr(session_label, "prev_kospi_session", lambda d: None)
    try:
        import scripts.session_label as scripts_session_label
        monkeypatch.setattr(scripts_session_label, "prev_kospi_session", lambda d: None)
    except ImportError:
        pass

    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    assert rows is None


def test_all_sectors_fail_returns_none():
    rows = m.fetch_overnight_bridge({}, _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    assert rows is None


def test_2026_07_27_incident_replay_shows_double_count():
    """§24 실사고 리플레이 — EWY -6.27%는 같은 날 코스피 -5.72% 급락을 이미 반영한 값이었다.
    반도체 섹터로 근사 재현: 미국이 크게 밀렸는데 한국도 비슷하게 밀리면 gap이 0에 가까워야
    '이미 반영됨'이 드러난다(선반영이 거의 없다는 뜻)."""
    us = _us(SOXX=-4.25)
    stocks = _kr_top2_all_sectors()
    stocks["005930"] = {"name": "삼성전자", "change_pct": -5.72}
    stocks["000660"] = {"name": "SK하이닉스", "change_pct": -5.72}

    rows = m.fetch_overnight_bridge(us, _snapshot(_SNAP_DATE, stocks), today=_TODAY)

    semicon = next(r for r in rows if r["sector"] == "반도체")
    assert semicon["us_change"] == -4.25
    assert semicon["kr_change"] == -5.72
    assert semicon["gap_pp"] == -1.5  # round(-5.72 - (-4.25), 1) — 정확한 값으로 고정(부호까지)


def test_bool_change_pct_treated_as_missing_not_as_one():
    """isinstance(True, int)가 True라서 change_pct: true가 1.0%로 둔갑하지 않는지 확인."""
    us = _us(SOXX={"change_pct": True, "session_date": _US_SESSION})

    rows = m.fetch_overnight_bridge(us, _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    sectors = {r["sector"] for r in rows}
    assert "반도체" not in sectors  # SOXX가 결측 취급돼 반도체 섹터 자체가 생략됨


def test_non_dict_us_changes_returns_none():
    rows = m.fetch_overnight_bridge("not-a-dict", _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)
    assert rows is None


def test_non_dict_snapshot_returns_none():
    rows = m.fetch_overnight_bridge(_us(), "not-a-dict", today=_TODAY)
    assert rows is None


def test_universe_load_failure_returns_none(monkeypatch, tmp_path):
    # BASE_DIR을 stock_universe.json이 없는 경로로 바꿔 로드 실패를 강제한다.
    monkeypatch.setattr(m, "BASE_DIR", tmp_path)

    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    assert rows is None


def test_snapshot_stocks_as_list_returns_none():
    snapshot = _snapshot(_SNAP_DATE, _kr_top2_all_sectors())
    snapshot["stocks"] = ["005930", "000660"]  # 딕셔너리가 아니라 리스트

    rows = m.fetch_overnight_bridge(_us(), snapshot, today=_TODAY)

    assert rows is None


def test_nonfinite_change_pct_treated_as_missing():
    """NaN·Infinity도 float이라 타입 검사만으론 통과한다 — 결측으로 걸러 섹터를 생략한다.

    파이썬 표준 json이 NaN·Infinity 리터럴을 그대로 읽고 쓰므로(§23/§28 수동 정정 절차),
    스냅샷을 손으로 고치다 실제로 섞여 들어올 수 있다. 통과시키면 평균이 NaN이 되어
    그 섹터 행이 통째로 오염된다.
    """
    for bad in (float("nan"), float("inf"), float("-inf")):
        us = _us(SOXX={"change_pct": bad, "session_date": _US_SESSION})
        rows = m.fetch_overnight_bridge(us, _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

        assert "반도체" not in {r["sector"] for r in rows}, bad
        # 나머지 섹터는 정상 진행 — 한 티커의 오염이 섹션 전체를 죽이지 않는다.
        assert len(rows) == 6, bad


def test_nonfinite_kr_change_pct_treated_as_missing():
    stocks = _kr_top2_all_sectors()
    # 반도체 한국 대표 2종을 모두 NaN으로 오염시키면 그 섹터만 빠진다.
    for code in ("005930", "000660"):
        stocks[code] = {**stocks[code], "change_pct": float("nan")}

    rows = m.fetch_overnight_bridge(_us(), _snapshot(_SNAP_DATE, stocks), today=_TODAY)

    assert "반도체" not in {r["sector"] for r in rows}


# ── 미국 레그가 정규장 종가-종가인지 고정하는 회귀 테스트 ──────────────────────
# 07:25 KST = 18:25 ET는 미국 애프터마켓 한복판이라, get_ticker_full() 경로로 되돌리면
# _extended_hours_price()가 항상 이겨 시간외 체결가가 미국 레그에 실린다(§26). 아래 테스트는
# 호출 형태가 아니라 **결과값의 성질**을 고정한다 — 시간외 가격을 주입해도 정규장 값이 나와야 한다.


class _FakeDailyHistory:
    """_yf_history(period="1mo")가 돌려주는 일봉 프레임의 최소 흉내."""

    def __init__(self, closes, last_date):
        import datetime as _dt
        self._closes = list(closes)
        self._dates = [last_date - _dt.timedelta(days=len(closes) - 1 - i) for i in range(len(closes))]

    def __len__(self):
        return len(self._closes)

    def __getitem__(self, key):
        assert key == "Close"
        return self

    def dropna(self):
        return self

    @property
    def iloc(self):
        return self._closes

    @property
    def index(self):
        return [type("_Ts", (), {"date": staticmethod(lambda d=d: d)})() for d in self._dates]


def _patch_daily(monkeypatch, closes, last_date):
    calls = []

    def fake_hist(ticker, **kwargs):
        calls.append((ticker, kwargs))
        return _FakeDailyHistory(closes, last_date)

    monkeypatch.setattr(m, "_yf_history", fake_hist)
    return calls


def test_us_leg_is_regular_close_to_close_and_carries_session_date(monkeypatch):
    calls = _patch_daily(monkeypatch, [90.0, 100.0, 103.0], _SNAP_DATE)

    rec = m._regular_session_change("GEV")

    assert rec == {"change_pct": 3.0, "session_date": _SNAP_DATE.isoformat()}
    # 일봉만 읽는다 — 5분봉·prepost를 켜면 정규장 종가-종가가 아니게 된다.
    _, kwargs = calls[0]
    assert kwargs.get("period") == "1mo"
    assert not kwargs.get("prepost")
    assert kwargs.get("interval") in (None, "1d")


def test_us_leg_ignores_extended_hours_price_incident_gev(monkeypatch):
    """실적 발표 종목이 시간외로 +6% 뛰어도 미국 레그는 정규장 값이어야 한다.

    get_ticker_full()로 되돌리면 _get_realtime_price()가 주는 시간외 체결가가 그대로
    실려 이 테스트가 실패한다 — 호출 형태가 아니라 값의 성질을 고정한다.
    """
    _patch_daily(monkeypatch, [100.0, 103.0], _SNAP_DATE)
    # 정규장 종가 103 위에 애프터마켓 +6% 체결(109.18)이 있는 상황을 주입한다.
    monkeypatch.setattr(m, "_get_realtime_price", lambda t: (109.18, 103.0))
    monkeypatch.setattr(m, "_extended_hours_price", lambda *a, **k: 109.18)

    rec = m._regular_session_change("GEV")

    assert rec["change_pct"] == 3.0  # 시간외 +6%가 섞이면 9.18이 된다


def test_bridge_us_leg_end_to_end_ignores_extended_hours(monkeypatch):
    """수집→조립 전 구간에서 시간외 가격이 새어 들어오지 않는지 확인한다."""
    _patch_daily(monkeypatch, [100.0, 103.0], _SNAP_DATE)
    monkeypatch.setattr(m, "_get_realtime_price", lambda t: (109.18, 103.0))

    us = m.fetch_bridge_us_changes()
    rows = m.fetch_overnight_bridge(us, _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    assert set(us) == {t for ts in m.BRIDGE_US_TICKERS.values() for t in ts}
    assert all(r["us_change"] == 3.0 for r in rows)


def test_us_and_kr_legs_must_be_same_session(monkeypatch):
    """미국 레그가 한국 레그보다 한 세션 뒤처지면(미국 휴장 등) 그 티커는 결측이다(§24)."""
    import datetime as _dt
    _patch_daily(monkeypatch, [100.0, 103.0], _SNAP_DATE - _dt.timedelta(days=1))

    us = m.fetch_bridge_us_changes()
    rows = m.fetch_overnight_bridge(us, _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    assert rows is None  # 전 섹터가 세션 불일치로 빠져 섹션 자체가 생략됨


def test_us_leg_without_session_date_is_treated_as_missing():
    """session_date가 없는 항목은 같은 세션인지 확인할 수 없으므로 채택하지 않는다."""
    us = _us(SOXX={"change_pct": 8.5})  # session_date 없음

    rows = m.fetch_overnight_bridge(us, _snapshot(_SNAP_DATE, _kr_top2_all_sectors()), today=_TODAY)

    assert "반도체" not in {r["sector"] for r in rows}
    assert len(rows) == 6


def test_regular_session_change_returns_none_on_short_history(monkeypatch):
    _patch_daily(monkeypatch, [100.0], _SNAP_DATE)
    assert m._regular_session_change("GEV") is None


def test_regular_session_change_returns_none_on_zero_prev_close(monkeypatch):
    _patch_daily(monkeypatch, [0.0, 103.0], _SNAP_DATE)
    assert m._regular_session_change("GEV") is None


def test_regular_session_change_swallows_network_failure(monkeypatch):
    def boom(ticker, **kwargs):
        raise RuntimeError("네트워크 실패")

    monkeypatch.setattr(m, "_yf_history", boom)
    assert m._regular_session_change("GEV") is None
    assert m.fetch_bridge_us_changes() == {}
