// vs-yesterday.js 렌더·폴링 창 회귀 테스트 — node:vm 샌드박스에서 실제 파일을 로드한다(stocks-home.test.mjs와 같은 방식)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';

const noop = () => {};
function load(nowMs) {
  const root = { hidden: true, innerHTML: '' };
  const FixedDate = class extends Date { constructor(...a) { super(...(a.length ? a : [nowMs])); } static now() { return nowMs; } };
  const sb = {
    document: { getElementById: (id) => (id === 'vs-root' ? root : null), hidden: false, addEventListener: noop },
    fetch: () => Promise.reject(new Error('no network')),
    setInterval: noop, clearInterval: noop, setTimeout: noop, console: { log: noop, warn: noop, error: noop },
    Date: nowMs ? FixedDate : Date, Intl, Math, JSON, String, Number,
  };
  sb.window = sb;
  runInContext(readFileSync(new URL('./vs-yesterday.js', import.meta.url), 'utf8'), createContext(sb));
  return { api: sb.window.__vsIntraday, root };
}
const kst = (s) => Date.parse(s + 'Z') - 9 * 3600 * 1000;

const PAYLOAD = {
  status: 'ok', time: '11:00',
  today: { date: '2026-09-14', label: '9/14(월)' }, prev: { date: '2026-09-11', label: '9/11(금)', rel: '지난 금요일' },
  verdict: { title: '지난 금요일과 비슷해요', sub: '코스피가 같은 시각 기준 거의 같은 자리예요(−0.14%p) · 외국인 누적 순매수는 8,693억 원 적어요', judge: 'same' },
  kospi: { t: -2.56, y: -2.42, diff: -0.14, judge: 'same', curveT: [[0, -2], [120, -2.56]], curveY: [[0, -1.5], [120, -2.42]] },
  flow: { t: { 개인: 22500, 외국인: -20900, 기관: -6453 }, y: { 개인: 17100, 외국인: -12300, 기관: -10600 }, time: '10:58', foreignDiff: -8600, judge: 'weak' },
  leaders: [{ code: '005930', name: '삼성전자', t: -2.89, y: -4.28, diff: 1.39, pxT: 252000, pxY: 257500 }],
  avg: null,
  issues: null, // C2 — 서버 응답은 항상 null(SERVICE_RULES §49)
};

test('ok 응답이면 결론·비교 칸·달라진 것을 그린다', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  assert.equal(root.hidden, false);
  for (const s of ['지난 금요일 11:00 vs 오늘 11:00', '지난 금요일과 비슷해요', '오늘이 약함', '−2.56%', '252,000', '외국인']) {
    assert.ok(root.innerHTML.includes(s), `빠짐: ${s}`);
  }
});

test('수급 범례는 d.time이 아니라 d.flow.time을 쓴다(I1)', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  assert.ok(root.innerHTML.includes('위 오늘 10:58'), '수급 범례가 flow.time을 안 씀');
  assert.ok(root.innerHTML.includes('아래 지난 금요일 10:58'));
  assert.ok(!root.innerHTML.includes('위 오늘 11:00'), '수급 범례가 여전히 d.time을 쓰고 있음');
});

test('이슈는 null이면 이슈 섹션을 그리지 않는다(C2)', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  assert.ok(!root.innerHTML.includes('장중 이슈'));
  assert.ok(!root.innerHTML.includes('vs-chip'));
});

test('주도주 표 — 값이 null이면 —만 표시하고 %를 붙이지 않는다(작은 것)', () => {
  const payload = { ...PAYLOAD, leaders: [...PAYLOAD.leaders, { code: '000660', name: 'SK하이닉스', t: null, y: -1.23, diff: null, pxT: null, pxY: 259000 }] };
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(payload);
  assert.ok(!root.innerHTML.includes('—%'), 'null 값에 %가 붙음(예: "—%")');
  assert.ok(root.innerHTML.includes('259,000'));
});

test('축 라벨 — 09:00·11:00·13:00·15:30을 0·120·240·390분 위치에 절대 배치, 마지막은 오른쪽 정렬(작은 것)', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  const axis = root.innerHTML.match(/<div class="vs-axis">[\s\S]*?<\/div>/)[0];
  assert.match(axis, /left:0%[^>]*>09:00</);
  assert.match(axis, /left:30\.77%[^>]*>11:00</);
  assert.match(axis, /left:61\.54%[^>]*>13:00</);
  assert.match(axis, /right:0[^>]*>15:30</);
});

test('주도주 평균이 없으면 그 칸을 그리지 않는다(§0)', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  assert.ok(!root.innerHTML.includes('주도주 3종목 평균'));
});

test('closed·waiting·실패는 영역을 숨긴다', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  for (const p of [{ status: 'closed' }, { status: 'waiting' }, null]) {
    root.hidden = false; api.render(p);
    assert.equal(root.hidden, true);
    assert.equal(root.innerHTML, '');
  }
});

test('폴링 창 — 평일 09:00~15:31만', () => {
  assert.equal(load(kst('2026-09-14T08:59:00')).api.shouldPoll(), false);
  assert.equal(load(kst('2026-09-14T09:00:00')).api.shouldPoll(), true);
  assert.equal(load(kst('2026-09-14T15:31:00')).api.shouldPoll(), true);
  assert.equal(load(kst('2026-09-14T15:32:00')).api.shouldPoll(), false);
  assert.equal(load(kst('2026-09-13T11:00:00')).api.shouldPoll(), false);
});

test('곡선 SVG — 두 선을 그린다', () => {
  const svg = load(kst('2026-09-14T11:00:00')).api.chartSvg(PAYLOAD.kospi.curveY, PAYLOAD.kospi.curveT);
  assert.equal((svg.match(/<path /g) || []).length, 2);
});
