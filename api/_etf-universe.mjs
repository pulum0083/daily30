// ETF 유니버스 상수 — 베팅(레버리지/인버스)·섹터·안전자산 분류 + 섹터 코드→한글 라벨
// codes는 네이버 polling.finance에서 등락·거래량·거래대금 조회 확인됨(2026-06-26 실측).

export const ETF_BET_DOWN = { '114800': 'KODEX 인버스', '252670': 'KODEX 200선물인버스2X' };
export const ETF_BET_UP   = { '122630': 'KODEX 레버리지' };
export const ETF_KOSPI200  = '069500'; // 인버스 거래량 배수 기준(분모)
export const ETF_SECTOR = {
  '091170': '은행', '091180': '자동차', '244580': '바이오', '139260': 'IT',
  '117700': '건설', '449450': '방산', '466920': '조선', '091230': '반도체', '305720': '2차전지',
};
export const ETF_SAFE = { '132030': '금', '148070': '국고채10년', '114260': '국고채3년' };

// 핸들러가 일괄 fetch할 전체 ETF 코드(중복 제거)
export const ALL_ETF_CODES = [
  ...Object.keys(ETF_BET_DOWN), ...Object.keys(ETF_BET_UP), ETF_KOSPI200,
  ...Object.keys(ETF_SECTOR), ...Object.keys(ETF_SAFE),
];
export const ETF_NAME = {
  ...ETF_BET_DOWN, ...ETF_BET_UP, [ETF_KOSPI200]: 'KODEX 200',
  ...Object.fromEntries(Object.entries(ETF_SECTOR).map(([c, n]) => [c, n])),
  ...ETF_SAFE,
};

// 스냅샷의 영문 섹터 코드 → 한글(섹터칩/표시용)
export const SECTOR_LABEL = {
  auto: '자동차', battery: '2차전지', bio: '바이오', defense: '방산',
  finance: '금융', power: '전력기기', semicon: '반도체', ship: '조선',
};
