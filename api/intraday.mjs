// 코스닥·코스피200·환율 일중 1분봉 데이터 프록시 — 스파크라인 히스토리 초기화용
const HDR = {
  'User-Agent': 'Mozilla/5.0 (compatible)',
  'Referer': 'https://finance.naver.com/',
};

// fchart API: 1분봉 XML → close 가격 배열 (당일 09:00~15:30, 5분 간격 샘플링)
async function fetchMinutes(symbol) {
  const url = `https://fchart.stock.naver.com/sise.nhn?symbol=${symbol}&timeframe=minute&count=420&requestType=0`;
  const r = await fetch(url, { headers: HDR, signal: AbortSignal.timeout(10000) });
  if (!r.ok) throw new Error(`${symbol} HTTP ${r.status}`);
  const text = await r.text();

  // data 속성: "YYYYMMDDHHmm|open|high|low|close|volume"
  // 종목 분봉은 open/high/low가 "null"이고 close·volume만 유효. volume은 당일 누적값.
  const re = /data="(\d{8})(\d{4})\|[^|]*\|[^|]*\|[^|]*\|([\d.]+)\|([\d.]+)/g;
  const rows = [];
  let m;
  while ((m = re.exec(text)) !== null) {
    rows.push({ date: m[1], hhmm: parseInt(m[2], 10), v: parseFloat(m[3]), vol: parseFloat(m[4]) });
  }
  if (!rows.length) return [];

  // 최신 세션 날짜만 유지 (피드가 ~6일치를 반환하므로)
  const latestDate = rows[rows.length - 1].date;
  const points = rows.filter(r => r.date === latestDate && r.hhmm >= 900 && r.hhmm <= 1530);
  if (!points.length) return [];

  // 5분 간격 샘플링 (00, 05, 10 ... 분 기준) + 마지막 포인트 항상 포함
  const sampled = points.filter((p, i) => p.hhmm % 5 === 0 || i === points.length - 1);
  return {
    date: latestDate, // 세션 날짜 YYYYMMDD — 클라이언트가 '오늘'인지 검증 후 헤더 가격 갱신
    values: sampled.map(p => p.v),
    volumes: sampled.map(p => p.vol), // 누적 거래량 (VWAP 계산용)
    times: sampled.map(p => {
      const h = Math.floor(p.hhmm / 100), m = p.hhmm % 100;
      return `${h < 10 ? '0' : ''}${h}:${m < 10 ? '0' : ''}${m}`;
    }),
  };
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 's-maxage=30, stale-while-revalidate=60');
  res.setHeader('Access-Control-Allow-Origin', '*');

  const code = (req.query && req.query.code) ? String(req.query.code).replace(/[^0-9A-Za-z]/g, '') : '';
  if (code) {
    try {
      const { date, values, volumes, times } = await fetchMinutes(code);
      return res.status(200).json({ code, date, minutes: values, volumes, times });
    } catch (e) {
      return res.status(502).json({ code, minutes: [], volumes: [], times: [], error: String(e) });
    }
  }

  const [kosdaq, kospi200, forex] = await Promise.allSettled([
    fetchMinutes('KOSDAQ'),
    fetchMinutes('KPI200'),
    fetchMinutes('FX_USDKRW'),
  ]);

  // 멀티 심볼 응답은 기존대로 값 배열만 (스파크라인용) — times 불필요
  res.json({
    kosdaq:   kosdaq.status   === 'fulfilled' ? kosdaq.value.values   : [],
    kospi200: kospi200.status === 'fulfilled' ? kospi200.value.values : [],
    forex:    forex.status    === 'fulfilled' ? forex.value.values    : [],
  });
}
