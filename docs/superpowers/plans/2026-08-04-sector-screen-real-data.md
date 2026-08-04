# 섹터 화면 실데이터화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/stocks/#sector` 화면을 반도체 하드코딩 고정에서 8개 섹터 전체 실데이터 전환으로 바꾸고, `goStock('000660')` 오타 버그를 없애고, 실측 소스가 없는 패시브 쏠림·ETF 관련 수치를 제거한다.

**Architecture:** `web/data/stocks-snapshot.json`(클라이언트가 이미 `SNAP` 전역으로 로드 중, 46종목 전체에 `sector` 필드 보유)을 `#sector` 화면의 **유일한** 데이터 소스로 통일한다. 지금은 섹터 평균·시장폭이 `/api/vol-top`(장중 라이브, 거래대금 상위 40종목만 커버)에서, 종목 랭킹은 완전 하드코딩(`SECTOR_RANK`)에서 오는 이중 소스 구조인데, 이를 하나로 합친다. 서브탭 IA 목업(`docs/prototypes/2026-08-03-stocks-subnav-fullsize.html`)에서 확정한 섹터 선택 칩 디자인(`.secsel`)을 그대로 가져와 쓴다.

**Tech Stack:** 순수 JS(기존 `stocks-home.js` IIFE 안), 순수 CSS. 테스트는 `node --test`(node:vm 샌드박스에서 실제 프로덕션 파일 로드 — `etf-signal.test.mjs`·`ds-subnav.test.mjs`와 같은 패턴).

---

## 배경 — 사전 조사로 확정된 사실 (다시 조사하지 말 것)

- `SNAP`(전역, `web/assets/stocks-home.js:2782`에서 할당)은 `web/data/stocks-snapshot.json`을 담고 있고, **46종목 전체**에 `sector` 필드가 있다(`semicon`/`power`/`defense`/`ship`/`battery`/`auto`/`bio`/`finance` 8개 키, `stock_universe.json`과 동일). 섹터별 종목 수: semicon 7·power 5·defense 5·ship 4·battery 6·auto 6·bio 6·finance 7.
- `SNAP`은 `(function(){...})()` IIFE 안(`stocks-home.js:2062`~`2805`)에서 선언되고, 이 IIFE 안에 이미 `SECTOR_LABELS`(`:2065`)와 `renderSectorBreadth`(`:2138`)·`renderEtfSignal`(`:2253`, Task 5 작업물)·`applySignals`(`:2307`)·`pollVolTop`(`:2369`)가 전부 같이 있다. **이번에 새로 짜는 함수도 반드시 이 IIFE 안에 넣어야 `SNAP`에 접근할 수 있다** — `SECTOR_RANK`/`secRow`/`secRender`(현재 `:1184`~`:1229`, 최상위 스코프)는 이 IIFE 밖에 있어서 애초에 `SNAP`을 볼 수 없었다.
- `SNAP` 로드 콜백은 `stocks-home.js:2779`~`2789`: `fetch(...).then(function(snap){ SNAP=snap; ...; if(SNAP&&SNAP.generated_at){_asOfYmd=...;applyAsOf();} })`. 이번 작업은 이 콜백 안, `applyAsOf();` 바로 다음 줄에 새 화면 렌더 호출을 추가한다.
- `goStock('000660')` 오타: `secRow(r)`(`:1215`)가 각 행의 실제 코드 `r[2]`를 스코프에 갖고 있으면서도 `onclick`에는 리터럴 `'000660'`을 박아뒀다. `passiveRow(r,i)`(`:1352`)에도 동일한 오타가 있다.
- `.ds-asof` 클래스(`applyAsOf()`가 채움, `:948`)는 장중엔 "오늘 실시간", 마감 후엔 "{날짜} 종가"를 보여주는 **공용** 클래스다. 이 화면은 이제 스냅샷(항상 마감 기준) 전용이므로 이 클래스를 재사용하면 안 된다 — 장중에 "오늘 실시간"이라고 뜨는데 실제로는 마감 데이터인 라벨 불일치가 생긴다(§24류 사고). 별도 텍스트로 채운다.
- **사용자 확정 사항 (2026-08-04)**:
  1. 섹터 평균·시장폭·센티멘트·대장주·랭킹 **전부** `stocks-snapshot.json` 단일 소스로 통일 (지금처럼 일부는 vol-top 라이브·일부는 하드코딩인 상태를 없앤다).
  2. 패시브 쏠림 데이터(ETF 보유비중·소진일수)는 이 저장소 어디에도 실측 소스가 없다 — `#sector`의 미니블록과 `#passive` 화면 전체를 "준비 중" 빈 상태로 바꾼다. 수집 스크립트는 이번 범위 밖.
  3. "반도체 대표 ETF"(`KODEX 반도체 +2.8%`, 하드코딩) 블록도 실측 소스가 없어 제거.
  4. `.lede` 문장("HBM·메모리 업황 회복 기대로…")도 근거 없는 서사 리터럴이라 제거.
- **대장주(리더) 선정**: 종목 "선택"은 `scripts/config/stock_universe.json`의 섹터별 상위 2~3종목을 손으로 골랐다(아래 `SECTOR_LEADERS` 상수) — 이건 §20 위반이 아니다, 밤사이 브리지의 `BRIDGE_US_TICKERS`와 같은 패턴이다(어떤 종목을 보여줄지는 큐레이션, 값은 전부 `SNAP` 실측). 8개 전부 `SNAP.stocks`에 존재함을 이미 확인했다:
  ```
  semicon: 005930,000660,042700   power: 267260,010120,298040
  defense: 012450,079550,064350  ship: 329180,042660,010140
  battery: 373220,247540,006400  auto: 005380,000270,012330
  bio: 207940,068270,000100      finance: 032830,105560,055550
  ```

## 파일 구조

