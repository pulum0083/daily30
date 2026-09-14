// 네이버 지수·종목 1분봉과 직전 거래일 종가 — 날짜 고정 조회(설계 §6·§45)
import { pct, prevTradingDay } from './_vs-core.mjs';

const BASE = 'https://api.stock.naver.com/chart/domestic';
const path = (kind, code) => (kind === 'index' ? `index/${code}` : `item/${code}`);

function shiftYmd(ymd, days) {
  const d = new Date(Date.UTC(+ymd.slice(0, 4), +ymd.slice(4, 6) - 1, +ymd.slice(6, 8) + days));
  return d.toISOString().slice(0, 10).replace(/-/g, '');
}

const toDash = (ymd) => `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}`;
const toYmd = (dash) => dash.replace(/-/g, '');

export async function minuteBars(kind, code, ymd, fetchJson, from = '0900', to = '1530') {
  const rows = await fetchJson(`${BASE}/${path(kind, code)}/minute?startDateTime=${ymd}${from}&endDateTime=${ymd}${to}`);
  return (Array.isArray(rows) ? rows : [])
    .filter((r) => String(r.localDateTime).slice(0, 8) === ymd && typeof r.currentPrice === 'number')
    .map((r) => ({ t: String(r.localDateTime).slice(8, 12), v: r.currentPrice }))
    .sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0));
}

// ymd의 직전 거래일(캘린더 기준, 공휴일 포함) 종가만 — 다른 날짜로 폴백하지 않는다(§45·§48·C1).
// 종목은 직전 거래일 15:30 1분봉의 currentPrice(장 마감 뒤엔 일봉이 애프터장 가격일 수 있다, §48).
// 지수는 애프터장이 없어 일봉을 쓰되, 고른 행의 날짜가 정확히 직전 거래일일 때만 인정한다.
export async function prevClose(kind, code, ymd, fetchJson) {
  const target = toYmd(prevTradingDay(toDash(ymd)));
  if (kind === 'item') {
    const rows = await fetchJson(`${BASE}/${path(kind, code)}/minute?startDateTime=${target}1530&endDateTime=${target}1530`);
    const bar = (Array.isArray(rows) ? rows : []).find((r) => typeof r.currentPrice === 'number'
      && String(r.localDateTime).slice(0, 8) === target && String(r.localDateTime).slice(8, 12) === '1530');
    return bar ? bar.currentPrice : null;
  }
  const rows = await fetchJson(`${BASE}/${path(kind, code)}/day?startDateTime=${shiftYmd(ymd, -14)}0000&endDateTime=${ymd}0000`);
  const past = (Array.isArray(rows) ? rows : []).filter((r) => String(r.localDate) < ymd && typeof r.closePrice === 'number');
  if (!past.length) return null;
  const last = past[past.length - 1];
  return String(last.localDate) === target ? last.closePrice : null;
}

const minFrom0900 = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(2)) - 540;

export function curve(bars, base, untilHHMM) {
  const pts = (bars || []).filter((b) => b.t <= untilHHMM);
  return pts
    .filter((b, i) => Number(b.t.slice(2)) % 5 === 0 || i === pts.length - 1)
    .map((b) => [minFrom0900(b.t), pct(b.v, base)])
    .filter((p) => p[1] != null);
}
