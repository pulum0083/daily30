// 종목 실시간 현재가 — 네이버 종목 시세. 라이브 데이터는 git 커밋 안 함.
// 토스 Open API는 IP 화이트리스트라 서버리스 유동 IP에서 막혀(access_denied: IP not allowed),
// IP 제한 없는 네이버로 조회한다. 6자리 한국 코드만 허용.
// 국내: polling.finance.naver.com 사용 (m.stock.naver.com은 Vercel 런타임에서 fetch failed — TLS 연결 실패).
const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };
const HDR_M = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://m.stock.naver.com/' };

function krNowMinutes() {
  const now = new Date();
  return ((now.getUTCHours() * 60 + now.getUTCMinutes()) + 9 * 60) % (24 * 60);
}

function krMarketOpen() {
  const m = krNowMinutes();
  return m >= 9 * 60 && m <= 15 * 60 + 30; // 09:00–15:30 KST
}

async function fetchOne(code) {
  try {
    const r = await fetch(`https://polling.finance.naver.com/api/realtime/domestic/stock/${code}`, {
      headers: HDR,
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return null;
    const d = await r.json();
    const item = d?.datas?.[0];
    if (!item) return null;
    const price = parseFloat(String(item.closePriceRaw || '').replace(/,/g, ''));
    const pct = parseFloat(String(item.fluctuationsRatioRaw || '').replace(/,/g, ''));
    if (!isFinite(price)) return null;
    return { code, price, changePct: isFinite(pct) ? pct : null };
  } catch (e) {
    return null;
  }
}

// 네이버 심볼 → 야후 티커 변환 (NVDA.O → NVDA, DRAM.K → DRAM)
function naverToYahoo(sym) { return sym.replace(/\.[A-Z]$/, ''); }

// 야후 파이낸스 — 프리장·애프터장 실시간 데이터 포함
async function fetchYahoo(sym) {
  const ticker = naverToYahoo(sym);
  try {
    const r = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=1d&interval=1m&includePrePost=true`,
      { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(6000) },
    );
    if (!r.ok) return null;
    const d = await r.json();
    const meta = d?.chart?.result?.[0]?.meta;
    if (!meta) return null;
    const price = meta.regularMarketPrice;
    const prevClose = meta.chartPreviousClose || meta.previousClose;
    let livePrice = price;
    let source = 'regular';
    if (meta.preMarketPrice && meta.preMarketPrice !== price) {
      livePrice = meta.preMarketPrice; source = 'pre';
    } else if (meta.postMarketPrice && meta.postMarketPrice !== price) {
      livePrice = meta.postMarketPrice; source = 'post';
    }
    if (!isFinite(livePrice) || !isFinite(prevClose) || prevClose === 0) return null;
    const pct = ((livePrice - prevClose) / prevClose) * 100;
    return { sym, price: livePrice, changePct: Math.round(pct * 100) / 100, source };
  } catch (e) {
    return null;
  }
}

// 해외 종목 — 네이버 우선, 정규장 외 시간대엔 야후 폴백 (프리장·애프터장 실시간)
async function fetchOverseas(sym) {
  try {
    const r = await fetch(`https://api.stock.naver.com/stock/${encodeURIComponent(sym)}/basic`, {
      headers: HDR_M,
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return fetchYahoo(sym);
    const d = await r.json();
    if (d.marketStatus !== 'OPEN') return (await fetchYahoo(sym)) || naverFallback(sym, d);
    const price = parseFloat(String(d.closePrice).replace(/,/g, ''));
    const pct = parseFloat(String(d.fluctuationsRatio).replace(/,/g, ''));
    if (!isFinite(price)) return null;
    return { sym, price, changePct: isFinite(pct) ? pct : null, source: 'regular' };
  } catch (e) {
    return fetchYahoo(sym);
  }
}

function naverFallback(sym, d) {
  const price = parseFloat(String(d.closePrice).replace(/,/g, ''));
  const pct = parseFloat(String(d.fluctuationsRatio).replace(/,/g, ''));
  if (!isFinite(price)) return null;
  return { sym, price, changePct: isFinite(pct) ? pct : null, source: 'close' };
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const codes = (req.query?.codes || '').toString()
      .split(',').map(s => s.trim()).filter(c => /^\d{6}$/.test(c)).slice(0, 50);
    const usSyms = (req.query?.us || '').toString()
      .split(',').map(s => s.trim()).filter(s => /^[A-Za-z]{1,6}(\.[A-Za-z])?$/.test(s)).slice(0, 20);
    const [prices, us] = await Promise.all([
      Promise.all(codes.map(fetchOne)).then(a => a.filter(Boolean)),
      Promise.all(usSyms.map(fetchOverseas)).then(a => a.filter(Boolean)),
    ]);
    return res.status(200).json({ open: krMarketOpen(), prices, us });
  } catch (e) {
    return res.status(502).json({ error: String(e), prices: [], us: [] });
  }
}
