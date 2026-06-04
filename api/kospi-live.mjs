// 네이버 코스피 실시간 지수를 브라우저에 CORS 없이 전달하는 프록시
const NAVER_URL = 'https://m.stock.naver.com/api/index/KOSPI/basic';

export default async function handler(req, res) {
  try {
    const r = await fetch(NAVER_URL, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) throw new Error(`naver ${r.status}`);
    const d = await r.json();

    const price   = parseFloat(d.closePrice.replace(/,/g, ''));
    const absChg  = parseFloat(d.compareToPreviousClosePrice.replace(/,/g, ''));
    const ratio   = parseFloat(d.fluctuationsRatio.replace(/,/g, ''));
    const code    = (d.compareToPreviousPrice || {}).code || '3';
    const sign    = ['1','2'].includes(code) ? 1 : ['4','5'].includes(code) ? -1 : 0;

    res.setHeader('Cache-Control', 's-maxage=10, stale-while-revalidate=20');
    res.json({
      price,
      changePct:    Math.round(sign * Math.abs(ratio)   * 100) / 100,
      changeAbs:    Math.round(sign * Math.abs(absChg)),
      marketStatus: d.marketStatus || 'UNKNOWN',
      updatedAt:    new Date().toISOString(),
    });
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
}
