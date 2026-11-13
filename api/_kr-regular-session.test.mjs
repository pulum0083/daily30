// 장 마감 뒤 정규장 세션 회귀 테스트 — 특이 신호가 애프터장 가격·등락률·거래량을 쓰지 않는지(§48)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { regularSessionFromBars, lastClosedSessions, fetchLastRegularSession } from './_kr-regular-session.mjs';

// 2026-09-14 SK하이닉스 1분봉(요약) — 전일(9/11) 15:30 종가 1,812,000, 정규장 09:00~15:29 합 3,492,572 + 15:30 봉 250,333.
// 16:00 봉은 애프터장이라 종가·거래량·저가 어디에도 들어가면 안 된다.
const bar = (ts, price, vol, hi = price, lo = price) => ({
  localDateTime: ts, currentPrice: price, openPrice: price, highPrice: hi, lowPrice: lo, accumulatedTradingVolume: vol,
});
const BARS = [
  bar('20260911153000', 1812000, 120000),
  bar('20260914090000', 1718000, 3492572, 1740000, 1686000),
  bar('20260914153000', 1697000, 250333),
  bar('20260914160000', 1678000, 405),
];

test('정규장 거래량·전일 공식 종가를 1분봉에서 만든다 (9/14 리플레이)', () => {
  const r = regularSessionFromBars(BARS);
  assert.equal(r.date, '20260914');
  assert.equal(r.close, 1697000);
  assert.equal(r.volume, 3742905);          // 일봉 4,001,549(애프터장 포함)가 아니다
  assert.equal(r.prevClose, 1812000);
  assert.equal(r.low, 1686000);             // 애프터장 1,678,000이 아니다
});

test('마지막으로 끝난 정규장 날짜 — 15:31부터 오늘, 주말·연휴는 건너뛴다', () => {
  const at = (iso) => new Date(iso);          // KST = UTC+9
  assert.deepEqual(lastClosedSessions(at('2026-09-14T06:30:00Z')), { session: '20260911', prev: '20260910' }); // 월 15:30 장중
  assert.deepEqual(lastClosedSessions(at('2026-09-14T06:31:00Z')), { session: '20260914', prev: '20260911' }); // 월 15:31
  assert.deepEqual(lastClosedSessions(at('2026-09-14T23:30:00Z')), { session: '20260914', prev: '20260911' }); // 화 08:30
  assert.deepEqual(lastClosedSessions(at('2026-09-27T03:00:00Z')), { session: '20260923', prev: '20260922' }); // 추석 연휴 일요일
});

function withFetch(body, fn) {
  const orig = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url) => { calls.push(url); return { ok: true, json: async () => body }; };
  return fn(calls).finally(() => { globalThis.fetch = orig; });
}

test('등락률은 공식 종가끼리 — 9/14 SK하이닉스 -6.35%, 같은 세션은 다시 조회하지 않는다', () => withFetch(BARS, async (calls) => {
  const now = new Date('2026-09-14T08:10:00Z');   // 17:10 KST
  const r = await fetchLastRegularSession('000660', now);
  assert.equal(r.changePct, -6.35);                // 실시간 closePriceRaw 1,686,000 기준 -6.95%가 아니다
  assert.equal(r.volume, 3742905);
  assert.match(calls[0], /startDateTime=202609111530&endDateTime=202609141539/);
  await fetchLastRegularSession('000660', now);
  assert.equal(calls.length, 1);
}));

test('그 세션의 15:30 봉이 아직 없으면 전날 값으로 채우지 않는다', () => withFetch(BARS.slice(0, 2), async () => {
  assert.equal(await fetchLastRegularSession('005930', new Date('2026-09-14T08:10:00Z')), null);
}));

test('전일 15:30 봉이 없으면 등락률을 만들지 않는다', () => withFetch(BARS.slice(1), async () => {
  assert.equal(await fetchLastRegularSession('005380', new Date('2026-09-14T08:10:00Z')), null);
}));

// 2026-11-12 HD현대중공업 실측 — 종가 단일가가 연장돼 종가 봉이 15:32에 찍혔다(15:30 봉 없음, 값은 야후 종가와 같다).
// 15:40 봉은 장후 시간외 종가매매, 16:00 봉은 애프터장이라 거래량에 들어가면 안 된다.
test('종가 단일가가 연장되면 15:30~15:39 사이 첫 봉이 종가다 (11/12 리플레이)', () => {
  const r = regularSessionFromBars([
    bar('20261111153000', 262500, 90000),
    bar('20261112090000', 262000, 1000000, 268000, 258000),
    bar('20261112151900', 266000, 5000),
    bar('20261112153200', 267500, 109390),
    bar('20261112154000', 267500, 572),
    bar('20261112160000', 267500, 20),
  ]);
  assert.equal(r.date, '20261112');
  assert.equal(r.close, 267500);
  assert.equal(r.volume, 1000000 + 5000 + 109390);
  assert.equal(r.prevClose, 262500);
  assert.equal(r.prevDate, '20261111');
});

test('전 세션이 연장된 날이어도 전일 종가를 찾는다', () => {
  const r = regularSessionFromBars([
    bar('20261112153200', 267500, 109390),
    bar('20261112154000', 267500, 572),
    bar('20261113090000', 270000, 500000),
    bar('20261113153000', 271500, 80000),
  ]);
  assert.equal(r.date, '20261113');
  assert.equal(r.prevClose, 267500);
});

test('15:40 이후 봉만 있는 날은 종가가 없다 — 시간외 가격을 종가로 쓰지 않는다', () => {
  const r = regularSessionFromBars([
    bar('20261111153000', 262500, 90000),
    bar('20261112154000', 267500, 572),
  ]);
  assert.equal(r.date, '20261111');
});
