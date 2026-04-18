export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { email } = req.body;
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: 'Invalid email' });
  }

  const RESEND_API_KEY = process.env.RESEND_API_KEY;
  if (!RESEND_API_KEY) {
    return res.status(500).json({ error: 'Missing RESEND_API_KEY' });
  }

  try {
    const r1 = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: "Daily30' <onboarding@resend.dev>",
        to: [email],
        subject: "[Daily30'] 구독 신청이 완료되었습니다",
        html: `
          <div style="font-family:sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;color:#111">
            <h2 style="font-size:22px;font-weight:800;margin-bottom:8px">Daily30' 구독을 시작합니다 🎉</h2>
            <p style="color:#555;line-height:1.7"><b>${email}</b>으로 매일 아침 투자 브리핑을 보내드릴게요.</p>
            <hr style="border:none;border-top:1px solid #eee;margin:24px 0"/>
            <p style="font-size:13px;color:#888;line-height:1.7">
              📈 <b>08:30</b> 코스피 시초가 브리핑 (평일)<br/>
              🇺🇸 <b>22:30</b> 미국 시장 브리핑 (평일)<br/>
              📊 <b>21:00</b> 주간 리포트 (일요일)
            </p>
            <hr style="border:none;border-top:1px solid #eee;margin:24px 0"/>
            <p style="font-size:12px;color:#aaa">언제든 구독을 해지할 수 있습니다.</p>
          </div>
        `,
      }),
    });

    const data = await r1.json();
    if (!r1.ok) return res.status(500).json({ error: data });

    // 관리자 알림
    await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: "Daily30' <onboarding@resend.dev>",
        to: ['luke00.ncsoft@gmail.com'],
        subject: `[Daily30'] 새 구독자: ${email}`,
        html: `<p>새 구독자: <b>${email}</b></p>`,
      }),
    });

    return res.status(200).json({ ok: true });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
