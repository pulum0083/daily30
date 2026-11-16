// 미국 주식 주간거래(오버나이트 세션, 뉴욕 20:00~04:00 = 한국 낮) 판정과 실제 체결가 — stocks-live 전용 공용 모듈
//
// 왜 필요한가 (2026-11-16 사용자 요청)
//   한국 낮 10:00~18:00(서머타임엔 09:00~17:00)에도 미국 주식은 블루오션 등에서 거래된다.
//   야후·네이버·웹불은 이 세션 시세를 주지 않아 '밤사이 미국'이 직전 종가로 멈춰 있었다.
//   로빈후드 공개 시세(bounds=24_5)의 last_non_reg_trade_price가 그 세션 실제 체결가다.
//   공식 공개 API가 아니므로 막히거나 값이 없으면 지금처럼 직전 종가를 그대로 둔다(§0 — 지어내지 않는다).
import { isUsMarketHoliday, nyYmd } from './_us-market-calendar.mjs';

const RH = 'https://api.robinhood.com/marketdata/quotes/';

function nyParts(ms) {
  const p = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', hourCycle: 'h23',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).formatToParts(new Date(ms));
  const g = (t) => Number(p.find((x) => x.type === t)?.value);
  return { y: g('year'), mo: g('month'), d: g('day'), h: g('hour'), mi: g('minute'), s: g('second') };
}

// 뉴욕 현지 날짜(y,mo,d)의 20:00이 몇 ms인지 — 그 시각의 뉴욕 UTC 오프셋으로 환산한다(서머타임 자동).
function ny2000(y, mo, d) {
  const guess = Date.UTC(y, mo - 1, d, 20, 0, 0);
  const p = nyParts(guess);
  const asUtc = Date.UTC(p.y, p.mo - 1, p.d, p.h, p.mi, p.s);
  return guess - (asUtc - guess);
}

// 지금 진행 중인 주간거래 세션의 시작 시각(ms) — 아니면 null.
// 세션은 '다음 정규장 날'에 속한다: 일요일 20:00~월요일 04:00은 월요일 세션이다.
// 그 다음 정규장 날이 휴장(주말·공휴일)이면 세션이 없다.
export function overnightSessionStart(nowMs = Date.now()) {
  const p = nyParts(nowMs);
  if (p.h >= 20) {
    const next = new Date(Date.UTC(p.y, p.mo - 1, p.d + 1, 12));
    if (isUsMarketHoliday(nyYmd(next))) return null;
    return ny2000(p.y, p.mo, p.d);
  }
  if (p.h < 4) {
    if (isUsMarketHoliday(`${p.y}-${String(p.mo).padStart(2, '0')}-${String(p.d).padStart(2, '0')}`)) return null;
    const prev = new Date(Date.UTC(p.y, p.mo - 1, p.d - 1, 12));
    const [py, pm, pd] = nyYmd(prev).split('-').map(Number);
    return ny2000(py, pm, pd);
  }
  return null;
}

// 로빈후드 시세 응답 → { TICKER: { price, at(ms) } } — 이번 세션(startMs 이후) 체결만 남긴다.
export function overnightTrades(json, startMs) {
  const out = {};
  for (const r of json?.results || []) {
    if (!r || !r.symbol) continue;
    const price = parseFloat(r.last_non_reg_trade_price);
    const at = Date.parse(r.venue_last_non_reg_trade_time || '');
    if (!isFinite(price) || price <= 0 || !isFinite(at) || at < startMs) continue;
    out[r.symbol.toUpperCase()] = { price, at };
  }
  return out;
}

export async function fetchOvernightTrades(tickers, startMs, fetchFn = fetch) {
  if (!tickers.length || startMs == null) return {};
  try {
    const r = await fetchFn(`${RH}?symbols=${tickers.map(encodeURIComponent).join(',')}&bounds=24_5`, {
      headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) return {};
    return overnightTrades(await r.json(), startMs);
  } catch (e) {
    return {};
  }
}

// 장 마감(closed) 시세에 주간거래 체결가를 얹는다. 기준가 = 그 시세의 가격(직전 정규장 종가).
// 체결이 없거나 ±25%를 넘게 벌어지면(데이터 문제로 본다, §79) 원래 시세를 그대로 둔다.
export function withOvernight(q, trade) {
  if (!q || q.state !== 'closed' || !trade) return q;
  const base = q.price;
  if (typeof base !== 'number' || !isFinite(base) || base <= 0) return q;
  const pct = ((trade.price - base) / base) * 100;
  if (Math.abs(pct) > 25) return q;
  return {
    sym: q.sym, price: trade.price,
    changePct: Math.round(pct * 100) / 100,
    source: 'robinhood', state: 'overnight',
    tradedAt: new Date(trade.at).toISOString(),
  };
}
