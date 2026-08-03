# 종목 시그널 서브 네비게이션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/stocks/`에 시그널 서브탭 바(전체·특이신호·섹터·ETF)를 신설해, 지금 인페이지 "더보기 →" 링크로만 도달 가능한 화면들에 상시 이동 경로를 만든다.

**Architecture:** 탭 정의·현재 탭 판정·렌더를 공용 스크립트 `web/assets/ds-subnav.js` 한 곳에 두고, 각 페이지에는 빈 껍데기 `<nav id="ds-subnav">`만 둔다. `/stocks/`는 손으로 쓴 정적 HTML이고 `/themes/`·`/calendar/`는 `generate_html.py` 산출물이라, 마크업을 양쪽에 복사하면 §30 이중 구현 사고가 재현되기 때문이다. 탭 바가 화면 전환과 무관하게 남아 있으려면 히어로·지수 카드가 `#home` **화면 밖**(페이지 레벨)에 있어야 하므로, 그 DOM 이동이 선행 작업이다.

**Tech Stack:** 빌드 없는 정적 HTML + 순수 JS(IIFE, `defer`) + 순수 CSS. 테스트는 `node --test`(node:vm 샌드박스에서 실제 프로덕션 파일 로드).

**참고 스펙:** [`docs/superpowers/specs/2026-08-02-stocks-subnav-ia-design.md`](../specs/2026-08-02-stocks-subnav-ia-design.md)

---

## 이번 작업의 범위

**점등하는 탭은 4개(전체·특이신호·섹터·ETF)뿐이다.** 테마·일정은 정의에 주석으로 남기고, 각 기능이 완성될 때 그 작업에서 주석을 푼다. 빈 탭을 먼저 만들지 않는다.

**홈은 재설계하지 않는다.** 기존 블록의 순서·내용을 건드리지 않고, 아래 4가지만 더한다(2026-08-03 목업 `docs/prototypes/2026-08-03-stocks-subnav-fullsize.html`에서 확정).

1. 서브탭 바 — 지수·수급 카드 바로 아래 (Task 1~4)
2. ETF 요약 블록 — **홈에 대응 블록이 없는 유일한 탭**이라 신설 (Task 5)
3. 섹터별 대표 종목 블록 끝에 `전체 보기 →` 링크 (Task 6)
4. 패시브 민감주·거래량 순위 진입 링크 복구 (Task 6)

**하지 않는 것** — SPA 해시 화면을 실 페이지로 분해하는 리팩터링, 홈 블록 순서·내용 변경, 종목 상세 페이지 탭 노출, 브리핑 쪽 서브탭, `/themes/`·`/calendar/` 페이지 자체, 탭 바 스티키 고정.

**의도적으로 뒤로 미룬 것 — 섹터 선택 칩 행.** 목업에는 서브탭 아래에 8개 섹터 칩을 그렸지만 이번 범위에 넣지 않는다. 라이브 `#sector`는 반도체로 하드코딩돼 있고(`stocks-home.js`의 `SECTOR_RANK`가 종목명·등락률·점수까지 전부 리터럴인 28행 배열), `go(id)`는 화면 id만 받고 섹터 인자가 없다. 지금 칩을 붙이면 어느 섹터를 눌러도 같은 반도체 화면이 뜬다 — **동작하지 않는 내비게이션을 먼저 만드는 셈**이라 §0(없으면 비운다) 취지에 어긋난다. 섹터별 실데이터가 붙은 뒤 별도 작업으로 진행한다.

## 이번 작업에서 고치지 않는 라이브 버그 (기록만 — 사용자 지시로 서브탭 이후)

실측으로 확인했고, 섹터 탭을 실데이터로 채우려면 선행돼야 하는 것들이다.

| # | 문제 | 위치 |
| --- | --- | --- |
| 1 | 섹터 전환 UI 부재 — 반도체 고정, 8섹터 중 4개는 노출조차 안 됨 | `#sector` |
| 2 | 종목 랭킹 15행 `onclick`이 전부 `goStock('000660')` — 어느 행을 눌러도 SK하이닉스로 이동 | `stocks-home.js:1215` `secRow()` |
| 3 | 28종목 랭킹·패시브 쏠림 수치("약 2.8조"·"15.0일")가 하드코딩 리터럴 | `stocks-home.js` `SECTOR_RANK`, `index.html` |
| 4 | `web/data/stocks-snapshot.json`과 `/api/vol-top`이 같은 종목에 다른 값 (삼성전자 262,500·+26.81% vs 239,500·−8.76%) | 데이터 소스 |

3번은 §20(목표주가 mock이 3주간 라이브 노출)과 같은 형태, 4번은 한 화면에 두 소스를 섞으면 서로 모순되는 숫자가 나오는 상태다.

## 사전 조사 결과 (이미 확인됨 — 다시 조사하지 말 것)

- `.wrap`(`stocks-home.css:28`) 안에 `.screen` 7개 + `#home`이 형제로 놓여 있다. `.screen{display:none}` / `.screen.on{display:block}`(`:29`).
- **히어로·LIVE 배지줄·지수 카드·수급 패널이 전부 `#home` 안에 있다**(`web/stocks/index.html:35-93`). `go('sector')`를 부르면 `#home`에서 `.on`이 빠지면서 이것들도 같이 사라진다 — 그래서 Task 1의 DOM 이동이 필요하다.
- `#home` 외 화면들(`#signals-all`·`#sector`·`#etf-rank`)은 `.crumb`(← 시그널 뒤로가기) + `.phead`로 시작한다. 이 브레드크럼은 **그대로 둔다**(기존 진입 경로를 깨지 않는다).
- 이동 대상 요소를 참조하는 JS는 전부 `getElementById`(`stocks-home.js:2708`·`2824`·`2841`)라 **부모가 바뀌어도 안전하다.** `#home .hero` 같은 하위 선택자는 없다.
- CSS도 `.hero`·`.idx-card`·`.sup-panel` 모두 독립 클래스 규칙이라 부모 의존이 없다(`stocks-home.css:35`·`47`·`84`).
- `:root` 변수(`stocks-home.css:1-3`): `--canvas --soft --inset --hair --ink --muted --primary --up --dn` 전부 존재.
- 실제 화면 id: `etf-detail sector income passive ranking signals-all etf-rank` + `home`.
- CI가 `node --test web/assets/*.test.mjs`를 이미 돌린다(`.github/workflows/ci.yml:61`) — 새 `*.test.mjs`는 자동으로 포함된다.
- `go()`는 `stocks-home.js:991`.

## 파일 구조

| 파일 | 책임 |
| --- | --- |
| `web/assets/ds-subnav.js` (신규) | 탭 정의 1벌, `resolveActiveTab` 순수함수, 렌더, 클릭 가로채기, `dsSubnavSync` 노출 |
| `web/assets/ds-subnav.css` (신규) | 언더라인 탭 스타일(ncai Tabs 규격) |
| `web/assets/ds-subnav.test.mjs` (신규) | 탭 판정·정의 정합성 테스트 |
| `web/stocks/index.html` (수정) | 히어로·지수 카드를 `#home` 밖으로 이동, `<nav id="ds-subnav">` 껍데기 추가, 두 파일 로드, ETF 블록 마크업, 링크 3종 |
| `web/assets/stocks-home.js` (수정) | `go()` 끝에 동기화 훅 한 줄, `renderEtfSignal()` 신규 + `applySignals()`에서 호출 |
| `web/assets/stocks-home.css` (수정) | ETF 요약 블록 스타일 |

### ETF 요약 블록의 데이터 (이미 확인됨)

