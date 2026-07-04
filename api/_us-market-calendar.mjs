// 미국 증시(NYSE/Nasdaq) 휴장 캘린더 — America/New_York 기준 날짜 판정

const HOLIDAYS = new Set([
  // 2026 (NYSE 휴장 — 대체휴일 포함)
  '2026-01-01', // New Year's Day
  '2026-01-19', // Martin Luther King Jr. Day
  '2026-02-16', // Washington's Birthday
  '2026-04-03', // Good Friday
  '2026-05-25', // Memorial Day
  '2026-06-19', // Juneteenth
  '2026-07-03', // Independence Day (7/4가 토요일 → 금요일 대체휴장)
  '2026-09-07', // Labor Day
  '2026-11-26', // Thanksgiving Day
  '2026-12-25', // Christmas Day
  // 2025 말 (이전 거래일 판정 보조)
  '2025-12-25',
]);

// 'YYYY-MM-DD'(America/New_York 날짜) 또는 Date → 그 날짜가 미국 증시 휴장일(주말 포함)인지
export function isUsMarketHoliday(input) {
  const ymd = typeof input === 'string' ? input : nyYmd(input);
  const [y, m, d] = ymd.split('-').map(Number);
  if (!y || !m || !d) return false;
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return wd === 0 || wd === 6 || HOLIDAYS.has(ymd);
}

// 임의 Date(또는 epoch ms/초)를 America/New_York 로컬 날짜 'YYYY-MM-DD'로 변환
export function nyYmd(d) {
  const date = d instanceof Date ? d : new Date(d);
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(date);
  const get = (t) => parts.find((p) => p.type === t)?.value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}

// 'YYYY-MM-DD'(NY 날짜) → 'M/D' 라벨 (요일 없이, 대시보드 뱃지용 축약)
export function nyLabelFromYmd(s) {
  const [, m, d] = String(s).split('-').map(Number);
  return `${m}/${d}`;
}
