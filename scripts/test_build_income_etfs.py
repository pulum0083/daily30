# build_income_etfs 순수 함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 scripts/test_build_income_etfs.py"""
from datetime import date

import build_income_etfs as m


def test_is_income_etf():
    assert m.is_income_etf("TIGER 미국배당다우존스")
    assert m.is_income_etf("KODEX 200타겟위클리커버드콜")
    assert m.is_income_etf("TIGER 리츠부동산인프라")
    assert m.is_income_etf("PLUS 고배당주")
    assert not m.is_income_etf("KODEX 200")
    assert not m.is_income_etf("TIGER 미국S&P500")
    assert not m.is_income_etf("")
    assert not m.is_income_etf(None)


def test_return_y1():
    perf = [{"periodTypeCode": "M6", "value": -2.48}, {"periodTypeCode": "Y1", "value": 1.85}]
    assert m.return_y1(perf) == 1.85
    assert m.return_y1([{"periodTypeCode": "M1", "value": 1.0}]) is None
    assert m.return_y1([]) is None
    assert m.return_y1(None) is None


def test_return_y1_rejects_nonfinite():
    # 2026-08-02 실사고: 벤더가 value에 NaN을 실어 보내면 json.dump가 리터럴 NaN을
    # 그대로 써버려 프론트 JSON.parse가 통째로 실패했다 — 소스에서부터 걸러야 한다.
    import math

    assert m.return_y1([{"periodTypeCode": "Y1", "value": float("nan")}]) is None
    assert m.return_y1([{"periodTypeCode": "Y1", "value": math.inf}]) is None
    assert m.return_y1([{"periodTypeCode": "Y1", "value": -math.inf}]) is None


def test_sanitize_nonfinite():
    import math

    raw = {
        "a": float("nan"),
        "b": [1, math.inf, {"c": -math.inf, "d": 2.5}],
        "e": None,
        "f": "ok",
    }
    out = m.sanitize_nonfinite(raw)
    assert out == {"a": None, "b": [1, None, {"c": None, "d": 2.5}], "e": None, "f": "ok"}
    # 결과가 실제로 유효한 JSON으로 직렬화되는지까지 확인 (이번 사고의 핵심 증상)
    import json

    json.dumps(out)


def test_classify_health():
    # 1년 가격 변화로 판정한다(2026-11-12 정정)
    assert m.classify_health(13.02, 1.85) == ("ok", 1.85)      # 가격이 올랐으면 분배율이 높아도 건전
    assert m.classify_health(10.0, 0.0) == ("ok", 0.0)         # 경계 — 그대로면 건전
    assert m.classify_health(10.0, -5.0) == ("warn", -5.0)     # 분배율의 절반까지 내림 → 주의
    assert m.classify_health(10.0, -5.01) == ("bad", -5.01)    # 그보다 더 내림 → 원금성
    assert m.classify_health(None, 5.0) == (None, None)
    assert m.classify_health(10.0, None) == (None, None)


def test_kr_health_uses_price_not_price_minus_yield():
    # 2026-11-12 실사고: ACE 미국반도체데일리타겟커버드콜 — 네이버 Y1(가격 변화) +8.51%, 분배율 35.22%.
    # 예전엔 8.51 − 35.22 = −26.7%로 '원금성'이라 했지만 실제 가격은 9,661 → 11,135원으로 올랐다.
    assert m.classify_health(35.22, 8.51)[0] == "ok"
    # 총수익 = 가격 변화 + 분배금 ÷ 1년 전 가격 = 8.51 + 35.22 × 1.0851
    assert m.total_from_price(8.51, 35.22) == 46.73
    assert m.total_from_price(None, 3.0) is None
    assert m.total_from_price(2.0, None) is None


def test_parse_months():
    assert m.parse_months("1,2,3,4,5") == [1, 2, 3, 4, 5]
    assert m.parse_months("12") == [12]
    assert m.parse_months("") == []
    assert m.parse_months(None) == []


def test_is_new_fund():
    today = date(2026, 6, 13)
    assert m.is_new_fund("20251201", today)        # 6개월 전 → 신생
    assert not m.is_new_fund("20240227", today)    # 2년+ → 아님
    assert not m.is_new_fund("20250613", today)    # 정확히 1년 → 아님(365일)
    assert m.is_new_fund("20250614", today)        # 364일 → 신생
    assert not m.is_new_fund("", today)
    assert not m.is_new_fund(None, today)
    assert not m.is_new_fund("2024", today)        # 형식 오류


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()


# ── 2026-10-28 점검 ──
QYLG_1Y = [0.276, 0.162, 2.778, 0.157, 0.146, 0.184, 0.153, 0.207, 0.208, 0.268, 0.171, 0.14, 0.17]   # 야후 실측, 2.778은 연말 특별분배


