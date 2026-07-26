// stocks-home.js 국면 판정(__layoutPhase) 회귀 테스트 — node:vm 샌드박스에서 실제 프로덕션 파일을 로드해 검증
//
// 왜 이런 방식인가
//   stocks-home.js는 브라우저용 IIFE(<script src defer>)라 import할 수 없고, 국면 판정은
//   섹션 재배치 IIFE의 클로저 안에 있다. 순수 함수를 별 파일로 복제하면 사본이 원본과
//   어긋나므로(SERVICE_RULES §20류 사고의 전형), 실제 파일을 최소 DOM 스텁과 함께 vm에서
//   실행하고 window.__layoutPhase로 꺼내 테스트한다. main.test.mjs와 같은 패턴.
//
// 검증 범위
//   국면 판정(day / us_open / quiet)만. 실제 DOM 이동 순서는 스텁 환경에서 확인할 수 없어
//   브라우저에서 별도 확인한다.
//
// 실행: node --test web/assets/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));

const noop = () => {};

/** 최소 엘리먼트 스텁 — stocks-home.js는 로드 시점에 다수의 DOM을 만지므로 null이 아닌 객체를 돌려줘야 한다. */
function mkEl() {
  const e = {
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false, replace: noop },
    dataset: {}, style: {}, children: [], innerHTML: '', textContent: '', value: '', hidden: false,
    addEventListener: noop, removeEventListener: noop, appendChild: noop, insertBefore: noop,
    setAttribute: noop, getAttribute: () => null, removeAttribute: noop, remove: noop, focus: noop,
    closest: () => null, contains: () => false,
    getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0 }),
    querySelector: () => null, querySelectorAll: () => [],
    nextElementSibling: null, previousElementSibling: null,
  };
  e.parentNode = { insertBefore: noop, removeChild: noop, appendChild: noop };
  return e;
}

/** Date.now()를 고정한 Date 서브클래스 — 시각 의존 로직을 결정론적으로 만든다. */
function makeFrozenDate(fixedMs) {
  return class FrozenDate extends Date {
    constructor(...args) {
      if (args.length === 0) super(fixedMs);
      else super(...args);
    }
    static now() { return fixedMs; }
  };
}

