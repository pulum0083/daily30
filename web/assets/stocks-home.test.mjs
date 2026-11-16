// stocks-home.js 국면 판정(__layoutPhase) 회귀 테스트 — node:vm 샌드박스에서 실제 프로덕션 파일을 로드해 검증
//
// 왜 이런 방식인가
//   stocks-home.js는 브라우저용 IIFE(<script src defer>)라 import할 수 없고, 국면 판정은
//   섹션 재배치 IIFE의 클로저 안에 있다. 순수 함수를 별 파일로 복제하면 사본이 원본과
//   어긋나므로(SERVICE_RULES §20류 사고의 전형), 실제 파일을 최소 DOM 스텁과 함께 vm에서
//   실행하고 window.__layoutPhase로 꺼내 테스트한다. main.test.mjs와 같은 패턴.
//
// 검증 범위
//   ① 국면 판정(day / us_open / quiet). 실제 DOM 이동 순서는 스텁 환경에서 확인할 수 없어
//      브라우저에서 별도 확인한다.
//   ② 라이브 타일 10초 폴링의 백그라운드 탭 가드(2026-08-16 Vercel 차단 사고 방지).
//
// 실행: node --test web/assets/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
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

/** stocks-home.js를 스텁 환경에서 실행하고 window(샌드박스)를 돌려준다.
 *  hooks: fetch(URL별 응답 제어) / onInterval·onDocListener(등록된 콜백 수집) — 넘기지 않으면
 *  기존 동작(네트워크 거부, 타이머·리스너 무시) 그대로다. */
