// 장 시간이 바뀐 날(2026-11-19 수능일 10:00~16:30) 다음 날의 대결판·마감 세션 — 네트워크 없이 리플레이(§91)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildIntradayVs } from './_vs-intraday.mjs';
import { buildCloseVs } from './_vs-close.mjs';
import { prevClose, curve } from './_vs-prices.mjs';
import { regularSessionFromBars, sessionHours, isCloseWindow } from './_kr-regular-session.mjs';

const kst = (s) => Date.parse(s + 'Z') - 9 * 3600 * 1000;
const bar = (ymd, hm, v) => ({ localDateTime: `${ymd}${hm}00`, currentPrice: v, highPrice: v + 1, lowPrice: v - 1, accumulatedTradingVolume: 100 });
// 날짜별 1분봉 — 11/18 평일(15:30 종가), 11/19 수능일(10:00 개장, 15:30은 장중, 16:30 종가), 11/20 평일
const ITEM = {
  20261118: [['1530', 194700]],
  20261119: [['1035', 190500], ['1530', 194500], ['1630', 196900]],
  20261120: [['0935', 187200]],
};
const INDEX = { 20261119: [['1035', 1010], ['1630', 1020]], 20261120: [['0935', 990], ['1530', 985]] };

function fetchJson(url) {
  let m;
  if ((m = url.match(/\/(index|item)\/[A-Za-z0-9]+\/minute\?startDateTime=(\d{8})(\d{4})&endDateTime=(\d{8})(\d{4})/))) {
    const [, kind, sY, sHM, eY, eHM] = m;
    const src = kind === 'item' ? ITEM : INDEX;
    const out = [];
    for (const [d, rows] of Object.entries(src)) {
      for (const [hm, v] of rows) {
        const k = d + hm;
        if (k >= sY + sHM && k <= eY + eHM) out.push(bar(d, hm, v));
      }
    }
    return out;
  }
  if ((m = url.match(/\/index\/[A-Za-z0-9]+\/day\?.*endDateTime=(\d{8})0000/))) {
    return m[1] === '20261120' ? [{ localDate: '20261119', closePrice: 1000 }] : [{ localDate: '20261118', closePrice: 1000 }];
  }
  return {};   // 수급 원천은 비운다 — 이 테스트는 가격 비교만 본다
}

test('장 시간 표 — 수능일은 16:30~16:39가 종가 봉, 평일은 15:30~15:39', () => {
  assert.deepEqual(sessionHours('20261119'), ['1000', '1630', '1639']);
  assert.deepEqual(sessionHours('20261120'), ['0900', '1530', '1539']);
  assert.equal(isCloseWindow('1530', '20261119'), false);
  assert.equal(isCloseWindow('1632', '20261119'), true);
  assert.equal(isCloseWindow('1532', '20261120'), true);
});

test('전일 종가 — 수능일은 15:30 장중 봉(194,500)이 아니라 16:30 종가 봉(196,900)', async () => {
  assert.equal(await prevClose('item', '005930', '20261120', async (u) => fetchJson(u)), 196900);
});

test('11/20 09:37 장중 비교 — 어제는 개장 뒤 같은 시각(10:35)과 맞댄다', async () => {
  const d = await buildIntradayVs({ now: kst('2026-11-20T09:37:30'), fetchJson: async (u) => fetchJson(u) });
  assert.equal(d.status, 'ok');
  assert.equal(d.time, '09:35');
  assert.equal(d.prev.time, undefined);   // 화면엔 평소처럼 오늘과 같은 시각으로 보인다
  const s = d.leaders.find((l) => l.code === '005930');
  assert.equal(s.t, -4.93);          // 187,200 ÷ 196,900(11/19 공식 종가)
  assert.equal(s.y, -2.16);          // 190,500 ÷ 194,700(11/18 공식 종가)
  assert.equal(d.kospi.y, 1);        // 어제 10:35
  assert.deepEqual(d.kospi.curveY[0], [35, 1]);   // 개장 뒤 35분 — 오늘 09:35와 같은 자리
});

test('11/20 마감 뒤 — 어제 값은 16:30 종가로(+2.0%), 15:30 장중 값이 아니다', async () => {
  const c = await buildCloseVs({ now: kst('2026-11-20T16:00:00'), fetchJson: async (u) => fetchJson(u) });
  assert.equal(c.status, 'ok');
  assert.equal(c.kospi.y, 2);
  assert.equal(c.kospi.t, -1.5);
});

test('마감 세션 — 수능일의 종가·전일 종가를 1분봉에서 바로 고른다', () => {
  const rows = Object.entries(ITEM).flatMap(([d, rs]) => rs.map(([hm, v]) => bar(d, hm, v))).filter((b) => b.localDateTime < '20261120');
  const r = regularSessionFromBars(rows);
  assert.equal(r.date, '20261119');
  assert.equal(r.close, 196900);
  assert.equal(r.prevClose, 194700);
});

test('곡선 x는 그날 개장 뒤 분', () => {
  assert.deepEqual(curve([{ t: '1035', v: 101 }], 100, '1035', '1000'), [[35, 1]]);
  assert.deepEqual(curve([{ t: '0935', v: 101 }], 100, '0935'), [[35, 1]]);
});
