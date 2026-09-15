// 코스닥·코스피200·원달러·KOSPI 수급 실시간 지표 프록시 — 장 중 사이드바용
const HDR = { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/' };

// Toss Open API 토큰 캐시 (서버리스 인스턴스 내 재사용)
let _tossToken = null;
let _tossExpires = 0;

async function _getTossToken() {
  if (_tossToken && Date.now() < _tossExpires - 60000) return _tossToken;
  const clientId = process.env.TOSS_CLIENT_ID;
  const clientSecret = process.env.TOSS_CLIENT_SECRET;
  if (!clientId || !clientSecret) throw new Error('Toss credentials not set');
  const r = await fetch('https://openapi.tossinvest.com/oauth2/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'client_credentials', client_id: clientId, client_secret: clientSecret }),
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`Toss token ${r.status}`);
  const d = await r.json();
  _tossToken = d.access_token;
  _tossExpires = Date.now() + (d.expires_in || 86400) * 1000;
  return _tossToken;
}

async function _fetchForexToss() {
  const token = await _getTossToken();
  const r = await fetch('https://openapi.tossinvest.com/api/v1/exchange-rate?baseCurrency=USD&quoteCurrency=KRW', {
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(6000),
  });
  if (!r.ok) throw new Error(`Toss forex ${r.status}`);
  const d = await r.json();
  const body = d.result || d;
  const price = parseFloat(body.midRate);
  if (!price) throw new Error('Toss forex: no midRate');
  return { price: Math.round(price * 100) / 100, changePct: 0 };
}

async function fetchIndex(code) {
  const r = await fetch(`https://m.stock.naver.com/api/index/${code}/basic`, {
    headers: HDR, signal: AbortSignal.timeout(6000),
  });
  if (!r.ok) throw new Error(`index/${code} ${r.status}`);
  const d = await r.json();
  const sign = ['1','2'].includes((d.compareToPreviousPrice||{}).code) ? 1
              : ['4','5'].includes((d.compareToPreviousPrice||{}).code) ? -1 : 0;
  return {
    price:     parseFloat(d.closePrice.replace(/,/g, '')),
    changePct: Math.round(sign * Math.abs(parseFloat(d.fluctuationsRatio.replace(/,/g,''))) * 100) / 100,
  };
}

// VIX 변동성 지수 (CBOE) — 네이버 해외지수. 미국 장 기준 15분 지연.
async function fetchVix() {
  const r = await fetch('https://api.stock.naver.com/index/.VIX/basic', {
    headers: { ...HDR, Referer: 'https://m.stock.naver.com/' },
    signal: AbortSignal.timeout(6000),
  });
  if (!r.ok) throw new Error(`vix ${r.status}`);
  const d = await r.json();
  const sign = ['1', '2'].includes((d.compareToPreviousPrice || {}).code) ? 1
              : ['4', '5'].includes((d.compareToPreviousPrice || {}).code) ? -1 : 0;
  return {
    price:     parseFloat(String(d.closePrice).replace(/,/g, '')),
    changePct: Math.round(sign * Math.abs(parseFloat(String(d.fluctuationsRatio).replace(/,/g, ''))) * 100) / 100,
  };
}

async function fetchForex() {
  // 1순위: Toss Open API (공식)
  try { return await _fetchForexToss(); } catch (e) {
    console.error('[market] Toss forex failed:', e.message);
  }
  // 2순위: 네이버 폴백
  const r = await fetch(
    'https://m.stock.naver.com/front-api/marketIndex/prices?reutersCode=FX_USDKRW&category=exchange&pageSize=10&page=1',
    { headers: HDR, signal: AbortSignal.timeout(6000) },
  );
  if (!r.ok) throw new Error(`forex naver ${r.status}`);
  const d  = await r.json();
  const rows = d.result || [];
  if (rows.length < 2) throw new Error('forex rows < 2');
  const price = parseFloat(rows[0].closePrice.replace(/,/g, ''));
  const prev  = parseFloat(rows[1].closePrice.replace(/,/g, ''));
  return {
    price,
    changePct: prev ? Math.round((price - prev) / prev * 10000) / 100 : 0,
  };
}

async function fetchKospiHistory() {
  const end = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10).replace(/-/g, '') + '2359';
  const start = new Date(Date.now() + 9 * 3600 * 1000 - 20 * 86400 * 1000).toISOString().slice(0, 10).replace(/-/g, '') + '0000';
  const r = await fetch(
    `https://api.stock.naver.com/chart/domestic/index/KOSPI/day?startDateTime=${start}&endDateTime=${end}`,
    { headers: { ...HDR, Referer: 'https://m.stock.naver.com/' }, signal: AbortSignal.timeout(6000) },
  );
  if (!r.ok) throw new Error(`kospi history ${r.status}`);
  const d = await r.json();
  const rows = (Array.isArray(d) ? d : [])
    .map(row => ({ d: row.localDate, c: parseFloat(row.closePrice) }))
    .filter(x => x.d && Number.isFinite(x.c));
  if (rows.length < 2) throw new Error('kospi history: too few closes');
  return rows.slice(-8); // 최근 8영업일 {날짜, 종가}
}

// 2026-09-15 네이버가 sise_index.naver를 stock.naver.com으로 옮겨(302) 옛 HTML 정규식이 매번 실패했다
// (SERVICE_RULES §51). 새 페이지의 JSON을 쓴다. 억원 단위의 장중 누적값이고, 16:00 이후엔 애프터장
// 체결이 섞인다 — 장중 사이드바용이다. 마감 브리핑의 정규장 수급은 fetch_data.py가 따로 만든다.
const INVESTOR_TREND_URL = 'https://m.stock.naver.com/api/index/KOSPI/trend';

export function parseInvestorTrend(d) {
  const raw = [d?.personalValue, d?.foreignValue, d?.institutionalValue];
  const [individual, foreign, institution] = raw.map((s) => (s == null || String(s).trim() === ''
    ? NaN : Number(String(s).replace(/[,+]/g, ''))));
  if (![individual, foreign, institution].every(Number.isFinite)) throw new Error('investor trend: empty');
  return { individual, foreign, institution };
}

async function fetchInvestor() {
  const r = await fetch(INVESTOR_TREND_URL, {
    headers: { ...HDR, Referer: 'https://m.stock.naver.com/' },
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`investor ${r.status}`);
  return parseInvestorTrend(await r.json());
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=120');
  res.setHeader('Access-Control-Allow-Origin', '*');

  const [kosdaq, kospi200, forex, investor, kospiSpark, vix] = await Promise.allSettled([
    fetchIndex('KOSDAQ'),
    fetchIndex('KPI200'),
    fetchForex(),
    fetchInvestor(),
    fetchKospiHistory(),
    fetchVix(),
  ]);

  res.json({
    kosdaq:     kosdaq.status     === 'fulfilled' ? kosdaq.value     : null,
    kospi200:   kospi200.status   === 'fulfilled' ? kospi200.value   : null,
    forex:      forex.status      === 'fulfilled' ? forex.value      : null,
    investor:   investor.status   === 'fulfilled' ? investor.value   : null,
    kospiSpark: kospiSpark.status === 'fulfilled' ? kospiSpark.value : null,
    vix:        vix.status        === 'fulfilled' ? vix.value        : null,
    fetchedAt:  new Date().toISOString(),
  });
}
