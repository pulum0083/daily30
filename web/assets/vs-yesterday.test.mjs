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
  // '오늘이 약함'(옛 외국인 누적 순매수 칸의 판정 배지)은 F2로 뺐다 — 대신 heroWhy 가격 줄의 '더 낮아요'로 확인한다.
  for (const s of ['지난 금요일 11:00 vs 오늘 11:00', '지난 금요일과 비슷해요', '더 낮아요', '−2.56%', '코스피 전체 · 투자자별 누적 순매수', '외국인']) {
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

test('거래량 막대는 상승/하락 색을 쓰지 않는다 — 방향이 없는 양이다', () => {
  const { api } = load();
  const html = api.miniBars(190662, 142592, { zero: false });
  assert.ok(html.includes('mag'), '중립 클래스 없음');
  assert.ok(!/class="[^"]*\b(up|dn)\b/.test(html), '방향 색이 섞임: ' + html);
});

test('수급 짝 막대는 오늘과 어제 값을 함께 적는다', () => {
  const { api } = load();
  const html = api.flowCard({ flow: { main: { 개인: { t: -9641, y: 5538, turned: true },
    외국인: { t: -13443, y: -12029, turned: false }, 기관: { t: 10502, y: -5890, turned: true } },
    inst: [{ key: '금융투자', t: 4226, y: -4336, turned: true }] } });
  assert.ok(html.includes('4,226'), '오늘 값 없음');
  assert.ok(html.includes('4,336'), '어제 값 없음 — 부호 반전이 안 읽힌다');
});

test('섹터 표는 "섹터 평균"이 아니라 "대표 3종목 평균"이라 적는다', () => {
  const { api } = load();
  const html = api.leadCard({ market: { kosdaq: {}, kospi200: {} },
    sectors: [{ key: 'semicon', label: '반도체', names: ['삼성전자', 'SK하이닉스', '한미반도체'],
      t: 2.56, y: -0.57, diff: 3.13, rank: 1, prevRank: 3, move: 2, n: 3 }] });
  assert.ok(html.includes('대표 3종목'), '평균 정의가 안 드러남');
  assert.ok(html.includes('삼성전자'), '대표 종목 이름이 없음');
});

test('축 데이터가 없으면 카드를 그리지 않는다', () => {
  const { api } = load();
  assert.equal(api.heatCard(null), '');
  assert.equal(api.flowCard({ flow: null }), '');
  assert.equal(api.leadCard({ sectors: [] }), '');
});

test('강도·주도권 카드는 데이터가 있으면 코스피 곡선 카드 뒤, 기존 수급 카드 앞 순서로 붙는다', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  const axes = {
    heat: { vol: { t: 142592, y: 190662, diff: -25.23, judge: 'weak' }, amp: { t: 1.75, y: 1.43, diff: 0.32, judge: 'strong' } },
    market: { kosdaq: { t: -0.12, y: 1.02, diff: -1.14, judge: 'weak' }, kospi200: { t: 1.32, y: -0.70, diff: 2.02, judge: 'strong' } },
    sectors: [{ key: 'semicon', label: '반도체', names: ['삼성전자', 'SK하이닉스', '한미반도체'], t: 1.52, y: -0.47, diff: 1.99, rank: 1, prevRank: 3, move: 2, n: 3 }],
    flow: { main: { 개인: { t: -9641, y: 5538, turned: true }, 외국인: { t: -13443, y: -12029, turned: false }, 기관: { t: 10502, y: -5890, turned: true } },
      inst: [{ key: '금융투자', t: 4226, y: -4336, turned: true }] },
  };
  api.render(Object.assign({}, PAYLOAD, { axes }));
  const html = root.innerHTML;
  const iChart = html.indexOf('코스피 · 전일 종가 대비');
  const iHeat = html.indexOf('얼마나 뜨거운가');
  const iLead = html.indexOf('어디가 끄는가');
  const iChanged = html.indexOf('달라진 것');
  const iFlow = html.indexOf('누가 사는가');
  assert.ok(iChart >= 0 && iHeat > iChart, '강도 카드가 곡선 카드 뒤에 있지 않음');
  assert.ok(iLead > iHeat, '주도권 카드가 강도 카드 뒤에 있지 않음');
  assert.ok(iChanged > iLead, '기존 수급 카드가 주도권 카드보다 앞에 있음');
  assert.ok(iFlow > iChanged, '기관 세부 카드가 마지막이 아님');
});

