// 거래량 톱 실시간 API — 유니버스 41종목 네이버 장중 거래량 병렬 fetch → 상위 5개 반환
const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };

const UNIVERSE = {"005930":{"name":"삼성전자","sector":"반도체"},"000660":{"name":"SK하이닉스","sector":"반도체"},"005380":{"name":"현대차","sector":"자동차"},"042700":{"name":"한미반도체","sector":"반도체"},"058470":{"name":"리노공업","sector":"반도체"},"000990":{"name":"DB하이텍","sector":"반도체"},"039030":{"name":"이오테크닉스","sector":"반도체"},"267260":{"name":"HD현대일렉트릭","sector":"전력기기"},"010120":{"name":"LS일렉트릭","sector":"전력기기"},"298040":{"name":"효성중공업","sector":"전력기기"},"034020":{"name":"두산에너빌리티","sector":"전력기기"},"033100":{"name":"제룡전기","sector":"전력기기"},"012450":{"name":"한화에어로스페이스","sector":"방산"},"079550":{"name":"LIG넥스원","sector":"방산"},"064350":{"name":"현대로템","sector":"방산"},"047810":{"name":"한국항공우주","sector":"방산"},"272210":{"name":"한화시스템","sector":"방산"},"329180":{"name":"HD현대중공업","sector":"조선"},"042660":{"name":"한화오션","sector":"조선"},"010140":{"name":"삼성중공업","sector":"조선"},"009540":{"name":"HD한국조선해양","sector":"조선"},"010620":{"name":"HD현대미포","sector":"조선"},"373220":{"name":"LG에너지솔루션","sector":"2차전지"},"247540":{"name":"에코프로비엠","sector":"2차전지"},"006400":{"name":"삼성SDI","sector":"2차전지"},"003670":{"name":"포스코퓨처엠","sector":"2차전지"},"066970":{"name":"엘앤에프","sector":"2차전지"},"000270":{"name":"기아","sector":"자동차"},"012330":{"name":"현대모비스","sector":"자동차"},"204320":{"name":"HL만도","sector":"자동차"},"011210":{"name":"현대위아","sector":"자동차"},"207940":{"name":"삼성바이오로직스","sector":"바이오"},"068270":{"name":"셀트리온","sector":"바이오"},"000100":{"name":"유한양행","sector":"바이오"},"326030":{"name":"SK바이오팜","sector":"바이오"},"196170":{"name":"알테오젠","sector":"바이오"},"105560":{"name":"KB금융","sector":"금융"},"055550":{"name":"신한지주","sector":"금융"},"138040":{"name":"메리츠금융지주","sector":"금융"},"086790":{"name":"하나금융지주","sector":"금융"},"316140":{"name":"우리금융지주","sector":"금융"}};

function krMarketOpen() {
  const m = ((new Date().getUTCHours() * 60 + new Date().getUTCMinutes()) + 9 * 60) % (24 * 60);
  return m >= 9 * 60 && m <= 15 * 60 + 30;
}

async function fetchVol(code) {
  try {
    const r = await fetch(`https://polling.finance.naver.com/api/realtime/domestic/stock/${code}`, {
      headers: HDR,
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return null;
    const d = await r.json();
    const item = d?.datas?.[0];
    if (!item) return null;
    const vol = parseInt(String(item.accumulatedTradingVolumeRaw || '0'), 10);
    const pct = parseFloat(String(item.fluctuationsRatioRaw || '0'));
    if (!vol) return null;
    const meta = UNIVERSE[code];
    return { code, name: meta.name, sector: meta.sector, vol, changePct: isFinite(pct) ? pct : 0 };
  } catch {
    return null;
  }
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const results = await Promise.all(Object.keys(UNIVERSE).map(fetchVol));
    const items = results.filter(Boolean).sort((a, b) => b.vol - a.vol);
    const top = items.slice(0, 5);
    const maxVol = top[0]?.vol || 1;
    return res.status(200).json({
      open: krMarketOpen(),
      top: top.map(x => ({ ...x, barPct: Math.round(x.vol / maxVol * 100) })),
      all: items, // 41종목 전체 {code,name,sector,vol,changePct} — 상승/하락 정렬용
      updatedAt: new Date().toISOString(),
    });
  } catch (e) {
    return res.status(502).json({ error: String(e), top: [] });
  }
}
