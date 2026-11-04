// /api/stocks-live 필드 추출 회귀 테스트 — 원화 등락을 원천 값 그대로 넘기는지(역산 금지) 검증
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fetchOne } from './stocks-live.mjs';

// 2026-09-11 15:17 네이버 실시간 실응답에서 필요한 필드만 옮겼다(삼성전자).
const REAL = {
  closePriceRaw: '259500', compareToPreviousClosePriceRaw: '-9500', fluctuationsRatioRaw: '-3.53',
  openPriceRaw: '258000', highPriceRaw: '261500', lowPriceRaw: '256500',
  accumulatedTradingValueRaw: '3167707000000',
};
function withFetch(item, fn) {
  const orig = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ datas: item ? [item] : [] }) });
  return fn().finally(() => { globalThis.fetch = orig; });
}

test('원천의 실제 원화 등락·전일 종가를 그대로 넘긴다 (실사고 리플레이)', () => withFetch(REAL, async () => {
  const r = await fetchOne('005930');
  assert.equal(r.price, 259500);
  assert.equal(r.changeAbs, -9500);
  assert.equal(r.prevClose, 269000);            // 호가 단위에 맞는 실제 전일 종가
  assert.equal(r.changePct, -3.53);
  assert.equal(r.open, 258000);
  assert.equal(r.high, 261500);
  assert.equal(r.low, 256500);
  assert.equal(r.tradingValue, 3167707000000);
}));

test('원화 등락이 없으면 null — %에서 역산해 채우지 않는다', () => withFetch(
  { ...REAL, compareToPreviousClosePriceRaw: undefined }, async () => {
    const r = await fetchOne('005930');
    assert.equal(r.changeAbs, null);
    assert.equal(r.prevClose, null);
    assert.equal(r.changePct, -3.53);
  }));

test('가격이 없으면 항목 자체를 버린다', () => withFetch({ ...REAL, closePriceRaw: '' }, async () => {
  assert.equal(await fetchOne('005930'), null);
}));

test('응답이 비면 null', () => withFetch(null, async () => {
  assert.equal(await fetchOne('005930'), null);
}));

// ── 장이 닫힌 뒤 정규장 값 (§48) ─────────────────────────────────────────────
// 9/14 저녁 실시간 응답은 삼성전자 lowPrice 248,000·closePrice 248,500을 줬다. 공식 정규장은
// 저가 248,500(14:57)·종가 249,000(15:30 1분봉, 야후와 일치). 1분봉으로 정규장만 만든다.
import { regularSessionFromBars, fetchClosedSession } from './_kr-regular-session.mjs';

const BARS_0914 = [
  { localDateTime: '20260911153000', currentPrice: 259500, openPrice: 259500, highPrice: 259500, lowPrice: 259500 },
  { localDateTime: '20260914090000', currentPrice: 250000, openPrice: 249500, highPrice: 250500, lowPrice: 249500 },
  { localDateTime: '20260914101000', currentPrice: 254000, openPrice: 253500, highPrice: 254500, lowPrice: 253500 },
  { localDateTime: '20260914145700', currentPrice: 248750, openPrice: 249000, highPrice: 249000, lowPrice: 248500 },
  { localDateTime: '20260914153000', currentPrice: 249000, openPrice: 249000, highPrice: 249000, lowPrice: 249000 },
  { localDateTime: '20260914171000', currentPrice: 248500, openPrice: 248500, highPrice: 248500, lowPrice: 248000 }, // 애프터장
];

test('정규장 시·고·저·종은 09:00~15:30 1분봉에서만 — 애프터장 체결을 섞지 않는다 (9/14 삼성전자 실측)', () => {
  const r = regularSessionFromBars(BARS_0914);
  assert.equal(r.date, '20260914');
  assert.equal(r.close, 249000);   // 실시간 248,500 아님
  assert.equal(r.open, 249500);
  assert.equal(r.high, 254500);
  assert.equal(r.low, 248500);     // 애프터장 248,000 아님
});

test('오늘 15:30 봉이 없으면 직전 거래일 세션을 쓴다(주말·새벽)', () => {
  const r = regularSessionFromBars(BARS_0914.slice(0, 1));
  assert.equal(r.date, '20260911');
  assert.equal(r.close, 259500);
});

