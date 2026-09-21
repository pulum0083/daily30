// 코스피 투자자별 순매수 1분 시계열 — 오늘은 네이버 새 원천, 지난 날짜는 마감 잡이 저장한 파일(SERVICE_RULES §56)
//
// 옛 표(finance.naver.com/sise/investorDealTrendTime.naver)는 2026-09-18부터 HTTP 410이다.
// 새 원천(stock.naver.com/api/domestic/market/trend/time)은 1분 단위지만 bizdate 인자를 무시하고 **오늘치만** 준다.
// 그래서 '어제 같은 시각'은 마감 잡이 web/data/investor-time/{날짜}.json에 저장한 시계열에서 읽는다.
// 코드 매핑·검산은 scripts/fetch_data.py INVESTOR_GUBUN과 같다(§30 — 규칙이 갈라지면 안 된다).
export const LIVE_URL = (p) =>
  `https://stock.naver.com/api/domestic/market/trend/time?tradeType=KRX&marketType=KOSPI&startIdx=${p}&pageSize=100`;
export const STORE_URL = (ymd) => `https://doubleshot.space/data/investor-time/${ymd}.json`;

const GUBUN = {
  1000: '금융투자', 2000: '보험', 3000: '투신', 3100: '투신', 4000: '은행', 5000: '기타금융',
  6000: '연기금', 7000: '연기금', 7100: '기타법인', 8000: '개인', 9000: '외국인', 9001: '외국인',
};
const INST = ['금융투자', '보험', '투신', '은행', '기타금융', '연기금'];
const MAX_PAGES = 10;

// 한 페이지 → [{date, t: 'HH:MM', 개인, 외국인, 기관, 기타법인, inst}] (억원, 원본 순서 = 최신순).
// 개인+외국인+기관계+기타법인이 ±5억을 벗어나면 코드가 바뀐 것이라 그 행을 버린다. 없는 기관 세부 칸은 null(§0).
export function parseInvestorTimeJson(payload) {
  const rows = [];
  for (const it of payload?.content || []) {
    const t = String(it?.time ?? ''), d = String(it?.bizdate ?? '');
    if (!/^\d{6}$/.test(t) || !/^\d{8}$/.test(d)) continue;
    const acc = {};
    let bad = false;
    for (const a of it.netAmounts || []) {
      const k = GUBUN[String(a?.investorGubun)];
      if (!k) continue;
      const v = Number(a?.diffValue);
      if (!Number.isFinite(v)) { bad = true; break; }
      acc[k] = (acc[k] ?? 0) + v;
    }
    if (bad || acc.개인 == null || acc.외국인 == null || acc.기타법인 == null || !INST.some((k) => k in acc)) continue;
    const inst = INST.reduce((s, k) => s + (acc[k] ?? 0), 0);
    if (Math.abs(acc.개인 + acc.외국인 + inst + acc.기타법인) > 5e8) continue;
    const eok = (v) => Math.round(v / 1e8);
    rows.push({
      date: d, t: `${t.slice(0, 2)}:${t.slice(2, 4)}`,
      개인: eok(acc.개인), 외국인: eok(acc.외국인), 기관: eok(inst), 기타법인: eok(acc.기타법인),
      inst: Object.fromEntries(INST.map((k) => [k, k in acc ? eok(acc[k]) : null])),
    });
  }
  return rows;
}

const hhmmOf = (r) => r.t.replace(':', '');

// 오늘 시계열에서 hhmm 이하 첫 행. 원천 날짜가 ymd가 아니면 null(지난 날짜를 오늘 값으로 착각하지 않는다).
// 행이 깨진 페이지를 만나면 그 전까지 찾은 값도 버린다 — 파싱 실패를 성공으로 착각하지 않는다(§45·I1).
export async function liveFlowAt(ymd, hhmm, fetchJson) {
  for (let p = 0; p < MAX_PAGES; p++) {
    const d = await fetchJson(LIVE_URL(p));
    const content = d?.content || [];
    const rows = parseInvestorTimeJson(d);
    if (!content.length || rows.length !== content.length) return null;
    if (rows.some((r) => r.date !== ymd)) return null;
    const hit = rows.find((r) => hhmmOf(r) <= hhmm);
    if (hit) return hit;
    if (String(d?.last).toLowerCase() === 'true') return null;
  }
  return null;
}

// 저장본(오래된→최신)에서 hhmm 이하 마지막 행. 파일이 없거나 날짜가 다르면 null.
export async function storedFlowAt(ymd, hhmm, fetchJson) {
  const body = await fetchJson(STORE_URL(ymd));
  if (!body || body.date !== ymd || !Array.isArray(body.rows)) return null;
  let hit = null;
  for (const r of body.rows) if (typeof r?.t === 'string' && hhmmOf(r) <= hhmm) hit = { ...r, date: ymd };
  return hit;
}
