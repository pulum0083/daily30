import { test } from 'node:test';
import assert from 'node:assert/strict';
import { regularFlowRow, buildCloseVs, closeCacheControl } from './_vs-close.mjs';
import { round2, prevTradingDay } from './_vs-core.mjs';

const r = (t) => ({ t, 개인: 0, 외국인: 0, 기관: 0, inst: {} });

test('15:31~15:40 사이 마지막 행을 고른다 — 애프터장 행은 쓰지 않는다', () => {
  const rows = [r('17:10'), r('16:05'), r('15:40'), r('15:35'), r('15:30')];
  assert.equal(regularFlowRow(rows).t, '15:40');
});

test('15:31 이전 행뿐이면 null — 장이 아직 안 끝난 것이다', () => {
  assert.equal(regularFlowRow([r('15:30'), r('15:20')]), null);
});

test('15:30~15:40 사이엔 early — 마감 카드를 만들지 않는다', async () => {
  const res = await buildCloseVs({ now: Date.parse('2026-09-16T06:35:00Z') }); // 15:35 KST
  assert.equal(res.status, 'early');
});

test('09:00~15:30 장중엔 closed — 장중 대결판이 담당한다', async () => {
  const res = await buildCloseVs({ now: Date.parse('2026-09-16T04:30:00Z') }); // 13:30 KST
  assert.equal(res.status, 'closed');
});

// ── status:'ok' 조립 통합 테스트 — 페이지네이션 → minuteBars/prevClose → rate/heatAxis/flowAxis/sectorRows 조립 ──
// api/_vs-intraday.test.mjs의 genericJson/minute/flowRow 스타일을 그대로 따른다.

const OK = (f) => ['0', String(f), '0', '0', '0', '0', '0', '0', '0', String(-f)];
const flowRow = (t, f) => `<tr><td>${t}</td>${OK(f).map((x) => `<td>${x}</td>`).join('')}</tr>`;
const flowPage = (t, f) => `<table>${flowRow(t, f)}</table>`;
const minute = (ymd, hhmm, v) => [{ localDateTime: `${ymd}${hhmm}00`, currentPrice: v }];
const toYmd = (dash) => dash.replace(/-/g, '');
const toDash = (ymd) => `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}`;

function baseFor(code) {
  let h = 0;
  for (const c of code) h = (h * 31 + c.charCodeAt(0)) % 97;
  return 1000 + h * 10;
}
// KOSPI 이외(코스닥·코스피200·섹터 대표 24종목)는 코드마다 다른 기준가 + 날짜별로 살짝 흔든 당일 값을 준다 —
// axes.market·axes.sectors가 값을 채우기만 하면 되고 정확한 수치는 이 테스트의 관심사가 아니다.
function genericJson(url) {
  let m;
  if ((m = url.match(/\/(index|item)\/([A-Za-z0-9]+)\/minute\?startDateTime=(\d{8})(\d{4})&endDateTime=(\d{8})(\d{4})/))) {
    const [, , code, sYmd, sHM, , eHM] = m;
    if (sHM === '1530' && eHM === '1530') return minute(sYmd, '1530', baseFor(code)); // prevClose(item)
    const scale = 1 + (Number(sYmd.slice(6, 8)) % 5) / 100;
    return minute(sYmd, '0905', baseFor(code) * scale);
  }
  if ((m = url.match(/\/index\/([A-Za-z0-9]+)\/day\?startDateTime=\d{8}0000&endDateTime=(\d{8})0000/))) {
    const [, code, endYmd] = m;
    const target = toYmd(prevTradingDay(toDash(endYmd)));
    return [{ localDate: target, closePrice: baseFor(code) }];
  }
  throw new Error('unexpected ' + url);
}

// 코스피만 값을 손으로 고정해 diff를 검증한다: 기준가 T=6700·Y=6600, 15:30 봉 T=6767(+1.00%)·Y=6633(+0.50%).
function fetchJsonOk(url) {
  if (/\/index\/KOSPI\/minute\?startDateTime=202609160900&endDateTime=202609161530/.test(url)) return minute('20260916', '1500', 6767);
  if (/\/index\/KOSPI\/minute\?startDateTime=202609150900&endDateTime=202609151530/.test(url)) return minute('20260915', '1500', 6633);
  if (/\/index\/KOSPI\/day\?startDateTime=\d{8}0000&endDateTime=202609160000/.test(url)) return [{ localDate: '20260915', closePrice: 6700 }];
  if (/\/index\/KOSPI\/day\?startDateTime=\d{8}0000&endDateTime=202609150000/.test(url)) return [{ localDate: '20260914', closePrice: 6600 }];
  return genericJson(url);
}

// 오늘(9/16) 수급 표엔 15:31~15:40 사이 마지막 행(15:40, 외국인 -20900)과 그 뒤 애프터장 행 두 개
// (16:05·17:10, 명백히 다른 값)를 함께 준다 — 조립이 애프터장 행을 집으면 이 테스트가 바로 잡아낸다.
const fetchTextOk = async (url) => {
  const m = url.match(/bizdate=(\d{8})/);
  if (m && m[1] === '20260916') {
    return `<table>${flowRow('17:10', -99999)}${flowRow('16:05', -88888)}${flowRow('15:40', -20900)}${flowRow('15:35', -20500)}${flowRow('15:30', -20000)}</table>`;
  }
  return flowPage('15:40', -12207); // 어제(9/15) 15:40 행
};

