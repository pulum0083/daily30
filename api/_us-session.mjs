// 미국 종목 세션 판정과 등락률 기준가 선택 — stocks-live·intraday 공용
//
// 왜 공용 모듈인가 (2026-07-30 실사고)
//   stocks-live는 프리·애프터장 기준가로 regularMarketPrice를, intraday는
//   chartPreviousClose를 각자 골라 써서 같은 종목이 홈 -1.25% / 상세 -7.35%로 갈렸다.
//   판정 로직이 두 곳에 있으면 한쪽만 고쳐진다(SERVICE_RULES §20·§30).
//
// Yahoo meta 필드의 함정
//   previousClose·chartPreviousClose는 regularMarketTime(직전 정규장 마감) 기준 "하루 전"이다.
//   정규장 중엔 그게 곧 전일 종가라 맞지만, 프리·애프터장엔 한 세션 과거가 되어 틀린다.
//   반대로 regularMarketPrice는 정규장 중엔 실시간 체결가라 기준가로 쓸 수 없다.
import { isUsMarketHoliday, nyYmd } from './_us-market-calendar.mjs';

// 현재 세션 — 'pre' | 'open' | 'post' | 'closed'
// 야후는 휴장일에도 currentTradingPeriod에 평시와 같은 세션 창을 내려주는 경우가 있어(휴일 미인지),
// 뉴욕 로컬 날짜가 휴장일이면 세션 창 판정을 무시하고 무조건 closed로 강제한다.
export function usSessionState(meta, nowSec) {
  const tp = (meta && meta.currentTradingPeriod) || {};
  const now = Math.floor(nowSec);
  if (isUsMarketHoliday(nyYmd(now * 1000))) return 'closed';
  if (tp.regular && now >= tp.regular.start && now < tp.regular.end) return 'open';
  if (tp.pre && now >= tp.pre.start && now < tp.pre.end) return 'pre';
  if (tp.post && now >= tp.post.start && now < tp.post.end) return 'post';
  return 'closed';
}

// 세션별 등락률 기준가 — 없으면 null (가짜 0% 대신 표시 생략을 택한다, 운영규칙 0)
//   pre  → regularMarketPrice = 어제 정규장 종가
//   post → regularMarketPrice = 당일 정규장 종가
//   open·closed → chartPreviousClose = 전일 종가
export function usBaseClose(meta, state) {
  const m = meta || {};
  const v = (state === 'pre' || state === 'post')
    ? m.regularMarketPrice
    : (m.chartPreviousClose ?? m.previousClose);
  return (typeof v === 'number' && isFinite(v) && v !== 0) ? v : null;
}
