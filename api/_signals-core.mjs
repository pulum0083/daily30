// 종목·ETF 신호 판정 순수 함수(네트워크 없음). 핸들러가 fetch한 데이터를 받아 가공한다.

import { SECTOR_LABEL, ETF_BET_DOWN, ETF_BET_UP, ETF_KOSPI200, ETF_SECTOR, ETF_SAFE } from './_etf-universe.mjs';

export const COUNTER_TREND_OUTPERF = 3.0;
// 급락일 보정: 지수가 크게 빠진 날은 '살짝 초록'인 종목까지 전부 역행 상승으로 잡혀 배지 변별력이 사라진다.
// 시장이 하락한 날엔 종목이 실제로 이 하한선 이상 오른 경우만 역행 상승으로 인정한다(지수 낙폭에 비례, 최대 1.5%).
export const COUNTER_MIN_GAIN_FACTOR = 0.25;
export const COUNTER_MIN_GAIN_CAP = 1.5;
export const VOL_SURGE_MIN = 1.5;
export const CAPITULATION_DROP = -3.0;
export const TURNOVER_TOP_N = 3;
export const NEAR_HIGH_RATIO = 0.98;
export const SIGNALS_DISPLAY_MAX = 8; // 특이 신호 카드 목록 최대 노출 수 (랭킹은 전체 집계)
// 카드 정렬 가중치 — 신고가·투매 같은 희소 신호를 최상위로. 급락일엔 역행 상승이 흔해지므로
// '그냥 초록'인 counter_up 보다, 급락장에도 신고가에 붙은 진짜 강세(near_high)와 투매(vol_surge)를 우선한다.
const SIGNAL_SCORE = { near_high: 5, vol_surge: 4, counter_up: 3, turnover: 2, foreign_buy: 1.5, inst_buy: 1.5 };

const sgn = (x) => (x > 0 ? 1 : x < 0 ? -1 : 0);

// 종목 1건의 가격·거래량 신호. stock={pct,vol,vol_avg20,price,wk52_high}
export function classifyStock(stock, kospiPct) {
  const cats = [];
  const badges = [];
  const { pct, vol, vol_avg20, price, wk52_high } = stock;

  // 역행: 방향 반대 + 아웃퍼폼. 단, 시장이 하락한 날엔 종목이 실제로 하한선 이상 올라야 인정(급락일 변별력 보정).
  const counterFloor = kospiPct < 0 ? Math.min(COUNTER_MIN_GAIN_CAP, Math.abs(kospiPct) * COUNTER_MIN_GAIN_FACTOR) : -Infinity;
  if (sgn(pct) !== sgn(kospiPct) && Math.abs(pct - kospiPct) >= COUNTER_TREND_OUTPERF && pct >= counterFloor) {
    cats.push('counter_up');
    badges.push('역행 상승');
  }
  // 투매(거래량 부분): 급증 + 급락
  const mult = vol_avg20 > 0 ? vol / vol_avg20 : 0;
  if (mult >= VOL_SURGE_MIN && pct <= CAPITULATION_DROP) {
    cats.push('vol_surge');
    badges.push(`거래량 ×${mult.toFixed(1)} 급증`);
  }
  // 신고가 근접
  if (wk52_high > 0 && price >= wk52_high * NEAR_HIGH_RATIO) {
    cats.push('near_high');
    const gap = Math.round((1 - price / wk52_high) * 100);
    badges.push(`52주 신고가 ${gap}%↓`);
  }
  return { cats, badges };
}

// 신호별 한 줄 설명 생성
function whyText(stock) {
  const { pct, cats } = stock;
  if (cats.includes('counter_up')) return `시장이 하락하는 동안 <b>${pct >= 0 ? '+' : ''}${pct.toFixed(1)}% ${pct >= 0 ? '상승' : '선방'}</b>했어요.`;
  if (cats.includes('vol_surge')) return `거래량이 급증하며 ${pct.toFixed(1)}% 급락했어요.`;
  if (cats.includes('near_high')) return `폭락장에도 <b>52주 신고가</b>에 근접했어요.`;
  if (cats.includes('turnover')) return `거래대금 상위. 지수에 큰 영향을 줬어요.`;
  if (cats.includes('foreign_buy')) return `외국인 수급이 꾸준히 들어오고 있어요.`;
  if (cats.includes('inst_buy')) return `기관 수급이 꾸준히 들어오고 있어요.`;
  return '';
}

