// 마감 후 대결판 — 정규장 확정(09:00~15:30) 1분봉과 15:31~15:40 수급 행으로만 만든다.
// 16:00부터 애프터장이 열려 실시간·일봉·토스 종가는 그 값을 따라간다(§48·§51).
import { isKospiHoliday, labelFromYmd } from './_market-calendar.mjs';
import { prevTradingDay, relLabel, atOrBefore, pct, round2, judge, TH, verdict } from './_vs-core.mjs';
import { minuteBars, prevClose, curve } from './_vs-prices.mjs';
import { flowAt } from './_vs-flow.mjs';
import { heatAxis, flowAxis } from './_vs-axes.mjs';
import { SECTOR_REPS, sectorRows } from './_vs-sectors.mjs';

export const CLOSE_AT = '1530';

const isNum = (n) => typeof n === 'number';
const normTime = (t) => String(t).replace(':', '');

// 마감 후 응답의 CDN 캐시 — 필요한 값이 전부 채워진 'ok'만 길게, 그 밖(부분 실패 포함)은 짧게(F1).
// status만 보던 예전 판정은 flow가 null이거나 15:40 미만 행·섹터 결측 등 불완전한 ok까지 길게 캐시했다.
export function closeCacheControl(payload) {
  const p = typeof payload === 'string' ? { status: payload } : (payload || {});
  const sectors = p.axes && p.axes.sectors;
  const complete = p.status === 'ok'
    && p.flow != null && normTime(p.flow.time) === '1540'
    && isNum(p.kospi && p.kospi.t) && isNum(p.kospi && p.kospi.y)
    && isNum(p.axes && p.axes.heat && p.axes.heat.vol && p.axes.heat.vol.t)
    && isNum(p.axes && p.axes.heat && p.axes.heat.amp && p.axes.heat.amp.t)
    && Array.isArray(sectors) && sectors.length === 8 && sectors.every((s) => s && s.n === 3);
  return complete
    ? 's-maxage=1800, stale-while-revalidate=600'
    : 's-maxage=60, stale-while-revalidate=60';
}

// 15:31~15:40 사이 마지막 행. 16:00 이후 행은 애프터장이 섞였다.
export function regularFlowRow(rows) {
  let hit = null;
  for (const r of rows || []) {
    const t = normTime(r.t);
    if (t >= '1531' && t <= '1540' && (!hit || t > normTime(hit.t))) hit = r;
  }
  return hit;
}

// 15:40 이하 가장 최근 행을 이진 탐색으로 찾은 뒤(_vs-flow.flowAt), 그 행이 실제로 15:31~15:40
// 구간 안인지 확인한다. 더 이른 행이 나오면(그날 표가 아직 15:31 전까지만 있으면) 확정 전이라 null.
async function regularFlowOf(ymd, fetchText) {
  const row = await flowAt(ymd, '1540', fetchText);
  if (!row) return null;
  const t = normTime(row.t);
  return t >= '1531' && t <= '1540' ? row : null;
}

const settle = (pr, fb) => pr.then((v) => v, () => fb);

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
