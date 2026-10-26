# build_stocks_snapshot 순수 계산함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 scripts/test_build_stocks_snapshot.py"""
import build_stocks_snapshot as m


def test_change_pct():
    assert m.change_pct([100.0, 110.0]) == 10.0
    assert m.change_pct([200.0, 190.0]) == -5.0
    assert m.change_pct([100.0]) is None     # 직전 종가 없음
    assert m.change_pct([]) is None


def test_wk52():
    closes = [float(x) for x in range(1, 301)]   # 1..300
    hi, lo = m.wk52_high_low(closes)
    assert hi == 300.0
    # 최근 252거래일 = closes[-252:] → 49..300, 최저 49
    assert lo == 49.0


def test_spark():
    closes = [float(x) for x in range(1, 31)]    # 1..30
    assert m.sparkline(closes, 5) == [26.0, 27.0, 28.0, 29.0, 30.0]
    assert m.sparkline([1.0, 2.0], 5) == [1.0, 2.0]   # 데이터 부족 시 있는 만큼


def test_ma200():
    closes = [float(x) for x in range(1, 301)]   # 1..300
    # 최근 200개 = 101..300, 평균 = (101+300)/2 = 200.5
    assert m.ma200(closes) == 200.5
    assert m.ma200([1.0, 2.0]) is None           # 200개 미만


def test_to_int():
    assert m._to_int("-847,969") == -847969
    assert m._to_int("+1,864,496") == 1864496
    assert m._to_int("") is None
    assert m._to_int(None) is None
    assert m._to_int("-") is None


def test_parse_supply5():
    # API는 최신순 → 결과는 오래된→최신
    rows = [
        {"bizdate": "20260626", "individualPureBuyQuant": "+1,864,496",
         "organPureBuyQuant": "-1,065,176", "foreignerPureBuyQuant": "-847,969"},
        {"bizdate": "20260625", "individualPureBuyQuant": "-716,876",
         "organPureBuyQuant": "+865,177", "foreignerPureBuyQuant": "-113,276"},
    ]
    out = m.parse_supply5(rows)
    assert [r["date"] for r in out] == ["6/25", "6/26"]
    assert out[-1] == {"date": "6/26", "i": 1864496, "o": -1065176, "f": -847969}
    # 셋 다 빈값이면 제외
    assert m.parse_supply5([{"bizdate": "20260626", "individualPureBuyQuant": "",
                             "organPureBuyQuant": "", "foreignerPureBuyQuant": ""}]) == []


def test_last_bar_date():
    rows = [
        {"localDate": "20260728", "closePrice": 100.0},
        {"localDate": "20260729", "closePrice": 101.0},
        {"localDate": "20260730", "closePrice": None},  # 종가 없는 행(휴장·결측)은 건너뜀
    ]
    assert m._last_bar_date(rows) == "2026-07-29"
    assert m._last_bar_date([]) is None
    assert m._last_bar_date([{"localDate": "20260730", "closePrice": None}]) is None


def test_reconcile_session_date_unanimous():
    assert m._reconcile_session_date(["2026-07-31", "2026-07-31", "2026-07-31"]) == "2026-07-31"


def test_reconcile_session_date_ignores_missing():
    # 일부 종목 조회 실패(None)는 투표에서 제외 — 나머지가 일치하면 채택
    assert m._reconcile_session_date(["2026-07-31", None, "2026-07-31"]) == "2026-07-31"


def test_reconcile_session_date_disagreement_returns_none():
    # 종목별 마지막 봉 날짜가 엇갈리면 다수결로 추정하지 않고 None(§0)
    assert m._reconcile_session_date(["2026-07-31", "2026-07-30"]) is None


def test_reconcile_session_date_all_missing_returns_none():
    assert m._reconcile_session_date([None, None]) is None
    assert m._reconcile_session_date([]) is None


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
