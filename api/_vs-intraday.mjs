// '어제랑 비교해서' 장중 대결판 응답 조립 — 코스피·수급·주도주·이슈를 직전 거래일 같은 시각과 맞댄다(설계 §4.2)
import { TH, prevTradingDay, relLabel, atOrBefore, pct, round2, judge, tickOk, verdict } from './_vs-core.mjs';
import { liveFlowAt, storedFlowAt } from './_vs-flow.mjs';
import { minuteBars, prevClose, curve } from './_vs-prices.mjs';
import { heatAxis, flowAxis } from './_vs-axes.mjs';
import { SECTOR_REPS, sectorRows } from './_vs-sectors.mjs';
// _vs-issues.mjs(issuesUntil·keywordDiff)는 지금 쓰지 않는다 — 아래 issues:null 주석 참고(C2). 계산 코드·사전은
// 남겨둔다(설계 남기기 — 불변 장중 기록이 생기면 다시 켠다).
import { isKospiHoliday, labelFromYmd } from './_market-calendar.mjs';

export const LEADERS = [['005930', '삼성전자'], ['000660', 'SK하이닉스'], ['005380', '현대차']];
const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };
// 비교 시각보다 이만큼(분) 넘게 늦은 원천은 비교 시각을 끌어내리지 않고 그 칸만 비운다.
// 수급 표는 보통 1분 늦게 갱신된다(9/15 09:14·10:11·13:16 실측 모두 1분 차).
const LAG_MIN = 2;

export async function getJson(url) {
  const r = await fetch(url, { headers: HDR, signal: AbortSignal.timeout(6000) });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return r.json();
}

const settle = (p, fallback) => Promise.resolve().then(() => p).catch(() => fallback);

// 어제 데이터(직전 거래일 1분봉·전일 종가·수급 표 페이지)는 다시 바뀌지 않는다. 엣지 캐시가 풀려 새로 조립할 때마다
// 네이버를 27번씩 부르던 것을 오늘 데이터만 부르게 줄인다(Fluid Compute는 인스턴스를 재사용한다 — 콜드 스타트면 처음부터).
// 캐시는 fetch 함수별로 따로 둔다(테스트의 가짜 fetch끼리 섞이지 않게). 날짜가 바뀌면 통째로 비운다.
const MEMO = new WeakMap();
function memoFor(fn, day) {
  let m = MEMO.get(fn);
  if (!m || m.day !== day) { m = { day, map: new Map() }; MEMO.set(fn, m); }
  return m.map;
}
// 진행 중인 요청도 공유한다(같은 조립 안에서 두 번 부르지 않게). 비었거나 실패한 결과는 담지 않는다 —
// 원천이 잠깐 빈 응답을 줬을 때 그 빈칸이 하루 종일 굳지 않게.
function remember(map, key, make, keep) {
  if (map.has(key)) return map.get(key);
  const p = Promise.resolve().then(make).then(
    (v) => { if (!keep(v)) map.delete(key); return v; },
    (e) => { map.delete(key); throw e; },
  );
  map.set(key, p);
  return p;
}
const hasRows = (v) => Array.isArray(v) && v.length > 0;
const isNum = (v) => typeof v === 'number';
const toMin = (hhmm) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(2, 4));
// 지금 분의 봉은 아직 만들어지는 중이다 — 그 값을 확정된 어제 봉과 맞대면 최대 1분 어긋난다(9/15 10:11 실측:
// 진행 중 −0.02% vs 확정 −0.16%). 막 끝난 분의 봉도 바로 굳지 않는다 — 9/15 13:30 봉을 5초 간격으로 다시 읽으니
// 끝난 뒤 약 1분 동안 응답마다 값이 오갔고(코스피 6,627.19↔6,632.57, SK하이닉스 1,694,000→1,695,000) 그 뒤에 멈췄다.
// 그래서 끝난 지 1분이 지난 봉(지금 분·직전 분 제외)만 쓴다. 화면은 2분쯤 늦게 따라온다.
const minusOne = (hhmm) => { const m = toMin(hhmm) - 1; return String(Math.floor(m / 60)).padStart(2, '0') + String(m % 60).padStart(2, '0'); };
const completed = (bars, hhmm) => (bars || []).filter((b) => b.t < minusOne(hhmm));

