const WEB_BASE    = 'https://doubleshot.space';
const ADMIN_EMAIL = 'pulum0083@gmail.com';

async function sendViaResend(apiKey, { from, to, subject, html, headers: extraHeaders = {} }) {
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type':  'application/json',
      'User-Agent':    'daily30-briefing/1.0',
    },
    body: JSON.stringify({ from, to: [to], subject, html, headers: extraHeaders }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resend error ${res.status}: ${body}`);
  }
  return res.json();
}

async function addContact(apiKey, audienceId, email) {
  const res = await fetch(`https://api.resend.com/audiences/${audienceId}/contacts`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type':  'application/json',
    },
    body: JSON.stringify({ email, subscribed: true }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resend Contacts error ${res.status}: ${body}`);
  }
  return res.json();
}

function buildBriefingEmail(latest) {
  const { label, title, direction, up_pct, confidence, reasons, link } = latest;

  const reasonRows = (reasons || []).map(r =>
    `<tr><td style="font-size:13px;line-height:1.8;color:#444444;padding:3px 0;">&#8226; ${r.replace(/<[^>]+>/g, '')}</td></tr>`
  ).join('');

  const predBlock = direction ? `
    <tr><td style="padding:4px 0;">
      <span style="font-size:14px;font-weight:700;color:#333333;">&#128202; &#xC608;&#xCE21;: ${direction} (${up_pct}%)</span><br/>
      <span style="font-size:13px;color:#888888;">&#xC2E0;&#xB8B0;&#xB3C4;: ${confidence}%</span>
    </td></tr>
    <tr><td style="padding:4px 0;"></td></tr>
  ` : '';

  return `<!DOCTYPE html>
<html lang="ko" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="UTF-8"/>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Double-Shot 브리핑</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f5f5;">
  <tr><td align="center" style="padding:24px 16px;">
    <table width="560" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;background:#ffffff;border:1px solid #e5e5e5;">
      <!-- 헤더 -->
      <tr>
        <td bgcolor="#006EFF" style="padding:24px 28px;background:#006EFF;">
          <p style="margin:0 0 8px 0;font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:rgba(255,255,255,0.8);letter-spacing:1px;">Double-Shot &#183; AI &#xD22C;&#xC790; &#xBE0C;&#xB9AC;&#xD551;</p>
          <p style="margin:0;font-family:Arial,sans-serif;font-size:18px;font-weight:800;color:#ffffff;line-height:1.4;">${title || label}</p>
        </td>
      </tr>
      <!-- 본문 -->
      <tr>
        <td style="padding:20px 28px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr><td style="font-size:13px;color:#888888;padding-bottom:12px;font-family:Arial,sans-serif;">${label}</td></tr>
            ${predBlock}
            ${reasonRows}
          </table>
        </td>
      </tr>
      <!-- CTA -->
      <tr>
        <td style="padding:16px 28px;border-top:1px solid #f0f0f0;background:#fafafa;">
          <a href="${link}" style="display:inline-block;background:#006EFF;color:#ffffff;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;font-weight:700;padding:12px 24px;">&#xC804;&#xCCB4; &#xBE0C;&#xB9AC;&#xD551; &#xBCF4;&#xAE30; &#x2192;</a>
        </td>
      </tr>
      <!-- 푸터 -->
      <tr>
        <td style="padding:14px 28px;font-family:Arial,sans-serif;font-size:11px;color:#bbbbbb;">
          Double-Shot &#183; AI &#xD22C;&#xC790; &#xBE0C;&#xB9AC;&#xD551; &#xC11C;&#xBE44;&#xC2A4;
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body>
</html>`;
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

  const RESEND_API_KEY    = process.env.RESEND_API_KEY;
  const RESEND_AUDIENCE_ID = process.env.RESEND_AUDIENCE_ID;
  if (!RESEND_API_KEY) return res.status(500).json({ error: 'Missing RESEND_API_KEY' });

  try {
    // 1. Resend Contacts에 구독자 저장 (일일 브리핑 발송용)
    let contactSaved = false;
    if (RESEND_AUDIENCE_ID) {
      try {
        await addContact(RESEND_API_KEY, RESEND_AUDIENCE_ID, email);
        contactSaved = true;
      } catch (e) {
        console.error('[subscribe] Contacts 저장 실패:', e.message);
      }
    }

    // 2. 최신 브리핑 정보 가져오기
    let latest = null;
    try {
      const r = await fetch(`${WEB_BASE}/data/latest.json`);
      if (r.ok) latest = await r.json();
    } catch (_) {}

    // 3. 구독자에게 최신 브리핑 즉시 발송
    let briefingSent = false;
    if (latest) {
      const html    = buildBriefingEmail(latest);
      const subject = `📊 ${latest.title || latest.label} — Double-Shot 최신 브리핑`;
      try {
        await sendViaResend(RESEND_API_KEY, {
          from:    "Double-Shot <noreply@doubleshot.space>",
          to:      email,
          subject,
          html,
          headers: {
            'List-Unsubscribe': `<mailto:unsubscribe@doubleshot.space?subject=unsubscribe>`,
            'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
          },
        });
        briefingSent = true;
      } catch (e) {
        console.error('[subscribe] 브리핑 발송 실패:', e.message);
      }
    }

    // 4. 관리자 알림
    try {
      await sendViaResend(RESEND_API_KEY, {
        from:    "Double-Shot <noreply@doubleshot.space>",
        to:      ADMIN_EMAIL,
        subject: `[Double-Shot] 새 구독자: ${email}`,
        html:    `<p>새 구독자: <b>${email}</b></p>
                  <p>Contacts 저장: ${contactSaved ? '✅ 완료' : '❌ 실패 (RESEND_AUDIENCE_ID 미설정 또는 오류)'}</p>
                  ${latest ? `<p>최신 브리핑 ${briefingSent ? '발송 완료 ✅' : '발송 실패 ❌'}: <a href="${latest.link}">${latest.title}</a></p>` : '<p>latest.json 없음</p>'}`,
      });
    } catch (e) {
      console.error('[subscribe] 관리자 알림 발송 실패:', e.message);
    }

    return res.status(200).json({ ok: true, briefingSent, contactSaved });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ error: err.message });
  }
}
