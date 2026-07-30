// 하이퍼리퀴드 야간 추정가 계산 순수 로직 (앵커 환산 + 레거시 보정)
//
// [앵커 환산 — 2026-07-31 도입, 현재 방식]
// 추정가 = KRX 종가 × (HL 현재가 ÷ HL 종가시점가)
// **비율만 쓰므로 HL 합성가의 상시 프리미엄은 자동으로 상쇄된다.** 아래 레거시 보정이 풀려던
// 문제를 계산식 자체가 없애고, 진짜 야간 변동은 그대로 살린다.
//
// 왜 레거시 보정을 대체했나 (2026-07-31 실측):
// 7거래일 × 3종목 전부 **KRX 종가 시점 프리미엄이 -3.7%~+0.4%** 로 허용치(5%) 안이었다.
// 즉 "상시 5~11% 프리미엄"은 존재하지 않는다. 2026-07-30 밤에 관측된 11~12% 괴리는
// 데이터 결함이 아니라 미국 반도체 급등(SOXX +8.9%, MU +12.8%)이 만든 **진짜 야간 상승**이었다.
// 그런데 레거시 보정은 그걸 이상치로 보고 종가로 덮어써서, 위젯이 존재하는 이유인 신호를
// **큰 밤에만 골라서** 지웠다. 게다가 정적인 종가를 '지금 이시각 추정가'로 표시해
// 운영 규칙 0(라벨과 데이터 불일치)도 위반했다.

import { isKospiHoliday } from './_market-calendar.mjs';

// 비율이 이 범위를 벗어나면 계산이 아니라 데이터가 깨진 것으로 본다(하루 만에 ±50%는 비정상).
export const ANCHOR_RATIO_MIN = 0.5;
export const ANCHOR_RATIO_MAX = 2;

const KRX_CLOSE_UTC_MIN = 6 * 60 + 30; // 15:30 KST = 06:30 UTC
const DAY_MS = 24 * 60 * 60 * 1000;

/** KRX 종가에 HL의 종가 이후 변동률을 실어 지금 추정가를 만든다. 근거가 없으면 null. */
export function anchorEstimate({ hlNow, hlAtClose, krxClose }) {
  const ok = v => typeof v === 'number' && isFinite(v) && v > 0;
  if (!ok(hlNow) || !ok(hlAtClose) || !ok(krxClose)) return null;
  const ratio = hlNow / hlAtClose;
  if (ratio < ANCHOR_RATIO_MIN || ratio > ANCHOR_RATIO_MAX) return null;
  return {
    krw: Math.round(krxClose * ratio),
    changePct: Math.round((ratio - 1) * 10000) / 100, // 종가 대비 %
    anchored: true,
  };
}

/** 종가 시각 이전에 닫힌 마지막 봉. HL candleSnapshot의 T는 봉 종료 시각(ms). */
export function pickAnchorCandle(candles, closeTs) {
  if (!Array.isArray(candles) || !candles.length) return null;
  let best = null;
  for (const c of candles) {
    if (typeof c?.T === 'number' && c.T <= closeTs && (!best || c.T > best.T)) best = c;
  }
  return best;
}

/** 지금 시점에서 가장 최근에 지난 KRX 종가(15:30 KST) 시각(ms). 주말·공휴일은 건너뛴다.
 *
 * KST 달력일 D의 15:30 KST는 같은 달력일 D의 06:30 UTC다(15:30-9=06:30, 날짜 안 넘어감).
 */
export function lastKrxCloseTs(nowMs = Date.now(), isHoliday = isKospiHoliday) {
  for (let i = 0; i < 15; i++) {
    const kstShifted = new Date(nowMs + 9 * 3600 * 1000 - i * DAY_MS);
    const ymd = kstShifted.toISOString().slice(0, 10);
    const closeTs = Date.parse(ymd + 'T00:00:00Z') + KRX_CLOSE_UTC_MIN * 60 * 1000;
    if (closeTs <= nowMs && !isHoliday(kstShifted)) return closeTs;
  }
  return null;
}

// ── 레거시: 실제 종가 대비 괴리 보정 (앵커 환산 실패 시 폴백으로만 사용) ────────
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
