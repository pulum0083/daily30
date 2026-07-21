// 종목·ETF 신호 통합 API — polling(가격·등락·거래량) + itemSummary(거래대금) + 일봉 스냅샷 조합 → 코어 가공
import { ALL_ETF_CODES, ETF_NAME } from './_etf-universe.mjs';
import { buildSignals, classifySupply, etfBettingFlow, etfSectorRotation, etfSafeHaven, etfLead, sectorAverages, SIGNAL_META } from './_signals-core.mjs';
import { krMarketOpen, krSessionProgress, kstTodayYmd, labelFromYmd, lastTradingDay } from './_market-calendar.mjs';

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

// ETF 전용 거래대금 조회. ETF는 전 종목 유가증권시장 상장이라 amount 단위가 백만원으로 일관됨(16종목 전수 확인).
// ⚠️ 개별 종목에는 쓰지 말 것 — itemSummary의 amount는 코스닥 종목만 '천원' 단위로 와서 1000배 뻥튀기된다.
//    종목 거래대금은 아래 pollOne의 price*vol로 직접 계산한다(단위 불문 일관).
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
    const base = process.env.SNAPSHOT_BASE || 'https://doubleshot.space';
    const r = await fetch(`${base}/api/kospi-live`, { signal: AbortSignal.timeout(6000) });
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

    const [stockPolls, etfPolls, etfAmts, kPct] = await Promise.all([
      Promise.all(stockCodes.map(pollOne)),
      Promise.all(ALL_ETF_CODES.map(pollOne)),
      Promise.all(ALL_ETF_CODES.map(amountOne)),
      kospiPct(),
    ]);

    const stocks = stockCodes.map((code, i) => {
      const p = stockPolls[i]; const s = snap.stocks[code];
      if (!p || !s) return null;
      // 거래대금은 price*vol로 직접 계산한다(원). itemSummary의 amount는 코스닥만 천원 단위로 와서
      // 정렬 시 1000배 뻥튀기된 코스닥이 '거래대금 상위'를 독식했다(2026-07-21 실사고).
      return { code, name: s.name, sector: s.sector, pct: p.pct, vol: p.vol, price: p.price,
               vol_avg20: s.vol_avg20 || 0, wk52_high: s.wk52_high || 0, amount: p.price * p.vol };
    }).filter(Boolean);

    const phase = krMarketOpen() ? 'intraday' : 'closed';
    // 데이터 기준일: 장중이면 오늘(라이브), 마감이면 스냅샷 생성일을 마지막 거래일로 보정
    // (스냅샷이 주말·공휴일에 생성되면 generated_at이 비거래일이라 라벨이 틀어진다)
    const snapDate = String(snap.generated_at || '').slice(0, 10);
    const asOfDate = phase === 'intraday' ? kstTodayYmd() : lastTradingDay(snapDate || kstTodayYmd());
    const asOf = { date: asOfDate, label: labelFromYmd(asOfDate), isToday: phase === 'intraday' };
    // 수급 신호는 장중에도 켠다. 단 네이버 trend API는 장중에 당일 행을 주지 않아(최신 = 전일)
    // 판정 근거가 전일 확정치다 — '잠정'이 아니라 '전일 기준'으로 사실대로 표기한다.
    const supplySuffix = phase === 'intraday' ? ' (전일 기준)' : '';
    const trends = await Promise.all(stocks.map((s) => trendOne(s.code)));
    const byTrend = {};
    stocks.forEach((s, i) => { if (trends[i]) byTrend[s.code] = trends[i]; });
    const enrich = (s) => (byTrend[s.code] ? classifySupply(byTrend[s.code], { suffix: supplySuffix }) : { cats: [], badges: [] });
    // 장중 누적 거래량을 종일 평균과 비교하면 축이 안 맞아 배수가 과소 계산된다 → 경과 비율로 분모 보정
    const progress = phase === 'intraday' ? krSessionProgress() : 1;
    const { signals, signalsAll } = buildSignals(stocks, kPct, { enrich, progress });

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
      phase, asOf, kospiPct: kPct, sectors: sectorAverages(stocks),
      signals, signalsAll, etf, meta: SIGNAL_META, updatedAt: new Date().toISOString(),
    });
  } catch (e) {
    return res.status(502).json({ error: String(e) });
  }
}
