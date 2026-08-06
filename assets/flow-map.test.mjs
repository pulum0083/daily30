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

/** 렌더 테스트용 최소 데이터 — 테마 2개, 3거래일. */
function fixture() {
  return {
    generated_at: '2026-07-31T18:05:00+09:00',
    source_generated_at: '2026-07-31T18:00:00+09:00',
    window_days: 3, aum_floor_eok: 300,
    coverage: { etf_count: 712, theme_count: 2 },
    dates: ['2026-07-29', '2026-07-30', '2026-07-31'],
    market_daily: [100, -200, 300],
    themes: [
      { theme: '반도체', flow_eok: 1500, gross_eok: 1800, etf_count: 30,
        daily: [400, -100, 1200],
        etfs: [
          { code: '1', name: 'TIGER 반도체', flow: 900, aum: 5000, pct: 18.0, daily: [300, -50, 650] },
          { code: '2', name: 'KODEX 반도체', flow: -200, aum: 4000, pct: -5.0, daily: [-50, -50, -100] },
        ],
        rest_n: 28, rest_flow: 800 },
      { theme: '채권', flow_eok: -74, gross_eok: 900, etf_count: 108,
        daily: [-30, -24, -20],
        etfs: [{ code: '3', name: 'KODEX 국고채', flow: -74, aum: 2000, pct: -3.7, daily: [-30, -24, -20] }],
        rest_n: 0, rest_flow: 0 },
    ],
  };
}

test('render — 시장 요약 3칸이 채워지고 pivot이 동조 수로 뽑힌다', () => {
  const { api, els } = load();
  api.render(fixture());
  const html = els['fmap-mkt'].innerHTML;
  assert.match(html, /3거래일 누적/);
  assert.match(html, /\+200억/);                 // 100 − 200 + 300
  // 금액 최대일은 07/31(+300)이지만 동조 테마는 1개뿐이고, 07/30은 −200으로 작아도
  // 두 테마가 함께 움직였다. 이 화면의 주제는 규모가 아니라 폭이므로 07/30이 뽑혀야 한다.
  assert.match(html, /07\/30\(목\)/);
  assert.match(html, /2\/2개 동시 유출/);
});

test('render — 전체 테마를 그리고 첫 테마가 기본 선택된다', () => {
  const { api, els } = load();
  api.render(fixture());
  const html = els['fmap-list'].innerHTML;
  assert.match(html, /data-th="반도체"/);
  assert.match(html, /data-th="채권"/);
  assert.match(html, /class="fmap-r on" data-th="반도체"/);
});

test('render — 막대 기준값은 정렬과 무관하게 전체 최대치로 고정', () => {
  const { api, els } = load();
  api.render(fixture());
  const before = els['fmap-list'].innerHTML.match(/data-th="반도체"[\s\S]*?width:([\d.]+)%/)[1];
  api.setSort('churn');
  const after = els['fmap-list'].innerHTML.match(/data-th="반도체"[\s\S]*?width:([\d.]+)%/)[1];
  assert.equal(before, after);
  assert.equal(before, '50.00');                 // |1500|이 전체 최대치
});

test('render — 정렬을 바꿔도 선택된 테마와 상세는 유지된다', () => {
  const { api, els } = load();
  api.render(fixture());
  api.select('채권');
  assert.match(els['fmap-detail'].innerHTML, /채권/);
  api.setSort('net');
  assert.match(els['fmap-list'].innerHTML, /class="fmap-r on" data-th="채권"/);
  assert.match(els['fmap-detail'].innerHTML, /채권/);   // 상세는 그대로
});

test('detail — 그 외 N개 절단을 명시하고, 10% 미만은 뱃지를 달지 않는다', () => {
  const { api, els } = load();
  api.render(fixture());
  const html = els['fmap-detail'].innerHTML;
  assert.match(html, /그 외 <b>28개<\/b>/);
  assert.match(html, /\+800억/);
  assert.match(html, /fmap-pill hot">\+18%/);          // 18.0% → 뱃지
  assert.doesNotMatch(html, /fmap-pill cold">−5%/);    // 5.0% → 뱃지 없음
});

test('detail — 일별 막대에 시장 동조/반대가 붙는다', () => {
  const { api, els } = load();
  api.render(fixture());
  api.select('반도체');
  const html = els['fmap-detail'].innerHTML;
  // 시장 [100,−200,300] vs 반도체 [400,−100,1200] → 전부 같은 방향
  assert.equal((html.match(/시장 동조/g) || []).length, 3);
  api.select('채권');
  // 채권 [−30,−24,−20] vs 시장 [+,−,+] → 1·3일차가 반대
  assert.equal((els['fmap-detail'].innerHTML.match(/시장 반대/g) || []).length, 2);
});

test('render — 데이터가 비면 빈 상태만 보여주고 본문을 그리지 않는다', () => {
  const { api, els } = load();
  api.render({ dates: [], market_daily: [], themes: [] });
  assert.equal(els['fmap-content'].style.display, 'none');
  assert.equal(els['fmap-empty'].style.display, '');
  assert.match(els['fmap-empty'].textContent, /준비 중/);
});
