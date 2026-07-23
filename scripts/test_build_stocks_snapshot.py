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


def test_to_int():
    assert m._to_int("-847,969") == -847969
    assert m._to_int("+1,864,496") == 1864496
    assert m._to_int("") is None
    assert m._to_int(None) is None
    assert m._to_int("-") is None


def test_q_label():
    assert m._q_label("202509") == "25Q3"
    assert m._q_label("202512") == "25Q4"
    assert m._q_label("202603") == "26Q1"


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


def test_parse_financials():
    info = {
        "trTitleList": [
            {"key": "202503", "isConsensus": "N"},
            {"key": "202506", "isConsensus": "N"},
            {"key": "202606", "isConsensus": "Y"},
        ],
        "rowList": [
            {"title": "매출액", "columns": {"202503": {"value": "176,391"},
             "202506": {"value": "222,320"}, "202606": {"value": "828,926"}}},
            {"title": "영업이익", "columns": {"202503": {"value": "74,405"},
             "202506": {"value": "92,129"}, "202606": {"value": "634,511"}}},
        ],
    }
    out = m.parse_financials(info)
    assert [r["q"] for r in out] == ["25Q1", "25Q2", "26Q2"]
    assert out[0] == {"q": "25Q1", "rev": 176391, "op": 74405, "est": False}
    assert out[-1]["est"] is True
    assert m.parse_financials(None) == []


def test_sector_bellwether_for_stock():
    snapshot = {"bellwethers": {"NVDA": {"name": "엔비디아", "change_pct": 1.9}}}
    sectors = {"semicon": {"bellwethers": [{"t": "NVDA"}]}}
    bw = g.sector_bellwether(snapshot, sectors, "semicon")
    assert bw["t"] == "NVDA"
    assert bw["change_pct"] == 1.9
    # 없는 섹터 → None
    assert g.sector_bellwether(snapshot, sectors, "nonexist") is None


def test_parse_financials_annual():
    info = {
        "trTitleList": [
            {"key": "202312", "isConsensus": "N"},
            {"key": "202412", "isConsensus": "N"},
            {"key": "202512", "isConsensus": "N"},
            {"key": "202612", "isConsensus": "Y"},
        ],
        "rowList": [
            {"title": "매출액", "columns": {"202312": {"value": "2,589,355"},
             "202412": {"value": "3,008,709"}, "202512": {"value": "3,336,059"},
             "202612": {"value": "7,324,732"}}},
            {"title": "영업이익", "columns": {"202312": {"value": "65,670"},
             "202412": {"value": "327,260"}, "202512": {"value": "436,011"},
             "202612": {"value": "3,832,404"}}},
        ],
    }
    out = m.parse_financials_annual(info)
    assert [r["year"] for r in out] == ["2023", "2024", "2025", "2026"]
    assert out[0] == {"year": "2023", "rev": 2589355, "op": 65670, "est": False}
    # 2026 컨센서스 — 영업(383조)<매출(732조)이라 게이트 통과, 크기는 손대지 않음
    assert out[-1]["est"] is True and out[-1]["rev"] == 7324732
    assert m.parse_financials_annual(None) == []


def test_parse_financials_annual_sanity_gate():
    # 구조적으로 불가능한 값만 폐기: 영업이익>매출, 매출≤0
    info = {
        "trTitleList": [
            {"key": "202512", "isConsensus": "N"},   # 정상 → 유지
            {"key": "202612", "isConsensus": "Y"},   # 영업>매출 → 폐기
            {"key": "202712", "isConsensus": "Y"},   # 매출 0 → 폐기
        ],
        "rowList": [
            {"title": "매출액", "columns": {"202512": {"value": "1,000"},
             "202612": {"value": "500"}, "202712": {"value": "0"}}},
            {"title": "영업이익", "columns": {"202512": {"value": "100"},
             "202612": {"value": "900"}, "202712": {"value": "50"}}},
        ],
    }
    out = m.parse_financials_annual(info)
    assert [r["year"] for r in out] == ["2025"]


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
