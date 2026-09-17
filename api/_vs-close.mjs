// 마감 후 대결판 — 정규장 확정(09:00~15:30) 1분봉과 15:31~15:40 수급 행으로만 만든다.
// 16:00부터 애프터장이 열려 실시간·일봉·토스 종가는 그 값을 따라간다(§48·§51).
import { isKospiHoliday, labelFromYmd } from './_market-calendar.mjs';
import { prevTradingDay, relLabel, atOrBefore, pct, round2, judge, TH, verdict } from './_vs-core.mjs';
import { minuteBars, prevClose, curve } from './_vs-prices.mjs';
import { parseInvestorTimePage } from './_vs-flow.mjs';
import { heatAxis, flowAxis } from './_vs-axes.mjs';
import { SECTOR_REPS, sectorRows } from './_vs-sectors.mjs';

export const CLOSE_AT = '1530';

// 마감 후 응답의 CDN 캐시 — ok는 확정값이라 길게, 그 밖(closed·early·waiting·error)은 곧 바뀔 수 있어 짧게
export function closeCacheControl(status) {
  return status === 'ok'
    ? 's-maxage=1800, stale-while-revalidate=600'
    : 's-maxage=60, stale-while-revalidate=60';
}

// 15:31~15:40 사이 마지막 행. 16:00 이후 행은 애프터장이 섞였다.
export function regularFlowRow(rows) {
  let hit = null;
  for (const r of rows || []) {
    const t = String(r.t).replace(':', '');
    if (t >= '1531' && t <= '1540' && (!hit || t > String(hit.t).replace(':', ''))) hit = r;
  }
  return hit;
}

const FLOW_URL = (ymd, p) =>
  `https://finance.naver.com/sise/investorDealTrendTime.naver?bizdate=${ymd}&sosok=01&page=${p}`;

// 15:31~15:40 행은 최신 시각부터 오는 표의 앞쪽이 아니라 중간에 있다 — 페이지를 끝까지 훑는다.
// 과거 날짜도 같은 방식으로 조회된다(1페이지만 보면 빈손으로 보인다).
async function regularFlowOf(ymd, fetchText) {
  const first = await fetchText(FLOW_URL(ymd, 1));
  const pages = Math.max(...[...String(first).matchAll(/page=(\d+)/g)].map((m) => +m[1]).concat(1));
  let rows = parseInvestorTimePage(first);
  for (let p = 2; p <= pages && !regularFlowRow(rows); p++) {
    rows = rows.concat(parseInvestorTimePage(await fetchText(FLOW_URL(ymd, p))));
  }
  return regularFlowRow(rows);
}

const settle = (pr, fb) => pr.then((v) => v, () => fb);
const isNum = (n) => typeof n === 'number';

export async function buildCloseVs({ now = Date.now(), fetchJson, fetchText }) {
  const k = new Date(now + 9 * 3600 * 1000);
  const dash = k.toISOString().slice(0, 10);
  const hhmm = k.toISOString().slice(11, 16).replace(':', '');
  if (isKospiHoliday(k)) return { status: 'closed' };
  if (hhmm < '1530') return { status: 'closed' };   // 장중은 vs=intraday가 담당
  if (hhmm < '1540') return { status: 'early' };    // 확정 수급 행이 아직 없다

  const yDash = prevTradingDay(dash);
  const T = dash.replace(/-/g, ''), Y = yDash.replace(/-/g, '');
  const at = CLOSE_AT;

  // 한 종목/지수의 오늘·어제 정규장 봉과 기준가. 기준가는 직전 거래일 15:30 1분봉이다(§48).
  const load = async (kind, code) => {
    const [bT, bY, pT, pY] = await Promise.all([
      settle(minuteBars(kind, code, T, fetchJson, '0900', at), []),
      settle(minuteBars(kind, code, Y, fetchJson, '0900', at), []),
      settle(prevClose(kind, code, T, fetchJson), null),
      settle(prevClose(kind, code, Y, fetchJson), null),
    ]);
    return { bT, bY, pT: isNum(pT) ? pT : null, pY: isNum(pY) ? pY : null };
  };
  const rate = (o) => {
    const tb = atOrBefore(o.bT, at), yb = atOrBefore(o.bY, at);
    const t = tb ? pct(tb.v, o.pT) : null, y = yb ? pct(yb.v, o.pY) : null;
    const d = t != null && y != null ? round2(t - y) : null;
    return { t, y, diff: d, judge: d == null ? null : judge(d, TH.pctPoint) };
  };

  const sectorCodes = SECTOR_REPS.flatMap((s) => s.codes);
  const [ks, kq, k2, sectorLoaded, fT] = await Promise.all([
    load('index', 'KOSPI'), load('index', 'KOSDAQ'), load('index', 'KPI200'),
    Promise.all(sectorCodes.map(async (c) => [c, rate(await load('item', c))])),
    settle(regularFlowOf(T, fetchText), null),
  ]);
  if (!ks.bT.length) return { status: 'waiting' };
  const fY = fT ? await settle(regularFlowOf(Y, fetchText), null) : null;

  const kospi = rate(ks);
  kospi.curveT = curve(ks.bT, ks.pT, at);
  kospi.curveY = curve(ks.bY, ks.pY, at);

  const byCode = Object.fromEntries(sectorLoaded.map(([c, r]) => [c, { t: r.t, y: r.y }]));
  const foreignDiff = fT && fY ? fT.외국인 - fY.외국인 : null;

  return {
    status: 'ok',
    time: '15:30',
    today: { date: dash, label: labelFromYmd(dash) },
    prev: { date: yDash, label: labelFromYmd(yDash), rel: relLabel(yDash, dash) },
    verdict: verdict({ yLabel: relLabel(yDash, dash), kospiDiff: kospi.diff, foreignDiff }),
    kospi,
    flow: fT && fY ? { t: fT, y: fY, time: fT.t, foreignDiff, judge: judge(foreignDiff, TH.eok) } : null,
    axes: {
      heat: heatAxis(ks.bT, ks.bY, ks.pT, ks.pY, at),
      market: { kosdaq: rate(kq), kospi200: rate(k2) },
      sectors: sectorRows(byCode),
      flow: flowAxis(fT, fY),
    },
  };
}