`loadSignals()`가 `/api/signals`를 이미 fetch해 `applySignals(d)`로 넘긴다(`stocks-home.js:2261`). 그 응답의 `d.etf`가 아래 객체인데 **`applySignals`가 지금 이 필드를 쓰지 않고 버린다** — 새 fetch가 필요 없다는 뜻이다.

```
d.etf.lead      = {title, body}                      // body에 <b> 태그 포함(우리 API가 생성)
d.etf.betting   = {downAmt, upAmt, downRatio, upRatio, invVolMultiple, levPct}   // 금액 단위 백만원
d.etf.sector    = [{code, label, pct, amount}, ...]  // 9종
d.etf.safeHaven = {rows:[{code,label,pct}], market}
```

⚠️ `renderEtf()`라는 함수가 이미 있는데(`stocks-home.js:2100`) 그건 `/api/vol-top`의 **배열**을 받는 다른 함수다. 이름을 재사용하지 말 것.

---

## Task 1: 히어로·지수 카드를 `#home` 밖(페이지 레벨)으로 이동

탭 바가 어느 화면에서든 남아 있으려면 그 위의 머리말도 화면 밖에 있어야 한다. 이 태스크는 **DOM 이동만** 한다 — 탭 바는 아직 넣지 않는다. 이동 자체가 화면을 깨지 않는지 먼저 확인하기 위해서다.

**Files:**
- Modify: `web/stocks/index.html:33-93`

- [ ] **Step 1: 이동 대상 경계 확인**

Run: `awk 'NR>=33 && NR<=95 { line=$0; sub(/^[ \t]*/,"",line); indent=length($0)-length(line); if (indent<=4 && length(line)>0) printf "%4d [%2d] %.80s\n", NR, indent, line }' web/stocks/index.html`

Expected: 아래 구조가 나온다. 줄 번호가 다르면 **이 태스크를 멈추고 보고할 것**(다른 작업이 파일을 바꾼 것이다).

```
  33 [ 2] <!-- ===== HOME ===== -->
  34 [ 2] <div class="screen on" id="home">
  35 [ 4] <div class="hero">
  44 [ 4] </div>
  45 [ 4] <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
  48 [ 4] </div>
  49 [ 4] <!-- 지수 + 수급 한 줄 카드(2026-07-26) — ...
  51 [ 4] <div class="idx-card" id="idx-card">
  73 [ 4] </div>
  74 [ 4] <!-- 최근 10거래일 수급 추이 — ...
  75 [ 4] <div class="sup-panel" id="sup-panel" hidden>
  93 [ 4] </div>
  94 [ 4] <!-- 더블샷 브리핑 커넥터 — ...
  95 [ 4] <a class="brief-card" id="brief-strip" ...
```

- [ ] **Step 2: 블록 이동**

`web/stocks/index.html`에서 **35~93행**(`<div class="hero">`부터 `.sup-panel`의 닫는 `</div>`까지, 사이의 주석 포함)을 잘라내어, **33행 `<!-- ===== HOME ===== -->` 바로 앞**에 붙인다. 들여쓰기를 4칸 → 2칸으로 맞춘다(`.wrap` 직계가 되므로).

결과 구조는 이렇게 된다:

```html
<div class="wrap">

  <!-- 페이지 머리말 — 화면(.screen) 밖에 둔다. 탭을 눌러 화면이 바뀌어도 종목 시그널의
       제목·검색·시장 맥락은 계속 남아 있어야 하기 때문이다(서브탭 IA 스펙). -->
  <div class="hero">
    ... (기존 내용 그대로)
  </div>
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
    <span class="upd-badge" id="kospi-live-badge">...</span>
    <span style="font-size:11px;color:var(--muted);">09:00 – 15:30 장중</span>
  </div>
  <!-- 지수 + 수급 한 줄 카드(2026-07-26) — ... (기존 주석 그대로) -->
  <div class="idx-card" id="idx-card">
    ... (기존 내용 그대로)
  </div>
  <!-- 최근 10거래일 수급 추이 — ... (기존 주석 그대로) -->
  <div class="sup-panel" id="sup-panel" hidden>
    ... (기존 내용 그대로)
  </div>

  <!-- ===== HOME ===== -->
  <div class="screen on" id="home">
    <!-- 더블샷 브리핑 커넥터 — 현재 브리핑 타임의 실제 브리핑으로 JS가 연결 -->
    <a class="brief-card" id="brief-strip" href="/briefings/" data-href="/briefings/">
    ... (이하 기존 내용 그대로)
```

**내용은 한 글자도 바꾸지 않는다.** 이동과 들여쓰기만이다.

- [ ] **Step 3: 구조 검증**

Run: `python3 -c "
import re
h = open('web/stocks/index.html', encoding='utf-8').read()
home = h.index('<div class=\"screen on\" id=\"home\">')
for tag in ['class=\"hero\"', 'id=\"idx-card\"', 'id=\"sup-panel\"', 'id=\"kospi-live-badge\"']:
    pos = h.index(tag)
    print(tag, 'BEFORE #home' if pos < home else '*** STILL INSIDE #home ***')
print('brief-strip after #home:', h.index('id=\"brief-strip\"') > home)
"`

Expected: 네 요소 모두 `BEFORE #home`, 마지막 줄 `True`.

- [ ] **Step 4: 기존 테스트 회귀 확인**

Run: `node --test web/assets/*.test.mjs`
Expected: 이전과 같은 pass 수, fail 0.

- [ ] **Step 5: 브라우저 확인**

```bash
cd web && python3 -m http.server 8899
```

`mcp__Claude_Browser__preview_start`로 `http://localhost:8899/stocks/` 열기. 확인할 것:

1. 홈 화면이 이동 전과 똑같이 보인다(히어로 → 검색창 → LIVE 배지 → 지수·수급 카드 → 브리핑 커넥터 순).
2. 지수 카드의 "코스닥·환율" 칩과 "10일 추이" 토글이 여전히 동작한다(`idx-card`·`sup-panel` JS가 부모 변경에 안 깨졌는지).
3. `read_console_messages`로 에러 0건.
4. 브라우저 콘솔에서 `go('sector')` 실행 → **섹터 화면으로 바뀌면서도 히어로·지수 카드가 그대로 남아 있어야 한다.** 이게 이 태스크의 핵심 검증이다. `go('home')`으로 복귀.

서버는 확인 후 종료한다.

- [ ] **Step 6: 커밋**

```bash
git add web/stocks/index.html
git commit -m "refactor(종목시그널): 히어로·지수 카드를 화면(.screen) 밖으로 이동

서브탭 바를 지수 카드 바로 아래 두려면 그 위의 머리말도 화면 밖에 있어야 한다.
지금은 히어로·지수 카드가 #home 안에 있어 go('sector')를 부르면 함께 사라진다.
내용 변경 없이 위치와 들여쓰기만 바꿨다."
```

---

## Task 2: `ds-subnav.js` — 탭 정의와 `resolveActiveTab` 순수함수

**Files:**
- Create: `web/assets/ds-subnav.js`
- Create: `web/assets/ds-subnav.test.mjs`

- [ ] **Step 1: 실패하는 테스트 작성**

`web/assets/ds-subnav.test.mjs` 신규 생성:

