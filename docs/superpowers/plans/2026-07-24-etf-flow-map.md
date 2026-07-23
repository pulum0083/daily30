# ETF 자금 지도 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 대시보드 홈(home-main, 밸류에이션 자리)에 테마별 ETF 순자금흐름(설정/환매)을 트리맵 히트맵으로 보여주는 "이번 주 자금 지도" 블록을 추가한다.

**Architecture:** 신규 파이썬 파이프라인이 매일 네이버 ETF 목록에서 AUM·NAV를 수집해 추정 좌수를 스냅샷으로 롤링 저장하고, 최대 5거래일 전 스냅샷과 차분해 테마별 순자금흐름을 `web/data/etf-flows.json`으로 낸다. 전용 일일 워크플로우가 평일 장 마감 후 실행하며 자기 파일만 커밋한다(§18). 홈은 이 JSON을 로드해 크기=|flow|·색=방향의 트리맵으로 렌더하고, 스냅샷이 없는 워밍업 첫날엔 블록을 숨긴다.

**Tech Stack:** Python 3.12(표준 라이브러리 urllib만), 순수함수 단위 테스트(pytest 없이 `python3 scripts/test_*.py`), 바닐라 JS 홈 위젯(IIFE + fetch), GitHub Actions.

---

## File Structure

- Create `scripts/build_etf_flows.py` — 수집·좌수추정·스냅샷 롤링·차분·테마집계·출력. 순수함수 + `main()`.
- Create `scripts/test_build_etf_flows.py` — 순수함수 단위 테스트(네트워크 없음).
- Create `.github/workflows/etf-flows.yml` — 평일 18:00 KST 전용 워크플로우.
- Modify `web/stocks/index.html` — home-main에 블록 마크업 삽입(섹터 브라우저 아래).
- Modify `web/assets/stocks-home.js` — 렌더러 IIFE 추가(fetch·트리맵·클릭확장·신선도가드).
- Modify `web/assets/stocks-home.css` — 히트맵 타일 스타일.
- 생성물(스크립트가 씀, 사람이 직접 안 만듦): `data/etf_flow_history.json`, `web/data/etf-flows.json`.

데이터 단위 규약(전 파일 공통): `marketSum`은 **억원**, `nav`는 **원**. `shares = marketSum×1e8÷nav`. `flow_eok = (shares_now − shares_prev)×nav ÷ 1e8`(억원).

---

## Task 1: 순수함수 — 좌수추정·테마분류·flow계산·적응형윈도우

**Files:**
- Create: `scripts/build_etf_flows.py`
- Test: `scripts/test_build_etf_flows.py`

- [ ] **Step 1: 테스트 작성** — `scripts/test_build_etf_flows.py`

```python
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


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd scripts && python3 test_build_etf_flows.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_etf_flows'`

- [ ] **Step 3: 순수함수 구현** — `scripts/build_etf_flows.py` 생성(파일 상단부터)

