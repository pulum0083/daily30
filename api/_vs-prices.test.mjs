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

test('직전 종가 — 기준일 당일 봉은 쓰지 않는다(장 마감 뒤엔 애프터장 가격, §48)', async () => {
  const f = fake([[/index\/KOSPI\/day/, [
    { localDate: '20260910', closePrice: 7033.92 },
    { localDate: '20260911', closePrice: 6909.91 },
    { localDate: '20260914', closePrice: 6684.37 },
  ]]]);
  assert.equal(await prevClose('index', 'KOSPI', '20260914', f), 6909.91);
  assert.equal(await prevClose('index', 'KOSPI', '20260911', f), 7033.92);
});

test('직전 종가가 없으면 null', async () => {
  assert.equal(await prevClose('item', '005930', '20260914', async () => []), null);
});

test('곡선 — 09:00 기준 경과 분, 5분 샘플, 마지막 점은 항상', () => {
  const bars = [{ t: '0900', v: 100 }, { t: '0903', v: 99 }, { t: '0905', v: 98 }, { t: '0907', v: 97 }, { t: '0910', v: 96 }];
  assert.deepEqual(curve(bars, 100, '0907'), [[0, 0], [5, -2], [7, -3]]);
});
