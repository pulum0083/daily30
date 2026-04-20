const VALID_TYPES = ['kospi', 'us', 'accuracy', 'fg-patch'];
const REPO = 'pulum0083/daily30';
const WORKFLOW = 'daily_report.yml';

export default async function handler(req, res) {
  // Vercel cron secret 검증
  const auth = req.headers['authorization'];
  if (auth !== `Bearer ${process.env.CRON_SECRET}`) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const { type } = req.query;
  if (!VALID_TYPES.includes(type)) {
    return res.status(400).json({ error: `Invalid type: ${type}` });
  }

  const GH_PAT = process.env.GH_PAT;
  if (!GH_PAT) {
    return res.status(500).json({ error: 'Missing GH_PAT env var' });
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
