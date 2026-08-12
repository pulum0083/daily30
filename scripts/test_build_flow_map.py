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


def test_etf_rows_pct_is_share_change_over_current():
    """덩치 대비 % = (현재좌수 − 기준좌수) / 현재좌수 × 100. NAV가 약분돼 순수 좌수 증감률."""
    today = _snap({"A": (70.0, 1e8, "KODEX 은행")})
    baseline = _snap({"A": (100.0, 1e8, "KODEX 은행")})
    flows = [{"code": "A", "name": "KODEX 은행", "theme": "금융·은행", "flow_eok": -30}]
    rows, rest_n, rest_flow = m.etf_rows(flows, today, baseline, {}, ["d1"], top_n=20)
    assert rows[0]["aum"] == 70                       # 70 × 1e8 / 1e8
    assert rows[0]["pct"] == -42.9                    # (70−100)/70×100
    assert rows[0]["daily"] == [0]                    # 일별 데이터 없으면 0으로 채운다
    assert (rest_n, rest_flow) == (0, 0)


def test_etf_rows_cuts_at_top_n_and_reports_rest():
    """상위 N개에서 끊되 밖으로 밀린 것은 개수·합계를 명시한다 — 무음 절단 금지(운영규칙 0)."""
    today, baseline, flows = {}, {}, []
    for i in range(25):
        code = f"C{i:02d}"
        today[code] = {"shares": 100.0, "nav": 1e8, "name": "KODEX 반도체"}
        baseline[code] = {"shares": 100.0 - (25 - i), "nav": 1e8, "name": "KODEX 반도체"}
        flows.append({"code": code, "name": "KODEX 반도체", "theme": "반도체", "flow_eok": 25 - i})
    rows, rest_n, rest_flow = m.etf_rows(flows, today, baseline, {}, ["d1"], top_n=20)
    assert len(rows) == 20
    assert rows[0]["flow"] == 25                      # |flow| 내림차순
    assert rest_n == 5
    assert rest_flow == sum(range(1, 6))              # 밀린 5개(5,4,3,2,1)의 합
    assert sum(r["flow"] for r in rows) + rest_flow == sum(f["flow_eok"] for f in flows)


def test_etf_rows_folds_unresolvable_top_item_into_rest():
    """상위 N 안에 today/baseline 스냅샷이 없는 종목이 있어도 금액이 사라지지 않는다."""
    today = _snap({"A": (100.0, 1e8, "KODEX 반도체"), "B": (50.0, 1e8, "KODEX 반도체")})
    baseline = _snap({"A": (80.0, 1e8, "KODEX 반도체")})   # B는 baseline에 없음(비정상 상태 시뮬레이션)
    flows = [
        {"code": "A", "name": "KODEX 반도체", "theme": "반도체", "flow_eok": 20},
        {"code": "B", "name": "KODEX 반도체", "theme": "반도체", "flow_eok": 999},   # 해석 불가
    ]
    rows, rest_n, rest_flow = m.etf_rows(flows, today, baseline, {}, ["d1"], top_n=20)
    assert len(rows) == 1 and rows[0]["code"] == "A"
    assert rest_n == 1 and rest_flow == 999            # B가 사라지지 않고 rest로 잡힌다
    assert sum(r["flow"] for r in rows) + rest_flow == sum(f["flow_eok"] for f in flows)


def test_etf_rows_pct_none_when_shares_zero():
    """좌수 0이면 비율을 만들 수 없다 — 지어내지 않고 None(뱃지 생략)."""
    today = _snap({"A": (0.0, 1e8, "KODEX 은행")})
    baseline = _snap({"A": (100.0, 1e8, "KODEX 은행")})
    flows = [{"code": "A", "name": "KODEX 은행", "theme": "금융·은행", "flow_eok": -100}]
    rows, _n, _f = m.etf_rows(flows, today, baseline, {}, ["d1"], top_n=20)
    assert rows[0]["pct"] is None


def test_dates_of_takes_longest_daily():
    """일별이 비어 있는 테마가 섞여도 날짜축은 가장 긴 것을 쓴다."""
    themes = [
        {"theme": "A", "daily": []},
        {"theme": "B", "daily": [{"date": "d1", "eok": 5}, {"date": "d2", "eok": 6}]},
    ]
    assert m.dates_of(themes) == ["d1", "d2"]
    assert m.dates_of([{"theme": "A", "daily": []}]) == []