```python
# 네이버 ETF 목록에서 테마별 순자금흐름(설정/환매)을 집계하는 자금 지도 파이프라인
#!/usr/bin/env python3
"""
ETF 자금 지도 파이프라인 (v1).

네이버 ETF 목록 API로 전 ETF의 AUM·NAV를 수집해 추정 좌수를 매일 스냅샷으로
저장하고, 최대 5거래일 전 스냅샷과 차분해 테마별 순자금흐름(억원)을 낸다.
가격 효과를 벗겨낸 순수 설정/환매 기준이라, "돈이 어디로 몰리나"를 보여준다.

지표:
  shares   ≈ marketSum(억원)×1e8 ÷ nav(원)          — 추정 발행좌수
  flow_eok = (shares_now − shares_prev)×nav ÷ 1e8    — 순자금흐름(억원)
  적응형 윈도우: 가진 스냅샷 만큼, 최대 5거래일 누적

정합성(SERVICE_RULES 운영규칙 0):
  - AUM 300억+ ETF만 집계(소형은 억원 반올림 노이즈가 커 제외)
  - 백필 불가(네이버는 현재 AUM만 제공) → 스냅샷 시작 이전은 계산 안 함
  - 어느 테마에도 안 잡히는 ETF는 지도에서 제외

산출:
  data/etf_flow_history.json   — 좌수 스냅샷(최근 7거래일 롤링, 커밋)
  web/data/etf-flows.json      — 테마별 순유입 + 테마별 상위 ETF (홈 블록용)

Usage:
  python3 scripts/build_etf_flows.py                    # 운영(AUM 300억+)
  python3 scripts/build_etf_flows.py --aum-floor 500    # 500억+
"""
import argparse
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

ETF_LIST_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"
ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "data" / "etf_flow_history.json"
OUT_PATH = ROOT / "web" / "data" / "etf-flows.json"

MAX_WINDOW = 5      # 최대 누적 거래일
KEEP_DAYS = 7       # 히스토리 보관 거래일(윈도우 + 버퍼)
TOP_ETFS = 5        # 테마별 상위 ETF 노출 수

# 테마 분류 — 순서 중요(먼저 매칭되는 규칙이 이김). 'TOP'·바 '금'/'은' 같은
# 오분류 유발 키워드는 쓰지 않는다(반도체TOP10 → 배당 오분류, 은행 → 금 오분류 방지).
THEME_RULES = [
    ("반도체",          ["반도체", "HBM"]),
    ("2차전지",         ["2차전지", "배터리", "리튬"]),
    ("자동차",          ["자동차", "모빌리티"]),
    ("방산",            ["방산", "우주항공", "K방산"]),
    ("조선",            ["조선"]),
    ("바이오·헬스",      ["바이오", "헬스", "제약", "의료"]),
    ("금융·은행",        ["은행", "금융", "증권", "보험"]),
    ("인터넷·게임",      ["인터넷", "게임", "미디어", "엔터"]),
    ("원자력·전력",      ["원자력", "전력", "태양광", "신재생"]),
    ("미국 나스닥·기술",  ["나스닥", "필라델피아", "미국테크", "미국AI", "미국반도체"]),
    ("미국 S&P·대형",    ["S&P", "미국500", "미국대표", "다우"]),
    ("중국·신흥국",      ["중국", "차이나", "인도", "베트남", "신흥"]),
    ("일본·유럽",        ["일본", "유럽", "니케이"]),
    ("채권",            ["채권", "국고채", "회사채", "통안", "미국채", "CD금리", "KOFR", "단기채"]),
    ("금·원자재",        ["원유", "구리", "원자재", "WTI", "골드", "금현물", "금선물", "은선물"]),
    ("배당·커버드콜",     ["배당", "커버드콜", "인컴", "리츠", "프리미엄", "고배당", "위클리", "데일리"]),
]


def estimate_shares(marketsum_eok, nav):
    """추정 발행좌수. NAV·AUM 결측/0이면 None."""
    if not marketsum_eok or not nav or nav <= 0:
        return None
    return marketsum_eok * 1e8 / nav


def classify_theme(name):
    """ETF 이름 → 테마명. 어느 규칙에도 안 걸리면 None(지도 제외)."""
    if not name:
        return None
    for theme, kws in THEME_RULES:
        for kw in kws:
            if kw in name:
                return theme
    return None


def net_flow_eok(shares_now, shares_prev, nav):
    """순자금흐름(억원, 정수 반올림). 양수 유입 / 음수 유출."""
    return round((shares_now - shares_prev) * nav / 1e8)


def select_baseline(prior_dates_desc, max_window):
    """과거 스냅샷 날짜(내림차순)에서 기준 스냅샷을 고른다.

    가진 만큼 최대 max_window거래일 전을 기준으로. 반환 (baseline_date, window_days).
    스냅샷이 0개면 (None, 0) — 워밍업 첫날, flow 계산 불가.
    """
    p = len(prior_dates_desc)
    if p == 0:
        return (None, 0)
    k = min(max_window, p)
    return (prior_dates_desc[k - 1], k)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd scripts && python3 test_build_etf_flows.py`
