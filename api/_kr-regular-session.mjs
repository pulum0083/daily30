// 한국 종목 정규장(09:00~15:30) 시·고·저·종 — 장이 닫힌 뒤 애프터장이 섞이지 않은 값의 단일 소스(§48·§30)
// stocks-live(주도주 타일)와 hl-night(야간 추정가 앵커)가 함께 쓴다. '_' 접두라 라우트로 배포되지 않는다.
const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };
const toNum = (v) => { const n = parseFloat(String(v ?? '').replace(/,/g, '')); return isFinite(n) ? n : null; };

// 장이 닫힌 뒤(애프터장 16:00~20:00, 밤·주말)엔 실시간 응답의 closePrice·저가·거래대금에
// 애프터장 체결이 섞인다 — 9/14 17:10 SK하이닉스 closePrice 1,686,000(공식 종가 1,697,000),
// 같은 날 저녁 삼성전자 lowPrice 248,000(정규장 저가 248,500, §48). 그 시간엔 1분봉으로
// 정규장(09:00~15:30) 값을 직접 만든다.
// 정규장만의 거래대금은 원천에 없어 비운다(운영 규칙 0).
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
  return { date: day, close, open: toNum(sess[0].openPrice), high: Math.max(...highs), low: Math.min(...lows) };
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