| 파일 | 책임 |
| --- | --- |
| `web/assets/stocks-home.js` | `secBuildSectorData`·`secAllAverages`·`secShowSector`·`secRenderChips`·`secSectorRow`·`secAsOfLabel` 신규(Block 8 IIFE 안). `SECTOR_RANK`·`secRow`·`secRender`·`secLoadMore`·`renderSectorBreadth`·`PASSIVE_DATA`·`passiveRow`·`passiveRender`·`passiveSort` 제거/축소 |
| `web/stocks/index.html` | `#sector`·`#passive` 화면 마크업 개편 |
| `web/assets/stocks-home.css` | `.secsel*` 칩 스타일(프로토타입에서 그대로 가져옴), 빈 상태 스타일 |
| `web/assets/sector-screen.test.mjs` (신규) | 순수 함수 회귀 테스트 |

---

## Task 1: `secBuildSectorData`·`secAllAverages` 순수 함수

**Files:**
- Modify: `web/assets/stocks-home.js` (Block 8 IIFE 안, `renderSectorBreadth` 자리)
- Test: `web/assets/sector-screen.test.mjs` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

`web/assets/sector-screen.test.mjs` 신규 생성:

```javascript
// stocks-home.js의 섹터 화면 데이터 함수 회귀 테스트 — node:vm에서 실제 프로덕션 파일 로드
//
// 순수 함수를 테스트 파일에 복제하면 사본이 원본과 어긋나므로(SERVICE_RULES §20류),
// 실제 파일을 최소 DOM 스텁과 함께 실행하고 window.__sectorScreen으로 꺼내 검증한다.
// etf-signal.test.mjs·ds-subnav.test.mjs와 같은 패턴.
//
// 실행: node --test web/assets/sector-screen.test.mjs
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
      body:mkEl(), documentElement:mkEl(), head:mkEl(),
    },
  };
  win.window = win;
  const ctx = createContext(win);
  try { runInContext(readFileSync(join(HERE,'stocks-home.js'),'utf8'), ctx); } catch (e) { /* 로드 시점 DOM 접근 실패는 무시 — 훅만 필요 */ }
  return win.__sectorScreen;
}

function fixtureSnap() {
  return {
    generated_at: '2026-08-01T16:33:00+09:00',
    stocks: {
      '005930': {name:'삼성전자', sector:'semicon', change_pct:-6.4},
      '000660': {name:'SK하이닉스', sector:'semicon', change_pct:3.4},
      '042700': {name:'한미반도체', sector:'semicon', change_pct:1.8},
      '005380': {name:'현대차', sector:'auto', change_pct:0.5},
      '000270': {name:'기아', sector:'auto', change_pct:-1.1},
    },
  };
}

test('섹터로 필터링하고 등락률 내림차순 정렬한다', () => {
  const { secBuildSectorData } = load();
  const d = secBuildSectorData(fixtureSnap(), 'semicon');
  assert.equal(d.total, 3);
  assert.deepEqual(d.rows.map((r) => r.code), ['000660', '042700', '005930']);
  assert.equal(d.rows[0].pct, 3.4);
});

test('상승·하락·보합 개수와 평균을 정확히 센다', () => {
  const { secBuildSectorData } = load();
  const d = secBuildSectorData(fixtureSnap(), 'semicon');
  assert.equal(d.upN, 2);
  assert.equal(d.dnN, 1);
  assert.equal(d.flatN, 0);
  assert.equal(Math.round(d.avg * 100) / 100, Math.round(((-6.4 + 3.4 + 1.8) / 3) * 100) / 100);
});

test('대장주는 SECTOR_LEADERS 순서·실측 등락률로 채워진다', () => {
  const { secBuildSectorData } = load();
  const d = secBuildSectorData(fixtureSnap(), 'semicon');
  assert.deepEqual(d.leaders.map((r) => r.code), ['005930', '000660', '042700']);
  assert.equal(d.leaders[0].pct, -6.4);
});

test('스냅샷에 없는 섹터는 null을 반환한다 — 지어내지 않는다(§0)', () => {
  const { secBuildSectorData } = load();
  assert.equal(secBuildSectorData(fixtureSnap(), 'ship'), null);
  assert.equal(secBuildSectorData({stocks:{}}, 'semicon'), null);
  assert.equal(secBuildSectorData(null, 'semicon'), null);
});

test('secAllAverages는 데이터가 있는 섹터만 돌려준다', () => {
  const { secAllAverages } = load();
  const out = secAllAverages(fixtureSnap());
  assert.deepEqual(Object.keys(out).sort(), ['auto', 'semicon']);
  assert.equal(out.semicon.label, '반도체');
  assert.equal(out.auto.label, '자동차');
});

test('마감 라벨은 장중 여부와 무관하게 항상 "N일 마감"이다', () => {
  // .ds-asof(장중 '오늘 실시간')와 다른 별도 라벨이어야 한다 — 이 화면은 항상 스냅샷(마감) 기준.
  const { secAsOfLabel } = load();
  const label = secAsOfLabel(fixtureSnap());
  assert.ok(label.endsWith('마감'), `"마감"으로 끝나야 하는데: ${label}`);
  assert.ok(!label.includes('실시간'), `실시간이 섞이면 안 되는데: ${label}`);
});

test('generated_at이 없으면 빈 문자열 — 지어내지 않는다', () => {
  const { secAsOfLabel } = load();
  assert.equal(secAsOfLabel({}), '');
  assert.equal(secAsOfLabel(null), '');
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/assets/sector-screen.test.mjs`
Expected: FAIL — `window.__sectorScreen`이 `undefined`라 구조분해에서 `TypeError`

- [ ] **Step 3: `renderSectorBreadth`를 새 함수들로 교체**

`web/assets/stocks-home.js`에서 `function renderSectorBreadth(all){`(`:2138`)부터 그 함수의 닫는 `}`까지(`:2161`) **전체를 삭제**하고, 그 자리에 아래를 넣는다:

