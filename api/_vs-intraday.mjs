// '어제랑 비교해서' 장중 대결판 응답 조립 — 코스피·수급·주도주·이슈를 직전 거래일 같은 시각과 맞댄다(설계 §4.2)
import { TH, prevTradingDay, relLabel, atOrBefore, pct, round2, judge, tickOk, verdict } from './_vs-core.mjs';
import { flowAt } from './_vs-flow.mjs';
import { minuteBars, prevClose, curve } from './_vs-prices.mjs';
// _vs-issues.mjs(issuesUntil·keywordDiff)는 지금 쓰지 않는다 — 아래 issues:null 주석 참고(C2). 계산 코드·사전은
// 남겨둔다(설계 남기기 — 불변 장중 기록이 생기면 다시 켠다).
import { isKospiHoliday, labelFromYmd } from './_market-calendar.mjs';

export const LEADERS = [['005930', '삼성전자'], ['000660', 'SK하이닉스'], ['005380', '현대차']];
const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };

export async function getJson(url) {
  const r = await fetch(url, { headers: HDR, signal: AbortSignal.timeout(6000) });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return r.json();
}

export async function getEucKr(url) {
  const r = await fetch(url, { headers: HDR, signal: AbortSignal.timeout(6000) });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return new TextDecoder('euc-kr').decode(await r.arrayBuffer());
}

const settle = (p, fallback) => Promise.resolve().then(() => p).catch(() => fallback);

export async function buildIntradayVs({ now = Date.now(), fetchJson, fetchText }) {
  const k = new Date(now + 9 * 3600 * 1000);
  const dash = k.toISOString().slice(0, 10);
  const hhmm = k.toISOString().slice(11, 16).replace(':', '');
  if (isKospiHoliday(k) || hhmm < '0901' || hhmm > '1530') return { status: 'closed' };

  const yDash = prevTradingDay(dash);
  const T = dash.replace(/-/g, ''), Y = yDash.replace(/-/g, '');
  const rel = relLabel(yDash, dash);

  const [kT, kY, baseT, baseY] = await Promise.all([
    settle(minuteBars('index', 'KOSPI', T, fetchJson, '0900', hhmm), []),
    settle(minuteBars('index', 'KOSPI', Y, fetchJson), []),
    settle(prevClose('index', 'KOSPI', T, fetchJson), null),
    settle(prevClose('index', 'KOSPI', Y, fetchJson), null),
  ]);
  if (!kT.length) return { status: 'waiting' };
  const at = kT[kT.length - 1].t;                       // 비교 시각 = 오늘 마지막 1분봉
  const kyAt = atOrBefore(kY, at);
  const kospi = { t: pct(kT[kT.length - 1].v, baseT), y: kyAt ? pct(kyAt.v, baseY) : null };
  kospi.diff = kospi.t != null && kospi.y != null ? round2(kospi.t - kospi.y) : null;
  kospi.judge = judge(kospi.diff, TH.pctPoint);
  kospi.curveT = curve(kT, baseT, at);
  kospi.curveY = curve(kY, baseY, at);

  // 수급(오늘→어제, I1 때문에 순서 유지)과 주도주 조회를 함께 돌린다(I2) — 서로 다른 데이터라
  // 순서를 맞출 필요가 없다. 수급 내부는 오늘 행을 먼저 찾아야 어제 조회 시각을 알 수 있어 순차다.
  const flowPromise = (async () => {
    const fT = await settle(flowAt(T, at, fetchText), null);
    const fY = fT ? await settle(flowAt(Y, fT.t.replace(':', ''), fetchText), null) : null;
    const f = fT && fY ? { t: fT, y: fY, time: fT.t, foreignDiff: fT.외국인 - fY.외국인 } : null;
    if (f) f.judge = judge(f.foreignDiff, TH.eok);
    return f;
  })();

  const leadersPromise = Promise.all(LEADERS.map(async ([code, name]) => {
    const [bT, bY, pT, pY] = await Promise.all([
      settle(minuteBars('item', code, T, fetchJson, '0900', at), []),
      settle(minuteBars('item', code, Y, fetchJson, '0900', at), []),
      settle(prevClose('item', code, T, fetchJson), null),
      settle(prevClose('item', code, Y, fetchJson), null),
    ]);
    // 오늘 봉을 먼저 고르고, 어제는 그 봉의 시각으로 고른다(I3) — 오늘 봉이 비교 시각(at)보다
    // 이르면(데이터 지연 등) 어제를 at으로 고르면 서로 다른 시각을 맞대게 된다.
    // 오늘 봉이 없으면 어제도 비교하지 않는다 — t·y·diff 모두 null(표에서 행이 빠진다).
    const tb = atOrBefore(bT, at);
    const yb = tb ? atOrBefore(bY, tb.t) : null;
    const t = tb ? pct(tb.v, pT) : null, y = yb ? pct(yb.v, pY) : null;
    return {
      code, name, t, y, diff: t != null && y != null ? round2(t - y) : null,
      pxT: tb && tickOk(tb.v) ? tb.v : null, pxY: yb && tickOk(yb.v) ? yb.v : null,
    };
  }));

  const [flow, leaders] = await Promise.all([flowPromise, leadersPromise]);
  const full = leaders.every((l) => l.t != null && l.y != null);
  const avg = full ? (() => {
    const t = round2(leaders.reduce((s, l) => s + l.t, 0) / leaders.length);
    const y = round2(leaders.reduce((s, l) => s + l.y, 0) / leaders.length);
    return { t, y, diff: round2(t - y), judge: judge(round2(t - y), TH.pctPoint) };
  })() : null;

  // 이슈 비교는 항상 null(C2) — 아카이브가 6개 상한으로 잘리고 최신 항목의 시각이 갱신 때마다
  // 덮어써져 "어제 이 시각까지"를 보장하지 못한다(SERVICE_RULES §49). 아카이브·사전 fetch도 하지 않는다.
  const issues = null;

  return {
    status: 'ok',
    time: at.slice(0, 2) + ':' + at.slice(2),
    today: { date: dash, label: labelFromYmd(dash) },
    prev: { date: yDash, label: labelFromYmd(yDash), rel },
    verdict: verdict({ yLabel: rel, kospiDiff: kospi.diff, foreignDiff: flow ? flow.foreignDiff : null }),
    kospi, flow, leaders, avg, issues,
  };
}
