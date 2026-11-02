// home-hero.js 시간대 판정·카드 회귀 테스트 — node:vm 샌드박스에서 실제 파일을 로드한다(§68)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';

const noop = () => {};
function load(hooks = {}) {
  const root = { hidden: true, innerHTML: '' };
  const cl = new Set();
  const home = { classList: { toggle: (c, on) => (on ? cl.add(c) : cl.delete(c)) } };
  const sb = {
    document: { getElementById: (id) => (id === 'home-hero' ? (hooks.noRoot ? null : root) : id === 'home' ? home : null),
                hidden: false, addEventListener: noop },
    location: { search: hooks.search || '' }, URLSearchParams,
    fetch: hooks.fetch || (() => Promise.reject(new Error('no network'))),
    setInterval: noop, console: { log: noop, warn: noop, error: noop }, Date, Math, JSON, String, Number, Promise,
  };
  sb.window = sb;
  runInContext(readFileSync(new URL('./home-hero.js', import.meta.url), 'utf8'), createContext(sb));
  return { api: sb.window.__homeHero, root, cl, sb };
}
const kst = (s) => new Date(Date.parse(s + 'Z') - 9 * 3600 * 1000);
const { api } = load({ noRoot: true });
const slot = (s, o) => { const r = api.homeSlot(kst(s), o); return r.slot + ' ' + r.date; };

test('평일 경계 — 07:29/07:30, 08:59/09:00, 15:30/15:31', () => {
  assert.equal(slot('2026-10-27T07:29:00'), 'evening 2026-10-26');   // 화 07:29 → 월요일 밤 미국 브리핑
  assert.equal(slot('2026-10-27T07:30:00'), 'morning 2026-10-27');
  assert.equal(slot('2026-10-27T08:59:00'), 'morning 2026-10-27');
  assert.equal(slot('2026-10-27T09:00:00'), 'intraday 2026-10-27');
  assert.equal(slot('2026-10-27T15:30:00'), 'intraday 2026-10-27');
  assert.equal(slot('2026-10-27T15:31:00'), 'close 2026-10-27');
});

test('미국 브리핑 발행 전후 — 발행되면 미국 카드', () => {
  const ready = { usReady: (d) => d === '2026-10-27' };
  assert.equal(slot('2026-10-27T21:20:00'), 'close 2026-10-27');
  assert.equal(slot('2026-10-27T21:20:00', ready), 'evening 2026-10-27');
  assert.equal(slot('2026-10-27T23:59:00', ready), 'evening 2026-10-27');
});

test('주말 — 토 07:30 전은 금요일 밤 미국, 그 뒤·일요일·월 07:30 전은 이번 주 정리', () => {
  assert.equal(slot('2026-10-31T07:29:00'), 'evening 2026-10-30');
  assert.equal(slot('2026-10-31T07:30:00'), 'weekend 2026-10-31');
  assert.equal(slot('2026-11-01T12:00:00'), 'weekend 2026-11-01');
  assert.equal(slot('2026-11-02T07:29:00'), 'weekend 2026-11-02');   // 일요일 밤엔 미국 브리핑이 없다
  assert.equal(slot('2026-11-02T07:30:00'), 'morning 2026-11-02');
});

test('한국 휴장일 — 코스피 카드는 빼고 미국 브리핑이 나오면 미국 카드(§13)', () => {
  const hol = { krHoliday: (d) => d === '2026-12-25' };
  assert.equal(slot('2026-12-25T08:00:00', hol), 'weekend 2026-12-25');
  assert.equal(slot('2026-12-25T10:00:00', hol), 'weekend 2026-12-25');
  assert.equal(slot('2026-12-25T21:30:00', { ...hol, usReady: () => true }), 'evening 2026-12-25');
  assert.equal(slot('2026-12-26T07:00:00', hol), 'evening 2026-12-25');  // 휴장일 다음 날 07:30 전(토)
});

const KSNAP = { generated_at: '2026-10-23T07:29:20+09:00',
  prediction: { direction: '하락 우위', up_pct: 7, down_pct: 93, confidence: 82, basis: 'open' },
  todays_view: { view_title: '메타發 AI 투자 공포', dek: '어제 코스피가 <b>-3.52%</b> 급락했어요.<script>x</script>' } };

