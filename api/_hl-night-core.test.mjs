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
