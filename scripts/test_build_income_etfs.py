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
    # 원금성: 분배 13.02 vs 총수익 1.85 → 침식 −11.17 < −분배/2(−6.51)
    assert m.classify_health(13.02, 1.85) == ("bad", -11.17)
    # 건전: 분배 3.6 vs 총수익 19.1 → 침식 +15.5 ≥ 0
    assert m.classify_health(3.6, 19.1) == ("ok", 15.5)
    # 경계 — 침식 정확히 0 → ok
    assert m.classify_health(10.0, 10.0) == ("ok", 0.0)
    # 경계 — 침식 = −분배/2 정확히 → warn (포함)
    assert m.classify_health(10.0, 5.0) == ("warn", -5.0)
    # 경계 — 침식 살짝 더 음수 → bad
    assert m.classify_health(10.0, 4.0) == ("bad", -6.0)
    # 데이터 부족
    assert m.classify_health(None, 5.0) == (None, None)
    assert m.classify_health(10.0, None) == (None, None)


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
