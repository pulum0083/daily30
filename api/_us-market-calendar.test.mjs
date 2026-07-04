// 미국 증시 캘린더 단위 테스트
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isUsMarketHoliday, nyYmd, nyLabelFromYmd } from './_us-market-calendar.mjs';

test('7/4(토)의 대체휴장 7/3(금)은 휴장', () => {
  assert.equal(isUsMarketHoliday('2026-07-03'), true);
});
test('7/4(토) 당일도 주말이라 휴장', () => {
  assert.equal(isUsMarketHoliday('2026-07-04'), true);
});
test('평일 거래일(7/2 목)은 개장일', () => {
  assert.equal(isUsMarketHoliday('2026-07-02'), false);
});
test('추수감사절(11/26 목)은 휴장', () => {
  assert.equal(isUsMarketHoliday('2026-11-26'), true);
});

test('nyYmd: UTC 자정 직후 시각도 뉴욕 로컬 날짜로는 전날', () => {
  // 2026-07-03 02:00 UTC = 2026-07-02 22:00 EDT(UTC-4)
  assert.equal(nyYmd('2026-07-03T02:00:00Z'), '2026-07-02');
});
test('nyYmd: 미 정규장 마감(20:00 UTC = 16:00 EDT)은 당일 뉴욕 날짜', () => {
  assert.equal(nyYmd('2026-07-02T20:00:00Z'), '2026-07-02');
});

test('라벨: 2026-07-02 → 7/2', () => {
  assert.equal(nyLabelFromYmd('2026-07-02'), '7/2');
});