```javascript
// ds-subnav.js 탭 판정·정의 정합성 테스트 — node:vm 샌드박스에서 실제 프로덕션 파일을 로드해 검증
//
// 왜 이런 방식인가
//   ds-subnav.js는 브라우저용 IIFE(<script src defer>)라 import할 수 없다. 순수 함수를
//   테스트 파일에 복제하면 사본이 원본과 어긋나므로(SERVICE_RULES §20류 사고의 전형),
//   실제 파일을 최소 DOM 스텁과 함께 vm에서 실행하고 window.__dsSubnav로 꺼내 검증한다.
//   stocks-home.test.mjs·main.test.mjs와 같은 패턴.
//
// 실행: node --test web/assets/ds-subnav.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const noop = () => {};

/** ds-subnav.js를 vm에서 실행하고 window.__dsSubnav를 돌려준다. */
function load() {
  const win = {
    location: { pathname: '/stocks/', hash: '' },
    addEventListener: noop,
    document: {
      readyState: 'complete',
      getElementById: () => null,        // 껍데기 없는 페이지 = 조용히 아무것도 안 함
      addEventListener: noop,
    },
  };
  win.window = win;
  const ctx = createContext(win);
  runInContext(readFileSync(join(HERE, 'ds-subnav.js'), 'utf8'), ctx);
  return win.__dsSubnav;
}

test('탭 정의는 이번 범위인 4개만 점등한다', () => {
  const { TABS } = load();
  assert.deepEqual(TABS.map((t) => t.id), ['home', 'signals', 'sector', 'etf']);
  assert.deepEqual(TABS.map((t) => t.label), ['전체', '특이신호', '섹터', 'ETF']);
});

test('경로·해시 조합별 활성 탭 판정', () => {
  const { resolveActiveTab } = load();
  assert.equal(resolveActiveTab('/stocks/', ''), 'home');
  assert.equal(resolveActiveTab('/stocks/', '#home'), 'home');
  assert.equal(resolveActiveTab('/stocks/', '#signals-all'), 'signals');
  assert.equal(resolveActiveTab('/stocks/', '#sector'), 'sector');
  assert.equal(resolveActiveTab('/stocks/', '#etf-rank'), 'etf');
});

test('탭이 없는 화면(#passive 등)은 전체로 떨어진다', () => {
  const { resolveActiveTab } = load();
  // 아무 탭도 활성이 아닌 것보다, 시그널 영역 안에 있다는 사실을 유지하는 쪽이 방향 감각에 낫다.
  assert.equal(resolveActiveTab('/stocks/', '#passive'), 'home');
  assert.equal(resolveActiveTab('/stocks/', '#ranking'), 'home');
  assert.equal(resolveActiveTab('/stocks/', '#mom-track'), 'home');
});

test('종목 상세 등 그 외 경로는 아무 탭도 활성이 아니다', () => {
  const { resolveActiveTab } = load();
  assert.equal(resolveActiveTab('/stocks/005930/', ''), null);
  assert.equal(resolveActiveTab('/stocks/us/nvda/', ''), null);
  assert.equal(resolveActiveTab('/briefings/', ''), null);
});

test('아직 점등하지 않은 탭 경로에서도 깨지지 않는다', () => {
  const { resolveActiveTab } = load();
  // 테마·일정은 정의에 주석 처리돼 있다 — 그 경로로 들어와도 null이지 예외가 아니다.
  assert.equal(resolveActiveTab('/themes/', ''), null);
  assert.equal(resolveActiveTab('/calendar/', ''), null);
});

test('로컬 정적 서버의 /stocks/index.html도 홈으로 본다', () => {
  const { resolveActiveTab } = load();
  assert.equal(resolveActiveTab('/stocks/index.html', ''), 'home');
});

test('TABS의 screen 값이 index.html에 실제로 있는 화면 id와 일치한다', () => {
  // 오타로 죽은 탭이 나가는 것을 막는다. screen이 없는 탭(독립 페이지)은 검사 제외.
  const { TABS } = load();
  const html = readFileSync(join(HERE, '..', 'stocks', 'index.html'), 'utf8');
  const ids = new Set(['home']);
  for (const m of html.matchAll(/class="screen[^"]*"\s+id="([a-z-]+)"/g)) ids.add(m[1]);
  for (const t of TABS) {
    if (!t.screen) continue;
    assert.ok(ids.has(t.screen), `TABS의 screen "${t.screen}"이 index.html에 없다`);
  }
});

test('href와 screen이 어긋나지 않는다', () => {
  // 정의를 손으로 고치다 둘이 갈라지는 것을 막는다.
  const { TABS } = load();
  for (const t of TABS) {
    if (!t.screen) continue;
    const hash = t.href.includes('#') ? t.href.split('#')[1] : '';
    if (hash) assert.equal(hash, t.screen, `${t.id}: href 해시와 screen이 다르다`);
    else assert.equal(t.screen, 'home', `${t.id}: 해시 없는 탭은 screen이 home이어야 한다`);
  }
});

test('껍데기(#ds-subnav)가 없는 페이지에서 로드해도 예외가 없다', () => {
  // main.js의 `if (!el) return` 가드 관례. 로드만 되면 통과 — load()가 이미 그 상황이다.
  assert.ok(load().TABS.length > 0);
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/assets/ds-subnav.test.mjs`
Expected: FAIL — `ENOENT: no such file or directory, open '.../ds-subnav.js'`

- [ ] **Step 3: `ds-subnav.js` 작성**

`web/assets/ds-subnav.js` 신규 생성:

```javascript
// 종목 시그널 서브 네비게이션 — 탭 정의·현재 탭 판정·렌더를 한 곳에 두는 공용 스크립트.
//
// 왜 공용 파일인가
//   탭 바는 최종적으로 /stocks/·/themes/·/calendar/ 세 곳에 똑같이 떠야 한다. 그런데
//   /stocks/index.html은 손으로 쓴 정적 HTML이고 신규 두 페이지는 generate_html.py가 만든다.
//   마크업을 양쪽에 복사하면 한쪽만 고쳐지고 다른 쪽이 방치돼도 겉보기엔 둘 다 정상으로
//   보인다(SERVICE_RULES §30 이중 구현). 각 페이지엔 빈 껍데기만 두고 정의는 여기 한 곳에 둔다.
//
// 이 컴포넌트는 없어도 기존 기능이 전부 동작해야 한다 — 홈 블록의 "전체 보기 →" 링크가
// 그대로 살아 있으므로 탭 바는 부가 경로다.
(function () {
  'use strict';

  // 점등하는 탭은 이번 범위인 4개뿐이다. 테마·일정은 각 기능이 완성될 때 그 작업에서
  // 주석을 푼다 — 빈 탭을 먼저 만들지 않는다.
  // screen이 있으면 /stocks/ 내부 화면, 없으면 독립 페이지다. 이 한 필드가 클릭 동작을 가른다.
  var TABS = [
    { id: 'home',    label: '전체',     href: '/stocks/',             screen: 'home' },
    { id: 'signals', label: '특이신호', href: '/stocks/#signals-all', screen: 'signals-all' },
    // { id: 'themes',   label: '테마', href: '/themes/' },    // 테마 타임라인 완성 시 점등
    { id: 'sector',  label: '섹터',     href: '/stocks/#sector',      screen: 'sector' },
    { id: 'etf',     label: 'ETF',      href: '/stocks/#etf-rank',    screen: 'etf-rank' },
    // { id: 'calendar', label: '일정', href: '/calendar/' },  // 실적 캘린더 완성 시 점등
  ];

  // 해시 → 탭 id. 여기 없는 해시(#passive·#ranking 등)는 '전체'로 떨어진다 — 아무 탭도
  // 활성이 아닌 것보다 시그널 영역 안에 있다는 사실을 유지하는 쪽이 방향 감각에 낫다.
  var HASH_TO_TAB = { 'signals-all': 'signals', 'sector': 'sector', 'etf-rank': 'etf' };

  var STOCKS_HOME_RE = /^\/stocks\/?(index\.html)?$/;

  function isStocksHome(pathname) {
    return STOCKS_HOME_RE.test(pathname || '');
  }

  /** 현재 탭 판정. DOM·전역 상태를 안 읽는 순수 함수라 테스트가 쉽다. */
  function resolveActiveTab(pathname, hash) {
    var id = null;
    if (/^\/themes(\/|$)/.test(pathname)) id = 'themes';
    else if (/^\/calendar(\/|$)/.test(pathname)) id = 'calendar';
    else if (isStocksHome(pathname)) id = HASH_TO_TAB[(hash || '').replace(/^#/, '')] || 'home';
    if (!id) return null;
    // 정의에 없는 탭으로 해석되면 null — 아직 점등하지 않은 테마·일정 경로로 들어와도 깨지지 않는다.
    for (var i = 0; i < TABS.length; i++) if (TABS[i].id === id) return id;
    return null;
  }

  window.__dsSubnav = { TABS: TABS, resolveActiveTab: resolveActiveTab };
})();
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test web/assets/ds-subnav.test.mjs`
Expected: PASS (9 tests)

