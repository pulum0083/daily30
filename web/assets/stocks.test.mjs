// stocks.js 상세 페이지 폴링 루프 회귀 테스트 — 2026-08-16 Vercel 차단 사고 방지
//
// 왜 이런 방식인가
//   stocks.js는 브라우저용 IIFE(<script src defer>)라 import할 수 없고, 폴링 루프는
//   각 IIFE의 클로저 안에 있다. 순수 함수를 별 파일로 복제하면 사본이 원본과 어긋나므로
//   (SERVICE_RULES §20류 사고의 전형), 실제 파일을 최소 DOM 스텁과 함께 vm에서 실행하고
//   등록된 인터벌·리스너 콜백을 훅으로 수집해 직접 호출한다. stocks-home.test.mjs와 같은 패턴.
//
// 검증 범위
//   상세 페이지의 두 폴링 루프가 백그라운드 탭에서 서버리스 함수를 깨우지 않는지.
//     · peers(20초) — /api/stocks-live, 시장 시간 게이트 없이 24시간
//     · night-px(30초) — /api/hl-night, 장 마감 구간 내내(평일 17.5시간 + 주말 종일)
//
// 실행: node --test web/assets/stocks.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const noop = () => {};

/** 최소 엘리먼트 스텁 — attrs로 getAttribute 응답을, kids로 querySelectorAll 응답을 지정한다. */
function mkEl(attrs = {}, kids = []) {
  const e = {
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false, replace: noop },
    dataset: {}, style: {}, children: [], innerHTML: '', textContent: '', value: '', hidden: false,
    addEventListener: noop, removeEventListener: noop, appendChild: noop, insertBefore: noop,
    setAttribute: noop, getAttribute: (k) => (k in attrs ? attrs[k] : null),
    removeAttribute: noop, remove: noop, focus: noop,
    closest: () => null, contains: () => false,
    getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0 }),
    querySelector: () => null, querySelectorAll: () => kids,
    nextElementSibling: null, previousElementSibling: null,
  };
  e.parentNode = { insertBefore: noop, removeChild: noop, appendChild: noop };
  return e;
}

function makeFrozenDate(fixedMs) {
  return class FrozenDate extends Date {
    constructor(...args) {
      if (args.length === 0) super(fixedMs);
      else super(...args);
    }
    static now() { return fixedMs; }
  };
}

/** KST 벽시계 문자열 → UTC epoch ms */
function kst(s) {
  return Date.parse(s + 'Z') - 9 * 3600 * 1000;
}

/** stocks.js를 스텁 환경에서 실행하고 인터벌·리스너·fetch 기록을 돌려준다. */
function loadStocks({ now } = {}) {
  const src = readFileSync(join(HERE, 'stocks.js'), 'utf8');
  const intervals = [];
  const docListeners = [];
  const fetched = [];

  // 두 루프는 각각 자기 앵커 엘리먼트가 없으면 즉시 return 한다 — 스텁을 안 채우면
  // 루프가 등록조차 되지 않아 테스트가 무의미하게 통과한다.
  const peerRows = ['NVDA', 'AMD'].map((t) => mkEl({ 'data-ticker': t }));
  const seeded = {
    'peers-panel': mkEl({}, peerRows),
    'night-px': mkEl({ 'data-code': '005930', 'data-close': '71000' }),
  };
  const els = new Map(Object.entries(seeded));

  const doc = {
    documentElement: mkEl(), head: mkEl(), body: mkEl(),
    hidden: false,
    getElementById: (id) => { if (!els.has(id)) els.set(id, mkEl()); return els.get(id); },
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener: (ev, fn) => { docListeners.push({ ev, fn }); },
    createElement: () => mkEl(), createTextNode: () => ({}),
  };

  const sandbox = {
    document: doc,
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    sessionStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    location: { pathname: '/stocks/005930/', search: '', hash: '', href: '' },
    navigator: { userAgent: 'node' },
    history: { pushState: noop, replaceState: noop },
    fetch: (url) => { fetched.push(String(url)); return Promise.reject(new Error('테스트 스텁')); },
    AbortSignal: { timeout: () => null },
    addEventListener: noop, removeEventListener: noop, scrollTo: noop,
    setTimeout: noop, setInterval: (fn, ms) => { intervals.push({ fn, ms }); },
    clearInterval: noop, clearTimeout: noop, requestAnimationFrame: noop,
    console: { log: noop, warn: noop, error: noop },
    matchMedia: () => ({ matches: false, addEventListener: noop }),
    getComputedStyle: () => ({}),
    Intl,
    Date: now ? makeFrozenDate(now) : Date,
  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.globalThis = sandbox;

  runInContext(src, createContext(sandbox), { filename: 'stocks.js' });

  return {
    win: sandbox.window,
    intervals,
    apiCalls: () => fetched.filter((u) => u.startsWith('/api/')),
    reset: () => { fetched.length = 0; },
    setHidden: (v) => { doc.hidden = v; },
    tickEvery: (ms) => {
      const it = intervals.find((i) => i.ms === ms);
      assert.ok(it, `${ms}ms 폴링 인터벌이 등록되지 않았다 — 루프가 사라졌거나 주기가 바뀌었다`);
      it.fn();
    },
    fireVisibilityChange: () => {
      const ls = docListeners.filter((l) => l.ev === 'visibilitychange');
      assert.ok(ls.length, 'visibilitychange 리스너가 없다 — 탭 복귀 시 즉시 복구되지 않는다');
      ls.forEach((l) => l.fn());
    },
  };
}

// 화요일 저녁 20:00 KST — 코스피 마감 후라 night-px가 폴링하는 구간이고,
// peers(미국 사이드바)는 시간과 무관하게 폴링한다. 두 루프를 한 시점에서 같이 본다.
const KR_CLOSED_EVENING = kst('2026-07-28T20:00:00');

test('stocks.js가 스텁 DOM 환경에서 예외 없이 로드된다', () => {
  const s = loadStocks({ now: KR_CLOSED_EVENING });
  assert.ok(s.intervals.length > 0, '인터벌이 하나도 등록되지 않았다 — 스텁이 루프 진입을 막고 있다');
});

for (const [label, ms] of [['peers(20초)', 20000], ['night-px(30초)', 30000]]) {
  test(`${label}: 탭이 보이지 않으면 API를 호출하지 않는다`, () => {
    const s = loadStocks({ now: KR_CLOSED_EVENING });
    s.reset();               // 로드 직후 1회 폴링은 정상 동작이므로 제외
    s.setHidden(true);
    s.tickEvery(ms);
    assert.deepEqual(s.apiCalls(), [], `${label}이 백그라운드 탭에서 서버리스 함수를 깨웠다`);
  });

  test(`${label}: 탭이 보이면 평소대로 API를 호출한다 (과잉 차단 방지)`, () => {
    const s = loadStocks({ now: KR_CLOSED_EVENING });
    s.reset();
    s.setHidden(false);
    s.tickEvery(ms);
    assert.equal(s.apiCalls().length, 1, `${label}이 보이는 탭에서도 멈췄다 — 가드가 과하다`);
  });
}

test('탭 복귀 시 두 루프 모두 다음 인터벌을 기다리지 않고 즉시 받아온다', () => {
  const s = loadStocks({ now: KR_CLOSED_EVENING });
  s.setHidden(true);
  s.tickEvery(20000);
  s.tickEvery(30000);
  s.reset();
  s.setHidden(false);
  s.fireVisibilityChange();
  assert.equal(s.apiCalls().length, 2, '복귀 직후 최대 30초간 낡은 값이 남는다');
});
