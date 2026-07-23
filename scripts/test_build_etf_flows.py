# build_etf_flows 순수 함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 scripts/test_build_etf_flows.py"""
import build_etf_flows as m


def test_estimate_shares():
    # KODEX 200: AUM 254428억, NAV 113361원 → 약 2.245억 좌
    s = m.estimate_shares(254428, 113361.0)
    assert abs(s - 254428 * 1e8 / 113361.0) < 1e-3
    assert m.estimate_shares(1000, 0) is None      # NAV 0 방어
    assert m.estimate_shares(1000, None) is None
    assert m.estimate_shares(None, 100) is None


def test_classify_theme():
    assert m.classify_theme("KODEX 반도체") == "반도체"
    assert m.classify_theme("TIGER 2차전지테마") == "2차전지"
    assert m.classify_theme("KODEX 200") is None          # 대형지수 catch-all은 테마 아님
    assert m.classify_theme("TIGER 미국나스닥100") == "미국 나스닥·기술"
    assert m.classify_theme("KODEX 국고채10년") == "채권"
    assert m.classify_theme("ACE KRX금현물") == "금·원자재"
    # "반도체TOP10"이 배당('TOP')으로 오분류되지 않아야 한다(반도체 우선 + TOP 미사용)
    assert m.classify_theme("TIGER 반도체TOP10") == "반도체"
    assert m.classify_theme("정체불명ETF") is None


def test_net_flow_eok():
    # 좌수 +100만 좌, NAV 1만원 → +100만×1만 = 100억
    assert m.net_flow_eok(2_000_000, 1_000_000, 10000.0) == 100
    # 유출
    assert m.net_flow_eok(1_000_000, 2_000_000, 10000.0) == -100
    assert m.net_flow_eok(1_000_000, 1_000_000, 10000.0) == 0


def test_select_baseline():
    # prior_dates: 과거 스냅샷 날짜 내림차순(어제가 [0])
    # 5개 이상이면 5거래일 전 기준, window=5
    dates = ["2026-07-23","2026-07-22","2026-07-21","2026-07-18","2026-07-17","2026-07-16"]
    assert m.select_baseline(dates, 5) == ("2026-07-17", 5)
    # 3개뿐이면 가장 오래된 것 기준, window=3
    assert m.select_baseline(["2026-07-23","2026-07-22","2026-07-21"], 5) == ("2026-07-21", 3)
    # 1개뿐이면 window=1
    assert m.select_baseline(["2026-07-23"], 5) == ("2026-07-23", 1)
    # 0개(워밍업 첫날) → None
    assert m.select_baseline([], 5) == (None, 0)


def test_roll_history():
    hist = {"2026-07-16": {"A": 1}, "2026-07-17": {"A": 2}}
    snap = {"A": 3}
    out = m.roll_history(hist, "2026-07-20", snap, keep_days=2)
    # 오늘 추가 + 최근 2거래일만 보관(가장 오래된 07-16 프룬)
    assert set(out.keys()) == {"2026-07-17", "2026-07-20"}
    assert out["2026-07-20"] == {"A": 3}


def test_aggregate_by_theme():
    flows = [
        {"code": "1", "name": "KODEX 반도체", "theme": "반도체", "flow_eok": 900},
        {"code": "2", "name": "TIGER 반도체TOP10", "theme": "반도체", "flow_eok": -200},
        {"code": "3", "name": "KODEX 국고채", "theme": "채권", "flow_eok": -500},
        {"code": "4", "name": "미분류", "theme": None, "flow_eok": 999},  # 제외돼야
    ]
    themes = m.aggregate_by_theme(flows, top_n=5)
    # None 테마 제외, |합| 내림차순: 반도체(+700), 채권(-500)
    assert [t["theme"] for t in themes] == ["반도체", "채권"]
    assert themes[0]["flow_eok"] == 700
    assert themes[0]["etf_count"] == 2
    # top_etfs는 |flow| 내림차순
    assert themes[0]["top_etfs"][0]["code"] == "1"
    assert themes[0]["top_etfs"][1]["code"] == "2"


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