// 15:40 KST(정규장 확정 + 확정 수급 행 존재)
const AT_1540 = Date.parse('2026-09-16T06:40:00Z');

test('status:ok — 응답 모양(kospi·flow·axes·verdict·time·today/prev 라벨)이 갖춰진다', async () => {
  const d = await buildCloseVs({ now: AT_1540, fetchJson: fetchJsonOk, fetchText: fetchTextOk });
  assert.equal(d.status, 'ok');
  assert.equal(d.time, '15:30');
  assert.equal(d.today.date, '2026-09-16');
  assert.ok(d.today.label, 'today.label 없음');
  assert.equal(d.prev.date, '2026-09-15');
  assert.ok(d.prev.label, 'prev.label 없음');
  assert.ok(d.kospi, 'kospi 없음');
  assert.ok(d.flow, 'flow 없음');
  assert.ok(d.axes, 'axes 없음');
  assert.ok(d.verdict, 'verdict 없음');
});

test('axes는 heat·market.kosdaq·market.kospi200·sectors 4개를 항상 갖는다', async () => {
  const d = await buildCloseVs({ now: AT_1540, fetchJson: fetchJsonOk, fetchText: fetchTextOk });
  assert.ok(d.axes.heat, 'axes.heat 없음');
  assert.ok(d.axes.market.kosdaq, 'axes.market.kosdaq 없음');
  assert.ok(d.axes.market.kospi200, 'axes.market.kospi200 없음');
  assert.ok(Array.isArray(d.axes.sectors), 'axes.sectors 배열 아님');
  assert.ok(d.axes.sectors.length > 0, '섹터가 하나도 없음');
});

test('16:05·17:10 애프터장 행은 쓰지 않는다 — flow·axes.flow 모두 15:40 값이어야 한다', async () => {
  const d = await buildCloseVs({ now: AT_1540, fetchJson: fetchJsonOk, fetchText: fetchTextOk });
  assert.equal(d.flow.time, '15:40');
  assert.equal(d.flow.t.외국인, -20900);        // 16:05(-88888)·17:10(-99999)이 아니다
  assert.equal(d.flow.foreignDiff, -20900 - -12207);
  assert.equal(d.axes.flow.main.외국인.t, -20900);
  assert.equal(d.axes.flow.main.외국인.y, -12207);
});

test('kospi.diff는 round2(t - y) — 반올림 전 값을 뺀다', async () => {
  const d = await buildCloseVs({ now: AT_1540, fetchJson: fetchJsonOk, fetchText: fetchTextOk });
  assert.equal(d.kospi.t, 1);
  assert.equal(d.kospi.y, 0.5);
  assert.equal(d.kospi.diff, round2(d.kospi.t - d.kospi.y));
  assert.equal(d.kospi.diff, 0.5);
});

// ── 시간 경계를 정확히 고정한다 ──

test('15:29 → closed', async () => {
  assert.equal((await buildCloseVs({ now: Date.parse('2026-09-16T06:29:00Z') })).status, 'closed');
});

test('15:30 → early', async () => {
  assert.equal((await buildCloseVs({ now: Date.parse('2026-09-16T06:30:00Z') })).status, 'early');
});

test('15:39 → early', async () => {
  assert.equal((await buildCloseVs({ now: Date.parse('2026-09-16T06:39:00Z') })).status, 'early');
});

test('15:40 → 조립된다(early가 아니다)', async () => {
  const d = await buildCloseVs({ now: AT_1540, fetchJson: fetchJsonOk, fetchText: fetchTextOk });
  assert.notEqual(d.status, 'early');
  assert.notEqual(d.status, 'closed');
});

test('공휴일이면 16:00이라도 closed', async () => {
  const boom = async () => { throw new Error('호출되면 안 된다'); };
  const d = await buildCloseVs({ now: Date.parse('2026-09-24T07:00:00Z'), fetchJson: boom, fetchText: boom }); // 추석 연휴, 16:00 KST
  assert.equal(d.status, 'closed');
});

// ── CDN 캐시 제어 ──

test("closeCacheControl('ok')는 s-maxage=1800을 갖는다", () => {
  const cc = closeCacheControl('ok');
  assert.ok(cc.includes('s-maxage=1800'), `기대: s-maxage=1800, 받음: ${cc}`);
  assert.ok(cc.includes('stale-while-revalidate=600'), `기대: stale-while-revalidate=600, 받음: ${cc}`);
});

test("closeCacheControl('closed')는 s-maxage=60을 갖는다", () => {
  const cc = closeCacheControl('closed');
  assert.ok(cc.includes('s-maxage=60'), `기대: s-maxage=60, 받음: ${cc}`);
  assert.ok(cc.includes('stale-while-revalidate=60'), `기대: stale-while-revalidate=60, 받음: ${cc}`);
});

test("closeCacheControl('early')는 s-maxage=60을 갖는다", () => {
  const cc = closeCacheControl('early');
  assert.ok(cc.includes('s-maxage=60'), `기대: s-maxage=60, 받음: ${cc}`);
});

test("closeCacheControl('waiting')는 s-maxage=60을 갖는다", () => {
  const cc = closeCacheControl('waiting');
  assert.ok(cc.includes('s-maxage=60'), `기대: s-maxage=60, 받음: ${cc}`);
});

test("closeCacheControl(undefined)는 s-maxage=60을 갖는다", () => {
  const cc = closeCacheControl(undefined);
  assert.ok(cc.includes('s-maxage=60'), `기대: s-maxage=60, 받음: ${cc}`);
});
