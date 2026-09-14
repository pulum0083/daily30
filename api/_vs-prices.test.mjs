// 지수·종목 1분봉과 직전 종가 조회 회귀 테스트(설계 §6 #1·#2·#7)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { minuteBars, prevClose, curve } from './_vs-prices.mjs';

const fake = (map) => async (url) => { for (const [re, v] of map) if (re.test(url)) return v; throw new Error('unexpected ' + url); };

test('지수 1분봉 — 그 날짜 봉만 오름차순으로', async () => {
  const f = fake([[/index\/KOSPI\/minute\?startDateTime=202609141000&endDateTime=202609141100$/, [
    { localDateTime: '20260914100000', currentPrice: 6750.1 },
    { localDateTime: '20260913235900', currentPrice: 1 },          // 다른 날짜 — 버린다
    { localDateTime: '20260914110000', currentPrice: 6732.94 },
  ]]]);
  assert.deepEqual(await minuteBars('index', 'KOSPI', '20260914', f, '1000', '1100'),
    [{ t: '1000', v: 6750.1 }, { t: '1100', v: 6732.94 }]);
});

test('종목 경로는 item/{code}', async () => {
  let u = '';
  await minuteBars('item', '005930', '20260911', async (url) => { u = url; return []; });
  assert.match(u, /item\/005930\/minute\?startDateTime=202609110900&endDateTime=202609111530$/);
});

test('직전 종가(지수) — 기준일 당일 봉은 쓰지 않는다(장 마감 뒤엔 애프터장 가격, §48)', async () => {
  const f = fake([[/index\/KOSPI\/day/, [
    { localDate: '20260910', closePrice: 7033.92 },
    { localDate: '20260911', closePrice: 6909.91 },
    { localDate: '20260914', closePrice: 6684.37 },
  ]]]);
  assert.equal(await prevClose('index', 'KOSPI', '20260914', f), 6909.91);
  assert.equal(await prevClose('index', 'KOSPI', '20260911', f), 7033.92);
});

test('직전 종가(지수) — 고른 행의 날짜가 직전 거래일이 아니면 null(다른 날짜 폴백 금지, C1)', async () => {
  // 20260914의 직전 거래일은 20260911(금)인데, 데이터에 그 날짜 행이 없다(20260910까지만 있음) — 더 과거로 폴백하지 않는다
  const f = fake([[/index\/KOSPI\/day/, [
    { localDate: '20260909', closePrice: 7000 },
    { localDate: '20260910', closePrice: 7033.92 },
  ]]]);
  assert.equal(await prevClose('index', 'KOSPI', '20260914', f), null);
});

test('직전 종가(지수)가 없으면 null', async () => {
  assert.equal(await prevClose('index', 'KOSPI', '20260914', async () => []), null);
});

test('직전 종가(종목) — 직전 거래일의 15:30 1분봉 currentPrice만 쓴다(C1·§48, 2026-09-14 20:09 KST 실측)', async () => {
  // 9/15 기준 직전 거래일은 9/14. 일봉은 애프터장 가격(248,500/1,683,000/367,500)을 주지만
  // 15:30 1분봉의 공식 종가(249,000/1,697,000/371,500)만 쓴다.
  const f = fake([
    [/item\/005930\/minute\?startDateTime=202609141530&endDateTime=202609141530$/,
      [{ localDateTime: '20260914153000', currentPrice: 249000 }]],
    [/item\/000660\/minute\?startDateTime=202609141530&endDateTime=202609141530$/,
      [{ localDateTime: '20260914153000', currentPrice: 1697000 }]],
    [/item\/005380\/minute\?startDateTime=202609141530&endDateTime=202609141530$/,
      [{ localDateTime: '20260914153000', currentPrice: 371500 }]],
  ]);
  assert.equal(await prevClose('item', '005930', '20260915', f), 249000);
  assert.equal(await prevClose('item', '000660', '20260915', f), 1697000);
  assert.equal(await prevClose('item', '005380', '20260915', f), 371500);
});

test('직전 종가(종목) — 15:30 봉이 없으면 null. 다른 시각 봉으로 폴백하지 않는다(C1)', async () => {
  const f = fake([[/item\/005930\/minute/, []]]);
  assert.equal(await prevClose('item', '005930', '20260915', f), null);
  assert.equal(await prevClose('item', '005930', '20260914', f), null);
});

test('곡선 — 09:00 기준 경과 분, 5분 샘플, 마지막 점은 항상', () => {
  const bars = [{ t: '0900', v: 100 }, { t: '0903', v: 99 }, { t: '0905', v: 98 }, { t: '0907', v: 97 }, { t: '0910', v: 96 }];
  assert.deepEqual(curve(bars, 100, '0907'), [[0, 0], [5, -2], [7, -3]]);
});