test('15:30 봉이 하나도 없으면 null — 만들어내지 않는다', () => {
  assert.equal(regularSessionFromBars([BARS_0914[5]]), null);
  assert.equal(regularSessionFromBars(null), null);
});

test('장 마감 뒤 응답은 정규장 값만, 거래대금·등락은 비운다', async () => {
  const orig = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => BARS_0914 });
  try {
    const r = await fetchClosedSession('005930', new Date('2026-09-14T08:10:00Z'));
    assert.equal(r.price, 249000);
    assert.equal(r.low, 248500);
    assert.equal(r.tradingValue, null);
    assert.equal(r.changeAbs, null);
    assert.equal(r.prevSessionClose, 259500);   // 직전 세션 15:30 봉 — 실시간 '전일 종가'가 아니다
  } finally { globalThis.fetch = orig; }
});

// ── 주도주 한 줄 목록(§79) — 날짜 붙은 직전 두 세션 종가, 애프터장 실시간 ──
import { afterHoursOpen, closedWithAfter } from './stocks-live.mjs';

const BARS_1103 = [
  { localDateTime: '20261030153000', currentPrice: 225000, openPrice: 225000, highPrice: 225000, lowPrice: 225000 },
  { localDateTime: '20261102153000', currentPrice: 229000, openPrice: 229000, highPrice: 229000, lowPrice: 229000 },
  { localDateTime: '20261103090000', currentPrice: 228000, openPrice: 228000, highPrice: 228500, lowPrice: 227500 },
  { localDateTime: '20261103153000', currentPrice: 219500, openPrice: 219500, highPrice: 219500, lowPrice: 219500 },
  { localDateTime: '20261103183000', currentPrice: 221000, openPrice: 221000, highPrice: 221000, lowPrice: 221000 }, // 애프터장
];

test('직전 세션·그 전 세션 공식 종가를 날짜와 함께 준다 (11/3 삼성전자 실측)', () => {
  const r = regularSessionFromBars(BARS_1103);
  assert.equal(r.close, 219500);
  assert.equal(r.prevClose, 229000);
  assert.equal(r.prevDate, '20261102');
  assert.equal(r.prev2Close, 225000);
  assert.equal(r.prev2Date, '20261030');   // 주말을 건너뛴 실제 직전 세션
});

test('그 전 세션 봉이 창에 없으면 비운다 — 만들어내지 않는다', () => {
  const r = regularSessionFromBars(BARS_1103.slice(1));
  assert.equal(r.prevClose, 229000);
  assert.equal(r.prev2Close, null);
  assert.equal(r.prev2Date, null);
});

test('애프터장 구간 — 거래일 15:30 초과 ~ 20:00 미만만', () => {
  const at = (s) => new Date(s + '+09:00');
  assert.equal(afterHoursOpen(at('2026-11-03T15:30:00')), false);
  assert.equal(afterHoursOpen(at('2026-11-03T15:31:00')), true);
  assert.equal(afterHoursOpen(at('2026-11-03T19:59:00')), true);
  assert.equal(afterHoursOpen(at('2026-11-03T20:00:00')), false);
  assert.equal(afterHoursOpen(at('2026-11-07T17:00:00')), false);   // 토요일
});

test('애프터장 시간엔 오늘 세션에만 실시간 체결가를 after로 붙인다', async () => {
  const orig = globalThis.fetch;
  globalThis.fetch = async (url) => ({
    ok: true,
    json: async () => (String(url).includes('polling')
      ? { datas: [{ closePriceRaw: '221000', fluctuationsRatioRaw: '0.68', compareToPreviousClosePriceRaw: '1500' }] }
      : BARS_1103),
  });
  try {
    const r = await closedWithAfter('005930', new Date('2026-11-03T18:30:00+09:00'));
    assert.equal(r.price, 219500);                 // 정규장 종가는 그대로
    assert.deepEqual(r.after, { price: 221000 });
    const night = await closedWithAfter('005930', new Date('2026-11-03T20:30:00+09:00'));
    assert.equal(night.after, undefined);          // 20:00 뒤엔 붙이지 않는다
    const nextDay = await closedWithAfter('005930', new Date('2026-11-04T18:30:00+09:00'));
    assert.equal(nextDay.after, undefined);        // 세션(11/3)이 오늘(11/4)이 아니면 붙이지 않는다
  } finally { globalThis.fetch = orig; }
});
