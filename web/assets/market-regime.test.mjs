// 국면 섹션 렌더 테스트 — stocks-home.js를 node:vm에서 실제 로드해 검증한다.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const noop = () => {};

function mkEl() {
  const e = { classList: { _s: new Set(), add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); }, contains(c) { return this._s.has(c); }, toggle: noop },
    dataset: {}, style: {}, children: [], innerHTML: '', textContent: '',
    addEventListener: noop, appendChild: noop, setAttribute: noop,
    getAttribute: () => null, querySelector: () => null, querySelectorAll: () => [],
    getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0 }) };
  return e;
}

function load() {
  const store = {};
  const els = new Proxy(store, { get(t, id) {
    if (typeof id !== 'string') return t[id];
    if (!t[id]) t[id] = mkEl();
    return t[id];
  } });
  const win = {
    location: { pathname: '/stocks/', hash: '' },
    addEventListener: noop, setInterval: () => 0, setTimeout: () => 0,
    fetch: () => Promise.reject(new Error('no network')),
    AbortSignal: { timeout: () => null },
    matchMedia: () => ({ matches: false, addEventListener: noop }),
    sessionStorage: { getItem: () => null, setItem: noop },
    document: { readyState: 'complete', getElementById: (id) => els[id],
      querySelector: () => mkEl(), querySelectorAll: () => [],
      createElement: () => mkEl(), addEventListener: noop,
      body: mkEl(), documentElement: mkEl(), head: mkEl() },
  };
  win.window = win;
  const ctx = createContext(win);
  runInContext(readFileSync(join(HERE, 'stocks-home.js'), 'utf8'), ctx);
  return { api: win.__marketRegime, els };
}

const FRESH = new Date().toISOString();
const SWAP = { generated_at: FRESH, session_date: '2026-08-07', state: 'swap',
  headline: '주도주가 메모리 반도체에서 AI 인프라로 넘어가는 중이에요',
  regime_since: '2026-06-24',
  cooled_keys: ['memory'], rising_keys: ['ai_infra'],
  baskets: [
    { key: 'memory', name: '메모리 반도체', scope: 'global', cum: 89.4, peak: 142.6,
      gap: -53.2, is_high: false, spark: [0, 50, 142, 89] },
    { key: 'ai_infra', name: 'AI 인프라', scope: 'global', cum: 17.2, peak: 17.2,
      gap: 0, is_high: true, spark: [0, 5, 10, 17] }],
  korea: { semi: 51.2, rest: -11.2, gap: 62.4 } };

test('swap — 좌우 2단을 그리고 블록을 보여준다', () => {
  const { api, els } = load();
  api.regimeRender(SWAP);
  assert.equal(els['regime-block'].classList.contains('is-hidden'), false);
  assert.match(els['regime-body'].innerHTML, /식는 중/);
  assert.match(els['regime-body'].innerHTML, /뜨는 중/);
  assert.match(els['regime-body'].innerHTML, /메모리 반도체/);
});

test('lead — 좌우 2단 없이 한 장으로 접힌다', () => {
  const { api, els } = load();
  api.regimeRender({ ...SWAP, state: 'lead', headline: '메모리 반도체 주도가 이어지고 있어요' });
  assert.doesNotMatch(els['regime-body'].innerHTML, /뜨는 중/);
  assert.match(els['regime-body'].innerHTML, /주도가 이어지고 있어요/);
});

test('none — 무주도 문구만 나온다', () => {
  const { api, els } = load();
  api.regimeRender({ ...SWAP, state: 'none', headline: '뚜렷한 주도주가 없어요' });
  assert.match(els['regime-body'].innerHTML, /뚜렷한 주도주가 없어요/);
  assert.doesNotMatch(els['regime-body'].innerHTML, /식는 중/);
});