Expected: PASS — `4 passed`

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_etf_flows.py scripts/test_build_etf_flows.py
git commit -m "feat(etf-flows): 좌수추정·테마분류·flow계산·적응형윈도우 순수함수 + 테스트"
```

---

## Task 2: 순수함수 — 히스토리 롤링·테마 집계

**Files:**
- Modify: `scripts/build_etf_flows.py` (Task 1 함수들 아래에 추가)
- Test: `scripts/test_build_etf_flows.py` (테스트 추가)

- [ ] **Step 1: 테스트 추가** — `run()` 함수 위에 아래 두 테스트 삽입

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd scripts && python3 test_build_etf_flows.py`
Expected: FAIL — `AttributeError: module 'build_etf_flows' has no attribute 'roll_history'`

- [ ] **Step 3: 구현 추가** — `select_baseline` 아래에 삽입

```python
def roll_history(history, today, snapshot, keep_days=KEEP_DAYS):
    """오늘 스냅샷을 추가하고 최근 keep_days거래일만 남긴다."""
    out = dict(history)
    out[today] = snapshot
    keep = sorted(out.keys(), reverse=True)[:keep_days]
    return {d: out[d] for d in keep}


def aggregate_by_theme(flows, top_n=TOP_ETFS):
    """ETF별 flow 리스트 → 테마별 집계. None 테마 제외, |합| 내림차순."""
    buckets = {}
    for f in flows:
        theme = f.get("theme")
        if not theme:
            continue
        b = buckets.setdefault(theme, {"theme": theme, "flow_eok": 0, "etfs": []})
        b["flow_eok"] += f["flow_eok"]
        b["etfs"].append(f)
    out = []
    for b in buckets.values():
        top = sorted(b["etfs"], key=lambda x: -abs(x["flow_eok"]))[:top_n]
        out.append({
            "theme": b["theme"],
            "flow_eok": b["flow_eok"],
            "etf_count": len(b["etfs"]),
            "top_etfs": [{"code": e["code"], "name": e["name"], "flow_eok": e["flow_eok"]} for e in top],
        })
    out.sort(key=lambda t: -abs(t["flow_eok"]))
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd scripts && python3 test_build_etf_flows.py`
Expected: PASS — `6 passed`

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_etf_flows.py scripts/test_build_etf_flows.py
git commit -m "feat(etf-flows): 히스토리 롤링·테마 집계 함수 + 테스트"
```

---

## Task 3: 네트워크 수집 + main 파이프라인

**Files:**
- Modify: `scripts/build_etf_flows.py` (Task 2 함수들 아래에 추가)

네트워크 함수는 단위 테스트하지 않는다(실 API 의존). 대신 Task 8에서 합성 히스토리로 스모크 검증한다.

- [ ] **Step 1: 수집·main 구현** — `aggregate_by_theme` 아래에 삽입

```python
def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def fetch_etf_list():
    """네이버 ETF 목록(euc-kr) → [{code,name,nav,aum_eok}] (AUM·NAV 유효한 것만)."""
    req = urllib.request.Request(ETF_LIST_URL, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=15).read().decode("euc-kr")
    items = json.loads(raw)["result"]["etfItemList"]
    out = []
    for e in items:
        nav = e.get("nav")
        aum = e.get("marketSum")   # 억원
        if not nav or not aum:
            continue
        out.append({
            "code": e["itemcode"],
            "name": e["itemname"],
            "nav": float(nav),
            "aum_eok": aum,
        })
    return out


def build_today_snapshot(etfs, aum_floor):
    """AUM 필터 통과 ETF의 오늘 스냅샷 {code: {shares, nav, name}}."""
    snap = {}
    for e in etfs:
        if e["aum_eok"] < aum_floor:
            continue
        shares = estimate_shares(e["aum_eok"], e["nav"])
        if shares is None:
            continue
        snap[e["code"]] = {"shares": shares, "nav": e["nav"], "name": e["name"]}
    return snap