def test_market_daily_sums_published_values_by_date():
    """전 테마 일별 합. 날짜로 맞춰 더한다 — 인덱스 위치로 더하면 축이 어긋난 테마에서 깨진다."""
    themes = [
        {"theme": "A", "daily": [{"date": "d1", "eok": 10}, {"date": "d2", "eok": -3}]},
        {"theme": "B", "daily": [{"date": "d2", "eok": 7}]},        # d1이 없는 테마
    ]
    assert m.market_daily(themes, ["d1", "d2"]) == [10, 4]


def test_build_aborts_when_history_and_published_disagree():
    """히스토리 최신일과 발행본 날짜가 다르면 섞지 않고 중단한다(§0)."""
    hist = {"2026-07-30": _snap({"A": (100.0, 1e8, "KODEX 반도체")}),
            "2026-07-31": _snap({"A": (110.0, 1e8, "KODEX 반도체")})}
    pub = {"generated_at": "2026-07-28T18:00:00+09:00", "window_days": 1,
           "aum_floor_eok": 300, "coverage": {"etf_count": 1, "theme_count": 1},
           "themes": [{"theme": "반도체", "flow_eok": 10, "gross_eok": 10, "etf_count": 1,
                       "daily": [{"date": "2026-07-31", "eok": 10}]}]}
    try:
        m.build(hist, pub, "2026-07-31T18:05:00+09:00")
        assert False, "날짜 불일치인데 중단하지 않았다"
    except RuntimeError as e:
        assert "날짜" in str(e)


def test_build_aborts_when_recomputed_totals_drift():
    """재계산 합계가 발행 합계와 ±2억을 넘게 벌어지면 중단한다."""
    hist = {"2026-07-30": _snap({"A": (100.0, 1e8, "KODEX 반도체")}),
            "2026-07-31": _snap({"A": (110.0, 1e8, "KODEX 반도체")})}
    pub = {"generated_at": "2026-07-31T18:00:00+09:00", "window_days": 1,
           "aum_floor_eok": 300, "coverage": {"etf_count": 1, "theme_count": 1},
           "themes": [{"theme": "반도체", "flow_eok": 999, "gross_eok": 999, "etf_count": 1,
                       "daily": [{"date": "2026-07-31", "eok": 999}]}]}
    try:
        m.build(hist, pub, "2026-07-31T18:05:00+09:00")
        assert False, "합계가 어긋났는데 중단하지 않았다"
    except RuntimeError as e:
        assert "정합" in str(e)


def test_build_returns_none_on_warmup():
    """발행본 themes가 비어 있으면(워밍업) None — 파일을 쓰지 않는다."""
    hist = {"2026-07-31": _snap({"A": (100.0, 1e8, "KODEX 반도체")})}
    pub = {"generated_at": "2026-07-31T18:00:00+09:00", "window_days": 0,
           "aum_floor_eok": 300, "coverage": {"etf_count": 1, "theme_count": 0}, "themes": []}
    assert m.build(hist, pub, "2026-07-31T18:05:00+09:00") is None


def test_build_raises_when_history_empty_but_published_has_themes():
    """발행본엔 테마가 있는데 히스토리가 비어 있으면 — 두 파일이 어긋난 것, 조용히 넘어가지 않는다."""
    hist = {}
    pub = {"generated_at": "2026-07-31T18:00:00+09:00", "window_days": 1,
           "aum_floor_eok": 300, "coverage": {"etf_count": 1, "theme_count": 1},
           "themes": [{"theme": "반도체", "flow_eok": 10, "gross_eok": 10, "etf_count": 1,
                       "daily": [{"date": "2026-07-31", "eok": 10}]}]}
    try:
        m.build(hist, pub, "2026-07-31T18:05:00+09:00")
        assert False, "히스토리가 비었는데 중단하지 않았다"
    except RuntimeError as e:
        assert "히스토리" in str(e)


def test_build_raises_when_rebuild_context_fails_despite_matching_date():
    """날짜는 맞는데 재구성이 실패하면(기준 스냅샷 없음) — 진짜 워밍업과 다르므로 크게 알린다."""
    hist = {"2026-07-31": _snap({"A": (100.0, 1e8, "KODEX 반도체")})}   # 오늘 하루뿐, 기준일 없음
    pub = {"generated_at": "2026-07-31T18:00:00+09:00", "window_days": 1,
           "aum_floor_eok": 300, "coverage": {"etf_count": 1, "theme_count": 1},
           "themes": [{"theme": "반도체", "flow_eok": 500, "gross_eok": 500, "etf_count": 1,
                       "daily": [{"date": "2026-07-31", "eok": 500}]}]}
    try:
        m.build(hist, pub, "2026-07-31T18:05:00+09:00")
        assert False, "재구성 실패인데 중단하지 않았다"
    except RuntimeError as e:
        assert "재구성" in str(e) or "히스토리" in str(e)


