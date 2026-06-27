// 종목·ETF 신호 판정 순수 함수(네트워크 없음). 핸들러가 fetch한 데이터를 받아 가공한다.

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