test('아침 카드 — 스냅샷 그대로, 큰 확률·신뢰도·신뢰 한 줄', () => {
  const h = api.cardMorning(KSNAP, '2026-10-23', '2026-10-23', { basis: 'open', scored: 9, hit: 7, pct: 78 }, { time: '07:29' });
  for (const s of ['오늘 07:29 · 코스피 시초가 예측', '새 브리핑', '↓ 하락 우위', '93%', '신뢰도 82%', '메타發 AI 투자 공포',
                   '<b>-3.52%</b>', '/briefings/2026-10-23/kospi/', '시초가 예측 적중 <b>7/9</b> (78%)', '07:25·16:25·21:15']) assert.ok(h.includes(s), s);
  assert.ok(!h.includes('<script>'), 'dek의 <b> 말고는 이스케이프');
});

test('아침 카드 — 채점 5건 미만이면 신뢰 한 줄 없음, 헤드라인 없으면 카드 없음', () => {
  assert.ok(!api.cardMorning(KSNAP, '2026-10-23', '2026-10-23', { basis: 'open', scored: 4, hit: 4, pct: 100 }).includes('적중'));
  assert.equal(api.cardMorning({ prediction: KSNAP.prediction, todays_view: {} }, '2026-10-23', '2026-10-23'), '');
});

test('마감 카드 — 제목(market_title→reason_title), 아침 예측 채점 칩', () => {
  const sum = { scores: [{ date: '2026-10-23', direction: '하락 우위', open_pct: -2.36, ok: true }] };
  const h = api.cardClose({ reason_title: '장 초반 4% 급락한 코스피, 어떻게 버텼나', generated_at: '2026-10-23T16:32:00+09:00' },
                          '2026-10-23', '2026-10-23', sum);
  for (const s of ['오늘 16:32 · 코스피 마감', '장 초반 4% 급락한 코스피', '📝 아침 시초가 예측 하락 우위', '−2.36%', '✓ 적중', '/briefings/2026-10-23/close/'])
    assert.ok(h.includes(s), s);
  assert.equal(api.morningChip(sum, '2026-10-22'), '');           // 그날 기록이 없으면 칩을 뺀다
});

test('미국 카드 — 큰 쪽 확률·나스닥 체크 칩, 다른 날이면 날짜 표기', () => {
  const us = { generated_at: '2026-10-23T21:17:00+09:00', prediction: { up_pct: 32, down_pct: 68 },
               todays_view: { view_title: '반도체가 먼저 맞았다', dek: '직전 정규장에서…' }, nasdaq_overheat: { gap_pct: 72.4 } };
  const h = api.cardEvening(us, '2026-10-23', '2026-10-24');
  for (const s of ['10/23(금) 21:17 · 미국 시장 브리핑', '↓ 하락 우위', '68%', '반도체가 먼저 맞았다', '나스닥 체크 <b>+72.4%</b> · 🚨 경고', '/briefings/2026-10-23/us/'])
    assert.ok(h.includes(s), s);
  assert.ok(!h.includes('새 브리핑'));
  // 정상(65% 미만)은 칩을 달지 않는다 — 미국 브리핑 페이지와 같다(§65)
  assert.ok(api.nasdaqChip({ gap_pct: 64.9 }) === '' && api.nasdaqChip({ gap_pct: 65 }).includes('⚠️ 주의'));
});

test('오늘 브리핑이 ready가 아니면 옛 날짜로 대체하지 않고 카드를 뺀다', async () => {
  const list = { slots: { '2026-10-26': { kospi: { state: 'pending' } }, '2026-10-23': { kospi: { state: 'ready' } } } };
  const t = load({ search: '?slot=morning&d=2026-10-26',
                   fetch: (u) => Promise.resolve({ ok: true, json: () => Promise.resolve(u.includes('briefings-list') ? list : {}) }) });
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(t.root.hidden, true);
  assert.ok(!t.cl.has('hero-on'));
});

// ── 구조 신호(§68 ⑤) ───────────────────────────────────────────────────
test('구조 신호 — 가장 최근 ready 날짜만, 10일보다 오래되면 뺀다(옛 날짜로 거슬러 가지 않는다)', () => {
  const slots = { '2026-10-23': { us: { state: 'ready' }, kospi: { state: 'ready' } },
                  '2026-10-26': { us: { state: 'pending' }, kospi: { state: 'ready' } } };
  assert.equal(api.latestReady(slots, 'kospi', '2026-10-26'), '2026-10-26');
  assert.equal(api.latestReady(slots, 'us', '2026-10-26'), '2026-10-23');
  assert.equal(api.latestReady(slots, 'us', '2026-11-05'), null);          // 13일 전 발행 — 수집이 멈춘 것으로 본다
  assert.equal(api.latestReady({}, 'us', '2026-10-26'), null);
});

