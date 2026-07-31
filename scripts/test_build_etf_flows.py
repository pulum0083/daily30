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


# ── 일별 분해 · gross (2026-07-31 추가) ──────────────────────────────────────
# 확장 패널의 일별 막대는 헤더의 누적값과 반드시 합이 맞아야 한다. 각 날의 NAV로
# 환산하면 실측 기준 최대 17.9%까지 어긋나(반도체) 한 화면 안에서 숫자가 서로를
# 부정한다 — 최종 NAV로 통일해 telescoping이 성립하는지가 핵심 검증 대상이다.

def _snap(shares_by_code, nav=10000.0, name="KODEX 반도체"):
    return {c: {"shares": s, "nav": nav, "name": name} for c, s in shares_by_code.items()}


def test_daily_by_theme_telescoping():
    """일별 합 == 누적. 최종 NAV 기준이므로 정확히 일치해야 한다."""
    snaps = [
        ("d1", _snap({"1": 1_000_000})),
        ("d2", _snap({"1": 1_500_000})),
        ("d3", _snap({"1": 1_200_000})),
        ("d4", _snap({"1": 2_000_000})),
    ]
    final = snaps[-1][1]
    daily = m.daily_by_theme(snaps, final, ["1"])["반도체"]
    assert [d["date"] for d in daily] == ["d2", "d3", "d4"]
    assert [d["eok"] for d in daily] == [50, -30, 80]
    cum = m.net_flow_eok(2_000_000, 1_000_000, 10000.0)
    assert sum(d["eok"] for d in daily) == cum == 100


def test_daily_by_theme_uses_final_nav_not_daily_nav():
    """중간 NAV가 요동쳐도 일별 합은 누적과 어긋나지 않는다."""
    snaps = [
        ("d1", _snap({"1": 1_000_000}, nav=10000.0)),
        ("d2", _snap({"1": 1_500_000}, nav=99999.0)),   # 중간 NAV 급변
        ("d3", _snap({"1": 2_000_000}, nav=20000.0)),
    ]
    final = snaps[-1][1]
    daily = m.daily_by_theme(snaps, final, ["1"])["반도체"]
    assert sum(d["eok"] for d in daily) == m.net_flow_eok(2_000_000, 1_000_000, 20000.0)


def test_daily_by_theme_carry_forward_on_missing():
    """중간 스냅샷 결측은 '그날 변화 없음' — 없는 유출을 만들지 않는다."""
    snaps = [
        ("d1", _snap({"1": 1_000_000})),
        ("d2", {}),                                  # 결측
        ("d3", _snap({"1": 1_400_000})),
    ]
    final = snaps[-1][1]
    daily = m.daily_by_theme(snaps, final, ["1"])["반도체"]
    assert [d["eok"] for d in daily] == [0, 40]      # d2는 0, d3에 전량
    assert sum(d["eok"] for d in daily) == 40


def test_daily_by_theme_short_history():
    """스냅샷이 1개뿐이면 일별 분해 불가 — 빈 dict(섹션 생략)."""
    assert m.daily_by_theme([("d1", _snap({"1": 1_000_000}))], _snap({"1": 1_000_000}), ["1"]) == {}
    assert m.daily_by_theme([], {}, []) == {}


def test_gross_eok_bounds():
    """gross >= |net| 이고, 집중도(top5/gross)는 100%를 넘지 않는다."""
    flows = [
        {"code": "1", "name": "KODEX 반도체", "theme": "반도체", "flow_eok": 900},
        {"code": "2", "name": "TIGER 반도체TOP10", "theme": "반도체", "flow_eok": -800},
    ]
    t = m.aggregate_by_theme(flows, top_n=5)[0]
    assert t["flow_eok"] == 100
    assert t["gross_eok"] == 1700                     # net으로 나누면 1700% — 불가능한 값
    top5 = sum(abs(e["flow_eok"]) for e in t["top_etfs"])
    assert top5 / t["gross_eok"] <= 1.0


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
