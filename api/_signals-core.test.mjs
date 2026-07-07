// api/_signals-core.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { classifyStock, buildSignals, etfBettingFlow, SIGNALS_DISPLAY_MAX } from './_signals-core.mjs';

test('역행: 시장 -5.8%인데 종목 +1.7% → counter_up', () => {
  const s = { pct: 1.7, vol: 100, vol_avg20: 100, price: 100, wk52_high: 200 };
  const r = classifyStock(s, -5.8);
  assert.ok(r.cats.includes('counter_up'));
});

test('급락일 보정: 시장 -5.8%인데 종목 +0.8%(하한선 미달) → counter_up 아님', () => {
  // 하한선 = min(1.5, 5.8*0.25=1.45) = 1.45. +0.8%는 미달이라 '살짝 초록'은 역행 상승으로 안 잡힌다.
  const s = { pct: 0.8, vol: 100, vol_avg20: 100, price: 100, wk52_high: 200 };
  const r = classifyStock(s, -5.8);
  assert.ok(!r.cats.includes('counter_up'));
});

test('상승장에선 역행 하한선 미적용: 시장 +4%인데 종목 -1% → counter_up 유지', () => {
  const s = { pct: -1, vol: 100, vol_avg20: 100, price: 50, wk52_high: 200 };
  const r = classifyStock(s, 4);
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
    { code: '2', name: 'B', sector: 'semicon', pct: 1.6, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 4 },
  ];
  const { rank } = buildSignals(stocks, -5.8); // 둘 다 하한선(1.45) 위 → counter_up
  const cu = rank.find(g => g.cat === 'counter_up');
  assert.equal(cu.items.length, 2);
});

import { sectorAverages } from './_signals-core.mjs';

test('섹터 평균: 섹터별 평균 등락률·상승/하락 집계', () => {
  const stocks = [
    { sector: 'bio', pct: 2 }, { sector: 'bio', pct: 1 },
    { sector: 'semicon', pct: -5 }, { sector: 'semicon', pct: -3 }, { sector: 'semicon', pct: 0 },
  ];
  const r = sectorAverages(stocks);
  assert.equal(r.bio.avg, 1.5);
  assert.equal(r.bio.up, 2);
  assert.equal(r.semicon.total, 3);
  assert.equal(r.semicon.dn, 2);
  assert.ok(Math.abs(r.semicon.avg - (-8 / 3)) < 1e-9);
});

import { etfSectorRotation, etfSafeHaven, etfLead } from './_signals-core.mjs';

test('섹터 로테이션: 등락률 내림차순', () => {
  const byCode = { '091170': { pct: -3.15, amount: 16000 }, '139260': { pct: -6.22, amount: 534000 }, '449450': { pct: -6.29, amount: 40000 } };
  const r = etfSectorRotation(byCode);
  assert.equal(r[0].label, '은행');       // 가장 덜 빠짐
  assert.equal(r[r.length - 1].label, '방산'); // 가장 약세
});

test('안전자산: 금·채권 + 시장 대비 행', () => {
  const byCode = { '132030': { pct: 0.91 }, '148070': { pct: 0.14 }, '114260': { pct: 0.09 } };
  const r = etfSafeHaven(byCode, -5.79);
  assert.equal(r.market, -5.79);
  assert.equal(r.rows[0].label, '금');
});

test('리드 헤드라인: 인버스 거래량 배수 크면 인버스 헤드라인', () => {
  const lead = etfLead({ invVolMultiple: 46 });
  assert.ok(lead.title.includes('인버스'));
  assert.ok(lead.body.includes('46'));
});

test('리드 헤드라인: 거래량↑지만 거래대금 비중 중립(49%)이면 엇갈림 톤으로 완화', () => {
  const lead = etfLead({ invVolMultiple: 52, downRatio: 49 });
  assert.ok(lead.title.includes('엇갈린'));
  assert.ok(lead.body.includes('52'));
});

test('리드 헤드라인: 거래대금도 하락 우위(72%)면 인버스 헤드라인 유지', () => {
  const lead = etfLead({ invVolMultiple: 52, downRatio: 72 });
  assert.ok(lead.title.includes('인버스'));
});

import { classifySupply } from './_signals-core.mjs';

test('수급: 외국인 3일 연속 순매수 → foreign_buy', () => {
  const trend = [{ foreign: 100 }, { foreign: 50 }, { foreign: 30 }]; // 최신순
  const r = classifySupply(trend);
  assert.ok(r.cats.includes('foreign_buy'));
});

test('수급: 기관 전일 매도→당일 매수 전환', () => {
  const trend = [{ organ: 100 }, { organ: -50 }];
  const r = classifySupply(trend);
  assert.ok(r.cats.includes('inst_buy'));
});

test('수급: 신호 없으면 빈 cats', () => {
  const trend = [{ foreign: -10, organ: -10 }, { foreign: -5, organ: -5 }];
  const r = classifySupply(trend);
  assert.deepEqual(r.cats, []);
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

test('why+enrich: 수급만 있는 종목도 enrich로 설명 문구가 채워진다', () => {
  const stocks = [{ code: '1', name: 'A', sector: 'defense', pct: -1, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 1 }];
  const { signals } = buildSignals(stocks, -5.8, { enrich: () => ({ cats: ['inst_buy'], badges: ['기관 5일 연속 순매수'] }) });
  assert.equal(signals.length, 1);
  assert.ok(signals[0].cats.includes('inst_buy'));
  assert.ok(signals[0].why && signals[0].why.length > 0);
});

test('신호 카드 목록은 SIGNALS_DISPLAY_MAX개로 제한 (랭킹은 전체 집계 유지)', () => {
  const stocks = [];
  for (let i = 0; i < 12; i++) stocks.push({ code: String(i), name: 'S' + i, sector: 'bio', pct: -1, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 1 });
  const { signals, rank } = buildSignals(stocks, -5.8, { enrich: () => ({ cats: ['inst_buy'], badges: ['기관'] }) });
  assert.equal(signals.length, SIGNALS_DISPLAY_MAX);
  const ib = rank.find((g) => g.cat === 'inst_buy');
  assert.equal(ib.items.length, 12); // 랭킹은 전체 12개 집계
});
