// 코스닥·코스피200·환율 일중 1분봉 데이터 프록시 — 스파크라인 히스토리 초기화용
const HDR = {
  'User-Agent': 'Mozilla/5.0 (compatible)',
  'Referer': 'https://finance.naver.com/',
};

// fchart API: 1분봉 XML → close 가격 배열 (09:00~현재, 5분 간격 샘플링)
async function fetchMinutes(symbol) {
  const url = `https://fchart.stock.naver.com/sise.nhn?symbol=${symbol}&timeframe=minute&count=420&requestType=0`;
  const r = await fetch(url, { headers: HDR, signal: AbortSignal.timeout(10000) });
  if (!r.ok) throw new Error(`${symbol} HTTP ${r.status}`);
  const text = await r.text();

  // data 속성: "YYYYMMDDHHmmSS|open|high|low|close|volume"
  const re = /data="(\d{8})(\d{6})\|[^|]*\|[^|]*\|[^|]*\|([\d.]+)\|/g;
  const points = [];
  let m;
  while ((m = re.exec(text)) !== null) {
    const hhmm = parseInt(m[2].slice(0, 4), 10); // HHMMSS → HHMM
    if (hhmm >= 900 && hhmm <= 1530) {
      points.push({ hhmm, v: parseFloat(m[3]) });
    }
  }
  if (!points.length) return [];

  // 5분 간격 샘플링 (00, 05, 10 ... 분 기준)
  const sampled = points.filter(p => p.hhmm % 5 === 0 || p === points[points.length - 1]);
  return sampled.map(p => p.v);
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=120');
  res.setHeader('Access-Control-Allow-Origin', '*');

  const [kosdaq, kospi200, forex] = await Promise.allSettled([
    fetchMinutes('KOSDAQ'),
    fetchMinutes('KPI200'),
    fetchMinutes('FX_USDKRW'),
  ]);

  res.json({
    kosdaq:   kosdaq.status   === 'fulfilled' ? kosdaq.value   : [],
    kospi200: kospi200.status === 'fulfilled' ? kospi200.value : [],
    forex:    forex.status    === 'fulfilled' ? forex.value    : [],
  });
}
