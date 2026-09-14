// 장중 대결판 응답 조립 회귀 테스트 — 네트워크 없이 9/14 11:00 실측 값으로 리플레이
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildIntradayVs } from './_vs-intraday.mjs';

const kst = (s) => Date.parse(s + 'Z') - 9 * 3600 * 1000;
const OK = (f) => ['0', String(f), '0', '0', '0', '0', '0', '0', '0', String(-f)];
const flowPage = (t, f) => `<table><tr><td>${t}</td>${OK(f).map((x) => `<td>${x}</td>`).join('')}</tr></table>`;
const minute = (ymd, hhmm, v) => [{ localDateTime: `${ymd}${hhmm}00`, currentPrice: v }];

function fakes() {
  const fetchJson = async (url) => {
    if (/KOSPI\/day/.test(url)) return [{ localDate: '20260910', closePrice: 7033.92 }, { localDate: '20260911', closePrice: 6909.91 }];
    if (/KOSPI\/minute\?startDateTime=202609140900/.test(url)) return minute('20260914', '1100', 6732.94);
    if (/KOSPI\/minute\?startDateTime=202609110900/.test(url)) return minute('20260911', '1100', 6863.70);
    // 005930 직전 종가 — 직전 거래일 15:30 1분봉(C1). 값은 옛 일봉 종가와 같게 둬 나머지 기대값을 그대로 유지한다.
    if (/005930\/minute\?startDateTime=202609111530/.test(url)) return minute('20260911', '1530', 259500);
    if (/005930\/minute\?startDateTime=202609101530/.test(url)) return minute('20260910', '1530', 269000);
    if (/005930\/minute\?startDateTime=202609140900/.test(url)) return minute('20260914', '1100', 252000);
    if (/005930\/minute\?startDateTime=202609110900/.test(url)) return minute('20260911', '1100', 257500);
    if (/\/(000660|005380)\//.test(url)) return [];
    if (/kospi-news-2026-09-14/.test(url)) return { history: [{ time: '10:30', market: { title: '코스피, AI 속도 조절론·중동 불안에 급락' } }] };
    if (/kospi-news-2026-09-11/.test(url)) return { history: [{ time: '10:00', market: { title: '국제유가 급등 여파' } }] };
    if (/issue-keywords/.test(url)) return { keywords: ['AI 속도 조절론', '중동', '유가'] };
    throw new Error('unexpected ' + url);
  };
  const fetchText = async (url) => (/bizdate=20260914/.test(url) ? flowPage('11:00', -20900) : flowPage('11:00', -12207));
  return { fetchJson, fetchText };
}

test('주말·장 전·장 후엔 closed — 네트워크를 부르지 않는다', async () => {
  const boom = async () => { throw new Error('호출되면 안 된다'); };
  for (const s of ['2026-09-13T11:00:00', '2026-09-14T08:59:00', '2026-09-14T15:31:00', '2026-09-24T11:00:00']) {
    assert.deepEqual(await buildIntradayVs({ now: kst(s), fetchJson: boom, fetchText: boom }), { status: 'closed' }, s);
  }
});

test('9/14 11:00 리플레이 — 코스피·외국인·결론', async () => {
  const d = await buildIntradayVs({ now: kst('2026-09-14T11:00:30'), ...fakes() });
  assert.equal(d.status, 'ok');
  assert.equal(d.time, '11:00');
  assert.equal(d.prev.rel, '지난 금요일');
  assert.equal(d.prev.label, '9/11(금)');
  assert.deepEqual([d.kospi.t, d.kospi.y, d.kospi.diff, d.kospi.judge], [-2.56, -2.42, -0.14, 'same']);
  assert.equal(d.flow.foreignDiff, -8693);
  assert.equal(d.flow.judge, 'weak');
  assert.equal(d.verdict.title, '지난 금요일과 비슷해요');
  assert.equal(d.issues, null); // C2 — 이슈 아카이브 6개 상한·시각 갱신 때문에 항상 null(SERVICE_RULES §49)
});

test('주도주 — 한 종목이라도 비면 평균을 만들지 않는다(§0)', async () => {
  const d = await buildIntradayVs({ now: kst('2026-09-14T11:00:30'), ...fakes() });
  const s = d.leaders.find((l) => l.code === '005930');
  assert.deepEqual([s.t, s.y, s.diff, s.pxT], [-2.89, -4.28, 1.39, 252000]);
  assert.equal(d.leaders.find((l) => l.code === '000660').t, null);
  assert.equal(d.avg, null);
});

test('오늘 1분봉이 아직 없으면 waiting', async () => {
  const f = fakes();
  const fetchJson = async (url) => (/minute\?startDateTime=20260914/.test(url) ? [] : f.fetchJson(url));
  assert.deepEqual(await buildIntradayVs({ now: kst('2026-09-14T09:01:10'), ...f, fetchJson }), { status: 'waiting' });
});

test('수급 원천이 실패해도 나머지는 그린다 — flow만 null', async () => {
  const f = fakes();
  const d = await buildIntradayVs({ now: kst('2026-09-14T11:00:30'), ...f, fetchText: async () => { throw new Error('down'); } });
  assert.equal(d.status, 'ok');
  assert.equal(d.flow, null);
  assert.equal(d.verdict.sub, '코스피가 같은 시각 기준 거의 같은 자리예요(−0.14%p)');
});

test('이슈는 항상 null — 이슈 아카이브·키워드 사전을 부르지 않는다(C2)', async () => {
  const f = fakes();
  const boom = async (url) => { throw new Error('호출되면 안 된다: ' + url); };
  const fetchJson = async (url) => (/kospi-news|issue-keywords/.test(url) ? boom(url) : f.fetchJson(url));
  const d = await buildIntradayVs({ now: kst('2026-09-14T11:00:30'), ...f, fetchJson });
  assert.equal(d.status, 'ok');
  assert.equal(d.issues, null);
});
