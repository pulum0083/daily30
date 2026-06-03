// 건의 텍스트를 텔레그램 관리자 봇으로 전달하는 Vercel 엔드포인트
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { message, page } = req.body || {};
  if (!message || !message.trim()) {
    return res.status(400).json({ error: 'message required' });
  }

  const token  = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) {
    return res.status(500).json({ error: 'Telegram env vars missing' });
  }

  const kst = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
  const ts  = `${kst.getFullYear()}-${String(kst.getMonth()+1).padStart(2,'0')}-${String(kst.getDate()).padStart(2,'0')} ${String(kst.getHours()).padStart(2,'0')}:${String(kst.getMinutes()).padStart(2,'0')} KST`;
  const text = `💬 [건의]\n\n${message.trim()}\n\n📄 ${page || '(페이지 미상)'}\n🕐 ${ts}`;

  const tgRes = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text }),
  });

  if (!tgRes.ok) {
    const body = await tgRes.text();
    console.error('[feedback] Telegram error:', body);
    return res.status(500).json({ error: 'Telegram send failed' });
  }

  return res.status(200).json({ ok: true });
}
