// cron-job.org를 대체하는 Cloudflare Workers 스케줄러
// cron 트리거 → GitHub Actions workflow_dispatch 호출

const REPO = 'pulum0083/daily30';

async function dispatch(env, workflow, inputs = null) {
  const body = inputs ? { ref: 'main', inputs } : { ref: 'main' };
  const resp = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization:          `Bearer ${env.GH_PAT}`,
        Accept:                 'application/vnd.github+json',
        'Content-Type':         'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent':           'doubleshot-worker/1.0',
      },
      body: JSON.stringify(body),
    }
  );
  if (resp.status !== 204) {
    const text = await resp.text();
    throw new Error(`GitHub API ${resp.status}: ${text}`);
  }
}

export default {
  async scheduled(event, env) {
    // scheduledTime은 UTC ms. KST = UTC+9
    const kst    = new Date(event.scheduledTime + 9 * 3600_000);
    const dow    = kst.getUTCDay();   // 0=일, 1=월 … 6=토
    const h      = kst.getUTCHours();
    const m      = kst.getUTCMinutes();
    const mins   = h * 60 + m;

    const isWeekday  = dow >= 1 && dow <= 5; // 월~금
    const isTueSat   = dow >= 2 && dow <= 6; // 화~토 (accuracy)

    console.log(`[cron] KST ${h}:${String(m).padStart(2,'0')} dow=${dow}`);

    // ── 정기 브리핑 (정확한 시각 매칭) ───────────────────────────────────

    // 코스피 시초가: 07:30 KST 월~금
    if (h === 7 && m === 30 && isWeekday) {
      console.log('[cron] → kospi briefing');
      return dispatch(env, 'daily_report.yml', { briefing_type: 'kospi', dry_run: 'false' });
    }

    // 코스피 마감: 16:30 KST 월~금
    if (h === 16 && m === 30 && isWeekday) {
      console.log('[cron] → kospi-close briefing');
      return dispatch(env, 'daily_report.yml', { briefing_type: 'kospi-close', dry_run: 'false' });
    }

    // 미국 시장: 21:20 KST 월~금
    if (h === 21 && m === 20 && isWeekday) {
      console.log('[cron] → us briefing');
      return dispatch(env, 'daily_report.yml', { briefing_type: 'us', dry_run: 'false' });
    }

    // 예측 정확도: 09:10 KST 화~토
    if (h === 9 && m === 10 && isTueSat) {
      console.log('[cron] → accuracy check');
      return dispatch(env, 'daily_report.yml', { briefing_type: 'accuracy', dry_run: 'false' });
    }

    // ── 이슈 브리핑 (시간대 범위 매칭) ──────────────────────────────────

    if (!isWeekday) return; // 주말 제외

    // MARKET:      09:00~15:30 KST, :00/:30 마다
    if (mins >= 540 && mins <= 930 && (m === 0 || m === 30)) {
      console.log('[cron] → issue briefing MARKET');
      return dispatch(env, 'kospi-news-live.yml');
    }

    // POST_MARKET: 16:35~20:35 KST, :35 마다
    if (mins >= 995 && mins <= 1235 && m === 35) {
      console.log('[cron] → issue briefing POST_MARKET');
      return dispatch(env, 'kospi-news-live.yml');
    }

    // US_MARKET:   21:30~23:30 KST, :30 마다
    if (mins >= 1290 && mins <= 1410 && m === 30) {
      console.log('[cron] → issue briefing US_MARKET');
      return dispatch(env, 'kospi-news-live.yml');
    }

    console.log('[cron] no matching job, skip');
  },
};