```javascript
  // 8개 섹터 대표 종목(대장주) — stock_universe.json 순서 그대로 상위 2~3종목 선별.
  // 종목 "선택"만 손으로 골랐을 뿐 값은 전부 SNAP(stocks-snapshot.json) 실측이다 —
  // 밤사이 브리지의 BRIDGE_US_TICKERS와 같은 패턴(§20 위반 아님, 종목 선택 큐레이션).
  var SECTOR_LEADERS={
    semicon:['005930','000660','042700'],
    power:['267260','010120','298040'],
    defense:['012450','079550','064350'],
    ship:['329180','042660','010140'],
    battery:['373220','247540','006400'],
    auto:['005380','000270','012330'],
    bio:['207940','068270','000100'],
    finance:['032830','105560','055550'],
  };
  var SECTOR_ICONS={semicon:'🔧',power:'⚡',defense:'🛡️',ship:'🚢',battery:'🔋',auto:'🚗',bio:'🧬',finance:'🏦'};

  // 섹터 화면 데이터 — stocks-snapshot.json(SNAP)만 쓴다. vol-top·API 라이브 소스와
  // 섞지 않는다(§0 정합성 우선, §24 시점 불일치 방지) — 이 화면은 항상 "직전 마감 기준"이다.
  function secBuildSectorData(snap, key){
    if(!snap||!snap.stocks) return null;
    var rows=[];
    Object.keys(snap.stocks).forEach(function(code){
      var s=snap.stocks[code];
      if(s&&s.sector===key&&typeof s.change_pct==='number') rows.push({code:code,name:s.name,pct:s.change_pct});
    });
    if(!rows.length) return null;
    rows.sort(function(a,b){return b.pct-a.pct;});
    var upN=0,dnN=0,flatN=0,sum=0;
    rows.forEach(function(r){sum+=r.pct;if(r.pct>0)upN++;else if(r.pct<0)dnN++;else flatN++;});
    var total=rows.length,avg=sum/total;
    var byCode={}; rows.forEach(function(r){byCode[r.code]=r;});
    var leaders=(SECTOR_LEADERS[key]||[]).map(function(c){return byCode[c];}).filter(Boolean);
    return {key:key,label:SECTOR_LABELS[key]||key,rows:rows,total:total,upN:upN,dnN:dnN,flatN:flatN,avg:avg,leaders:leaders};
  }

  // 8개 섹터 전부의 평균 — 섹터 선택 칩 렌더에 쓴다. 데이터 없는 섹터는 빠진다(§0).
  function secAllAverages(snap){
    var out={};
    Object.keys(SECTOR_LABELS).forEach(function(key){
      var d=secBuildSectorData(snap,key);
      if(d) out[key]={avg:d.avg,label:d.label};
    });
    return out;
  }

  // 이 화면은 항상 스냅샷(마감) 기준이라 .ds-asof(장중 '오늘 실시간')를 재사용하면 안 된다.
  function secAsOfLabel(snap){
    if(!snap||!snap.generated_at) return '';
    var ymd=String(snap.generated_at).slice(0,10);
    return fmtKoDate(ymd)+' 마감';
  }

  // 테스트 훅 — node:vm에서 순수 함수만 꺼내 검증한다(DOM 결과는 브라우저에서 확인).
  window.__sectorScreen={secBuildSectorData:secBuildSectorData, secAllAverages:secAllAverages, secAsOfLabel:secAsOfLabel};
```

이 코드는 `renderTops(d)` 함수 안에서 옛 `renderSectorBreadth(all);` 호출부(`:2135`, 정확한 줄은 삭제 전 `grep -n "renderSectorBreadth(all);" web/assets/stocks-home.js`로 재확인)를 그대로 두면 `renderSectorBreadth is not defined`로 깨진다 — 이 태스크에서는 아직 호출부를 안 지운다(Task 3에서 지운다). **일단 `ReferenceError`가 나도 정상이다** — Step 4는 새 테스트 파일만 통과하면 된다.

- [ ] **Step 4: 새 테스트 통과 확인**

Run: `node --test web/assets/sector-screen.test.mjs`
Expected: PASS (7 tests)

- [ ] **Step 5: 전체 스위트 확인 — `renderTops` 호출 경로는 아직 깨져 있어도 정상**

Run: `node --test web/assets/*.test.mjs`
Expected: `sector-screen.test.mjs` 7개는 PASS. `stocks-home.test.mjs`가 `pollVolTop`/`renderTops`를 실행 경로로 태우는 테스트가 있다면 `renderSectorBreadth is not defined`로 FAIL할 수 있다 — **그 경우 실패 테스트 이름을 정확히 기록해 두고 Task 3으로 넘긴다** (Task 3에서 호출부를 지우면 해결된다). 다른 실패가 있으면 안 된다.

- [ ] **Step 6: 커밋**

```bash
git add web/assets/stocks-home.js web/assets/sector-screen.test.mjs
git commit -m "feat(종목시그널): 섹터 데이터 함수를 stocks-snapshot.json 단일 소스로 신설

renderSectorBreadth(반도체 고정, /api/vol-top 라이브)를 8개 섹터 전부를
지원하는 secBuildSectorData/secAllAverages로 교체한다. 아직 화면에
배선하지 않아 renderTops의 옛 호출부가 깨져 있을 수 있다 — Task 3에서
정리한다."
```

---

## Task 2: 렌더 함수 — `secShowSector`·`secRenderChips`·행 템플릿

**Files:**
- Modify: `web/assets/stocks-home.js` (Task 1에서 추가한 함수들 바로 아래)
- Test: `web/assets/sector-screen.test.mjs`

- [ ] **Step 1: 실패하는 테스트 추가**

`web/assets/sector-screen.test.mjs`의 `load()`를 Task 3(서브탭)의 패턴과 동일하게 확장한다 — DOM을 실제로 기록하는 스텁이 필요하다. `mkEl()` 바로 아래에 추가:

