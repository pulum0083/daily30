import { test } from 'node:test';
import assert from 'node:assert/strict';
import { heatAxis, TH_VOL } from './_vs-axes.mjs';

const bars = (rows) => rows.map(([t, v, h, l, vol]) => ({ t, v, h, l, vol }));

test('거래량은 at 이하 봉만 누적하고 차이를 %로 낸다', () => {
  const T = bars([['0900', 100, 101, 99, 10], ['0901', 100, 100, 100, 5], ['1400', 100, 100, 100, 99]]);
  const Y = bars([['0900', 100, 100, 100, 20], ['0901', 100, 100, 100, 5]]);
  const r = heatAxis(T, Y, 100, 100, '0901');
  assert.equal(r.vol.t, 15);
  assert.equal(r.vol.y, 25);
  assert.equal(r.vol.diff, -40);        // (15/25 - 1) * 100
  assert.equal(r.vol.judge, 'weak');    // |−40| > 10
});

test('진폭은 (고−저)/기준가 이고 임계 안이면 same', () => {
  const T = bars([['0900', 100, 102, 99, 1]]);
  const Y = bars([['0900', 100, 102, 99, 1]]);
  const r = heatAxis(T, Y, 100, 100, '0900');
  assert.equal(r.amp.t, 3);
  assert.equal(r.amp.diff, 0);
  assert.equal(r.amp.judge, 'same');
});

test('어제 봉이 없으면 비운다 — 오늘 값으로 대신하지 않는다', () => {
  const T = bars([['0900', 100, 101, 99, 10]]);
  const r = heatAxis(T, [], 100, null, '0900');
  assert.equal(r.vol.t, 10);
  assert.equal(r.vol.y, null);
  assert.equal(r.vol.diff, null);
  assert.equal(r.vol.judge, null);
  assert.equal(r.amp.y, null);
});

test('거래량 임계는 10%', () => { assert.equal(TH_VOL, 10); });