test('기관 세부 막대는 값이 없으면 그리지 않는다 — 0이나 다른 값으로 채우지 않는다', () => {
  const { api } = load();
  const html = api.flowCard({ flow: { inst: [{ key: '단독', t: null, y: -1234, turned: null }] } });
  assert.ok(html.includes('<span class="vsx-bar"></span>'), '값 없는 오늘 칸이 빈 슬롯이 아님: ' + html);
  assert.ok(!/vsx-bar">\s*<i class="up"/.test(html), '값 없는 오늘 칸에 상승 막대가 생김(0으로 채움): ' + html);
  assert.ok(/vsx-bar prev"><i class="dn"/.test(html), '값 있는 어제 막대가 그려지지 않음: ' + html);
});

test('섹터 표는 대표 종목 중 일부가 결측이면 실제 조회된 종목 수를 적는다', () => {
  const { api } = load();
  const html = api.leadCard({ sectors: [{ key: 'auto', label: '자동차', names: ['현대차', '기아'],
    t: -1.2, y: -0.5, diff: -0.7, rank: 2, prevRank: 2, move: 0, n: 2 }] });
  assert.ok(html.includes('대표 2종목'), 'n=2인데 실제 종목 수가 반영되지 않음: ' + html);
  assert.ok(!html.includes('대표 3종목 · 현대차'), '결측인데도 3종목이라 지어냄: ' + html);
  assert.ok(html.includes('대표 3종목 평균'), '표 제목까지 바뀌면 안 됨(고정 문구): ' + html);
});

test('주도권 카드는 코스피 → 코스피200 → 코스닥 순서로 세 칸을 모두 보여준다', () => {
  const { api } = load();
  const kospi = { t: 1.37, y: -0.85, diff: 2.22, judge: 'strong' };
  const axes = {
    market: { kosdaq: { t: 0.44, y: 0.72, diff: -0.28, judge: 'same' }, kospi200: { t: 1.69, y: -0.80, diff: 2.49, judge: 'strong' } },
    sectors: [{ key: 'semicon', label: '반도체', names: ['삼성전자', 'SK하이닉스', '한미반도체'],
      t: 2.56, y: -0.57, diff: 3.13, rank: 1, prevRank: 3, move: 2, n: 3 }],
  };
  const html = api.leadCard(axes, kospi);
  const iK = html.indexOf('>코스피<'), iK2 = html.indexOf('>코스피200<'), iKq = html.indexOf('>코스닥<');
  assert.ok(iK >= 0 && iK2 > iK && iKq > iK2, '코스피 → 코스피200 → 코스닥 순서가 아님: ' + html);
});

// ── 시간대별 표시 규칙(§3.2) ──
test('시간대 경계', () => {
  const { api } = load();
  const d = (s) => new Date(kst(s));
  assert.equal(api.slotOf(d('2026-09-16T07:29:00')), 'night');
  assert.equal(api.slotOf(d('2026-09-16T07:30:00')), 'pre');
  assert.equal(api.slotOf(d('2026-09-16T08:59:00')), 'pre');
  assert.equal(api.slotOf(d('2026-09-16T09:30:00')), 'open');
  assert.equal(api.slotOf(d('2026-09-16T15:30:00')), 'open');
  assert.equal(api.slotOf(d('2026-09-16T15:35:00')), 'close');   // early — 카드는 안 그린다
  assert.equal(api.slotOf(d('2026-09-16T17:00:00')), 'night');
  assert.equal(api.slotOf(d('2026-09-19T12:00:00')), 'weekend'); // 토요일
});

test('장 전엔 카드가 없고 밤엔 강도만', () => {
  const { api } = load();
  // cardsFor는 vm 샌드박스의 Array를 반환한다 — 바깥 realm의 assert.deepEqual과 배열 프로토타입이
  // 달라 참조 비교에서 어긋나므로 Array.from으로 이 realm의 배열로 복사해 비교한다.
  assert.deepEqual(Array.from(api.cardsFor('pre')), []);
  assert.deepEqual(Array.from(api.cardsFor('open')), ['hero', 'heat', 'lead', 'flow']);
  assert.deepEqual(Array.from(api.cardsFor('close')), ['hero', 'heat', 'lead', 'flow']);
  assert.deepEqual(Array.from(api.cardsFor('night')), ['heat']);
  assert.deepEqual(Array.from(api.cardsFor('weekend')), []);
});

test('엔드포인트 선택 — open은 vs=intraday, close·night은 vs=close, pre·weekend는 호출하지 않는다', () => {
  const { api } = load();
  assert.equal(api.endpointFor('open'), '/api/intraday?vs=intraday');
  assert.equal(api.endpointFor('close'), '/api/intraday?vs=close');
  assert.equal(api.endpointFor('night'), '/api/intraday?vs=close');
  assert.equal(api.endpointFor('pre'), null);
  assert.equal(api.endpointFor('weekend'), null);
});

test('night 슬롯은 강도 카드만 그린다 — 결론·곡선·주도권·수급은 없다', () => {
  const { api, root } = load(kst('2026-09-14T20:00:00'));
  const axes = {
    heat: { vol: { t: 142592, y: 190662, diff: -25.23, judge: 'weak' }, amp: { t: 1.75, y: 1.43, diff: 0.32, judge: 'strong' } },
    market: { kosdaq: { t: -0.12, y: 1.02, diff: -1.14, judge: 'weak' }, kospi200: { t: 1.32, y: -0.70, diff: 2.02, judge: 'strong' } },
    sectors: [{ key: 'semicon', label: '반도체', names: ['삼성전자', 'SK하이닉스', '한미반도체'], t: 1.52, y: -0.47, diff: 1.99, rank: 1, prevRank: 3, move: 2, n: 3 }],
    flow: { main: { 개인: { t: -9641, y: 5538, turned: true }, 외국인: { t: -13443, y: -12029, turned: false }, 기관: { t: 10502, y: -5890, turned: true } },
      inst: [{ key: '금융투자', t: 4226, y: -4336, turned: true }] },
  };
  api.render(Object.assign({}, PAYLOAD, { axes }), 'night');
  assert.equal(root.hidden, false);
  assert.ok(root.innerHTML.includes('얼마나 뜨거운가'), '강도 카드가 없음');
  assert.ok(!root.innerHTML.includes('vs-hero'), '결론(hero)이 그려짐');
  assert.ok(!root.innerHTML.includes('class="vs-chartbox"'), '곡선이 그려짐');
  assert.ok(!root.innerHTML.includes('어디가 끄는가'), '주도권 카드가 그려짐');
  assert.ok(!root.innerHTML.includes('누가 사는가'), '수급 심층 카드가 그려짐');
  assert.ok(!root.innerHTML.includes('달라진 것'), '수급(달라진 것) 카드가 그려짐');
});

test('slot이 pre·weekend면(카드 없음) ok 응답이어도 아무것도 그리지 않는다', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD, 'pre');
  assert.equal(root.hidden, true);
  assert.equal(root.innerHTML, '');
  api.render(PAYLOAD, 'weekend');
  assert.equal(root.hidden, true);
  assert.equal(root.innerHTML, '');
});

