// api/_signals-core.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { classifyStock } from './_signals-core.mjs';

test('역행: 시장 -5.8%인데 종목 +1.7% → counter_up', () => {
  const s = { pct: 1.7, vol: 100, vol_avg20: 100, price: 100, wk52_high: 200 };
  const r = classifyStock(s, -5.8);
  assert.ok(r.cats.includes('counter_up'));
});

test('투매: 거래량 3.2배 + -8.4% → vol_surge', () => {
  const s = { pct: -8.4, vol: 320, vol_avg20: 100, price: 100, wk52_high: 200 };
  const r = classifyStock(s, -5.8);
  assert.ok(r.cats.includes('vol_surge'));
  assert.ok(r.badges.some(b => b.includes('거래량') && b.includes('3.2')));
});

test('신고가: 현재가가 52주고가 99% → near_high', () => {
  const s = { pct: 0.3, vol: 100, vol_avg20: 100, price: 99, wk52_high: 100 };
  const r = classifyStock(s, -5.8);
  assert.ok(r.cats.includes('near_high'));
});

test('아무 신호 없으면 빈 cats', () => {
  const s = { pct: -5.0, vol: 100, vol_avg20: 100, price: 50, wk52_high: 200 };
  const r = classifyStock(s, -5.8);
  assert.deepEqual(r.cats, []);
});