def theme_bar_tolerance(n_dates, n_etfs):
    """불변식②(일별 막대 합 vs 헤더)의 반올림 노이즈 상한(억).

    헤더와 막대는 **같은 실수값을 서로 다르게 분할해 각각 반올림**한 결과다.

      헤더 flow_eok = Σ_ETF round(ETF별 흐름)          — ETF 수만큼 반올림
      막대 합       = Σ_날짜 round(그날 전 ETF 합)      — 날짜 수만큼 반올림

    두 실수 합은 telescoping으로 정확히 같지만(build_etf_flows.daily_by_theme 참고),
    반올림 지점이 달라 정수끼리는 최대 0.5×(날짜수 + ETF수)까지 벌어진다.

    이 오차는 제거할 수 없다 — 개별 표시값은 전부 자기 실측의 최근접 정수이고,
    둘을 동시에 정확히 맞추려면 최대잔여법으로 각 값을 실측에서 1억씩 밀어내야 한다.
    표시값 자체의 정확도를 희생하는 쪽이 운영규칙 0에 어긋나므로 그렇게 하지 않는다.
    (헤더를 round(Σ실수)로 바꾸는 방향도 검토했으나, 그러면 같은 오차가 그대로
     불변식①로 옮겨갈 뿐이다 — ETF 행은 여전히 개별 반올림이라 합이 안 맞는다.)

    실측(2026-08-12, 5일·테마당 2~109개 ETF): 최대 4억. 상한 대비 한참 아래다.
    이 게이트가 노리는 진짜 고장(telescoping 파괴 = NAV 기준 오적용)은 실측 기준
    17.9% 규모라 이 상한으로도 여전히 잡힌다.
    """
    return max(3, (n_dates + n_etfs + 1) // 2)


def test_theme_bar_tolerance_scales_with_etf_count():
    """상한이 ETF 수를 반영하는지 — 날짜 수만 보면 이 사고가 그대로 재발한다."""
    # 실사고(2026-08-12) 재현: 5일·46개 ETF 테마에서 4억 어긋났다. 고정 ±3은 실패했다.
    assert theme_bar_tolerance(5, 46) >= 4
    # ETF가 늘면 상한도 늘어야 한다(반올림 지점이 그만큼 많아진다).
    assert theme_bar_tolerance(5, 109) > theme_bar_tolerance(5, 46)
    # 작은 테마에서 상한이 0으로 붕괴하지 않는다.
    assert theme_bar_tolerance(5, 2) >= 3


def test_build_real_data_invariants():
    """저장소 실데이터로 스펙의 불변식 2개를 확인한다.

      ① ETF 목록 합 + 그 외 합계 = 헤더 순유입액 (±3억)
      ② 일별 막대 합 = 헤더 순유입액 (반올림 노이즈 상한 이내)
    """
    real = _load_real()
    if real is None:
        print("    (워밍업 데이터 — 스킵)"); return
    hist, pub = real
    out = m.build(hist, pub, "2026-01-01T00:00:00+09:00")
    assert out is not None
    assert len(out["themes"]) == len(pub["themes"])
    assert len(out["market_daily"]) == len(out["dates"])

    for t in out["themes"]:
        listed = sum(e["flow"] for e in t["etfs"]) + t["rest_flow"]
        assert abs(listed - t["flow_eok"]) <= 3, f"불변식① {t['theme']}: {listed} vs {t['flow_eok']}"
        bars = sum(t["daily"])
        tol = theme_bar_tolerance(len(out["dates"]), t["etf_count"])
        assert abs(bars - t["flow_eok"]) <= tol, (
            f"불변식② {t['theme']}: {bars} vs {t['flow_eok']} (허용 ±{tol})")
        assert len(t["daily"]) == len(out["dates"])
        assert len(t["etfs"]) <= m.TOP_ETFS_DETAIL
        for e in t["etfs"]:
            assert len(e["daily"]) == len(out["dates"])
            # ETF 하나는 반올림 지점이 날짜수 + 자기 자신 1개뿐이라 상한이 0.5×(5+1)=3이다.
            # 테마 단위(위 tol)와 달리 ETF 수가 안 곱해지므로 고정 ±3이 맞다.
            assert abs(sum(e["daily"]) - e["flow"]) <= 3, (
                f"ETF 반올림 노이즈 초과 {e['name']}: {sum(e['daily'])} vs {e['flow']}")


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