- [ ] **Step 5: 커밋**

```bash
git add web/assets/ds-subnav.js web/assets/ds-subnav.test.mjs
git commit -m "feat(종목시그널): 서브탭 정의와 현재 탭 판정 순수함수 추가"
```

---

## Task 3: 렌더·클릭 동작·CSS

**Files:**
- Modify: `web/assets/ds-subnav.js`
- Create: `web/assets/ds-subnav.css`
- Modify: `web/assets/ds-subnav.test.mjs`

- [ ] **Step 1: 실패하는 테스트 추가**

`web/assets/ds-subnav.test.mjs`의 `load()` 함수를 아래로 **교체**하고(껍데기 DOM 스텁을 받도록 확장), 파일 끝에 테스트를 추가한다:

```javascript
/** ds-subnav.js를 vm에서 실행한다. host를 주면 #ds-subnav 껍데기가 있는 페이지를 흉내낸다. */
function load(opts) {
  opts = opts || {};
  var host = opts.host || null;
  const win = {
    location: { pathname: opts.pathname || '/stocks/', hash: opts.hash || '' },
    addEventListener: opts.onWinEvent || noop,
    document: {
      readyState: 'complete',
      getElementById: (id) => (id === 'ds-subnav' ? host : null),
      addEventListener: noop,
    },
  };
  if (opts.go) win.go = opts.go;
  win.window = win;
  const ctx = createContext(win);
  runInContext(readFileSync(join(HERE, 'ds-subnav.js'), 'utf8'), ctx);
  return { api: win.__dsSubnav, win: win };
}

/** #ds-subnav 껍데기 스텁 — innerHTML만 기록하고 클릭 핸들러를 붙잡아 둔다. */
function mkHost() {
  return {
    innerHTML: '',
    _click: null,
    addEventListener(type, fn) { if (type === 'click') this._click = fn; },
  };
}
```

기존 테스트들은 `load()` 반환값이 바뀌었으므로 `const { TABS } = load();` → `const { TABS } = load().api;`, `const { resolveActiveTab } = load();` → `const { resolveActiveTab } = load().api;`로 고치고, 마지막 테스트의 `load().TABS.length` → `load().api.TABS.length`로 고친다.

파일 끝에 추가:

```javascript
test('렌더 — 활성 탭에만 is-active와 aria-current가 붙는다', () => {
  const host = mkHost();
  load({ host, pathname: '/stocks/', hash: '#sector' });

  assert.ok(host.innerHTML.includes('data-tab="sector"'));
  const sectorTag = host.innerHTML.match(/<a[^>]*data-tab="sector"[^>]*>/)[0];
  const homeTag = host.innerHTML.match(/<a[^>]*data-tab="home"[^>]*>/)[0];
  assert.ok(sectorTag.includes('is-active'), '활성 탭에 is-active가 없다');
  assert.ok(sectorTag.includes('aria-current="page"'));
  assert.ok(!homeTag.includes('is-active'), '비활성 탭에 is-active가 붙었다');
});

test('렌더 — 아무 탭도 활성이 아니어도 탭 바 자체는 그대로 보인다', () => {
  const host = mkHost();
  load({ host, pathname: '/stocks/005930/', hash: '' });

  assert.ok(host.innerHTML.includes('data-tab="home"'), '탭이 렌더되지 않았다');
  assert.ok(!host.innerHTML.includes('is-active'), '활성 탭이 없어야 한다');
});

test('클릭 — /stocks/ 내부 화면은 go()로 전환하고 기본 이동을 막는다', () => {
  // go()는 history.pushState로 해시를 바꾸는데 pushState는 hashchange를 발생시키지 않는다.
  // 링크 기본 동작에 맡기면 화면 전환과 탭 강조가 어긋나므로 클릭을 가로챈다.
  const host = mkHost();
  const calls = [];
  load({ host, pathname: '/stocks/', hash: '', go: (s) => calls.push(s) });

  let prevented = false;
  host._click({
    target: { closest: () => ({ getAttribute: () => 'sector' }) },
    preventDefault: () => { prevented = true; },
  });

  assert.deepEqual(calls, ['sector']);
  assert.equal(prevented, true);
});

test('클릭 — go()가 없는 페이지에서는 가로채지 않는다', () => {
  // /themes/에서 "섹터" 탭을 누르면 /stocks/#sector로 정상 이동한 뒤
  // 그 페이지의 해시 복원 로직이 화면을 띄운다.
  const host = mkHost();
  load({ host, pathname: '/themes/', hash: '' });   // go 미주입

  let prevented = false;
  host._click({
    target: { closest: () => ({ getAttribute: () => 'sector' }) },
    preventDefault: () => { prevented = true; },
  });

  assert.equal(prevented, false, '기본 링크 이동을 막으면 안 된다');
});

test('클릭 — 탭이 아닌 곳을 누르면 아무 일도 없다', () => {
  const host = mkHost();
  const calls = [];
  load({ host, pathname: '/stocks/', hash: '', go: (s) => calls.push(s) });

  host._click({ target: { closest: () => null }, preventDefault: () => { throw new Error('막으면 안 된다'); } });

  assert.deepEqual(calls, []);
});

test('dsSubnavSync는 현재 위치로 강조를 다시 계산한다', () => {
  const host = mkHost();
  const { win } = load({ host, pathname: '/stocks/', hash: '' });
  assert.ok(host.innerHTML.match(/<a[^>]*data-tab="home"[^>]*>/)[0].includes('is-active'));

  win.location.hash = '#etf-rank';       // go()가 해시를 바꾼 뒤의 상태를 흉내낸다
  win.dsSubnavSync();

  assert.ok(host.innerHTML.match(/<a[^>]*data-tab="etf"[^>]*>/)[0].includes('is-active'));
  assert.ok(!host.innerHTML.match(/<a[^>]*data-tab="home"[^>]*>/)[0].includes('is-active'));
});

test('hashchange·popstate에 강조 갱신을 걸어둔다', () => {
  // 주소창 직접 수정·외부 앵커 링크·뒤로가기에서도 탭이 따라와야 한다.
  const seen = [];
  load({ host: mkHost(), onWinEvent: (type) => seen.push(type) });
  assert.ok(seen.includes('hashchange'), 'hashchange 미등록');
  assert.ok(seen.includes('popstate'), 'popstate 미등록');
});

test('CSS — 활성 탭 굵기를 바꾸지 않는다(레이아웃 점프 금지)', () => {
  // ncai Tabs 명시적 금지 사항. 활성 신호는 primary 컬러 하나로 통일한다.
  const css = readFileSync(join(HERE, 'ds-subnav.css'), 'utf8');
  const active = css.match(/\.ds-subnav__tab\.is-active\s*\{([^}]*)\}/);
  assert.ok(active, '.ds-subnav__tab.is-active 규칙이 없다');
  assert.ok(!/font-weight/.test(active[1]), '활성 탭에 font-weight를 주면 안 된다');
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/assets/ds-subnav.test.mjs`
Expected: FAIL — 렌더 관련 테스트에서 `host.innerHTML`이 빈 문자열, `host._click`이 `null`, `ds-subnav.css` 없음(ENOENT)