```javascript
/** id별로 실제 엘리먼트를 돌려주는 문서 스텁. 렌더 함수가 innerHTML/textContent를 쓰는 걸 검증한다. */
function mkDoc() {
  const els = {};
  const get = (id) => { if (!els[id]) els[id] = mkEl(); return els[id]; };
  return {
    els,
    doc: {
      readyState:'complete',
      getElementById: get,
      querySelector: () => mkEl(), querySelectorAll: () => [],
      createElement:()=>mkEl(), addEventListener:noop,
      body:mkEl(), documentElement:mkEl(), head:mkEl(),
    },
  };
}
```

`load()` 함수를 아래로 **교체**(DOM 스텁을 주입할 수 있도록):

```javascript
function load(docOverride) {
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
    document: docOverride || {
      readyState:'complete',
      getElementById:()=>mkEl(), querySelector:()=>mkEl(), querySelectorAll:()=>[],
      createElement:()=>mkEl(), addEventListener:noop,
      body:mkEl(), documentElement:mkEl(), head:mkEl(),
    },
  };
  win.window = win;
  const ctx = createContext(win);
  try { runInContext(readFileSync(join(HERE,'stocks-home.js'),'utf8'), ctx); } catch (e) { /* 로드 시점 DOM 접근 실패는 무시 — 훅만 필요 */ }
  return win.__sectorScreen;
}
```

기존 6개 테스트는 `load()`를 인자 없이 그대로 호출하므로 수정 없이 통과해야 한다(기본값이 예전과 동일).

파일 끝에 추가:

```javascript
test('secShowSector — 실제 DOM에 등락률·상승/하락 개수를 쓴다', () => {
  const { doc, els } = mkDoc();
  const { secShowSector } = load(doc);
  secShowSector(fixtureSnap(), 'semicon');

  assert.equal(els['sec-avg'].textContent, '−0.40%'); // (−6.4+3.4+1.8)/3 = −0.4
  assert.equal(els['sec-avg'].className, 'v num dn');
  assert.match(els['sec-breadth-label'].innerHTML, /3종목 중/);
  assert.match(els['sec-rows'].innerHTML, /SK하이닉스/);
});

test('secShowSector — 각 행의 onclick이 그 행의 실제 코드를 쓴다 (goStock 하드코딩 버그 회귀 방지)', () => {
  const { doc, els } = mkDoc();
  const { secShowSector } = load(doc);
  secShowSector(fixtureSnap(), 'semicon');

  assert.match(els['sec-rows'].innerHTML, /goStock\('000660'\)/);   // 1위: SK하이닉스
  assert.match(els['sec-rows'].innerHTML, /goStock\('042700'\)/);   // 2위: 한미반도체
  assert.match(els['sec-rows'].innerHTML, /goStock\('005930'\)/);   // 3위: 삼성전자
  // 세 행의 코드가 전부 같은 값이면(예전 버그) 위 세 assert 중 최소 하나는 실패한다.
});

test('secShowSector — 대장주 3명을 순서대로 렌더한다', () => {
  const { doc, els } = mkDoc();
  const { secShowSector } = load(doc);
  secShowSector(fixtureSnap(), 'semicon');

  const html = els['sec-leaders'].innerHTML;
  const i1 = html.indexOf('①'), i2 = html.indexOf('②'), i3 = html.indexOf('③');
  assert.ok(i1 >= 0 && i2 > i1 && i3 > i2, '①②③ 순서가 맞아야 한다');
  assert.match(html, /goStock\('005930'\)/);
});

test('secShowSector — 데이터 없는 섹터는 기존 DOM을 그대로 둔다(지우지 않는다)', () => {
  const { doc, els } = mkDoc();
  const { secShowSector } = load(doc);
  secShowSector(fixtureSnap(), 'semicon');
  const before = els['sec-rows'].innerHTML;
  secShowSector(fixtureSnap(), 'ship'); // fixtureSnap에는 ship 데이터가 없다
  assert.equal(els['sec-rows'].innerHTML, before, '없는 섹터로 전환 시도 시 화면이 깨지면 안 된다');
});

test('secRenderChips — 활성 섹터가 맨 앞, 나머지는 평균 내림차순', () => {
  const { doc, els } = mkDoc();
  const { secRenderChips } = load(doc);
  secRenderChips(els['secsel'], 'semicon', {
    semicon:{avg:-4.1,label:'반도체'}, auto:{avg:1.5,label:'자동차'}, bio:{avg:-0.1,label:'바이오'},
  });
  const order = [...els['secsel'].innerHTML.matchAll(/data-sector="([a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, ['semicon', 'auto', 'bio']); // semicon 먼저(활성), 그다음 1.5 > -0.1
});

test('secRenderChips — 활성 칩만 is-active 클래스를 갖는다', () => {
  const { doc, els } = mkDoc();
  const { secRenderChips } = load(doc);
  secRenderChips(els['secsel'], 'auto', { semicon:{avg:-4.1,label:'반도체'}, auto:{avg:1.5,label:'자동차'} });
  const autoTag = els['secsel'].innerHTML.match(/<a[^>]*data-sector="auto"[^>]*>/)[0];
  const semiTag = els['secsel'].innerHTML.match(/<a[^>]*data-sector="semicon"[^>]*>/)[0];
  assert.ok(autoTag.includes(' on'), '활성 칩에 on 클래스가 없다');
  assert.ok(!semiTag.includes(' on'), '비활성 칩에 on이 붙었다');
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test web/assets/sector-screen.test.mjs`
Expected: FAIL — `secShowSector`/`secRenderChips`가 `undefined`

- [ ] **Step 3: 렌더 함수 추가**

`web/assets/stocks-home.js`에서 Task 1의 `window.__sectorScreen={...};` 줄을 **아래 전체로 교체**한다:

```javascript
  function secSectorRow(r,i){
    var top3=i<3;
    var cls=r.pct>=0?'up':'dn', sign=r.pct>=0?'+':'−';
    var barPct=Math.max(4,Math.min(100,Math.round(Math.abs(r.pct)/10*100)));
    return '<a class="row" onclick="goStock(\''+r.code+'\')"><span class="rk'+(top3?' t':'')+' num">'+(i+1)+'</span>'
      +'<div class="nm"><b>'+r.name+'</b><small class="num">'+r.code+'</small></div>'
      +'<div class="barwrap"><div class="bar '+cls+'" style="width:'+barPct+'%"></div></div>'
      +'<span class="barval '+cls+' num">'+sign+Math.abs(r.pct).toFixed(1)+'%</span></a>';
  }

  function secChipHtml(key,label,avg,active){
    var cls=avg>=0?'up':'dn', sign=avg>=0?'+':'−';
    return '<a class="secsel__i'+(active?' on':'')+'" role="tab" aria-selected="'+(active?'true':'false')+'" data-sector="'+key+'">'
      +'<span class="ic">'+(SECTOR_ICONS[key]||'')+'</span>'+label
      +'<b class="'+cls+' num">'+sign+Math.abs(avg).toFixed(2)+'%</b></a>';
  }

  // order: 활성 섹터 먼저, 나머지는 평균 내림차순. 순수 평균순이면 최하위 섹터를 보는 중일 때
  // 그 섹터가 390px 가로스크롤 밖으로 밀려 자기 자신이 안 보인다(목업 설계 노트 그대로).
  function secRenderChips(box, activeKey, allAvgs){
    if(!box) return;
    var order=Object.keys(allAvgs).filter(function(k){return k!==activeKey;})
      .sort(function(a,b){return allAvgs[b].avg-allAvgs[a].avg;});
    if(allAvgs[activeKey]) order.unshift(activeKey);
    box.innerHTML=order.map(function(k){
      var d=allAvgs[k]; return secChipHtml(k,d.label,d.avg,k===activeKey);
    }).join('');
  }

  var secActiveKey='semicon';
  function secShowSector(snap, key){
    var d=secBuildSectorData(snap,key);
    if(!d) return;   // 없는 섹터면 화면을 건드리지 않는다(§0) — 직전 상태 유지
    secActiveKey=key;

    var crumbEl=document.getElementById('sec-crumb-label'); if(crumbEl) crumbEl.textContent=d.label;
    var titleEl=document.getElementById('sec-title'); if(titleEl) titleEl.textContent=(SECTOR_ICONS[key]||'')+' '+d.label;
    var subEl=document.getElementById('sec-sub'); if(subEl) subEl.textContent='추적 '+d.total+'종목 · 코스피·코스닥 · '+secAsOfLabel(snap);

    var avgEl=document.getElementById('sec-avg');
    if(avgEl){avgEl.textContent=(d.avg>=0?'+':'−')+Math.abs(d.avg).toFixed(2)+'%';avgEl.className='v num '+(d.avg>=0?'up':'dn');}

    var lbl=document.getElementById('sec-breadth-label');
    if(lbl) lbl.innerHTML=d.total+'종목 중 <b class="up num">'+d.upN+' 상승</b>';
    var bbar=document.getElementById('sec-bbar');
    if(bbar){var bu=Math.round(d.upN/d.total*1000)/10,bdw=Math.round(d.dnN/d.total*1000)/10,bn=Math.round(d.flatN/d.total*1000)/10;
      bbar.innerHTML='<i class="bu" style="width:'+bu+'%"></i><i class="bd" style="width:'+bdw+'%"></i><i class="bn" style="width:'+bn+'%"></i>';}
    var bk=document.getElementById('sec-bk');
    if(bk) bk.innerHTML='<span><i class="iu"></i>상승 <span class="num">'+d.upN+'</span></span><span><i class="id"></i>하락 <span class="num">'+d.dnN+'</span></span><span><i class="in"></i>보합 <span class="num">'+d.flatN+'</span></span>';

    var senti=document.getElementById('sec-senti'), pct=Math.round(d.upN/d.total*100);
    var slbl=document.getElementById('sec-senti-label'), needle=document.getElementById('sec-senti-needle');
    if(senti&&slbl&&needle){senti.style.display='';slbl.innerHTML=(pct>=55?'상승 우위':pct<=45?'하락 우위':'중립')+' <b class="num">'+pct+'%</b>';needle.style.left=pct+'%';}

    var lw=document.getElementById('sec-leaders');
    if(lw) lw.innerHTML=d.leaders.map(function(r,i){var cls=r.pct>=0?'up':'dn',sign=r.pct>=0?'+':'−';
      return '<a class="srow" onclick="goStock(\''+r.code+'\')"><span class="n2">'+['①','②','③'][i]+' '+r.name+' <small class="num">'+r.code+'</small></span><span class="c '+cls+' num">'+sign+Math.abs(r.pct).toFixed(2)+'%</span></a>';
    }).join('');

    var rowsWrap=document.getElementById('sec-rows');
    if(rowsWrap) rowsWrap.innerHTML=d.rows.map(secSectorRow).join('');

    secRenderChips(document.getElementById('secsel'), key, secAllAverages(snap));
  }

  // 칩 클릭 위임 — 칩은 매번 innerHTML로 다시 그려지므로 개별 리스너 대신 문서 레벨 위임 1개만 둔다.
  document.addEventListener('click', function(e){
    var chip=e.target&&e.target.closest?e.target.closest('.secsel__i'):null;
    if(!chip) return;
    var key=chip.getAttribute('data-sector');
    if(key&&SNAP) secShowSector(SNAP, key);
  });

  // 테스트 훅 — node:vm에서 함수만 꺼내 검증한다(실제 DOM 결과는 브라우저에서 확인).
  window.__sectorScreen={
    secBuildSectorData:secBuildSectorData, secAllAverages:secAllAverages, secAsOfLabel:secAsOfLabel,
    secShowSector:secShowSector, secRenderChips:secRenderChips,
  };
```