// 신호 카테고리 메타(랭킹 라벨·아이콘) — 색 없음(색 절제 규칙)
export const SIGNAL_META = {
  vol_surge:  { ic: '🔥', label: '거래량 급증' },
  counter_up: { ic: '↗',  label: '역행 상승' },
  near_high:  { ic: '▲',  label: '52주 신고가 근접' },
  turnover:   { ic: '💰', label: '거래대금 상위' },
  inst_buy:   { ic: '🏛️', label: '기관 순매수' },
  foreign_buy:{ ic: '🌏', label: '외국인 순매수' },
  foreign_sell:{ ic: '🌏', label: '외국인 순매도' },
};

// stocks: [{code,name,sector,pct,vol,vol_avg20,price,wk52_high,amount}]
export function buildSignals(stocks, kospiPct, opts = {}) {
  const enrich = opts.enrich; // Task 9에서 수급 cats 주입용 (stock)=>({cats,badges})
  // 1) per-stock 분류
  const classified = stocks.map((s) => {
    const r = classifyStock(s, kospiPct);
    const cats = [...r.cats];
    const badges = [...r.badges];
    if (enrich) { const e = enrich(s); cats.push(...e.cats); badges.push(...e.badges); }
    return { ...s, cats, badges };
  });
  // 2) 거래대금 쏠림: 상위 N (충분한 종목이 있을 때만 의미 있음)
  if (classified.length > TURNOVER_TOP_N) {
    [...classified].sort((a, b) => (b.amount || 0) - (a.amount || 0)).slice(0, TURNOVER_TOP_N)
      .forEach((s) => { if (!s.cats.includes('turnover')) { s.cats.push('turnover'); s.badges.push('거래대금 상위'); } });
  }
  // 3) 신호 있는 종목만
  const signals = classified.filter((s) => s.cats.length > 0).map((s) => ({
    code: s.code, name: s.name, sector: SECTOR_LABEL[s.sector] || s.sector,
    pct: s.pct, dir: s.pct >= 0 ? 'up' : 'dn', cats: s.cats, badges: s.badges, why: whyText(s),
  }));
  // 4) 랭킹: 카테고리별 묶음, 종목수 내림차순(동수면 META 선언 순)
  const order = Object.keys(SIGNAL_META);
  const groups = {};
  signals.forEach((s) => s.cats.forEach((c) => { (groups[c] = groups[c] || []).push(s); }));
  const rank = Object.keys(groups)
    .sort((a, b) => groups[b].length - groups[a].length || order.indexOf(a) - order.indexOf(b))
    .slice(0, 5)
    .map((cat) => ({ cat, ...SIGNAL_META[cat], items: groups[cat] }));
  // 5) 점수순 정렬 — 카드(홈)는 상위 N, 전체(더보기)는 무제한. 랭킹은 위에서 전체 집계 완료.
  const sorted = [...signals]
    .map((s) => ({ s, score: s.cats.reduce((a, c) => a + (SIGNAL_SCORE[c] || 1), 0) }))
    .sort((a, b) => b.score - a.score || Math.abs(b.s.pct) - Math.abs(a.s.pct))
    .map((x) => ({ ...x.s, score: x.score }));
  const display = sorted.slice(0, SIGNALS_DISPLAY_MAX);
  return { signals: display, signalsAll: sorted, rank };
}

// 섹터별 평균 등락률·상승/하락 카운트 — '오늘의 한 줄' 배너가 장중에도 전 섹터 라이브 값을 쓰도록.
// stocks의 sector는 영문 키(semicon 등). 반환: { [sector]: {avg, up, dn, total} }
export function sectorAverages(stocks) {
  const acc = {};
  for (const s of stocks || []) {
    const k = s.sector; if (!k) continue;
    const a = acc[k] || (acc[k] = { sum: 0, up: 0, dn: 0, total: 0 });
    const p = s.pct || 0;
    a.sum += p; a.total += 1; if (p > 0) a.up += 1; else if (p < 0) a.dn += 1;
  }
  const out = {};
  for (const k of Object.keys(acc)) { const a = acc[k]; out[k] = { avg: a.total ? a.sum / a.total : 0, up: a.up, dn: a.dn, total: a.total }; }
  return out;
}

