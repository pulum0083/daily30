const WEB_BASE    = 'https://doubleshot.space';
const ADMIN_EMAIL = 'pulum0083@gmail.com';

async function sendViaResend(apiKey, { from, to, subject, html }) {
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type':  'application/json',
      'User-Agent':    'daily30-briefing/1.0',
    },
    body: JSON.stringify({ from, to: [to], subject, html }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resend error ${res.status}: ${body}`);
  }
  return res.json();
}

function buildBriefingEmail(latest, email) {
  const { label, title, direction, up_pct, confidence, reasons, link } = latest;

  const reasonRows = (reasons || []).map(r =>
    `<tr><td style="font-size:13px;line-height:1.7;color:#444;padding:3px 0">• ${r}</td></tr>`
  ).join('');

  const predBlock = direction ? `
    <tr><td style="padding:4px 0">
      <span style="font-size:14px;font-weight:700;color:#333">📊 예측: ${direction} (${up_pct}%)</span><br/>
      <span style="font-size:13px;color:#888">신뢰도: ${confidence}%</span>
    </td></tr>
    <tr><td style="padding:4px 0"></td></tr>
  ` : '';

  return `
    <div style="font-family:'Apple SD Gothic Neo',sans-serif;max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e5e5;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#006EFF,#7C3AED);padding:24px 28px">
        <div style="color:rgba(255,255,255,.7);font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px">Daily30' · AI 투자 브리핑</div>
        <div style="color:#fff;font-size:18px;font-weight:800;line-height:1.35">${title || label}</div>
      </div>
      <div style="padding:20px 28px">
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="font-size:13px;color:#888;padding-bottom:12px">${label}</td></tr>
          ${predBlock}
          ${reasonRows}
        </table>
      </div>
      <div style="padding:16px 28px;border-top:1px solid #f0f0f0;background:#fafafa">
        <a href="${link}" style="display:inline-block;background:#006EFF;color:#fff;text-decoration:none;font-size:14px;font-weight:700;padding:12px 24px;border-radius:8px">전체 브리핑 보기 →</a>
      </div>
      <div style="padding:14px 28px;font-size:11px;color:#bbb">
        Daily30' · 개인 투자 비서
      </div>
    </div>
  `;
}

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
  if (!RESEND_API_KEY) return res.status(500).json({ error: 'Missing RESEND_API_KEY' });

  try {
    // 최신 브리핑 정보 가져오기
    let latest = null;
    try {
      const r = await fetch(`${WEB_BASE}/data/latest.json`);
      if (r.ok) latest = await r.json();
    } catch (_) {}

    // 구독자에게 최신 브리핑 발송
    let briefingSent = false;
    if (latest) {
      const html    = buildBriefingEmail(latest, email);
      const subject = `📊 ${latest.title || latest.label} — Double-Shot 최신 브리핑`;
      try {
        await sendViaResend(RESEND_API_KEY, {
          from:    "Double-Shot <noreply@doubleshot.space>",
          to:      email,
          subject,
          html,
        });
        briefingSent = true;
      } catch (e) {
        console.error('[subscribe] 브리핑 발송 실패:', e.message);
      }
    }

    // 관리자 알림
    await sendViaResend(RESEND_API_KEY, {
      from:    "Double-Shot <noreply@doubleshot.space>",
      to:      ADMIN_EMAIL,
      subject: `[Double-Shot] 새 구독자: ${email}`,
      html:    `<p>새 구독자: <b>${email}</b></p>${latest ? `<p>최신 브리핑 ${briefingSent ? '발송 완료' : '발송 실패'}: <a href="${latest.link}">${latest.title}</a></p>` : ''}`,
    });

    return res.status(200).json({ ok: true, briefingSent });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ error: err.message });
  }
}