- [ ] **Step 3: `ds-subnav.js`에 렌더·클릭·이벤트 추가**

`web/assets/ds-subnav.js`의 `window.__dsSubnav = ...` 줄을 **아래 전체로 교체**한다:

```javascript
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function tabById(id) {
    for (var i = 0; i < TABS.length; i++) if (TABS[i].id === id) return TABS[i];
    return null;
  }

  function host() {
    return document.getElementById('ds-subnav');
  }

  /** 현재 위치로 강조를 다시 계산해 반영한다. 껍데기가 없는 페이지에서는 조용히 아무것도 안 한다. */
  function render() {
    var el = host();
    if (!el) return;
    var active = resolveActiveTab(location.pathname, location.hash);
    el.innerHTML = TABS.map(function (t) {
      var on = t.id === active;
      return '<a class="ds-subnav__tab' + (on ? ' is-active' : '') + '"'
        + ' href="' + esc(t.href) + '" data-tab="' + esc(t.id) + '"'
        + (on ? ' aria-current="page"' : '') + '>' + esc(t.label) + '</a>';
    }).join('');
  }

  function onClick(e) {
    var a = e.target && e.target.closest ? e.target.closest('.ds-subnav__tab') : null;
    if (!a) return;
    var tab = tabById(a.getAttribute('data-tab'));
    // 독립 페이지이거나, go()가 없는 페이지이거나, /stocks/가 아니면 기본 링크 이동에 맡긴다.
    if (!tab || !tab.screen) return;
    if (!isStocksHome(location.pathname)) return;
    if (typeof window.go !== 'function') return;
    e.preventDefault();
    window.go(tab.screen);
    render();
  }

  function init() {
    var el = host();
    if (el) el.addEventListener('click', onClick);
    render();
  }

  window.dsSubnavSync = render;
  window.__dsSubnav = { TABS: TABS, resolveActiveTab: resolveActiveTab };

  window.addEventListener('hashchange', render);   // 주소창 직접 수정·외부 앵커 링크
  window.addEventListener('popstate', render);     // 뒤로/앞으로 가기

  // defer 스크립트는 DOMContentLoaded 전에 실행되지만, 다른 로드 경로도 견디게 둔다.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
```

- [ ] **Step 4: `ds-subnav.css` 작성**

`web/assets/ds-subnav.css` 신규 생성:

```css
/* 종목 시그널 서브탭 — ncai-design-system Tabs의 Underline 변형.
   알약 탭 대비 6개가 들어가도 시각적으로 가볍고, 콘텐츠를 가르는 경계로 읽혀 조용하다.

   모든 변수에 폴백을 둔다 — 세 페이지가 서로 다른 스타일시트(stocks-home.css / style.css)를
   쓰고 변수명도 갈려 있어(--hair vs --hairline) 값이 없을 수 있다. §5에서 CSS 변수 하나가
   없어 랜딩이 통째로 빈 화면이 된 사고가 있었다. */
#ds-subnav{display:flex;align-items:stretch;gap:0;border-bottom:1px solid var(--hair,#E5E7EB);margin-bottom:16px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;}
#ds-subnav::-webkit-scrollbar{display:none;}
.ds-subnav__tab{display:inline-flex;align-items:center;flex:0 0 auto;min-height:40px;padding:0 16px;font-size:14px;font-weight:500;line-height:1.2;letter-spacing:-.16px;color:var(--muted,#5B6472);text-decoration:none;border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;}
.ds-subnav__tab:hover{color:var(--ink,#13151A);}
/* 활성 = 텍스트·언더라인 모두 primary. weight는 500 고정 — 굵기 변화는 레이아웃 점프를 만든다(ncai 명시 금지). */
.ds-subnav__tab.is-active{color:var(--primary,#006EFF);border-bottom-color:var(--primary,#006EFF);}
.ds-subnav__tab:focus-visible{outline:1px dotted var(--primary,#006EFF);outline-offset:-3px;}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `node --test web/assets/ds-subnav.test.mjs`
Expected: PASS (17 tests)

- [ ] **Step 6: 커밋**

```bash
git add web/assets/ds-subnav.js web/assets/ds-subnav.css web/assets/ds-subnav.test.mjs
git commit -m "feat(종목시그널): 서브탭 렌더·클릭 가로채기·언더라인 스타일 추가"
```

---

## Task 4: `/stocks/`에 배선

**Files:**
- Modify: `web/stocks/index.html:22-26`(에셋 로드), Task 1에서 옮긴 머리말 블록 끝
- Modify: `web/assets/stocks-home.js:991-997`(`go()`)

- [ ] **Step 1: 에셋 로드 추가**

`web/stocks/index.html:24` 다음 줄에 추가:

```html
<script src="/assets/ds-subnav.js?v=1" defer></script>
```

`web/stocks/index.html:26` 다음 줄에 추가:

```html
<link rel="stylesheet" href="/assets/ds-subnav.css?v=1">
```

- [ ] **Step 2: 껍데기 추가**

Task 1에서 옮긴 `.sup-panel` 닫는 `</div>` **바로 다음**, `<!-- ===== HOME ===== -->` **바로 앞**에 추가:

```html

  <!-- 시그널 서브탭 — 마크업은 비워 두고 ds-subnav.js가 채운다. 탭 정의를 한 곳에만 두기
       위해서다(§30 이중 구현 방지). 이 껍데기가 없으면 스크립트는 조용히 아무것도 안 한다. -->
  <nav id="ds-subnav" aria-label="종목 시그널 메뉴"></nav>
