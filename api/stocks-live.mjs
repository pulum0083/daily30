// 종목 실시간 현재가 — 네이버 종목 시세. 라이브 데이터는 git 커밋 안 함.
// 토스 Open API는 IP 화이트리스트라 서버리스 유동 IP에서 막혀(access_denied: IP not allowed),
// IP 제한 없는 네이버로 조회한다. 6자리 한국 코드만 허용.
// 국내: polling.finance.naver.com 사용 (m.stock.naver.com은 Vercel 런타임에서 fetch failed — TLS 연결 실패).
// 세션 판정·기준가 선택은 intraday와 공유하는 _us-session.mjs가 정본(§30 — 이중 구현 금지).
import { usSessionState, usBaseClose } from './_us-session.mjs';
// 개장 판정은 주말·공휴일까지 아는 공용 캘린더를 쓴다(로컬 시간 전용 판정은 평일 공휴일에 장중으로 오판).
import { krMarketOpen, isKospiHoliday } from './_market-calendar.mjs';
// 장이 닫힌 뒤 정규장 값은 공용 모듈이 만든다 — 실시간 closePrice·저가는 애프터장이 섞인다(§48).
import { fetchClosedSession } from './_kr-regular-session.mjs';
const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };
const HDR_M = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://m.stock.naver.com/' };

const toNum = (v) => { const n = parseFloat(String(v ?? '').replace(/,/g, '')); return isFinite(n) ? n : null; };

