// 섹터 대표 3종목 평균·순위 — 순수 계산. 종목은 stock_universe.json 각 섹터의 앞 3개와 같다.
// "섹터 평균"이 아니라 "대표 3종목 평균"이다(설계 §5 — 46종목 평균과 순위가 갈린다).
import { round2 } from './_vs-core.mjs';

export const SECTOR_REPS = [
  { key: 'semicon', label: '반도체', codes: ['005930', '000660', '042700'], names: ['삼성전자', 'SK하이닉스', '한미반도체'] },
  { key: 'power', label: '전력기기', codes: ['267260', '010120', '298040'], names: ['HD현대일렉트릭', 'LS일렉트릭', '효성중공업'] },
  { key: 'defense', label: '방산', codes: ['012450', '079550', '064350'], names: ['한화에어로스페이스', 'LIG넥스원', '현대로템'] },
  { key: 'ship', label: '조선', codes: ['329180', '042660', '010140'], names: ['HD현대중공업', '한화오션', '삼성중공업'] },
  { key: 'battery', label: '2차전지', codes: ['373220', '247540', '006400'], names: ['LG에너지솔루션', '에코프로비엠', '삼성SDI'] },
  { key: 'auto', label: '자동차', codes: ['005380', '000270', '012330'], names: ['현대차', '기아', '현대모비스'] },
  { key: 'bio', label: '바이오', codes: ['207940', '068270', '000100'], names: ['삼성바이오로직스', '셀트리온', '유한양행'] },
  { key: 'finance', label: '금융', codes: ['032830', '105560', '055550'], names: ['삼성생명', 'KB금융', '신한지주'] },
];

const mean = (a) => (a.length ? a.reduce((s, n) => s + n, 0) / a.length : null);

export function sectorRows(byCode) {
  const rows = [];
  for (const s of SECTOR_REPS) {
    const ts = s.codes.map((c) => byCode[c]?.t).filter((n) => typeof n === 'number');
    const ys = s.codes.map((c) => byCode[c]?.y).filter((n) => typeof n === 'number');
    if (!ts.length) continue;                 // 오늘 값이 없으면 그 섹터는 내보내지 않는다
    const t = mean(ts), y = ys.length ? mean(ys) : null;
    rows.push({
      key: s.key, label: s.label, names: s.names, n: ts.length,
      t: round2(t), y: y == null ? null : round2(y),
      diff: y == null ? null : round2(t - y),  // 반올림 전 값으로 뺀다
      _rawY: y,
    });
  }
  const byT = [...rows].sort((a, b) => b.t - a.t);
  const withY = rows.filter((r) => r._rawY != null).sort((a, b) => b._rawY - a._rawY);
  byT.forEach((r, i) => {
    r.rank = i + 1;
    const j = withY.findIndex((x) => x.key === r.key);
    r.prevRank = j < 0 ? null : j + 1;
    r.move = r.prevRank == null ? null : r.prevRank - r.rank;
    delete r._rawY;
  });
  return byT;
}
