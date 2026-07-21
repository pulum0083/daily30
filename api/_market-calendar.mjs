// 한국 증시 개장 캘린더 — 주말·공휴일 판정 + 거래일 라벨 (scripts/holiday_check.py 2026 목록 포팅)

const HOLIDAYS = new Set([
  // 2026 (KRX 휴장)
  '2026-01-01', '2026-02-16', '2026-02-17', '2026-02-18', '2026-03-02',
  '2026-05-01', '2026-05-05', '2026-05-25', '2026-06-03', '2026-07-17',
  '2026-08-17', '2026-09-24', '2026-09-25', '2026-09-26', '2026-10-05',
  '2026-10-09', '2026-12-25', '2026-12-31',
  // 2025 말 (이전 거래일 판정 보조)
  '2025-12-25', '2025-12-31',
]);

const WD = ['일', '월', '화', '수', '목', '금', '토'];

function kstNow() { return new Date(Date.now() + 9 * 60 * 60 * 1000); }
function ymd(d) { return d.toISOString().slice(0, 10); }

// 주말 또는 공휴일이면 true (KST 기준)
export function isKospiHoliday(d) {
  const day = d.getUTCDay(); // shifted date의 UTC요일 = KST요일
  return day === 0 || day === 6 || HOLIDAYS.has(ymd(d));
}

// 지금 정규장이 열려 있는가 (평일·비휴일 09:00~15:30 KST)
export function krMarketOpen() {
  const k = kstNow();
  if (isKospiHoliday(k)) return false;
  const m = k.getUTCHours() * 60 + k.getUTCMinutes();
  return m >= 9 * 60 && m <= 15 * 60 + 30;
}

export function kstTodayYmd() { return ymd(kstNow()); }

const SESSION_OPEN = 9 * 60;        // 09:00
const SESSION_CLOSE = 15 * 60 + 30; // 15:30

// KST 자정 기준 분(min)을 받아 정규장 경과 비율 0~1을 반환한다(순수 함수, 테스트용).
// 장중 누적 거래량을 '종일 평균 거래량'과 비교할 때 분모를 이 비율로 축소해 축을 맞춘다.
export function sessionProgressAt(min) {
  if (min <= SESSION_OPEN) return 0;
  if (min >= SESSION_CLOSE) return 1;
  return (min - SESSION_OPEN) / (SESSION_CLOSE - SESSION_OPEN);
}

// 지금 시점의 정규장 경과 비율. 휴장일·장 마감 후는 1(종일 기준).
export function krSessionProgress() {
  const k = kstNow();
  if (isKospiHoliday(k)) return 1;
  return sessionProgressAt(k.getUTCHours() * 60 + k.getUTCMinutes());
}

// 'YYYY-MM-DD' → 그 날짜를 포함해 거슬러 올라간 마지막 거래일 'YYYY-MM-DD'.
// 주말·공휴일이면 직전 거래일로 보정한다(비거래일에 생성된 스냅샷 날짜 교정용).
export function lastTradingDay(s) {
  const [y, m, d] = String(s).split('-').map(Number);
  if (!y || !m || !d) return s;
  const dt = new Date(Date.UTC(y, m - 1, d));
  for (let i = 0; i < 15 && isKospiHoliday(dt); i++) {
    dt.setUTCDate(dt.getUTCDate() - 1);
  }
  return ymd(dt);
}

// 'YYYY-MM-DD' → 'M/D(요일)'  예: '2026-06-26' → '6/26(금)'
export function labelFromYmd(s) {
  const [y, m, d] = String(s).split('-').map(Number);
  if (!y || !m || !d) return '';
  const dt = new Date(Date.UTC(y, m - 1, d));
  return `${m}/${d}(${WD[dt.getUTCDay()]})`;
}
