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
// 야후 파이낸스 — 프리장·정규장·애프터장 실시간. 시세는 1분봉 시계열의 마지막 유효 체결가에서 뽑는다.
// (chart meta에는 pre/postMarketPrice 필드가 없어 시계열을 직접 읽어야 한다.)
async function fetchYahoo(sym) {
  const ticker = naverToYahoo(sym);
  try {
    const r = await fetch(
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=1d&interval=1m&includePrePost=true`,
      { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(6000) },
    );
    if (!r.ok) return null;
    const d = await r.json();
    const result = d?.chart?.result?.[0];
    const meta = result?.meta;
    if (!meta) return null;

    const regClose = meta.regularMarketPrice;          // 마지막 정규장 체결가(정규장 중엔 실시간)
    const prevDayClose = meta.chartPreviousClose ?? meta.previousClose; // 직전 거래일 종가

    // 현재 세션 판별 — 야후가 내려주는 거래시간대(currentTradingPeriod)와 현재 시각 비교
    const tp = meta.currentTradingPeriod || {};
    const now = Math.floor(Date.now() / 1000);
    let state = 'closed';
    if (tp.regular && now >= tp.regular.start && now < tp.regular.end) state = 'open';
    else if (tp.pre && now >= tp.pre.start && now < tp.pre.end) state = 'pre';
    else if (tp.post && now >= tp.post.start && now < tp.post.end) state = 'post';

    // 시계열 마지막 유효 종가 = 프리·애프터 실시간 체결가
    let lastPx = null, lastTs = meta.regularMarketTime || null;
    const ts = result.timestamp || [];
    const closes = result.indicators?.quote?.[0]?.close || [];
    for (let i = ts.length - 1; i >= 0; i--) {
      if (typeof closes[i] === 'number') { lastPx = closes[i]; lastTs = ts[i]; break; }
    }

    // 세션별 표시가·등락 기준가
    let price, base;
    if (state === 'pre' || state === 'post') {
      price = (lastPx != null) ? lastPx : regClose;    // 프리·애프터 실시간가
      base = regClose;                                  // 직전 정규장 종가 대비
    } else if (state === 'open') {
      price = (typeof regClose === 'number') ? regClose : lastPx;
      base = prevDayClose;
    } else {                                            // closed — 마지막 정규장 종가
      price = (typeof regClose === 'number') ? regClose : lastPx;
      base = prevDayClose;
    }
    if (!isFinite(price) || !isFinite(base) || base === 0) return null;
    const pct = ((price - base) / base) * 100;
    return {
      sym, price,
      changePct: Math.round(pct * 100) / 100,
      source: 'yahoo', state,
      tradedAt: lastTs ? new Date(lastTs * 1000).toISOString() : null,
    };
  } catch (e) {
    return null;
  }
}

// 해외 종목 — 야후 우선(프리·정규·애프터 실시간), 실패 시 네이버 폴백
async function fetchOverseas(sym) {
  const y = await fetchYahoo(sym);
  if (y) return y;
  try {
    const r = await fetch(`https://api.stock.naver.com/stock/${encodeURIComponent(sym)}/basic`, {
      headers: HDR_M,
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return null;
    const d = await r.json();
    const open = d.marketStatus === 'OPEN';
    const price = parseFloat(String(d.closePrice).replace(/,/g, ''));
    const pct = parseFloat(String(d.fluctuationsRatio).replace(/,/g, ''));
    if (!isFinite(price)) return null;
    return {
      sym, price,
      changePct: isFinite(pct) ? pct : null,
      source: 'naver', state: open ? 'open' : 'closed',
      tradedAt: d.localTradedAt || null,
    };
  } catch (e) {
    return null;
  }
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
