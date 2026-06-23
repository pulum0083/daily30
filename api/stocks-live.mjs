// 종목 유니버스 실시간 현재가 — KST 시간대 분기 (KR 장중 / 마감 후 US 벨웨더)
import { readFileSync } from 'node:fs';

const universe = JSON.parse(
  readFileSync(new URL('../scripts/config/stock_universe.json', import.meta.url), 'utf-8')
);

let _tossToken = null;
let _tossExpires = 0;

async function getTossToken() {
  const clientId = process.env.TOSS_CLIENT_ID;
  const clientSecret = process.env.TOSS_CLIENT_SECRET;
  if (!clientId || !clientSecret) throw new Error('Toss credentials not set');
  if (_tossToken && Date.now() < _tossExpires - 60000) return _tossToken;
  const r = await fetch('https://openapi.tossinvest.com/oauth2/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: clientId,
      client_secret: clientSecret,
    }),
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) throw new Error(`Toss token ${r.status}`);
  const d = await r.json();
  _tossToken = d.access_token;
  _tossExpires = Date.now() + (d.expires_in || 86400) * 1000;
  return _tossToken;
}

function krNowMinutes() {
  const now = new Date();
  const utcMin = now.getUTCHours() * 60 + now.getUTCMinutes();
  return (utcMin + 9 * 60) % (24 * 60);
}

function phase() {
  const m = krNowMinutes();
  if (m >= 9 * 60 && m <= 15 * 60 + 30) return 'kr';
  if (m > 15 * 60 + 30 || m < 6 * 60) return 'us';
  return 'none';
}

function krCodes() {
  return Object.values(universe.sectors).flatMap(s => s.stocks.map(x => x.code));
}

function usTickers() {
  const set = new Set();
  Object.values(universe.sectors).forEach(s =>
    (s.bellwethers || []).forEach(b => set.add(b.t))
  );
  return [...set];
}

async function tossPrices(symbols) {
  const token = await getTossToken();
  const r = await fetch(
    'https://openapi.tossinvest.com/api/v1/prices?symbols=' + encodeURIComponent(symbols.join(',')),
    { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(8000) }
  );
  if (!r.ok) throw new Error(`Toss prices ${r.status}`);
  const d = await r.json();
  return Array.isArray(d.result) ? d.result : (d.result?.prices || d.prices || []);
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const ph = phase();
    if (ph === 'none') return res.status(200).json({ phase: 'none', prices: [] });
    const symbols = ph === 'kr' ? krCodes() : usTickers();
    const prices = await tossPrices(symbols);
    return res.status(200).json({ phase: ph, prices });
  } catch (e) {
    return res.status(502).json({ error: String(e), prices: [] });
  }
}
