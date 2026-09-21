// 투자자별 순매수 1분 시계열(새 원천·저장본) 파서·시각 조회 회귀 테스트(SERVICE_RULES §56)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseInvestorTimeJson, liveFlowAt, storedFlowAt, LIVE_URL, STORE_URL } from './_vs-flow.mjs';

// 9/21 15:40 실측 행(억원) — 개인 + 외국인(9000+9001) + 기관(1000~7000) + 기타법인(7100) = 0
export const CLOSE_VALS = { 1000: 12474, 2000: -47, 3000: 1280, 3100: 1615, 4000: 27, 5000: 205,
  6000: -630, 7000: 0, 7100: 16585, 8000: -29790, 9000: -1603, 9001: -116 };
export function item(date, hhmmss, vals) {
  return { bizdate: date, time: hhmmss, netAmounts: Object.entries(vals).map(([k, v]) => ({ investorGubun: k, diffValue: String(v * 1e8) })) };
}
export const livePage = (items, last = true) => ({ content: items, last: last ? 'true' : 'false' });

test('실응답 한 페이지를 읽는다 — 사모·국가는 투신·연기금, 기타외국인은 외국인에 더한다', () => {
  const fx = JSON.parse(readFileSync(new URL('../scripts/fixtures/naver_market/investor_time_20260921.json', import.meta.url), 'utf8'));
  const r = parseInvestorTimeJson(fx).find((x) => x.t === '15:40');
  assert.equal(r.date, '20260921');
  assert.deepEqual([r.개인, r.외국인, r.기관], [-29790, -1719, 14924]);
  assert.equal(r.inst.투신, 2895);
  assert.equal(r.inst.연기금, -630);
  assert.equal(r.개인 + r.외국인 + r.기관 + r.기타법인, 0);
});

test('합계 0 검사를 통과하지 못한 행은 버린다(코드가 바뀐 경우 방어)', () => {
  const rows = parseInvestorTimeJson(livePage([item('20260921', '154000', { ...CLOSE_VALS, 8000: 0 }), item('20260921', '153900', CLOSE_VALS)]));
  assert.deepEqual(rows.map((r) => r.t), ['15:39']);
});

test('기관 세부 코드가 없으면 그 칸은 0이 아니라 null이다(§0)', () => {
  const vals = { ...CLOSE_VALS }; delete vals[4000];
  const r = parseInvestorTimeJson(livePage([item('20260921', '154000', { ...vals, 7100: 16612 })]))[0];
  assert.equal(r.inst.은행, null);
});

test('오늘 시계열에서 시각 이하 첫 행을 페이지를 넘기며 찾는다', async () => {
  const pages = [
    livePage([item('20260921', '113000', CLOSE_VALS), item('20260921', '110200', CLOSE_VALS)], false),
    livePage([item('20260921', '110100', CLOSE_VALS), item('20260921', '105900', CLOSE_VALS)], true),
  ];
  const seen = [];
  const hit = await liveFlowAt('20260921', '1100', async (url) => { const p = Number(url.match(/startIdx=(\d+)/)[1]); seen.push(p); return pages[p]; });
  assert.equal(hit.t, '10:59');
  assert.deepEqual(seen, [0, 1]);
});

test('원천 날짜가 요청 날짜와 다르면 null — 지난 날짜를 오늘 값으로 쓰지 않는다', async () => {
  assert.equal(await liveFlowAt('20260918', '1540', async () => livePage([item('20260921', '154000', CLOSE_VALS)])), null);
});

test('그 시각 이전 행이 없으면 null — 다른 시각으로 폴백하지 않는다', async () => {
  assert.equal(await liveFlowAt('20260921', '0900', async () => livePage([item('20260921', '090500', CLOSE_VALS)])), null);
});

test('깨진 행이 섞인 페이지를 만나면 null — 파싱 실패를 성공으로 착각하지 않는다(I1)', async () => {
  const broken = livePage([item('20260921', '154100', { 8000: 1 }), item('20260921', '154000', CLOSE_VALS)]);
  assert.equal(await liveFlowAt('20260921', '1540', async () => broken), null);
});

test('저장본에서 시각 이하 마지막 행을 읽고, 없거나 날짜가 다르면 null', async () => {
  const body = { date: '20260921', rows: [{ t: '15:30', 개인: 1 }, { t: '15:40', 개인: 2 }, { t: '16:25', 개인: 3 }] };
  let u = '';
  const hit = await storedFlowAt('20260921', '1540', async (url) => { u = url; return body; });
  assert.equal(hit.개인, 2);
  assert.equal(u, STORE_URL('20260921'));
  assert.equal(await storedFlowAt('20260918', '1540', async () => body), null);
  assert.equal(await storedFlowAt('20260921', '1540', async () => { throw new Error('404'); }).catch(() => 'threw'), 'threw');
});

test('오늘 원천은 코스피(대문자 KOSPI)·KRX로 고정한다', () => {
  assert.match(LIVE_URL(0), /tradeType=KRX&marketType=KOSPI&startIdx=0&pageSize=100$/);
});
