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
  // 정상(60% 미만)은 칩을 달지 않는다 — 미국 브리핑 페이지와 같다(§65)
  assert.ok(api.nasdaqChip({ gap_pct: 59.9 }) === '' && api.nasdaqChip({ gap_pct: 60 }).includes('⚠️ 주의'));
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

test('장기 신호 · 나스닥 체크 — 단계 알약·설명·미니 게이지, 상세 페이지로 간다, 값이 없으면 줄을 뺀다', () => {
  const ok = api.nasdaqRow({ gap_pct: 48.92 });
  assert.match(ok, /href="\/stocks\/nasdaq-check\/"/);
  assert.match(ok, /\+48\.9%<span class="pill ok">✓ 정상/);
  assert.match(ok, /주의 기준 60%보다 아래예요/);
  assert.match(api.nasdaqRow({ gap_pct: 60 }), /pill caution">⚠️ 주의[\s\S]*주의 구간/);
  assert.match(api.nasdaqRow({ gap_pct: 71.2 }), /pill warn">🚨 경고[\s\S]*경고 구간/);
  assert.equal(api.nasdaqRow(null), '');
  assert.equal(api.nasdaqRow({ gap_pct: null }), '');
});

test('장기 신호 · 나스닥 체크 — 기준일을 적고, 홈 파일과 스냅샷 중 더 최근 것을 쓴다(2026-11-09)', () => {
  assert.match(api.nasdaqRow({ gap_pct: 48.92, asof: '2026-11-06' }, '2026-11-09'), /<em>11\/6\(금\) 종가<\/em>/);
  assert.match(api.nasdaqRow({ gap_pct: 48.96, last_date: '2026-11-05' }, '2026-11-09'), /11\/5\(목\) 종가/);
  assert.equal(api.nasdaqRow({ gap_pct: 48.9, asof: '2026-10-20' }, '2026-11-09'), '');   // 10일 넘게 멈췄으면 뺀다
  const home = { gap_pct: 48.92, asof: '2026-11-06' }, snap = { gap_pct: 48.96, last_date: '2026-11-05' };
  assert.equal(api.pickNasdaq(home, snap), home);
  assert.equal(api.pickNasdaq({ gap_pct: 50, asof: '2026-11-04' }, snap), snap);
  assert.equal(api.pickNasdaq(null, snap), snap);
  assert.equal(api.pickNasdaq(home, null), home);
});

const SPH = { asof: '2026-11-06', pct: 58.8, week: { d: '10/30', pct: 61.6 }, median_all: 66.3, hot: 3, deep: 40, spark: [60, 62, 61, 58.8] };
test('장기 신호 · S&P 500 — 비율·한 주 전·보통 대비·과열/20%↓, 기준일, 상세 페이지', () => {
  const h = api.sp500Row(SPH, '2026-11-08');
  assert.match(h, /href="\/stocks\/sp500-200\/"/);
  assert.match(h, /11\/6\(금\) 종가/);
  assert.match(h, /58\.8%<small>한 주 전 61\.6%<\/small>/);
  assert.match(h, /보통\(66\.3%\)보다 낮아요 · 과열 3개, 20%↓ 40개/);
  assert.match(h, /<svg/);
  assert.match(api.sp500Row({ ...SPH, pct: 66.8 }, '2026-11-08'), /비슷해요/);
  assert.equal(api.sp500Row(SPH, '2026-11-20'), '');                 // 10일 넘게 멈춘 값
  assert.equal(api.sp500Row(null, '2026-11-08'), '');
});

// ── 코스피 체크 ─────────────────────────────────────────────────────
const KC_SERIES = [];
for (let y = 2001; y <= 2026; y++) for (let m = 1; m <= 12; m++) {
  const k = `${y}-${String(m).padStart(2, '0')}`;
  if (k < '2001-11' || k > '2026-11') continue;
  KC_SERIES.push([k, k === '2007-10' ? 87.5 : k === '2026-05' ? 178.6 : k === '2026-11' ? 49.2 : 10]);
}
const KC = { asof: '2026-11-06', gap_pct: 49.2, since: '2001-11', months: 301, above: 39, year_max: { m: '2026-05', gap: 178.6 }, prev_max: { m: '2007-10', gap: 87.5 }, series: KC_SERIES };
test('장기 신호 · 코스피 체크 — 거리·올해 꼭대기에서 좁혀진 설명·25년 작은 그래프, 판정 없음', () => {
  const h = api.kospiRow(KC, '2026-11-08');
  assert.match(h, /href="\/stocks\/kospi-check\/"/);
  assert.match(h, /11\/6\(금\) 종가/);
  assert.match(h, /\+49\.2%/);
  assert.match(h, /올해 5월 \+178\.6%에서 좁혀졌어요/);
  assert.doesNotMatch(h, /정상|주의|경고|class="pill/);
  assert.match(api.kospiRow({ ...KC, gap_pct: 178.6, year_max: { m: '2026-11', gap: 178.6 } }, '2026-11-08'), /올해 들어 가장 멀어요/);
  assert.equal(api.kospiRow(KC, '2026-11-20'), '');
  assert.equal(api.kospiRow(null, '2026-11-03'), '');
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

test('장기 신호 블록 — 나스닥 → S&P 500 → 코스피 → 월봉 순, 주간 리포트 링크, 줄이 없으면 블록째 뺀다', () => {
  const m5 = { items: [{ name: '삼성화재', streak: 6, strip: [] }] };
  const h = api.structHtml({ gap_pct: 48.9 }, SPH, KC, m5, '2026-11-06', '2026-11-08');
  const at = (s) => h.indexOf(s);
  assert.ok(at('나스닥 체크') < at('S&amp;P 500') && at('S&amp;P 500') < at('코스피 체크') && at('코스피 체크') < at('월봉 5개월선'));
  assert.match(h, /장기 신호/);
  assert.match(h, /href="\/weekly\/">주간 장기 리포트 ›/);
  assert.doesNotMatch(h, /구조 신호|200일선 대비/);
  assert.equal(api.structHtml(null, null, null, { items: [] }, '2026-11-06', '2026-11-08'), '');
  assert.doesNotMatch(api.structHtml({ gap_pct: 48.9 }, null, null, null, null, '2026-11-08'), /S&amp;P|코스피 체크/);
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

// 미국 지수 요일 계단(2026-11-09) — 주간 장기 리포트 data.json의 idx를 읽는다
const WK = { end: '2026-10-23', monday: '2026-10-19', idx: {
  '^GSPC': [['2026-10-16', 100], ['2026-10-19', 101], ['2026-10-20', 99.99], ['2026-10-22', 98], ['2026-10-23', 99]],   // 10/21 휴장
  '^SOX': [['2026-10-16', 100], ['2026-10-23', 90]] } };

test('주말 카드 — 주간 리포트가 있으면 미국 지수 요일 계단과 리포트 링크가 붙는다', () => {
  const h = api.cardWeekend(SUM, '2026-10-24', '2026-10-24', false, WK);
  assert.match(h, /미국 지수 · 이번 주/);
  assert.ok(h.indexOf('st-plot') < h.indexOf('uwk-r'));                  // 코스피 그림이 먼저
  assert.match(h, /S&amp;P 500|S&P 500/);
  assert.match(h, /휴장/);                                               // 수요일 칸
  assert.match(h, /href="\/weekly\/2026-10-23\/"/);
  assert.match(h, /반도체\(SOX\)[\s\S]*−10\.00%/);                     // SOX는 금요일 하루만 있어도 주간 등락
  assert.doesNotMatch(api.cardWeekend(SUM, '2026-10-24', '2026-10-24', false, null), /uwk/);   // 리포트 전엔 코스피만
  assert.doesNotMatch(api.cardWeekend(SUM, '2026-10-24', '2026-10-24', false, { ...WK, monday: '2026-10-12' }), /uwk/);   // 다른 주면 붙이지 않는다
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
