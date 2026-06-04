// 네이버 폴링 API로 코스피 실시간 지수를 브라우저에 CORS 없이 전달하는 프록시
// polling API: 서버 갱신 주기 ~7초, basic API 대비 빠름
const POLLING_URL = 'https://polling.finance.naver.com/api/realtime?query=SERVICE_INDEX:KOSPI';
const FALLBACK_URL = 'https://m.stock.naver.com/api/index/KOSPI/basic';

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 's-maxage=10, stale-while-revalidate=20');

  // 1차: polling API
  try {
    const r = await fetch(POLLING_URL, {
      headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/' },
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) throw new Error(`polling ${r.status}`);
    const d = await r.json();
    const item = d?.result?.areas?.[0]?.datas?.[0];
    if (!item || !item.nv) throw new Error('no data');

    const price     = item.nv / 100;
    const changePct = Math.round(item.cr * 100) / 100;   // 이미 % 단위
    const changeAbs = Math.round(item.cv / 100);
    const ms        = item.ms || 'UNKNOWN';

    return res.json({ price, changePct, changeAbs, marketStatus: ms, updatedAt: new Date().toISOString() });
  } catch (e1) {
    // 2차: basic API 폴백
    try {
      const r2 = await fetch(FALLBACK_URL, {
        headers: { 'User-Agent': 'Mozilla/5.0' },
        signal: AbortSignal.timeout(8000),
      });
      if (!r2.ok) throw new Error(`basic ${r2.status}`);
      const d2 = await r2.json();
      const price   = parseFloat(d2.closePrice.replace(/,/g, ''));
      const absChg  = parseFloat(d2.compareToPreviousClosePrice.replace(/,/g, ''));
      const ratio   = parseFloat(d2.fluctuationsRatio.replace(/,/g, ''));
      const code    = (d2.compareToPreviousPrice || {}).code || '3';
      const sign    = ['1','2'].includes(code) ? 1 : ['4','5'].includes(code) ? -1 : 0;
      return res.json({
        price,
        changePct: Math.round(sign * Math.abs(ratio) * 100) / 100,
        changeAbs: Math.round(sign * Math.abs(absChg)),
        marketStatus: d2.marketStatus || 'UNKNOWN',
        updatedAt: new Date().toISOString(),
      });
    } catch (e2) {
      return res.status(502).json({ error: String(e2) });
    }
  }
}
