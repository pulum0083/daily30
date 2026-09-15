// 장중 대결판 응답 조립 회귀 테스트 — 네트워크 없이 9/14 11:00 실측 값으로 리플레이
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildIntradayVs } from './_vs-intraday.mjs';
import { pct } from './_vs-core.mjs';

const kst = (s) => Date.parse(s + 'Z') - 9 * 3600 * 1000;
const OK = (f) => ['0', String(f), '0', '0', '0', '0', '0', '0', '0', String(-f)];
const flowRow = (t, f) => `<tr><td>${t}</td>${OK(f).map((x) => `<td>${x}</td>`).join('')}</tr>`;
const flowPage = (t, f) => `<table>${flowRow(t, f)}</table>`;
const minute = (ymd, hhmm, v) => [{ localDateTime: `${ymd}${hhmm}00`, currentPrice: v }];
const bars = (ymd, pairs) => pairs.map(([hhmm, v]) => ({ localDateTime: `${ymd}${hhmm}00`, currentPrice: v }));
// 11:00 봉이 끝나고 1분 더 지난 뒤(11:02대)에 조회한다 — 지금 분·직전 분의 봉은 아직 흔들려서 쓰지 않는다.
const AFTER_1100 = kst('2026-09-14T11:02:30');

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
  const d = await buildIntradayVs({ now: AFTER_1100, ...fakes() });
  assert.equal(d.status, 'ok');
  assert.equal(d.time, '11:00');
  assert.equal(d.prev.rel, '지난 금요일');
  assert.equal(d.prev.label, '9/11(금)');
  assert.deepEqual([d.kospi.t, d.kospi.y, d.kospi.diff, d.kospi.judge], [-2.56, -2.42, -0.14, 'same']);
  assert.equal(d.flow.foreignDiff, -8693);
  assert.equal(d.flow.time, '11:00');
  assert.equal(d.flow.judge, 'weak');
  assert.equal(d.verdict.title, '지난 금요일과 비슷해요');
  assert.equal(d.issues, null); // C2 — 이슈 아카이브 6개 상한·시각 갱신 때문에 항상 null(SERVICE_RULES §49)
});

test('주도주 — 한 종목이라도 비면 평균을 만들지 않는다(§0)', async () => {
  const d = await buildIntradayVs({ now: AFTER_1100, ...fakes() });
  const s = d.leaders.find((l) => l.code === '005930');
  assert.deepEqual([s.t, s.y, s.diff, s.pxT], [-2.89, -4.28, 1.39, 252000]);
  assert.equal(d.leaders.find((l) => l.code === '000660').t, null);
  assert.equal(d.avg, null);
});

// ── 비교 시각 통일(2026-09-15) — 9/15 10:11 실측에서 진행 중인 봉·종목마다 다른 분이 섞였다 ──

function withMinute1059(overrides = {}) {
  const f = fakes();
  const fetchJson = async (url) => {
    for (const [re, v] of Object.entries(overrides)) if (new RegExp(re).test(url)) return v;
    if (/KOSPI\/minute\?startDateTime=202609140900/.test(url)) return bars('20260914', [['1059', 6740], ['1100', 6732.94]]);
    if (/KOSPI\/minute\?startDateTime=202609110900/.test(url)) return bars('20260911', [['1059', 6870], ['1100', 6863.70]]);
    if (/005930\/minute\?startDateTime=202609140900/.test(url)) return bars('20260914', [['1059', 252500], ['1100', 252000]]);
    if (/005930\/minute\?startDateTime=202609110900/.test(url)) return bars('20260911', [['1059', 258000], ['1100', 257500]]);
    return f.fetchJson(url);
  };
  const fetchText = async (url) => (/bizdate=20260914/.test(url)
    ? `<table>${flowRow('11:00', -20900)}${flowRow('10:59', -20000)}</table>`
    : `<table>${flowRow('11:00', -12207)}${flowRow('10:59', -12000)}</table>`);
  return { fetchJson, fetchText };
}

test('지금 분·직전 분의 봉은 버린다 — 11:01:30엔 10:59 봉끼리 맞댄다', async () => {
  const d = await buildIntradayVs({ now: kst('2026-09-14T11:01:30'), ...withMinute1059() });
  assert.equal(d.time, '10:59');
  assert.equal(d.kospi.t, pct(6740, 6909.91));
  assert.equal(d.kospi.y, pct(6870, 7033.92));
  assert.equal(d.leaders.find((l) => l.code === '005930').t, pct(252500, 259500));
  assert.equal(d.flow.time, '10:59');
  assert.equal(d.flow.foreignDiff, -20000 - -12000);
});

