// 하이퍼리퀴드 실제가 보정 로직 단위 테스트
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reconcileWithReal, REAL_PRICE_TOLERANCE_PCT } from './_hl-night-core.mjs';

test('허용 오차 이내면 HL 값을 그대로 쓴다 (현대차 -2.5% 케이스)', () => {
  const out = reconcileWithReal({ krw: 435489, changePct: -2.47 }, { price: 444000, changePct: -1.5 });
  assert.equal(out.krw, 435489);
  assert.equal(out.changePct, -2.47);
  assert.equal(out.adjusted, false);
});

test('허용 오차 초과(양의 방향)면 실제 종가로 대체한다 (SK하이닉스 +11% 케이스)', () => {
  const out = reconcileWithReal({ krw: 2046653, changePct: 11.06 }, { price: 1845000, changePct: 0.8 });
  assert.equal(out.krw, 1845000);
  assert.equal(out.changePct, 0.8);
  assert.equal(out.adjusted, true);
});

test('허용 오차 초과(삼성전자 +8.6% 케이스)도 실제 종가로 대체한다', () => {
  const out = reconcileWithReal({ krw: 277021, changePct: 8.64 }, { price: 254500, changePct: 0.2 });
  assert.equal(out.krw, 254500);
  assert.equal(out.adjusted, true);
});

test('실제가 조회 실패 시(real null) HL 값을 그대로 유지한다', () => {
  const out = reconcileWithReal({ krw: 277021, changePct: 8.64 }, null);
  assert.equal(out.krw, 277021);
  assert.equal(out.changePct, 8.64);
  assert.equal(out.adjusted, false);
});

test('HL 값이 없으면(hl null) 실제가로 채운다', () => {
  const out = reconcileWithReal(null, { price: 254500, changePct: 0.2 });
  assert.equal(out.krw, 254500);
  assert.equal(out.changePct, 0.2);
  assert.equal(out.adjusted, true);
});

test('실제가의 changePct가 없으면 HL changePct를 유지한다', () => {
  const out = reconcileWithReal({ krw: 277021, changePct: 8.64 }, { price: 254500, changePct: null });
  assert.equal(out.krw, 254500);
  assert.equal(out.changePct, 8.64);
  assert.equal(out.adjusted, true);
});

test('경계값(정확히 5%)은 초과가 아니므로 HL 값을 유지한다', () => {
  // real=100000, hl=105000 → diff = 5.0% (초과 아님, 경계 포함)
  const out = reconcileWithReal({ krw: 105000, changePct: 1.0 }, { price: 100000, changePct: 0.5 });
  assert.equal(out.krw, 105000);
  assert.equal(out.adjusted, false);
});

test('REAL_PRICE_TOLERANCE_PCT는 5다', () => {
  assert.equal(REAL_PRICE_TOLERANCE_PCT, 5);
});

// ── 앵커 환산 (2026-07-31 추가) ────────────────────────────────────────────
// 종가 대비 HL 비율만 쓰므로 합성가의 상시 프리미엄은 상쇄되고, 진짜 야간 변동은 살아남는다.
import { anchorEstimate, pickAnchorCandle, lastKrxCloseTs } from './_hl-night-core.mjs';

test('앵커: 종가 × (현재/종가시점) 비율로 추정가를 만든다', () => {
  // 2026-07-30 실측 — 삼성 KRX 207,000 / HL $145.36 → $162.22 (+11.6%)
  const out = anchorEstimate({ hlNow: 162.22, hlAtClose: 145.36, krxClose: 207000 });
  assert.equal(out.krw, 231009); // 207000 × 162.22/145.36
  assert.ok(Math.abs(out.changePct - 11.60) < 0.05);
  assert.equal(out.anchored, true);
});

test('앵커: 상시 프리미엄이 있어도 비율에서 상쇄된다', () => {
  // HL이 실제가보다 10% 높게 찍히더라도, 종가 이후 움직임이 없으면 추정가 = 종가
  const out = anchorEstimate({ hlNow: 110, hlAtClose: 110, krxClose: 200000 });
  assert.equal(out.krw, 200000);
  assert.equal(out.changePct, 0);
});

test('앵커: 값이 없거나 0이면 null (지어내지 않는다)', () => {
  assert.equal(anchorEstimate({ hlNow: 100, hlAtClose: 0, krxClose: 200000 }), null);
  assert.equal(anchorEstimate({ hlNow: null, hlAtClose: 100, krxClose: 200000 }), null);
  assert.equal(anchorEstimate({ hlNow: 100, hlAtClose: 100, krxClose: null }), null);
});

test('앵커: 비율이 상식 밖이면 데이터 이상으로 보고 버린다', () => {
  assert.equal(anchorEstimate({ hlNow: 300, hlAtClose: 100, krxClose: 200000 }), null);
  assert.equal(anchorEstimate({ hlNow: 10, hlAtClose: 100, krxClose: 200000 }), null);
});

test('앵커 캔들: 종가 시각 이전에 닫힌 마지막 봉을 고른다', () => {
  const ts = Date.parse('2026-07-30T06:30:00Z');
  const cs = [
    { T: Date.parse('2026-07-30T06:14:59.999Z'), c: '144.0' },
    { T: Date.parse('2026-07-30T06:29:59.999Z'), c: '145.36' },
    { T: Date.parse('2026-07-30T06:44:59.999Z'), c: '144.32' },
  ];
  assert.equal(pickAnchorCandle(cs, ts).c, '145.36');
});

test('앵커 캔들: 후보가 없으면 null', () => {
  assert.equal(pickAnchorCandle([], Date.now()), null);
  assert.equal(pickAnchorCandle(null, Date.now()), null);
});

test('직전 KRX 종가 시각: 목요일 밤이면 그날 15:30 KST', () => {
  // 2026-07-31 01:00 KST = 2026-07-30 16:00 UTC
  const got = lastKrxCloseTs(Date.parse('2026-07-30T16:00:00Z'));
  assert.equal(new Date(got).toISOString(), '2026-07-30T06:30:00.000Z');
});

test('직전 KRX 종가 시각: 장중이면 전 거래일 종가', () => {
  // 2026-07-30 11:00 KST = 02:00 UTC (아직 15:30 전) → 7/29 종가
  const got = lastKrxCloseTs(Date.parse('2026-07-30T02:00:00Z'));
  assert.equal(new Date(got).toISOString(), '2026-07-29T06:30:00.000Z');
});

test('직전 KRX 종가 시각: 일요일이면 금요일 종가 (주말 건너뜀)', () => {
  // 2026-08-02(일) 12:00 KST → 7/31(금) 15:30
  const got = lastKrxCloseTs(Date.parse('2026-08-02T03:00:00Z'));
  assert.equal(new Date(got).toISOString(), '2026-07-31T06:30:00.000Z');
});

test('직전 KRX 종가 시각: 공휴일 다음날 새벽이면 그 전 거래일', () => {
  // 2026-07-17 제헌절(휴장). 7/18(토) 01:00 KST → 7/16(목) 15:30
  const got = lastKrxCloseTs(Date.parse('2026-07-17T16:00:00Z'));
  assert.equal(new Date(got).toISOString(), '2026-07-16T06:30:00.000Z');
});