test('status가 ok가 아니면 어느 슬롯이든 새 카드를 그리지 않는다', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  for (const slot of ['open', 'close', 'night']) {
    root.hidden = false; root.innerHTML = 'x';
    api.render({ status: 'closed' }, slot);
    assert.equal(root.hidden, true, slot);
    assert.equal(root.innerHTML, '', slot);
  }
});

test('주도권 카드 — 응답에 코스피가 없으면 그 칸만 뺀다(지어내지 않는다)', () => {
  const { api } = load();
  const axes = {
    market: { kosdaq: { t: 0.44, y: 0.72, diff: -0.28, judge: 'same' }, kospi200: {} },
    sectors: [{ key: 'semicon', label: '반도체', names: ['삼성전자', 'SK하이닉스', '한미반도체'],
      t: 2.56, y: -0.57, diff: 3.13, rank: 1, prevRank: 3, move: 2, n: 3 }],
  };
  const html = api.leadCard(axes);
  assert.ok(!html.includes('>코스피<'), '코스피 데이터가 없는데 칸이 생김: ' + html);
  assert.ok(html.includes('>코스닥<'), '있는 데이터(코스닥)까지 같이 빠짐: ' + html);
});

// ── F2: 결론 카드는 승인 시안대로 근거 4줄(.vsx-why)을 그린다 ──

