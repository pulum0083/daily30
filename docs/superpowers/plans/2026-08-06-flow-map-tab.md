# 자금 지도 탭 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/stocks/`에 "자금 지도" 서브탭을 추가한다 — 16개 테마 전부를 발산 바 리스트로 보여주고, 선택한 테마의 ETF 최대 20개까지 일별 흐름과 함께 파고든다.

**Architecture:** 화면의 **테마 합계·일별·시장 요약은 이미 발행 중인 `web/data/etf-flows.json`의 값을 그대로 승계**한다(정본 1개 — §30 이중 구현 방지). 새 빌더 `scripts/build_flow_map.py`는 커밋된 `data/etf_flow_history.json`에서 **ETF 단위 분해만** 재계산해 두 소스를 합친 `web/data/flow-map.json`을 낸다. 재계산에는 `build_etf_flows.py`의 함수를 import해서 쓴다(재구현 금지). 프런트는 새 화면 스크립트 `web/assets/flow-map.js` + 스코프된 스타일 `web/assets/flow-map.css`가 담당하고, 탭 등록은 `ds-subnav.js`의 `TABS` 배열에 한 줄 추가로 끝난다.

**Tech Stack:** Python 3.12 (표준 라이브러리만, 네트워크 없음) · 브라우저 IIFE 바닐라 JS(ES5 스타일, 기존 파일과 동일) · 테스트는 `pytest`(파이썬) / `node --test` + `node:vm` 샌드박스(JS).

---

## 사전 확인 — 이 계획이 서 있는 근거

이미 실데이터로 검증했다. 구현 중 어긋나면 여기부터 의심할 것.

- `data/etf_flow_history.json`만으로 발행본 `web/data/etf-flows.json`을 **오차 0으로** 재구성할 수 있다. `build_etf_flows.py`가 파일을 쓴 **뒤에** 히스토리를 롤링하므로(`main()` 282~291줄), 잡이 끝난 시점의 히스토리에는 오늘 스냅샷이 들어 있고 `select_baseline()`이 고르는 기준일도 동일하다.
- 불변식 실측: ETF 합계 vs 발행 테마 합계 = **최대 0억**, 발행 `daily` 합 vs `flow_eok` = **최대 3억**(발행본 자체의 반올림).
- `pct`(덩치 대비 증감률) 정의 = `(shares_now − shares_base) / shares_now × 100`. NAV가 약분돼 순수 좌수 증감률이 된다. 프로토타입 데이터(KODEX 은행 −41.6%, RISE 26-11 회사채 −51.9%)와 일치 확인.

## 파일 구조

| 파일 | 신규/수정 | 책임 |
| --- | --- | --- |
| `scripts/build_flow_map.py` | 신규 | 히스토리에서 ETF 단위 분해 → 발행본 테마 합계와 결합 → `web/data/flow-map.json` |
| `scripts/test_build_flow_map.py` | 신규 | 위 순수 함수 단위 테스트 + 저장소 실데이터 정합성 대조 |
| `web/data/flow-map.json` | 신규(생성물) | 탭이 fetch하는 데이터 |
| `web/assets/flow-map.css` | 신규 | `#flow-map` 스코프 스타일 |
| `web/assets/flow-map.js` | 신규 | 탭 화면 렌더러(IIFE) |
| `web/assets/flow-map.test.mjs` | 신규 | 순수 함수 + 렌더 회귀 테스트 |
| `web/stocks/index.html` | 수정 | `#flow-map` 화면 마크업 + 에셋 태그 + 홈 위젯 링크 |
| `web/assets/ds-subnav.js` | 수정 | `TABS`에 자금 지도 한 줄 |
| `web/assets/ds-subnav.test.mjs` | 수정 | 탭 개수·라벨 단언 갱신 |
| `.github/workflows/etf-flows.yml` | 수정 | 빌더 실행 스텝 + 커밋 대상 파일 추가 |

**왜 `stocks-home.js`에 넣지 않는가:** 그 파일은 이미 3,300줄이 넘는다. `ds-subnav.js`가 만든 선례(독립 파일 + `node:vm` 테스트)를 따르는 편이 읽기도 테스트하기도 낫다.

**왜 클래스 이름에 전부 `fmap-` 접두사를 붙이는가:** 프로토타입이 쓴 `.st`·`.nm`·`.sp`·`.kpi`·`.mk`·`.leg`·`.conc`는 **전부 `stocks-home.css`에 이미 있다**(`.sp`는 35곳). 접두사 + `#flow-map` 스코프 이중 방어를 한다. 반대로 `.block`·`.block__h`·`.stabs`·`.home-cols`·`.up`·`.dn`은 기존 정의를 **그대로 재사용**한다 — 다시 정의하지 말 것.

---

## Task 1: ETF 단위 일별 분해 함수

**Files:**
- Create: `scripts/build_flow_map.py`
- Create: `scripts/test_build_flow_map.py`

`build_etf_flows.daily_by_theme()`는 테마 단위로만 합산한다. 스파크라인에는 ETF 단위 일별 값이 필요하다. 같은 규약(**최종 NAV 고정**, **중간 결측 carry-forward**)을 지켜야 테마 합계와 어긋나지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_build_flow_map.py`를 새로 만든다.

```python
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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `cd /Users/ncsoft/my-project/double-shot && python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_flow_map'`

- [ ] **Step 3: 최소 구현**

`scripts/build_flow_map.py`를 새로 만든다.

```python
# 자금 지도 탭용 ETF 단위 분해 데이터 빌더 — 테마 합계는 발행본(etf-flows.json)을 그대로 승계한다
#!/usr/bin/env python3
"""
자금 지도 탭 데이터 빌더.

`web/data/etf-flows.json`(발행본)의 테마 합계·일별 값을 정본으로 승계하고,
`data/etf_flow_history.json`에서 ETF 단위 분해만 재계산해 합친다.
네트워크를 쓰지 않는다 — 커밋된 두 파일만 읽는다.

왜 재계산인가
  히스토리는 좌수·NAV 스냅샷일 뿐 ETF별 흐름이 저장돼 있지 않다. 다만 build_etf_flows가
  파일을 쓴 **뒤에** 히스토리를 롤링하므로, 잡 종료 시점의 히스토리로 발행본을 오차 0으로
  재구성할 수 있다(실측 확인). 분류·환산은 build_etf_flows의 함수를 그대로 import한다 —
  재구현하면 한쪽만 고쳐져도 겉보기엔 둘 다 정상으로 보인다(SERVICE_RULES §30).

산출:
  web/data/flow-map.json

Usage:
  python3 scripts/build_flow_map.py
"""
import json
import sys
from datetime import datetime

import build_etf_flows as base

KST = base.KST
ROOT = base.ROOT
HISTORY_PATH = base.HISTORY_PATH
FLOWS_PATH = base.OUT_PATH                       # web/data/etf-flows.json — 입력이자 정본
OUT_PATH = ROOT / "web" / "data" / "flow-map.json"

TOP_ETFS_DETAIL = 20     # 테마당 노출 ETF 수. 밖으로 밀린 것은 개수·합계를 명시한다(무음 절단 금지)


def daily_by_etf(snapshots, final_snap, codes):
    """연속 스냅샷 쌍의 좌수 차분을 ETF별·날짜별로 낸다. {code: {date: eok(float)}}.

    build_etf_flows.daily_by_theme와 **같은 규약**이다 — 환산은 각 날의 NAV가 아니라 최종
    NAV로 통일하고(telescoping 보장), 중간 스냅샷에 없는 종목은 직전 좌수를 유지한다.
    이 함수의 테마 롤업이 daily_by_theme와 일치하는지는 테스트가 실데이터로 대조한다.

    반올림하지 않고 float로 돌려준다 — 합산 후 한 번만 반올림해야 오차가 누적되지 않는다.
    """
    if len(snapshots) < 2:
        return {}
    prev_shares = {}
    for code in codes:
        b = snapshots[0][1].get(code)
        if b:
            prev_shares[code] = b["shares"]

    out = {}
    for date, snap in snapshots[1:]:
        for code in codes:
            if code not in prev_shares:
                continue
            cur = snap.get(code)
            if not cur:
                continue                 # carry-forward — prev_shares 유지
            fin = final_snap.get(code)
            if not fin:
                continue
            out.setdefault(code, {})[date] = (cur["shares"] - prev_shares[code]) * fin["nav"] / 1e8
            prev_shares[code] = cur["shares"]
    return out
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

Run: `python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_flow_map.py scripts/test_build_flow_map.py
git commit -m "feat(자금지도): ETF 단위 일별 분해 함수 daily_by_etf 추가"
```

---

## Task 2: 테마 롤업이 발행 빌더와 일치하는지 실데이터로 대조

**Files:**
- Modify: `scripts/test_build_flow_map.py` (테스트 추가)

Task 1의 함수가 `daily_by_theme`와 **같은 값**을 내는지 저장소 실데이터로 못박는다. 이게 어긋나면 ETF 스파크라인 합이 테마 막대와 달라져 사용자가 더했을 때 숫자가 안 맞는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_build_flow_map.py`의 `def run():` **위에** 추가한다.

```python
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
    hist, _pub = real
    ctx = m.rebuild_context(hist)
    per_etf = m.daily_by_etf(ctx["snapshots"], ctx["today_snap"], ctx["codes"])
    mine = m.rollup_to_theme(per_etf, ctx["today_snap"], ctx["dates"])
    theirs = base.daily_by_theme(ctx["snapshots"], ctx["today_snap"], ctx["codes"])

    assert set(mine) == set(theirs), f"테마 집합 불일치: {set(mine) ^ set(theirs)}"
    for theme, rows in theirs.items():
        got = {r["date"]: r["eok"] for r in mine[theme]}
        for r in rows:
            d = abs(got[r["date"]] - r["eok"])
            assert d <= 1, f"{theme} {r['date']}: {got[r['date']]} vs {r['eok']}"
```

파일 상단 import에 `import build_etf_flows as base`를 추가한다(맨 위 `import build_flow_map as m` 아래).

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: FAIL — `AttributeError: module 'build_flow_map' has no attribute 'rebuild_context'`

- [ ] **Step 3: 최소 구현**

`scripts/build_flow_map.py`의 `daily_by_etf` **아래**에 추가한다.

