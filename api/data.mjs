// /data/*.json 정적 파일 프록시 — 사내망에서 /data/ 가 차단될 때 서버 경유 fallback (화이트리스트 처리)
// 저장소가 private이라 raw.githubusercontent.com은 모든 파일에 404(→502)를 반환한다. 대신 배포된
// 같은 출처의 /data/ 정적 파일을 서버에서 fetch한다 — 클라이언트가 사내망에서 /data/ 차단돼도 Vercel
// 함수는 정상 접근하므로 원래 fallback 목적을 유지하고, 배포마다 갱신되는 -live 파일이라 신선하다.

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
    const host = req.headers['x-forwarded-host'] || req.headers.host;
    const proto = req.headers['x-forwarded-proto'] || 'https';
    const r = await fetch(`${proto}://${host}/data/${file}`, { signal: AbortSignal.timeout(8000) });
    if (!r.ok) throw new Error(`upstream ${r.status}`);
    const data = await r.json();
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
    res.status(200).json(data);
  } catch (e) {
    res.status(502).json({ error: 'upstream', message: String(e) });
  }
}