주의: 테스트의 `secShowSector(fixtureSnap(), 'semicon')` 호출 시그니처는 `(snap, key)`이고, 실제 화면 배선(Task 3)에서는 `secShowSector(SNAP, key)`로 전역 `SNAP`을 넘겨 호출한다 — 함수 자체는 `snap`을 인자로 받아 전역에 의존하지 않는다(순수성 유지, 테스트 용이).

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test web/assets/sector-screen.test.mjs`
Expected: PASS (13 tests — Task 1의 7개 + 이번 6개)

- [ ] **Step 5: 커밋**

```bash
git add web/assets/stocks-home.js web/assets/sector-screen.test.mjs
git commit -m "feat(종목시그널): 섹터 화면 렌더 함수 추가 — 8개 섹터 전환, goStock 오타 수정

secShowSector가 각 행에 실제 종목 코드를 쓴다 — 예전 secRow/passiveRow의
goStock('000660') 하드코딩 오타(모든 행이 SK하이닉스로 이동)가 여기선
구조적으로 재발할 수 없다(행 렌더가 r.code를 직접 쓴다). 아직 화면에
배선하지 않았다 — Task 3에서 마크업과 연결한다."
```

---

## Task 3: 마크업 배선 — `index.html`·CSS·죽은 코드 제거

**Files:**
- Modify: `web/stocks/index.html`
- Modify: `web/assets/stocks-home.js`
- Modify: `web/assets/stocks-home.css`

- [ ] **Step 1: `#sector` 화면 마크업 교체**

`web/stocks/index.html`에서 `<div class="screen" id="sector">`부터 그 화면의 닫는 `</div>`까지(정확한 현재 줄 번호는 `grep -n '<div class="screen" id="sector">' web/stocks/index.html`로 재확인 — Task 5까지 거치며 줄 번호가 이동했을 수 있다) **전체를 아래로 교체**:

```html
  <div class="screen" id="sector">
    <div class="crumb"><button class="back-btn" onclick="goBack()"><svg width="7" height="12" viewBox="0 0 7 12" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 1L1 6L6 11" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></button><a href="/stocks/" onclick="event.preventDefault();go('home')">홈</a> › <a href="/stocks/" onclick="event.preventDefault();go('home')">종목</a> › 섹터 › <span id="sec-crumb-label" style="color:var(--ink)">반도체</span></div>
    <!-- 섹터 선택 칩 — secRenderChips()가 채운다. 8개 섹터 평균은 stocks-snapshot.json 실측. -->
    <div class="secsel" id="secsel" role="tablist" aria-label="섹터 선택"></div>
    <div class="grid">
      <div>
        <div class="dbox">
        <div class="shead"><div class="top">
          <div><div class="st" id="sec-title">🔧 반도체</div><div class="ss" id="sec-sub">추적 —종목 · 코스피·코스닥 · —</div></div>
          <div class="kpi"><div class="l">섹터 평균</div><div class="v num" id="sec-avg">—</div></div>
        </div>
        <div class="senti" id="sec-senti" style="display:none;"><div class="l"><span>섹터 AI 심리</span><span id="sec-senti-label">—</span></div><div class="gg"><div class="n" id="sec-senti-needle" style="left:50%"></div></div><div class="gg__s"><span>약세</span><span>중립</span><span>강세</span></div></div>
        <div class="breadth" id="sec-breadth">
          <div class="l"><span>시장폭</span><span id="sec-breadth-label">—</span></div>
          <div class="bbar" id="sec-bbar"><i class="bu" style="width:0"></i><i class="bd" style="width:0"></i><i class="bn" style="width:100%"></i></div>
          <div class="bk" id="sec-bk"><span><i class="iu"></i>상승 <span class="num">—</span></span><span><i class="id"></i>하락 <span class="num">—</span></span><span><i class="in"></i>보합 <span class="num">—</span></span></div>
        </div>
        </div>
        <div class="block">
          <div class="block__h"><span class="block__t">종목 랭킹</span><span class="block__s">등락률순</span></div>
          <div id="sec-rows"></div>
        </div>
        <!-- 패시브 쏠림 — ETF 보유비중·소진일수 실측 소스가 없다(§0, 2026-08-04 확정). 준비 중 상태만 표시. -->
        <div class="block">
          <div class="block__h"><span class="block__t"><span class="ic">🧲</span> 패시브 쏠림</span></div>
          <div class="empty-note">🧲 ETF 기계매매 노출 데이터는 아직 실측 소스가 없어요.<br>곧 추가할 예정이에요.</div>
        </div>
        </div>
      </div>
      <div>
        <div class="panel"><div class="panel__h">대장주</div>
          <div id="sec-leaders"></div>
        </div>
      </div>
    </div>
  </div>
```

바뀐 점 요약(리뷰 시 참고): `.lede` 문단 제거, "반도체 대표 ETF" 패널 제거, "다른 섹터" 패널 제거(칩이 그 역할을 대신함), 패시브 쏠림 미니블록을 준비중 안내로 축소, `#sec-more`(더보기 버튼) 제거(섹터당 최대 7종목이라 페이지네이션 불필요), 헤더 라벨을 "시총순"에서 실제 정렬 기준인 "등락률순"으로 정정, `#sec-title`/`#sec-sub`/`#sec-crumb-label` id 신설(JS가 채움).

- [ ] **Step 2: `#passive` 화면 마크업 교체**

`web/stocks/index.html`에서 `<div class="screen" id="passive">`부터 그 화면의 닫는 `</div>`까지 전체를 아래로 교체:

