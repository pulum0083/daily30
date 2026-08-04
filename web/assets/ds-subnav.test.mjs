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
  // Array.from으로 vm 컨텍스트 배열을 호스트 realm 배열로 재구성한다 — assert.deepEqual(=deepStrictEqual)이
  // 값이 같아도 realm이 다른 배열의 prototype/constructor를 비교해 실패시키는 Node 고질적 이슈 회피
  // (nodejs/node#44462, Node 22·24 모두 재현 확인).
  assert.deepEqual(Array.from(TABS.map((t) => t.id)), ['home', 'signals', 'sector', 'etf']);
  assert.deepEqual(Array.from(TABS.map((t) => t.label)), ['전체', '특이신호', '섹터', 'ETF']);
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

test('해시 대소문자와 무관하게 같은 탭으로 판정한다', () => {
  // 이 파일이 만드는 href는 전부 소문자지만, 손으로 친 링크·옛 북마크 등 다른 출처의
  // 해시가 다른 대소문자로 들어올 수 있다 — 그 경우도 '전체'로 조용히 떨어지면 안 된다.
  const { resolveActiveTab } = load();
  assert.equal(resolveActiveTab('/stocks/', '#SIGNALS-ALL'), 'signals');
  assert.equal(resolveActiveTab('/stocks/', '#Sector'), 'sector');
  assert.equal(resolveActiveTab('/stocks/', '#ETF-RANK'), 'etf');
});

test('탭을 TABS에 하나 추가하면 해시 판정도 별도 편집 없이 즉시 따라온다 (드리프트 회귀)', () => {
  // 코드 리뷰에서 지적된 실제 드리프트 재현: 해시→탭 매핑을 손으로 유지하는 두 번째 표로
  // 두면, TABS에 새 탭을 추가해도 그 표를 깜빡하면 잘못된 탭이 조용히 활성화된다. 이 테스트는
  // TABS 배열 자체를 직접 조작해(테스트 전용 항목 — 실제 정의의 주석 처리된 테마·일정 탭은
  // 건드리지 않는다) TABS 하나만 고치는 것으로 충분함을 증명한다.
  const { TABS, resolveActiveTab } = load();
  TABS.push({ id: 'income', label: '배당', href: '/stocks/#income', screen: 'income' });
  assert.equal(resolveActiveTab('/stocks/', '#income'), 'income');
});
