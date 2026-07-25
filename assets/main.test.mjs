// main.js 순수 함수 회귀 테스트 — node:vm 샌드박스에서 실제 프로덕션 파일을 로드해 검증
//
// 왜 이런 방식인가
//   main.js는 브라우저용 IIFE(<script src>)라 import할 수 없고, 내부 함수는 클로저에
//   갇혀 있다. 순수 함수만 별 파일로 복제하면 사본이 원본과 어긋나므로(그게 §20류 사고의
//   전형), 실제 main.js를 최소 DOM 스텁과 함께 vm에서 실행하고 window.__dsTestables로
//   내부 함수를 꺼내 테스트한다.
//
// 스텁 범위
//   main.js는 로드 시점에 initLiveMarketPanel·initNowBand·initSidebarSignals를
//   즉시 호출하는데, 모두 `if (!el) return`으로 시작한다.
//   따라서 getElementById/querySelector가 null만 돌려주면 조용히 빠져나온다.
//
// 실행: node --test web/assets/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));

/** main.js를 스텁 환경에서 실행하고 내부 순수 함수를 꺼낸다. */
function loadMainJs({ now } = {}) {
  const src = readFileSync(join(HERE, 'main.js'), 'utf8');

  const noop = () => {};
  const el = {
    classList: { replace: noop, add: noop, remove: noop, toggle: noop, contains: () => false },
    dataset: {},
    style: {},
    addEventListener: noop,
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  const doc = {
    documentElement: el,
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: noop,
    createElement: () => ({ ...el, innerHTML: '', appendChild: noop }),
    body: { ...el, appendChild: noop },
  };
  const store = new Map();
  const sandbox = {
    document: doc,
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    },
    sessionStorage: {
      getItem: () => null, setItem: noop, removeItem: noop,
    },
    location: { pathname: '/briefings/2026-07-24/kospi/', search: '', href: '' },
    navigator: { userAgent: 'node' },
    fetch: () => Promise.reject(new Error('테스트에서는 네트워크를 쓰지 않는다')),
    AbortSignal: { timeout: () => null },
    // window.addEventListener('load', ...) — main.js가 로드 시점에 등록한다
    addEventListener: noop,
    removeEventListener: noop,
    setTimeout: noop,
    setInterval: noop,
    clearInterval: noop,
    requestAnimationFrame: noop,
    console: { log: noop, warn: noop, error: noop },
    Date: now ? makeFrozenDate(now) : Date,
  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.globalThis = sandbox;

  runInContext(src, createContext(sandbox), { filename: 'main.js' });

  const t = sandbox.window.__dsTestables;
  assert.ok(t, 'window.__dsTestables가 없다 — main.js의 테스트 훅이 제거됐는지 확인할 것');
  return t;
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

// ─────────────────────────────────────────────────────────────────────────────
// 로드 자체 (회귀 방지의 핵심 — 고아 참조·구문 오류가 여기서 터진다)
// ─────────────────────────────────────────────────────────────────────────────

test('main.js가 DOM 없는 환경에서 예외 없이 로드된다', () => {
  const t = loadMainJs();
  assert.equal(typeof t.kstNow, 'function');
  assert.equal(typeof t.kstDateStr, 'function');
  assert.equal(typeof t.kstMinsOfDay, 'function');
  assert.equal(typeof t.trustRelTime, 'function');
});

// ─────────────────────────────────────────────────────────────────────────────
// kstDateStr — KST 날짜 문자열
// ─────────────────────────────────────────────────────────────────────────────

test('kstDateStr: UTC 자정 직전도 KST로는 다음날이다', () => {
  // 2026-07-24T15:30:00Z = 2026-07-25 00:30 KST
  const t = loadMainJs({ now: Date.parse('2026-07-24T15:30:00Z') });
  assert.equal(t.kstDateStr(), '2026-07-25');
});

test('kstDateStr: UTC 같은 날이라도 KST 09시 이전이면 같은 날', () => {
  // 2026-07-24T00:30:00Z = 2026-07-24 09:30 KST
  const t = loadMainJs({ now: Date.parse('2026-07-24T00:30:00Z') });
  assert.equal(t.kstDateStr(), '2026-07-24');
});

test('kstDateStr: 월·일 한 자리는 0으로 채운다', () => {
  const t = loadMainJs({ now: Date.parse('2026-01-05T01:00:00Z') });
  assert.equal(t.kstDateStr(), '2026-01-05');
});

test('kstDateStr: 연말 경계 — UTC 12/31 저녁은 KST 1/1', () => {
  const t = loadMainJs({ now: Date.parse('2026-12-31T15:00:00Z') });
  assert.equal(t.kstDateStr(), '2027-01-01');
});

test('kstDateStr: 인자를 주면 그 시각 기준으로 계산한다', () => {
  const t = loadMainJs();
  const d = new Date(Date.parse('2026-03-01T00:00:00Z') + 9 * 3600 * 1000);
  assert.equal(t.kstDateStr(d), '2026-03-01');
});

// ─────────────────────────────────────────────────────────────────────────────
// kstMinsOfDay — 장중 판정에 쓰이는 분
// ─────────────────────────────────────────────────────────────────────────────

test('kstMinsOfDay: 09:00 KST는 540분 (장 시작)', () => {
  const t = loadMainJs({ now: Date.parse('2026-07-24T00:00:00Z') });
  assert.equal(t.kstMinsOfDay(), 540);
});

test('kstMinsOfDay: 15:30 KST는 930분 (장 마감)', () => {
  const t = loadMainJs({ now: Date.parse('2026-07-24T06:30:00Z') });
  assert.equal(t.kstMinsOfDay(), 930);
});

test('kstMinsOfDay: 08:50 KST는 530분 (스코어보드 노출 시작)', () => {
  const t = loadMainJs({ now: Date.parse('2026-07-23T23:50:00Z') });
  assert.equal(t.kstMinsOfDay(), 530);
});

// ─────────────────────────────────────────────────────────────────────────────
// trustRelTime — 신뢰 스트립 상대 시각 + stale 판정
// ─────────────────────────────────────────────────────────────────────────────

const NOW = Date.parse('2026-07-25T12:00:00Z');
const ago = (ms) => new Date(NOW - ms).toISOString();

test('trustRelTime: 1분 미만은 "방금"', () => {
  const t = loadMainJs({ now: NOW });
  assert.equal(t.trustRelTime(ago(30 * 1000)).text, '방금');
});

test('trustRelTime: 분 → 시간 → 일 경계', () => {
  const t = loadMainJs({ now: NOW });
  assert.equal(t.trustRelTime(ago(59 * 60 * 1000)).text, '59분 전');
  assert.equal(t.trustRelTime(ago(60 * 60 * 1000)).text, '1시간 전');
  assert.equal(t.trustRelTime(ago(23.5 * 3600 * 1000)).text, '23시간 전');
  assert.equal(t.trustRelTime(ago(25 * 3600 * 1000)).text, '1일 전');
});

test('trustRelTime: hours는 구간에 상관없이 실수 경과시간이다', () => {
  // 예전엔 분 구간에서 mins/60(실수), 시간 구간에서 정수를 반환해
  // stale 판정 입력이 구간마다 달랐다.
  const t = loadMainJs({ now: NOW });
  assert.ok(Math.abs(t.trustRelTime(ago(30 * 60 * 1000)).hours - 0.5) < 1e-9);
  assert.ok(Math.abs(t.trustRelTime(ago(90 * 60 * 1000)).hours - 1.5) < 1e-9);
});

test('trustRelTime: 미래 시각은 null (신뢰하지 않는다)', () => {
  const t = loadMainJs({ now: NOW });
  assert.equal(t.trustRelTime(new Date(NOW + 3600 * 1000).toISOString()), null);
});

test('trustRelTime: 파싱 불가 입력은 모두 null', () => {
  const t = loadMainJs({ now: NOW });
  for (const bad of ['not-a-date', '', null, undefined, {}, []]) {
    assert.equal(t.trustRelTime(bad), null, `입력: ${JSON.stringify(bad)}`);
  }
});

test('trustRelTime: epoch 0은 파싱 실패와 구분된다', () => {
  // 예전 구현은 `!t`로 검사해 epoch 0(1970-01-01)을 파싱 실패로 취급했다.
  const t = loadMainJs({ now: NOW });
  const r = t.trustRelTime(new Date(0).toISOString());
  assert.ok(r, 'epoch 0은 유효한 시각이다');
  assert.ok(r.hours > 400000, '1970년이면 매우 오래된 값으로 나와야 한다');
});

// ─────────────────────────────────────────────────────────────────────────────
// stale 임계치 — 신뢰 스트립 숨김 정책
// ─────────────────────────────────────────────────────────────────────────────

test('TRUST_STALE_HOURS는 채점 잡 토→화 공백(72h)보다 넉넉하다', () => {
  // 채점은 평일(화~토) 09:10 — 토요일 실행 후 다음은 화요일이라 정상 공백이 72h다.
  // 공휴일 하루를 더 얹어도 살아남아야 오탐이 없다.
  const t = loadMainJs();
  assert.ok(t.TRUST_STALE_HOURS > 72, '정상 주말 공백을 죽은 잡으로 오판하면 안 된다');
  assert.equal(t.TRUST_STALE_HOURS, 96);
});

test('stale 경계: 95h는 표시 대상, 97h는 숨김 대상', () => {
  const t = loadMainJs({ now: NOW });
  assert.ok(t.trustRelTime(ago(95 * 3600 * 1000)).hours < t.TRUST_STALE_HOURS);
  assert.ok(t.trustRelTime(ago(97 * 3600 * 1000)).hours > t.TRUST_STALE_HOURS);
});
