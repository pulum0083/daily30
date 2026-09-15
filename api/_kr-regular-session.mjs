// 한국 종목 정규장(09:00~15:30) 시·고·저·종·거래량 — 장이 닫힌 뒤 애프터장이 섞이지 않은 값의 단일 소스(§48·§30)
// stocks-live(주도주 타일)·hl-night(야간 추정가 앵커)·signals(장 마감 특이 신호)가 함께 쓴다. '_' 접두라 라우트로 배포되지 않는다.
import { isKospiHoliday, lastTradingDay } from './_market-calendar.mjs';

const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };
const toNum = (v) => { const n = parseFloat(String(v ?? '').replace(/,/g, '')); return isFinite(n) ? n : null; };

// 장이 닫힌 뒤(애프터장 16:00~20:00, 밤·주말)엔 실시간 응답의 closePrice·저가·거래대금에
// 애프터장 체결이 섞인다 — 9/14 17:10 SK하이닉스 closePrice 1,686,000(공식 종가 1,697,000),
// 같은 날 저녁 삼성전자 lowPrice 248,000(정규장 저가 248,500, §48). 그 시간엔 1분봉으로
// 정규장(09:00~15:30) 값을 직접 만든다.
// 1분봉 accumulatedTradingVolume은 이름과 달리 봉 하나의 거래량이라 합이 정규장 거래량이다
// (9/14 SK하이닉스 09:00~15:30 합 3,742,905 + 애프터장 256,370 ≈ 일봉 4,001,549).
// 창에 더 이른 날짜의 15:30 봉이 있으면 그 종가가 전일 공식 종가(prevClose)다.
export function regularSessionFromBars(bars) {
  const rows = (Array.isArray(bars) ? bars : [])
    .filter((b) => b && typeof b.localDateTime === 'string' && b.localDateTime.length >= 12);
  const closeBar = [...rows].reverse().find((b) => b.localDateTime.slice(8, 12) === '1530');
  if (!closeBar) return null;
  const day = closeBar.localDateTime.slice(0, 8);
  const sess = rows.filter((b) => {
    const hm = b.localDateTime.slice(8, 12);
    return b.localDateTime.slice(0, 8) === day && hm >= '0900' && hm <= '1530';
  });
  const highs = sess.map((b) => toNum(b.highPrice)).filter((v) => v != null);
  const lows = sess.map((b) => toNum(b.lowPrice)).filter((v) => v != null);
  const close = toNum(closeBar.currentPrice);
  if (close == null || !highs.length || !lows.length) return null;
  const vols = sess.map((b) => toNum(b.accumulatedTradingVolume)).filter((v) => v != null);
  const prevBar = [...rows].reverse()
    .find((b) => b.localDateTime.slice(8, 12) === '1530' && b.localDateTime.slice(0, 8) < day);
  return {
    date: day, close, open: toNum(sess[0].openPrice), high: Math.max(...highs), low: Math.min(...lows),
    volume: vols.length ? vols.reduce((a, v) => a + v, 0) : null,
    prevClose: prevBar ? toNum(prevBar.currentPrice) : null,
  };
}

const ymd = (d) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' })
  .format(d).replace(/-/g, '');

export async function fetchClosedSession(code, now = new Date()) {
  try {
    const start = ymd(new Date(now.getTime() - 7 * 86400000));   // 주말·연휴를 넘겨 직전 거래일까지
    const r = await fetch(
      `https://api.stock.naver.com/chart/domestic/item/${code}/minute?startDateTime=${start}0900&endDateTime=${ymd(now)}1530`,
      { headers: HDR, signal: AbortSignal.timeout(6000) },
    );
    if (!r.ok) return null;
    const reg = regularSessionFromBars(await r.json());
    if (!reg) return null;
    // 등락은 비운다 — 새벽 넥스트레이드 프리마켓이 열리면 실시간의 '전일 종가'가 다음 날로 넘어가
    // 이 세션의 전일 종가와 어긋날 수 있다. 밤 화면은 등락을 쓰지 않는다.
    return {
      code, price: reg.close, session: 'regular-closed', sessionDate: reg.date,
      changePct: null, changeAbs: null, prevClose: null,
      open: reg.open, high: reg.high, low: reg.low, tradingValue: null,
    };
  } catch (e) {
    return null;
  }
}

const dayBefore = (dash) => {
  const [y, m, d] = dash.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d - 1)).toISOString().slice(0, 10);
};

// 정규장이 끝난 마지막 거래일(session)과 그 전 거래일(prev), 'YYYYMMDD'. 오늘이 거래일이고 15:30이 지났으면
// session은 오늘이다. krMarketOpen()이 15:30까지 장중으로 보므로 15:31부터 오늘로 넘어간다.
export function lastClosedSessions(now = new Date()) {
  const k = new Date(now.getTime() + 9 * 3600000);
  const today = k.toISOString().slice(0, 10);
  const min = k.getUTCHours() * 60 + k.getUTCMinutes();
  const session = !isKospiHoliday(k) && min > 15 * 60 + 30 ? today : lastTradingDay(dayBefore(today));
  const prev = lastTradingDay(dayBefore(session));
  return { session: session.replace(/-/g, ''), prev: prev.replace(/-/g, '') };
}

// 끝난 정규장 값은 바뀌지 않는다 — 세션 날짜가 같으면 인스턴스 메모리에서 다시 쓴다(폴링마다 1분봉 재조회 방지).
let cachedSession = null;
const sessionCache = new Map();

// 마지막으로 끝난 정규장의 종가·거래량·전일 공식 종가·등락률. 그 세션의 15:30 봉이나 전일 15:30 봉이 없으면
// null — 다른 날짜 값이나 애프터장 가격으로 채우지 않는다(운영 규칙 0).
export async function fetchLastRegularSession(code, now = new Date()) {
  const { session, prev } = lastClosedSessions(now);
  if (cachedSession !== session) { sessionCache.clear(); cachedSession = session; }
  if (sessionCache.has(code)) return sessionCache.get(code);
  try {
    const r = await fetch(
      `https://api.stock.naver.com/chart/domestic/item/${code}/minute?startDateTime=${prev}1530&endDateTime=${session}1530`,
      { headers: HDR, signal: AbortSignal.timeout(6000) },
    );
    if (!r.ok) return null;
    const reg = regularSessionFromBars(await r.json());
    if (!reg || reg.date !== session || !(reg.prevClose > 0) || reg.volume == null) return null;
    const out = { ...reg, changePct: Math.round((reg.close / reg.prevClose - 1) * 10000) / 100 };
    sessionCache.set(code, out);
    return out;
  } catch (e) {
    return null;
  }
}
