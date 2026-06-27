// 한국 증시 캘린더 단위 테스트
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isKospiHoliday, labelFromYmd } from './_market-calendar.mjs';

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
