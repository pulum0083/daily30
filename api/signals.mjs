// 종목·ETF 신호 통합 API — polling(가격·등락·거래량) + itemSummary(거래대금) + 일봉 스냅샷 조합 → 코어 가공
import { ALL_ETF_CODES, ETF_NAME } from './_etf-universe.mjs';
import { buildSignals, classifySupply, etfBettingFlow, etfSectorRotation, etfSafeHaven, etfLead, SIGNAL_META } from './_signals-core.mjs';
import { krMarketOpen, kstTodayYmd, labelFromYmd } from './_market-calendar.mjs';

const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };

async function pollOne(code) {
  try {
    const r = await fetch(`https://polling.finance.naver.com/api/realtime/domestic/stock/${code}`, { headers: HDR, signal: AbortSignal.timeout(6000) });
    if (!r.ok) return null;
    const it = (await r.json())?.datas?.[0];
    if (!it) return null;
    return {
      code,
      pct: parseFloat(String(it.fluctuationsRatioRaw || '0').replace(/,/g, '')) || 0,
      vol: parseInt(String(it.accumulatedTradingVolumeRaw || '0').replace(/,/g, ''), 10) || 0,
      price: parseFloat(String(it.closePriceRaw || '0').replace(/,/g, '')) || 0,
    };
  } catch { return null; }
}

async function amountOne(code) {
  try {
    const r = await fetch(`https://api.finance.naver.com/service/itemSummary.naver?itemcode=${code}`, { headers: HDR, signal: AbortSignal.timeout(6000) });
    if (!r.ok) return 0;
    const d = await r.json();
    return Number(d.amount) || 0; // 거래대금(백만)
  } catch { return 0; }
}

async function trendOne(code) {
  try {
    const r = await fetch(`https://m.stock.naver.com/api/stock/${code}/trend`, { headers: { 'User-Agent': 'Mozilla/5.0', Referer: 'https://m.stock.naver.com/' }, signal: AbortSignal.timeout(6000) });
    if (!r.ok) return null;
    const rows = await r.json();
    if (!Array.isArray(rows)) return null;
    const num = (v) => parseInt(String(v || '0').replace(/[,+]/g, ''), 10) || 0;
    return rows.slice(0, 5).map((x) => ({ foreign: num(x.foreignerPureBuyQuant), organ: num(x.organPureBuyQuant) }));
  } catch { return null; }
}

async function loadSnapshot() {
  try {
    const base = process.env.SNAPSHOT_BASE || 'https://doubleshot.space';
    const r = await fetch(`${base}/data/stocks-snapshot.json`, { signal: AbortSignal.timeout(6000) });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

async function kospiPct() {
  try {
    const r = await fetch('https://doubleshot.space/api/kospi-live', { signal: AbortSignal.timeout(6000) });
    const d = r.ok ? await r.json() : null;
    return Number(d?.changePct) || 0;
  } catch { return 0; }
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const snap = await loadSnapshot();
    if (!snap || !snap.stocks) return res.status(502).json({ error: 'snapshot unavailable' });
    const stockCodes = Object.keys(snap.stocks);

    const [stockPolls, stockAmts, etfPolls, etfAmts, kPct] = await Promise.all([
      Promise.all(stockCodes.map(pollOne)),
      Promise.all(stockCodes.map(amountOne)),
      Promise.all(ALL_ETF_CODES.map(pollOne)),
      Promise.all(ALL_ETF_CODES.map(amountOne)),
      kospiPct(),
    ]);

    const stocks = stockCodes.map((code, i) => {
      const p = stockPolls[i]; const s = snap.stocks[code];
      if (!p || !s) return null;
      return { code, name: s.name, sector: s.sector, pct: p.pct, vol: p.vol, price: p.price,
               vol_avg20: s.vol_avg20 || 0, wk52_high: s.wk52_high || 0, amount: stockAmts[i] || 0 };
    }).filter(Boolean);

    const phase = krMarketOpen() ? 'intraday' : 'closed';
    // 데이터 기준일: 장중이면 오늘(라이브), 마감이면 스냅샷 생성일(마지막 거래일)
    const snapDate = String(snap.generated_at || '').slice(0, 10);
    const asOfDate = phase === 'intraday' ? kstTodayYmd() : (snapDate || kstTodayYmd());
    const asOf = { date: asOfDate, label: labelFromYmd(asOfDate), isToday: phase === 'intraday' };
    let enrich;
    if (phase === 'closed') {
      const trends = await Promise.all(stocks.map((s) => trendOne(s.code)));
      const byTrend = {};
      stocks.forEach((s, i) => { if (trends[i]) byTrend[s.code] = trends[i]; });
      enrich = (s) => (byTrend[s.code] ? classifySupply(byTrend[s.code]) : { cats: [], badges: [] });
    }
    const { signals, rank } = buildSignals(stocks, kPct, { enrich });

    const byCode = {};
    ALL_ETF_CODES.forEach((code, i) => {
      const p = etfPolls[i];
      if (p) byCode[code] = { pct: p.pct, vol: p.vol, amount: etfAmts[i] || 0, name: ETF_NAME[code] };
    });
    const betting = etfBettingFlow(byCode);
    const etf = {
      lead: etfLead(betting),
      betting,
      sector: etfSectorRotation(byCode),
      safeHaven: etfSafeHaven(byCode, byCode['069500']?.pct ?? kPct),
    };

    return res.status(200).json({
      phase, asOf,
      signals, rank, etf, meta: SIGNAL_META, updatedAt: new Date().toISOString(),
    });
  } catch (e) {
    return res.status(502).json({ error: String(e) });
  }
}
