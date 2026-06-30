// /data/*.json 정적 파일 프록시 — 사내망에서 /data/ 가 차단될 때 fallback (단일 함수로 화이트리스트 처리)
const RAW_BASE = 'https://raw.githubusercontent.com/pulum0083/daily30/main/web/data';

// 허용 파일 화이트리스트: 키 → 실제 파일명
const ALLOW = {
  'news-live': 'kospi-news-live.json',
  'briefings-list': 'briefings-list.json',
  'movers-why': 'movers-why-live.json',
};

export default async function handler(req, res) {
  const key = (req.query && req.query.f) || '';
  const file = ALLOW[key];
  if (!file) {
    res.status(400).json({ error: 'bad_request', message: 'unknown f' });
    return;
  }
  try {
    const r = await fetch(`${RAW_BASE}/${file}`, { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error(`upstream ${r.status}`);
    const data = await r.json();
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
    res.status(200).json(data);
  } catch (e) {
    res.status(502).json({ error: 'upstream', message: String(e) });
  }
}