```

- [ ] **Step 3: `go()`에 동기화 훅 추가**

`web/assets/stocks-home.js:991-997`의 `go()` 함수에서 `history.pushState(...)` 줄 **다음**, 닫는 `}` **앞**에 한 줄 추가:

```javascript
function go(id,noHistory){
  const el=document.getElementById(id);if(!el||!el.classList.contains('screen'))return;
  if(!noHistory){const cur=document.querySelector('.screen.on');if(cur&&cur.id!==id)navHistory.push(cur.id);}
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('on'));
  el.classList.add('on');
  window.scrollTo({top:0,behavior:'smooth'});
  history.pushState({screen:id},'','#'+id);
  // pushState는 hashchange를 발생시키지 않으므로 서브탭 강조를 직접 갱신한다.
  // 프로젝트의 옵셔널 호출 관례를 따라 결합을 최소로 둔다 — 없으면 그냥 넘어간다.
  if(typeof window.dsSubnavSync==='function')window.dsSubnavSync();
}
```

- [ ] **Step 4: 테스트 회귀 확인**

Run: `node --test web/assets/*.test.mjs`
Expected: 전체 PASS, fail 0.

- [ ] **Step 5: 브라우저 확인**

```bash
cd web && python3 -m http.server 8899
```

`http://localhost:8899/stocks/`에서 확인:

1. 탭 바가 지수·수급 카드 **바로 아래**, 브리핑 커넥터 **위**에 있다. 탭은 `전체 특이신호 섹터 ETF` 4개.
2. 최초 진입 시 "전체"가 primary 컬러 + 언더라인. 나머지는 무채색.
3. "섹터" 클릭 → 섹터 화면으로 전환되고, **탭 바와 지수 카드가 그대로 남아 있으며**, "섹터"가 활성으로 바뀐다. 주소창이 `#sector`가 된다.
4. 브라우저 뒤로가기 → 홈으로 돌아오고 "전체"가 다시 활성.
5. 주소창에 `#etf-rank`를 직접 입력 → ETF 탭이 활성으로 바뀐다(hashchange 경로).
6. 홈에서 "패시브 민감주"의 "전체 보기 →" 링크 클릭 → `#passive` 화면으로 가되 **"전체" 탭이 활성 유지**.
7. `resize_window`로 375px — 탭 4개가 넘치지 않고, 가로 스크롤이 페이지 전체에 생기지 않는다.
8. `read_console_messages` 에러 0건.
9. 종목 상세(`/stocks/005930/`)로 이동 → 탭 바가 없어야 한다(껍데기를 안 넣었으므로).

`computer {action:"screenshot"}`으로 데스크톱·모바일 각 1장 남긴다. 서버는 확인 후 종료한다.

- [ ] **Step 6: 커밋**

```bash
git add web/stocks/index.html web/assets/stocks-home.js
git commit -m "feat(종목시그널): /stocks/에 서브탭 바 배선"
```

---

## Task 5: 홈에 ETF 요약 블록 신설

ETF는 서브탭 4개 중 **홈에 대응 블록이 없는 유일한 탭**이다(홈 본문에 "ETF"라는 단어가 한 번도 안 나온다 — 실측 확인). 스펙의 "탭이 있는 영역은 홈에도 요약 블록이 있어야 한다" 규칙을 지키려면 이 하나를 새로 만들어야 한다.

**Files:**
- Modify: `web/stocks/index.html` (`#flow-block`이 있는 `.home-main` 안, 자금 지도 다음)
- Modify: `web/assets/stocks-home.js` (`applySignals` 부근)
- Modify: `web/assets/stocks-home.css`
- Test: `web/assets/etf-signal.test.mjs` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

`web/assets/etf-signal.test.mjs` 신규 생성:

```javascript
// stocks-home.js의 ETF 요약 블록 포맷터 회귀 테스트 — node:vm에서 실제 프로덕션 파일 로드
//
// 순수 함수를 테스트 파일에 복제하면 사본이 원본과 어긋나므로(SERVICE_RULES §20류),
// 실제 파일을 최소 DOM 스텁과 함께 실행하고 window.__etfSignal로 꺼내 검증한다.
// stocks-home.test.mjs·ds-subnav.test.mjs와 같은 패턴.
//
// 실행: node --test web/assets/etf-signal.test.mjs
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
    classList:{add:noop,remove:noop,toggle:noop,contains:()=>false},
    dataset:{}, style:{}, children:[], innerHTML:'', textContent:'', hidden:false,
    addEventListener:noop, removeEventListener:noop, appendChild:noop, insertBefore:noop,
    setAttribute:noop, getAttribute:()=>null, remove:noop, focus:noop,
    closest:()=>null, contains:()=>false,
    getBoundingClientRect:()=>({top:0,left:0,width:0,height:0}),
    querySelector:()=>null, querySelectorAll:()=>[],
  };
  e.parentNode = {insertBefore:noop, removeChild:noop, appendChild:noop};
  return e;
}

function load() {
  const win = {
    location:{pathname:'/stocks/', hash:'', href:'https://x/stocks/'},
    addEventListener:noop, removeEventListener:noop,
    setInterval:()=>0, clearInterval:noop, setTimeout:()=>0, clearTimeout:noop,
    fetch:()=>Promise.reject(new Error('no network in test')),
    matchMedia:()=>({matches:false, addEventListener:noop}),
    sessionStorage:{getItem:()=>null, setItem:noop},
    localStorage:{getItem:()=>null, setItem:noop},
    Intl, Date, Math, JSON, console:{log:noop, warn:noop, error:noop},
    navigator:{userAgent:'node'},
    history:{pushState:noop, replaceState:noop},
    document:{
      readyState:'complete',
      getElementById:()=>mkEl(), querySelector:()=>mkEl(), querySelectorAll:()=>[],
      createElement:()=>mkEl(), addEventListener:noop,
      body:mkEl(), documentElement:mkEl(),
    },
  };
  win.window = win;
  const ctx = createContext(win);
  try { runInContext(readFileSync(join(HERE,'stocks-home.js'),'utf8'), ctx); } catch (e) { /* 로드 시점 DOM 접근 실패는 무시 — 훅만 필요 */ }
  return win.__etfSignal;
}

test('백만원을 조·억 표기로 바꾼다', () => {
  const { fmtEok } = load();
  assert.equal(fmtEok(1985526), '1조 9,855억');   // 하락 베팅 실측값
  assert.equal(fmtEok(1992279), '1조 9,923억');   // 상승 베팅 실측값
  assert.equal(fmtEok(356700), '3,567억');
  assert.equal(fmtEok(1000000), '1조');           // 나머지가 0이면 '억'을 붙이지 않는다
});

test('섹터 ETF 최고·최저를 등락률로 고른다', () => {
  const { pickExtremes } = load();
  const rows = [
    {label:'바이오', pct:4.59}, {label:'건설', pct:2.87},
    {label:'반도체', pct:-6.92}, {label:'IT', pct:-7.06},
  ];
  const r = pickExtremes(rows);
  assert.equal(r.top.label, '바이오');
  assert.equal(r.bottom.label, 'IT');
});

test('섹터 배열이 비어 있으면 극단값이 없다', () => {
  const { pickExtremes } = load();
  assert.equal(pickExtremes([]), null);
  assert.equal(pickExtremes(null), null);
});