function loadWindow({ now, hooks } = {}) {
  const h = hooks || {};
  const src = readFileSync(join(HERE, 'stocks-home.js'), 'utf8');
  const els = new Map();
  const doc = {
    documentElement: mkEl(), head: mkEl(), body: mkEl(),
    hidden: false,
    // id별로 같은 엘리먼트를 돌려준다 — 렌더 결과(display·innerHTML)를 밖에서 확인하려면
    // 매 호출마다 새 스텁을 만들면 안 된다.
    getElementById: (id) => { if (!els.has(id)) els.set(id, mkEl()); return els.get(id); },
    querySelector: () => mkEl(), querySelectorAll: h.querySelectorAll || (() => []),
    addEventListener: h.onDocListener || noop,
    createElement: () => mkEl(), createTextNode: () => ({}),
  };
  const sandbox = {
    document: doc,
    __els: els,
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    sessionStorage: { getItem: () => null, setItem: noop, removeItem: noop },
    location: { pathname: '/stocks/', search: '', hash: '', href: '' },
    navigator: { userAgent: 'node' },
    fetch: h.fetch || (() => Promise.reject(new Error('테스트에서는 네트워크를 쓰지 않는다'))),
    AbortSignal: { timeout: () => null },
    addEventListener: noop, removeEventListener: noop,
    setTimeout: noop, setInterval: h.onInterval || noop, clearInterval: noop, clearTimeout: noop,
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
// go() — pushState 뒤 서브탭 동기화 훅. pushState는 hashchange를 발생시키지 않으므로
// go()가 화면을 바꿀 때마다 window.dsSubnavSync를 직접 불러 서브탭 강조를 맞춘다(/stocks/
// 서브탭 배선). loadWindow()의 스텁 document/window엔 history·scrollTo가 없어 go()가 그
// 지점에서 바로 예외를 던지므로, 이 두 테스트에서만 최소로 채워 넣는다.
// ─────────────────────────────────────────────────────────────────────────────

/** go()를 실행할 수 있는 상태로 만든다 — 대상 화면 el이 .screen 클래스를 가진 것처럼 위장하고,
 *  go() 본문이 무조건 건드리는 window.scrollTo·history.pushState를 최소 스텁으로 채운다. */
function loadWindowForGo() {
  const win = loadWindow();
  const el = win.document.getElementById('sector');
  el.classList.contains = (cls) => cls === 'screen';
  win.scrollTo = noop;
  win.history = { pushState: noop };
  return win;
}

test('go(): 화면 전환 후 window.dsSubnavSync를 정확히 한 번 호출한다', () => {
  const win = loadWindowForGo();
  let calls = 0;
  win.dsSubnavSync = () => { calls++; };
  win.go('sector');
  assert.equal(calls, 1);
});

test('go(): window.dsSubnavSync가 함수가 아니어도(미정의·문자열) 예외 없이 넘어간다', () => {
  for (const bad of [undefined, 'not-a-function']) {
    const win = loadWindowForGo();
    win.dsSubnavSync = bad;
    assert.doesNotThrow(() => win.go('sector'), `dsSubnavSync=${String(bad)} 케이스에서 예외 발생`);
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// 라이브 타일 60초 폴링 — 백그라운드 탭 가드 (2026-08-16 Vercel 차단 사고 방지)
//
// 사고: Vercel 팀이 FAIR_USE_LIMITS_EXCEEDED(fluidCpuDuration)로 소프트 차단돼
// doubleshot.space 전체가 402를 반환했다. 이 10초 폴링은 시장 시간·탭 포커스와 무관하게
// 24시간 돌아 탭 하나당 하루 8,640회 서버리스 함수를 깨웠다.
//
// 보이지 않는 탭에서 값을 갱신해봐야 아무도 보지 않는다. 복귀 시 즉시 다시 받으므로
// 사용자가 보는 화면의 신선도는 그대로다.
// ─────────────────────────────────────────────────────────────────────────────

/** 라이브 타일 폴링 루프를 스텁 환경에서 띄우고 조작 핸들을 돌려준다. */
function loadLivePolling({ now } = {}) {
  const intervals = [];
  const docListeners = [];
  const fetched = [];
  // liveCodes는 #ld-row의 한 줄 타일에서 나온다 — 비어 있으면 poll()이 즉시 return해
  // 테스트가 무의미하게 통과한다(가드가 없어도 fetch가 0건).
  const tiles = ['005930', '000660'].map((code) => {
    const t = mkEl();
    t.getAttribute = (k) => (k === 'data-code' ? code : null);
    return t;
  });

  const win = loadWindow({
    now,
    hooks: {
      onInterval: (fn, ms) => { intervals.push({ fn, ms }); },
      onDocListener: (ev, fn) => { docListeners.push({ ev, fn }); },
      querySelectorAll: (sel) => (String(sel).includes('#ld-row .ld[data-code]') ? tiles : []),
      fetch: (url) => { fetched.push(String(url)); return Promise.reject(new Error('테스트 스텁')); },
    },
  });

  // 60초 인터벌은 여러 개다(날짜 롤오버 체커·섹터 시세·시장 지표·라이브 타일…).
  // ms만으로는 라이브 타일 루프를 못 고르므로, 후보를 하나씩 돌려보고 타일 엔드포인트
  // (stocks-live·hl-night)를 부르는 놈을 찾는다. 로드가 결정론적이라 인덱스는 재현된다.
  const candidates = intervals.filter((i) => i.ms === 60000);
  assert.ok(candidates.length, '60초 폴링 인터벌이 하나도 없다 — 루프가 사라졌거나 주기가 바뀌었다');
  let tick = null;
  for (const c of candidates) {
    fetched.length = 0;
    c.fn();
    if (fetched.some((u) => /\/api\/(stocks-live|hl-night)/.test(u))) { tick = c; break; }
  }
  assert.ok(tick, '라이브 타일 루프를 찾지 못했다 — 타일이 stocks-live·hl-night를 부르지 않는다');

  return {
    win,
    apiCalls: () => fetched.filter((u) => u.startsWith('/api/')),
    reset: () => { fetched.length = 0; },
    setHidden: (v) => { win.document.hidden = v; },
    tick: () => tick.fn(),
    fireVisibilityChange: () => {
      const ls = docListeners.filter((l) => l.ev === 'visibilitychange');
      assert.ok(ls.length, 'visibilitychange 리스너가 없다 — 탭 복귀 시 즉시 복구되지 않는다');
      ls.forEach((l) => l.fn());
    },
  };
}

const WEEKDAY_OPEN = kst('2026-07-28T10:00:00'); // 화요일 장중 — pollDay 경로

test('폴링 가드: 탭이 보이지 않으면 API를 호출하지 않는다', () => {
  const p = loadLivePolling({ now: WEEKDAY_OPEN });
  p.reset();                 // 로드 직후 1회 폴링은 정상 동작이므로 제외
  p.setHidden(true);
  p.tick();
  assert.deepEqual(p.apiCalls(), [], '백그라운드 탭에서 서버리스 함수를 깨웠다');
});

test('폴링 가드: 탭이 보이면 평소대로 API를 호출한다 (과잉 차단 방지)', () => {
  const p = loadLivePolling({ now: WEEKDAY_OPEN });
  p.reset();
  p.setHidden(false);
  p.tick();
  assert.equal(p.apiCalls().length, 1, '보이는 탭에서 폴링이 멈췄다 — 가드가 과하다');
});

test('폴링 가드: 탭 복귀 시 다음 인터벌을 기다리지 않고 즉시 받아온다', () => {
  const p = loadLivePolling({ now: WEEKDAY_OPEN });
  p.setHidden(true);
  p.tick();
  p.reset();
  p.setHidden(false);
  p.fireVisibilityChange();
  assert.equal(p.apiCalls().length, 1, '복귀 직후 최대 10초간 낡은 값이 남는다');
});

test('폴링 가드: 숨김→복귀를 반복해도 폴링이 중복 등록되지 않는다', () => {
  const p = loadLivePolling({ now: WEEKDAY_OPEN });
  for (let i = 0; i < 3; i++) { p.setHidden(true); p.tick(); p.setHidden(false); p.fireVisibilityChange(); }
  p.reset();
  p.tick();
  assert.equal(p.apiCalls().length, 1, '인터벌이 중복 등록돼 호출이 배로 늘었다');
});

// ─────────────────────────────────────────────────────────────────────────────
// 표기 ↔ 실제 주기 1:1 (SERVICE_RULES §10)
//
// 2026-08-17 실사고: #kospi-live-badge가 'LIVE · 10초 갱신'이라 적혀 있었는데 그 구역의
// 실제 폴링은 pollMarket 60초였다. 10초 인터벌은 다른 위젯의 것이었고, 아무도 몇 달간
// 눈치채지 못했다. 화면이 약속한 신선도보다 실제가 느리면 그건 §0 위반이다.
//
// 소스에 박힌 'N초 갱신' 문구의 N이 실제로 등록되는 setInterval 주기 중에 있는지 검사한다.
// 분 단위 문구(뉴스 수집 주기 등)는 폴링 인터벌이 아니라 대상이 아니다.
// ─────────────────────────────────────────────────────────────────────────────

test('표기된 "N초 갱신"은 실제로 존재하는 폴링 주기여야 한다', () => {
  const src = readFileSync(join(HERE, 'stocks-home.js'), 'utf8');

  const labelled = [...src.matchAll(/(\d+)\s*초\s*갱신/g)].map((m) => Number(m[1]));
  assert.ok(labelled.length, '초 단위 갱신 표기를 하나도 못 찾았다 — 정규식이 낡았는지 확인할 것');

  const intervals = new Set(
    [...src.matchAll(/setInterval\s*\([^,]+,\s*(\d+)\s*\)/g)].map((m) => Number(m[1]) / 1000),
  );
  // 변수로 주기를 넘기는 위젯(setPoll(POLL_LIVE))은 상수 선언에서 값을 거둔다.
  for (const m of src.matchAll(/POLL_[A-Z]+\s*=\s*(\d+)/g)) intervals.add(Number(m[1]) / 1000);

  for (const sec of labelled) {
    assert.ok(
      intervals.has(sec),
      `'${sec}초 갱신'이라 표기했지만 ${sec}초 폴링이 없다 — 화면이 거짓 신선도를 약속한다. ` +
      `실제 등록된 주기(초): ${[...intervals].sort((a, b) => a - b).join(', ')}`,
    );
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// 코스피 주도주 확장 타일 계산 (2026-09-11)
//
// 사고: 원화 등락폭을 반올림된 %에서 역산(prev = close/(1+pct/100))해 호가 단위에 없는 값이
// 나갔다 — 삼성전자 실제 −9,250원이 −9,254원, SK하이닉스 −40,000원이 −40,025원.
// ─────────────────────────────────────────────────────────────────────────────

test('타일 — 소스에 %→전일가 역산 식이 되돌아오지 않는다', () => {
  const src = readFileSync(join(HERE, 'stocks-home.js'), 'utf8');
  assert.ok(!/\/\(1\+pct\/100\)/.test(src), 'close/(1+pct/100) 역산이 다시 들어왔다');
});

// ── 주도주 펼치기 정리(2026-11-04) — 뉴스만 남기고 큰 타일·목표주가·외국계 시각과 그 수집을 걷어냈다 ──
test('주도주 펼치기엔 관련 뉴스만 있고, 목표주가·외국계 시각 조회가 다시 붙지 않는다', () => {
  const html = readFileSync(new URL('../stocks/index.html', import.meta.url), 'utf8');
  const js = readFileSync(new URL('./stocks-home.js', import.meta.url), 'utf8');
  for (const id of ['us-tile', 'ut-rng', 'lw-tp-val', 'lw-ib', 'vs-tb']) {
    assert.ok(!html.includes(id), `${id}가 홈 HTML에 남아 있다`);
  }
  assert.ok(html.includes('id="lw-news"'), '관련 뉴스는 남는다');
  assert.ok(!js.includes('stock-targets.json') && !js.includes('ib_korea_views.json'), '목표주가·외국계 시각을 다시 불러온다');
  assert.ok(!existsSync(new URL('../../scripts/fetch_stock_targets.py', import.meta.url)), '목표주가 수집 스크립트가 되살아났다');
});

// ── 주도주 한 줄 목록(2026-11-04 B안, §79) ──
test('주도주 — 지금 가격 시간대: 장중 → 15:30~20:00 애프터장 → 20:00 이후·휴장일 추정가', () => {
  const { phase } = loadWindow({}).__leaders;
  const at = (s) => Date.parse(s + '+09:00');
  assert.equal(phase(at('2026-11-04T09:00:00')), 'open');
  assert.equal(phase(at('2026-11-04T15:30:00')), 'open');
  assert.equal(phase(at('2026-11-04T15:31:00')), 'after');
  assert.equal(phase(at('2026-11-04T19:59:00')), 'after');
  assert.equal(phase(at('2026-11-04T20:00:00')), 'night');
  assert.equal(phase(at('2026-11-05T08:59:00')), 'night');
  assert.equal(phase(at('2026-11-07T12:00:00')), 'night');      // 토요일
  assert.equal(phase(at('2026-12-25T12:00:00')), 'night');      // 공휴일
});

test('주도주 — 15:31~15:59는 애프터장 전(시간외 종가)이라 종가로 보인다', () => {
  const { afterPre } = loadWindow({}).__leaders;
  const at = (s) => Date.parse(s + '+09:00');
  assert.equal(afterPre(at('2026-11-04T15:30:00')), false);
  assert.equal(afterPre(at('2026-11-04T15:31:00')), true);
  assert.equal(afterPre(at('2026-11-04T15:59:00')), true);
  assert.equal(afterPre(at('2026-11-04T16:00:00')), false);
});

test('주도주 — 장 마감 뒤 비교는 날짜 붙은 세 공식 종가로, 하나라도 없으면 비운다 (11/3 실측)', () => {
  const { closeCmp } = loadWindow({}).__leaders;
  const p = { price: 219500, sessionDate: '20261103', prevSessionClose: 229000, prevSessionDate: '20261102', prev2SessionClose: 225000 };
  assert.deepEqual({ ...closeCmp(p) }, { date: '20261103', prevDate: '20261102', t: -4.15, y: 1.78, diff: -5.93 });
  assert.equal(closeCmp({ ...p, prev2SessionClose: null }), null);
  assert.equal(closeCmp({ ...p, prevSessionDate: null }), null);
  assert.equal(closeCmp(null), null);
});

test('주도주 모바일(M1) — 애프터장엔 1줄 가격·애프터 표시, 2줄 그날 종가 등락 · 전날보다 차이 (11/3 실측)', async () => {
  const prices = [
    { code: '005930', price: 219500, sessionDate: '20261103', prevSessionClose: 229000, prevSessionDate: '20261102', prev2SessionClose: 225000, after: { price: 221000 } },
  ];
  const win = loadWindow({
    now: kst('2026-11-03T18:30:00'),
    hooks: { fetch: (u) => Promise.resolve({ ok: true, json: () => Promise.resolve(String(u).includes('stocks-live') ? { prices } : null) }) },
  });
  await new Promise((r) => setImmediate(r));
  await new Promise((r) => setImmediate(r));
  const html = win.__els.get('ld-list').innerHTML;
  const m = html.match(/<div class="ldl-m">.*?<\/div><\/div><\/div>/);
  assert.ok(m, '모바일 줄(.ldl-m)이 없다');
  assert.match(m[0], /221,000 <span class="up">\+0\.68%<\/span><span class="ldl-pill aft"/);
  assert.match(m[0], /11\/3 종가 <b class="num dn">−4\.15%<\/b> · 전날보다/);
  assert.match(m[0], /−5\.93%p/);
  assert.match(html, /<div class="ldl-foot">차이 = 11\/3 종가 등락 − 11\/2 종가 등락이에요\.<\/div>/);
});

test('주도주 뉴스 — 세 종목을 섞어 7개, 종목마다 최신 1건은 반드시 들어가고 같은 기사는 한 번만', () => {
  const { mixNews } = loadWindow({}).__leaders;
  const mk = (code, n, hh) => Array.from({ length: n }, (_, i) => ({ url: `u-${code}-${i}`, title: `${code}-${i}`, published: `2026-11-04T${String(hh - i).padStart(2, '0')}:00:00+09:00` }));
  const stocks = { '005930': mk('005930', 5, 20), '000660': mk('000660', 5, 19), '005380': mk('005380', 2, 9) };
  stocks['000660'].push({ ...stocks['005930'][1] });          // 두 종목에 같은 기사
  const out = mixNews(stocks, 7);
  assert.equal(out.length, 7);
  assert.ok(out.some((x) => x.code === '005380'), '뉴스가 적은 종목도 1건은 들어간다');
  assert.equal(new Set(out.map((x) => x.url)).size, 7, '같은 기사가 두 번 나왔다');
  const ts = [...out].map((x) => Date.parse(x.published));   // 샌드박스 배열을 바깥 배열로 옮겨 비교
  assert.deepEqual(ts, [...ts].sort((a, b) => b - a), '최신순이 아니다: ' + out.map((x) => x.published).join(','));
});

test('주도주 뉴스 시각 — 오늘이면 시:분, 지난 날이면 월/일 시:분(저장 라벨을 쓰지 않는다)', () => {
  const { newsTime } = loadWindow({}).__leaders;
  const now = Date.parse('2026-11-04T10:30:00+09:00');
  assert.equal(newsTime('2026-11-04T09:52:10+09:00', now), '09:52');
  assert.equal(newsTime('2026-11-03T21:10:00+09:00', now), '11/3 21:10');
  assert.equal(newsTime('', now), '');
});

// ── 섹터별 대표 종목 펼치기 제거(2026-10-27) — 화면·전용 조회가 다시 붙지 않게 ──
test('섹터 펼치기·섹터 탭이 없고, 그 영역 전용 조회(/api/intraday?code=)도 없다', () => {
  const html = readFileSync(new URL('../stocks/index.html', import.meta.url), 'utf8');
  const js = readFileSync(new URL('./stocks-home.js', import.meta.url), 'utf8');
  assert.ok(!html.includes('sbx-more') && !html.includes('id="sbx-tabs"') && !html.includes('id="today-line"'));
  assert.ok(html.includes('id="sb-bars"'), '섹터 한눈에 막대는 남는다');
  assert.ok(!js.includes("/api/intraday?code="), '섹터 카드 곡선 조회가 남아 있다');
});

test('특이 신호 전체 화면은 상승률순 하나 — 정렬 탭·하락률 순 목록이 없다', () => {
  const html = readFileSync(new URL('../stocks/index.html', import.meta.url), 'utf8');
  assert.ok(!html.includes('sigall-sort-tabs') && !html.includes('sigall-dn-rows') && !html.includes('신호 강도순'));
});

test('goStock — 종목을 누르면 그 종목의 섹터 페이지로 간다(SECTOR_LABELS가 전역에 있어야 한다, 2026-10-27)', () => {
  const win = loadWindow();
  runInContext("STOCK_LIST=[{code:'005930',name:'삼성전자',sector:'semicon'}]", win);
  assert.doesNotThrow(() => win.goStock('005930'));
  assert.equal(win.location.href, '/stocks/sector/semicon/');
});

test('마감 시간대 저녁(밤사이 미국이 보일 때) 순서 — 밤사이 미국 → 이시각 추정가 → 마감 카드(2026-10-27)', () => {
  const src = readFileSync(join(HERE, 'stocks-home.js'), 'utf8');
  const css = readFileSync(join(HERE, 'stocks-home.css'), 'utf8');
  assert.match(src, /classList\.toggle\('ue-on', ev && /);               // 노출될 때만, 17:00부터 클래스를 단다(isUeTop)
  assert.match(css, /#home\.slot-close\.ue-on #us-evening\{order:-2\}/);
  assert.match(css, /#home\.slot-close\.ue-on #us-linked-widget\{order:-1\}/);
  assert.match(css, /#home #home-hero\{order:0\}/);
  assert.doesNotMatch(css, /#home\.slot-close #us-evening\{order:-1\}/);  // 17:00 전엔 주도주가 마감 카드 위로 오면 안 된다
});

// 지금 미국은 하루 종일 보인다 — 평일 한국 낮에도 미국 애프터장·주간거래가 열려 있다(2026-11-16).
// 맨 위로 올라가는 순서(ue-on)는 17:00부터, 장중엔 섹터 아래(CSS).
function ueAt(iso) {
  const win = loadWindow({ now: Date.parse(iso) });
  const home = win.document.getElementById('home');
  let on = null;
  home.classList.toggle = (c, v) => { if (c === 'ue-on') on = v; };
  win.__ueLoad = noop; win.__ueStop = noop;
  win.ueGate();
  return { shown: win.document.getElementById('us-evening').style.display !== 'none', top: on };
}

test('지금 미국 노출 경계 — 하루 종일 보이고, 평일 09:00~17:00만 맨 위가 아니다', () => {
  assert.deepEqual(ueAt('2026-11-16T08:59:00+09:00'), { shown: true, top: true });
  assert.deepEqual(ueAt('2026-11-16T09:00:00+09:00'), { shown: true, top: false });
  assert.deepEqual(ueAt('2026-11-16T12:00:00+09:00'), { shown: true, top: false });
  assert.deepEqual(ueAt('2026-11-16T16:59:00+09:00'), { shown: true, top: false });
  assert.deepEqual(ueAt('2026-11-16T17:00:00+09:00'), { shown: true, top: true });
  assert.deepEqual(ueAt('2026-11-15T12:00:00+09:00'), { shown: true, top: true });   // 일요일
});

test('장중엔 지금 미국을 섹터 아래·장기 신호 위에 둔다', () => {
  const css = readFileSync(join(HERE, 'stocks-home.css'), 'utf8');
  assert.match(css, /#home\.slot-intraday #us-evening\{order:8\}/);
  assert.match(css, /#home\.slot-intraday \.sbx-block\{order:4\}/);
});
