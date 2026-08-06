// flow-map.js 순수 함수 테스트 — node:vm 샌드박스에서 실제 프로덕션 파일을 로드해 검증
//
// 순수 함수를 테스트 파일에 복제하면 사본이 원본과 어긋나므로(SERVICE_RULES §20류),
// 실제 파일을 최소 DOM 스텁과 함께 실행하고 window.__flowMap으로 꺼내 검증한다.
// ds-subnav.test.mjs·sector-screen.test.mjs와 같은 패턴.
//
// 실행: node --test web/assets/flow-map.test.mjs
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
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    style: {}, innerHTML: '', textContent: '',
    addEventListener: noop, setAttribute: noop, getAttribute: () => null,
    closest: () => null, querySelector: () => null, querySelectorAll: () => [],
  };
  return e;
}

/** flow-map.js를 vm에서 실행하고 공개 API를 돌려준다. */
function load() {
  const els = {};
  const win = {
    location: { pathname: '/stocks/', hash: '' },
    addEventListener: noop,
    fetch: () => new Promise(() => {}),        // 실제 네트워크는 타지 않는다
    document: {
      readyState: 'complete',
      getElementById: (id) => (els[id] || (els[id] = mkEl())),
      addEventListener: noop,
      querySelector: () => null,
      querySelectorAll: () => [],
    },
  };
  win.window = win;
  const ctx = createContext(win);
  runInContext(readFileSync(join(HERE, 'flow-map.js'), 'utf8'), ctx);
  return { api: win.__flowMap, els, win };
}

test('eok — 억/조 단위 포맷과 부호', () => {
  const { eok } = load().api;
  assert.equal(eok(9500), '+9,500억');
  assert.equal(eok(-74), '−74억');            // U+2212 마이너스
  assert.equal(eok(0), '0억');
  assert.equal(eok(15592), '+1.6조');         // 1만억 이상은 조로 접는다
  assert.equal(eok(25000), '+2.5조');
  assert.equal(eok(-120000), '−12조');        // 10조 이상은 소수점 없이
});

test('eok — 조 단위 전환 경계값(9999 vs 10000)', () => {
  const { eok } = load().api;
  assert.equal(eok(9999), '+9,999억');
  assert.equal(eok(10000), '+1조');
});

test('wd — 요일은 Date.UTC 조립으로 구한다(오프바이원 회귀)', () => {
  const { wd } = load().api;
  // 'YYYY-MM-DDT00:00:00+09:00' 파싱은 KST 자정 = 전날 15:00 UTC라 getUTCDay()가 하루 밀린다.
  assert.equal(wd('2026-07-31'), '금');
  assert.equal(wd('2026-08-03'), '월');
  assert.equal(wd('2026-07-27'), '월');
});

test('wd — 일요일·토요일도 정확히 매핑된다', () => {
  const { wd } = load().api;
  assert.equal(wd('2026-08-02'), '일');
  assert.equal(wd('2026-08-01'), '토');
});

test('churn — 회전율은 gross / |net|, net 0이어도 나눗셈이 깨지지 않는다', () => {
  const { churn } = load().api;
  assert.equal(churn({ gross_eok: 1700, flow_eok: 100 }), 17);
  assert.equal(churn({ gross_eok: 50, flow_eok: 0 }), 50);
});

test('barPct — 한쪽 최대 50%, 전체 최대치 기준', () => {
  const { barPct } = load().api;
  assert.equal(barPct(100, 100), '50.00');
  assert.equal(barPct(-50, 100), '25.00');
  assert.equal(barPct(0, 0), '0.00');         // 전 테마 0 — 0으로 나누지 않는다
});

test('pivot — 금액이 아니라 동조 테마 수로 고른다', () => {
  const { pivot } = load().api;
  const themes = [
    { daily: [1, -1] }, { daily: [1, -1] }, { daily: [-1, -1] }, { daily: [-1, -1] },
  ];
  // d0: 시장 +, 같은 방향 2개 / d1: 시장 −, 같은 방향 4개 → 금액이 작아도 d1이 선정
  const r = pivot([9999, -10], themes);
  assert.equal(r.i, 1);
  assert.equal(r.same, 4);
});

test('pivot — 동수면 금액으로 타이브레이크', () => {
  const { pivot } = load().api;
  const themes = [{ daily: [1, 1] }, { daily: [1, 1] }];
  assert.equal(pivot([10, 500], themes).i, 1);
});

test('pivot — 빈 입력이면 -1', () => {
  const { pivot } = load().api;
  // vm 샌드박스 객체는 별도 realm이라 deepStrictEqual({i:-1,same:0})은 프로토타입 불일치로
  // 항상 실패한다 — 다른 pivot 테스트와 같이 프로퍼티를 개별 비교한다.
  const r = pivot([], []);
  assert.equal(r.i, -1);
  assert.equal(r.same, 0);
});

test('staleDays — 마지막 갱신 경과 일수', () => {
  const { staleDays } = load().api;
  const now = Date.parse('2026-08-06T20:00:00+09:00');
  assert.equal(staleDays('2026-08-06T18:00:00+09:00', now), 0);
  assert.equal(staleDays('2026-07-31T18:00:00+09:00', now), 6);
  assert.equal(staleDays('nonsense', now), null);
  assert.equal(staleDays('2026-08-07T08:00:00+09:00', now), 0);   // 12시간 뒤(미래) — 0으로 clamp
  assert.equal(staleDays('2026-08-08T02:00:00+09:00', now), 0);   // 30시간 뒤(미래) — 0으로 clamp
});