test('나스닥 체크 — 65·70 눈금과 단계, 값이 없으면 줄을 뺀다', () => {
  const ok = api.nasdaqRow({ gap_pct: 59.79, month: '2026-10' }, '2026-10-23', '2026-10-26');
  assert.match(ok, /\+59\.8%/);
  assert.match(ok, /pill ok">✓ 정상/);
  assert.match(ok, /65 주의/);
  assert.match(ok, /70 경고/);
  assert.match(ok, /href="\/stocks\/nasdaq-check\/"/);          // 상세 페이지로 간다(2026-10-28)
  assert.match(ok, /class="ss-go">상세 그래프 ›/);
  assert.doesNotMatch(ok, /미국 브리핑/);                              // 브리핑 날짜 라벨은 뺐다(2026-10-28)
  assert.match(api.nasdaqRow({ gap_pct: 64 }, '2026-10-23', '2026-10-23'), /pill ok">✓ 정상/);
  assert.match(api.nasdaqRow({ gap_pct: 65 }, '2026-10-23', '2026-10-23'), /pill caution">⚠️ 주의/);
  assert.match(api.nasdaqRow({ gap_pct: 71.2 }, '2026-10-23', '2026-10-23'), /pill warn">🚨 경고/);
  assert.equal(api.nasdaqRow(null, '2026-10-23', '2026-10-26'), '');
  assert.equal(api.nasdaqRow({ gap_pct: null }, '2026-10-23', '2026-10-26'), '');
});

test('월봉 5개월선 — 최근 6개월 막대(안착 구간·이번 달 표시), 종목이 없으면 줄째 뺀다', () => {
  const strip = ['5월', '6월', '7월', '8월', '9월', '10월', '이번 달'].map((label, i) =>
    ({ label, gap_pct: [-9.69, -5.49, 11.59, 7.87, 8.69, 3.1, 5.46][i], run: i >= 2 && i <= 4, cur: i === 6 }));
  const m5 = { items: [{ name: '메리츠금융지주', streak: 3, now_gap_pct: 5.46, strip }, { name: 'B', streak: 3, strip: [] }] };
  const h = api.ma5Row(m5, '2026-10-26', '2026-10-26');
  assert.equal((h.match(/class="m5b[ "]/g) || []).length, 6);                  // 7개 중 최근 6개월
  assert.equal((h.match(/class="m5b run/g) || []).length, 3);              // 7·8·9월(5월이 잘린다)
  assert.match(h, /class="m5b cur"/);
  assert.match(h, /메리츠금융지주 외 1종목/);
  assert.match(h, /3개월째/);
  assert.match(h, /지금 이격 \+5\.5%/);
  assert.ok(!/매매 신호/.test(h));
  assert.equal(api.ma5Row({ items: [] }, '2026-10-26', '2026-10-26'), '');                       // 빈 문구 없이 줄째 뺀다
  assert.equal(api.ma5Row(null, '2026-10-26', '2026-10-26'), '');
});

test('구조 신호 블록 — 두 줄 모두 없으면 블록째 뺀다', () => {
  assert.equal(api.structHtml(null, null, null, null, '2026-10-26'), '');
  assert.equal(api.structHtml(null, '2026-10-23', { items: [] }, '2026-10-26', '2026-10-26'), '');   // 나스닥 값 없음 + 종목 없음
  assert.match(api.structHtml({ gap_pct: 59.8 }, '2026-10-23', { items: [] }, '2026-10-26', '2026-10-26'), /구조 신호/);
});

// ── 미국 지수 · 200일선 대비(밤 구조 신호) ─────────────────────────────
const POS = { asof: '2026-10-30', items: [{ name: 'S&P500', pct: 3.7 }, { name: '나스닥', pct: 1.52 }, { name: '다우', pct: 2.3 }, { name: '반도체', pct: -0.86 }] };
test('미국 지수 줄 — 네 지수·위/아래 태그·200일선 표기·기준일', () => {
  const h = api.usIndexRow(POS);
  assert.equal((h.match(/class="uip-r"/g) || []).length, 4);
  assert.match(h, /미국 지수 · 200일선 대비/);
  assert.match(h, /10\/30\(금\) 종가/);
  assert.match(h, /<b>S&amp;P500 \+3\.70%<\/b>/);
  assert.equal((h.match(/pill above">위</g) || []).length, 3);
  assert.equal((h.match(/pill below">아래</g) || []).length, 1);
  assert.match(h, /−5%<\/span><span class="m">200일선<\/span><span>\+5%/);
  assert.match(h, /class="dn" style="width:8\.6%"/);                  // 0.86 ÷ 5 × 50
});
test('미국 지수 줄 — 눈금은 가장 벌어진 지수에 맞춰 넓어지고, 값이 없으면 줄을 뺀다', () => {
  assert.match(api.usIndexRow({ asof: '2026-10-30', items: [{ name: '반도체', pct: -7.2 }] }), /−10%<\/span>/);
  assert.equal(api.usIndexRow(null), '');
  assert.equal(api.usIndexRow({ asof: '2026-10-30', items: [] }), '');
  assert.equal(api.usIndexRow({ items: [{ name: '다우', pct: 1 }] }), '');   // 기준일 없으면 쓰지 않는다
});
test('구조 신호 — 밤엔 국내 월봉 줄 대신 미국 지수 줄, 머리글에서 월봉 기준을 뺀다', () => {
  const h = api.structHtml({ gap_pct: 59.9 }, '2026-10-30', null, null, '2026-10-30', POS);
  assert.match(h, /나스닥 체크/);
  assert.match(h, /200일선 대비/);
  assert.doesNotMatch(h, /월봉 5개월선/);
  assert.match(h, />매일 업데이트</);
  assert.match(api.structHtml({ gap_pct: 59.9 }, '2026-10-30', null, null, '2026-10-30', null), /월봉 기준 · 매일 업데이트/);
});

// ── 코스피 체크 ─────────────────────────────────────────────────────
const KC = { asof: '2026-11-02', gap_pct: 72.1, since: '2001-11', months: 301, above: 15, year_max: { m: '2026-05', gap: 178.6 }, prev_max: { m: '2007-10', gap: 87.5 } };
test('코스피 체크 — 값·과거 최고 눈금·과거 위치, 판정 표시는 없다', () => {
  const h = api.kospiRow(KC, '2026-11-03');
  assert.match(h, /코스피 체크/);
  assert.match(h, /11\/2\(월\) 종가/);
  assert.match(h, /<b>\+72\.1%<\/b>/);
  assert.match(h, /2007년 \+88%/);
  assert.match(h, /올해 \+179%/);
  assert.equal((h.match(/class="mk"/g) || []).length, 2);
  assert.match(h, /2001년 이후 301개월 중 지금보다 높았던 달 15개월/);
  assert.doesNotMatch(h, /정상|주의|경고|class="pill/);
  assert.match(h, /class="dot n" style="left:36\.[01]%"/);            // 72.1 ÷ 200
});
test('코스피 체크 — 옛 값·빈 값은 줄을 빼고, 가까운 눈금 글자는 높은 쪽만 남긴다', () => {
  assert.equal(api.kospiRow(KC, '2026-11-20'), '');                   // 10일 넘게 멈춘 값
  assert.equal(api.kospiRow(null, '2026-11-03'), '');
  assert.equal(api.kospiRow({ ...KC, gap_pct: null }, '2026-11-03'), '');
  const near = api.kospiRow({ ...KC, year_max: { m: '2027-01', gap: 100 }, prev_max: { m: '2026-05', gap: 110 } }, '2026-11-03');
  assert.match(near, /2026년 \+110%/);
  assert.doesNotMatch(near, /올해/);
  assert.equal((near.match(/class="mk"/g) || []).length, 1);
  const first = api.kospiRow({ ...KC, prev_max: null, year_max: { m: '2026-05', gap: 178.6 } }, '2026-11-03');
  assert.match(first, /올해 \+179%/);                                   // 이전 해 기록이 없어도 그린다
});
test('구조 신호 — 아침은 코스피 체크 + 월봉, 주말은 나스닥까지 세 줄, 밤엔 코스피 체크를 그리지 않는다', () => {
  const m5 = { items: [{ name: '삼성화재', streak: 6, strip: [] }] };
  const am = api.structHtml(null, null, m5, '2026-11-02', '2026-11-02', null, KC);
  assert.ok(am.indexOf('코스피 체크') < am.indexOf('월봉 5개월선'));
  assert.doesNotMatch(am, /나스닥 체크/);
  const wk = api.structHtml({ gap_pct: 59.9 }, '2026-11-02', m5, '2026-11-02', '2026-11-02', null, KC);
  assert.ok(wk.indexOf('나스닥 체크') < wk.indexOf('코스피 체크') && wk.indexOf('코스피 체크') < wk.indexOf('월봉 5개월선'));
  const pm = api.structHtml({ gap_pct: 59.9 }, '2026-11-02', null, null, '2026-11-02', POS, null);
  assert.doesNotMatch(pm, /코스피 체크|월봉 5개월선/);
});

// ── 주말 카드(§68 ⑥) ───────────────────────────────────────────────────
const SUM = {
  kospi_days: [
    { date: '2026-10-16', close: 5668.0, pct: 0.5, open_pct: 0.1 },
    { date: '2026-10-19', close: 5767.8, pct: 1.76, open_pct: 0.4 },
    { date: '2026-10-20', close: 5552.7, pct: -3.73, open_pct: -1.0 },
    { date: '2026-10-21', close: 5735.66, pct: 3.29, open_pct: 1.2 },
    { date: '2026-10-22', close: 5533.77, pct: -3.52, open_pct: -1.14 },
    { date: '2026-10-23', close: 5550.3, pct: 0.3, open_pct: -2.36 }],
  scores: [{ date: '2026-10-16', ok: true }, { date: '2026-10-22', ok: false }, { date: '2026-10-23', ok: true }],
  sectors_week: [{ key: 'ship', label: '조선', pct: 4.12, n: 5 }, { key: 'bio', label: '바이오', pct: -1 }],
};

test('주말 카드 — 계단 그림·헤드라인(시작→끝 종가·가장 큰 하루), 주간 등락·이번 주 예측 성적·가장 강한 섹터', () => {
  const h = api.cardWeekend(SUM, '2026-10-24', '2026-10-24', false);
  assert.match(h, /이번 주 정리 · 10\/19~10\/23/);
  assert.match(h, />주말</);
  assert.match(h, /5,668 → 5,550, 화요일 하루에 <span class="dn">−215p<\/span>/);   // 5552.7 − 5767.8
  assert.doesNotMatch(h, /\+1\.76% → −3\.73%/);                                   // 옛 화살표 나열 문장은 없다
  assert.match(h, /<div class="hh-steps"[^>]*><div class="st-plot"/);
  assert.match(h, /<b class="dn">−2\.08%<\/b>/);                         // 5550.3 / 5668 - 1
  assert.match(h, /5,668 → 5,550/);
  assert.match(h, /<b>1\/2<\/b>/);                                       // 10/16은 지난 주라 빠진다
  assert.match(h, /조선/);
  assert.match(h, /5거래일 중 3일 오르고 2일 내려/);
  assert.match(h, /href="\/briefings\/"/);
});

test('주말 카드 — 휴장 표기, 지난 주 요약이면·직전 주 종가가 없으면 카드 없음', () => {
  assert.match(api.cardWeekend(SUM, '2026-10-26', '2026-10-26', true), />휴장</);
  assert.equal(api.cardWeekend(SUM, '2026-11-02', '2026-11-02', false), '');   // 10일 지난 요약
  const noPrev = { kospi_days: SUM.kospi_days.slice(1) };
  assert.equal(api.cardWeekend(noPrev, '2026-10-24', '2026-10-24', false), '');
  assert.equal(api.cardWeekend(null, '2026-10-24', '2026-10-24', false), '');
});

test('주말 계단 그림 — 지난주 종가·요일 막대 5개·이번 주 종가, 막대 색은 그날 오르내림', () => {
  const week = SUM.kospi_days.slice(1), prev = SUM.kospi_days[0];
  const svg = api.weekSteps(prev, week);
  assert.equal((svg.match(/class="st-b /g) || []).length, 5);
  assert.equal((svg.match(/class="st-b up"/g) || []).length, 3);
  assert.equal((svg.match(/class="st-b dn"/g) || []).length, 2);
  assert.match(svg, /<b>지난주<\/b>/);
  assert.match(svg, /<b>이번 주<\/b>/);
  assert.match(svg, />5,668<\/span>/);
  assert.match(svg, />5,550<\/span>/);
  assert.match(svg, /class="st-p dn u"[^>]*>−3\.73%</);
  assert.match(svg, /<b>월<\/b>.*<b>금<\/b>/);
  assert.doesNotMatch(svg, /<svg/);                       // SVG는 PC 폭에서 글자까지 커진다
  // 휴장으로 거래일이 적은 주도 그 수만큼만 그린다
  assert.equal((api.weekSteps(prev, week.slice(0, 3)).match(/class="st-b /g) || []).length, 3);
});

test('주말 헤드라인 — 첫날이 가장 크면 지난주 종가 대비 포인트', () => {
  const prev = { date: '2026-10-23', close: 5550.3 };
  const week = [{ date: '2026-10-26', close: 5469.47, pct: -1.46 }, { date: '2026-10-27', close: 5490, pct: 0.38 }];
  assert.equal(api.weekStepHead(prev, week), '5,550 → 5,490, 월요일 하루에 <span class="dn">−81p</span>');
});
