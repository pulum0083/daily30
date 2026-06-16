# 배당 인컴 설계기 실 페이지 이식 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docs/superpowers/specs/mockups/income-designer.html` 목업을 `web/stocks/income-designer/index.html`로 이식해 실 서비스에 배포한다. 하드코딩 샘플 데이터를 `data/income_etfs.json` 실측 바인딩으로 교체하고, 주1회 갱신 cron job을 추가한다.

**Architecture:** 정적 HTML + 인라인 JS. 페이지 로드 시 `fetch('/data/income_etfs.json')`으로 KR ETF 유니버스를 로드하고, US ETF는 페이지 내 상수로 유지. 댓글은 인메모리 mock(Supabase 연동은 후속). Vercel filesystem routing으로 `/stocks/income-designer/` → `web/stocks/income-designer/index.html`.

**Tech Stack:** 바닐라 HTML/CSS/JS, Python(build_income_etfs.py), GitHub Actions, Vercel

---

## 파일 구조

| 파일 | 변경 |
|---|---|
| `web/stocks/income-designer/index.html` | **신규** — 목업 이식 + 실데이터 바인딩 |
| `vercel.json` | 수정 — `/stocks/income-designer/` 라우트 추가 |
| `.github/workflows/income_etfs.yml` | **신규** — 주1회 cron job |
| `scripts/templates/base.html` | 수정 — GNB "종목" 링크 추가 |

---

## Task 1: `web/stocks/income-designer/index.html` 생성

**Files:**
- Create: `web/stocks/income-designer/index.html`

### Step 1-1: 디렉토리 생성 확인
- [ ] `mkdir -p web/stocks/income-designer` 실행

### Step 1-2: 목업 복사

- [ ] `cp docs/superpowers/specs/mockups/income-designer.html web/stocks/income-designer/index.html` 실행

### Step 1-3: `<head>` canonical URL 및 OG 태그 수정

파일 상단 `<title>` 주변 메타 태그를 실 URL로 교체한다.

- [ ] 아래 내용으로 교체한다.

**찾을 내용 (title + og:url 포함 meta 블록):**
```html
<title>배당 인컴 설계기 — Double-Shot</title>
```

**교체 후:**
```html
<title>배당 인컴 설계기 — 월배당 ETF 건전성·인컴 계산기 | Double-Shot</title>
<link rel="canonical" href="https://doubleshot.space/stocks/income-designer/">
```

### Step 1-4: GNB 프로토타입 링크 수정

- [ ] GNB 657번 줄 근처의 `gnb__logo` onclick을 수정한다.

**찾을 내용:**
```html
<span class="gnb__logo" onclick="location.href='flow-clickable.html'">Double<b>-Shot</b></span><a href="/briefings/">브리핑</a><a class="on" href="/stocks/" onclick="event.preventDefault();location.href='flow-clickable.html'">종목</a>
```

**교체 후:**
```html
<a class="gnb__logo" href="/">Double<b>-Shot</b></a><a href="/briefings/">브리핑</a><a class="on" href="/stocks/income-designer/">종목</a>
```

### Step 1-5: `go()` / `goBack()` 함수 수정

- [ ] 프로토타입 라우터 스텁을 실 URL로 교체한다.

**찾을 내용:**
```javascript
// standalone: 라우터 스텁 (flow-clickable에서 독립 실행)
function go(id){ location.href='flow-clickable.html'; }
function goBack(){ if(history.length>1) history.back(); else location.href='flow-clickable.html'; }
```

**교체 후:**
```javascript
function go(id){ /* 종목 상세 페이지 미구현 — 추후 연결 */ }
function goBack(){ if(history.length>1) history.back(); else location.href='/'; }
```

### Step 1-6: INCOME_UNIVERSE를 fetch 기반으로 교체

목업의 `const INCOME_UNIVERSE=[...]` 블록 전체(KR 20종 + US 5종)를 다음으로 교체한다.

- [ ] 아래 코드로 교체한다.

**찾을 내용** (855번 줄 근처, 주석 포함 전체 블록):
```javascript
// 국내 20종 = data/income_etfs.json 실측(2026-06-13, build_income_etfs.py, 순자산 7천억+).
// 미국 5종 = yfinance 실측(2026-06-16, 가격 원화 환산 @1,513.3원, TTM 분배율·1년 총수익).
// 전 종목 월배당(분배 12회/연). lc=true는 상장 1년 미만이라 총수익(r) 미집계 — 건전성 판정 불가.
const INCOME_UNIVERSE=[
```

> 이 줄부터 `const UNIV={};INCOME_UNIVERSE.forEach(d=>UNIV[d.code]=d);` 직전까지가 교체 대상이다. 편집기에서 블록 전체를 선택해 아래로 교체한다.

