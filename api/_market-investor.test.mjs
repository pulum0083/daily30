// /api/market 수급 — stock.naver.com JSON 전환(SERVICE_RULES §51) 파서 회귀 테스트
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { parseInvestorTrend } from './market.mjs';

const FX = join(dirname(fileURLToPath(import.meta.url)), '..', 'scripts', 'fixtures', 'naver_market');

test('m.stock.naver.com/api/index/KOSPI/trend 실응답(억원)을 읽는다', () => {
  const d = JSON.parse(readFileSync(join(FX, 'index_trend.json'), 'utf8'));
  assert.deepEqual(parseInvestorTrend(d), { individual: 4239, foreign: -2961, institution: -2539 });
});

test('빈 응답은 0이 아니라 실패다 — 사이드바에 순매수 0억을 그리지 않는다', () => {
  assert.throws(() => parseInvestorTrend({}), /empty/);
  assert.throws(() => parseInvestorTrend(null), /empty/);
  assert.throws(() => parseInvestorTrend({ personalValue: '', foreignValue: '-1', institutionalValue: '1' }), /empty/);
});
