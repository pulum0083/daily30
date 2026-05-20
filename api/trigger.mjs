const VALID_TYPES = ['kospi', 'kospi-close', 'us', 'accuracy'];
const REPO = 'pulum0083/daily30';
const WORKFLOW = 'daily_report.yml';

function isAuthorized(req) {
  const secret = process.env.CRON_SECRET;
  if (!secret) return { ok: false, status: 500, error: 'Missing CRON_SECRET env var' };

  const auth = req.headers.authorization || '';
  if (auth !== `Bearer ${secret}`) {
    return { ok: false, status: 401, error: 'Unauthorized' };
  }

  return { ok: true };
}

// KST 기준 오늘 00:00 UTC ISO 문자열
function todayKSTStartUtc() {
  return new Date(Date.parse(
    new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10) + 'T00:00:00+09:00'
  )).toISOString();
}

// 오늘 KST 기준으로 동일 type 워크플로우 실행이 이미 있는지 확인
async function alreadyRunToday(ghPat, type) {
  const since = todayKSTStartUtc();
  const url = new URL(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs`);
  url.searchParams.set('created', `>=${since}`);
  url.searchParams.set('per_page', '20');
  const resp = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${ghPat}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`GitHub runs API ${resp.status}: ${body}`);
  }

  const data = await resp.json();
  return (data.workflow_runs || []).some(run =>
    run.display_title === `Daily 30 Report (${type})` &&
    ['queued', 'in_progress', 'completed'].includes(run.status)
  );
}

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const auth = isAuthorized(req);
  if (!auth.ok) {
    return res.status(auth.status).json({ error: auth.error });
  }

  const { type } = req.query;
  if (!VALID_TYPES.includes(type)) {
    return res.status(400).json({ error: `Invalid type: ${type}` });
  }

  const dryRun = req.query.dry_run === 'true' ? 'true' : 'false';

  const GH_PAT = process.env.GH_PAT;
  if (!GH_PAT) {
    return res.status(500).json({ error: 'Missing GH_PAT env var' });
  }

  // 오늘 이미 실행된 워크플로우가 있으면 중복 dispatch 방지
  let isDuplicate = false;
  try {
    isDuplicate = await alreadyRunToday(GH_PAT, type);
  } catch (err) {
    console.error(`[trigger] duplicate check failed: ${err.message}`);
    return res.status(503).json({ error: 'Could not verify duplicate run state' });
  }

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
      body: JSON.stringify({ ref: 'main', inputs: { briefing_type: type, dry_run: dryRun } }),
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
