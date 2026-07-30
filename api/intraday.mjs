// 코스닥·코스피200·환율 일중 1분봉 데이터 프록시 — 스파크라인 히스토리 초기화용
import { usSessionState, usBaseClose } from './_us-session.mjs';

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

// 미국 종목 1분봉 (프리·정규·애프터 포함) — 야후 차트 API.
// 세션을 pre/regular/post로 구분하고, 표시 시각은 한국시간(KST)으로 내려준다.
// stocks-live.mjs와 동일한 엔드포인트지만, 여기선 마지막 체결가만이 아니라 시계열 전체를 곡선으로 반환한다.
const ET_TIME = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit' });
const ET_DATE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });
const KST_TIME = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Seoul', hour12: false, hour: '2-digit', minute: '2-digit' });

// ET 분(자정 기준) → 세션 구분. 프리 04:00~09:30 / 정규 09:30~16:00 / 애프터 16:00~20:00
function usSession(etMod) {
  if (etMod >= 240 && etMod < 570) return 'pre';
  if (etMod >= 570 && etMod < 960) return 'regular';
  if (etMod >= 960 && etMod <= 1200) return 'post';
  return 'other';
}

async function fetchUSMinutes(ticker) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=1d&interval=1m&includePrePost=true`;
  const r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, signal: AbortSignal.timeout(10000) });
  if (!r.ok) throw new Error(`${ticker} HTTP ${r.status}`);
  const d = await r.json();
  const result = d?.chart?.result?.[0];
  if (!result) throw new Error(`${ticker} no result`);
  const ts = result.timestamp || [];
  const closes = result.indicators?.quote?.[0]?.close || [];
  const meta = result.meta || {};
  const prevClose = meta.chartPreviousClose ?? meta.previousClose ?? null;
  // 등락률 기준가는 세션에 따라 다르다 — 프리·애프터장엔 prevClose가 한 세션 과거라 쓸 수 없다(§30).
  // stocks-live와 같은 _us-session.mjs로 판정해 홈·상세가 갈리지 않게 한다.
  const session = usSessionState(meta, Date.now() / 1000);
  const baseClose = usBaseClose(meta, session);

  const minutes = [], times = [], sessions = [], stamps = [];
  let lastTs = 0;
  for (let i = 0; i < ts.length; i++) {
    const c = closes[i];
    if (typeof c !== 'number') continue;            // 거래 없는 분은 close=null
    const ep = ET_TIME.format(new Date(ts[i] * 1000)).split(':'); // ET ["HH","MM"]
    const eMod = (parseInt(ep[0], 10) % 24) * 60 + parseInt(ep[1], 10);
    const sess = usSession(eMod);
    if (sess === 'other') continue;                 // 정규 거래시간대(프리~애프터) 밖은 제외
    // 5분 간격 샘플링 + 마지막 포인트는 항상 포함 (SVG 곡선 경량화)
    if (eMod % 5 !== 0 && i !== ts.length - 1) continue;
    minutes.push(Math.round(c * 100) / 100);
    times.push(KST_TIME.format(new Date(ts[i] * 1000)));  // 표시 시각 = 한국시간 "HH:MM"
    sessions.push(sess);
    stamps.push(ts[i]);                             // x축 정렬용 epoch (KST 자정 넘김 방지)
    lastTs = ts[i];
  }
  const refTs = lastTs || ts[ts.length - 1] || Math.floor(Date.now() / 1000);
  return {
    date: ET_DATE.format(new Date(refTs * 1000)).replace(/-/g, ''), // 세션 날짜(ET) YYYYMMDD
    minutes,
    times,       // KST 시각
    sessions,    // 'pre' | 'regular' | 'post'
    ts: stamps,  // epoch(초) — 클라이언트 x 위치 계산
    prevClose,   // 전일 종가 (하위호환 — 정규장·마감 기준가와 동일)
    baseClose,   // 세션별 등락률 기준가 — 클라이언트는 이 값을 우선 사용한다
    session,     // 'pre' | 'open' | 'post' | 'closed'
    // 최신 체결이 12시간 이내면 '실시간/직전 세션'으로 간주 → 헤더 시세 갱신 허용
    fresh: lastTs ? (Date.now() / 1000 - lastTs) < 12 * 3600 : false,
  };
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 's-maxage=30, stale-while-revalidate=60');
  res.setHeader('Access-Control-Allow-Origin', '*');

  // 미국 종목 (티커) — 프리/정규/애프터 1분봉 곡선
  const us = (req.query && req.query.us) ? String(req.query.us).replace(/[^0-9A-Za-z.\-]/g, '') : '';
  if (us) {
    try {
      const out = await fetchUSMinutes(us);
      return res.status(200).json({ ticker: us, ...out });
    } catch (e) {
      return res.status(502).json({ ticker: us, minutes: [], times: [], fresh: false, error: String(e) });
    }
  }

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
  // fetchMinutes는 데이터 없을 때 [] 를 반환하므로 .values 접근 전 항상 배열로 정규화한다.
  const vals = (s) => (s.status === 'fulfilled' && s.value && s.value.values) ? s.value.values : [];
  res.json({
    kosdaq:   vals(kosdaq),
    kospi200: vals(kospi200),
    forex:    vals(forex),
  });
}
