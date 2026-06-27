// api/_signals-core.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { classifyStock, buildSignals, etfBettingFlow } from './_signals-core.mjs';

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

test('거래대금 상위 3종목에 turnover cat', () => {
  const stocks = [
    { code: '1', name: 'A', sector: 'semicon', pct: -2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 500 },
    { code: '2', name: 'B', sector: 'semicon', pct: -2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 400 },
    { code: '3', name: 'C', sector: 'auto', pct: -2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 300 },
    { code: '4', name: 'D', sector: 'auto', pct: -2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 10 },
  ];
  const { signals } = buildSignals(stocks, -5.8);
  const a = signals.find(s => s.code === '1');
  assert.ok(a.cats.includes('turnover'));
  const d = signals.find(s => s.code === '4');
  assert.ok(!d || !d.cats.includes('turnover'));
});

test('신호 없는 종목은 signals에서 제외', () => {
  const stocks = [
    { code: '9', name: 'Z', sector: 'bio', pct: -5.0, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 1 },
  ];
  const { signals } = buildSignals(stocks, -5.8);
  assert.equal(signals.length, 0);
});

test('랭킹은 신호별 그룹 + 종목수 내림차순', () => {
  const stocks = [
    { code: '1', name: 'A', sector: 'semicon', pct: 1.7, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 5 },
    { code: '2', name: 'B', sector: 'semicon', pct: 1.2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 4 },
  ];
  const { rank } = buildSignals(stocks, -5.8); // 둘 다 counter_up
  const cu = rank.find(g => g.cat === 'counter_up');
  assert.equal(cu.items.length, 2);
});

test('베팅 흐름: 인버스류 거래대금 합산 vs 레버리지 + 인버스 거래량 배수', () => {
  const byCode = {
    '114800': { amount: 1122000, vol: 1239929374, pct: 6.08 }, // 인버스(백만)
    '252670': { amount: 1183000, vol: 17149039548, pct: 11.29 }, // 인버스2X
    '122630': { amount: 3163000, vol: 15796886, pct: -12.04 }, // 레버리지
    '069500': { amount: 3677000, vol: 26711323, pct: -5.79 }, // KODEX200(분모)
  };
  const r = etfBettingFlow(byCode);
  assert.equal(r.downAmt, 2305000);
  assert.equal(r.upAmt, 3163000);
  assert.equal(r.downRatio, 42); // 2305/(2305+3163) = 42.2 → 42
  assert.equal(r.levPct, -12.04);
  assert.ok(r.invVolMultiple >= 45 && r.invVolMultiple <= 47); // 12.4억/0.267억 ≈ 46
});
