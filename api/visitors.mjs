// GA4 누적 방문자수 조회 — OAuth2 리프레시 토큰으로 Analytics Data API 호출 (1시간 CDN 캐시)

async function getAccessToken(clientId, clientSecret, refreshToken) {
  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id:     clientId,
      client_secret: clientSecret,
      refresh_token: refreshToken,
      grant_type:    'refresh_token',
    }),
  });
  const { access_token } = await res.json();
  return access_token;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'GET') return res.status(405).end();

  const clientId     = process.env.GOOGLE_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET;
  const refreshToken = process.env.GOOGLE_REFRESH_TOKEN;
  const propertyId   = process.env.GA_PROPERTY_ID;
  if (!clientId || !clientSecret || !refreshToken || !propertyId)
    return res.status(503).json({ error: 'GA not configured' });

  const token = await getAccessToken(clientId, clientSecret, refreshToken);

  const gaRes = await fetch(
    `https://analyticsdata.googleapis.com/v1beta/properties/${propertyId}:runReport`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dateRanges: [{ startDate: '2025-01-01', endDate: 'today' }],
        metrics:    [{ name: 'totalUsers' }, { name: 'screenPageViews' }],
      }),
    }
  );

  if (!gaRes.ok) return res.status(502).json({ error: 'GA API failed' });
  const data      = await gaRes.json();
  const pageViews = parseInt(data.rows?.[0]?.metricValues?.[1]?.value || '0', 10);

  res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=86400');
  return res.status(200).json({ pageViews });
}
