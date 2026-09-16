import { test } from 'node:test';
import assert from 'node:assert/strict';
import { heatAxis, TH_VOL, flowAxis, INST_KEYS } from './_vs-axes.mjs';

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

const row = (개인, 외국인, 기관, inst) => ({ t: '13:30', 개인, 외국인, 기관, inst });

test('부호가 바뀐 주체는 turned', () => {
  const T = row(-9641, -13443, 10502, { 금융투자: 4226, 연기금: 4224, 투신: 1798, 기타금융: 130, 보험: 189, 은행: -64 });
  const Y = row(5538, -12029, -5890, { 금융투자: -4336, 연기금: -47, 투신: -1848, 기타금융: 145, 보험: 75, 은행: 122 });
  const r = flowAxis(T, Y);
  assert.equal(r.main.개인.turned, true);     // +5538 → −9641
  assert.equal(r.main.외국인.turned, false);  // 둘 다 음수
  assert.equal(r.main.기관.turned, true);
  assert.deepEqual(r.inst.map((x) => x.key), INST_KEYS);
  assert.equal(r.inst[0].t, 4226);
  assert.equal(r.inst[0].y, -4336);
});

test('어제 행이 없으면 null', () => {
  assert.equal(flowAxis(row(1, 2, 3, {}), null), null);
});

test('진폭 차이는 반올림 전 값으로 계산한다 — round2(t)-round2(y)가 아니다', () => {
  // 두 진폭이 반올림 후 같은 값으로 보이지만 차이는 다르다
  // 기준가 100000, 오늘 고14-저0, 어제 고6-저0 → 원시값 0.014 / 0.006 → 반올림 0.01 / 0.01
  // 버그면 diff = 0, 정정 후 diff = 0.01
  const T = bars([['0900', 100000, 100014, 100000, 1]]);
  const Y = bars([['0900', 100000, 100006, 100000, 1]]);
  const r = heatAxis(T, Y, 100000, 100000, '0900');
  assert.equal(r.amp.t, 0.01);        // 반올림 표시값
  assert.equal(r.amp.y, 0.01);        // 반올림 표시값
  assert.equal(r.amp.diff, 0.01);     // 미반올림 차이: round2(0.014 - 0.006)
});