// byCode: { code: {amount, vol, pct} } — amount는 거래대금(백만)
export function etfBettingFlow(byCode) {
  const sum = (codes, f) => codes.reduce((a, c) => a + (byCode[c]?.[f] || 0), 0);
  const downAmt = sum(Object.keys(ETF_BET_DOWN), 'amount');
  const upAmt = sum(Object.keys(ETF_BET_UP), 'amount');
  const total = downAmt + upAmt;
  const downRatio = total > 0 ? Math.round((downAmt / total) * 100) : 0;
  const invCode = Object.keys(ETF_BET_DOWN)[0]; // 114800 KODEX 인버스
  const invVol = byCode[invCode]?.vol || 0;
  const refVol = byCode[ETF_KOSPI200]?.vol || 0;
  const invVolMultiple = refVol > 0 ? Math.round(invVol / refVol) : 0;
  const levCode = Object.keys(ETF_BET_UP)[0];
  return { downAmt, upAmt, downRatio, upRatio: 100 - downRatio, invVolMultiple, levPct: byCode[levCode]?.pct ?? null };
}

export function etfSectorRotation(byCode) {
  return Object.keys(ETF_SECTOR)
    .filter((c) => byCode[c] && typeof byCode[c].pct === 'number')
    .map((c) => ({ code: c, label: ETF_SECTOR[c], pct: byCode[c].pct, amount: byCode[c].amount || 0 }))
    .sort((a, b) => b.pct - a.pct);
}

// ETF_SAFE 선언 순서를 명시적으로 보존 (정수형 키는 V8이 숫자순 정렬)
const ETF_SAFE_ORDER = ['132030', '148070', '114260'];

export function etfSafeHaven(byCode, marketPct) {
  const rows = ETF_SAFE_ORDER
    .filter((c) => byCode[c] && typeof byCode[c].pct === 'number')
    .map((c) => ({ code: c, label: ETF_SAFE[c], pct: byCode[c].pct }));
  return { rows, market: marketPct };
}

export const SUPPLY_STREAK_MIN = 3;
// trend: 최신순 [{foreign, organ}] (순매수 수량). 연속 순매수 또는 전환 판정.
export function classifySupply(trend) {
  const cats = [], badges = [];
  if (!Array.isArray(trend) || trend.length === 0) return { cats, badges };
  const streak = (key) => { let n = 0; for (const r of trend) { if ((r[key] || 0) > 0) n++; else break; } return n; };
  const fb = streak('foreign'); if (fb >= SUPPLY_STREAK_MIN) { cats.push('foreign_buy'); badges.push(`외국인 ${fb}일 연속 순매수`); }
  const ib = streak('organ'); if (ib >= SUPPLY_STREAK_MIN) { cats.push('inst_buy'); badges.push(`기관 ${ib}일 연속 순매수`); }
  if (trend.length >= 2) {
    if ((trend[0].foreign || 0) > 0 && (trend[1].foreign || 0) < 0 && !cats.includes('foreign_buy')) { cats.push('foreign_buy'); badges.push('외국인 순매수 전환'); }
    if ((trend[0].organ || 0) > 0 && (trend[1].organ || 0) < 0 && !cats.includes('inst_buy')) { cats.push('inst_buy'); badges.push('기관 순매수 전환'); }
  }
  return { cats, badges };
}

export function etfLead(betting) {
  const m = betting?.invVolMultiple || 0;
  const dr = betting?.downRatio;
  if (m >= 5) {
    // 거래량(인버스 회전)은 폭증했지만 방향 베팅(거래대금 비중)이 중립권(40~60%)이면
    // 헤드라인이 '하락 대비 수요'만 단정하는 건 과장이다. 두 신호가 엇갈릴 땐 중립 톤으로 완화.
    const conflict = typeof dr === 'number' && dr >= 40 && dr <= 60;
    if (conflict) {
      return {
        title: '엇갈린 ETF 신호 · 거래량↑ 방향은 중립',
        body: `KODEX 인버스 거래량이 KODEX 200의 <b>${m}배</b>지만, 인버스·레버리지 거래대금은 <b>${dr} : ${100 - dr}</b>으로 팽팽해요. 하락 대비 수요는 늘었어도 방향을 단정하긴 일러요.`,
      };
    }
    return {
      title: '인버스 ETF 거래량 폭증 · 하락 대비 수요 확대',
      body: `KODEX 인버스 거래량이 KODEX 200의 <b>${m}배</b>예요. 급락장에서 하락 대비·저점매수·안전자산 수요가 동시에 움직였어요.`,
    };
  }
  return { title: 'ETF 시황', body: '오늘 ETF 흐름을 아래에서 나눠 봐요.' };
}
