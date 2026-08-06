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

test('탭 정의는 이번 범위인 5개만 점등한다', () => {
  const { TABS } = load().api;
  // Array.from으로 vm 컨텍스트 배열을 호스트 realm 배열로 재구성한다 — assert.deepEqual(=deepStrictEqual)이
  // 값이 같아도 realm이 다른 배열의 prototype/constructor를 비교해 실패시키는 Node 고질적 이슈 회피
  // (nodejs/node#44462, Node 22·24 모두 재현 확인).
  assert.deepEqual(Array.from(TABS.map((t) => t.id)), ['home', 'signals', 'sector', 'flow', 'etf']);
  assert.deepEqual(Array.from(TABS.map((t) => t.label)), ['전체', '특이신호', '섹터', '자금 지도', 'ETF']);
});

test('경로·해시 조합별 활성 탭 판정', () => {
  const { resolveActiveTab } = load().api;
  assert.equal(resolveActiveTab('/stocks/', ''), 'home');
  assert.equal(resolveActiveTab('/stocks/', '#home'), 'home');
  assert.equal(resolveActiveTab('/stocks/', '#signals-all'), 'signals');
  assert.equal(resolveActiveTab('/stocks/', '#sector'), 'sector');
  assert.equal(resolveActiveTab('/stocks/', '#etf-rank'), 'etf');
});

test('탭이 없는 화면(#passive 등)은 전체로 떨어진다', () => {
  const { resolveActiveTab } = load().api;
  // 아무 탭도 활성이 아닌 것보다, 시그널 영역 안에 있다는 사실을 유지하는 쪽이 방향 감각에 낫다.
  assert.equal(resolveActiveTab('/stocks/', '#passive'), 'home');
  assert.equal(resolveActiveTab('/stocks/', '#ranking'), 'home');
  assert.equal(resolveActiveTab('/stocks/', '#mom-track'), 'home');
});

test('종목 상세 등 그 외 경로는 아무 탭도 활성이 아니다', () => {
  const { resolveActiveTab } = load().api;
  assert.equal(resolveActiveTab('/stocks/005930/', ''), null);
  assert.equal(resolveActiveTab('/stocks/us/nvda/', ''), null);
  assert.equal(resolveActiveTab('/briefings/', ''), null);
});

test('아직 점등하지 않은 탭 경로에서도 깨지지 않는다', () => {
  const { resolveActiveTab } = load().api;
  // 테마·일정은 정의에 주석 처리돼 있다 — 그 경로로 들어와도 null이지 예외가 아니다.
  assert.equal(resolveActiveTab('/themes/', ''), null);
  assert.equal(resolveActiveTab('/calendar/', ''), null);
});

test('로컬 정적 서버의 /stocks/index.html도 홈으로 본다', () => {
  const { resolveActiveTab } = load().api;
  assert.equal(resolveActiveTab('/stocks/index.html', ''), 'home');
});

test('TABS의 screen 값이 index.html에 실제로 있는 화면 id와 일치한다', () => {
  // 오타로 죽은 탭이 나가는 것을 막는다. screen이 없는 탭(독립 페이지)은 검사 제외.
  const { TABS } = load().api;
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
  const { TABS } = load().api;
  for (const t of TABS) {
    if (!t.screen) continue;
    const hash = t.href.includes('#') ? t.href.split('#')[1] : '';
    if (hash) assert.equal(hash, t.screen, `${t.id}: href 해시와 screen이 다르다`);
    else assert.equal(t.screen, 'home', `${t.id}: 해시 없는 탭은 screen이 home이어야 한다`);
  }
});

test('껍데기(#ds-subnav)가 없는 페이지에서 로드해도 예외가 없다', () => {
  // main.js의 `if (!el) return` 가드 관례. 로드만 되면 통과 — load()가 이미 그 상황이다.
  assert.ok(load().api.TABS.length > 0);
});

test('해시 대소문자와 무관하게 같은 탭으로 판정한다', () => {
  // 이 파일이 만드는 href는 전부 소문자지만, 손으로 친 링크·옛 북마크 등 다른 출처의
  // 해시가 다른 대소문자로 들어올 수 있다 — 그 경우도 '전체'로 조용히 떨어지면 안 된다.
  const { resolveActiveTab } = load().api;
  assert.equal(resolveActiveTab('/stocks/', '#SIGNALS-ALL'), 'signals');
  assert.equal(resolveActiveTab('/stocks/', '#Sector'), 'sector');
  assert.equal(resolveActiveTab('/stocks/', '#ETF-RANK'), 'etf');
});

test('탭을 TABS에 하나 추가하면 해시 판정도 별도 편집 없이 즉시 따라온다 (드리프트 회귀)', () => {
  // 코드 리뷰에서 지적된 실제 드리프트 재현: 해시→탭 매핑을 손으로 유지하는 두 번째 표로
  // 두면, TABS에 새 탭을 추가해도 그 표를 깜빡하면 잘못된 탭이 조용히 활성화된다. 이 테스트는
  // TABS 배열 자체를 직접 조작해(테스트 전용 항목 — 실제 정의의 주석 처리된 테마·일정 탭은
  // 건드리지 않는다) TABS 하나만 고치는 것으로 충분함을 증명한다.
  const { TABS, resolveActiveTab } = load().api;
  TABS.push({ id: 'income', label: '배당', href: '/stocks/#income', screen: 'income' });
  assert.equal(resolveActiveTab('/stocks/', '#income'), 'income');
});

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

test('같은 window에 스크립트가 두 번 실행돼도 리스너가 중복 등록되지 않는다 (더블 로드)', () => {
  // load()는 호출마다 새 vm 컨텍스트를 만들어 이 상황을 재현하지 못하므로, 여기서만
  // 같은 컨텍스트에 소스를 두 번 runInContext한다 — 페이지에 스크립트 태그가 실수로
  // 두 번 include되는 상황(예: 템플릿 중복 include)을 그대로 흉내낸다.
  const host = mkHost();
  let clickAdds = 0;
  const origAddEventListener = host.addEventListener.bind(host);
  host.addEventListener = (type, fn) => {
    if (type === 'click') clickAdds++;
    origAddEventListener(type, fn);
  };

  const hashHandlers = [];
  const popHandlers = [];
  const calls = [];
  const win = {
    location: { pathname: '/stocks/', hash: '' },
    addEventListener: (type, fn) => {
      if (type === 'hashchange') hashHandlers.push(fn);
      if (type === 'popstate') popHandlers.push(fn);
    },
    document: {
      readyState: 'complete',
      getElementById: (id) => (id === 'ds-subnav' ? host : null),
      addEventListener: noop,
    },
    go: (s) => calls.push(s),
  };
  win.window = win;
  const ctx = createContext(win);
  const src = readFileSync(join(HERE, 'ds-subnav.js'), 'utf8');
  runInContext(src, ctx);
  runInContext(src, ctx);   // 같은 컨텍스트에 두 번째 실행

  assert.equal(clickAdds, 1, 'click 리스너가 두 번 등록됐다');
  assert.equal(hashHandlers.length, 1, 'hashchange 리스너가 두 번 등록됐다');
  assert.equal(popHandlers.length, 1, 'popstate 리스너가 두 번 등록됐다');

  host._click({
    target: { closest: () => ({ getAttribute: () => 'sector' }) },
    preventDefault: noop,
  });
  assert.deepEqual(calls, ['sector'], '클릭 한 번에 go()가 정확히 한 번만 호출돼야 한다');
});
