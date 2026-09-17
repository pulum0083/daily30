// '어제랑 비교해서' 세 축(강도·주도권·누가)의 순수 계산 — 네트워크 없음
import { round2, judge, TH } from './_vs-core.mjs';

export const TH_VOL = 10;   // 거래량 "비슷해요" 임계(%)

const upto = (bars, at) => (bars || []).filter((b) => b.t <= at);

// 숫자 거래량을 가진 봉이 하나도 없으면 null(0이 아니다 — §0, 지어낸 "0천주" 방지).
// 일부만 결측이면 있는 것만 합산한다.
function sumVol(bars) {
  const nums = bars.map((b) => b.vol).filter((n) => typeof n === 'number');
  if (!nums.length) return null;
  return nums.reduce((s, n) => s + n, 0);
}

function amplitude(bars, base) {
  if (!bars.length || !(base > 0)) return null;
  const hs = bars.map((b) => b.h).filter((n) => typeof n === 'number');
  const ls = bars.map((b) => b.l).filter((n) => typeof n === 'number');
  if (!hs.length || !ls.length) return null;
  return (Math.max(...hs) - Math.min(...ls)) / base * 100;
}

// 두 값을 받아 {t,y,diff,judge}. 한쪽이라도 없으면 diff·judge는 null(§45 — 오늘 값으로 메우지 않는다)
function pair(t, y, diff, th) {
  const d = t != null && y != null ? diff : null;
  return { t, y, diff: d, judge: d == null ? null : judge(d, th) };
}

// 화면 표시 순서 — 금액이 큰 주체부터
export const INST_KEYS = ['금융투자', '연기금', '투신', '기타금융', '보험', '은행'];

const turned = (t, y) => (typeof t !== 'number' || typeof y !== 'number' ? null : Math.sign(t) !== Math.sign(y));

export function flowAxis(rowT, rowY) {
  if (!rowT || !rowY) return null;
  const one = (k) => ({ t: rowT[k], y: rowY[k], turned: turned(rowT[k], rowY[k]) });
  return {
    main: { 개인: one('개인'), 외국인: one('외국인'), 기관: one('기관') },
    inst: INST_KEYS.map((key) => ({
      key, t: rowT.inst?.[key] ?? null, y: rowY.inst?.[key] ?? null,
      turned: turned(rowT.inst?.[key], rowY.inst?.[key]),
    })),
  };
}

export function heatAxis(barsT, barsY, baseT, baseY, at) {
  const T = upto(barsT, at), Y = upto(barsY, at);
  const vt = sumVol(T), vy = sumVol(Y);
  const at_ = amplitude(T, baseT), ay = amplitude(Y, baseY);
  // 진폭 차이는 미반올림 값으로 계산한 후 반올림, t·y는 각각 반올림해 표시
  const ampDiff = at_ != null && ay != null ? round2(at_ - ay) : null;
  return {
    vol: pair(vt, vy, vt != null && vy > 0 ? round2((vt / vy - 1) * 100) : null, TH_VOL),
    amp: pair(at_ != null ? round2(at_) : null, ay != null ? round2(ay) : null, ampDiff, TH.pctPoint),
  };
}
