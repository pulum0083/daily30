// 게시판 글 등록: GitHub board.json 업데이트 + 텔레그램 관리자 알림
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { content, author } = req.body || {};
  if (!content || !content.trim()) return res.status(400).json({ error: 'content required' });
  if (!author  || !author.trim())  return res.status(400).json({ error: 'author required' });

  const GH_PAT = process.env.GH_PAT;
  const REPO   = 'pulum0083/daily30';
  const PATH   = 'web/data/board.json';
  const ghHeaders = {
    Authorization: `Bearer ${GH_PAT}`,
    Accept: 'application/vnd.github+json',
    'Content-Type': 'application/json',
    'X-GitHub-Api-Version': '2022-11-28',
  };

  // 현재 파일 읽기 (SHA 필요)
  const getRes = await fetch(`https://api.github.com/repos/${REPO}/contents/${PATH}`, { headers: ghHeaders });
  if (!getRes.ok) return res.status(502).json({ error: 'github read failed' });
  const { content: b64, sha } = await getRes.json();
  const current = JSON.parse(Buffer.from(b64, 'base64').toString('utf8'));

  // 새 글 추가
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
  if (!putRes.ok) return res.status(502).json({ error: 'github write failed' });

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
