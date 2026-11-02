// 섹터 페이지 장 마감 뒤 오늘 공식 종가 판정 테스트
import test from 'node:test';
import assert from 'node:assert/strict';
import './sector-closed.js';

const pick = globalThis.sectorClosedUpdate;
const row = (code, price, prev, date = '20261102') => ({ code, price, prevSessionClose: prev, sessionDate: date });

test('마감 뒤 새 세션이면 오늘 공식 종가와 전일 공식 종가 대비 등락을 쓴다 (11/2 두산에너빌리티 실측)', () => {
  const r = pick([row('034020', 55700, 54800), row('267260', 446500, 424500)], ['034020', '267260'], '2026-10-30');
  assert.equal(r.date, '2026-11-02');
  assert.deepEqual(r.rows['034020'], { price: 55700, pct: 1.64 });
  assert.deepEqual(r.rows['267260'], { price: 446500, pct: 5.18 });
});

test('마감 잡이 페이지를 다시 만든 뒤(세션 = 스냅샷)엔 손대지 않는다', () => {
  assert.equal(pick([row('034020', 55700, 54800)], ['034020'], '2026-11-02'), null);
});

test('한 종목이라도 없으면 쓰지 않는다 — 두 날짜를 섞지 않는다', () => {
  assert.equal(pick([row('034020', 55700, 54800)], ['034020', '267260'], '2026-10-30'), null);
});

test('세션 날짜가 종목마다 다르면 쓰지 않는다', () => {
  const r = pick([row('034020', 55700, 54800), row('267260', 424500, 440000, '20261030')], ['034020', '267260'], '2026-10-29');
  assert.equal(r, null);
});

test('전일 공식 종가가 없으면 등락을 지어내지 않는다', () => {
  assert.equal(pick([row('034020', 55700, null)], ['034020'], '2026-10-30'), null);
});