// 테스트가 네트워크 없이 필드 추출을 검증할 수 있게 export한다(기본 export인 handler는 그대로).
export async function fetchOne(code) {
  try {
    const r = await fetch(`https://polling.finance.naver.com/api/realtime/domestic/stock/${code}`, {
      headers: HDR,
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return null;
    const d = await r.json();
    const item = d?.datas?.[0];
    if (!item) return null;
    const price = toNum(item.closePriceRaw);
    if (price == null) return null;
    // 원화 등락은 원천의 실제 값을 그대로 넘긴다(2026-09-11). 그 전엔 price·changePct만 넘겨
    // 클라이언트가 반올림된 %에서 전일 종가를 역산했고, 호가 단위에 없는 값이 나갔다
    // (삼성전자 실제 −9,250 → 화면 −9,254). 전일 종가도 이 값에서 계산한다 — 역산하지 않는다.
    const changeAbs = toNum(item.compareToPreviousClosePriceRaw);
    return {
      code, price,
      changePct: toNum(item.fluctuationsRatioRaw),
      changeAbs,
      prevClose: changeAbs != null ? price - changeAbs : null,
      open: toNum(item.openPriceRaw),
      high: toNum(item.highPriceRaw),
      low: toNum(item.lowPriceRaw),
      tradingValue: toNum(item.accumulatedTradingValueRaw),   // 원 단위(누적 거래대금)
    };
  } catch (e) {
    return null;
  }
}

// KRX 애프터마켓이 열려 있는 구간(거래일 16:00 ~ 20:00 미만, §48). 이 동안 주도주 목록은
// 실시간 체결가를 '지금 가격'으로 보인다(§79). 20:00 뒤엔 하이퍼리퀴드 추정가(/api/hl-night)가 맡는다.
// 15:31~15:59는 KRX 시간외 종가 매매라 체결가가 늘 종가와 같다(2026-11-04 실측) — after를 붙이지 않는다.
// closePriceRaw는 KRX 가격이다. 같은 응답의 overMarketPriceInfo는 넥스트레이드라 섞지 않는다
// (11/4 17:12:04 삼성전자 KRX 219,000 vs 넥스트레이드 218,500 — 같은 시각에 갈린다).
export function afterHoursOpen(now = new Date()) {
  const k = new Date(now.getTime() + 9 * 3600000);
  if (isKospiHoliday(k)) return false;
  const m = k.getUTCHours() * 60 + k.getUTCMinutes();
  return m >= 16 * 60 && m < 20 * 60;
}

// 장이 닫힌 뒤 응답 — 정규장 값(1분봉)에, 애프터장 시간이면 실시간 체결가를 after로 붙인다.
// after는 그 세션이 오늘일 때만 붙인다(실시간 응답의 가격이 어느 세션 것인지 그때만 확실하다).
export async function closedWithAfter(code, now = new Date()) {
  const reg = await fetchClosedSession(code, now);
  if (!reg || !afterHoursOpen(now)) return reg;
  const today = new Date(now.getTime() + 9 * 3600000).toISOString().slice(0, 10).replace(/-/g, '');
  if (reg.sessionDate !== today) return reg;
  const rt = await fetchOne(code);
  if (rt && typeof rt.price === 'number') reg.after = { price: rt.price };
  return reg;
}

// 네이버 심볼 → 야후 티커 변환 (NVDA.O → NVDA, DRAM.K → DRAM)
function naverToYahoo(sym) { return sym.replace(/\.[A-Z]$/, ''); }

// 야후 파이낸스 — 프리장·애프터장 실시간 데이터 포함
// 야후 파이낸스 — 프리장·정규장·애프터장 실시간. 시세는 1분봉 시계열의 마지막 유효 체결가에서 뽑는다.
// (chart meta에는 pre/postMarketPrice 필드가 없어 시계열을 직접 읽어야 한다.)
// 프리·애프터 값이 기준가에서 이만큼 벌어지면 시세가 아니라 데이터 문제로 본다 — 2026-11-05 SOXX가 프리마켓 144달러,
// 종가 450달러로 와 −67.97%가 나갔다(액면분할로 보이는데 기준가는 분할 전 값이었다).
export function implausibleExtended(state, pct) {
  return (state === 'pre' || state === 'post') && Math.abs(pct) > 25;
}

async function fetchYahoo(sym) {
  const ticker = naverToYahoo(sym);
  try {
    const r = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=1d&interval=1m&includePrePost=true`,
      { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(6000) },
    );
    if (!r.ok) return null;
    const d = await r.json();
    const result = d?.chart?.result?.[0];
    const meta = result?.meta;
    if (!meta) return null;

    const regClose = meta.regularMarketPrice;          // 마지막 정규장 체결가(정규장 중엔 실시간)

    // 현재 세션 판별 + 세션별 기준가 — intraday와 공유하는 _us-session.mjs가 정본(§30).
    const state = usSessionState(meta, Date.now() / 1000);
    const base = usBaseClose(meta, state);

    // 시계열 마지막 유효 종가 = 프리·애프터 실시간 체결가
    let lastPx = null, lastTs = meta.regularMarketTime || null;
    const ts = result.timestamp || [];
    const closes = result.indicators?.quote?.[0]?.close || [];
    for (let i = ts.length - 1; i >= 0; i--) {
      if (typeof closes[i] === 'number') { lastPx = closes[i]; lastTs = ts[i]; break; }
    }

    // 세션별 표시가 — 기준가(base)는 위 usBaseClose가 이미 정했다.
    let price;
    if (state === 'pre' || state === 'post') {
      // 실시간 체결(lastPx)이 없으면 regClose를 price·base 양쪽에 그대로 써서
      // 항상 등락률이 정확히 0.00%로 계산되는 가짜 "플랫" 데이터가 만들어진다(SK하이닉스 ADR처럼
      // 사실상 미거래인 심볼에서 확인됨 — 최근 1개월 일봉 0개, 마지막 체결 6일 전).
      // 진짜 프리·애프터 체결이 없으면 수집 실패로 보고 표시하지 않는다(운영규칙 0).
      // 야후가 오늘 프리·애프터 봉을 비워 주는 날이 있다(2026-11-11 나스닥 상장 종목 전부 — 0봉).
      // 그때 null을 돌려주면 네이버 '어제 종가 등락'으로 넘어가 엔비디아가 프리마켓 +4.36%인데 −5.47%로 보였다.
      // 연장시간대라는 사실을 넘겨 네이버 프리·애프터 체결가로만 대신하게 한다(fetchOverseas).
      if (lastPx == null) return { needExtended: true, state };
      price = lastPx;
    } else {                                            // open·closed — 정규장 체결가/마지막 종가
      price = (typeof regClose === 'number') ? regClose : lastPx;
    }
    // price가 null이면 isFinite(null)===true라 통과해 -100%가 만들어진다 — 타입까지 확인한다.
    if (base == null || typeof price !== 'number' || !isFinite(price)) return null;
    const pct = ((price - base) / base) * 100;
    if (implausibleExtended(state, pct)) return null;     // 틀린 등락을 보이느니 네이버 종가로 넘긴다
    return {
      sym, price,
      changePct: Math.round(pct * 100) / 100,
      source: 'yahoo', state,
      tradedAt: lastTs ? new Date(lastTs * 1000).toISOString() : null,
    };
  } catch (e) {
    return null;
  }
}

// 네이버 해외 시세의 프리·애프터장 체결가(overMarketPriceInfo) — 열려 있고 3시간 안에 체결된 값만.
// 기준가는 closePrice다: 프리장엔 직전 정규장 종가, 애프터장엔 그날 정규장 종가(§30 세션별 기준가와 같다).
// 열린 연장시간대인데 값이 없으면 { missing: true } — 어제 종가 등락으로 대신하지 않는다(§0).
export function naverExtendedQuote(sym, d, nowMs = Date.now()) {
  const o = d?.overMarketPriceInfo;
  const type = o?.tradingSessionType;
  if (!o || (type !== 'PRE_MARKET' && type !== 'AFTER_MARKET') || o.overMarketStatus !== 'OPEN') return null;
  const price = toNum(o.overPrice), base = toNum(d.closePrice);
  const at = Date.parse(o.localTradedAt || '');
  if (price == null || base == null || base <= 0 || !isFinite(at) || nowMs - at > 3 * 3600000) return { missing: true };
  const state = type === 'PRE_MARKET' ? 'pre' : 'post';
  const pct = ((price - base) / base) * 100;
  if (implausibleExtended(state, pct)) return { missing: true };
  return { sym, price, changePct: Math.round(pct * 100) / 100, source: 'naver', state, tradedAt: o.localTradedAt };
}

// 해외 종목 — 야후 우선(프리·정규·애프터 실시간), 실패 시 네이버 폴백
export async function fetchOverseas(sym) {
  const y = await fetchYahoo(sym);
  if (y && !y.needExtended) return y;
  try {
    const r = await fetch(`https://api.stock.naver.com/stock/${encodeURIComponent(sym)}/basic`, {
      headers: HDR_M,
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return null;
    const d = await r.json();
    const ext = naverExtendedQuote(sym, d);
    if (ext) return ext.missing ? null : ext;
    // 야후가 연장시간대라고 했는데 네이버에도 그 체결이 없으면 빼둔다 — 어제 종가 등락을 '지금'으로 보이지 않는다.
    if (y && y.needExtended) return null;
    const open = d.marketStatus === 'OPEN';
    const price = parseFloat(String(d.closePrice).replace(/,/g, ''));
    const pct = parseFloat(String(d.fluctuationsRatio).replace(/,/g, ''));
    if (!isFinite(price)) return null;
    return {
      sym, price,
      changePct: isFinite(pct) ? pct : null,
      source: 'naver', state: open ? 'open' : 'closed',
      tradedAt: d.localTradedAt || null,
    };
  } catch (e) {
    return null;
  }
}

export default async function handler(req, res) {
  // 최단 소비자는 홈 라이브 타일(30초). s-maxage를 그 주기와 맞춘다 — 더 길게 잡으면
  // 화면이 약속한 신선도보다 낡은 값이 나가 표기가 거짓이 된다(운영 규칙 0·§10).
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=120');
  try {
    const codes = (req.query?.codes || '').toString()
      .split(',').map(s => s.trim()).filter(c => /^\d{6}$/.test(c)).slice(0, 50);
    const usSyms = (req.query?.us || '').toString()
      .split(',').map(s => s.trim()).filter(s => /^[A-Za-z]{1,6}(\.[A-Za-z])?$/.test(s)).slice(0, 20);
    const open = krMarketOpen();
    const [prices, us] = await Promise.all([
      Promise.all(codes.map(open ? fetchOne : (c) => closedWithAfter(c))).then(a => a.filter(Boolean)),
      Promise.all(usSyms.map(fetchOverseas)).then(a => a.filter(Boolean)),
    ]);
    return res.status(200).json({ open, prices, us });
  } catch (e) {
    return res.status(502).json({ error: String(e), prices: [], us: [] });
  }
}