def compute_flows(today_snap, baseline_snap):
    """오늘 vs 기준 스냅샷 차분 → ETF별 flow 리스트(양쪽에 다 있는 종목만)."""
    flows = []
    for code, cur in today_snap.items():
        base = baseline_snap.get(code)
        if not base:
            continue   # 신규 상장 등 기준에 없는 종목은 제외
        flows.append({
            "code": code,
            "name": cur["name"],
            "theme": classify_theme(cur["name"]),
            "flow_eok": net_flow_eok(cur["shares"], base["shares"], cur["nav"]),
        })
    return flows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aum-floor", type=int, default=300, help="집계 대상 최소 AUM(억원)")
    args = ap.parse_args()

    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

    etfs = fetch_etf_list()
    today_snap = build_today_snapshot(etfs, args.aum_floor)

    history = load_json(HISTORY_PATH, {})
    prior_dates = sorted([d for d in history if d < today], reverse=True)
    baseline_date, window_days = select_baseline(prior_dates, MAX_WINDOW)

    themes = []
    if baseline_date:
        themes = aggregate_by_theme(compute_flows(today_snap, history[baseline_date]))

    OUT_PATH.write_text(json.dumps({
        "generated_at": now.isoformat(),
        "window_days": window_days,
        "aum_floor_eok": args.aum_floor,
        "coverage": {"etf_count": len(today_snap), "theme_count": len(themes)},
        "themes": themes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    new_history = roll_history(history, today, today_snap)
    HISTORY_PATH.write_text(json.dumps(new_history, ensure_ascii=False), encoding="utf-8")

    print(f"[etf-flows] {today} · ETF {len(today_snap)}개 · window {window_days}일 · 테마 {len(themes)}개")
    if not baseline_date:
        print("[etf-flows] ⚠️ 스냅샷 부족(워밍업) — themes 비어있음, 블록 숨김 상태")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 기존 테스트 여전히 통과 확인**(네트워크 함수 추가가 순수함수를 깨지 않았는지)

Run: `cd scripts && python3 test_build_etf_flows.py`
Expected: PASS — `6 passed`

- [ ] **Step 3: 커밋**

```bash
git add scripts/build_etf_flows.py
git commit -m "feat(etf-flows): 네이버 수집 + main 파이프라인(스냅샷 차분·JSON 출력)"
```

---

## Task 4: 전용 일일 워크플로우

**Files:**
- Create: `.github/workflows/etf-flows.yml`

- [ ] **Step 1: 워크플로우 작성** — `stock-news-weekend.yml`의 §17·§18 방어 패턴을 그대로 따른다

```yaml
# ETF 자금 지도 수집 워크플로우
#
# 평일 장 마감 후(KST 18:00) ETF 순자금흐름 스냅샷을 찍어 web/data/etf-flows.json을 낸다.
# 자기 파일만 커밋한다(SERVICE_RULES §18 — 넓은 경로를 통째로 add 하지 않는다).
# 순자산 EOD 확정 후라야 좌수 추정이 정확하므로 마감보다 늦게 돈다.
#
# 스케줄(GHA native cron, UTC 기준 — KST = UTC+9):
#   '0 9 * * 1-5' → KST 평일 18:00

name: ETF 자금 지도 수집

on:
  schedule:
    - cron: '0 9 * * 1-5'
  workflow_dispatch:

permissions:
  contents: write
  actions: write   # vercel-deploy.yml 명시적 dispatch

concurrency:
  group: etf-flows
  cancel-in-progress: false

jobs:
  run:
    name: "🧭 ETF 자금 지도 수집"
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: 📥 체크아웃
        uses: actions/checkout@v6
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      # GHA cron 지연 발화 방어 — 실제 실행이 주말이면 스킵(거래일만 윈도우 전진)
      - name: 🗓️ 평일 여부 확인
        id: guard
        run: |
          dow=$(TZ=Asia/Seoul date +%u)   # 1=월 … 7=일
          if [ "$dow" -le 5 ]; then
            echo "weekday=true" >> "$GITHUB_OUTPUT"
          else
            echo "weekday=false" >> "$GITHUB_OUTPUT"
            echo "::notice::KST 기준 주말($dow)이라 건너뜁니다 — cron 지연 발화로 판단."
          fi

      - name: 🐍 Python 세팅
        if: steps.guard.outputs.weekday == 'true'
        uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: 🧭 ETF 자금흐름 수집
        if: steps.guard.outputs.weekday == 'true'
        run: python3 scripts/build_etf_flows.py

      - name: 💾 JSON 커밋 & 푸시
        id: commit
        if: steps.guard.outputs.weekday == 'true'
        run: |
          git config user.name  "DailyB Bot"
          git config user.email "dailyb-bot@users.noreply.github.com"
          # 이 워크플로우가 소유한 파일만 커밋한다(§18).
          git add web/data/etf-flows.json data/etf_flow_history.json
          if git diff --cached --quiet; then
            echo "변경 없음, 커밋 스킵"
            echo "pushed=false" >> "$GITHUB_OUTPUT"
          else
            git commit -m "data: ETF 자금 지도 갱신 $(TZ=Asia/Seoul date +'%Y-%m-%d') KST"
            pushed=false
            for i in 1 2 3 4 5; do
              git fetch origin main
              if git rebase origin/main; then
                if git push; then pushed=true; break; fi
              else
                git rebase --abort 2>/dev/null || true
              fi
              echo "Push attempt $i failed, retrying in 15s..."
              sleep 15
            done
            echo "pushed=$pushed" >> "$GITHUB_OUTPUT"
            # 5회 모두 실패하면 명시적으로 중단(§17 — 무음 실패 방지).
            if [ "$pushed" != "true" ]; then
              echo "::error::push 5회 재시도 모두 실패 — 잡을 중단합니다."
              exit 1
            fi
          fi

      - name: 🚀 Vercel 배포 트리거
        if: steps.commit.outputs.pushed == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          sha=$(git rev-parse HEAD)
          for i in 1 2 3 4 5; do
            if gh workflow run vercel-deploy.yml --ref main -f sha="$sha"; then break; fi
            echo "dispatch attempt $i failed, retrying in 10s..."
            sleep 10
          done
```

- [ ] **Step 2: YAML 문법 검증**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/etf-flows.yml'))" && echo OK`
Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/etf-flows.yml
git commit -m "ci(etf-flows): 평일 18:00 KST 자금 지도 수집 워크플로우(§17·§18 방어)"
```

---

## Task 5: 홈 블록 마크업

**Files:**
- Modify: `web/stocks/index.html` (line 150 `</div><!-- /home-main -->` 직전, 섹터 브라우저 블록 아래)

- [ ] **Step 1: 블록 삽입** — `web/stocks/index.html`의 `</div><!-- /home-main -->`(현재 line 151) 바로 위에 아래 마크업 추가

```html
    <!-- 🧭 이번 주 자금 지도 (ETF 순유입·유출 히트맵) · JS가 /data/etf-flows.json 로드해 렌더, 데이터 없으면 숨김 -->
    <div class="block flow-block" id="flow-block" style="display:none;">
      <div class="block__h"><span class="block__t"><span class="ic">🧭</span><span id="flow-title">이번 주 자금 지도</span><span class="help-q" data-tip-title="자금 지도란?" data-tip="국내·해외·채권·원자재 <b>ETF로 실제로 들어오고 나간 돈</b>(설정·환매)을 테마별로 묶어 보여줘요.<br><br>· <b>타일 크기</b> = 이번 주 움직인 자금 규모<br>· <b>색</b> = 방향(빨강 유입 / 파랑 유출), 진할수록 큼<br><br>ETF 순자산 ÷ 기준가로 추정한 발행좌수의 하루하루 변화를 누적했어요(최대 5거래일). 가격이 올라 순자산이 는 건 제외하고, <b>순수하게 좌수가 늘고 준 것</b>만 집계해요. 투자 권유가 아닌 참고용이에요.">?</span></span><span class="block__s" id="flow-window"></span></div>
      <div class="flow-body" id="flow-body"></div>
      <p class="flow-quiet" id="flow-quiet"></p>
      <div class="flow-leg">
        <span>크기 = 움직인 자금</span>
        <span>유입 <span class="flow-scale"><i style="background:rgba(224,49,49,0.25)"></i><i style="background:rgba(224,49,49,0.55)"></i><i style="background:rgba(224,49,49,1)"></i></span></span>
        <span>유출 <span class="flow-scale"><i style="background:rgba(39,117,237,0.25)"></i><i style="background:rgba(39,117,237,0.55)"></i><i style="background:rgba(39,117,237,1)"></i></span></span>
      </div>
    </div>
```

- [ ] **Step 2: 삽입 위치 확인**

Run: `grep -n "flow-block\|/home-main" web/stocks/index.html | head`
Expected: `flow-block` 줄이 `/home-main` 줄보다 먼저 나온다(같은 home-main 안).

- [ ] **Step 3: 커밋**

```bash
git add web/stocks/index.html
git commit -m "feat(stocks): 홈에 '이번 주 자금 지도' 블록 마크업(기본 숨김)"
```

---

## Task 6: JS 렌더러 (트리맵·클릭확장·신선도가드)

**Files:**
- Modify: `web/assets/stocks-home.js` (파일 끝, 다른 홈 위젯 IIFE들과 같은 위치에 추가)

렌더 규칙: |flow| 상위 10개 테마를 순위 티어로 배치(1~2위=1행 큰 타일, 3~4위=2행, 5~7위=3행, 8~10위=4행). 각 타일 flex-grow=|flow|, 색 alpha=0.15+0.85×(|flow|/maxFlow), 텍스트는 alpha>0.46이면 흰색. 나머지 테마는 아래 한 줄 요약. `generated_at`이 5일보다 오래됐거나(§20 기준, 주말 버퍼) themes 비면 블록 숨김.

- [ ] **Step 1: 렌더러 IIFE 추가** — `web/assets/stocks-home.js` 파일 맨 끝에 삽입

```javascript
/* ── 🧭 이번 주 자금 지도 (ETF 순유입·유출 히트맵) ── */
(function(){
  var block=document.getElementById('flow-block');
  if(!block) return;
  var body=document.getElementById('flow-body');
  var TIERS=[[0,2,98],[2,4,74],[4,7,60],[7,10,48]];  // [start,end,rowHeightPx]

  function fmtEok(v){
    var a=Math.abs(v), sign=v>0?'+':(v<0?'−':'');
    if(a>=10000) return sign+(a/10000).toFixed(1).replace(/\.0$/,'')+'조';
    return sign+a.toLocaleString('en-US')+'억';
  }
  function tileStyle(flow,maxFlow){
    var inten=maxFlow?Math.abs(flow)/maxFlow:0;
    var alpha=(0.15+0.85*inten).toFixed(2);
    var rgb=flow>=0?'224,49,49':'39,117,237';
    var fg=alpha>0.46?'#fff':'#0F172A';
    return 'background:rgba('+rgb+','+alpha+');color:'+fg+';';
  }
  function tileHtml(t,maxFlow){
    return '<div class="flow-tile" style="flex:'+Math.abs(t.flow_eok)+';'+tileStyle(t.flow_eok,maxFlow)
      +'" data-theme="'+t.theme+'">'
      +'<div class="ft-nm">'+t.theme+'</div><div class="ft-amt">'+fmtEok(t.flow_eok)+'</div></div>';
  }
  function expandHtml(t){
    var rows=(t.top_etfs||[]).map(function(e){
      return '<div class="ft-ex-row"><span>'+e.name+'</span><span class="'+(e.flow_eok>=0?'ft-in':'ft-out')+'">'
        +fmtEok(e.flow_eok)+'</span></div>';
    }).join('');
    return '<div class="ft-expand" data-for="'+t.theme+'">'+rows+'</div>';
  }

  function render(data){
    var themes=(data.themes||[]).slice();
    if(!themes.length){ block.style.display='none'; return; }
    var visible=themes.slice(0,10), rest=themes.slice(10);
    var maxFlow=Math.max.apply(null, visible.map(function(t){return Math.abs(t.flow_eok);}));

    var html='';
    TIERS.forEach(function(tier){
      var seg=visible.slice(tier[0],tier[1]);
      if(!seg.length) return;
      html+='<div class="flow-row" style="height:'+tier[2]+'px;">'
        +seg.map(function(t){return tileHtml(t,maxFlow);}).join('')+'</div>';
    });
    body.innerHTML=html;

    var win=document.getElementById('flow-window');
    if(win) win.textContent='최근 '+(data.window_days||1)+'거래일 · 실측 설정/환매';
    var quiet=document.getElementById('flow-quiet');
    if(quiet){
      quiet.textContent=rest.length
        ? '그 외 '+rest.length+'개 테마는 이번 주 자금 이동이 크지 않았어요.' : '';
      quiet.style.display=rest.length?'':'none';
    }
    // 타일 클릭 → 인라인 확장(상위 ETF). 다시 누르면 접힘.
    body.querySelectorAll('.flow-tile').forEach(function(el){
      el.addEventListener('click',function(){
        var theme=el.getAttribute('data-theme');
        var open=body.querySelector('.ft-expand[data-for="'+CSS.escape(theme)+'"]');
        body.querySelectorAll('.ft-expand').forEach(function(x){x.remove();});
        if(open) return;
        var t=visible.filter(function(x){return x.theme===theme;})[0];
        if(t) el.closest('.flow-row').insertAdjacentHTML('afterend',expandHtml(t));
      });
    });
    block.style.display='';
  }

  function isFresh(iso){
    if(!iso) return false;
    // 5일 = 평일 갱신 + 주말·연휴 버퍼(§20 밸류에이션 가드와 동일 기준).
    // 달력 2일로 잡으면 월요일마다 금요일 데이터(3일 전)를 stale로 오판해 꺼진다.
    var age=(Date.now()-new Date(iso).getTime())/86400000;  // 일
    if(age>5){ console.warn('[flow-map] etf-flows.json이 5일 넘게 안 갱신됨 — 블록 숨김'); return false; }
    return true;
  }

  fetch('/data/etf-flows.json',{cache:'no-store'})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(data){
      if(!data || !isFresh(data.generated_at)){ block.style.display='none'; return; }
      render(data);
    })
    .catch(function(){ block.style.display='none'; });
})();
```

- [ ] **Step 2: JS 문법 검증**

Run: `node --check web/assets/stocks-home.js && echo OK`
Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add web/assets/stocks-home.js
git commit -m "feat(stocks): 자금 지도 렌더러 — 트리맵·클릭확장·신선도가드(2일)"
```

---

## Task 7: CSS

**Files:**
- Modify: `web/assets/stocks-home.css` (`.block__t.etf` 규칙 근처, 236행 부근 뒤)

- [ ] **Step 1: 스타일 추가** — `web/assets/stocks-home.css` 파일 끝에 삽입

```css
/* ── 🧭 이번 주 자금 지도 (ETF 자금흐름 히트맵) ── */
#flow-block .block__t::before{background:#0F172A;}
.flow-body{padding:14px 16px 4px;display:flex;flex-direction:column;gap:5px;}
.flow-row{display:flex;gap:5px;}
.flow-tile{border-radius:8px;padding:9px 11px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;min-width:0;cursor:pointer;}
.flow-tile .ft-nm{font-size:12px;font-weight:700;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.flow-tile .ft-amt{font-size:12.5px;font-weight:800;font-variant-numeric:tabular-nums;margin-top:4px;}
.ft-expand{background:var(--soft,#F7F9FC);border-radius:8px;padding:6px 12px;margin:5px 0 0;}
.ft-ex-row{display:flex;justify-content:space-between;gap:10px;font-size:12px;padding:4px 0;border-bottom:1px solid var(--hair,#EEF2F7);}
.ft-ex-row:last-child{border-bottom:none;}
.ft-in{color:#E03131;font-weight:700;font-variant-numeric:tabular-nums;}
.ft-out{color:#2775ED;font-weight:700;font-variant-numeric:tabular-nums;}
.flow-quiet{font-size:11.5px;color:#B0B6BE;margin:9px 16px 0;}
.flow-leg{font-size:11px;color:#94A3B8;padding:11px 16px 14px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;}
.flow-scale{display:inline-flex;vertical-align:middle;}
.flow-scale i{width:15px;height:11px;display:inline-block;}
@media(max-width:640px){
  .flow-tile .ft-nm{font-size:11px;}
  .flow-tile .ft-amt{font-size:11px;}
}
```

- [ ] **Step 2: 커밋**

```bash
git add web/assets/stocks-home.css
git commit -m "style(stocks): 자금 지도 히트맵 타일·확장·범례 스타일"
```

---

## Task 8: 통합 스모크 — 합성 히스토리로 렌더 확인

워밍업 특성상 실행 1회로는 flow가 안 나온다(기준 스냅샷 없음). 어제 날짜 합성 히스토리를 심어 오늘 실행하면 실제 flow가 나오는지, 그리고 홈이 렌더되는지 확인한다.

**Files:** (수정 없음 — 검증만)

- [ ] **Step 1: 워밍업 첫 실행 — 블록 숨김 상태 확인**

```bash
rm -f data/etf_flow_history.json
python3 scripts/build_etf_flows.py
python3 -c "import json; d=json.load(open('web/data/etf-flows.json')); print('window', d['window_days'], 'themes', len(d['themes']))"
```
Expected: `window 0 themes 0` (워밍업 — themes 비어있음). `data/etf_flow_history.json`에 오늘 날짜 스냅샷 1개 생성됨.

- [ ] **Step 2: 어제 스냅샷을 합성해 2일차 상태 재현**

```bash
python3 -c "
import json
from datetime import datetime, timedelta, timezone
KST=timezone(timedelta(hours=9))
h=json.load(open('data/etf_flow_history.json'))
today=max(h.keys())
y=(datetime.strptime(today,'%Y-%m-%d')-timedelta(days=1)).strftime('%Y-%m-%d')
# 어제 좌수를 오늘 대비 소폭 다르게(±1%) 흔들어 flow가 생기게
snap={c:{'shares':v['shares']*0.99,'nav':v['nav'],'name':v['name']} for c,v in h[today].items()}
h[y]=snap
json.dump(h, open('data/etf_flow_history.json','w'), ensure_ascii=False)
print('injected baseline', y)
"
python3 scripts/build_etf_flows.py
python3 -c "import json; d=json.load(open('web/data/etf-flows.json')); print('window', d['window_days'], 'themes', len(d['themes'])); [print(t['theme'], t['flow_eok'], 'ETF', t['etf_count']) for t in d['themes'][:8]]"
```
Expected: `window 1`, themes 여러 개, 각 테마에 실제 flow_eok 값. (합성 좌수라 숫자 자체는 무의미 — 파이프라인·집계·출력이 도는지만 확인.)

- [ ] **Step 2b: 단위 테스트 전체 통과 재확인**

Run: `cd scripts && python3 test_build_etf_flows.py`
Expected: `6 passed`

- [ ] **Step 3: 홈 렌더 확인 (브라우저)**

로컬 정적 서버로 홈을 열어 블록이 뜨는지·클릭 확장이 되는지 확인한다.
- `preview_start`로 `daily30-web`(web 디렉터리, 포트 8788) 기동 → `http://localhost:8788/stocks/`
- `#flow-block`이 `display:none`이 아니고, `.flow-tile`이 렌더되고, 타일 클릭 시 `.ft-expand`가 삽입되는지 `read_page`/`javascript_tool`로 확인.
- 스크린샷으로 트리맵 시각(크기·색) 확인.

Expected: 자금 지도 블록이 섹터 브라우저 아래 표시, 타일 크기·색이 flow에 비례, 클릭 시 상위 ETF 확장.

- [ ] **Step 4: 합성 히스토리 정리**(커밋하지 않음 — 합성 flow가 실데이터로 새어나가지 않게)

```bash
rm -f data/etf_flow_history.json web/data/etf-flows.json
git status --short data/ web/data/
```
Expected: 두 파일이 추적되지 않은 상태(운영 워크플로우가 실데이터로 처음 생성할 때 커밋됨). 스모크 산출물은 커밋 금지.

- [ ] **Step 5: 최종 커밋 없음** — 이 태스크는 검증 전용. 코드 변경 없음.

---

## 배포 메모 (구현 후)

- `etf-flows.yml`이 **첫 실행에서 스냅샷 1개만** 만들어 `etf-flows.json`은 `themes:[]`로 나가고 블록은 숨겨진다(정상 — 워밍업). **이튿날 실행부터 실데이터로 라이브**된다.
- 프로덕션 반영은 사용자 지시가 있을 때만 푸시/배포한다(라이브 서비스 경계).
- cron-job.org가 아니라 GHA native cron이라, 첫 배포 후 `workflow_dispatch`로 1회 수동 실행해 스냅샷을 시작해두면 워밍업이 하루 앞당겨진다.