test('결론 근거 4줄 — 가격·강도·주도권·누가를 그리고, 오늘 코스피 절대값은 다시 적지 않는다(F2)', () => {
  const { api } = load();
  const axes = {
    heat: { vol: { t: 142592, y: 190662, diff: -25.23, judge: 'weak' }, amp: { t: 1.75, y: 1.43, diff: 0.32, judge: 'strong' } },
    sectors: [
      { key: 'semicon', label: '반도체', names: ['삼성전자', 'SK하이닉스', '한미반도체'], t: 1.52, y: -0.47, diff: 1.99, rank: 1, prevRank: 3, move: 2, n: 3 },
      { key: 'battery', label: '2차전지', names: ['LG에너지솔루션', '에코프로비엠', '삼성SDI'], t: -0.30, y: 1.80, diff: -2.10, rank: 4, prevRank: 1, move: -3, n: 3 },
    ],
    flow: { main: { 개인: { t: -9641, y: 5538, turned: true }, 외국인: { t: -13443, y: -12029, turned: false }, 기관: { t: 10502, y: -5890, turned: true } }, inst: [] },
  };
  const d = Object.assign({}, PAYLOAD, { axes });
  const html = api.heroWhy(d, 'open');
  const lis = html.match(/<li>/g) || [];
  assert.equal(lis.length, 4, '근거 줄이 4개가 아님: ' + html);
  assert.ok(html.includes('−2.42%'), '어제 코스피 값(d.kospi.y)이 없음: ' + html);
  assert.ok(html.includes('−0.14%p'), '코스피 차이(d.kospi.diff)가 없음: ' + html);
  assert.ok(!html.includes('−2.56%'), '오늘 코스피 절대값(d.kospi.t)을 다시 적음: ' + html);
  assert.ok(html.includes('반도체'), '주도권 — 오늘 1위(어제 3위)가 안 보임: ' + html);
  assert.ok(html.includes('2차전지'), '주도권 — 어제 1위였던 섹터의 하락이 안 보임: ' + html);
  assert.ok(html.includes('190,662천주'), '강도 — 어제 거래량이 없음: ' + html);
  assert.ok(html.includes('1.75%') && html.includes('1.43%'), '강도 — 오늘·어제 진폭이 없음: ' + html);
  // 계사(이었어요)는 </b> 태그 바깥에 붙는다 — 값 자체는 <b>로 감싸므로 태그를 포함해 확인한다.
  assert.ok(html.includes('5,890억</b>이었어요'), '누가 — 억 단위 계사(이었어요)가 틀림: ' + html);
  assert.ok(html.includes('1.05조'), '누가 — 오늘 기관 순매수가 없음: ' + html);
});

test('결론 근거 — 축 데이터가 일부 없으면 그 줄만 빠진다(F2)', () => {
  const { api } = load();
  const axes = { heat: { vol: { t: 142592, y: 190662, diff: -25.23, judge: 'weak' }, amp: { t: 1.75, y: 1.43, diff: 0.32, judge: 'strong' } } };
  // sectors·flow 없음 — 주도권·누가 줄은 없어야 한다.
  const html = api.heroWhy(Object.assign({}, PAYLOAD, { axes }), 'open');
  assert.ok(html.includes('<span class="k">가격</span>'), '가격 줄이 없음');
  assert.ok(html.includes('<span class="k">강도</span>'), '강도 줄이 없음');
  assert.ok(!html.includes('<span class="k">주도권</span>'), '섹터 데이터가 없는데 주도권 줄이 생김');
  assert.ok(!html.includes('<span class="k">누가</span>'), '수급 데이터가 없는데 누가 줄이 생김');
});

