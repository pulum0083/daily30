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

/**
 * id별로 실제 엘리먼트를 돌려주는 문서 스텁. 렌더 함수가 innerHTML/textContent를 쓰는 걸 검증한다.
 *
 * `els`는 Proxy다 — 일부 렌더 함수(secRenderChips)는 엘리먼트를 내부에서 getElementById로
 * 찾지 않고 인자로 직접 받으므로, 테스트가 `document.getElementById(id)`를 거치지 않고
 * `els[id]`로 먼저 접근하는 경우가 있다(etf-signal.test.mjs의 Map 사전등록 패턴과 달리
 * id를 미리 나열하지 않는다). 평범한 객체 + 지연 생성 클로저였다면 이 경우 `els[id]`가
 * `getElementById`와 별개로 undefined를 반환해 같은 id가 서로 다른 엘리먼트로 갈리는
 * 문제가 있었다 — Proxy로 두 경로가 항상 같은 엘리먼트를 공유하도록 보장한다.
 */
function mkDoc() {
  const store = {};
  const els = new Proxy(store, {
    get(target, id) {
      if (typeof id !== 'string') return target[id];
      if (!target[id]) target[id] = mkEl();
      return target[id];
    },
  });
  return {
    els,
    doc: {
      readyState:'complete',
      getElementById: (id) => els[id],
      querySelector: () => mkEl(), querySelectorAll: () => [],
      createElement:()=>mkEl(), addEventListener:noop,
      body:mkEl(), documentElement:mkEl(), head:mkEl(),
    },
  };
}

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
  // Array.from으로 vm 컨텍스트 배열을 호스트 realm 배열로 재구성한다 — assert.deepEqual(=deepStrictEqual)이
  // 구조는 같아도 realm이 다르면 reference-equal 실패로 오판한다(ds-subnav.test.mjs와 동일 패턴).
  assert.deepEqual(Array.from(d.rows.map((r) => r.code)), ['000660', '042700', '005930']);
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
  assert.deepEqual(Array.from(d.leaders.map((r) => r.code)), ['005930', '000660', '042700']);
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

test('secRenderChips — 항상 평균 내림차순, 활성 섹터를 앞으로 보내지 않는다', () => {
  const { doc, els } = mkDoc();
  const { secRenderChips } = load(doc);
  const avgs = { semicon:{avg:-4.1,label:'반도체'}, auto:{avg:1.5,label:'자동차'}, bio:{avg:-0.1,label:'바이오'} };
  secRenderChips(els['secsel'], 'semicon', avgs);
  const order = [...els['secsel'].innerHTML.matchAll(/data-sector="([a-z]+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, ['auto', 'bio', 'semicon']); // 순수 평균 내림차순: 1.5 > -0.1 > -4.1
});

// Regression: 클릭할 때마다 칩 순서가 바뀌어 메뉴가 들썩였다 — 활성 섹터를 바꿔도
// 같은 데이터면 배열 순서가 완전히 동일해야 한다(강조만 이동, 위치는 고정).
test('secRenderChips — 활성 섹터가 바뀌어도 칩 순서 자체는 고정이다', () => {
  const avgs = { semicon:{avg:-4.1,label:'반도체'}, auto:{avg:1.5,label:'자동차'}, bio:{avg:-0.1,label:'바이오'} };
  const { doc: doc1, els: els1 } = mkDoc();
  const { secRenderChips: r1 } = load(doc1);
  r1(els1['secsel'], 'semicon', avgs);
  const orderWhenSemiconActive = [...els1['secsel'].innerHTML.matchAll(/data-sector="([a-z]+)"/g)].map((m) => m[1]);

  const { doc: doc2, els: els2 } = mkDoc();
  const { secRenderChips: r2 } = load(doc2);
  r2(els2['secsel'], 'bio', avgs);
  const orderWhenBioActive = [...els2['secsel'].innerHTML.matchAll(/data-sector="([a-z]+)"/g)].map((m) => m[1]);

  assert.deepEqual(orderWhenSemiconActive, orderWhenBioActive, '활성 섹터만 바뀌었는데 칩 위치가 달라지면 안 된다');
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

// Regression: QA-001 — 같은 종목이 종목 랭킹은 +29.9%, 대장주는 +29.95%로 자릿수가 갈렸다
// Found by /qa on 2026-08-04
// Report: .gstack/qa-reports/qa-report-localhost-2026-08-04.md
test('secShowSector — 같은 종목은 랭킹·대장주에서 동일한 자릿수로 표기된다', () => {
  const { doc, els } = mkDoc();
  const { secShowSector } = load(doc);
  secShowSector(fixtureSnap(), 'semicon');

  // 000660(SK하이닉스, +3.4)은 랭킹 1위이자 대장주 ②라 한 화면에 두 번 나온다.
  const rowPct = els['sec-rows'].innerHTML.match(/000660[\s\S]*?([+−]\d+\.\d+)%/)[1];
  const leadPct = els['sec-leaders'].innerHTML.match(/000660[\s\S]*?([+−]\d+\.\d+)%/)[1];
  assert.equal(rowPct, leadPct, `같은 종목인데 표기가 다르다: 랭킹 ${rowPct} vs 대장주 ${leadPct}`);

  // 섹터 평균과도 자릿수를 맞춘다(전부 소수점 2자리).
  const decimals = (s) => s.split('.')[1].length;
  assert.equal(decimals(rowPct), 2, `랭킹 행은 소수점 2자리여야 하는데: ${rowPct}`);
  assert.equal(decimals(els['sec-avg'].textContent.replace('%', '')), 2);
});
