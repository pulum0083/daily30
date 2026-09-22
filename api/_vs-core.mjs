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

// 오늘의 방향을 먼저 말한다 — 오르다/내리다 × 어제보다 더/덜 · 어제와 달리 · 어제처럼.
function directionTitle(y, t, yv, jk, done) {
  const up = done ? '올랐어요' : '오르고 있어요', dn = done ? '내렸어요' : '내리고 있어요';
  const verb = t > 0 ? up : t < 0 ? dn : null;
  if (!verb) return jk === 'same' ? withJosa(y, '와과') + ' 비슷해요' : '보합이에요 · ' + y + '보다 ' + (jk === 'strong' ? '세요' : '약해요');
  const sameDir = (t > 0 && yv > 0) || (t < 0 && yv < 0);
  if (jk === 'same') return sameDir ? y + '처럼 ' + verb : withJosa(y, '와과') + ' 비슷해요';
  if (!sameDir) return withJosa(y, '와과') + ' 달리 ' + verb;
  const more = (t > 0) === (jk === 'strong');   // 오르는 날엔 세면 더, 내리는 날엔 약하면 더
  if (more) return y + '보다 더 ' + verb;
  return t > 0 ? (done ? '올랐지만 ' + y + '보다 오름폭이 작았어요' : '오르고 있지만 ' + y + '보다 오름폭이 작아요')
    : (done ? '내렸지만 ' + y + '보다 낙폭이 작았어요' : '내리고 있지만 ' + y + '보다 낙폭이 작아요');
}

function signedPct(n) { return (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(2); }

// 결론 문장. "오늘이 어제보다 약해요"만 쓰면 둘 다 오른 날(오늘이 덜 오른 날)에 지수가 빠진 것으로 읽혔다
// (2026-09-22 사용자 지적) — 오늘·어제 등락률이 있으면 제목에 오늘의 방향(오르고/내리고)을 먼저 적고,
// 근거 줄에 두 값을 함께 쓴다. done이면(마감 후) 과거형으로 쓴다. 두 값이 없으면 예전 문장으로 둔다.
export function verdict({ yLabel, kospiDiff, foreignDiff, kospiT = null, kospiY = null, done = false }) {
  const jk = judge(kospiDiff, TH.pctPoint);
  if (!jk) return null;
  const both = Number.isFinite(kospiT) && Number.isFinite(kospiY);
  const title = both ? directionTitle(yLabel, kospiT, kospiY, jk, done)
    : jk === 'same' ? withJosa(yLabel, '와과') + ' 비슷해요'
      : '오늘이 ' + yLabel + '보다 ' + (jk === 'strong' ? '세요' : '약해요');
  const gap = jk === 'same' ? '거의 같은 자리예요(' + signedPct(kospiDiff) + '%p)'
    : Math.abs(kospiDiff).toFixed(2) + '%p ' + (kospiDiff > 0 ? '높아요' : '낮아요');
  let sub = both
    ? '코스피 오늘 ' + signedPct(kospiT) + '% · ' + yLabel + (done ? ' ' : ' 같은 시각 ') + signedPct(kospiY) + '% — ' + gap
    : '코스피가 같은 시각 기준 ' + gap;
  const jf = judge(foreignDiff, TH.eok);
  if (jf && jf !== 'same') sub += ' · 외국인 누적 순매수는 ' + eokText(foreignDiff) + ' 원 ' + (foreignDiff > 0 ? '많아요' : '적어요');
  // 제목 색은 오늘의 방향을 따른다 — '오르고 있지만 덜'을 파랑으로 칠하면 다시 하락으로 읽힌다.
  const tone = both ? (kospiT > 0 ? 'up' : kospiT < 0 ? 'dn' : '') : undefined;
  return tone === undefined ? { title, sub, judge: jk } : { title, sub, judge: jk, tone };
}
