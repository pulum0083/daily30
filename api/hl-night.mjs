// 하이퍼리퀴드 xyz dex 한국 종목 24h 무기한선물 시세 + USD/KRW 환산 — 장 마감 후 코스피 주도주 참고 시세
// 데이터: api.hyperliquid.xyz/info (인증·IP화이트리스트 없음 → Vercel 서버리스 호환). 실제 KRX 체결가 아님, 참고용.
const HL = 'https://api.hyperliquid.xyz/info';

// HL 심볼 → 6자리 코드 (코스피 주도주 타일과 매칭)
const SYM2CODE = { SKHX: '000660', SMSN: '005930', HYUNDAI: '005380' };
// 코드 없는 지수·ETF (이름만)
const EXTRA = { KR200: '코스피200', EWY: '한국 ETF(EWY)' };

function krMarketOpen() {
  const now = new Date();
  const m = ((now.getUTCHours() * 60 + now.getUTCMinutes()) + 9 * 60) % (24 * 60);
  return m >= 9 * 60 && m <= 15 * 60 + 30; // 09:00–15:30 KST
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Access-Control-Allow-Origin', '*');
  try {
    const r = await fetch(HL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'metaAndAssetCtxs', dex: 'xyz' }),
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) return res.status(502).json({ error: `hl ${r.status}`, items: [] });
    const d = await r.json();
    const meta = d?.[0]?.universe, ctxs = d?.[1];
    if (!Array.isArray(meta) || !Array.isArray(ctxs)) {
      return res.status(502).json({ error: 'hl shape', items: [] });
    }
    const idx = {};
    meta.forEach((u, i) => { idx[String(u.name).replace('xyz:', '')] = ctxs[i]; });

    const fxCtx = idx['KRW'];
    const fx = fxCtx ? parseFloat(fxCtx.markPx) : null; // USD/KRW (HL xyz:KRW ≈ spot)

    function build(sym) {
      const c = idx[sym];
      if (!c) return null;
      const usd = parseFloat(c.markPx), prev = parseFloat(c.prevDayPx);
      if (!isFinite(usd)) return null;
      const changePct = isFinite(prev) && prev ? Math.round((usd - prev) / prev * 10000) / 100 : 0;
      const funding = c.funding != null ? Math.round(parseFloat(c.funding) * 1e6) / 1e4 : null; // %/h
      return { sym, usd, krw: fx ? Math.round(usd * fx) : null, changePct, funding };
    }

    const items = [];
    Object.keys(SYM2CODE).forEach(sym => { const b = build(sym); if (b) { b.code = SYM2CODE[sym]; items.push(b); } });
    const extra = [];
    Object.keys(EXTRA).forEach(sym => { const b = build(sym); if (b) { b.name = EXTRA[sym]; extra.push(b); } });

    return res.status(200).json({
      open: krMarketOpen(),
      fx, items, extra,
      source: 'hyperliquid xyz · 24h perp · 참고용',
      updatedAt: new Date().toISOString(),
    });
  } catch (e) {
    return res.status(502).json({ error: String(e), items: [] });
  }
}
