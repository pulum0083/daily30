# build_flow_map 순수 함수 단위 테스트 + 저장소 실데이터 정합성 대조
#!/usr/bin/env python3
"""실행: python3 scripts/test_build_flow_map.py"""
import build_flow_map as m


def _snap(rows):
    """{code: (shares, nav, name)} → 스냅샷 dict."""
    return {c: {"shares": s, "nav": n, "name": nm} for c, (s, n, nm) in rows.items()}


def test_daily_by_etf_telescoping():
    """일별 합 = 전체 구간 차분. 최종 NAV로 통일하므로 정확히 telescoping 된다."""
    s0 = _snap({"A": (100.0, 1e8, "KODEX 반도체")})
    s1 = _snap({"A": (130.0, 1e8, "KODEX 반도체")})
    s2 = _snap({"A": (120.0, 2e8, "KODEX 반도체")})   # NAV가 바뀌어도 최종 NAV로 환산
    per = m.daily_by_etf([("d0", s0), ("d1", s1), ("d2", s2)], s2, ["A"])
    assert sorted(per["A"].keys()) == ["d1", "d2"]
    total = sum(per["A"].values())
    assert abs(total - (120.0 - 100.0) * 2e8 / 1e8) < 1e-6


def test_daily_by_etf_carry_forward_on_missing():
    """중간 스냅샷에 없는 종목은 직전 좌수를 유지한다 — 없는 유출을 만들지 않는다."""
    s0 = _snap({"A": (100.0, 1e8, "KODEX 반도체")})
    s1 = _snap({})                                     # A가 빠진 날
    s2 = _snap({"A": (140.0, 1e8, "KODEX 반도체")})
    per = m.daily_by_etf([("d0", s0), ("d1", s1), ("d2", s2)], s2, ["A"])
    assert "d1" not in per["A"]                        # 그날은 변화 없음
    assert abs(per["A"]["d2"] - 40.0) < 1e-6           # 이틀치가 d2에 몰린다


def test_daily_by_etf_short_history():
    """스냅샷이 1개뿐이면 일별 분해 불가 — 빈 dict."""
    s0 = _snap({"A": (100.0, 1e8, "KODEX 반도체")})
    assert m.daily_by_etf([("d0", s0)], s0, ["A"]) == {}


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
