// 네이버 지수·종목 1분봉과 직전 거래일 종가 — 날짜 고정 조회(설계 §6·§45)
import { pct } from './_vs-core.mjs';

const BASE = 'https://api.stock.naver.com/chart/domestic';
const path = (kind, code) => (kind === 'index' ? `index/${code}` : `item/${code}`);

function shiftYmd(ymd, days) {
  const d = new Date(Date.UTC(+ymd.slice(0, 4), +ymd.slice(4, 6) - 1, +ymd.slice(6, 8) + days));
  return d.toISOString().slice(0, 10).replace(/-/g, '');
}

export async function minuteBars(kind, code, ymd, fetchJson, from = '0900', to = '1530') {
  const rows = await fetchJson(`${BASE}/${path(kind, code)}/minute?startDateTime=${ymd}${from}&endDateTime=${ymd}${to}`);
  return (Array.isArray(rows) ? rows : [])
    .filter((r) => String(r.localDateTime).slice(0, 8) === ymd && typeof r.currentPrice === 'number')
    .map((r) => ({ t: String(r.localDateTime).slice(8, 12), v: r.currentPrice }))
    .sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0));
}

// ymd보다 앞선 마지막 일봉 종가. 과거 봉은 공식 종가와 일치한다(§48)
export async function prevClose(kind, code, ymd, fetchJson) {
  const rows = await fetchJson(`${BASE}/${path(kind, code)}/day?startDateTime=${shiftYmd(ymd, -14)}0000&endDateTime=${ymd}0000`);
  const past = (Array.isArray(rows) ? rows : []).filter((r) => String(r.localDate) < ymd && typeof r.closePrice === 'number');
  return past.length ? past[past.length - 1].closePrice : null;
}

const minFrom0900 = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(2)) - 540;

export function curve(bars, base, untilHHMM) {
  const pts = (bars || []).filter((b) => b.t <= untilHHMM);
  return pts
    .filter((b, i) => Number(b.t.slice(2)) % 5 === 0 || i === pts.length - 1)
    .map((b) => [minFrom0900(b.t), pct(b.v, base)])
    .filter((p) => p[1] != null);
}