test('5일 넘게 낡으면 섹션을 표시하지 않는다', () => {
  const { api, els } = load();
  const old = new Date(Date.now() - 6 * 864e5).toISOString();
  api.regimeRender({ ...SWAP, generated_at: old });
  assert.equal(els['regime-block'].classList.contains('is-hidden'), true);
});

test('데이터가 없거나 헤드라인이 비면 표시하지 않는다', () => {
  const { api, els } = load();
  api.regimeRender(null);
  assert.equal(els['regime-block'].classList.contains('is-hidden'), true);
  api.regimeRender({ ...SWAP, headline: '' });
  assert.equal(els['regime-block'].classList.contains('is-hidden'), true);
});

test('baskets가 비어있거나 없으면 표시하지 않는다 — 근거 없는 헤드라인 금지', () => {
  const { api, els } = load();
  api.regimeRender({ ...SWAP, baskets: [] });
  assert.equal(els['regime-block'].classList.contains('is-hidden'), true);
  const { api: api2, els: els2 } = load();
  const { baskets, ...noBaskets } = SWAP;
  api2.regimeRender(noBaskets);
  assert.equal(els2['regime-block'].classList.contains('is-hidden'), true);
});

test('숨길 때·보일 때 인라인 display도 함께 바뀐다 — is-hidden 클래스만으로는 Task 12 CSS 전까지 숨겨지지 않는다', () => {
  const { api, els } = load();
  api.regimeRender(SWAP);
  assert.equal(els['regime-block'].style.display, '');
  api.regimeRender(null);
  assert.equal(els['regime-block'].style.display, 'none');
});

test('basket 이름·헤드라인에 HTML 특수문자가 있으면 이스케이프한다', () => {
  const { api, els } = load();
  api.regimeRender({ ...SWAP, headline: '<script>alert(1)</script> & 테스트',
    baskets: [{ ...SWAP.baskets[0], name: 'AT&T <b>류</b>' }] });
  assert.doesNotMatch(els['regime-body'].innerHTML, /<script>/);
  assert.match(els['regime-body'].innerHTML, /AT&amp;T/);
  assert.match(els['regime-body'].innerHTML, /&amp; 테스트/);
});

test('한국 read-through는 격차를 함께 보여준다', () => {
  const { api, els } = load();
  api.regimeRender(SWAP);
  assert.match(els['regime-body'].innerHTML, /62/);
});

test('카드는 cooled_keys/rising_keys를 쓴다 — raw 최저 gap·최고 cum이 아니다', () => {
  const { api, els } = load();
  const data = { ...SWAP, baskets: [
    ...SWAP.baskets,
    // raw gap이 memory(-53.2)보다 낮지만 cooled_keys엔 없다 — 히스테리시스 미달로 봐야 한다.
    { key: 'dividend_defensive', name: '배당 방어', scope: 'global', cum: 5.0, peak: 100.0,
      gap: -95.0, is_high: false, spark: [0, 0, 0, 0] },
    // is_high=true·raw cum이 ai_infra보다 높지만 rising_keys엔 없다.
    { key: 'value_cyclical', name: '가치 경기민감', scope: 'global', cum: 500.0, peak: 500.0,
      gap: 0, is_high: true, spark: [0, 0, 0, 0] },
  ] };
  api.regimeRender(data);
  assert.match(els['regime-body'].innerHTML, /메모리 반도체/);
  assert.doesNotMatch(els['regime-body'].innerHTML, /배당 방어/);
  assert.match(els['regime-body'].innerHTML, /AI 인프라/);
  assert.doesNotMatch(els['regime-body'].innerHTML, /가치 경기민감/);
});

test('cooled_keys/rising_keys가 없는 구 캐시 JSON은 raw 근사치로 폴백한다', () => {
  const { api, els } = load();
  const { cooled_keys, rising_keys, ...noKeys } = SWAP;
  api.regimeRender(noKeys);
  assert.match(els['regime-body'].innerHTML, /메모리 반도체/);
  assert.match(els['regime-body'].innerHTML, /AI 인프라/);
});