test('lead·betting이 없으면 블록을 숨긴다 — 빈 껍데기를 노출하지 않는다(§0)', () => {
  const { shouldShowEtfSignal } = load();
  assert.equal(shouldShowEtfSignal({lead:{title:'t',body:'b'}, betting:{downRatio:50,upRatio:50}}), true);
  assert.equal(shouldShowEtfSignal({betting:{downRatio:50,upRatio:50}}), false);
  assert.equal(shouldShowEtfSignal({lead:{title:'t',body:'b'}}), false);
  assert.equal(shouldShowEtfSignal(null), false);
  assert.equal(shouldShowEtfSignal(undefined), false);
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/assets/etf-signal.test.mjs`
Expected: FAIL — `window.__etfSignal`이 `undefined`라 구조분해에서 `TypeError`

- [ ] **Step 3: `index.html`에 블록 마크업 추가**

`web/stocks/index.html:186`의 `<div class="block flow-block" id="flow-block" style="display:none;">`(자금 지도)의 **닫는 `</div>` 다음**, `<div class="block sig-block" id="sig-block">`(199번째 줄, 특이 신호) **앞**에 추가한다. 자금 지도와 같은 ETF 자금 흐름 계열이고, 3,904px짜리 특이 신호 블록 아래는 사실상 안 보이는 자리다.

(참고: `#flow-block`도 `style="display:none;"`으로 시작해 JS가 데이터를 받으면 켠다 — 새 ETF 블록의 `display:none` 시작이 이 관례와 같다.)

```html
    <!-- ETF 신호 — /api/signals의 etf(lead·betting·sector)로 채운다. 데이터가 없으면 통째로 숨긴다.
         홈 4개 서브탭 중 ETF만 대응 블록이 없어 신설한 요약 블록이다(서브탭 IA 스펙). -->
    <div class="block etfsig-block" id="etf-signal" style="display:none">
      <div class="block__h">
        <span class="block__t"><span class="ic">📊</span> ETF 신호</span>
        <span class="block__s" id="etfsig-asof"></span>
      </div>
      <div class="etfsig-lead">
        <div class="etfsig-lead__t" id="etfsig-title"></div>
        <p class="etfsig-lead__b" id="etfsig-body"></p>
      </div>
      <div class="etfsig-bet">
        <div class="etfsig-bet__lbl">
          <span class="dn">하락 베팅 <b id="etfsig-dn-amt"></b></span>
          <span class="up"><b id="etfsig-up-amt"></b> 상승 베팅</span>
        </div>
        <div class="etfsig-bar"><span class="etfsig-bar__dn" id="etfsig-bar-dn"></span></div>
        <div class="etfsig-bet__pct"><span id="etfsig-dn-pct"></span><span id="etfsig-up-pct"></span></div>
      </div>
      <div class="etfsig-kpi">
        <div><span class="k">인버스 거래량</span><span class="v" id="etfsig-inv"></span></div>
        <div><span class="k">KODEX 레버리지</span><span class="v num" id="etfsig-lev"></span></div>
      </div>
      <div class="etfsig-ext" id="etfsig-ext"></div>
      <a class="etfsig-more" onclick="go('etf-rank')">ETF 전체 보기 →</a>
    </div>
```

- [ ] **Step 4: `stocks-home.js`에 렌더 함수 추가**

`applySignals` 함수 **바로 위**에 추가:

```javascript
  // ETF 요약 블록 — /api/signals의 etf(lead·betting·sector). 상세는 #etf-rank 탭.
  // ⚠️ 위쪽 renderEtf()는 /api/vol-top 배열을 받는 다른 함수다. 혼동 금지.
  function fmtEok(mw){                       // 백만원 → '1조 9,855억'
    var eok = Math.round(mw/100);
    if(eok >= 10000){
      var jo = Math.floor(eok/10000), rest = eok % 10000;
      return jo + '조' + (rest ? ' ' + rest.toLocaleString() + '억' : '');
    }
    return eok.toLocaleString() + '억';
  }
  function pickExtremes(rows){
    if(!rows || !rows.length) return null;
    var s = rows.slice().sort(function(a,b){ return b.pct - a.pct; });
    return { top: s[0], bottom: s[s.length-1] };
  }
  function shouldShowEtfSignal(etf){
    return !!(etf && etf.lead && etf.lead.title && etf.lead.body && etf.betting);
  }
  function pctCls(v){ return v >= 0 ? 'up' : 'dn'; }
  function pctFmt(v){ return (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2) + '%'; }
  function renderEtfSignal(etf, asOf){
    var box = document.getElementById('etf-signal');
    if(!box) return;
    if(!shouldShowEtfSignal(etf)){ box.style.display = 'none'; return; }   // 없으면 비운다(§0)
    var b = etf.betting;
    var set = function(id, txt){ var e = document.getElementById(id); if(e) e.textContent = txt; };
    set('etfsig-asof', asOf && asOf.label ? asOf.label + ' 종가' : '');
    set('etfsig-title', etf.lead.title);
    // lead.body는 우리 API가 만든 문자열이고 <b>만 들어간다 — 그대로 렌더한다.
    var bodyEl = document.getElementById('etfsig-body'); if(bodyEl) bodyEl.innerHTML = etf.lead.body;
    set('etfsig-dn-amt', fmtEok(b.downAmt));
    set('etfsig-up-amt', fmtEok(b.upAmt));
    set('etfsig-dn-pct', b.downRatio + '%');
    set('etfsig-up-pct', b.upRatio + '%');
    var bar = document.getElementById('etfsig-bar-dn'); if(bar) bar.style.width = b.downRatio + '%';
    set('etfsig-inv', 'KODEX 200 대비 ×' + b.invVolMultiple);
    var lev = document.getElementById('etfsig-lev');
    if(lev){ lev.textContent = pctFmt(b.levPct); lev.className = 'v num ' + pctCls(b.levPct); }
    var ext = document.getElementById('etfsig-ext'), ex = pickExtremes(etf.sector);
    if(ext){
      ext.innerHTML = ex ? [
        ['섹터 ETF 최고', ex.top], ['섹터 ETF 최저', ex.bottom]
      ].map(function(p){
        return '<div class="etfsig-ext__r"><span class="k">' + p[0] + '</span>'
             + '<span class="n">' + p[1].label + '</span>'
             + '<span class="v num ' + pctCls(p[1].pct) + '">' + pctFmt(p[1].pct) + '</span></div>';
      }).join('') : '';
    }
    box.style.display = '';
  }
  // 테스트 훅 — node:vm에서 순수 포맷터만 꺼내 검증한다(DOM 결과는 브라우저에서 확인).
  window.__etfSignal = { fmtEok: fmtEok, pickExtremes: pickExtremes, shouldShowEtfSignal: shouldShowEtfSignal };

```

`applySignals(d)` 본문의 `renderTodayLine();` **다음 줄**에 추가:

```javascript
    renderEtfSignal(d.etf, d.asOf);
```

- [ ] **Step 5: CSS 추가**

`web/assets/stocks-home.css` 맨 끝에 추가:

```css
/* ETF 요약 블록(홈) — 상세는 #etf-rank. 모든 변수에 폴백을 둔다(§5). */
.etfsig-lead{padding:14px 16px 12px;}
.etfsig-lead__t{font-size:14px;font-weight:700;color:var(--ink,#13151A);margin-bottom:6px;}
.etfsig-lead__b{margin:0;font-size:13px;line-height:1.6;color:var(--muted,#5B6472);}
.etfsig-lead__b b{font-weight:700;color:var(--ink,#13151A);}
.etfsig-bet{padding:0 16px 12px;}
.etfsig-bet__lbl{display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px;}
.etfsig-bet__lbl .dn{color:var(--dn,#2775ED);}
.etfsig-bet__lbl .up{color:var(--up,#E03131);}
.etfsig-bet__lbl b{font-weight:700;}
.etfsig-bar{position:relative;height:8px;border-radius:999px;background:var(--up,#E03131);overflow:hidden;}
.etfsig-bar__dn{position:absolute;left:0;top:0;bottom:0;background:var(--dn,#2775ED);}
.etfsig-bet__pct{display:flex;justify-content:space-between;font-size:13px;color:var(--muted,#5B6472);margin-top:5px;}
.etfsig-kpi{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--hair,#E5E7EB);border-top:1px solid var(--hair,#E5E7EB);border-bottom:1px solid var(--hair,#E5E7EB);}
.etfsig-kpi>div{background:var(--soft,#F9FAFB);padding:10px 16px;display:flex;flex-direction:column;gap:3px;}
.etfsig-kpi .k{font-size:13px;color:var(--muted,#5B6472);}
.etfsig-kpi .v{font-size:14px;font-weight:700;color:var(--ink,#13151A);}
.etfsig-kpi .v.up{color:var(--up,#E03131);}
.etfsig-kpi .v.dn{color:var(--dn,#2775ED);}
.etfsig-ext__r{display:flex;align-items:center;gap:8px;padding:10px 16px;border-bottom:1px solid var(--hair,#E5E7EB);font-size:13px;}
.etfsig-ext__r:last-child{border-bottom:0;}
.etfsig-ext__r .k{color:var(--muted,#5B6472);}
.etfsig-ext__r .n{font-weight:700;color:var(--ink,#13151A);}
.etfsig-ext__r .v{margin-left:auto;font-weight:700;}
.etfsig-ext__r .v.up{color:var(--up,#E03131);}
.etfsig-ext__r .v.dn{color:var(--dn,#2775ED);}
.etfsig-more{display:block;padding:12px 16px;text-align:center;font-size:13px;font-weight:500;color:var(--primary,#006EFF);cursor:pointer;border-top:1px solid var(--hair,#E5E7EB);}
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `node --test web/assets/etf-signal.test.mjs`
Expected: PASS (4 tests)

Run: `node --test web/assets/*.test.mjs`
Expected: 전체 PASS, fail 0 (기존 테스트 회귀 없음)

- [ ] **Step 7: 브라우저 확인**

```bash
cd web && python3 -m http.server 8899
```

`http://localhost:8899/stocks/`는 `/api/*`가 없어 스켈레톤만 뜬다. 실데이터로 보려면 콘솔에서 라이브 응답을 직접 주입한다:

```js
fetch('https://doubleshot.space/api/signals').then(r=>r.json()).then(d=>{ renderEtfSignal(d.etf, d.asOf); })
```

확인할 것: 블록이 자금 지도 **다음**, 특이 신호 **앞**에 뜬다 / 하락·상승 베팅 바 비율이 `downRatio:upRatio`와 일치 / 레버리지 음수가 **파랑**, 섹터 최고가 **빨강**(한국 관례) / `ETF 전체 보기 →` 클릭 시 `#etf-rank`로 전환. `resize_window` 375px에서 KPI 2칸이 안 깨지는지도 본다.

- [ ] **Step 8: 커밋**

```bash
git add web/stocks/index.html web/assets/stocks-home.js web/assets/stocks-home.css web/assets/etf-signal.test.mjs
git commit -m "feat(종목시그널): 홈에 ETF 요약 블록 신설

서브탭 4개 중 ETF만 홈에 대응 블록이 없었다(홈 본문에 'ETF'라는 단어가
한 번도 안 나옴). /api/signals의 etf 필드는 이미 받아오면서 쓰지 않고
버리고 있어 새 fetch 없이 붙였다. 데이터가 없으면 블록을 통째로 숨긴다."
```

---

## Task 6: 홈 진입 링크 3종 (섹터 전체 보기 + 패시브·순위 복구)

실측 결과 **홈 전체에 다른 화면으로 가는 링크가 `특이 신호 전체 보기 →` 하나뿐**이다(15,095px 중 y=8534 지점). `#sector`·`#passive`·`#ranking`은 만들어져 있는데 홈에서 갈 방법이 없다.

**Files:**
- Modify: `web/stocks/index.html`
- Modify: `web/assets/stocks-home.css`

- [ ] **Step 1: 섹터별 대표 종목 블록에 링크 추가**

⚠️ **새 클래스를 만들지 말 것.** 기존 링크가 이미 `.more`를 쓴다 — `web/stocks/index.html:210`의 `<a class="more" onclick="go('signals-all')">특이 신호 전체 보기 →</a>`, 규칙은 `stocks-home.css:258`. 같은 역할에 새 클래스를 만들면 §30 이중 구현이고, 두 "전체 보기" 링크가 서로 다르게 보이게 된다.

`web/stocks/index.html`에서 `<div class="block sbx-block">`(165번째 줄, 섹터별 대표 종목)의 **닫는 `</div>` 바로 앞**에 추가:

```html
      <a class="more" onclick="go('sector')">섹터 전체 보기 →</a>
```

- [ ] **Step 2: 패시브·순위 링크 블록 추가**

Task 5에서 넣은 `#etf-signal` 블록의 **닫는 `</div>` 다음**에 추가:

```html
    <!-- 탭에 없는 화면 진입점 — 서브탭에는 넣지 않되(스펙: 탭 넘침 방지) 홈에서는 도달 가능해야 한다.
         지금까지 이 두 화면은 홈에 링크가 없어 사실상 고립돼 있었다. -->
    <div class="block">
      <div class="block__h"><span class="block__t"><span class="ic">🔗</span> 더 보기</span></div>
      <a class="xlink" onclick="go('passive')"><span class="n">패시브 민감주</span><span class="d">ETF 기계매매에 노출된 종목</span><span class="go">›</span></a>
      <a class="xlink" onclick="go('ranking')"><span class="n">거래량 순위</span><span class="d">추적 40종목 거래량·상승률</span><span class="go">›</span></a>
    </div>
```

- [ ] **Step 3: CSS 추가**

`web/assets/stocks-home.css` 맨 끝에 추가:

```css
/* 탭에 없는 화면 진입 링크. '전체 보기' 링크는 기존 .more(stocks-home.css:258)를 그대로 쓴다 — 새로 만들지 않는다. */
.xlink{display:flex;align-items:center;gap:10px;padding:13px 16px;border-bottom:1px solid var(--hair,#E5E7EB);cursor:pointer;}
.xlink:last-child{border-bottom:0;}
.xlink .n{font-size:14px;font-weight:700;color:var(--ink,#13151A);}
.xlink .d{font-size:13px;color:var(--muted,#5B6472);}
.xlink .go{margin-left:auto;color:var(--muted,#5B6472);font-size:16px;}
```

- [ ] **Step 4: 진입점이 실제로 늘었는지 확인**

```bash
cd web && python3 -m http.server 8899
```

브라우저 콘솔에서:

```js
[...document.getElementById('home').querySelectorAll('[onclick]')]
  .map(e => (e.getAttribute('onclick').match(/go\('([a-z-]+)'\)/)||[])[1])
  .filter(Boolean)
```

Expected: `['sector','etf-rank','passive','ranking']` + 기존 `signals-all` — 실측 전에는 `signals-all` 하나뿐이었다.

- [ ] **Step 5: 커밋**

```bash
git add web/stocks/index.html web/assets/stocks-home.css
git commit -m "feat(종목시그널): 홈에서 섹터·패시브·거래량 순위로 가는 링크 복구

홈 15,095px 전체에 다른 화면으로 가는 링크가 '특이 신호 전체 보기' 하나뿐이라
#sector·#passive·#ranking이 만들어져 있는데도 홈에서 도달할 수 없었다."
```

---

## 마무리 확인

- [ ] **전체 테스트**

Run: `node --test web/assets/*.test.mjs && node --test api/*.test.mjs && python3 -m pytest scripts/ -q`
Expected: 전부 통과.

- [ ] **작업 산출물만 변경됐는지 확인**

Run: `git status --short`
Expected: 커밋되지 않은 변경 없음. 특히 `web/data/`·`web/briefings/`에 변경이 없어야 한다.

- [ ] **스펙 갱신**

`docs/superpowers/specs/2026-08-02-stocks-subnav-ia-design.md`의 "배치" 절에 실제 구현을 반영한다 — 스펙은 히어로·시장 패널이 이미 페이지 레벨인 것처럼 썼지만 실제로는 `#home` 안에 있었고, 이번에 밖으로 옮겼다는 사실을 적는다. 문서가 코드보다 오래 사는 상황을 만들지 않는다(§10).

```bash
git add docs/superpowers/specs/2026-08-02-stocks-subnav-ia-design.md
git commit -m "docs(서브탭): 히어로·지수 카드를 화면 밖으로 옮긴 실제 구현 반영"
```