test('결론 근거 — 입력이 하나도 없으면 빈 문자열을 낸다(§0)', () => {
  const { api } = load();
  assert.equal(api.heroWhy({ prev: { rel: '어제' }, kospi: {} }, 'open'), '');
});

test('결론 근거 — close·night 슬롯은 "이 시각"이 아니라 "어제는"(하루 전체) 표현을 쓴다(F2)', () => {
  const { api } = load();
  const d = Object.assign({}, PAYLOAD);
  assert.ok(api.heroWhy(d, 'open').includes('지난 금요일 이 시각엔'), 'open 표현이 없음');
  assert.ok(api.heroWhy(d, 'close').includes('지난 금요일는'), 'close 표현이 없음');
  assert.ok(!api.heroWhy(d, 'close').includes('이 시각엔'), 'close인데 이 시각 표현이 남음');
});

test('였어요/이었어요 계사 — eok가 내는 조(받침 없음)·억(받침 있음)에 맞춘다', () => {
  const { api } = load();
  assert.equal(api.wasKo('−5,890억'), '이었어요', '억(받침 있음)인데 였어요를 씀');
  assert.equal(api.wasKo('+1.20조'), '였어요', '조(받침 없음)인데 이었어요를 씀');
});

test('결론 카드에서 예전 3칸(오늘 코스피·외국인 누적·주도주 평균)이 빠진다(F2)', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);   // axes 없음 — heat/lead/flow(신규) 카드는 안 그려진다
  assert.ok(!root.innerHTML.includes('<span>코스피</span>'), '옛 코스피 칸이 남음');
  assert.ok(!root.innerHTML.includes('<span>외국인 누적 순매수</span>'), '옛 외국인 칸이 남음');
  assert.ok(!root.innerHTML.includes('<span>주도주 3종목 평균</span>'), '옛 주도주 평균 칸이 남음');
  assert.ok(root.innerHTML.includes('vsx-why'), '근거 목록(.vsx-why)이 없음');
});

test('수급 카드 — close·night 슬롯이면 라벨이 "정규장 확정 15:40"으로 바뀐다(F2)', () => {
  const { api } = load();
  const flow = { flow: { main: { 개인: { t: -9641, y: 5538, turned: true } }, inst: [] } };
  assert.ok(api.flowCard(flow).includes('새 축 · 수급 심층'), '기본(open) 라벨이 안 나옴');
  assert.ok(api.flowCard(flow, 'open').includes('새 축 · 수급 심층'), 'open 라벨이 안 나옴');
  assert.ok(api.flowCard(flow, 'close').includes('정규장 확정 15:40'), 'close 라벨이 안 바뀜');
  assert.ok(api.flowCard(flow, 'night').includes('정규장 확정 15:40'), 'night 라벨이 안 바뀜');
});

// ── F4: 새 카드 함수는 인라인 static 레이아웃 스타일을 쓰지 않는다 ──

test('강도·주도권·수급 카드는 인라인 grid-template-columns를 쓰지 않는다(F4)', () => {
  const { api } = load();
  const heat = api.heatCard({ heat: { vol: { t: 142592, y: 190662, diff: -25.23, judge: 'weak' }, amp: { t: 1.75, y: 1.43, diff: 0.32, judge: 'strong' } } });
  const lead = api.leadCard({ sectors: [{ key: 'semicon', label: '반도체', names: ['삼성전자', 'SK하이닉스', '한미반도체'],
    t: 1.52, y: -0.47, diff: 1.99, rank: 1, prevRank: 3, move: 2, n: 3 }] });
  const flow = api.flowCard({ flow: { main: { 개인: { t: -9641, y: 5538, turned: true } }, inst: [] } });
  for (const [name, html] of [['heat', heat], ['lead', lead], ['flow', flow]]) {
    assert.ok(html.length > 0, `${name} 카드가 비어 테스트 자체가 무의미함`);
    assert.ok(!/style="[^"]*grid-template-columns/.test(html), `${name} 카드에 인라인 grid-template-columns가 남음: ` + html);
  }
});