test('종목 하나가 1분 늦으면 코스피·수급·다른 종목까지 그 분으로 맞춘다', async () => {
  const d = await buildIntradayVs({ now: AFTER_1100, ...withMinute1059({ '005930\\/minute\\?startDateTime=202609140900': bars('20260914', [['1059', 252500]]) }) });
  assert.equal(d.time, '10:59');
  assert.equal(d.kospi.t, pct(6740, 6909.91));             // 코스피도 11:00이 아니라 10:59
  const s = d.leaders.find((l) => l.code === '005930');
  assert.deepEqual([s.t, s.y], [pct(252500, 259500), pct(258000, 269000)]);
  assert.equal(d.flow.time, '10:59');
});

test('종목 하나가 2분 넘게 늦으면 그 종목만 비우고 비교 시각은 내리지 않는다', async () => {
  const d = await buildIntradayVs({ now: AFTER_1100, ...withMinute1059({ '005930\\/minute\\?startDateTime=202609140900': bars('20260914', [['1057', 253000]]) }) });
  assert.equal(d.time, '11:00');
  const s = d.leaders.find((l) => l.code === '005930');
  assert.deepEqual([s.t, s.y, s.diff, s.pxT, s.pxY], [null, null, null, null, null]);
});

test('수급 표가 1분 늦으면 비교 시각을 수급 행 시각으로 내린다(I1)', async () => {
  const f = withMinute1059();
  const fetchText = async (url) => (/bizdate=20260914/.test(url)
    ? `<table>${flowRow('10:59', -20000)}</table>`
    : `<table>${flowRow('11:00', -9999)}${flowRow('10:59', -12000)}</table>`);
  const d = await buildIntradayVs({ now: AFTER_1100, ...f, fetchText });
  assert.equal(d.time, '10:59');
  assert.equal(d.flow.time, '10:59');
  assert.equal(d.flow.foreignDiff, -8000);   // −20000 − (−12000). 어제 11:00 행(−9999)과 비교하면 틀린다
  assert.equal(d.kospi.t, pct(6740, 6909.91));
});

test('수급 표가 2분 넘게 늦으면 수급만 비우고 비교 시각은 그대로', async () => {
  const f = withMinute1059();
  const fetchText = async (url) => (/bizdate=20260914/.test(url) ? flowPage('10:55', -5000) : flowPage('10:55', -3000));
  const d = await buildIntradayVs({ now: AFTER_1100, ...f, fetchText });
  assert.equal(d.time, '11:00');
  assert.equal(d.flow, null);
});

test('오늘 1분봉이 아직 없거나 굳지 않은 봉뿐이면 waiting', async () => {
  const f = fakes();
  const none = async (url) => (/minute\?startDateTime=20260914/.test(url) ? [] : f.fetchJson(url));
  assert.deepEqual(await buildIntradayVs({ now: kst('2026-09-14T09:01:10'), ...f, fetchJson: none }), { status: 'waiting' });
  const onlyForming = async (url) => (/KOSPI\/minute\?startDateTime=20260914/.test(url) ? bars('20260914', [['0900', 6905], ['0901', 6900]]) : f.fetchJson(url));
  assert.deepEqual(await buildIntradayVs({ now: kst('2026-09-14T09:01:40'), ...f, fetchJson: onlyForming }), { status: 'waiting' });
});

test('수급 원천이 실패해도 나머지는 그린다 — flow만 null', async () => {
  const f = fakes();
  const d = await buildIntradayVs({ now: AFTER_1100, ...f, fetchText: async () => { throw new Error('down'); } });
  assert.equal(d.status, 'ok');
  assert.equal(d.flow, null);
  assert.equal(d.verdict.sub, '코스피가 같은 시각 기준 거의 같은 자리예요(−0.14%p)');
});

test('이슈는 항상 null — 이슈 아카이브·키워드 사전을 부르지 않는다(C2)', async () => {
  const f = fakes();
  const boom = async (url) => { throw new Error('호출되면 안 된다: ' + url); };
  const fetchJson = async (url) => (/kospi-news|issue-keywords/.test(url) ? boom(url) : f.fetchJson(url));
  const d = await buildIntradayVs({ now: AFTER_1100, ...f, fetchJson });
  assert.equal(d.status, 'ok');
  assert.equal(d.issues, null);
});
