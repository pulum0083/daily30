// GA4 누적 방문자수 조회 — 서비스 계정 JWT로 Analytics Data API 호출 (1시간 CDN 캐시)
import { createSign } from 'crypto';

async function getAccessToken(sa) {
  const now = Math.floor(Date.now() / 1000);
  const header  = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({
    iss:   sa.client_email,
    scope: 'https://www.googleapis.com/auth/analytics.readonly',
    aud:   'https://oauth2.googleapis.com/token',
    iat:   now,
    exp:   now + 3600,
  })).toString('base64url');

  const unsigned = `${header}.${payload}`;
  const sign = createSign('RSA-SHA256');
  sign.update(unsigned);
  const sig = sign.sign(sa.private_key, 'base64url');

  const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=${unsigned}.${sig}`,
  });
  const { access_token } = await tokenRes.json();
  return access_token;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'GET') return res.status(405).end();

  const saJson      = process.env.GA_SERVICE_ACCOUNT_JSON;
  const propertyId  = process.env.GA_PROPERTY_ID;
  if (!saJson || !propertyId) return res.status(503).json({ error: 'GA not configured' });

  const sa    = JSON.parse(saJson);
  const token = await getAccessToken(sa);

  const gaRes = await fetch(
    `https://analyticsdata.googleapis.com/v1beta/properties/${propertyId}:runReport`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dateRanges: [{ startDate: '2025-01-01', endDate: 'today' }],
        metrics:    [{ name: 'totalUsers' }],
      }),
    }
  );

  if (!gaRes.ok) {
    const errBody = await gaRes.json().catch(() => ({}));
    console.error('[visitors] GA API failed', gaRes.status, JSON.stringify(errBody));
    return res.status(502).json({ error: 'GA API failed', _debug: { status: gaRes.status, ga: errBody } });
  }
  const data  = await gaRes.json();
  const count = parseInt(data.rows?.[0]?.metricValues?.[0]?.value || '0', 10);

  res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=86400');
  return res.status(200).json({ totalUsers: count });
}
