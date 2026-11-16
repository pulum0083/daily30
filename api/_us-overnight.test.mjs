// 미국 주간거래 세션 판정·로빈후드 체결가 적용 테스트
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { overnightSessionStart, overnightTrades, withOvernight, fetchOvernightTrades } from './_us-overnight.mjs';

const at = (s) => Date.parse(s);

test('일요일 20:00 ET~월요일 04:00 ET는 월요일 세션 — 시작은 일요일 20:00 ET', () => {
  // 2026-11-16 17:07 KST = 11-16 03:07 EST (실사고 시각)
  assert.equal(overnightSessionStart(at('2026-11-16T08:07:00Z')), at('2026-11-16T01:00:00Z'));
  // 일요일 21:00 EST
  assert.equal(overnightSessionStart(at('2026-11-16T02:00:00Z')), at('2026-11-16T01:00:00Z'));
});

test('프리장·정규장·애프터장 시간엔 주간거래가 아니다', () => {
  assert.equal(overnightSessionStart(at('2026-11-16T09:30:00Z')), null); // 04:30 EST 프리장
  assert.equal(overnightSessionStart(at('2026-11-16T16:00:00Z')), null); // 11:00 EST 정규장
  assert.equal(overnightSessionStart(at('2026-11-17T00:30:00Z')), null); // 19:30 EST 애프터장
});

test('금요일 밤·토요일엔 세션이 없다 (다음 날이 주말)', () => {
  assert.equal(overnightSessionStart(at('2026-11-14T02:00:00Z')), null); // 금 21:00 EST
  assert.equal(overnightSessionStart(at('2026-11-14T07:00:00Z')), null); // 토 02:00 EST
});

test('다음 정규장 날이 공휴일이면 세션이 없다 — 추수감사절(11-26)', () => {
  assert.equal(overnightSessionStart(at('2026-11-26T02:00:00Z')), null); // 수 21:00 EST → 목 휴장
  assert.equal(overnightSessionStart(at('2026-11-26T07:00:00Z')), null); // 목 02:00 EST
  assert.notEqual(overnightSessionStart(at('2026-11-27T02:00:00Z')), null); // 목 21:00 EST → 금 거래일
});

test('서머타임에도 20:00 현지 기준 — 2026-07-14 21:00 EDT', () => {
  assert.equal(overnightSessionStart(at('2026-07-15T01:00:00Z')), at('2026-07-15T00:00:00Z'));
});

test('이번 세션 이전 체결(금요일 애프터장)은 쓰지 않는다', () => {
  const start = at('2026-11-16T01:00:00Z');
  const json = { results: [
    { symbol: 'NVDA', last_non_reg_trade_price: '162.37', venue_last_non_reg_trade_time: '2026-11-16T08:08:22.889Z' },
    { symbol: 'XYZ', last_non_reg_trade_price: '10.00', venue_last_non_reg_trade_time: '2026-11-14T00:59:00Z' },
    null,
    { symbol: 'BAD', last_non_reg_trade_price: null, venue_last_non_reg_trade_time: '2026-11-16T08:00:00Z' },
  ] };
  const t = overnightTrades(json, start);
  assert.deepEqual(Object.keys(t), ['NVDA']);
  assert.equal(t.NVDA.price, 162.37);
});

test('장 마감 시세에 체결가를 얹고 직전 종가 대비로 등락을 다시 낸다 (2026-11-16 SKHY 실측)', () => {
  const q = { sym: 'SKHY', price: 131.79, changePct: -4.2, source: 'yahoo', state: 'closed', tradedAt: 'x' };
  const r = withOvernight(q, { price: 126.35, at: at('2026-11-16T08:08:13Z') });
  assert.equal(r.state, 'overnight');
  assert.equal(r.price, 126.35);
  assert.equal(r.changePct, -4.13);
  assert.equal(r.source, 'robinhood');
});

test('체결이 없거나 ±25% 넘게 벌어지거나 장 마감이 아니면 원래 시세 그대로', () => {
  const q = { sym: 'A', price: 100, changePct: 1, state: 'closed' };
  assert.equal(withOvernight(q, null), q);
  assert.equal(withOvernight(q, { price: 60, at: 0 }), q);
  const pre = { ...q, state: 'pre' };
  assert.equal(withOvernight(pre, { price: 101, at: 0 }), pre);
});

test('로빈후드 조회가 실패하면 빈 결과 — 직전 종가가 남는다', async () => {
  const boom = async () => { throw new Error('blocked'); };
  assert.deepEqual(await fetchOvernightTrades(['NVDA'], 0, boom), {});
  const forbidden = async () => ({ ok: false });
  assert.deepEqual(await fetchOvernightTrades(['NVDA'], 0, forbidden), {});
  assert.deepEqual(await fetchOvernightTrades(['NVDA'], null, boom), {});
});
