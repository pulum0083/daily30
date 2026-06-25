# build_stocks_snapshot 순수 계산함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 scripts/test_build_stocks_snapshot.py"""
import build_stocks_snapshot as m
import generate_html as g


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


def test_sector_bellwether_for_stock():
    snapshot = {"bellwethers": {"NVDA": {"name": "엔비디아", "change_pct": 1.9}}}
    sectors = {"semicon": {"bellwethers": [{"t": "NVDA"}]}}
    bw = g.sector_bellwether(snapshot, sectors, "semicon")
    assert bw["t"] == "NVDA"
    assert bw["change_pct"] == 1.9
    # 없는 섹터 → None
    assert g.sector_bellwether(snapshot, sectors, "nonexist") is None


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
