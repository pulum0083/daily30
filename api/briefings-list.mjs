// briefings-list.json을 프록시로 반환 — 사내망에서 /data/*.json이 차단될 때 fallback
export default async function handler(req, res) {
  try {
    const r = await fetch(
      'https://raw.githubusercontent.com/pulum0083/daily30/main/web/data/briefings-list.json',
      { signal: AbortSignal.timeout(8000) }
    );
    if (!r.ok) throw new Error(`upstream ${r.status}`);
    const data = await r.json();
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
    res.status(200).json(data);
  } catch (e) {
    res.status(502).json({ error: 'upstream', message: String(e) });
  }
}
