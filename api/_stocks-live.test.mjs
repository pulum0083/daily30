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
