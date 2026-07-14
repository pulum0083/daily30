// 하이퍼리퀴드 합성가와 실제 KRX 가격을 비교해 과도한 괴리 시 실제 종가로 보정하는 순수 로직
// SKHX·SMSN 등 일부 종목의 HL 합성가가 실제 종가 대비 상시 5~11% 웃도는 현상 발견(2026-07-15) —
// 오라클/유동성 특성으로 추정되며 저희 변환식(usd × fx) 자체는 정상이라 원본 데이터를 못 고치므로,
// 괴리가 큰 경우 실제 종가로 대체 표시한다.
export const REAL_PRICE_TOLERANCE_PCT = 5; // 이 이상 벗어나면 HL 값 대신 실제 종가로 대체

export function reconcileWithReal(hl, real) {
  const hlKrw = hl?.krw;
  const hlChangePct = hl?.changePct;
  if (!real || !isFinite(real.price)) {
    return { krw: hlKrw ?? null, changePct: hlChangePct ?? null, adjusted: false };
  }
  const hasRealChangePct = real.changePct != null && isFinite(real.changePct);
  if (hlKrw == null || !isFinite(hlKrw)) {
    return { krw: real.price, changePct: hasRealChangePct ? real.changePct : null, adjusted: true };
  }
  const diffPct = Math.abs(hlKrw - real.price) / real.price * 100;
  if (diffPct > REAL_PRICE_TOLERANCE_PCT) {
    return {
      krw: real.price,
      changePct: hasRealChangePct ? real.changePct : hlChangePct,
      adjusted: true,
    };
  }
  return { krw: hlKrw, changePct: hlChangePct, adjusted: false };
}
