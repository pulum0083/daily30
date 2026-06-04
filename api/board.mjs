// 게시판 글 조회(GET) / 등록(POST): GitHub board.json 실시간 읽기·쓰기 + 텔레그램 관리자 알림
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const GH_PAT = process.env.GH_PAT;
  if (!GH_PAT) return res.status(500).json({ error: 'Missing GH_PAT env var' });
  const REPO   = 'pulum0083/daily30';
  const PATH   = 'web/data/board.json';
  const ghHeaders = {
    Authorization: `Bearer ${GH_PAT}`,
    Accept: 'application/vnd.github+json',
    'Content-Type': 'application/json',
    'X-GitHub-Api-Version': '2022-11-28',
  };

  // GET — GitHub에서 실시간으로 최신 글 목록 반환
  if (req.method === 'GET') {
    const getRes = await fetch(`https://api.github.com/repos/${REPO}/contents/${PATH}`, { headers: ghHeaders });
    if (!getRes.ok) return res.status(502).json({ error: 'github read failed' });
    const { content: b64 } = await getRes.json();
    const data = JSON.parse(Buffer.from(b64, 'base64').toString('utf8'));
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).json(data);
  }

  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { content, author } = req.body || {};
  if (!content || !content.trim()) return res.status(400).json({ error: 'content required' });
  if (!author  || !author.trim())  return res.status(400).json({ error: 'author required' });
  if (content.trim().length > 1000) return res.status(400).json({ error: 'content too long' });
  if (author.trim().length > 50)    return res.status(400).json({ error: 'author too long' });

  // 현재 파일 읽기 (SHA 필요)
  const getRes = await fetch(`https://api.github.com/repos/${REPO}/contents/${PATH}`, { headers: ghHeaders });
  if (!getRes.ok) return res.status(502).json({ error: 'github read failed' });
  const { content: b64, sha } = await getRes.json();
  const current = JSON.parse(Buffer.from(b64, 'base64').toString('utf8'));

  // 속도 제한: 최근 1분 내 전체 게시물 5개 초과 시 거부
  if (Array.isArray(current.posts)) {
    const cutoff = Date.now() - 60_000;
    const recentCount = current.posts.filter(p => new Date(p.created_at).getTime() > cutoff).length;
    if (recentCount >= 5) {
      return res.status(429).json({ error: '잠시 후 다시 시도해주세요 (분당 최대 5건)' });
    }
  }

  // 새 글 추가
  if (!Array.isArray(current.posts)) current.posts = [];
  const newPost = {
    id:         crypto.randomUUID(),
    content:    content.trim(),
    author:     author.trim(),
    created_at: new Date().toISOString(),
    is_admin:   false,
    parent_id:  null,
  };
  current.posts.push(newPost);

  // 파일 업데이트 (커밋)
  const kst     = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
  const dateStr = `${kst.getFullYear()}-${String(kst.getMonth()+1).padStart(2,'0')}-${String(kst.getDate()).padStart(2,'0')}`;
  const putRes  = await fetch(`https://api.github.com/repos/${REPO}/contents/${PATH}`, {
    method: 'PUT',
    headers: ghHeaders,
    body: JSON.stringify({
      message: `feat: 게시판 글 추가 (${author.trim()}, ${dateStr})`,
      content: Buffer.from(JSON.stringify(current, null, 2)).toString('base64'),
      sha,
    }),
  });
  if (!putRes.ok) return res.status(503).json({ error: '잠시 후 다시 시도해주세요' });

  // 텔레그램 알림 (실패해도 201 반환)
  const token  = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (token && chatId) {
    const ts   = `${dateStr} ${String(kst.getHours()).padStart(2,'0')}:${String(kst.getMinutes()).padStart(2,'0')} KST`;
    const text = `💬 [게시판] ${author.trim()}\n\n${content.trim()}\n\n🕐 ${ts}`;
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, text }),
    }).catch(() => {});
  }

  return res.status(201).json({ ok: true, post: newPost });
}
