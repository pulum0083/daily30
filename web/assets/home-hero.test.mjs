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
  assert.ok(api.nasdaqChip({ gap_pct: 59.9 }).includes('✓ 정상') && api.nasdaqChip({ gap_pct: 60 }).includes('⚠️ 주의'));
});

test('오늘 브리핑이 ready가 아니면 옛 날짜로 대체하지 않고 카드를 뺀다', async () => {
  const list = { slots: { '2026-10-26': { kospi: { state: 'pending' } }, '2026-10-23': { kospi: { state: 'ready' } } } };
  const t = load({ search: '?slot=morning&d=2026-10-26',
                   fetch: (u) => Promise.resolve({ ok: true, json: () => Promise.resolve(u.includes('briefings-list') ? list : {}) }) });
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(t.root.hidden, true);
  assert.ok(!t.cl.has('hero-on'));
});