**교체 후:**
```javascript
// 미국 5종 — yfinance 실측 하드코딩 (build_income_etfs.py 범위 밖)
const US_UNIVERSE=[
  {code:'JEPI',name:'JPMorgan 에쿼티프리미엄 (JEPI)',aum:44.6,price:85400,y:8.12,r:9.11,mk:'US',lc:false,aumLabel:'$44.6B'},
  {code:'JEPQ',name:'JPMorgan 나스닥 에쿼티프리미엄 (JEPQ)',aum:39.6,price:92390,y:10.02,r:29.12,mk:'US',lc:false,aumLabel:'$39.6B'},
  {code:'QYLD',name:'Global X 나스닥100 커버드콜 (QYLD)',aum:8.4,price:27560,y:11.42,r:23.81,mk:'US',lc:false,aumLabel:'$8.4B'},
  {code:'XYLD',name:'Global X S&P500 커버드콜 (XYLD)',aum:3.2,price:61930,y:10.47,r:17.71,mk:'US',lc:false,aumLabel:'$3.2B'},
  {code:'DIVO',name:'Amplify CWP 강화배당 (DIVO)',aum:7.1,price:70530,y:6.34,r:20.31,mk:'US',lc:false,aumLabel:'$7.1B'},
];

// income_etfs.json 필드 → INCOME_UNIVERSE 형식 변환
function normKrEtf(e) {
  return {
    code: e.code,
    name: e.name,
    aum: e.aum_jo,
    price: e.price,
    y: e.yield_ttm,
    r: e.return_1y,
    mk: 'KR',
    lc: e.low_confidence,
  };
}

let INCOME_UNIVERSE = [...US_UNIVERSE]; // fetch 완료 전 fallback
```

### Step 1-7: 초기화 지점에 fetch 로직 추가

`simRowsRender();simOut();` 줄을 찾아 그 앞에 fetch 초기화를 삽입한다.

- [ ] 아래 내용을 삽입한다.

**찾을 내용:**
```javascript
simRowsRender();simOut();
```

**교체 후:**
```javascript
fetch('/data/income_etfs.json')
  .then(r => r.json())
  .then(data => {
    const krEtfs = (data.etfs || []).map(normKrEtf);
    INCOME_UNIVERSE = [...krEtfs, ...US_UNIVERSE];
    INCOME_UNIVERSE.forEach(d => UNIV[d.code] = d);
    incomeRender();
    incomeAllPageRender();
  })
  .catch(() => {
    // 로컬 개발 환경 등 fetch 실패 시 US_UNIVERSE만으로 초기화
    INCOME_UNIVERSE = [...US_UNIVERSE];
    INCOME_UNIVERSE.forEach(d => UNIV[d.code] = d);
  });
simRowsRender();simOut();
```

### Step 1-8: UNIV 초기화 순서 수정

fetch 기반으로 바꿨으므로, 기존 `const UNIV={};INCOME_UNIVERSE.forEach(d=>UNIV[d.code]=d);` 줄을 찾아 `let`으로 선언만 유지한다.

- [ ] 찾아서 교체한다.

**찾을 내용:**
```javascript
const UNIV={};INCOME_UNIVERSE.forEach(d=>UNIV[d.code]=d);
```

**교체 후:**
```javascript
const UNIV={};US_UNIVERSE.forEach(d=>UNIV[d.code]=d); // 초기 상태, fetch 후 갱신
```

### Step 1-9: "매주 월요일 갱신" 안내 추가

랭킹 섹션 헤더 `.psub` 텍스트를 찾아 갱신 안내를 추가한다.

- [ ] 찾아서 교체한다.

**찾을 내용:**
```html
<div class="psub">순자산 7천억 이상 월배당 ETF (국내·미국). 종목 클릭 시 시뮬레이터에 추가 후 이전 화면으로 돌아가요.</div>
```

**교체 후:**
```html
<div class="psub">순자산 7천억 이상 월배당 ETF (국내·미국). 종목 클릭 시 시뮬레이터에 추가돼요. <span style="color:var(--muted);">데이터 기준: 매주 월요일 갱신</span></div>
```

### Step 1-10: 로컬에서 동작 확인

- [ ] `python3 -m http.server 8790 --directory web` 실행 (별도 포트)
- [ ] 브라우저에서 `http://localhost:8790/stocks/income-designer/` 열기
- [ ] 콘솔 에러 없음 확인
- [ ] 랭킹 카드 20종 표시 확인 (fetch 성공 시)
- [ ] 시뮬레이터 KPI 숫자 계산 확인

### Step 1-11: 커밋

- [ ] 커밋한다.

```bash
git add web/stocks/income-designer/index.html
git commit -m "feat: 배당 인컴 설계기 실 페이지 이식 — /stocks/income-designer/"
```

---

## Task 2: `vercel.json` 라우팅 추가

**Files:**
- Modify: `vercel.json`

Vercel은 `handle: filesystem`이 있어 `web/stocks/income-designer/index.html` 파일이 있으면 `/stocks/income-designer/index.html`은 자동 서빙된다. 그러나 후행 슬래시 없는 `/stocks/income-designer` 요청을 처리하려면 명시적 라우트가 필요하다.

- [ ] `vercel.json`의 `routes` 배열 맨 앞에 아래 라우트를 추가한다.

**찾을 내용:**
```json
  "routes": [
    { "src": "^/$",
```

