// 종목·ETF 신호 판정 순수 함수(네트워크 없음). 핸들러가 fetch한 데이터를 받아 가공한다.

import { SECTOR_LABEL } from './_etf-universe.mjs';

export const COUNTER_TREND_OUTPERF = 3.0;
export const VOL_SURGE_MIN = 1.5;
export const CAPITULATION_DROP = -3.0;
export const TURNOVER_TOP_N = 3;
export const NEAR_HIGH_RATIO = 0.98;

const sgn = (x) => (x > 0 ? 1 : x < 0 ? -1 : 0);

// 종목 1건의 가격·거래량 신호. stock={pct,vol,vol_avg20,price,wk52_high}
export function classifyStock(stock, kospiPct) {
  const cats = [];
  const badges = [];
  const { pct, vol, vol_avg20, price, wk52_high } = stock;

  // 역행: 방향 반대 + 아웃퍼폼
  if (sgn(pct) !== sgn(kospiPct) && Math.abs(pct - kospiPct) >= COUNTER_TREND_OUTPERF) {
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
  return { signals, rank };
}
