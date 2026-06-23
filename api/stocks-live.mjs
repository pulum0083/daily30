// 종목 실시간 현재가 — 네이버 종목 시세(m.stock.naver.com). 라이브 데이터는 git 커밋 안 함.
// 토스 Open API는 IP 화이트리스트라 서버리스 유동 IP에서 막혀(access_denied: IP not allowed),
// kospi-live.mjs와 동일하게 IP 제한 없는 네이버로 조회한다. 6자리 한국 코드만 허용.
const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://m.stock.naver.com/' };

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
    const r = await fetch(`https://m.stock.naver.com/api/stock/${code}/basic`, {
      headers: HDR,
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return null;
    const d = await r.json();
    const price = parseFloat(String(d.closePrice).replace(/,/g, ''));
    const pct = parseFloat(String(d.fluctuationsRatio).replace(/,/g, ''));
    if (!isFinite(price)) return null;
    return { code, price, changePct: isFinite(pct) ? pct : null };
  } catch (e) {
    return null;
  }
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const raw = (req.query?.codes || '').toString();
    const codes = raw
      .split(',')
      .map(s => s.trim())
      .filter(c => /^\d{6}$/.test(c))
      .slice(0, 50);
    if (!codes.length) return res.status(200).json({ open: krMarketOpen(), prices: [] });
    const results = await Promise.all(codes.map(fetchOne));
    return res.status(200).json({ open: krMarketOpen(), prices: results.filter(Boolean) });
  } catch (e) {
    return res.status(502).json({ error: String(e), prices: [] });
  }
}
