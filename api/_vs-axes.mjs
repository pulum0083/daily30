// '어제랑 비교해서' 세 축(강도·주도권·누가)의 순수 계산 — 네트워크 없음
import { round2, judge, TH } from './_vs-core.mjs';

export const TH_VOL = 10;   // 거래량 "비슷해요" 임계(%)

const upto = (bars, at) => (bars || []).filter((b) => b.t <= at);

function sumVol(bars) {
  if (!bars.length) return null;
  return bars.reduce((s, b) => s + (Number(b.vol) || 0), 0);
}

function amplitude(bars, base) {
  if (!bars.length || !(base > 0)) return null;
  const hs = bars.map((b) => b.h).filter((n) => typeof n === 'number');
  const ls = bars.map((b) => b.l).filter((n) => typeof n === 'number');
  if (!hs.length || !ls.length) return null;
  return round2((Math.max(...hs) - Math.min(...ls)) / base * 100);
}

// 두 값을 받아 {t,y,diff,judge}. 한쪽이라도 없으면 diff·judge는 null(§45 — 오늘 값으로 메우지 않는다)
function pair(t, y, diff, th) {
  const d = t != null && y != null ? diff : null;
  return { t, y, diff: d, judge: d == null ? null : judge(d, th) };
}

export function heatAxis(barsT, barsY, baseT, baseY, at) {
  const T = upto(barsT, at), Y = upto(barsY, at);
  const vt = sumVol(T), vy = sumVol(Y);
  const at_ = amplitude(T, baseT), ay = amplitude(Y, baseY);
  return {
    vol: pair(vt, vy, vt != null && vy > 0 ? round2((vt / vy - 1) * 100) : null, TH_VOL),
    amp: pair(at_, ay, at_ != null && ay != null ? round2(at_ - ay) : null, TH.pctPoint),
  };
}
