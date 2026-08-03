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

/** stocks-home.js를 스텁 환경에서 실행하고 window(샌드박스)를 돌려준다. */
function loadWindow({ now } = {}) {
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
  return sandbox.window;
}

/** stocks-home.js를 스텁 환경에서 실행하고 국면 판정 함수를 꺼낸다. */
function loadStocksHome({ now } = {}) {
  const fn = loadWindow({ now }).__layoutPhase;
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

// ─────────────────────────────────────────────────────────────────────────────
// 장중 곡선 세션 검증 (__wmIsTodaySession)
//
// 2026-07-31 실사고: /api/intraday는 네이버 피드의 '최신 세션'을 돌려준다 — 오늘 첫 1분봉이
// 생기기 전(개장 전·공휴일)엔 그게 전 거래일이다. 허브 위젯이 이걸 검증 없이 받아
// buf에 채운 뒤, 09:00부터 라이브 폴러가 오늘 실측을 같은 버퍼에 이어붙였다.
// buft의 시각이 09:00→15:30(어제) 후 09:00(오늘)으로 되감기며 곡선이 대각선으로 깨지고,
// 당일 레인지 저점이 전일 저가(202,750)로 오염됐다. 상세 페이지(stocks.js)는 같은 API에
// d.date===todayKST() 검증이 있어 멀쩡했다 — 같은 데이터의 이중 소비처 중 한쪽만 검증한
// SERVICE_RULES §20·§30 패턴.
// ─────────────────────────────────────────────────────────────────────────────

/** 해당 KST 시각 기준으로 payload를 오늘 세션으로 인정하는가 */
function acceptsAt(when, payload) {
  const fn = loadWindow({ now: kst(when) }).__wmIsTodaySession;
  assert.ok(fn, 'window.__wmIsTodaySession이 없다 — 장중 곡선 세션 검증 훅이 제거됐는지 확인할 것');
  return fn(payload);
}

test('오늘 세션 1분봉은 받는다', () => {
  assert.equal(acceptsAt('2026-07-31T10:00:00', { date: '20260731', minutes: [1, 2], times: ['09:05', '09:10'] }), true);
});

test('전 거래일 1분봉은 거부한다 (개장 전 백필 — 실사고 리플레이)', () => {
  // 07-31 08:00엔 오늘 봉이 아직 없어 피드가 07-30 세션을 돌려준다
  assert.equal(acceptsAt('2026-07-31T08:00:00', { date: '20260730', minutes: [214000, 207000], times: ['09:00', '15:30'] }), false);
});

test('공휴일·주말엔 직전 거래일 세션을 거부한다', () => {
  assert.equal(acceptsAt('2026-08-01T11:00:00', { date: '20260731', minutes: [1, 2], times: ['09:00', '15:30'] }), false);
});

test('date가 없는 응답(502 등)은 거부한다', () => {
  assert.equal(acceptsAt('2026-07-31T10:00:00', { minutes: [1, 2], times: ['09:05', '09:10'] }), false);
  assert.equal(acceptsAt('2026-07-31T10:00:00', {}), false);
  assert.equal(acceptsAt('2026-07-31T10:00:00', null), false);
});

test('KST 자정 직후에도 전일 세션을 오늘로 받지 않는다', () => {
  assert.equal(acceptsAt('2026-07-31T00:10:00', { date: '20260730', minutes: [1, 2], times: ['09:00', '15:30'] }), false);
});

test('UTC 기준으로 날짜가 갈리지 않는다 (KST 09:00 = UTC 전날 00:00)', () => {
  assert.equal(acceptsAt('2026-07-31T09:00:00', { date: '20260731', minutes: [1, 2], times: ['09:00', '09:05'] }), true);
});

// ─────────────────────────────────────────────────────────────────────────────
// 밤사이 브리지 노출 게이트 (__obShouldShow)
//
// 거래일 07:30~09:00(KST)에만 뜬다. 07:30은 '밤사이 미국 반도체 시황'이 꺼지는 경계(핸드오프),
// 09:00은 코스피 개장 — 개장 뒤에도 갭을 띄우면 '한국 직전 마감'이 어제 종가가 되면서 오늘
// 등락과 이중 계상된다(§24). 09:00 off-by-one이 곧 §24 위반이라 경계를 분 단위로 고정한다.
// 파일은 주말·공휴일에도 배포된 채 남으므로, 그날들을 실제로 막는 건 date 게이트다(§0).
// ─────────────────────────────────────────────────────────────────────────────

/** 해당 KST 시각에 이 payload로 브리지를 노출하는가 */
function bridgeShows(when, payload) {
  const fn = loadWindow({ now: kst(when) }).__obShouldShow;
  assert.ok(fn, 'window.__obShouldShow가 없다 — 밤사이 브리지 게이트 훅이 제거됐는지 확인할 것');
  return fn(payload);
}

/** 표시용 행 하나의 HTML */
function bridgeRowHtml(row) {
  const fn = loadWindow().__obRowHtml;
  assert.ok(fn, 'window.__obRowHtml이 없다 — 밤사이 브리지 렌더 훅이 제거됐는지 확인할 것');
  return fn(row);
}

/** date를 지정한 정상 payload */
function payload(date) {
  return {
    date, kr_session_date: '2026-07-31',
    rows: [{
      sector: '반도체', us_label: '반도체 ETF', kr_label: '삼성전자·SK하이닉스',
      us_change_fmt: '+8.50%', kr_change_fmt: '+28.38%', us_cls: 'up', kr_cls: 'up',
      gap_fmt: '+19.9%p', gap_cls: 'up', gap_word: '선반영',
    }],
  };
}

test('브리지: 거래일 08:00, 오늘자 데이터 → 노출', () => {
  assert.equal(bridgeShows('2026-08-03T08:00:00', payload('2026-08-03')), true);
});

test('브리지 경계: 07:29는 아직 안 뜨고 07:30부터 뜬다', () => {
  assert.equal(bridgeShows('2026-08-03T07:29:00', payload('2026-08-03')), false);
  assert.equal(bridgeShows('2026-08-03T07:30:00', payload('2026-08-03')), true);
});

test('브리지 경계: 08:59는 뜨고 09:00(개장)엔 내려간다 — off-by-one이 곧 §24 위반', () => {
  assert.equal(bridgeShows('2026-08-03T08:59:00', payload('2026-08-03')), true);
  assert.equal(bridgeShows('2026-08-03T09:00:00', payload('2026-08-03')), false);
});

test('브리지: 개장 후 장중엔 뜨지 않는다', () => {
  assert.equal(bridgeShows('2026-08-03T10:30:00', payload('2026-08-03')), false);
});

test('브리지: 주말엔 시간대가 맞아도 뜨지 않는다', () => {
  assert.equal(bridgeShows('2026-08-01T08:00:00', payload('2026-08-01')), false); // 토
  assert.equal(bridgeShows('2026-08-02T08:00:00', payload('2026-08-02')), false); // 일
});

test('브리지: 공휴일(광복절 대체 08-17)엔 뜨지 않는다', () => {
  assert.equal(bridgeShows('2026-08-17T08:00:00', payload('2026-08-17')), false);
});

test('브리지: 어제 날짜 파일은 렌더하지 않는다 (§0 — 완전성보다 정합성)', () => {
  assert.equal(bridgeShows('2026-08-03T08:00:00', payload('2026-07-31')), false);
});

test('브리지: 파일이 없거나(null) rows가 비면 뜨지 않는다', () => {
  assert.equal(bridgeShows('2026-08-03T08:00:00', null), false);
  assert.equal(bridgeShows('2026-08-03T08:00:00', undefined), false);
  assert.equal(bridgeShows('2026-08-03T08:00:00', { date: '2026-08-03', rows: [] }), false);
  assert.equal(bridgeShows('2026-08-03T08:00:00', { date: '2026-08-03' }), false);
});

test('브리지: 파일이 없어도 스크립트 로드가 죽지 않는다 (fetch 거부 경로)', () => {
  // loadWindow의 fetch 스텁은 항상 reject한다 — 여기까지 오면 catch가 살아 있다는 뜻.
  assert.equal(typeof loadWindow().__obShouldShow, 'function');
});

test('브리지: gap_cls가 빈 문자열(동조)이면 색 클래스를 붙이지 않는다', () => {
  const html = bridgeRowHtml({
    sector: '자동차', us_label: 'TSLA·F', kr_label: '현대차·기아',
    us_change_fmt: '+1.00%', kr_change_fmt: '+1.00%', us_cls: 'up', kr_cls: 'up',
    gap_fmt: '+0.0%p', gap_cls: '', gap_word: '동조',
  });
  assert.match(html, /class="ob-pill">동조</);
  assert.match(html, /class="num">\+0\.0%p</);
});

test('브리지: 색 클래스는 파이썬이 구운 us_cls·kr_cls·gap_cls를 그대로 쓴다 (§30 재계산 금지)', () => {
  const html = bridgeRowHtml(payload('2026-08-03').rows[0]);
  assert.match(html, /class="ob-pill up">선반영</);
  assert.match(html, /class="num up">\+19\.9%p</);
  assert.match(html, /class="num up">\+8\.50%</);
});
