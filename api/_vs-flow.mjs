// 네이버 금융 시간대별 투자자 매매동향(코스피) — 표 파싱과 '그 시각 이하 마지막 행' 조회(설계 §6 #4)
const URL_BASE = 'https://finance.naver.com/sise/investorDealTrendTime.naver';

export function parseInvestorTimePage(html) {
  const rows = [];
  for (const tr of String(html).match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || []) {
    const cells = [...tr.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((m) => m[1].replace(/<[^>]+>|&nbsp;/g, '').trim());
    if (cells.length !== 11 || !/^\d{2}:\d{2}$/.test(cells[0])) continue;
    const v = cells.slice(1).map((x) => Number(x.replace(/,/g, '')));
    if (v.some((n) => !Number.isFinite(n))) continue;
    // 개인+외국인+기관계+기타법인 = 0(반올림 최대 2억). 벗어나면 열이 밀린 것이라 쓰지 않는다
    if (Math.abs(v[0] + v[1] + v[2] + v[9]) > 5) continue;
    rows.push({ t: cells[0], 개인: v[0], 외국인: v[1], 기관: v[2] });
  }
  return rows;
}

export function lastPage(html) {
  const nums = [...String(html).matchAll(/page=(\d+)/g)].map((m) => Number(m[1]));
  return nums.length ? Math.max(...nums) : 1;
}

// 페이지는 최신 시각부터. 어떤 페이지에 target 이하 행이 있으면 답은 그 페이지거나 더 앞 페이지다
export async function flowAt(ymd, hhmm, fetchText) {
  const url = (p) => `${URL_BASE}?bizdate=${ymd}&sosok=01&page=${p}`;
  const firstHtml = await fetchText(url(1));
  const cache = new Map([[1, parseInvestorTimePage(firstHtml)]]);
  const rowsOf = async (p) => {
    if (!cache.has(p)) cache.set(p, parseInvestorTimePage(await fetchText(url(p))));
    return cache.get(p);
  };
  let lo = 1, hi = lastPage(firstHtml), found = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const rows = await rowsOf(mid);
    if (!rows.length) return found;
    const hit = rows.find((r) => r.t.replace(':', '') <= hhmm);
    if (hit) { found = hit; hi = mid - 1; } else lo = mid + 1;
  }
  return found;
}