export async function buildIntradayVs({ now = Date.now(), fetchJson }) {
  const k = new Date(now + 9 * 3600 * 1000);
  const dash = k.toISOString().slice(0, 10);
  const hhmm = k.toISOString().slice(11, 16).replace(':', '');
  if (isKospiHoliday(k) || hhmm < '0901' || hhmm > '1530') return { status: 'closed' };

  const yDash = prevTradingDay(dash);
  const T = dash.replace(/-/g, ''), Y = yDash.replace(/-/g, '');
  const rel = relLabel(yDash, dash);
  const memoJ = memoFor(fetchJson, T);
  const once = (key, make, keep) => remember(memoJ, key, make, keep);
  // 어제 수급은 마감 잡이 저장한 파일이라 장중에 바뀌지 않는다 — 행이 있는 응답만 기억한다.
  const jsonY = (url) => remember(memoJ, url, () => fetchJson(url), (b) => Array.isArray(b?.rows) && b.rows.length > 0);

  // 코스피와 주도주 1분봉을 먼저 모은다 — 비교 시각은 이 둘과 수급 표를 모두 본 뒤에 정한다.
  const [kospiRaw, leadersRaw] = await Promise.all([
    Promise.all([
      settle(minuteBars('index', 'KOSPI', T, fetchJson, '0900', hhmm), []),
      settle(once('kY', () => minuteBars('index', 'KOSPI', Y, fetchJson), hasRows), []),
      settle(once('kBaseT', () => prevClose('index', 'KOSPI', T, fetchJson), isNum), null),
      settle(once('kBaseY', () => prevClose('index', 'KOSPI', Y, fetchJson), isNum), null),
    ]),
    Promise.all(LEADERS.map(async ([code, name]) => {
      const [bT, bY, pT, pY] = await Promise.all([
        settle(minuteBars('item', code, T, fetchJson, '0900', hhmm), []),
        settle(once(`bY:${code}`, () => minuteBars('item', code, Y, fetchJson), hasRows), []),
        settle(once(`pT:${code}`, () => prevClose('item', code, T, fetchJson), isNum), null),
        settle(once(`pY:${code}`, () => prevClose('item', code, Y, fetchJson), isNum), null),
      ]);
      return { code, name, bT: completed(bT, hhmm), bY, pT, pY };
    })),
  ]);
  const [kTall, kY, baseT, baseY] = kospiRaw;
  const kT = completed(kTall, hhmm);
  if (!kT.length) return { status: 'waiting' };

  // 비교 시각 = 코스피·주도주 3종목·수급 표가 모두 가진 가장 이른 확정 분. 하나만 LAG_MIN 넘게 늦으면
  // 그 원천은 제외하고(칸이 빈다) 나머지로 정한다 — 한 곳의 지연이 화면 전체를 몇 분씩 끌어내리지 않게.
  const kAt = kT[kT.length - 1].t;
  const fresh = (t, ref) => !!t && toMin(ref) - toMin(t) <= LAG_MIN;
  let at = kAt;
  for (const l of leadersRaw) {
    const last = l.bT.length ? l.bT[l.bT.length - 1].t : null;
    l.fresh = fresh(last, kAt);
    if (l.fresh && last < at) at = last;
  }
  // 수급 — 오늘 표에서 비교 시각 이하 마지막 행. 그 행이 조금 늦으면 비교 시각을 그 행 시각으로 내린다.
  // 어제는 오늘 행과 같은 분으로 고른다(I1).
  const fT = await settle(liveFlowAt(T, at, fetchJson), null);
  const flowOk = !!fT && fresh(fT.t.replace(':', ''), at);
  if (flowOk && fT.t.replace(':', '') < at) at = fT.t.replace(':', '');
  const fY = flowOk ? await settle(storedFlowAt(Y, at, jsonY), null) : null;
  const flow = flowOk && fY ? { t: fT, y: fY, time: fT.t, foreignDiff: fT.외국인 - fY.외국인 } : null;
  if (flow) flow.judge = judge(flow.foreignDiff, TH.eok);

  const kb = atOrBefore(kT, at), kyAt = atOrBefore(kY, at);
  const kospi = { t: kb ? pct(kb.v, baseT) : null, y: kyAt ? pct(kyAt.v, baseY) : null };
  kospi.diff = kospi.t != null && kospi.y != null ? round2(kospi.t - kospi.y) : null;
  kospi.judge = judge(kospi.diff, TH.pctPoint);
  kospi.curveT = curve(kT, baseT, at);
  kospi.curveY = curve(kY, baseY, at);

  const leaders = leadersRaw.map((l) => {
    // 늦은 종목은 비교하지 않는다(t·y·diff 모두 null). 오늘 봉을 고른 뒤 어제는 그 봉의 시각으로 고른다(I3).
    const tb = l.fresh ? atOrBefore(l.bT, at) : null;
    const yb = tb ? atOrBefore(l.bY, tb.t) : null;
    const t = tb ? pct(tb.v, l.pT) : null, y = yb ? pct(yb.v, l.pY) : null;
    return {
      code: l.code, name: l.name, t, y, diff: t != null && y != null ? round2(t - y) : null,
      pxT: tb && tickOk(tb.v) ? tb.v : null, pxY: yb && tickOk(yb.v) ? yb.v : null,
    };
  });
  const full = leaders.every((l) => l.t != null && l.y != null);
  const avg = full ? (() => {
    const t = round2(leaders.reduce((s, l) => s + l.t, 0) / leaders.length);
    const y = round2(leaders.reduce((s, l) => s + l.y, 0) / leaders.length);
    return { t, y, diff: round2(t - y), judge: judge(round2(t - y), TH.pctPoint) };
  })() : null;

  // 이슈 비교는 항상 null(C2) — 아카이브가 6개 상한으로 잘리고 최신 항목의 시각이 갱신 때마다
  // 덮어써져 "어제 이 시각까지"를 보장하지 못한다(SERVICE_RULES §49). 아카이브·사전 fetch도 하지 않는다.
  const issues = null;

  // ── 축 확장 ── 어제 값은 장중에 안 바뀌므로 전부 once()에 태운다(§49 메모 재사용)
  const idxAxis = async (code) => {
    const [bT, bY, pT, pY] = await Promise.all([
      settle(minuteBars('index', code, T, fetchJson, '0900', hhmm), []),
      settle(once(`iY:${code}`, () => minuteBars('index', code, Y, fetchJson), hasRows), []),
      settle(once(`iBT:${code}`, () => prevClose('index', code, T, fetchJson), isNum), null),
      settle(once(`iBY:${code}`, () => prevClose('index', code, Y, fetchJson), isNum), null),
    ]);
    const tb = atOrBefore(completed(bT, hhmm), at), yb = atOrBefore(bY, at);
    const t = tb ? pct(tb.v, pT) : null, y = yb ? pct(yb.v, pY) : null;
    return { t, y, diff: t != null && y != null ? round2(t - y) : null,
             judge: t != null && y != null ? judge(round2(t - y), TH.pctPoint) : null };
  };

  const sectorCodes = SECTOR_REPS.flatMap((s) => s.codes);
  const [kosdaq, kospi200, sectorPairs] = await Promise.all([
    idxAxis('KOSDAQ'), idxAxis('KPI200'),
    Promise.all(sectorCodes.map(async (code) => {
      const [bT, bY, pT, pY] = await Promise.all([
        settle(minuteBars('item', code, T, fetchJson, '0900', hhmm), []),
        settle(once(`sY:${code}`, () => minuteBars('item', code, Y, fetchJson), hasRows), []),
        settle(once(`sPT:${code}`, () => prevClose('item', code, T, fetchJson), isNum), null),
        settle(once(`sPY:${code}`, () => prevClose('item', code, Y, fetchJson), isNum), null),
      ]);
      const tb = atOrBefore(completed(bT, hhmm), at), yb = tb ? atOrBefore(bY, tb.t) : null;
      return [code, { t: tb ? pct(tb.v, pT) : null, y: yb ? pct(yb.v, pY) : null }];
    })),
  ]);

  const axes = {
    heat: heatAxis(kT, kY, baseT, baseY, at),
    market: { kosdaq, kospi200 },
    sectors: sectorRows(Object.fromEntries(sectorPairs)),
    flow: flow ? flowAxis(flow.t, flow.y) : null,
  };

  return {
    status: 'ok',
    time: at.slice(0, 2) + ':' + at.slice(2),
    today: { date: dash, label: labelFromYmd(dash) },
    prev: { date: yDash, label: labelFromYmd(yDash), rel },
    verdict: verdict({ yLabel: rel, kospiDiff: kospi.diff, foreignDiff: flow ? flow.foreignDiff : null, kospiT: kospi.t, kospiY: kospi.y }),
    kospi, flow, leaders, avg, issues, axes,
  };
}