/** stocks-home.js를 스텁 환경에서 실행하고 국면 판정 함수를 꺼낸다. */
function loadStocksHome({ now } = {}) {
  const src = readFileSync(join(HERE, 'stocks-home.js'), 'utf8');
  const doc = {
    documentElement: mkEl(), head: mkEl(), body: mkEl(),
    getElementById: () => mkEl(), querySelector: () => mkEl(), querySelectorAll: () => [],
    addEventListener: noop, createElement: () => mkEl(), createTextNode: () => ({}),
  };
  const sandbox = {
    document: doc,
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    sessionStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    location: { pathname: '/stocks/', search: '', hash: '', href: '' },
    navigator: { userAgent: 'node' },
    fetch: () => Promise.reject(new Error('테스트에서는 네트워크를 쓰지 않는다')),
    AbortSignal: { timeout: () => null },
    addEventListener: noop, removeEventListener: noop,
    setTimeout: noop, setInterval: noop, clearInterval: noop, clearTimeout: noop,
    requestAnimationFrame: noop,
    console: { log: noop, warn: noop, error: noop },
    matchMedia: () => ({ matches: false, addEventListener: noop }),
    getComputedStyle: () => ({}),
    Intl,
    Date: now ? makeFrozenDate(now) : Date,
  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.globalThis = sandbox;

  runInContext(src, createContext(sandbox), { filename: 'stocks-home.js' });

  const fn = sandbox.window.__layoutPhase;
  assert.ok(fn, 'window.__layoutPhase가 없다 — 섹션 재배치 IIFE의 테스트 훅이 제거됐는지 확인할 것');
  return fn;
}

/** KST 벽시계 문자열 → UTC epoch ms */
function kst(s) {
  return Date.parse(s + 'Z') - 9 * 3600 * 1000;
}

/** 해당 KST 시각의 국면 */
function phaseAt(s) {
  return loadStocksHome({ now: kst(s) })();
}

// ─────────────────────────────────────────────────────────────────────────────
// 로드 자체 (회귀 방지의 핵심 — 고아 참조·구문 오류가 여기서 터진다)
// ─────────────────────────────────────────────────────────────────────────────

test('stocks-home.js가 스텁 DOM 환경에서 예외 없이 로드된다', () => {
  assert.equal(typeof loadStocksHome(), 'function');
});

// ─────────────────────────────────────────────────────────────────────────────
// day — 한국 거래일 07:30~17:00. 코스피 실시간이 주인공이라 원래 순서를 유지한다.
// ─────────────────────────────────────────────────────────────────────────────

test('day: 평일 장중', () => {
  assert.equal(phaseAt('2026-07-28T10:00:00'), 'day');
});

test('day: 코스피 개장 전이라도 07:30을 넘겼으면 day', () => {
  assert.equal(phaseAt('2026-07-28T07:31:00'), 'day');
});

test('day: 마감 직후 낮(16:00)도 아직 day', () => {
  assert.equal(phaseAt('2026-07-28T16:00:00'), 'day');
});

test('day 경계: 07:29는 아직 quiet, 07:31부터 day', () => {
  assert.equal(phaseAt('2026-07-29T07:29:00'), 'quiet');
  assert.equal(phaseAt('2026-07-29T07:31:00'), 'day');
});

test('day 경계: 17:00부터는 day가 아니다', () => {
  assert.equal(phaseAt('2026-07-28T16:59:00'), 'day');
  assert.notEqual(phaseAt('2026-07-28T17:01:00'), 'day');
});

// ─────────────────────────────────────────────────────────────────────────────
// us_open — 미국 정규장(ET 09:30~16:00). 밤사이 미국 반도체가 10초 갱신되는 유일한 구간.
// ─────────────────────────────────────────────────────────────────────────────

test('us_open: 여름(EDT) 22:31 KST = ET 09:31', () => {
  assert.equal(phaseAt('2026-07-28T22:31:00'), 'us_open');
});

test('us_open: 정규장 막판 05:00 직전', () => {
  assert.equal(phaseAt('2026-07-29T04:59:00'), 'us_open');
});

test('us_open 경계: 개장 2분 전(22:29)은 아직 quiet', () => {
  assert.equal(phaseAt('2026-07-28T22:29:00'), 'quiet');
});

test('us_open 경계: 마감 직후(05:01)는 애프터장 → quiet', () => {
  assert.equal(phaseAt('2026-07-29T05:01:00'), 'quiet');
});

test('us_open: 토요일 새벽은 금요일 미국 정규장이다 (주말이라고 quiet로 묶으면 안 된다)', () => {
  // KST 토 02:00 = ET 금 13:00 — 미국장이 열려 있다.
  assert.equal(phaseAt('2026-08-01T02:00:00'), 'us_open');
});

test('서머타임: 겨울(EST)엔 22:31이 아직 개장 전, 23:31이 정규장', () => {
  // KST 고정 시각(22:30)으로 판정하면 반년마다 틀린다. 뉴욕 현지 시각으로 판정해야 한다.
  assert.equal(phaseAt('2026-12-15T22:31:00'), 'quiet');
  assert.equal(phaseAt('2026-12-15T23:31:00'), 'us_open');
});

// ─────────────────────────────────────────────────────────────────────────────
// quiet — 그 외 전부. HL 24h 추정가만 두껍게 살아있어 그것이 히어로가 된다.
// ─────────────────────────────────────────────────────────────────────────────

test('quiet: 평일 저녁(프리장) — 거래가 얇아 히어로로 올리지 않는다', () => {
  assert.equal(phaseAt('2026-07-28T18:00:00'), 'quiet');
});

test('quiet: 평일 애프터장~개장 전 새벽', () => {
  assert.equal(phaseAt('2026-07-29T06:00:00'), 'quiet');
});

test('quiet: 주말 종일', () => {
  assert.equal(phaseAt('2026-08-01T10:00:00'), 'quiet'); // 토
  assert.equal(phaseAt('2026-08-02T15:00:00'), 'quiet'); // 일
});

test('quiet: 토요일 저녁 — 미국장도 닫혀 완전 정지', () => {
  assert.equal(phaseAt('2026-08-01T06:00:00'), 'quiet');
});

test('quiet: 월요일 07:30 이전 (주말이 이어지는 구간)', () => {
  assert.equal(phaseAt('2026-08-03T07:00:00'), 'quiet');
});
