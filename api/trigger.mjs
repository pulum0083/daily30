const VALID_TYPES = ['kospi', 'us', 'accuracy', 'fg-patch'];
const REPO = 'pulum0083/daily30';
const WORKFLOW = 'daily_report.yml';

// KST 기준 오늘 00:00 UTC ISO 문자열
function todayKSTStartUtc() {
  return new Date(Date.parse(
    new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10) + 'T00:00:00+09:00'
  )).toISOString();
}

// 오늘 KST 기준으로 동일 type 워크플로우 실행이 이미 있는지 확인
async function alreadyRunToday(ghPat, type) {
  const since = todayKSTStartUtc();
  const url = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?created=>=${since}&per_page=20`;
  try {
    const resp = await fetch(url, {
      headers: {
        Authorization: `Bearer ${ghPat}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
    });
    if (!resp.ok) return false;
    const data = await resp.json();
    return (data.workflow_runs || []).some(run =>
      run.inputs?.briefing_type === type &&
      ['queued', 'in_progress', 'completed'].includes(run.status)
    );
  } catch {
    return false; // 확인 실패 시 발송 허용
  }
}

export default async function handler(req, res) {
  const { type } = req.query;
  if (!VALID_TYPES.includes(type)) {
    return res.status(400).json({ error: `Invalid type: ${type}` });
  }

  const GH_PAT = process.env.GH_PAT;
  if (!GH_PAT) {
    return res.status(500).json({ error: 'Missing GH_PAT env var' });
  }

  // 오늘 이미 실행된 워크플로우가 있으면 중복 dispatch 방지
  const isDuplicate = await alreadyRunToday(GH_PAT, type);
  if (isDuplicate) {
    console.log(`[trigger] ⚠️ Already ran today for type=${type}. Skipping dispatch.`);
    return res.status(200).json({ ok: true, skipped: true, reason: 'already_ran_today', type });
  }

  const resp = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${GH_PAT}`,
        Accept: 'application/vnd.github+json',
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      body: JSON.stringify({ ref: 'main', inputs: { briefing_type: type } }),
    }
  );

  if (resp.status === 204) {
    console.log(`[trigger] ✓ dispatched type=${type}`);
    return res.status(200).json({ ok: true, type });
  }

  const body = await resp.text();
  console.error(`[trigger] GitHub API ${resp.status}: ${body}`);
  return res.status(500).json({ error: `GitHub API ${resp.status}`, body });
}