```html
  <div class="screen" id="passive">
    <div class="crumb"><button class="back-btn" onclick="goBack()"><svg width="7" height="12" viewBox="0 0 7 12" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 1L1 6L6 11" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg></button><a href="/stocks/" onclick="event.preventDefault();go('home')">홈</a> › <a href="/stocks/" onclick="event.preventDefault();go('home')">종목</a> › <span style="color:var(--ink)">패시브 민감주</span></div>
    <div class="phead">
      <div>
        <h1 style="color:#0C4A6E;"><span class="ic">🧲</span> 패시브 민감주</h1>
        <div class="psub">ETF 기계매매에 구조적으로 노출된 종목</div>
      </div>
    </div>
    <div class="block">
      <div class="empty-note">🧲 ETF 보유비중·거래일수 소진 데이터는 아직 실측 소스가 없어요.<br>수집이 준비되는 대로 채울게요.</div>
    </div>
  </div>
```

(`#psort-tabs`·`.sector-bias`·`#passive-tbl`·`passive-rows`·하단 안내 문구 전부 제거 — 정렬할 실데이터가 없으니 정렬 탭도 의미가 없다.)

- [ ] **Step 3: 죽은 코드 제거**

`web/assets/stocks-home.js`에서 아래를 **전부 삭제**한다:

1. `/* 섹터 종목 랭킹 — 15개 기본 + 10개씩 더보기... */` 주석부터 `secRender();` 호출 줄까지(`const SECTOR_RANK=[...]`, `let secShown=15;`, `function secRow(r){...}`, `function secRender(){...}`, `function secLoadMore(){...}`, `secRender();`) — Task 1 이전 기준 `:1183`~`:1229` 부근. `grep -n "const SECTOR_RANK=\[" web/assets/stocks-home.js`로 정확한 시작 줄을 재확인한다.
2. `/* ── 패시브 민감주 랭킹 ── */` 주석부터 `passiveRender();` 호출 줄까지(`const PASSIVE_DATA=[...]`, `let pSortKey='dov';`, `const maxDov=15.0;`, `function passiveRow(r,i){...}`, `function passiveRender(){...}`, `function passiveSort(key,el){...}`, `passiveRender();`) — `grep -n "const PASSIVE_DATA=\[" web/assets/stocks-home.js`로 정확한 시작 줄을 재확인한다.
3. `renderTops(d)` 함수 안의 `renderSectorBreadth(all);` 호출 줄 — Task 1에서 이미 정의가 삭제됐으니 이 호출부만 남아 있다. `grep -n "renderSectorBreadth(all);" web/assets/stocks-home.js`로 찾아 그 한 줄만 삭제한다.

삭제 후 `grep -n "SECTOR_RANK\|PASSIVE_DATA\|secRow\|secRender\|secLoadMore\|passiveRow\|passiveRender\|passiveSort\|renderSectorBreadth" web/assets/stocks-home.js`를 실행해 **아무 결과도 나오지 않아야** 정상이다(Task 1·2에서 새로 만든 `secShowSector`·`secBuildSectorData` 등은 이름이 겹치지 않으므로 안 걸린다).

- [ ] **Step 4: 초기 렌더 호출 연결**

`web/assets/stocks-home.js`의 `SNAP` 로드 콜백에서 `if(SNAP&&SNAP.generated_at){_asOfYmd=String(SNAP.generated_at).slice(0,10);applyAsOf();}` 줄(`grep -n "_asOfYmd=String(SNAP.generated_at)" web/assets/stocks-home.js`로 정확한 줄 재확인) **바로 다음**에 추가:

```javascript
      if(SNAP&&SNAP.stocks) secShowSector(SNAP, secActiveKey);
```

- [ ] **Step 5: CSS 추가 — 칩 스타일(프로토타입에서 그대로) + 빈 상태**

`web/assets/stocks-home.css` 맨 끝에 추가:

```css
/* 섹터 선택 칩 — docs/prototypes/2026-08-03-stocks-subnav-fullsize.html에서 확정된 디자인 그대로.
   서브탭 바(#ds-subnav, 언더라인+primary)와 시각적으로 겹치지 않도록 먹색 채움 방식을 쓴다. */
.secsel{display:flex;align-items:center;gap:6px;margin:0 0 16px;padding-bottom:2px;overflow-x:auto;scrollbar-width:none;-ms-overflow-style:none;}
.secsel::-webkit-scrollbar{display:none;}
.secsel__i{display:inline-flex;align-items:center;gap:4px;flex:none;height:32px;padding:0 10px;border-radius:999px;background:var(--canvas,#FFF);border:1px solid var(--hair,#E5E7EB);font-size:13px;font-weight:500;color:#475569;text-decoration:none;white-space:nowrap;cursor:pointer;transition:border-color .12s,background .12s;}
.secsel__i:hover{border-color:#CBD5E1;background:var(--soft,#F9FAFB);}
.secsel__i .ic{font-size:13px;line-height:1;}
.secsel__i b{font-size:13px;font-weight:700;}
.secsel__i.on{background:var(--ink,#13151A);border-color:var(--ink,#13151A);color:#fff;}
.secsel__i.on b.up{color:#FF7B7B;}
.secsel__i.on b.dn{color:#7FB0FF;}

/* 실측 소스가 없어 준비 중으로 표시하는 블록 공용 스타일. */
.empty-note{padding:24px 16px;text-align:center;font-size:12px;color:var(--muted,#5B6472);line-height:1.6;}
```

- [ ] **Step 6: 테스트 회귀 확인**

Run: `node --test web/assets/*.test.mjs`
Expected: 전체 PASS, fail 0 (Task 1 Step 5에서 기록해 둔 `renderSectorBreadth` 관련 실패가 있었다면 이제 사라져야 한다).

- [ ] **Step 7: 브라우저 확인 — 실데이터로 8개 섹터 전부**

```bash
cd web && python3 -m http.server 8899
```

`/api/*`가 로컬에 없으므로 실데이터를 로컬 파일로 얹는다:

```bash
mkdir -p web/api
curl -s https://doubleshot.space/api/signals -o web/api/signals
curl -s https://doubleshot.space/api/vol-top -o web/api/vol-top
```

`mcp__Claude_Browser__preview_start`로 `http://localhost:8899/stocks/` 열고 확인:

