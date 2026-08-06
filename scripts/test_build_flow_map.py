# build_flow_map 순수 함수 단위 테스트 + 저장소 실데이터 정합성 대조
#!/usr/bin/env python3
"""실행: python3 scripts/test_build_flow_map.py"""
import build_flow_map as m
import build_etf_flows as base


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


def _load_real():
    """저장소에 커밋된 실데이터. 워밍업 등으로 쓸 수 없으면 None."""
    import json
    hist = json.loads(m.HISTORY_PATH.read_text(encoding="utf-8"))
    pub = json.loads(m.FLOWS_PATH.read_text(encoding="utf-8"))
    if not hist or not pub.get("themes"):
        return None
    return hist, pub


def test_theme_rollup_matches_published_builder():
    """daily_by_etf를 테마로 롤업한 값이 build_etf_flows.daily_by_theme와 일치한다.

    두 함수는 합산 순서가 달라(코드 우선 vs 날짜 우선) 부동소수 오차로 반올림이 1억
    갈릴 수 있다. 그 이상 벌어지면 규약이 어긋난 것이다.
    """
    real = _load_real()
    if real is None:
        print("    (워밍업 데이터 — 스킵)"); return
    hist, pub = real
    ctx = m.rebuild_context(hist)
    per_etf = m.daily_by_etf(ctx["snapshots"], ctx["today_snap"], ctx["codes"])
    mine = m.rollup_to_theme(per_etf, ctx["today_snap"], ctx["dates"])
    # 같은 ctx에서 나온 값끼리의 대조 — 합산 순서(코드 우선 vs 날짜 우선) 동치성 확인일 뿐,
    # rebuild_context 자체가 틀렸으면(기준일·윈도우 오류 등) 양쪽 다 같이 틀려 못 잡는다.
    # 실제 그라운드트루스 대조는 아래 pub_by_theme 블록.
    theirs = base.daily_by_theme(ctx["snapshots"], ctx["today_snap"], ctx["codes"])

    assert set(mine) == set(theirs), f"테마 집합 불일치: {set(mine) ^ set(theirs)}"
    for theme, rows in theirs.items():
        got = {r["date"]: r["eok"] for r in mine[theme]}
        for r in rows:
            d = abs(got[r["date"]] - r["eok"])
            assert d <= 1, f"{theme} {r['date']}: {got[r['date']]} vs {r['eok']}"

    # 발행본(web/data/etf-flows.json)을 독립된 그라운드트루스로 대조 — rebuild_context 자체의
    # 오류(기준일 오선택, 윈도우 슬라이스 오프바이원, stale today 등)를 잡아낸다.
    pub_by_theme = {t["theme"]: t for t in pub["themes"]}
    checked = 0
    for theme, rows in mine.items():
        pub_daily = pub_by_theme.get(theme, {}).get("daily") or []
        pub_by_date = {r["date"]: r["eok"] for r in pub_daily}
        for r in rows:
            if r["date"] not in pub_by_date:
                continue   # 발행본 window가 더 짧을 수 있음(워밍업 직후 등) — 있는 날짜만 대조
            d = abs(r["eok"] - pub_by_date[r["date"]])
            assert d <= 1, f"{theme} {r['date']}: 재구성 {r['eok']} vs 발행본 {pub_by_date[r['date']]}"
            checked += 1
    assert checked > 0, "발행본과 대조된 (테마, 날짜) 쌍이 하나도 없음 — 게이트가 공회전 중"


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
