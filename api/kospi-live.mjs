// 네이버 폴링 API로 코스피 실시간 지수를 브라우저에 CORS 없이 전달하는 프록시
// 장중: polling API (7초 갱신) → 실패 시 basic API
// 장 마감(15:30~): polling API 건너뛰고 basic API 직행 (polling은 장 후 nv=0 반환)
import { parseBasicIndex, signedChange, toNum } from './_naver-quote.mjs';

const POLLING_URL = 'https://polling.finance.naver.com/api/realtime?query=SERVICE_INDEX:KOSPI';
const FALLBACK_URL = 'https://m.stock.naver.com/api/index/KOSPI/basic';

function isAfterMarketKST() {
  const kst  = new Date(Date.now() + 9 * 3600 * 1000);
  const day  = kst.getUTCDay();
  const mins = kst.getUTCHours() * 60 + kst.getUTCMinutes();
  return day !== 0 && day !== 6 && mins >= 930; // 15:30 KST 이후 평일
}

async function fetchBasic() {
  const r = await fetch(FALLBACK_URL, {
    headers: { 'User-Agent': 'Mozilla/5.0' },
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`basic ${r.status}`);
  const d = await r.json();
  return {
    ...parseBasicIndex(d),
    changeAbs: signedChange(d.compareToPreviousClosePrice, d.compareToPreviousPrice?.code, 0),
    marketStatus: d.marketStatus || 'UNKNOWN',
    updatedAt:  new Date().toISOString(),
  };
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 's-maxage=20, stale-while-revalidate=20');   // 60초 폴링 — s-maxage+swr을 주기보다 작게(§68 ④, 2026-11-13)

  // 장 마감 후 → basic API 직행
  if (isAfterMarketKST()) {
    try {
      return res.json(await fetchBasic());
    } catch (e) {
      return res.status(502).json({ error: String(e) });
    }
  }

  // 장중 → polling API 1차, 실패 시 basic API 폴백
  try {
    const r = await fetch(POLLING_URL, {
      headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/' },
      signal: AbortSignal.timeout(5000),
    });
    if (!r.ok) throw new Error(`polling ${r.status}`);
    const d    = await r.json();
    const item = d?.result?.areas?.[0]?.datas?.[0];
    const price = toNum(item?.nv);
    if (price == null || price <= 0) throw new Error('no data');
    const ratio = toNum(item.cr), change = toNum(item.cv);
    if (ratio == null) throw new Error('no changePct');
    return res.json({
      price:        price / 100,
      changePct:    Math.round(ratio * 100) / 100,
      changeAbs:    change == null ? null : Math.round(change / 100),
      marketStatus: item.ms || 'UNKNOWN',
      updatedAt:    new Date().toISOString(),
    });
  } catch (_) {
    try {
      return res.json(await fetchBasic());
    } catch (e2) {
      return res.status(502).json({ error: String(e2) });
    }
  }
}