1. 서브탭 "섹터" 클릭 → 칩 8개가 뜬다. 첫 칩(활성)이 "반도체"이고 먹색 채움, 텍스트·언더라인 방식인 서브탭과 시각적으로 구분된다.
2. 칩을 하나씩 눌러 8개 섹터를 전부 순회 — 매번 종목 랭킹·대장주·섹터 평균·시장폭이 바뀐다. 클릭할 때마다 주소창 해시는 `#sector`로 유지된다(페이지 이동 없음, in-page 전환).
3. 종목 랭킹의 각 행을 하나씩 눌러 각기 다른 종목 상세로 이동하는지 확인(`goStock` 버그 재발 여부의 실측 확인) — 최소 3개 다른 섹터에서 각 2행씩 확인.
4. "패시브 쏠림" 블록에 "🧲 ETF 기계매매 노출 데이터는 아직 실측 소스가 없어요" 문구만 있고 가짜 수치가 없다.
5. `#passive` 화면(서브탭엔 없음, 홈 "더 보기"에서 진입)도 준비 중 안내만 뜨고 예전 9행 표가 없다.
6. `read_console_messages` 에러 0건.
7. `resize_window` 375px — 칩 행이 가로 스크롤되고 페이지 전체 가로 스크롤은 생기지 않는다.

```bash
rm -rf web/api
```

서버는 확인 후 종료한다.

- [ ] **Step 8: 커밋**

```bash
git add web/stocks/index.html web/assets/stocks-home.js web/assets/stocks-home.css
git commit -m "feat(종목시그널): 섹터 화면을 8개 섹터 실데이터 전환으로 배선

#sector가 반도체 고정에서 벗어난다. 섹터 평균·시장폭·랭킹·대장주 전부
stocks-snapshot.json 단일 소스(§0 정합성, §24 시점 불일치 방지 — vol-top
라이브와 안 섞는다). 실측 소스 없는 패시브 쏠림·ETF 관련 블록은 제거하고
준비 중 안내로 대체한다."
```

---

## Task 4: 전체 회귀 확인·문서 갱신

- [ ] **Step 1: 전체 테스트**

Run: `node --test web/assets/*.test.mjs && node --test api/*.test.mjs && python3 -m pytest scripts/ -q`
Expected: 전부 PASS.

- [ ] **Step 2: 오염 여부 확인**

Run: `git status --short`
Expected: 이번 작업에서 커밋한 파일 외에 변경 없음. 특히 `web/data/`·`web/briefings/`·`web/api/`(Step 7에서 만든 임시 디렉터리)에 흔적이 없어야 한다.

- [ ] **Step 3: 컨텍스트 노트 갱신**

`docs/plans/2026-08-02-stockripple-features/context-notes.md`의 서브탭 IA 절 끝에 추가(정확한 삽입 지점은 `grep -n "이번에 고치지 않고 기록만 한" docs/plans/2026-08-02-stockripple-features/context-notes.md`로 찾는다 — 그 문단을 아래로 교체):

```markdown
- **이번에 고치지 않고 기록만 한 라이브 버그 4건 — 2026-08-04에 착수, 상태 갱신**: ① 섹터 전환 UI 부재 → **해결**(`docs/superpowers/plans/2026-08-04-sector-screen-real-data.md`, 8개 섹터 칩 전환) ② `goStock('000660')` 오타 → **해결**(같은 작업, 각 행이 실제 코드 사용) ③ 하드코딩 리터럴(28종목 랭킹·패시브 쏠림) → **패시브는 준비 중으로 전환, 수집 스크립트는 별건으로 미룸**. 조사 중 같은 계열의 하드코딩 2건을 추가로 발견해 함께 처리: "반도체 대표 ETF"(`+2.8%` 고정)와 `.lede` 서사 문단 — 둘 다 실측 소스 없어 제거 ④ `stocks-snapshot.json` vs `/api/vol-top` 불일치 → **버그가 아니라 신선도 계층 차이로 확인**. `#sector` 화면을 스냅샷 단일 소스로 통일해 한 화면에 두 소스를 섞지 않는 것으로 해소.
```

```bash
git add docs/plans/2026-08-02-stockripple-features/context-notes.md
git commit -m "docs(섹터화면): 실데이터 전환 작업 완료 상태로 컨텍스트 노트 갱신"
```

---

## 자체 점검 결과 (writing-plans 셀프 리뷰)

- **스펙 커버리지**: 사용자가 확정한 4가지(스냅샷 단일화·패시브 비우기·대표 ETF 제거·lede 제거) 전부 Task 3에 반영됨. 원래 4건 버그(①~④) 전부 Task 1~3에서 다뤄짐.
- **플레이스홀더 스캔**: "TBD"·"나중에"·"적절히" 패턴 없음. 모든 코드 스텝에 완전한 코드 포함.
- **타입/이름 일관성**: `secBuildSectorData(snap, key)`·`secAllAverages(snap)`·`secAsOfLabel(snap)`·`secShowSector(snap, key)`·`secRenderChips(box, activeKey, allAvgs)` 시그니처가 Task 1~3 전체에서 동일하게 쓰임. `SECTOR_LEADERS`·`SECTOR_ICONS`는 Task 1에서 선언, Task 2에서 참조. `secActiveKey`는 Task 2에서 선언, Task 3의 부팅 호출에서 참조.
- **한 가지 남겨둔 판단**: `.secsel` 칩의 `role="tablist"`/`role="tab"`은 실제로는 화면 전환이 아닌 같은 화면 내 필터에 가깝다(서브탭 리뷰에서 `aria-current="page"` vs `"location"` 논쟁과 유사한 종류). ARIA `tab` 롤이 최선인지는 이번 범위에서 확정하지 않고 프로토타입 그대로 가져왔다 — 실사용성에 문제 없으면 그대로 두고, 코드 품질 리뷰에서 이견이 나오면 그때 판단한다.