```python
def rebuild_context(history):
    """히스토리에서 발행본과 동일한 계산 컨텍스트를 복원한다.

    build_etf_flows.main()이 파일을 쓴 뒤에 히스토리를 롤링하므로, 잡 종료 시점의
    히스토리에는 오늘 스냅샷이 들어 있고 select_baseline이 고르는 기준일도 그때와 같다.
    반환 dict: today / baseline / window_days / today_snap / baseline_snap /
              snapshots(기준일→오늘) / dates(일별 날짜) / flows / codes
    """
    today = max(history)
    prior = sorted([d for d in history if d < today], reverse=True)
    baseline, window_days = base.select_baseline(prior, base.MAX_WINDOW)
    if not baseline:
        return None                                  # 워밍업 — flow 계산 불가
    today_snap = history[today]
    baseline_snap = history[baseline]
    flows = base.compute_flows(today_snap, baseline_snap)
    window_dates = list(reversed(prior[:window_days]))
    snapshots = [(d, history[d]) for d in window_dates] + [(today, today_snap)]
    return {
        "today": today,
        "baseline": baseline,
        "window_days": window_days,
        "today_snap": today_snap,
        "baseline_snap": baseline_snap,
        "snapshots": snapshots,
        "dates": [d for d, _ in snapshots[1:]],
        "flows": flows,
        "codes": [f["code"] for f in flows],
    }


def rollup_to_theme(per_etf, final_snap, dates):
    """ETF별 일별값을 테마로 합산. daily_by_theme와 같은 형태로 돌려준다(대조 테스트용)."""
    agg = {}
    for code, byd in per_etf.items():
        fin = final_snap.get(code)
        theme = base.classify_theme(fin["name"]) if fin else None
        if not theme:
            continue
        bucket = agg.setdefault(theme, {})
        for d, v in byd.items():
            bucket[d] = bucket.get(d, 0.0) + v
    return {
        theme: [{"date": d, "eok": round(byd.get(d, 0.0))} for d in dates]
        for theme, byd in agg.items()
    }
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

Run: `python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_flow_map.py scripts/test_build_flow_map.py
git commit -m "test(자금지도): ETF 롤업이 발행 빌더 daily_by_theme와 일치함을 실데이터로 대조"
```

---

## Task 3: ETF 행 조립 (AUM · 덩치 대비 % · 상위 20 · 그 외)

**Files:**
- Modify: `scripts/build_flow_map.py`
- Modify: `scripts/test_build_flow_map.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_build_flow_map.py`의 `def run():` 위에 추가한다.

```python
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


def test_etf_rows_pct_none_when_shares_zero():
    """좌수 0이면 비율을 만들 수 없다 — 지어내지 않고 None(뱃지 생략)."""
    today = _snap({"A": (0.0, 1e8, "KODEX 은행")})
    baseline = _snap({"A": (100.0, 1e8, "KODEX 은행")})
    flows = [{"code": "A", "name": "KODEX 은행", "theme": "금융·은행", "flow_eok": -100}]
    rows, _n, _f = m.etf_rows(flows, today, baseline, {}, ["d1"], top_n=20)
    assert rows[0]["pct"] is None
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: FAIL — `AttributeError: module 'build_flow_map' has no attribute 'etf_rows'`

- [ ] **Step 3: 최소 구현**

`scripts/build_flow_map.py`의 `rollup_to_theme` 아래에 추가한다.

```python
def etf_rows(flows, today_snap, baseline_snap, per_etf_daily, dates, top_n=TOP_ETFS_DETAIL):
    """테마 하나의 ETF flow 목록 → 화면용 행 + 잘린 나머지 요약.

    반환 (rows, rest_n, rest_flow). rows는 |flow| 내림차순 상위 top_n개.

    pct(덩치 대비 증감률) = (현재좌수 − 기준좌수) / 현재좌수 × 100.
    NAV가 약분되므로 가격 효과 없는 순수 설정/환매 비율이다. 큰 ETF의 큰 금액보다
    작은 ETF가 덩치 대비 크게 움직인 것이 더 드문 신호라서 별도로 낸다.
    """
    ranked = sorted(flows, key=lambda f: -abs(f["flow_eok"]))
    top, rest = ranked[:top_n], ranked[top_n:]

    rows = []
    for f in top:
        cur = today_snap.get(f["code"])
        bas = baseline_snap.get(f["code"])
        if not cur or not bas:
            continue                      # compute_flows가 걸렀어야 할 상태 — 지어내지 않고 건너뛴다
        shares = cur["shares"]
        byd = per_etf_daily.get(f["code"], {})
        rows.append({
            "code": f["code"],
            "name": f["name"],
            "flow": f["flow_eok"],
            "aum": round(shares * cur["nav"] / 1e8),
            "pct": round((shares - bas["shares"]) / shares * 100, 1) if shares else None,
            "daily": [round(byd.get(d, 0.0)) for d in dates],
        })
    return rows, len(rest), sum(f["flow_eok"] for f in rest)
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

Run: `python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_flow_map.py scripts/test_build_flow_map.py
git commit -m "feat(자금지도): ETF 행 조립 — AUM·덩치 대비 증감률·상위 20 절단 요약"
```

---

## Task 4: 시장 요약용 날짜축·일별 합계

**Files:**
- Modify: `scripts/build_flow_map.py`
- Modify: `scripts/test_build_flow_map.py`

날짜축(`dates`)과 전 테마 일별 합계(`market_daily`)는 **발행본 테마의 `daily`에서** 뽑는다. 재계산값을 쓰지 않는다 — 화면의 테마 합계·시장 요약은 발행본 값만 쓴다는 규약이다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: FAIL — `AttributeError: module 'build_flow_map' has no attribute 'dates_of'`

- [ ] **Step 3: 최소 구현**

`scripts/build_flow_map.py`의 `etf_rows` 아래에 추가한다.

```python
def dates_of(themes_pub):
    """발행본 테마들의 daily에서 날짜축을 뽑는다(가장 긴 것 기준)."""
    best = []
    for t in themes_pub:
        ds = [x["date"] for x in (t.get("daily") or [])]
        if len(ds) > len(best):
            best = ds
    return best


def market_daily(themes_pub, dates):
    """전 테마 일별 순유입 합계. 날짜 키로 맞춰 더한다(인덱스 위치로 더하지 않는다)."""
    acc = {d: 0 for d in dates}
    for t in themes_pub:
        for x in (t.get("daily") or []):
            if x["date"] in acc:
                acc[x["date"]] += x["eok"]
    return [acc[d] for d in dates]
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

Run: `python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_flow_map.py scripts/test_build_flow_map.py
git commit -m "feat(자금지도): 날짜축·시장 일별 합계를 발행본에서 산출"
```

---

## Task 5: 전체 조립 + 정합성 게이트

**Files:**
- Modify: `scripts/build_flow_map.py`
- Modify: `scripts/test_build_flow_map.py`

히스토리와 발행본이 다른 날짜면 **즉시 중단**한다(§0 — 어긋난 두 소스를 섞어 발행하지 않는다). 재계산 ETF 합계가 발행 테마 합계와 ±2억을 넘게 벌어져도 중단한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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


