// 한국 증시 캘린더 단위 테스트
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isKospiHoliday, labelFromYmd, lastTradingDay } from './_market-calendar.mjs';

// 헬퍼: KST 날짜를 shifted-UTC Date로 (isKospiHoliday는 getUTCDay/toISOString 사용)
function kstDate(s) { return new Date(s + 'T05:00:00Z'); } // 임의 시각, 날짜만 중요

test('주말(토)은 휴장', () => {
  assert.equal(isKospiHoliday(kstDate('2026-06-27')), true); // 토
});
test('일요일은 휴장', () => {
  assert.equal(isKospiHoliday(kstDate('2026-06-28')), true); // 일
});
test('공휴일(어린이날 5/5 화)은 휴장', () => {
  assert.equal(isKospiHoliday(kstDate('2026-05-05')), true);
});
test('평일 거래일(금 6/26)은 개장일', () => {
  assert.equal(isKospiHoliday(kstDate('2026-06-26')), false);
});

test('라벨: 2026-06-26 → 6/26(금)', () => {
  assert.equal(labelFromYmd('2026-06-26'), '6/26(금)');
});
test('라벨: 빈 입력 → 빈 문자열', () => {
  assert.equal(labelFromYmd(''), '');
});

test('마지막 거래일: 일요일 6/28 → 금요일 6/26', () => {
  assert.equal(lastTradingDay('2026-06-28'), '2026-06-26');
});
test('마지막 거래일: 토요일 6/27 → 금요일 6/26', () => {
  assert.equal(lastTradingDay('2026-06-27'), '2026-06-26');
});
test('마지막 거래일: 거래일은 그대로 (금 6/26)', () => {
  assert.equal(lastTradingDay('2026-06-26'), '2026-06-26');
});
test('마지막 거래일: 공휴일 연휴(현충일 대체 6/3 수) → 직전 거래일', () => {
  // 2026-06-03(수)은 휴장 → 직전 거래일 6/2(화)
  assert.equal(lastTradingDay('2026-06-03'), '2026-06-02');
});
