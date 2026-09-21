// 테스트 전용 — 옛 시간대별 표(HTML) 픽스처를 새 원천(JSON)·저장본 응답으로 바꿔 대결판 조립 테스트에 먹인다.
// 옛 픽스처의 기대값(외국인 −8,693억 등)을 그대로 검증하려고 둔다. 운영 코드는 이 파일을 import하지 않는다.
// 옛 표 한 행: 시간 · 개인 · 외국인 · 기관계 · [금융투자 · 보험 · 투신 · 은행 · 기타금융 · 연기금] · 기타법인
function htmlRows(html) {
  const rows = [];
  for (const tr of String(html).match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || []) {
    const cells = [...tr.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((m) => m[1].replace(/<[^>]+>/g, '').trim());
    if (cells.length !== 11 || !/^\d{2}:\d{2}$/.test(cells[0])) continue;
    const v = cells.slice(1).map((x) => Number(x.replace(/,/g, '')));
    if (v.some((n) => !Number.isFinite(n))) continue;
    rows.push({ t: cells[0], v });
  }
  return rows;
}
const CODES = { 8000: 0, 9000: 1, 1000: 3, 2000: 4, 3000: 5, 4000: 6, 5000: 7, 6000: 8, 7100: 9 };
const INST = ['금융투자', '보험', '투신', '은행', '기타금융', '연기금'];

const toItem = (ymd, r) => ({
  bizdate: ymd, time: r.t.replace(':', '') + '00',
  netAmounts: Object.entries(CODES).map(([k, i]) => ({ investorGubun: k, diffValue: String(r.v[i] * 1e8) })),
});
const toStored = (r) => ({
  t: r.t, 개인: r.v[0], 외국인: r.v[1], 기관: r.v[2], 기타법인: r.v[9],
  inst: Object.fromEntries(INST.map((k, i) => [k, r.v[3 + i]])),
});

const CACHE = new WeakMap();
// now의 KST 날짜가 오늘(T)이고, 저장본 요청은 URL의 날짜를 그대로 쓴다. 같은 (fetchJson, fetchText) 쌍엔 같은 함수를 돌려줘
// 운영 코드의 fetch 참조별 메모(memoFor)가 테스트에서도 그대로 작동하게 한다.
export function withFlow(fetchJson, fetchText, now) {
  if (!fetchText) return fetchJson;
  const byText = CACHE.get(fetchJson) || new WeakMap();
  CACHE.set(fetchJson, byText);
  if (byText.has(fetchText)) return byText.get(fetchText);
  const dash = new Date(now + 9 * 3600 * 1000).toISOString().slice(0, 10);
  const T = dash.replace(/-/g, '');
  const oldUrl = (ymd) => `https://finance.naver.com/sise/investorDealTrendTime.naver?bizdate=${ymd}&sosok=01&page=1`;
  const fn = async (url) => {
    if (/stock\.naver\.com\/api\/domestic\/market\/trend\/time/.test(url)) {
      if (!/startIdx=0&/.test(url)) return { content: [], last: 'true' };
      return { content: htmlRows(await fetchText(oldUrl(T))).map((r) => toItem(T, r)), last: 'true' };
    }
    const m = url.match(/\/data\/investor-time\/(\d{8})\.json$/);
    if (m) {
      const rows = htmlRows(await fetchText(oldUrl(m[1]))).map(toStored).sort((a, b) => a.t.localeCompare(b.t));
      return { date: m[1], rows };
    }
    return fetchJson(url);
  };
  byText.set(fetchText, fn);
  return fn;
}