def test_build_real_data_invariants():
    """저장소 실데이터로 스펙의 불변식 2개를 확인한다.

      ① ETF 목록 합 + 그 외 합계 = 헤더 순유입액 (±3억)
      ② 일별 막대 합 = 헤더 순유입액 (±3억)
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
        assert abs(bars - t["flow_eok"]) <= 3, f"불변식② {t['theme']}: {bars} vs {t['flow_eok']}"
        assert len(t["daily"]) == len(out["dates"])
        assert len(t["etfs"]) <= m.TOP_ETFS_DETAIL
        for e in t["etfs"]:
            assert len(e["daily"]) == len(out["dates"])
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: FAIL — `AttributeError: module 'build_flow_map' has no attribute 'build'`

- [ ] **Step 3: 최소 구현**

`scripts/build_flow_map.py`의 `market_daily` 아래에 추가한다.

```python
RECONCILE_TOL_EOK = 2      # 재계산 vs 발행 테마 합계 허용 오차(억). 실측은 0이다.


def reconcile(themes_pub, flows_by_theme, tol=RECONCILE_TOL_EOK):
    """재계산 ETF 합계와 발행 테마 합계를 대조해 어긋난 항목 설명을 돌려준다."""
    bad = []
    for t in themes_pub:
        fs = flows_by_theme.get(t["theme"], [])
        got = sum(f["flow_eok"] for f in fs)
        if abs(got - t["flow_eok"]) > tol:
            bad.append(f"{t['theme']} 합계 {got} vs 발행 {t['flow_eok']}")
        if len(fs) != t["etf_count"]:
            bad.append(f"{t['theme']} ETF수 {len(fs)} vs 발행 {t['etf_count']}")
    return bad


def build(history, published, now_iso, top_n=TOP_ETFS_DETAIL):
    """발행본(테마 합계 정본) + 히스토리(ETF 분해) → 자금 지도 탭 데이터. 워밍업이면 None."""
    themes_pub = published.get("themes") or []
    if not themes_pub:
        return None

    today = max(history)
    pub_date = (published.get("generated_at") or "")[:10]
    if pub_date != today:
        raise RuntimeError(
            f"[flow-map] 날짜 불일치 — 히스토리 최신 {today} vs 발행본 {pub_date}. "
            f"어긋난 두 소스를 섞어 발행하지 않는다(운영규칙 0)."
        )

    ctx = rebuild_context(history)
    if ctx is None:
        return None

    flows_by_theme = {}
    for f in ctx["flows"]:
        if f["theme"]:
            flows_by_theme.setdefault(f["theme"], []).append(f)

    bad = reconcile(themes_pub, flows_by_theme)
    if bad:
        raise RuntimeError(
            "[flow-map] 정합성 실패 — 재계산이 발행본과 어긋난다: " + " / ".join(bad)
        )

    dates = dates_of(themes_pub)
    per_etf = daily_by_etf(ctx["snapshots"], ctx["today_snap"], ctx["codes"])

    themes = []
    for t in themes_pub:
        rows, rest_n, rest_flow = etf_rows(
            flows_by_theme.get(t["theme"], []),
            ctx["today_snap"], ctx["baseline_snap"], per_etf, dates, top_n,
        )
        by_date = {x["date"]: x["eok"] for x in (t.get("daily") or [])}
        themes.append({
            "theme": t["theme"],
            "flow_eok": t["flow_eok"],
            "gross_eok": t["gross_eok"],
            "etf_count": t["etf_count"],
            "daily": [by_date.get(d, 0) for d in dates],
            "etfs": rows,
            "rest_n": rest_n,
            "rest_flow": rest_flow,
        })

    return {
        "generated_at": now_iso,
        "source_generated_at": published.get("generated_at"),
        "window_days": published.get("window_days"),
        "aum_floor_eok": published.get("aum_floor_eok"),
        "coverage": published.get("coverage"),
        "dates": dates,
        "market_daily": market_daily(themes_pub, dates),
        "themes": themes,
    }
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

Run: `python3 -m pytest scripts/test_build_flow_map.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_flow_map.py scripts/test_build_flow_map.py
git commit -m "feat(자금지도): 발행본+히스토리 조립과 정합성 게이트(날짜 불일치·합계 드리프트 중단)"
```

---

## Task 6: CLI 진입점 + 실데이터 생성

**Files:**
- Modify: `scripts/build_flow_map.py`
- Create: `web/data/flow-map.json` (생성물)

- [ ] **Step 1: `main()` 추가**

`scripts/build_flow_map.py` 맨 아래에 추가한다.

```python
def main():
    now = datetime.now(KST)
    history = base.load_json(HISTORY_PATH, {})
    published = base.load_json(FLOWS_PATH, {})

    if not history:
        print("[flow-map] ✗ 히스토리가 비어 있음 — 파일을 건드리지 않고 중단")
        sys.exit(1)

    out = build(history, published, now.isoformat())
    if out is None:
        print("[flow-map] ⚠️ 워밍업(발행본 themes 없음) — 파일을 쓰지 않고 종료")
        return

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    etfs = sum(len(t["etfs"]) for t in out["themes"])
    print(f"[flow-map] {out['dates'][0]}~{out['dates'][-1]} · 테마 {len(out['themes'])}개 · "
          f"ETF {etfs}개 노출 · {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행해서 파일 생성**

Run: `cd /Users/ncsoft/my-project/double-shot && python3 scripts/build_flow_map.py`
Expected: `[flow-map] 2026-07-27~2026-07-31 · 테마 16개 · ETF 200개 내외 노출 · web/data/flow-map.json`

에러로 죽으면 **정합성 게이트가 제대로 잡은 것**이다. 메시지가 "날짜 불일치"면 `data/etf_flow_history.json`과 `web/data/etf-flows.json`이 서로 다른 날짜다(둘은 항상 같은 커밋에서 갱신되므로, 한쪽만 손댄 커밋이 있는지 `git log`로 확인). "정합성 실패"면 Task 1~5의 재계산 규약이 발행 빌더와 어긋난 것이다.

- [ ] **Step 3: 결과 눈으로 확인**

Run:
```bash
python3 -c "
import json
d=json.load(open('web/data/flow-map.json'))
print('dates', d['dates'])
print('market_daily', d['market_daily'])
t=d['themes'][0]
print(t['theme'], t['flow_eok'], 'etfs', len(t['etfs']), 'rest', t['rest_n'], t['rest_flow'])
print(t['etfs'][0])
"
```
Expected: `dates`가 5개, `themes[0]`이 반도체, `etfs[0]`에 `code/name/flow/aum/pct/daily` 6개 키가 모두 있음.

- [ ] **Step 4: 전체 파이썬 테스트 통과 확인**

Run: `python3 -m pytest scripts/ -q`
Expected: PASS — 기존 테스트 포함 전부 통과(기존 `test_build_etf_flows.py`도 깨지지 않아야 한다)

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_flow_map.py web/data/flow-map.json
git commit -m "feat(자금지도): 빌더 CLI 추가 및 flow-map.json 최초 생성"
```

---

## Task 7: 워크플로우 배선

**Files:**
- Modify: `.github/workflows/etf-flows.yml`

빌더는 `build_etf_flows.py` **뒤에** 돌아야 한다 — 그때야 히스토리에 오늘 스냅샷이 들어 있고 발행본도 갱신돼 있다.

- [ ] **Step 1: 실행 스텝 추가**

`.github/workflows/etf-flows.yml`에서 "🧭 ETF 자금흐름 수집" 스텝 **바로 아래**에 추가한다.

```yaml
      # build_etf_flows가 파일을 쓴 뒤 히스토리를 롤링하므로, 반드시 그 다음에 돌아야
      # 오늘 스냅샷이 히스토리에 들어 있다. 정합성 게이트가 어긋나면 여기서 실패한다(§0).
      - name: 🗺️ 자금 지도 탭 데이터 생성
        if: steps.holiday.outputs.open == 'true'
        run: python3 scripts/build_flow_map.py
```

- [ ] **Step 2: 커밋 대상에 파일 추가**

같은 파일의 "💾 JSON 커밋 & 푸시" 스텝에서 `git add` 줄을 바꾼다.

바꾸기 전:
```bash
          git add web/data/etf-flows.json data/etf_flow_history.json
```
바꾼 뒤:
```bash
          git add web/data/etf-flows.json web/data/flow-map.json data/etf_flow_history.json
```

- [ ] **Step 3: YAML 문법 확인**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/etf-flows.yml')); print('ok')"`
Expected: `ok`

(`yaml`이 없으면 `pip install pyyaml` 후 재실행)

- [ ] **Step 4: 커밋**

```bash
git add .github/workflows/etf-flows.yml
git commit -m "ci(자금지도): etf-flows 워크플로우에 flow-map 빌더 스텝·커밋 대상 추가"
```

---

## Task 8: 화면 스타일

**Files:**
- Create: `web/assets/flow-map.css`

프로토타입 v6의 CSS를 옮기되 **모든 선택자를 `#flow-map`으로 스코프**하고 클래스에 `fmap-` 접두사를 붙인다. `.block`·`.block__h`·`.stabs`·`.home-cols`·`.up`·`.dn`은 `stocks-home.css` 것을 그대로 쓴다.

- [ ] **Step 1: 파일 생성**

```css
/* 자금 지도 탭(#flow-map) 전용 스타일 — 클래스는 전부 fmap- 접두사 + #flow-map 스코프 */

/* stocks-home.css에 이미 .st/.nm/.sp/.kpi/.mk/.leg/.conc가 있어(특히 .sp는 35곳) 접두사와
   스코프를 이중으로 건다. 색 토큰(--up/--dn/--inset/--hair)과 .up/.dn/.block/.stabs는
   stocks-home.css 정의를 그대로 재사용한다 — 여기서 다시 정의하지 않는다. */

/* 2단 — 좌측을 바 리스트로 바꾸면서 3.5 : 6.5로 좁혔다(홈의 2:1 아님). */
#flow-map .home-cols{grid-template-columns:3.5fr 6.5fr;}
/* 우측(ETF 20개)이 좌측보다 훨씬 길다. 좌측을 sticky로 붙여야 하단이 비지 않고 스크롤 중에도
   테마를 바꿀 수 있다. ⚠ .home-cols가 align-items:start라 .home-main이 콘텐츠 높이로 줄면
   sticky가 움직일 공간이 없어 그냥 밀려 올라간다 — stretch로 그 열만 되돌린다. */
#flow-map .home-main{align-self:stretch;}
#flow-map .fmap-block{position:sticky;top:14px;}

#flow-map .fmap-empty{font-size:12.5px;color:var(--muted);background:var(--canvas);
  border:1px solid var(--hair);border-radius:10px;padding:14px 16px;line-height:1.6;margin:0;}
#flow-map .fmap-stale{font-size:11.5px;color:#B45309;background:#FEF3C7;
  border-radius:8px;padding:8px 11px;margin:0 0 12px;line-height:1.55;}

/* 시장 요약 3칸 */
#flow-map .fmap-mkt{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--hair);}
#flow-map .fmap-mk{background:var(--canvas);padding:10px 14px;}
#flow-map .fmap-mk .k{font-size:10.5px;font-weight:700;color:var(--muted);margin-bottom:3px;}
#flow-map .fmap-mk .v{font-size:16px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums;}
#flow-map .fmap-mk .s{font-size:11px;color:var(--muted);margin-top:2px;}

#flow-map .fmap-intro{font-size:11.5px;color:var(--muted);padding:10px 14px 0;margin:0;line-height:1.55;}
#flow-map .fmap-intro b{color:var(--ink);}
#flow-map .fmap-pad{padding:10px 14px 12px;}

/* ── 좌: 발산 바 리스트 ──
   가운데 0축 기준으로 유입은 오른쪽(빨강)·유출은 왼쪽(파랑). 방향을 색뿐 아니라 위치로도 구분한다.
   길이는 제곱근이 아니라 선형이다 — 상위 6개가 전체의 대부분이고 나머지는 실제로 미미하다는
   사실이 그대로 보이는 게 정직하다. 대신 아주 작은 값도 사라지지 않게 최소 3px을 준다. */
#flow-map .fmap-list{display:flex;flex-direction:column;gap:1px;}
/* 선택은 테두리가 아니라 음영 값으로만 구분한다 — 검은 라인 박스는 표 안에서 지나치게 튀고,
   행마다 두께가 생겨 리듬이 깨진다. 색상(hue)은 쓰지 않는다: 이 리스트는 이미
   빨강=유입/파랑=유출로 색을 쓰고 있어 선택에 색을 넣으면 방향처럼 읽힌다. */
#flow-map .fmap-r{display:grid;grid-template-columns:88px 1fr 62px;gap:8px;align-items:center;
  padding:7px 8px;border-radius:7px;cursor:pointer;background:transparent;transition:background .12s;}
#flow-map .fmap-r:hover{background:var(--inset);}
#flow-map .fmap-r.on{background:#DCE2EA;}
#flow-map .fmap-r.on .fmap-nm{font-weight:800;}
#flow-map .fmap-nm{font-size:11.5px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
#flow-map .fmap-nm em{font-style:normal;font-weight:700;color:var(--muted);font-size:10.5px;margin-left:4px;}
#flow-map .fmap-bw{position:relative;height:15px;}
#flow-map .fmap-ax{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--hair);}
#flow-map .fmap-bar{position:absolute;top:3px;bottom:3px;border-radius:2px;min-width:3px;}
#flow-map .fmap-bar.p{left:50%;background:var(--up);}
#flow-map .fmap-bar.m{right:50%;background:var(--dn);}
#flow-map .fmap-v{font-size:11.5px;font-weight:800;text-align:right;font-variant-numeric:tabular-nums;}
#flow-map .fmap-hd{display:grid;grid-template-columns:88px 1fr 62px;gap:8px;padding:0 8px 6px;
  font-size:10px;color:var(--muted);font-weight:700;border-bottom:1px solid var(--hair);margin-bottom:5px;}
#flow-map .fmap-hd .c{text-align:center;}
#flow-map .fmap-hd .r{text-align:right;}
#flow-map .fmap-leg{display:flex;gap:13px;align-items:center;font-size:11px;color:var(--muted);
  padding:9px 14px 12px;flex-wrap:wrap;}
#flow-map .fmap-leg span{display:flex;align-items:center;gap:5px;}
#flow-map .fmap-leg i{width:11px;height:11px;border-radius:3px;display:block;}
#flow-map #fmap-sorttabs{margin-bottom:0;}

/* ── 우: 상세 ── */
#flow-map .fmap-dh{padding:13px 16px;background:var(--canvas);border-bottom:1px solid var(--hair);}
#flow-map .fmap-dh .r1{display:flex;align-items:baseline;gap:10px;}
#flow-map .fmap-dh .fmap-tt{font-size:17px;font-weight:800;letter-spacing:-.02em;}
#flow-map .fmap-dh .fmap-amt{font-size:17px;font-weight:800;font-variant-numeric:tabular-nums;margin-left:auto;}
#flow-map .fmap-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:10px;}
#flow-map .fmap-kpi{background:var(--inset);border-radius:7px;padding:6px 10px;}
#flow-map .fmap-kpi .k{font-size:10px;color:var(--muted);font-weight:700;}
#flow-map .fmap-kpi .v{font-size:13px;font-weight:800;font-variant-numeric:tabular-nums;}
#flow-map .fmap-st{font-size:11.5px;font-weight:800;color:var(--ink);margin:0 0 8px;
  display:flex;align-items:baseline;gap:5px;}
#flow-map .fmap-st .n{font-weight:600;color:var(--muted);font-size:10.5px;}

/* 일별 차트 — 폭을 470px로 묶고 막대를 54px로 좁힌다. 우측 패널이 679px가 되면서 flex:1이
   폭을 다 먹어 막대 하나가 130px 폭 × 7~28px 높이가 됐고, 가로:세로 3:1을 넘으면 막대가
   아니라 납작한 판으로 읽힌다. */
#flow-map .fmap-days{display:flex;gap:8px;align-items:flex-end;max-width:470px;margin:0 auto;}
#flow-map .fmap-dy{flex:1;display:flex;flex-direction:column;align-items:center;}
#flow-map .fmap-dy .u,#flow-map .fmap-dy .d{width:100%;display:flex;flex-direction:column;align-items:center;}
#flow-map .fmap-dy .u{height:56px;justify-content:flex-end;}
#flow-map .fmap-dy .d{height:40px;justify-content:flex-start;}
#flow-map .fmap-dy .b{width:54px;max-width:100%;border-radius:3px;}
#flow-map .fmap-dy .b.p{background:rgba(224,49,49,.85);border-radius:3px 3px 0 0;}
#flow-map .fmap-dy .b.m{background:rgba(39,117,237,.85);border-radius:0 0 3px 3px;}
#flow-map .fmap-dy .z{height:1px;background:#CBD5E1;width:100%;}
#flow-map .fmap-dy .v{font-size:10.5px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap;}
#flow-map .fmap-dy .lb{font-size:10px;color:var(--muted);margin-top:5px;text-align:center;line-height:1.35;}
#flow-map .fmap-dy .q{font-size:9.5px;font-weight:700;}
#flow-map .fmap-dy .q.same{color:#94A3B8;}
#flow-map .fmap-dy .q.opp{color:#B45309;}

/* 좌우 패딩 11px = 아래 .fmap-er 행의 border(1) + padding(10). 이 값을 맞춰야 그룹 헤더의
   "유입 N개"·합계가 아래 ETF 이름·금액과 같은 세로선에 선다. .fmap-er의 padding이나 border를
   바꾸면 여기도 같이 바꿔야 한다. */
#flow-map .fmap-gh{display:flex;align-items:center;gap:6px;font-size:11.5px;font-weight:800;
  margin:16px 0 6px;padding:0 11px 6px;border-bottom:1px solid var(--hair);}
#flow-map .fmap-gh .dot{width:7px;height:7px;border-radius:2px;display:block;}
#flow-map .fmap-gh .sum{margin-left:auto;font-variant-numeric:tabular-nums;}
#flow-map .fmap-gh.i{color:var(--up);}
#flow-map .fmap-gh.i .dot{background:var(--up);}
#flow-map .fmap-gh.o{color:var(--dn);}
#flow-map .fmap-gh.o .dot{background:var(--dn);}
#flow-map .fmap-er{display:grid;grid-template-columns:1fr auto auto auto;gap:10px;align-items:center;
  padding:8px 10px;border-radius:7px;margin-bottom:4px;background:var(--canvas);border:1px solid var(--hair);}
#flow-map .fmap-er .en{font-size:12.5px;font-weight:700;min-width:0;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;}
#flow-map .fmap-er .eaum{font-size:10.5px;color:var(--muted);font-variant-numeric:tabular-nums;
  white-space:nowrap;display:flex;align-items:center;gap:5px;}
#flow-map .fmap-er .efl{font-size:12.5px;font-weight:800;font-variant-numeric:tabular-nums;
  white-space:nowrap;text-align:right;min-width:66px;}
/* 스파크라인 — 0축 위 유입 / 아래 유출. 각 ETF 자기 최대로 정규화한다(그룹 공통 기준이면
   작은 ETF가 전부 납작한 점선이 돼 '데이터 없음'처럼 보인다). 절대 규모는 옆 금액이 말해준다. */
#flow-map .fmap-sp{display:flex;gap:2px;height:15px;width:54px;}
#flow-map .fmap-sp .c{flex:1;display:flex;flex-direction:column;height:100%;}
#flow-map .fmap-sp .h{flex:1;display:flex;}
#flow-map .fmap-sp .h.u{align-items:flex-end;}
#flow-map .fmap-sp i{width:100%;border-radius:1px;min-height:1px;display:block;}
#flow-map .fmap-sp .z{height:1px;background:var(--hair);}
#flow-map .fmap-pill{font-size:9.5px;font-weight:800;padding:1px 5px;border-radius:4px;white-space:nowrap;}
#flow-map .fmap-pill.hot{background:var(--up-bg);color:#B91C1C;}
#flow-map .fmap-pill.cold{background:var(--dn-bg);color:#1D4ED8;}
#flow-map .fmap-rest{font-size:11px;color:var(--muted);background:var(--inset);border-radius:7px;
  padding:8px 10px;margin-top:8px;line-height:1.5;}
#flow-map .fmap-rest b{color:var(--ink);}
#flow-map .fmap-conc{font-size:11px;color:var(--muted);margin-top:8px;}
#flow-map .fmap-conc b{color:var(--ink);}

/* ⚠ 미디어쿼리는 반드시 위 기본 규칙들보다 **뒤에** 둔다. 앞에 두면 같은 특이도의 뒤따르는
   기본 규칙에 덮여 좁은 화면에서 조용히 무시된다(프로토타입에서 실제로 겪은 실수). */
@media(max-width:900px){
  /* stocks-home.css의 .home-cols 축소 규칙(minmax(0,1fr))은 specificity가 낮아
     이 파일의 무조건 규칙(#flow-map .home-cols, 위)에 항상 진다 — 미디어쿼리 안에
     있어도 소용없다(같은 selector가 아니라 specificity 차이라 media query만으로는
     못 이긴다). 여기서 같은 값으로 직접 되돌려야 실제로 1단으로 풀린다. */
  #flow-map .home-cols{grid-template-columns:minmax(0,1fr);}
  /* stocks-home.css가 .home-main/.home-side를 display:contents로 이미 풀어준다.
     여기선 좌측 블록을 위로 올리고 sticky만 해제한다. */
  #flow-map .fmap-block{order:-1;position:static;}
}
@media(max-width:560px){
  #flow-map .fmap-mkt{grid-template-columns:1fr;}
  #flow-map .fmap-r{grid-template-columns:74px 1fr 58px;gap:6px;}
  #flow-map .fmap-hd{grid-template-columns:74px 1fr 58px;gap:6px;}
  #flow-map .fmap-er{grid-template-columns:1fr auto;row-gap:6px;}
  #flow-map .fmap-days{gap:5px;}
  #flow-map .fmap-dy .b{width:38px;}
}
```

- [ ] **Step 2: 커밋**

```bash
git add web/assets/flow-map.css
git commit -m "feat(자금지도): 탭 전용 스타일 추가(#flow-map 스코프 + fmap- 접두사)"
```

---

## Task 9: 화면 스크립트 — 순수 함수

**Files:**
- Create: `web/assets/flow-map.js`
- Create: `web/assets/flow-map.test.mjs`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/assets/flow-map.test.mjs`를 새로 만든다.

```js
// flow-map.js 순수 함수 테스트 — node:vm 샌드박스에서 실제 프로덕션 파일을 로드해 검증
//
// 순수 함수를 테스트 파일에 복제하면 사본이 원본과 어긋나므로(SERVICE_RULES §20류),
// 실제 파일을 최소 DOM 스텁과 함께 실행하고 window.__flowMap으로 꺼내 검증한다.
// ds-subnav.test.mjs·sector-screen.test.mjs와 같은 패턴.
//
// 실행: node --test web/assets/flow-map.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const noop = () => {};

function mkEl() {
  const e = {
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    style: {}, innerHTML: '', textContent: '',
    addEventListener: noop, setAttribute: noop, getAttribute: () => null,
    closest: () => null, querySelector: () => null, querySelectorAll: () => [],
  };
  return e;
}

/** flow-map.js를 vm에서 실행하고 공개 API를 돌려준다. */
function load() {
  const els = {};
  const win = {
    location: { pathname: '/stocks/', hash: '' },
    addEventListener: noop,
    fetch: () => new Promise(() => {}),        // 실제 네트워크는 타지 않는다
    document: {
      readyState: 'complete',
      getElementById: (id) => (els[id] || (els[id] = mkEl())),
      addEventListener: noop,
      querySelector: () => null,
      querySelectorAll: () => [],
    },
  };
  win.window = win;
  const ctx = createContext(win);
  runInContext(readFileSync(join(HERE, 'flow-map.js'), 'utf8'), ctx);
  return { api: win.__flowMap, els, win };
}

test('eok — 억/조 단위 포맷과 부호', () => {
  const { eok } = load().api;
  assert.equal(eok(9500), '+9,500억');
  assert.equal(eok(-74), '−74억');            // U+2212 마이너스
  assert.equal(eok(0), '0억');
  assert.equal(eok(15592), '+1.6조');         // 1만억 이상은 조로 접는다
  assert.equal(eok(25000), '+2.5조');
  assert.equal(eok(-120000), '−12조');        // 10조 이상은 소수점 없이
});

test('wd — 요일은 Date.UTC 조립으로 구한다(오프바이원 회귀)', () => {
  const { wd } = load().api;
  // 'YYYY-MM-DDT00:00:00+09:00' 파싱은 KST 자정 = 전날 15:00 UTC라 getUTCDay()가 하루 밀린다.
  assert.equal(wd('2026-07-31'), '금');
  assert.equal(wd('2026-08-03'), '월');
  assert.equal(wd('2026-07-27'), '월');
});

test('churn — 회전율은 gross / |net|, net 0이어도 나눗셈이 깨지지 않는다', () => {
  const { churn } = load().api;
  assert.equal(churn({ gross_eok: 1700, flow_eok: 100 }), 17);
  assert.equal(churn({ gross_eok: 50, flow_eok: 0 }), 50);
});

test('barPct — 한쪽 최대 50%, 전체 최대치 기준', () => {
  const { barPct } = load().api;
  assert.equal(barPct(100, 100), '50.00');
  assert.equal(barPct(-50, 100), '25.00');
  assert.equal(barPct(0, 0), '0.00');         // 전 테마 0 — 0으로 나누지 않는다
});

test('pivot — 금액이 아니라 동조 테마 수로 고른다', () => {
  const { pivot } = load().api;
  const themes = [
    { daily: [1, -1] }, { daily: [1, -1] }, { daily: [-1, -1] }, { daily: [-1, -1] },
  ];
  // d0: 시장 +, 같은 방향 2개 / d1: 시장 −, 같은 방향 4개 → 금액이 작아도 d1이 선정
  const r = pivot([9999, -10], themes);
  assert.equal(r.i, 1);
  assert.equal(r.same, 4);
});

test('pivot — 동수면 금액으로 타이브레이크', () => {
  const { pivot } = load().api;
  const themes = [{ daily: [1, 1] }, { daily: [1, 1] }];
  assert.equal(pivot([10, 500], themes).i, 1);
});

test('staleDays — 마지막 갱신 경과 일수', () => {
  const { staleDays } = load().api;
  const now = Date.parse('2026-08-06T20:00:00+09:00');
  assert.equal(staleDays('2026-08-06T18:00:00+09:00', now), 0);
  assert.equal(staleDays('2026-07-31T18:00:00+09:00', now), 6);
  assert.equal(staleDays('nonsense', now), null);
});
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `cd /Users/ncsoft/my-project/double-shot && node --test web/assets/flow-map.test.mjs`
Expected: FAIL — `ENOENT: no such file or directory ... flow-map.js`

- [ ] **Step 3: 최소 구현**

`web/assets/flow-map.js`를 새로 만든다.

```js
// 자금 지도 탭(#flow-map) 화면 — /data/flow-map.json을 받아 테마 바 리스트와 테마 상세를 그린다
//
// 이 파일이 stocks-home.js가 아니라 별도 파일인 이유: stocks-home.js는 이미 3,300줄이 넘어
// 화면 하나를 더 얹으면 읽기도 테스트하기도 어려워진다. ds-subnav.js가 만든 선례를 따른다.
(function () {
  'use strict';

  // 같은 페이지에 두 번 로드돼도 리스너가 겹쳐 쌓이지 않게 한다(ds-subnav.js와 같은 가드).
  if (window.__flowMapInited) return;
  window.__flowMapInited = true;

  var DATA = null, DATES = [], MKT = [], TH = [], sortKey = 'size';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /** 억원 → 표시 문자열. 1조 이상은 조 단위로 접는다. 마이너스는 U+2212(−). */
  function eok(v) {
    var a = Math.abs(v), sg = v > 0 ? '+' : (v < 0 ? '−' : '');
    if (a >= 10000) return sg + (a / 10000).toFixed(a >= 100000 ? 0 : 1).replace(/\.0$/, '') + '조';
    return sg + a.toLocaleString('en-US') + '억';
  }

  /** 총량 표시 — 부호를 떼고 절대값만. */
  function amt(v) { return eok(Math.abs(v)).replace(/^[+−]/, ''); }

  function md(d) { return String(d).slice(5).replace('-', '/'); }

  /** 요일. Date.UTC로 조립한 뒤 getUTCDay()를 쓴다 —
      'YYYY-MM-DDT00:00:00+09:00' 파싱은 KST 자정이 전날 15:00 UTC라 요일이 하루 밀린다. */
  function wd(d) {
    var p = String(d).split('-');
    return ['일', '월', '화', '수', '목', '금', '토'][
      new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay()];
  }

  /** 회전율 — 테마 안에서 돈이 얼마나 돌았나. 분모는 gross가 아니라 |net|이다. */
  function churn(t) { return t.gross_eok / Math.max(Math.abs(t.flow_eok), 1); }

  var SORTS = {
    size: function (a, b) { return Math.abs(b.flow_eok) - Math.abs(a.flow_eok); },
    net: function (a, b) { return b.flow_eok - a.flow_eok; },        // 유입 위 → 유출 아래
    churn: function (a, b) { return churn(b) - churn(a); }
  };

  /** 막대 폭(%). 0축이 가운데라 한쪽 최대 50%. 제곱근으로 부풀리지 않는다 — 상위 몇 개가
      사실상 전부라는 게 이 데이터의 진실이고 그대로 보이는 편이 정직하다. */
  function barPct(v, mx) { return (Math.abs(v) / (mx || 1) * 50).toFixed(2); }

  /** 가장 많은 테마가 한꺼번에 움직인 날. 기준은 금액이 아니라 **동조 테마 수(breadth)** —
      절대금액 최대일로 고르면 "15/16개가 동시에 뒤집힌 날"을 놓친다. 이 화면의 주제는
      규모가 아니라 폭이다. 동수면 금액으로 타이브레이크. 반환 {i, same}. */
  function pivot(mkt, themes) {
    var n = (mkt || []).length;
    if (!n) return { i: -1, same: 0 };
    var same = mkt.map(function (m, i) {
      return themes.filter(function (t) {
        var v = (t.daily || [])[i];
        return m >= 0 ? v > 0 : v < 0;
      }).length;
    });
    var p = 0;
    for (var i = 1; i < n; i++) {
      if (same[i] > same[p] || (same[i] === same[p] && Math.abs(mkt[i]) > Math.abs(mkt[p]))) p = i;
    }
    return { i: p, same: same[p] };
  }

  /** 마지막 갱신 이후 경과 일수. 파싱 실패면 null(판단하지 않는다). */
  function staleDays(iso, nowMs) {
    var t = Date.parse(iso);
    if (!isFinite(t)) return null;
    return Math.floor(((nowMs == null ? Date.now() : nowMs) - t) / 864e5);
  }

  window.__flowMap = {
    esc: esc, eok: eok, amt: amt, md: md, wd: wd,
    churn: churn, SORTS: SORTS, barPct: barPct, pivot: pivot, staleDays: staleDays
  };
})();
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

Run: `node --test web/assets/flow-map.test.mjs`
Expected: PASS (7 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/assets/flow-map.js web/assets/flow-map.test.mjs
git commit -m "feat(자금지도): 화면 스크립트 순수 함수(포맷·정렬·pivot) + 테스트"
```

---

## Task 10: 화면 스크립트 — 렌더 + 데이터 로드

**Files:**
- Modify: `web/assets/flow-map.js`
- Modify: `web/assets/flow-map.test.mjs`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/assets/flow-map.test.mjs` 맨 아래에 추가한다.

```js
/** 렌더 테스트용 최소 데이터 — 테마 2개, 3거래일. */
function fixture() {
  return {
    generated_at: '2026-07-31T18:05:00+09:00',
    source_generated_at: '2026-07-31T18:00:00+09:00',
    window_days: 3, aum_floor_eok: 300,
    coverage: { etf_count: 712, theme_count: 2 },
    dates: ['2026-07-29', '2026-07-30', '2026-07-31'],
    market_daily: [100, -200, 300],
    themes: [
      { theme: '반도체', flow_eok: 1500, gross_eok: 1800, etf_count: 30,
        daily: [400, -100, 1200],
        etfs: [
          { code: '1', name: 'TIGER 반도체', flow: 900, aum: 5000, pct: 18.0, daily: [300, -50, 650] },
          { code: '2', name: 'KODEX 반도체', flow: -200, aum: 4000, pct: -5.0, daily: [-50, -50, -100] },
        ],
        rest_n: 28, rest_flow: 800 },
      { theme: '채권', flow_eok: -74, gross_eok: 900, etf_count: 108,
        daily: [-30, -24, -20],
        etfs: [{ code: '3', name: 'KODEX 국고채', flow: -74, aum: 2000, pct: -3.7, daily: [-30, -24, -20] }],
        rest_n: 0, rest_flow: 0 },
    ],
  };
}

test('render — 시장 요약 3칸이 채워지고 pivot이 동조 수로 뽑힌다', () => {
  const { api, els } = load();
  api.render(fixture());
  const html = els['fmap-mkt'].innerHTML;
  assert.match(html, /3거래일 누적/);
  assert.match(html, /\+200억/);                 // 100 − 200 + 300
  // 금액 최대일은 07/31(+300)이지만 동조 테마는 1개뿐이고, 07/30은 −200으로 작아도
  // 두 테마가 함께 움직였다. 이 화면의 주제는 규모가 아니라 폭이므로 07/30이 뽑혀야 한다.
  assert.match(html, /07\/30\(목\)/);
  assert.match(html, /2\/2개 동시 유출/);
});

test('render — 전체 테마를 그리고 첫 테마가 기본 선택된다', () => {
  const { api, els } = load();
  api.render(fixture());
  const html = els['fmap-list'].innerHTML;
  assert.match(html, /data-th="반도체"/);
  assert.match(html, /data-th="채권"/);
  assert.match(html, /class="fmap-r on" data-th="반도체"/);
});

test('render — 막대 기준값은 정렬과 무관하게 전체 최대치로 고정', () => {
  const { api, els } = load();
  api.render(fixture());
  const before = els['fmap-list'].innerHTML.match(/data-th="반도체"[\s\S]*?width:([\d.]+)%/)[1];
  api.setSort('churn');
  const after = els['fmap-list'].innerHTML.match(/data-th="반도체"[\s\S]*?width:([\d.]+)%/)[1];
  assert.equal(before, after);
  assert.equal(before, '50.00');                 // |1500|이 전체 최대치
});

test('render — 정렬을 바꿔도 선택된 테마와 상세는 유지된다', () => {
  const { api, els } = load();
  api.render(fixture());
  api.select('채권');
  assert.match(els['fmap-detail'].innerHTML, /채권/);
  api.setSort('net');
  assert.match(els['fmap-list'].innerHTML, /class="fmap-r on" data-th="채권"/);
  assert.match(els['fmap-detail'].innerHTML, /채권/);   // 상세는 그대로
});

test('detail — 그 외 N개 절단을 명시하고, 10% 미만은 뱃지를 달지 않는다', () => {
  const { api, els } = load();
  api.render(fixture());
  const html = els['fmap-detail'].innerHTML;
  assert.match(html, /그 외 <b>28개<\/b>/);
  assert.match(html, /\+800억/);
  assert.match(html, /fmap-pill hot">\+18%/);          // 18.0% → 뱃지
  assert.doesNotMatch(html, /fmap-pill cold">−5%/);    // 5.0% → 뱃지 없음
});

test('detail — 일별 막대에 시장 동조/반대가 붙는다', () => {
  const { api, els } = load();
  api.render(fixture());
  api.select('반도체');
  const html = els['fmap-detail'].innerHTML;
  // 시장 [100,−200,300] vs 반도체 [400,−100,1200] → 전부 같은 방향
  assert.equal((html.match(/시장 동조/g) || []).length, 3);
  api.select('채권');
  // 채권 [−30,−24,−20] vs 시장 [+,−,+] → 1·3일차가 반대
  assert.equal((els['fmap-detail'].innerHTML.match(/시장 반대/g) || []).length, 2);
});

test('render — 데이터가 비면 빈 상태만 보여주고 본문을 그리지 않는다', () => {
  const { api, els } = load();
  api.render({ dates: [], market_daily: [], themes: [] });
  assert.equal(els['fmap-content'].style.display, 'none');
  assert.equal(els['fmap-empty'].style.display, '');
  assert.match(els['fmap-empty'].textContent, /준비 중/);
});
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `node --test web/assets/flow-map.test.mjs`
Expected: FAIL — `TypeError: api.render is not a function`

- [ ] **Step 3: 구현**

`web/assets/flow-map.js`의 `window.__flowMap = {...}` **바로 위**에 아래를 삽입하고, `window.__flowMap` 객체에 `render`·`select`·`setSort`를 추가한다.

```js
  function $(id) { return document.getElementById(id); }

  function setText(id, s) { var el = $(id); if (el) el.textContent = s; }
  function setHtml(id, s) { var el = $(id); if (el) el.innerHTML = s; }

  /* ── 시장 요약 ── */
  function renderMarket() {
    var cum = MKT.reduce(function (a, b) { return a + b; }, 0);
    var pv = pivot(MKT, TH);
    var inn = TH.filter(function (t) { return t.flow_eok > 0; }).length;
    var pvCell = pv.i < 0 ? '<div class="v">—</div><div class="s">데이터 부족</div>'
      : '<div class="v ' + (MKT[pv.i] >= 0 ? 'up' : 'dn') + '">'
        + md(DATES[pv.i]) + '(' + wd(DATES[pv.i]) + ')</div>'
        + '<div class="s">' + pv.same + '/' + TH.length + '개 동시 '
        + (MKT[pv.i] < 0 ? '유출' : '유입') + ' · ' + eok(MKT[pv.i]) + '</div>';
    setHtml('fmap-mkt',
      '<div class="fmap-mk"><div class="k">' + DATES.length + '거래일 누적</div>'
      + '<div class="v ' + (cum >= 0 ? 'up' : 'dn') + '">' + eok(cum) + '</div>'
      + '<div class="s">전 테마 합계</div></div>'
      + '<div class="fmap-mk"><div class="k">가장 많은 테마가 한꺼번에 움직인 날</div>' + pvCell + '</div>'
      + '<div class="fmap-mk"><div class="k">유입 / 유출 테마</div>'
      + '<div class="v">' + inn + ' <span style="color:var(--muted);font-size:13px">/ '
      + (TH.length - inn) + '</span></div>'
      + '<div class="s">' + DATES.length + '일 누적 기준</div></div>');
  }

  /* ── 좌: 발산 바 리스트 ── */
  function renderList() {
    // 막대 기준값은 정렬과 무관하게 항상 전체 최대치 — 정렬마다 최대치를 다시 잡으면
    // 같은 테마의 막대 길이가 들쭉날쭉해져 비교가 깨진다.
    var mx = Math.max.apply(null, TH.map(function (t) { return Math.abs(t.flow_eok); }));
    // 선택 상태는 DOM이 아니라 selected 변수가 정본이다 — 다시 그려도 그대로 살아남고,
    // 정렬만 바뀌고 우측 상세는 유지된다.
    var sel = selected;
    setHtml('fmap-list', TH.slice().sort(SORTS[sortKey]).map(function (t) {
      var pos = t.flow_eok >= 0;
      // 회전율 정렬일 때만 배수를 이름 옆에 붙인다 — 왜 이 순서인지 근거를 보여준다.
      var sub = sortKey === 'churn' ? ' <em>' + churn(t).toFixed(1) + '배</em>' : '';
      return '<div class="fmap-r' + (t.theme === sel ? ' on' : '') + '" data-th="' + esc(t.theme)
        + '" title="' + esc(t.theme) + ' · ETF ' + t.etf_count + '개">'
        + '<span class="fmap-nm">' + esc(t.theme) + sub + '</span>'
        + '<span class="fmap-bw"><i class="fmap-ax"></i>'
        + '<i class="fmap-bar ' + (pos ? 'p' : 'm') + '" style="width:'
        + barPct(t.flow_eok, mx) + '%"></i></span>'
        + '<span class="fmap-v ' + (pos ? 'up' : 'dn') + '">' + eok(t.flow_eok) + '</span></div>';
    }).join(''));
  }

  /* ── 우: 상세 ── */
  function etfGroup(title, list, cls) {
    if (!list.length) return '';
    var sum = list.reduce(function (s, e) { return s + e.flow; }, 0);
    return '<div class="fmap-gh ' + cls + '"><i class="dot"></i>' + title + ' ' + list.length + '개'
      + '<span class="sum">' + eok(sum) + '</span></div>'
      + list.map(function (e) {
        var emx = Math.max.apply(null, e.daily.map(Math.abs)) || 1;   // 자기 기준 정규화
        var sp = e.daily.map(function (v) {
          var hh = Math.max(1, Math.abs(v) / emx * 7);
          var bg = v >= 0 ? 'rgba(224,49,49,.85)' : 'rgba(39,117,237,.85)';
          return '<div class="c"><div class="h u">'
            + (v >= 0 ? '<i style="height:' + hh + 'px;background:' + bg + '"></i>' : '')
            + '</div><div class="z"></div><div class="h">'
            + (v < 0 ? '<i style="height:' + hh + 'px;background:' + bg + '"></i>' : '')
            + '</div></div>';
        }).join('');
        // 덩치 대비 % — 큰 ETF의 큰 금액보다 작은 ETF가 덩치 대비 크게 움직인 게 더 드문 신호.
        // 10% 미만은 노이즈라 뱃지를 달지 않는다.
        var pl = (e.pct != null && Math.abs(e.pct) >= 10)
          ? '<span class="fmap-pill ' + (e.pct > 0 ? 'hot' : 'cold') + '">'
            + (e.pct > 0 ? '+' : '−') + Math.abs(Math.round(e.pct)) + '%</span>' : '';
        return '<div class="fmap-er"><span class="en">' + esc(e.name) + '</span>'
          + '<span class="eaum">AUM ' + amt(e.aum) + pl + '</span>'
          + '<span class="fmap-sp">' + sp + '</span>'
          + '<span class="efl ' + (e.flow >= 0 ? 'up' : 'dn') + '">' + eok(e.flow) + '</span></div>';
      }).join('');
  }

  function detail(theme) {
    var t = TH.filter(function (x) { return x.theme === theme; })[0];
    if (!t) return;
    selected = theme;
    var ch = Math.abs(t.flow_eok) ? t.gross_eok / Math.abs(t.flow_eok) : 0;
    var shown = t.etfs.reduce(function (s, e) { return s + Math.abs(e.flow); }, 0);
    var conc = t.gross_eok ? Math.max(0, Math.min(100, Math.round(shown / t.gross_eok * 100))) : 0;

    var h = '<div class="fmap-dh"><div class="r1"><span class="fmap-tt">' + esc(t.theme) + '</span>'
      + '<span class="fmap-amt ' + (t.flow_eok >= 0 ? 'up' : 'dn') + '">' + eok(t.flow_eok) + '</span></div>'
      + '<div class="fmap-kpis">'
      + '<div class="fmap-kpi"><div class="k">오간 돈</div><div class="v">' + amt(t.gross_eok) + '</div></div>'
      + '<div class="fmap-kpi"><div class="k">회전율</div><div class="v">' + ch.toFixed(1) + '배</div></div>'
      + '<div class="fmap-kpi"><div class="k">ETF</div><div class="v">' + t.etf_count + '개</div></div>'
      + '</div></div><div class="fmap-pad" style="padding:12px 16px 14px">';

    var dmx = Math.max.apply(null, t.daily.map(Math.abs)) || 1;
    h += '<div class="fmap-st">일별 순유입 <span class="n">막대 합 = 위 누적값</span></div>'
      + '<div class="fmap-days">';
    t.daily.forEach(function (v, i) {
      var pos = v >= 0, ht = Math.max(3, Math.round(Math.abs(v) / dmx * (pos ? 50 : 34)));
      // 시장 파도를 기준선으로 먼저 세워야 "그 파도 대비 무엇이 버텼는지"라는 신호가 남는다.
      var opp = (MKT[i] > 0 && v < 0) || (MKT[i] < 0 && v > 0);
      h += '<div class="fmap-dy"><div class="u">'
        + (pos ? '<span class="v up">' + eok(v) + '</span><i class="b p" style="height:' + ht + 'px"></i>' : '')
        + '</div><div class="z"></div><div class="d">'
        + (pos ? '' : '<i class="b m" style="height:' + ht + 'px"></i><span class="v dn">' + eok(v) + '</span>')
        + '</div><span class="lb">' + md(DATES[i]) + '(' + wd(DATES[i]) + ')<br>'
        + '<span class="q ' + (opp ? 'opp' : 'same') + '">' + (opp ? '시장 반대' : '시장 동조')
        + '</span></span></div>';
    });
    h += '</div>';

    h += etfGroup('유입', t.etfs.filter(function (e) { return e.flow >= 0; }), 'i')
      + etfGroup('유출', t.etfs.filter(function (e) { return e.flow < 0; }), 'o');

    // 절단은 숨기지 않는다 — 목록에서 빠졌을 뿐 위 누적값에는 포함돼 있다(운영규칙 0).
    if (t.rest_n) {
      h += '<div class="fmap-rest">그 외 <b>' + t.rest_n + '개</b> 합계 <b>' + eok(t.rest_flow)
        + '</b> — 금액이 작아 목록에선 생략했지만 위 누적값에는 포함돼 있어요.</div>';
    }
    h += '<div class="fmap-conc">위 <b>' + t.etfs.length + '개</b>가 이 테마에서 오간 돈의 <b>'
      + conc + '%</b>를 차지해요. <span style="color:var(--muted)">%는 AUM 대비 증감</span></div>';

    setHtml('fmap-detail', h + '</div>');

    var rows = document.querySelectorAll('.fmap-r');
    for (var i = 0; i < rows.length; i++) {
      rows[i].classList.toggle('on', rows[i].getAttribute('data-th') === theme);
    }
  }

  function setSort(key) {
    if (!SORTS[key]) return;
    sortKey = key;
    var tabs = $('fmap-sorttabs');
    if (tabs && tabs.querySelectorAll) {
      var as = tabs.querySelectorAll('a');
      for (var i = 0; i < as.length; i++) {
        as[i].classList.toggle('on', as[i].getAttribute('data-sort') === key);
      }
    }
    renderList();   // 선택된 테마는 renderList가 읽어 유지한다 — 정렬만 바뀌고 상세는 그대로
  }

  function showEmpty(msg) {
    var c = $('fmap-content'), e = $('fmap-empty');
    if (c) c.style.display = 'none';
    if (e) { e.style.display = ''; e.textContent = msg; }
  }

  function render(data) {
    DATA = data || {};
    TH = (DATA.themes || []).slice().sort(SORTS.size);
    DATES = DATA.dates || [];
    MKT = DATA.market_daily || [];
    if (!TH.length || !DATES.length) {
      showEmpty('자금 지도 데이터를 준비 중이에요. 평일 18:00에 갱신돼요.');
      return;
    }
    var c = $('fmap-content'), e = $('fmap-empty');
    if (c) c.style.display = '';
    if (e) e.style.display = 'none';

    setText('fmap-sub', md(DATES[0]) + '~' + md(DATES[DATES.length - 1]) + ' 누적 · '
      + 'ETF 설정/환매 실측 · ' + DATES.length + '거래일');
    setText('fmap-win', '· ' + md(DATES[0]) + '~' + md(DATES[DATES.length - 1]) + ' 누적');
    setText('fmap-legn', TH.length + '개 전부 · 막대 길이는 실제 비례');

    // 오래된 데이터도 감추지 않고 그대로 보여주되 언제 것인지 명시한다 — 사용자가 직접 눌러
    // 들어온 화면이라, 날짜를 밝히고 보여주는 편이 통째로 숨기는 것보다 정직하다.
    var sd = staleDays(DATA.source_generated_at || DATA.generated_at);
    var stale = $('fmap-stale');
    if (stale) {
      if (sd != null && sd >= 5) {
        stale.style.display = '';
        stale.textContent = '마지막 갱신이 ' + sd + '일 전(' + String(DATA.source_generated_at || '').slice(0, 10)
          + ')이에요. 평일 18:00에 갱신돼요.';
      } else {
        stale.style.display = 'none';
      }
    }

    // 빈 상태를 두지 않는다 — 규모 1위 테마를 먼저 편다.
    // selected를 renderList 앞에서 정해야 첫 렌더부터 선택 행에 음영이 들어간다.
    selected = TH[0].theme;
    renderMarket();
    renderList();
    detail(selected);
  }

  function boot() {
    if (!$('flow-map')) return;   // 이 화면이 없는 페이지에서는 아무것도 하지 않는다
    var tabs = $('fmap-sorttabs');
    if (tabs) {
      tabs.addEventListener('click', function (ev) {
        var a = ev.target && ev.target.closest ? ev.target.closest('a[data-sort]') : null;
        if (a) setSort(a.getAttribute('data-sort'));
      });
    }
    // 리스트는 매번 innerHTML로 다시 그리므로 리스너는 개별 행이 아니라 컨테이너에 건다.
    var list = $('fmap-list');
    if (list) {
      list.addEventListener('click', function (ev) {
        var el = ev.target && ev.target.closest ? ev.target.closest('.fmap-r') : null;
        if (el) detail(el.getAttribute('data-th'));
      });
    }
    window.fetch('/data/flow-map.json', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d) render(d);
        else showEmpty('자금 지도 데이터를 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.');
      })
      .catch(function () {
        showEmpty('자금 지도 데이터를 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.');
      });
  }
```

또한 파일 상단의 상태 변수 줄을 아래로 바꾼다(선택 테마 보관용 `selected` 추가).

바꾸기 전:
```js
  var DATA = null, DATES = [], MKT = [], TH = [], sortKey = 'size';
```
바꾼 뒤:
```js
  var DATA = null, DATES = [], MKT = [], TH = [], sortKey = 'size', selected = null;
```

그리고 `window.__flowMap` 객체와 부트스트랩을 아래로 교체한다.

```js
  window.__flowMap = {
    esc: esc, eok: eok, amt: amt, md: md, wd: wd,
    churn: churn, SORTS: SORTS, barPct: barPct, pivot: pivot, staleDays: staleDays,
    render: render, select: detail, setSort: setSort
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

Run: `node --test web/assets/flow-map.test.mjs`
Expected: PASS (14 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/assets/flow-map.js web/assets/flow-map.test.mjs
git commit -m "feat(자금지도): 시장 요약·바 리스트·테마 상세 렌더와 데이터 로드"
```

---

## Task 11: 화면 마크업과 에셋 연결

**Files:**
- Modify: `web/stocks/index.html`

- [ ] **Step 1: 에셋 태그 추가**

`web/stocks/index.html` 25번째 줄(`<script src="/assets/ds-subnav.js?v=1" defer></script>`) **바로 아래**에 추가한다.

```html
<script src="/assets/flow-map.js?v=1" defer></script>
```

28번째 줄(`<link rel="stylesheet" href="/assets/ds-subnav.css?v=1">`) **바로 아래**에 추가한다.

```html
<link rel="stylesheet" href="/assets/flow-map.css?v=1">
```

- [ ] **Step 2: 화면 마크업 추가**

`<div class="screen" id="etf-rank">`가 시작하는 줄 **바로 앞**에 아래 블록을 통째로 넣는다(서브탭 순서와 DOM 순서를 맞춘다 — 섹터 다음, ETF 앞).

```html
  <!-- 🧭 자금 지도 — flow-map.js가 /data/flow-map.json을 받아 채운다.
       테마 합계·일별·시장 요약은 전부 발행본 etf-flows.json 값을 승계한 것이고,
       ETF 분해만 히스토리에서 재계산한 값이다(빌더 scripts/build_flow_map.py). -->
  <div class="screen" id="flow-map">
    <div class="phead">
      <div><h1><span class="ic">🧭</span> 자금 지도</h1>
        <div class="psub" id="fmap-sub">—</div></div>
    </div>
    <p class="fmap-stale" id="fmap-stale" style="display:none;"></p>
    <p class="fmap-empty" id="fmap-empty" style="display:none;"></p>
    <div id="fmap-content" style="display:none;">
      <div class="block" style="margin-bottom:14px;"><div class="fmap-mkt" id="fmap-mkt"></div></div>
      <div class="home-cols">
        <div class="home-main">
          <div class="block fmap-block" style="margin-bottom:0;">
            <div class="block__h"><span class="block__t"><span class="ic">🧭</span>테마별 순유입</span>
              <span class="block__s"><span class="stabs" id="fmap-sorttabs">
                <a class="on" data-sort="size">규모순</a><a data-sort="net">유입순</a><a data-sort="churn">회전율순</a>
              </span></span></div>
            <p class="fmap-intro">가운데 선이 0. 오른쪽으로 뻗으면 <b>유입</b>, 왼쪽이면 <b>유출</b>.
              <b>행을 누르면 오른쪽 상세가 바뀌어요.</b> <span id="fmap-win"></span></p>
            <div class="fmap-pad">
              <div class="fmap-hd"><span>테마</span><span class="c">유출 ← 0 → 유입</span><span class="r">순유입</span></div>
              <div class="fmap-list" id="fmap-list"></div>
            </div>
            <div class="fmap-leg">
              <span><i style="background:var(--up)"></i>유입</span>
              <span><i style="background:var(--dn)"></i>유출</span>
              <span id="fmap-legn"></span>
            </div>
          </div>
        </div>
        <div class="home-side">
          <div class="block" style="margin-bottom:0;" id="fmap-detail"></div>
        </div>
      </div>
    </div>
  </div>
```

- [ ] **Step 3: 화면 id가 하나만 있는지 확인**

Run: `grep -c 'id="flow-map"' web/stocks/index.html`
Expected: `1`

Run: `grep -o 'id="fmap-[a-z]*"' web/stocks/index.html | sort`
Expected: 아래 10개가 각각 정확히 한 번씩 나온다 — `fmap-content` `fmap-detail` `fmap-empty` `fmap-legn` `fmap-list` `fmap-mkt` `fmap-sorttabs` `fmap-stale` `fmap-sub` `fmap-win`. 빠진 게 있으면 `flow-map.js`의 `setText`/`setHtml`이 조용히 no-op가 되어 그 영역만 빈 채로 남는다.

- [ ] **Step 4: 커밋**

```bash
git add web/stocks/index.html
git commit -m "feat(자금지도): #flow-map 화면 마크업과 에셋 태그 추가"
```

---

## Task 12: 서브탭 등록

**Files:**
- Modify: `web/assets/ds-subnav.js:27-34`
- Modify: `web/assets/ds-subnav.test.mjs:54-55`

`ds-subnav.js`는 `TABS` 한 곳만 고치면 해시 판정·렌더·클릭이 전부 따라오도록 설계돼 있다(파일 주석 참조). 다른 표를 만들지 말 것.

- [ ] **Step 1: 실패하는 테스트로 바꾸기**

`web/assets/ds-subnav.test.mjs` 54~55줄을 아래로 바꾼다.

```js
  assert.deepEqual(Array.from(TABS.map((t) => t.id)), ['home', 'signals', 'sector', 'flow', 'etf']);
  assert.deepEqual(Array.from(TABS.map((t) => t.label)), ['전체', '특이신호', '섹터', '자금 지도', 'ETF']);
```

같은 테스트의 이름도 개수에 맞게 바꾼다.

바꾸기 전:
```js
test('탭 정의는 이번 범위인 4개만 점등한다', () => {
```
바꾼 뒤:
```js
test('탭 정의는 이번 범위인 5개만 점등한다', () => {
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인**

Run: `node --test web/assets/ds-subnav.test.mjs`
Expected: FAIL — 탭 id 배열이 `['home','signals','sector','etf']`라 단언 불일치

- [ ] **Step 3: 탭 추가**

`web/assets/ds-subnav.js`의 `TABS` 배열에서 `sector`와 `etf` 사이에 한 줄 넣는다.

바꾸기 전:
```js
    { id: 'sector',  label: '섹터',     href: '/stocks/#sector',      screen: 'sector' },
    { id: 'etf',     label: 'ETF',      href: '/stocks/#etf-rank',    screen: 'etf-rank' },
```
바꾼 뒤:
```js
    { id: 'sector',  label: '섹터',     href: '/stocks/#sector',      screen: 'sector' },
    { id: 'flow',    label: '자금 지도', href: '/stocks/#flow-map',    screen: 'flow-map' },
    { id: 'etf',     label: 'ETF',      href: '/stocks/#etf-rank',    screen: 'etf-rank' },
```

- [ ] **Step 4: 테스트를 돌려 통과 확인**

Run: `node --test web/assets/ds-subnav.test.mjs`
Expected: PASS — 특히 "TABS의 screen 값이 index.html에 실제로 있는 화면 id와 일치한다" 테스트가 Task 11의 마크업 덕에 통과해야 한다. 여기서 실패하면 `#flow-map` 화면 마크업이 없거나 id 오타다.

- [ ] **Step 5: 커밋**

```bash
git add web/assets/ds-subnav.js web/assets/ds-subnav.test.mjs
git commit -m "feat(자금지도): 서브탭에 자금 지도 등록(섹터와 ETF 사이)"
```

---

## Task 13: 홈 위젯에서 탭으로 가는 링크

**Files:**
- Modify: `web/stocks/index.html` (`#flow-block` 헤더)

홈의 "이번 주 자금 지도" 위젯에서 확대 화면으로 넘어가는 경로를 만든다.

- [ ] **Step 1: 링크 추가**

`web/stocks/index.html`의 `#flow-block` 블록 헤더에서 `<span class="block__s" id="flow-window"></span>` 줄을 아래로 바꾼다.

바꾸기 전:
```html
<span class="block__s" id="flow-window"></span>
```
바꾼 뒤:
```html
<span class="block__s"><span id="flow-window"></span> <a href="/stocks/#flow-map" onclick="go('flow-map');return false;">전체 보기 →</a></span>
```

- [ ] **Step 2: 확인**

Run: `grep -n 'flow-map' web/stocks/index.html | head`
Expected: 화면 마크업(`id="flow-map"`)과 이 링크 두 군데가 잡힌다.

- [ ] **Step 3: 커밋**

```bash
git add web/stocks/index.html
git commit -m "feat(자금지도): 홈 자금 지도 위젯에서 탭으로 가는 전체 보기 링크"
```

---

## Task 14: 전체 검증

**Files:** 없음(확인만)

- [ ] **Step 1: 파이썬 테스트 전체**

Run: `cd /Users/ncsoft/my-project/double-shot && python3 -m pytest scripts/ -q`
Expected: 전부 통과. **착수 전 기준선은 559 passed**이므로, 이 계획이 더한 13개를 합쳐 572가 되어야 한다. 숫자가 그보다 적으면 새 테스트가 수집되지 않은 것이고, 실패가 있으면 그 파일만 다시 돌려 원인을 읽고 고친다(추측 금지).

- [ ] **Step 2: JS 테스트 전체**

Run: `node --test api/*.test.mjs && node --test web/assets/*.test.mjs`
Expected: 전부 통과. **착수 전 기준선은 web/assets 111 pass**이므로, 이 계획이 더한 14개를 합쳐 125가 되어야 한다(`ds-subnav.test.mjs`는 개수 변화 없이 단언만 바뀐다).

- [ ] **Step 3: 빌더 재실행이 멱등한지 확인**

Run:
```bash
python3 scripts/build_flow_map.py && git diff --stat web/data/flow-map.json
```
Expected: `generated_at`만 바뀐다(그 외 필드는 동일). 다른 필드가 바뀌면 빌더에 비결정적 요소가 있는 것이다.

Run: `git checkout -- web/data/flow-map.json`

- [ ] **Step 4: 브라우저에서 실제 확인**

`.claude/launch.json`에 정적 서버 설정이 있으면 그것으로, 없으면 아래로 띄운다.

```bash
python3 -m http.server 8765 --directory web
```

`http://localhost:8765/stocks/#flow-map`을 열어 확인한다.

- 서브탭에 "자금 지도"가 섹터와 ETF 사이에 있고, 눌렀을 때 활성 표시가 그 탭으로 옮겨간다.
- 시장 요약 3칸이 채워진다("가장 많은 테마가 한꺼번에 움직인 날"이 —가 아니어야 한다).
- 좌측 리스트에 테마 16개가 전부 있고, 가운데 0축 기준으로 유입은 오른쪽 빨강 / 유출은 왼쪽 파랑이다.
- 행을 누르면 우측 상세가 바뀌고, 선택 행에 음영이 들어간다(테두리가 아니라).
- 정렬 탭 3개를 눌러도 **선택한 테마와 우측 상세가 유지**되고, 같은 테마의 막대 길이가 정렬에 따라 변하지 않는다.
- 우측 일별 차트의 막대가 납작한 판이 아니라 세로 막대로 보인다(폭 54px).
- 채권 테마를 선택하면 "그 외 N개 합계"가 뜬다.
- 브라우저 폭을 900px 이하로 줄이면 1단으로 풀리고 지도가 위로 올라온다. 560px에서도 시장 요약 3칸이 잘리지 않는다.
- 콘솔에 에러가 없다.

- [ ] **Step 5: 불변식을 화면에서 직접 확인**

한 테마를 골라 우측 상세에서 **일별 막대 값을 손으로 더한 값**이 헤더 순유입액과 3억 이내인지, **ETF 목록 금액 합 + "그 외" 합계**가 헤더 값과 3억 이내인지 눈으로 확인한다. 어긋나면 Task 5의 테스트가 통과했는데 화면이 틀린 것이므로 렌더 쪽(`detail()`)을 의심한다.

- [ ] **Step 6: 최종 커밋(변경이 남아 있다면)**

```bash
git status --short
```
Expected: 깨끗함. 남은 게 있으면 어느 Task의 누락인지 확인하고 그 Task의 커밋 메시지 규칙에 맞춰 커밋한다.

---

## 구현 시 주의할 함정 (스펙에서 옮김)

1. **요일 오프바이원** — `new Date('YYYY-MM-DDT00:00:00+09:00').getUTCDay()`는 KST 자정을 UTC로 해석해 하루 밀린다. 반드시 `Date.UTC(y, m-1, d)`로 조립한 뒤 `getUTCDay()`. Task 9의 `wd()`와 그 테스트가 이걸 못박는다.
2. **미디어쿼리 우선순위** — `@media` 블록은 기본 규칙보다 **뒤에** 둔다. 앞에 두면 같은 특이도의 뒤따르는 규칙에 덮여 좁은 화면에서 조용히 무시된다. Task 8 CSS의 마지막 두 블록 위치를 바꾸지 말 것.
3. **일별 환산은 최종 NAV 고정** — 날짜별 NAV를 쓰면 telescoping이 깨져 일별 합이 헤더 누적값과 최대 17.9%까지 어긋난다. Task 1의 `daily_by_etf`가 `final_snap["nav"]`만 쓰는지 확인.
4. **sticky가 안 먹는 경우** — `.home-cols`가 `align-items:start`라 `.home-main`이 콘텐츠 높이로 줄면 sticky가 움직일 공간이 없다. `#flow-map .home-main{align-self:stretch}`를 지우지 말 것.
5. **클래스 이름 충돌** — `.st`·`.nm`·`.sp`·`.kpi`·`.mk`·`.leg`·`.conc`는 `stocks-home.css`에 이미 있다. 새 클래스는 반드시 `fmap-` 접두사 + `#flow-map` 스코프.
6. **`#flow-map .home-cols`가 모바일에서 안 풀림(2026-08-06 Task 8 코드 리뷰에서 실제 헤드리스 크롬 렌더로 발견)** — `#flow-map .home-cols{grid-template-columns:3.5fr 6.5fr}`(specificity 1,1,0)가 무조건 규칙이라, `stocks-home.css`의 `@media(max-width:900px){.home-cols{...minmax(0,1fr)}}`(specificity 0,1,0)를 미디어쿼리 안에 있어도 이긴다 — "미디어쿼리가 나중에 오면 이긴다"는 함정 2번 규칙은 **같은 selector일 때만** 성립하고, specificity가 다르면 안 통한다. `@media(max-width:900px)` 블록 안에 `#flow-map .home-cols{grid-template-columns:minmax(0,1fr)}`를 직접 추가해야 실제로 1단으로 풀린다(위 CSS에 이미 반영됨).
