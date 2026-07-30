// 미국 세션 판정·기준가 선택 회귀 테스트 — 2026-07-30 프리장 실사고 리플레이 포함
//
// 실행: node --test api/_us-session.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { usSessionState, usBaseClose } from './_us-session.mjs';

// ── 2026-07-30 프리장 실측 meta (DRAM · Roundhill Memory ETF) ──
// 실제 일봉: 07-28 = 47.77, 07-29 = 44.85 (직전 정규장 종가)
// regularMarketTime = 1785355201 = 2026-07-29 16:00 ET (정규장 마감)
const DRAM_PRE = {
  symbol: 'DRAM',
  regularMarketPrice: 44.85,     // 직전 완료 정규장 종가 = 07-29
  chartPreviousClose: 47.77,     // 그 하루 전 = 07-28  ← 사고 당시 기준가로 쓰인 값
  previousClose: 47.77,
  regularMarketTime: 1785355201,
  currentTradingPeriod: {
    pre: { start: 1785398400, end: 1785418200 },      // 07-30 04:00~09:30 ET
    regular: { start: 1785418200, end: 1785441600 },  // 07-30 09:30~16:00 ET
    post: { start: 1785441600, end: 1785456000 },     // 07-30 16:00~20:00 ET
  },
};
const T_PRE = 1785403914;      // 07-30 05:31 ET — 사용자 신고 시각 (프리장 한복판)
const T_REGULAR = 1785425000;  // 07-30 11:23 ET
const T_POST = 1785445000;     // 07-30 16:56 ET
const T_CLOSED = 1785460000;   // 07-30 21:06 ET — 애프터장 종료 후

test('프리장 — 기준가는 직전 정규장 종가(regularMarketPrice)', () => {
  assert.equal(usSessionState(DRAM_PRE, T_PRE), 'pre');
  assert.equal(usBaseClose(DRAM_PRE, 'pre'), 44.85);
});

test('실사고 리플레이 — 프리장 44.26은 -1.3%대여야 하고 -7.35%가 아니다', () => {
  const base = usBaseClose(DRAM_PRE, usSessionState(DRAM_PRE, T_PRE));
  const pct = ((44.26 - base) / base) * 100;
  // 사고 당시 화면에 뜬 값 (07-28 기준)
  const buggy = ((44.26 - 47.77) / 47.77) * 100;
  assert.ok(Math.abs(buggy - -7.35) < 0.01, '재현 확인: 옛 기준가는 -7.35%를 만든다');
  assert.ok(Math.abs(pct - -1.32) < 0.05, `프리장 등락률이 어긋남: ${pct}`);
});

test('애프터장 — 기준가는 당일 정규장 종가(regularMarketPrice)', () => {
  assert.equal(usSessionState(DRAM_PRE, T_POST), 'post');
  assert.equal(usBaseClose(DRAM_PRE, 'post'), 44.85);
});

test('정규장 — 기준가는 전일 종가(chartPreviousClose)', () => {
  // 정규장 중 regularMarketPrice는 실시간 체결가라 기준가로 쓸 수 없다.
  assert.equal(usSessionState(DRAM_PRE, T_REGULAR), 'open');
  assert.equal(usBaseClose(DRAM_PRE, 'open'), 47.77);
});

test('장 마감 — 기준가는 전일 종가(chartPreviousClose)', () => {
  assert.equal(usSessionState(DRAM_PRE, T_CLOSED), 'closed');
  assert.equal(usBaseClose(DRAM_PRE, 'closed'), 47.77);
});

test('미국 공휴일이면 세션 창과 무관하게 closed', () => {
  // 2026-01-01(신년) 정규장 시간대 — 야후가 휴장일에도 세션 창을 내려주는 경우 방어
  const ny = {
    ...DRAM_PRE,
    currentTradingPeriod: {
      pre: { start: 1767250800, end: 1767270600 },
      regular: { start: 1767270600, end: 1767294000 },
      post: { start: 1767294000, end: 1767308400 },
    },
  };
  assert.equal(usSessionState(ny, 1767280000), 'closed');
});

test('chartPreviousClose가 없으면 previousClose로 폴백', () => {
  const m = { ...DRAM_PRE, chartPreviousClose: undefined };
  assert.equal(usBaseClose(m, 'open'), 47.77);
});

test('기준가가 없거나 0이면 null — 가짜 0% 방지', () => {
  assert.equal(usBaseClose({ regularMarketPrice: 0 }, 'pre'), null);
  assert.equal(usBaseClose({}, 'pre'), null);
  assert.equal(usBaseClose({ chartPreviousClose: null, previousClose: null }, 'open'), null);
});

test('세션 창이 없으면 closed — meta 불완전 방어', () => {
  assert.equal(usSessionState({ ...DRAM_PRE, currentTradingPeriod: undefined }, T_PRE), 'closed');
});
