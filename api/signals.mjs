// 종목 신호 통합 API — polling(가격·등락·거래량) + 일봉 스냅샷 조합 → 코어 가공
import { buildSignals, classifySupply, sectorAverages, SIGNAL_META } from './_signals-core.mjs';
import { krMarketOpen, krSessionProgress, kstTodayYmd, labelFromYmd } from './_market-calendar.mjs';
import { fetchLastRegularSession, lastClosedSessions } from './_kr-regular-session.mjs';

const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };

// 장이 닫힌 뒤 — 실시간 가격·등락률·거래량은 애프터장(16:00~20:00) 체결을 따른다(§48). 2026-09-15 16:04
// SK하이닉스 closePriceRaw 1,688,000·-0.53%·거래량 2,549,066 vs 15:30 종가 1,690,000·정규장 1분봉 합 2,547,696.
// 그래서 마지막 정규장 1분봉으로 만든 값을 쓴다(공용 모듈, §30).
async function closedOne(code) {
  const s = await fetchLastRegularSession(code);
  return s ? { code, pct: s.changePct, vol: s.volume, price: s.close } : null;
}

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
  // 장중 120초 주기 폴링 — 주기의 절반으로 잡아 신선도 여유를 남긴다.
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=120');
  try {
    const snap = await loadSnapshot();
    if (!snap || !snap.stocks) return res.status(502).json({ error: 'snapshot unavailable' });
    const stockCodes = Object.keys(snap.stocks);

    const phase = krMarketOpen() ? 'intraday' : 'closed';
    const [stockPolls, kPct] = await Promise.all([
      Promise.all(stockCodes.map(phase === 'intraday' ? pollOne : closedOne)),
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

    // 데이터 기준일: 장중이면 오늘(라이브), 마감이면 값을 만든 마지막 정규장 날짜(스냅샷 생성일이 아니다 —
    // 15:31~16:35엔 스냅샷이 아직 전날 것이다)
    const closed = lastClosedSessions().session;
    const asOfDate = phase === 'intraday' ? kstTodayYmd() : `${closed.slice(0, 4)}-${closed.slice(4, 6)}-${closed.slice(6)}`;
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

    return res.status(200).json({
      phase, asOf, kospiPct: kPct, sectors: sectorAverages(stocks),
      signals, signalsAll, meta: SIGNAL_META, updatedAt: new Date().toISOString(),
    });
  } catch (e) {
    return res.status(502).json({ error: String(e) });
  }
}