def test_regular_dividends_drops_special_and_keeps_last_12():
    from build_income_etfs import regular_dividends
    reg, spec = regular_dividends(QYLG_1Y)
    assert spec == [2.778]
    assert len(reg) == 12 and reg[-1] == 0.17
    assert round(sum(reg) / 29.86 * 100, 1) < 8   # 정기분 기준 약 7.5% (특별분배를 넣으면 16.8%)


def test_regular_dividends_keeps_steady_payers():
    from build_income_etfs import regular_dividends
    qyld = [0.173, 0.178, 0.179, 0.177, 0.172, 0.179, 0.179, 0.185, 0.178, 0.183, 0.177, 0.183]
    assert regular_dividends(qyld) == (qyld, [])
    assert regular_dividends([]) == ([], [])


def test_january_keeps_last_weeks_monthly_etfs():
    from datetime import date
    from build_income_etfs import is_monthly
    jan = date(2027, 1, 4)
    assert is_monthly([], "20200101", jan, was_monthly=True) is True    # 1월 첫 갱신 — 올해 지급 월이 아직 비어 있다
    assert is_monthly([], "20200101", jan, was_monthly=False) is False
    assert is_monthly([], "20200101", date(2027, 3, 2), was_monthly=True) is False   # 1월이 지나면 원래 판정


def test_enough_kr_guard():
    from build_income_etfs import enough_kr
    assert enough_kr(68, 68) and enough_kr(40, 68)
    assert not enough_kr(0, 68) and not enough_kr(20, 68)
    assert enough_kr(5, 0) and not enough_kr(0, 0)


# ── 2026-11-12 건전성 보드 지표 ──
from datetime import date as _d


def test_category():
    assert m.category("TIGER 배당커버드콜액티브", True) == "cc"
    assert m.category("JPMorgan 에쿼티프리미엄 (JEPI)", False) == "cc"
    assert m.category("NEOS 나스닥100 고인컴 (QQQI)", False) == "cc"
    assert m.category("KODEX 단기채권", False) == "bond"
    assert m.category("iShares 우선주·인컴 (PFF)", False) == "bond"
    assert m.category("TIGER 미국배당다우존스", False) == "div"


def test_price_change_and_spark():
    today = _d(2026, 11, 12)
    rows = [("2025-11-10", 100.0), ("2026-08-10", 150.0), ("2026-11-11", 120.0)]
    assert m.price_change(rows, today, 365) == 20.0          # 1년 전 이하 마지막 종가 100 → 120
    assert m.price_change(rows, today, 91) == -20.0          # 3개월 전 이하 마지막 150 → 120
    assert m.price_change([("2026-10-01", 1.0)], today, 365) is None   # 그만큼 오래된 기록이 없으면 비운다
    sp = m.weekly_spark([(f"2026-01-{i:02d}", float(i)) for i in range(1, 13)], today)
    assert sp["d"][0] == "2026-01-01" and sp["d"][-1] == "2026-01-12"   # 마지막 날은 꼭 들어간다
    assert len(sp["d"]) == len(sp["p"]) == 4                            # 1, 6, 11, 12일


def test_monthly_dist_excludes_current_month():
    today = _d(2026, 11, 12)
    divs = [("2025-10-30", 9.0), ("2025-11-13", 100.0), ("2026-09-14", 50.0), ("2026-09-28", 30.0), ("2026-11-05", 77.0)]
    out = m.monthly_dist(divs, today, 1000)
    assert [x["m"] for x in out][0] == "2025-11" and out[-1]["m"] == "2026-10"   # 지난달까지 12개월
    sep = next(x for x in out if x["m"] == "2026-09")
    assert sep["amt"] == 80.0 and sep["n"] == 2 and sep["pct"] == 8.0
    assert next(x for x in out if x["m"] == "2026-10")["n"] == 0                 # 분배 없는 달
    assert all(x["m"] != "2026-11" for x in out)                                 # 이번 달은 아직 안 센다


def test_dist_trend():
    today = _d(2026, 11, 12)
    divs = [("2025-11-20", 100.0), ("2025-12-20", 100.0), ("2026-09-20", 130.0), ("2026-10-20", 110.0)]
    assert m.dist_trend(divs, today) == 20.0
    assert m.dist_trend(divs[:3], today) is None              # 최근이 2회 미만이면 판단하지 않는다


def test_kr_bench_key():
    assert m.kr_bench_key("NASDAQ-100 Daily Covered Call 101 Index(TR)") == "nasdaq"
    assert m.kr_bench_key("코스피 200 커버드콜 5% OTM 지수(PR 지수)") == "kospi"
    assert m.kr_bench_key("코스피 200 금융 고배당 TOP 10 타겟 15% 분배 위클리 커버드콜 지수") is None
    assert m.kr_bench_key("KEDI 팔란티어커버드콜OTM 채권혼합지수(NTR)") is None
    assert m.kr_bench_key("Dow Jones U.S. Dividend 100 10% Premium Covered Call Index(Total Return)") == "usdiv"
    assert m.kr_bench_key(None) is None
