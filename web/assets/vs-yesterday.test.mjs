// vs-yesterday.js 렌더·폴링 창 회귀 테스트 — node:vm 샌드박스에서 실제 파일을 로드한다(stocks-home.test.mjs와 같은 방식)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';

const noop = () => {};
function load(nowMs, tiles, hooks) {
  hooks = hooks || {};
  const root = { hidden: true, innerHTML: '' };
  const FixedDate = class extends Date { constructor(...a) { super(...(a.length ? a : [nowMs])); } static now() { return nowMs; } };
  const sb = {
    document: { getElementById: (id) => (id === 'vs-root' ? root : null), querySelectorAll: () => tiles || [], hidden: hooks.hidden || false, addEventListener: hooks.onDocEvent || noop },
    fetch: hooks.fetch || (() => Promise.reject(new Error('no network'))),
    setInterval: noop, clearInterval: noop, setTimeout: noop, console: { log: noop, warn: noop, error: noop },
    Date: nowMs ? FixedDate : Date, Intl, Math, JSON, String, Number,
  };
  sb.window = sb;
  runInContext(readFileSync(new URL('./vs-yesterday.js', import.meta.url), 'utf8'), createContext(sb));
  return { api: sb.window.__vsIntraday, root, sb };
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
  for (const s of ['지난 금요일 11:00 vs 오늘 11:00', '지난 금요일과 비슷해요', '오늘이 약함', '−2.56%', '코스피 전체 · 투자자별 누적 순매수', '외국인']) {
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

test('주도주 표는 대결판 카드에서 빠진다 — 타일 블록으로 옮겼다', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  assert.ok(!root.innerHTML.includes('vs-table'));
  assert.ok(!root.innerHTML.includes('주도주 · 전일 종가 대비'));
});

const box = (code) => ({ hidden: true, innerHTML: '', closest: () => ({ getAttribute: () => code }) });

test('타일 블록 — 비교 시각·어제·오늘·차이를 채우고, 값이 빈 종목은 숨긴다', () => {
  const b1 = box('005930'), b2 = box('000660'), b3 = box('005380');
  const payload = { ...PAYLOAD, leaders: [...PAYLOAD.leaders, { code: '000660', name: 'SK하이닉스', t: null, y: -1.23, diff: null, pxT: null, pxY: 259000 }] };
  const { api } = load(kst('2026-09-14T11:00:00'), [b1, b2, b3]);
  api.render(payload);
  assert.equal(b1.hidden, false);
  for (const s of ['지난 금요일 같은 시각', '11:00 기준', '−4.28%', '−2.89%', '지난 금요일보다', '+1.39%p']) assert.ok(b1.innerHTML.includes(s), `빠짐: ${s}`);
  assert.equal(b2.hidden, true, '오늘 값이 없는 종목은 숨긴다');
  assert.equal(b3.hidden, true, '응답에 없는 종목은 숨긴다');
});

test('타일 블록 — closed·실패면 비운다', () => {
  const b1 = box('005930');
  const { api } = load(kst('2026-09-14T11:00:00'), [b1]);
  api.render(PAYLOAD);
  assert.equal(b1.hidden, false);
  api.render({ status: 'closed' });
  assert.equal(b1.hidden, true);
  assert.equal(b1.innerHTML, '');
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

test('마우스 오버 — 가장 가까운 샘플 점의 오늘·어제·차이를 준다(보간 없음)', () => {
  const { api } = load(kst('2026-09-15T09:20:00'));
  const y = [[0, -3.27], [5, -3.17], [10, -3.03], [14, -3.1]];
  const t = [[0, -0.15], [5, -0.89], [10, -0.53], [14, -0.49]];
  const h = api.hoverAt(y, t, 6 / 390);
  assert.equal(h.m, 5);
  assert.equal(h.time, '09:05');
  assert.equal(h.t, -0.89);
  assert.equal(h.y, -3.17);
  assert.equal(h.diff, 2.28);
  const far = api.hoverAt(y, t, 0.9);
  assert.equal(far.m, 14, '곡선이 끝난 오른쪽은 마지막 점에 붙는다');
  assert.equal(far.time, '09:14');
  assert.equal(api.hoverAt([], [], 0.5), null);
});

test('마우스 오버 — 한쪽 곡선에만 있는 점이면 차이를 비운다', () => {
  const h = load(kst('2026-09-15T09:20:00')).api.hoverAt([[0, -1]], [[0, 0.5], [5, 0.7]], 5 / 390);
  assert.equal(h.t, 0.7);
  assert.equal(h.y, null);
  assert.equal(h.diff, null);
});

test('곡선은 말풍선 자리와 함께 그린다(처음엔 숨김)', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  assert.ok(root.innerHTML.includes('class="vs-plot"'));
  assert.ok(/class="vs-tip"[^>]*hidden/.test(root.innerHTML));
});

// ── A안 곡선(2026-09-15) — 차이 색 띠·눈금·선 끝 값·지금 선 ──
const WIDE = { curveT: [[0, 0], [5, -0.2], [120, -0.5]], curveY: [[0, -3], [5, -3.1], [120, -3]] };

test('A안 — 오늘이 위인 구간은 빨강 띠, 아래 구간은 파랑 띠', () => {
  const { api } = load(kst('2026-09-14T11:00:00'));
  const up = api.chartSvg(WIDE.curveY, WIDE.curveT);
  assert.ok(/class="vs-band up"/.test(up) && !/class="vs-band dn"/.test(up));
  const dn = api.chartSvg(PAYLOAD.kospi.curveY, PAYLOAD.kospi.curveT);
  assert.ok(/class="vs-band dn"/.test(dn));
  assert.equal((dn.match(/<path /g) || []).length, 2, '선은 여전히 두 줄');
});

test('A안 — 같은 분에 어제 값이 없는 구간은 띠를 채우지 않는다(§0)', () => {
  const svg = load(kst('2026-09-14T11:00:00')).api.chartSvg([[0, -1]], [[0, 0], [5, 0.2]]);
  assert.ok(!svg.includes('vs-band'));
});

test('A안 — 장이 남았으면 지금 선·남은 장 음영, 15:30이면 없다', () => {
  const { api } = load(kst('2026-09-14T11:00:00'));
  assert.ok(api.chartSvg(WIDE.curveY, WIDE.curveT).includes('class="vs-rest"'));
  assert.ok(!api.chartSvg([[0, -1], [390, -2]], [[0, 0], [390, 1]]).includes('vs-rest'));
});

test('A안 — 세로 눈금·선 끝 값을 그리고, 차이가 크면 괄호와 %p를 단다', () => {
  const ov = load(kst('2026-09-14T11:00:00')).api.chartOverlay(WIDE.curveY, WIDE.curveT, '어제');
  assert.ok(ov.left.includes('>0%<'));
  for (const s of ['−0.50%', '오늘', '−3.00%', '어제']) assert.ok(ov.right.includes(s), `빠짐: ${s}`);
  assert.ok(ov.plot.includes('vs-gap up') && ov.plot.includes('+2.50%p'));
  assert.ok(ov.plot.includes('남은 장'));
});

test('A안 — 두 끝 값이 가까우면 괄호를 빼고 라벨끼리 밀어낸다', () => {
  const ov = load(kst('2026-09-14T11:00:00')).api.chartOverlay(PAYLOAD.kospi.curveY, PAYLOAD.kospi.curveT, '지난 금요일');
  assert.ok(!ov.plot.includes('vs-gap'));
  const tops = [...ov.right.matchAll(/top:([\d.]+)%/g)].map((m) => Number(m[1]));
  assert.ok(Math.abs(tops[0] - tops[1]) >= 19.9, `라벨 간격 ${tops}`);
});

test('A안 — 렌더에 차이 범례·곡선 상자를 넣는다', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  assert.ok(root.innerHTML.includes('class="vs-chartbox"'));
  assert.ok(root.innerHTML.includes('<i class="a"></i>차이'));
});

test('뒤에서 열린 탭 — 로드 땐 요청하지 않고, 보이는 순간 바로 불러온다', () => {
  const calls = [], handlers = {};
  const hooks = {
    hidden: true,
    onDocEvent: (type, fn) => { handlers[type] = fn; },
    fetch: (url) => { calls.push(url); return Promise.reject(new Error('no network')); },
  };
  const { sb } = load(kst('2026-09-15T11:00:00'), [], hooks);
  assert.equal(calls.length, 0, '숨은 탭에서 요청하면 안 된다');
  assert.equal(typeof handlers.visibilitychange, 'function', 'visibilitychange 미등록');
  sb.document.hidden = false;               // 탭이 보이게 됐다
  handlers.visibilitychange();
  assert.equal(calls.length, 1, '보이는 순간 한 번 불러와야 한다');
  assert.match(calls[0], /vs=intraday/);
  sb.document.hidden = true;                // 다시 가려지면 요청하지 않는다
  handlers.visibilitychange();
  assert.equal(calls.length, 1);
});