**교체 후:**
```json
  "routes": [
    { "src": "^/stocks/income-designer/?$", "dest": "/stocks/income-designer/index.html" },
    { "src": "^/$",
```

- [ ] 커밋한다.

```bash
git add vercel.json
git commit -m "feat: vercel.json에 /stocks/income-designer/ 라우트 추가"
```

---

## Task 3: 주1회 GHA 데이터 갱신 cron job

**Files:**
- Create: `.github/workflows/income_etfs.yml`

`daily_report.yml`은 `workflow_dispatch` 전용이라 별도 파일로 분리한다.

- [ ] `.github/workflows/income_etfs.yml` 파일을 아래 내용으로 생성한다.

```yaml
# 배당 인컴 ETF 유니버스를 주1회 갱신하는 워크플로우
name: Income ETFs Update

on:
  schedule:
    - cron: '0 21 * * 0'   # 일요일 21:00 UTC = 월요일 06:00 KST
  workflow_dispatch:         # 수동 실행 허용

permissions:
  contents: write

jobs:
  update-income-etfs:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests

      - name: Build income_etfs.json
        run: python3 scripts/build_income_etfs.py

      - name: Commit and push
        run: |
          git config user.name "DailyB Bot"
          git config user.email "bot@doubleshot.space"
          git add data/income_etfs.json
          git diff --staged --quiet || git commit -m "data: income_etfs.json 주간 갱신 $(date +'%Y-%m-%d')"
          git push
```

- [ ] 로컬에서 `python3 scripts/build_income_etfs.py` 실행해 에러 없음 확인

```bash
python3 scripts/build_income_etfs.py
```

기대 출력:
```
✅ data/income_etfs.json 저장 완료 (N종)
```

- [ ] 커밋한다.

```bash
git add .github/workflows/income_etfs.yml
git commit -m "feat: 배당 인컴 ETF 주간 갱신 GHA 워크플로우 추가 (매주 월요일)"
```

---

## Task 4: GNB "종목" 진입점 연결

**Files:**
- Modify: `scripts/templates/base.html`

브리핑 페이지들의 GNB에 "종목" 링크를 추가해 인컴 설계기로 연결한다.

- [ ] `scripts/templates/base.html` 25~32줄의 `gnb__left` div 안에 종목 링크를 추가한다.

`base.html`의 GNB는 로고(`gnb__logo`)만 있고 nav 링크가 없다. 로고 다음에 nav 영역을 추가한다.

**찾을 내용** (`scripts/templates/base.html`, 27~32번 줄):
```html
    <div class="gnb__left">
      <a class="gnb__logo" href="/briefings">
        <div class="gnb__logo-mark">
```

**교체 후:**
```html
    <div class="gnb__left">
      <a class="gnb__logo" href="/briefings">
        <div class="gnb__logo-mark">
```

> base.html GNB는 브리핑 전용 레이아웃(날짜·테마 토글·알림)으로 nav 링크 추가가 디자인과 맞지 않는다. **이 Task는 실 서비스 GNB 재설계 시 함께 처리한다 — 현재 범위에서 제외한다.**

대신, income-designer 페이지 자체의 GNB(Task 1-4에서 이미 수정)와 `web/landing.html`에 직접 진입 링크를 추가한다.

- [ ] `web/landing.html` GNB에서 "종목" 관련 링크를 찾아 `/stocks/income-designer/`로 연결한다.

```bash
grep -n "gnb\|종목\|stocks" web/landing.html | grep -i "gnb\|nav\|menu" | head -10
```

실제 GNB 구조 확인 후, 브리핑 링크 옆에 추가하거나 기존 "종목" 링크 href를 수정한다.

- [ ] 커밋한다.

```bash
git add scripts/templates/base.html
git commit -m "feat: GNB에 종목 메뉴 추가 — /stocks/income-designer/ 연결"
```

---

## Task 5: 최종 검증

- [ ] 프리뷰 서버 실행 (`python3 -m http.server 8788 --directory web`)
- [ ] `http://localhost:8788/stocks/income-designer/` 열기
- [ ] 아래 항목 체크
  - [ ] 페이지 로드 후 랭킹 카드 렌더 (KR ETF 20종 + US 5종)
  - [ ] 랭킹 헤더에 "데이터 기준: 매주 월요일 갱신" 표시
  - [ ] 브레드크럼: 홈 > 종목 > 배당 인컴 설계기 (링크 없음, 텍스트만)
  - [ ] GNB 로고 클릭 → `/` 이동
  - [ ] GNB "종목" 클릭 → 현재 페이지(self)
  - [ ] 시뮬레이터 기본 3종목 렌더 + KPI 계산
  - [ ] ETF 추가 (콤보박스 선택 → + 추가)
  - [ ] 사이드바 행 클릭 → 시뮬레이터 담기
  - [ ] 의견 남기기 버튼 → 모달 열림
  - [ ] 콘솔 에러 0개
- [ ] 문제 없으면 최종 커밋 없음 (이미 Task별 커밋 완료)
