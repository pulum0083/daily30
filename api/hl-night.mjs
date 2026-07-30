// 하이퍼리퀴드 xyz dex 한국 종목 24h 무기한선물 시세 + USD/KRW 환산 — 장 마감 후 코스피 주도주 참고 시세
// 데이터: api.hyperliquid.xyz/info (인증·IP화이트리스트 없음 → Vercel 서버리스 호환). 실제 KRX 체결가 아님, 참고용.
// SKHX·SMSN 등 일부 종목은 HL 합성가가 실제 종가 대비 상시 큰 폭(5~11%)으로 웃도는 현상이 있어(2026-07-15
// 발견 — 오라클/유동성 특성으로 추정, 저희 환산식 문제 아님), 네이버 실시간가와 비교해 괴리가 크면 보정한다.
import { reconcileWithReal, anchorEstimate, pickAnchorCandle, lastKrxCloseTs } from './_hl-night-core.mjs';

const HL = 'https://api.hyperliquid.xyz/info';
const NAVER_HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };

// HL 심볼 → 6자리 코드 (코스피 주도주 타일과 매칭)
const SYM2CODE = { SKHX: '000660', SMSN: '005930', HYUNDAI: '005380' };
// 코드 없는 지수·ETF (이름만) — 실제가 비교 대상 아님(6자리 코드 없음)
const EXTRA = { KR200: '코스피200', EWY: '한국 ETF(EWY)' };

function krMarketOpen() {
  const now = new Date();
  const m = ((now.getUTCHours() * 60 + now.getUTCMinutes()) + 9 * 60) % (24 * 60);
  return m >= 9 * 60 && m <= 15 * 60 + 30; // 09:00–15:30 KST
}

// stocks-live.mjs와 동일한 네이버 실시간 시세 조회 (6자리 코드 전용)
async function fetchRealKr(code) {
  try {
    const r = await fetch(`https://polling.finance.naver.com/api/realtime/domestic/stock/${code}`, {
      headers: NAVER_HDR,
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return null;
    const d = await r.json();
    const item = d?.datas?.[0];
    if (!item) return null;
    const price = parseFloat(String(item.closePriceRaw || '').replace(/,/g, ''));
    const pct = parseFloat(String(item.fluctuationsRatioRaw || '').replace(/,/g, ''));
    if (!isFinite(price)) return null;
    return { price, changePct: isFinite(pct) ? pct : null };
  } catch (e) {
    return null;
  }
}

// HL 종가시점 가격(앵커)은 하루에 한 번만 바뀌므로 종가 시각을 키로 캐시한다.
// 이 엔드포인트는 방문자마다 10초 간격으로 폴링되므로 매번 캔들을 받아오면 낭비다.
let anchorCache = { key: null, map: null };

async function fetchAnchorUsd(sym, closeTs) {
  try {
    const r = await fetch(HL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 종가 전후 6시간만 받으면 앵커 봉을 고르기에 충분하다.
      body: JSON.stringify({ type: 'candleSnapshot', req: {
        coin: `xyz:${sym}`, interval: '15m', startTime: closeTs - 6 * 3600 * 1000, endTime: closeTs,
      } }),
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return null;
    const c = pickAnchorCandle(await r.json(), closeTs);
    const px = c ? parseFloat(c.c) : NaN;
    return isFinite(px) ? px : null;
  } catch (e) {
    return null;
  }
}

async function getAnchors(syms, closeTs) {
  const key = String(closeTs);
  if (anchorCache.key === key && anchorCache.map) return anchorCache.map;
  const vals = await Promise.all(syms.map(s => fetchAnchorUsd(s, closeTs)));
  const map = {};
  syms.forEach((s, i) => { map[s] = vals[i]; });
  anchorCache = { key, map };
  return map;
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

    // 앵커 환산 — KRX 종가 × (HL 현재가 ÷ HL 종가시점가).
    // 비율만 쓰므로 HL 합성가의 상시 프리미엄은 상쇄되고 진짜 야간 변동만 남는다.
    // changePct의 의미가 'HL 24h 변동'에서 '종가 대비 변동'으로 바뀐다 — 화면이 KRX 종가와
    // 나란히 보여주는 값이므로 이쪽이 사용자가 읽는 기준과 일치한다.
    const closeTs = lastKrxCloseTs();
    const [realPrices, anchors] = await Promise.all([
      Promise.all(items.map(it => fetchRealKr(it.code))),
      closeTs ? getAnchors(items.map(it => it.sym), closeTs) : Promise.resolve({}),
    ]);
    items.forEach((it, i) => {
      const real = realPrices[i];
      const est = anchorEstimate({
        hlNow: it.usd, hlAtClose: anchors[it.sym], krxClose: real?.price,
      });
      if (est) {
        it.krw = est.krw;
        it.changePct = est.changePct;
        it.anchored = true;
        it.adjusted = false; // 종가로 덮어쓴 값이 아니다 — 상세 페이지가 이 플래그로 표시 여부를 정한다
        return;
      }
      // 앵커 근거(종가시점 HL 또는 KRX 종가)를 못 구한 경우에만 레거시 보정으로 폴백
      const merged = reconcileWithReal({ krw: it.krw, changePct: it.changePct }, real);
      it.krw = merged.krw;
      it.changePct = merged.changePct;
      it.adjusted = merged.adjusted;
      it.anchored = false;
    });

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
