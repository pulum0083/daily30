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
