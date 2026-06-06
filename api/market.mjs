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

async function fetchInvestor() {
  const r = await fetch('https://finance.naver.com/sise/sise_index.naver?code=KOSPI', {
    headers: { ...HDR, 'Accept-Language': 'ko-KR' },
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`investor ${r.status}`);
  const buf  = await r.arrayBuffer();
  const text = new TextDecoder('euc-kr').decode(buf);

  // "개인<br><span class="up">+N,NNN<span>억</span>..."
  const m = text.match(
    /개인<br>.*?([+-][\d,]+)<span>억.*?외국인<br>.*?([+-][\d,]+)<span>억.*?기관<br>.*?([+-][\d,]+)<span>억/s
  );
  if (!m) throw new Error('investor pattern not found');

  const parse = s => parseInt(s.replace(/,/g, '').replace('+', ''), 10);
  return {
    individual: parse(m[1]),
    foreign:    parse(m[2]),
    institution: parse(m[3]),
  };
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 's-maxage=30, stale-while-revalidate=60');
  res.setHeader('Access-Control-Allow-Origin', '*');

  const [kosdaq, kospi200, forex, investor] = await Promise.allSettled([
    fetchIndex('KOSDAQ'),
    fetchIndex('KPI200'),
    fetchForex(),
    fetchInvestor(),
  ]);

  res.json({
    kosdaq:    kosdaq.status    === 'fulfilled' ? kosdaq.value    : null,
    kospi200:  kospi200.status  === 'fulfilled' ? kospi200.value  : null,
    forex:     forex.status     === 'fulfilled' ? forex.value     : null,
    investor:  investor.status  === 'fulfilled' ? investor.value  : null,
    fetchedAt: new Date().toISOString(),
  });
}
