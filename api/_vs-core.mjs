// '어제랑 비교해서' 공용 순수 함수 — 직전 거래일·날짜 고정 조회·판정·결론 문장(설계 §2·§5)
import { lastTradingDay } from './_market-calendar.mjs';

export const TH = { pctPoint: 0.3, eok: 1000 };
const WD = ['일', '월', '화', '수', '목', '금', '토'];

export function prevTradingDay(dash) {
  const [y, m, d] = dash.split('-').map(Number);
  return lastTradingDay(new Date(Date.UTC(y, m - 1, d - 1)).toISOString().slice(0, 10));
}

export function relLabel(prevDash, todayDash) {
  const gap = (Date.parse(todayDash) - Date.parse(prevDash)) / 86400000;
  if (gap === 1) return '어제';
  return '지난 ' + WD[new Date(prevDash + 'T00:00:00Z').getUTCDay()] + '요일';
}

export function withJosa(word, pair) {
  const c = word.charCodeAt(word.length - 1) - 0xac00;
  const batchim = c >= 0 && c < 11172 && c % 28 !== 0;
  return word + (batchim ? pair[1] : pair[0]);
}

// bars는 한 날짜의 1분봉(시각 오름차순). 그 시각 이하 마지막 봉만 — 다른 날짜로 폴백하지 않는다(§45)
export function atOrBefore(bars, hhmm) {
  let hit = null;
  for (const b of bars || []) {
    if (b.t <= hhmm) hit = b;
    else break;
  }
  return hit;
}

export function round2(n) { return Math.round(n * 100) / 100; }

export function pct(v, base) {
  if (typeof v !== 'number' || typeof base !== 'number' || !(base > 0)) return null;
  return round2((v / base - 1) * 100);
}

export function judge(diff, th) {
  if (diff == null || !Number.isFinite(diff)) return null;
  if (Math.abs(diff) <= th) return 'same';
  return diff > 0 ? 'strong' : 'weak';
}

export function eokText(e) {
  const a = Math.abs(e);
  return a >= 10000 ? (a / 10000).toFixed(2) + '조' : a.toLocaleString('en-US') + '억';
}

// KRX 호가 단위(2023~). 1분봉 종가에 단위에 맞지 않는 값이 섞여 화면 숫자로는 거른다(설계 §6 #6)
export function tickOk(price) {
  if (typeof price !== 'number' || !(price > 0) || !Number.isInteger(price)) return false;
  const u = price < 2000 ? 1 : price < 5000 ? 5 : price < 20000 ? 10 : price < 50000 ? 50
    : price < 200000 ? 100 : price < 500000 ? 500 : 1000;
  return price % u === 0;
}

function signedPct(n) { return (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(2); }

export function verdict({ yLabel, kospiDiff, foreignDiff }) {
  const jk = judge(kospiDiff, TH.pctPoint);
  if (!jk) return null;
  const title = jk === 'same' ? withJosa(yLabel, '와과') + ' 비슷해요'
    : '오늘이 ' + yLabel + '보다 ' + (jk === 'strong' ? '세요' : '약해요');
  let sub = jk === 'same'
    ? '코스피가 같은 시각 기준 거의 같은 자리예요(' + signedPct(kospiDiff) + '%p)'
    : '코스피가 같은 시각 기준 ' + Math.abs(kospiDiff).toFixed(2) + '%p ' + (kospiDiff > 0 ? '높아요' : '낮아요');
  const jf = judge(foreignDiff, TH.eok);
  if (jf && jf !== 'same') sub += ' · 외국인 누적 순매수는 ' + eokText(foreignDiff) + ' 원 ' + (foreignDiff > 0 ? '많아요' : '적어요');
  return { title, sub, judge: jk };
}
