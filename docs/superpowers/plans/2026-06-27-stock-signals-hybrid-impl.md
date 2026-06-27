# 종목 홈 신호 하이브리드 + ETF 사이드 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 홈(`web/stocks/index.html`) 하단을 좌(신호/랭킹/섹터)+우측사이드(ETF 4카드)로 재배치하고, 하드코딩 `PROTO_*`를 실측 기반 `/api/signals` 엔드포인트로 전환한다.

**Architecture:** 판정 로직을 네트워크와 분리한 순수 모듈(`api/_signals-core.mjs`)로 빼서 `node:test`로 TDD한다. 핸들러(`api/signals.mjs`)는 네이버 polling(현재가·등락·거래량) + itemSummary(거래대금) + 일봉 스냅샷(`vol_avg20`·`wk52_high`)을 조합해 순수 모듈에 넘기고 JSON을 반환한다. 프런트는 그 JSON으로 렌더한다. 장중(`phase:intraday`)엔 가격·거래량 신호만, 마감(`phase:closed`)엔 수급 신호까지 합류한다.

**Tech Stack:** Vercel serverless (ESM `.mjs`), Node 내장 `node:test`/`node:assert`(무의존성), 바닐라 JS 프런트.

**참고 스펙:** [하이브리드 아키텍처](../specs/2026-06-27-stock-signals-realtime-hybrid.md) · [색 절제](../specs/2026-06-27-stock-home-signals-color-design.md) · [신호 규칙](../specs/2026-06-27-stock-home-signals-rules.md). 프로토타입: [ETF 사이드](../../prototypes/2026-06-27-stock-etf-sidebar.html).

---

## 파일 구조

| 파일 | 책임 | 신규/수정 |
| --- | --- | --- |
| `api/_etf-universe.mjs` | ETF 유니버스 상수(베팅/섹터/안전자산) + 섹터 코드→한글 라벨 | 신규 |
| `api/_signals-core.mjs` | 순수 판정 함수(네트워크 없음): 종목 신호 분류·랭킹·ETF 4카드 가공 | 신규 |
| `api/_signals-core.test.mjs` | 위 순수 함수 단위 테스트(`node:test`) | 신규 |
| `api/signals.mjs` | 핸들러: fetch 조합 → core 호출 → JSON 반환 | 신규 |
| `web/stocks/index.html` | 레이아웃 재배치 + `PROTO_*` → `/api/signals` 전환 + phase 라벨 | 수정 |

**임계 상수(규칙 스펙과 동일, `_signals-core.mjs` 상단 한 곳):**
```
COUNTER_TREND_OUTPERF = 3.0   // %p
VOL_SURGE_MIN         = 1.5
CAPITULATION_DROP     = -3.0  // %
TURNOVER_TOP_N        = 3
NEAR_HIGH_RATIO       = 0.98
```

**스코프 경계:** 본 계획은 **장중 실시간 신호(역행·거래대금·신고가·투매 거래량) + ETF 4카드 + 레이아웃 + phase 라벨**까지 구현해 동작하는 소프트웨어를 만든다. **마감판 종목별 수급 신호(외국인/기관 연속·전환)는 Task 9에서 추가**한다(`trend` 다일자 fetch + streak/transition). Task 9가 미뤄져도 Task 1~8만으로 장중판은 완전히 동작한다.

---

### Task 1: ETF 유니버스 상수 모듈

**Files:**
- Create: `api/_etf-universe.mjs`

- [ ] **Step 1: 모듈 작성**

```javascript
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

// 스냅샷의 영문 섹터 코드 → 한글(섹터칩/표시용)
export const SECTOR_LABEL = {
  auto: '자동차', battery: '2차전지', bio: '바이오', defense: '방산',
  finance: '금융', power: '전력기기', semicon: '반도체', ship: '조선',
};

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
```

- [ ] **Step 2: import 확인**

Run: `node -e "import('./api/_etf-universe.mjs').then(m=>console.log(m.ALL_ETF_CODES.length, m.SECTOR_LABEL.semicon))"`
Expected: `15 반도체` (베팅 3 + 섹터 9 + 안전 3 = 15, 중복 없음)

- [ ] **Step 3: Commit**

```bash
git add api/_etf-universe.mjs
git commit -m "feat(종목): ETF 유니버스 상수 모듈 — 베팅·섹터·안전자산 + 섹터 라벨"
```

---

### Task 2: 코어 — 종목 신호 분류 (per-stock)

**Files:**
- Create: `api/_signals-core.mjs`
- Test: `api/_signals-core.test.mjs`

종목 1건의 가격·거래량 기반 신호를 분류한다. 거래대금 쏠림(turnover)은 종목 간 랭킹이라 Task 3에서 별도 처리.

- [ ] **Step 1: 실패 테스트 작성**

```javascript
// api/_signals-core.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { classifyStock } from './_signals-core.mjs';

test('역행: 시장 -5.8%인데 종목 +1.7% → counter_up', () => {
  const s = { pct: 1.7, vol: 100, vol_avg20: 100, price: 100, wk52_high: 200 };
  const r = classifyStock(s, -5.8);
  assert.ok(r.cats.includes('counter_up'));
});

test('투매: 거래량 3.2배 + -8.4% → vol_surge', () => {
  const s = { pct: -8.4, vol: 320, vol_avg20: 100, price: 100, wk52_high: 200 };
  const r = classifyStock(s, -5.8);
  assert.ok(r.cats.includes('vol_surge'));
  assert.ok(r.badges.some(b => b.includes('거래량') && b.includes('3.2')));
});

test('신고가: 현재가가 52주고가 99% → near_high', () => {
  const s = { pct: 0.3, vol: 100, vol_avg20: 100, price: 99, wk52_high: 100 };
  const r = classifyStock(s, -5.8);
  assert.ok(r.cats.includes('near_high'));
});

test('아무 신호 없으면 빈 cats', () => {
  const s = { pct: -5.0, vol: 100, vol_avg20: 100, price: 50, wk52_high: 200 };
  const r = classifyStock(s, -5.8);
  assert.deepEqual(r.cats, []);
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test api/_signals-core.test.mjs`
Expected: FAIL — `Cannot find module './_signals-core.mjs'` 또는 `classifyStock is not a function`

- [ ] **Step 3: 최소 구현**

```javascript
// api/_signals-core.mjs
// 종목·ETF 신호 판정 순수 함수(네트워크 없음). 핸들러가 fetch한 데이터를 받아 가공한다.

export const COUNTER_TREND_OUTPERF = 3.0;
export const VOL_SURGE_MIN = 1.5;
export const CAPITULATION_DROP = -3.0;
export const TURNOVER_TOP_N = 3;
export const NEAR_HIGH_RATIO = 0.98;

const sgn = (x) => (x > 0 ? 1 : x < 0 ? -1 : 0);

// 종목 1건의 가격·거래량 신호. stock={pct,vol,vol_avg20,price,wk52_high}
export function classifyStock(stock, kospiPct) {
  const cats = [];
  const badges = [];
  const { pct, vol, vol_avg20, price, wk52_high } = stock;

  // 역행: 방향 반대 + 아웃퍼폼
  if (sgn(pct) !== sgn(kospiPct) && Math.abs(pct - kospiPct) >= COUNTER_TREND_OUTPERF) {
    cats.push('counter_up');
    badges.push('역행 상승');
  }
  // 투매(거래량 부분): 급증 + 급락
  const mult = vol_avg20 > 0 ? vol / vol_avg20 : 0;
  if (mult >= VOL_SURGE_MIN && pct <= CAPITULATION_DROP) {
    cats.push('vol_surge');
    badges.push(`거래량 ×${mult.toFixed(1)} 급증`);
  }
  // 신고가 근접
  if (wk52_high > 0 && price >= wk52_high * NEAR_HIGH_RATIO) {
    cats.push('near_high');
    const gap = Math.round((1 - price / wk52_high) * 100);
    badges.push(`52주 신고가 ${gap}%↓`);
  }
  return { cats, badges };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test api/_signals-core.test.mjs`
Expected: PASS — 4 tests

- [ ] **Step 5: Commit**

```bash
git add api/_signals-core.mjs api/_signals-core.test.mjs
git commit -m "feat(종목): 신호 코어 — 종목 가격·거래량 신호 분류(역행·투매·신고가)"
```

---

### Task 3: 코어 — 거래대금 쏠림 + 신호 묶음/랭킹

**Files:**
- Modify: `api/_signals-core.mjs`
- Modify: `api/_signals-core.test.mjs`

- [ ] **Step 1: 실패 테스트 추가**

```javascript
// api/_signals-core.test.mjs 에 추가
import { buildSignals } from './_signals-core.mjs';

test('거래대금 상위 3종목에 turnover cat', () => {
  const stocks = [
    { code: '1', name: 'A', sector: 'semicon', pct: -2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 500 },
    { code: '2', name: 'B', sector: 'semicon', pct: -2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 400 },
    { code: '3', name: 'C', sector: 'auto', pct: -2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 300 },
    { code: '4', name: 'D', sector: 'auto', pct: -2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 10 },
  ];
  const { signals } = buildSignals(stocks, -5.8);
  const a = signals.find(s => s.code === '1');
  assert.ok(a.cats.includes('turnover'));
  const d = signals.find(s => s.code === '4');
  assert.ok(!d || !d.cats.includes('turnover'));
});

test('신호 없는 종목은 signals에서 제외', () => {
  const stocks = [
    { code: '9', name: 'Z', sector: 'bio', pct: -5.0, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 1 },
  ];
  const { signals } = buildSignals(stocks, -5.8);
  assert.equal(signals.length, 0);
});

test('랭킹은 신호별 그룹 + 종목수 내림차순', () => {
  const stocks = [
    { code: '1', name: 'A', sector: 'semicon', pct: 1.7, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 5 },
    { code: '2', name: 'B', sector: 'semicon', pct: 1.2, vol: 1, vol_avg20: 1, price: 1, wk52_high: 99, amount: 4 },
  ];
  const { rank } = buildSignals(stocks, -5.8); // 둘 다 counter_up
  const cu = rank.find(g => g.cat === 'counter_up');
  assert.equal(cu.items.length, 2);
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test api/_signals-core.test.mjs`
Expected: FAIL — `buildSignals is not a function`

- [ ] **Step 3: 구현 추가**

```javascript
// api/_signals-core.mjs 에 추가
import { SECTOR_LABEL } from './_etf-universe.mjs';

// 신호별 한 줄 설명 생성
function whyText(stock) {
  const { pct, cats } = stock;
  if (cats.includes('counter_up')) return `시장이 하락하는 동안 <b>${pct >= 0 ? '+' : ''}${pct.toFixed(1)}% ${pct >= 0 ? '상승' : '선방'}</b>했어요.`;
  if (cats.includes('vol_surge')) return `거래량이 급증하며 ${pct.toFixed(1)}% 급락했어요.`;
  if (cats.includes('near_high')) return `폭락장에도 <b>52주 신고가</b>에 근접했어요.`;
  if (cats.includes('turnover')) return `거래대금 상위. 지수에 큰 영향을 줬어요.`;
  return '';
}

// 신호 카테고리 메타(랭킹 라벨·아이콘) — 색 없음(색 절제 규칙)
export const SIGNAL_META = {
  vol_surge:  { ic: '🔥', label: '거래량 급증' },
  counter_up: { ic: '↗',  label: '역행 상승' },
  near_high:  { ic: '▲',  label: '52주 신고가 근접' },
  turnover:   { ic: '💰', label: '거래대금 상위' },
  inst_buy:   { ic: '🏛️', label: '기관 순매수' },     // Task 9
  foreign_buy:{ ic: '🌏', label: '외국인 순매수' },     // Task 9
  foreign_sell:{ ic: '🌏', label: '외국인 순매도' },    // Task 9
};

// stocks: [{code,name,sector,pct,vol,vol_avg20,price,wk52_high,amount}], 코어가 cats/badges 주입
export function buildSignals(stocks, kospiPct, opts = {}) {
  const enrich = opts.enrich; // Task 9에서 수급 cats 주입용 (stock)=>({cats,badges})
  // 1) per-stock 분류
  const classified = stocks.map((s) => {
    const r = classifyStock(s, kospiPct);
    const cats = [...r.cats];
    const badges = [...r.badges];
    if (enrich) { const e = enrich(s); cats.push(...e.cats); badges.push(...e.badges); }
    return { ...s, cats, badges };
  });
  // 2) 거래대금 쏠림: 상위 N
  [...classified].sort((a, b) => (b.amount || 0) - (a.amount || 0)).slice(0, TURNOVER_TOP_N)
    .forEach((s) => { if (!s.cats.includes('turnover')) { s.cats.push('turnover'); s.badges.push('거래대금 상위'); } });
  // 3) 신호 있는 종목만
  const signals = classified.filter((s) => s.cats.length > 0).map((s) => ({
    code: s.code, name: s.name, sector: SECTOR_LABEL[s.sector] || s.sector,
    pct: s.pct, dir: s.pct >= 0 ? 'up' : 'dn', cats: s.cats, badges: s.badges, why: whyText(s),
  }));
  // 4) 랭킹: 카테고리별 묶음, 종목수 내림차순(동수면 META 선언 순)
  const order = Object.keys(SIGNAL_META);
  const groups = {};
  signals.forEach((s) => s.cats.forEach((c) => { (groups[c] = groups[c] || []).push(s); }));
  const rank = Object.keys(groups)
    .sort((a, b) => groups[b].length - groups[a].length || order.indexOf(a) - order.indexOf(b))
    .slice(0, 5)
    .map((cat) => ({ cat, ...SIGNAL_META[cat], items: groups[cat] }));
  return { signals, rank };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test api/_signals-core.test.mjs`
Expected: PASS — 7 tests

- [ ] **Step 5: Commit**

```bash
git add api/_signals-core.mjs api/_signals-core.test.mjs
git commit -m "feat(종목): 신호 코어 — 거래대금 쏠림 + 신호별 그룹·랭킹"
```

---

### Task 4: 코어 — ETF 베팅 흐름

**Files:**
- Modify: `api/_signals-core.mjs`
- Modify: `api/_signals-core.test.mjs`

- [ ] **Step 1: 실패 테스트 추가**

```javascript
import { etfBettingFlow } from './_signals-core.mjs';

test('베팅 흐름: 인버스류 거래대금 합산 vs 레버리지 + 인버스 거래량 배수', () => {
  const byCode = {
    '114800': { amount: 1122000, vol: 1239929374, pct: 6.08 }, // 인버스(백만)
    '252670': { amount: 1183000, vol: 17149039548, pct: 11.29 }, // 인버스2X
    '122630': { amount: 3163000, vol: 15796886, pct: -12.04 }, // 레버리지
    '069500': { amount: 3677000, vol: 26711323, pct: -5.79 }, // KODEX200(분모)
  };
  const r = etfBettingFlow(byCode);
  assert.equal(r.downAmt, 2305000);
  assert.equal(r.upAmt, 3163000);
  assert.equal(r.downRatio, 42); // 2305/(2305+3163) = 42.2 → 42
  assert.equal(r.levPct, -12.04);
  assert.ok(r.invVolMultiple >= 45 && r.invVolMultiple <= 47); // 12.4억/0.267억 ≈ 46
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test api/_signals-core.test.mjs`
Expected: FAIL — `etfBettingFlow is not a function`

- [ ] **Step 3: 구현 추가**

```javascript
import { ETF_BET_DOWN, ETF_BET_UP, ETF_KOSPI200 } from './_etf-universe.mjs';

// byCode: { code: {amount, vol, pct} } — amount는 거래대금(백만)
export function etfBettingFlow(byCode) {
  const sum = (codes, f) => codes.reduce((a, c) => a + (byCode[c]?.[f] || 0), 0);
  const downAmt = sum(Object.keys(ETF_BET_DOWN), 'amount');
  const upAmt = sum(Object.keys(ETF_BET_UP), 'amount');
  const total = downAmt + upAmt;
  const downRatio = total > 0 ? Math.round((downAmt / total) * 100) : 0;
  const invCode = Object.keys(ETF_BET_DOWN)[0]; // 114800 KODEX 인버스
  const invVol = byCode[invCode]?.vol || 0;
  const refVol = byCode[ETF_KOSPI200]?.vol || 0;
  const invVolMultiple = refVol > 0 ? Math.round(invVol / refVol) : 0;
  const levCode = Object.keys(ETF_BET_UP)[0];
  return { downAmt, upAmt, downRatio, upRatio: 100 - downRatio, invVolMultiple, levPct: byCode[levCode]?.pct ?? null };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test api/_signals-core.test.mjs`
Expected: PASS — 8 tests

- [ ] **Step 5: Commit**

```bash
git add api/_signals-core.mjs api/_signals-core.test.mjs
git commit -m "feat(종목): 신호 코어 — ETF 베팅 흐름(인버스류 vs 레버리지 거래대금·거래량 배수)"
```

---

### Task 5: 코어 — 섹터 로테이션 + 안전자산 + 리드 헤드라인

**Files:**
- Modify: `api/_signals-core.mjs`
- Modify: `api/_signals-core.test.mjs`

- [ ] **Step 1: 실패 테스트 추가**

```javascript
import { etfSectorRotation, etfSafeHaven, etfLead } from './_signals-core.mjs';

test('섹터 로테이션: 등락률 내림차순', () => {
  const byCode = { '091170': { pct: -3.15, amount: 16000 }, '139260': { pct: -6.22, amount: 534000 }, '449450': { pct: -6.29, amount: 40000 } };
  const r = etfSectorRotation(byCode);
  assert.equal(r[0].label, '은행');       // 가장 덜 빠짐
  assert.equal(r[r.length - 1].label, '방산'); // 가장 약세
});

test('안전자산: 금·채권 + 시장 대비 행', () => {
  const byCode = { '132030': { pct: 0.91 }, '148070': { pct: 0.14 }, '114260': { pct: 0.09 } };
  const r = etfSafeHaven(byCode, -5.79);
  assert.equal(r.market, -5.79);
  assert.equal(r.rows[0].label, '금');
});

test('리드 헤드라인: 인버스 거래량 배수 크면 인버스 헤드라인', () => {
  const lead = etfLead({ invVolMultiple: 46 });
  assert.ok(lead.title.includes('인버스'));
  assert.ok(lead.body.includes('46'));
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `node --test api/_signals-core.test.mjs`
Expected: FAIL — `etfSectorRotation is not a function`

- [ ] **Step 3: 구현 추가**

```javascript
import { ETF_SECTOR, ETF_SAFE } from './_etf-universe.mjs';

export function etfSectorRotation(byCode) {
  return Object.keys(ETF_SECTOR)
    .filter((c) => byCode[c] && typeof byCode[c].pct === 'number')
    .map((c) => ({ code: c, label: ETF_SECTOR[c], pct: byCode[c].pct, amount: byCode[c].amount || 0 }))
    .sort((a, b) => b.pct - a.pct);
}

export function etfSafeHaven(byCode, marketPct) {
  const rows = Object.keys(ETF_SAFE)
    .filter((c) => byCode[c] && typeof byCode[c].pct === 'number')
    .map((c) => ({ code: c, label: ETF_SAFE[c], pct: byCode[c].pct }));
  return { rows, market: marketPct };
}

export function etfLead(betting) {
  const m = betting?.invVolMultiple || 0;
  if (m >= 5) {
    return {
      title: '인버스 ETF 거래량 폭증 · 하락 대비 수요 확대',
      body: `KODEX 인버스 거래량이 KODEX 200의 <b>${m}배</b>예요. 급락장에서 하락 대비·저점매수·안전자산 수요가 동시에 움직였어요.`,
    };
  }
  return { title: 'ETF 시황', body: '오늘 ETF 흐름을 아래에서 나눠 봐요.' };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test api/_signals-core.test.mjs`
Expected: PASS — 11 tests

- [ ] **Step 5: Commit**

```bash
git add api/_signals-core.mjs api/_signals-core.test.mjs
git commit -m "feat(종목): 신호 코어 — 섹터 로테이션·안전자산·리드 헤드라인"
```

---

### Task 6: 핸들러 `api/signals.mjs`

**Files:**
- Create: `api/signals.mjs`

기존 `api/vol-top.mjs`의 fetch 패턴(네이버 polling 병렬, `krMarketOpen`)을 따른다. 거래대금은 `itemSummary.naver`에서 별도 조회.

- [ ] **Step 1: 핸들러 작성**

```javascript
// 종목·ETF 신호 통합 API — polling(가격·등락·거래량) + itemSummary(거래대금) + 일봉 스냅샷 조합 → 코어 가공
import { ALL_ETF_CODES, ETF_NAME } from './_etf-universe.mjs';
import { buildSignals, etfBettingFlow, etfSectorRotation, etfSafeHaven, etfLead, SIGNAL_META } from './_signals-core.mjs';

const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };

function krMarketOpen() {
  const m = ((new Date().getUTCHours() * 60 + new Date().getUTCMinutes()) + 9 * 60) % (24 * 60);
  return m >= 9 * 60 && m <= 15 * 60 + 30;
}

async function pollOne(code) {
  try {
    const r = await fetch(`https://polling.finance.naver.com/api/realtime/domestic/stock/${code}`, { headers: HDR, signal: AbortSignal.timeout(6000) });
    if (!r.ok) return null;
    const it = (await r.json())?.datas?.[0];
    if (!it) return null;
    return {
      code,
      pct: parseFloat(String(it.fluctuationsRatioRaw || '0').replace(/,/g, '')) || 0,
      vol: parseInt(String(it.accumulatedTradingVolumeRaw || '0').replace(/,/g, ''), 10) || 0,
      price: parseFloat(String(it.closePriceRaw || '0').replace(/,/g, '')) || 0,
    };
  } catch { return null; }
}

async function amountOne(code) {
  try {
    const r = await fetch(`https://api.finance.naver.com/service/itemSummary.naver?itemcode=${code}`, { headers: HDR, signal: AbortSignal.timeout(6000) });
    if (!r.ok) return 0;
    const d = await r.json();
    return Number(d.amount) || 0; // 거래대금(백만)
  } catch { return 0; }
}

async function loadSnapshot() {
  // 정적 스냅샷(vol_avg20·wk52_high·name·sector). 배포 환경에선 같은 도메인 정적 경로.
  try {
    const base = process.env.SNAPSHOT_BASE || 'https://doubleshot.space';
    const r = await fetch(`${base}/data/stocks-snapshot.json`, { signal: AbortSignal.timeout(6000) });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

async function kospiPct() {
  try {
    const r = await fetch('https://doubleshot.space/api/kospi-live', { signal: AbortSignal.timeout(6000) });
    const d = r.ok ? await r.json() : null;
    return Number(d?.changePct) || 0;
  } catch { return 0; }
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const snap = await loadSnapshot();
    if (!snap || !snap.stocks) return res.status(502).json({ error: 'snapshot unavailable' });
    const stockCodes = Object.keys(snap.stocks);

    const [stockPolls, stockAmts, etfPolls, etfAmts, kPct] = await Promise.all([
      Promise.all(stockCodes.map(pollOne)),
      Promise.all(stockCodes.map(amountOne)),
      Promise.all(ALL_ETF_CODES.map(pollOne)),
      Promise.all(ALL_ETF_CODES.map(amountOne)),
      kospiPct(),
    ]);

    // 종목 병합(실측 가격·거래량·거래대금 + 스냅샷 분모)
    const stocks = stockCodes.map((code, i) => {
      const p = stockPolls[i]; const s = snap.stocks[code];
      if (!p || !s) return null;
      return { code, name: s.name, sector: s.sector, pct: p.pct, vol: p.vol, price: p.price,
               vol_avg20: s.vol_avg20 || 0, wk52_high: s.wk52_high || 0, amount: stockAmts[i] || 0 };
    }).filter(Boolean);

    const { signals, rank } = buildSignals(stocks, kPct);

    // ETF byCode 조립
    const byCode = {};
    ALL_ETF_CODES.forEach((code, i) => {
      const p = etfPolls[i];
      if (p) byCode[code] = { pct: p.pct, vol: p.vol, amount: etfAmts[i] || 0, name: ETF_NAME[code] };
    });
    const betting = etfBettingFlow(byCode);
    const etf = {
      lead: etfLead(betting),
      betting,
      sector: etfSectorRotation(byCode),
      safeHaven: etfSafeHaven(byCode, byCode['069500']?.pct ?? kPct),
    };

    return res.status(200).json({
      phase: krMarketOpen() ? 'intraday' : 'closed',
      signals, rank, etf, meta: SIGNAL_META, updatedAt: new Date().toISOString(),
    });
  } catch (e) {
    return res.status(502).json({ error: String(e) });
  }
}
```

- [ ] **Step 2: 코어 로직 단위 테스트 재확인(회귀)**

Run: `node --test api/_signals-core.test.mjs`
Expected: PASS — 11 tests (핸들러 추가가 코어를 깨지 않았는지)

- [ ] **Step 3: 로컬 실행 점검**

Run: `vercel dev --listen 3000 --yes` 백그라운드 기동 후 `node -e "fetch('http://localhost:3000/api/signals').then(r=>r.json()).then(d=>console.log(d.phase, 'signals:', d.signals.length, 'etf.sector:', d.etf.sector.length, 'downRatio:', d.etf.betting.downRatio))"`
Expected: `closed signals: N etf.sector: 9 downRatio: <0~100>` (토요일이면 phase=closed, signals N≥0)

> 주의: `itemSummary`/`kospi-live`/스냅샷은 실서비스 도메인을 fetch한다. 로컬에서 막히면 `SNAPSHOT_BASE`로 우회하거나 배포 후 점검.

- [ ] **Step 4: Commit**

```bash
git add api/signals.mjs
git commit -m "feat(종목): /api/signals 핸들러 — polling+거래대금+스냅샷 조합, phase 분기"
```

---

### Task 7: 프런트 — 레이아웃 재배치

**Files:**
- Modify: `web/stocks/index.html` (신호별 랭킹/섹터칩 마크업을 좌측으로, ETF 영역을 우측 사이드 4카드 골격으로)

> ⚠️ 라이브 파일. 재배치 전 `git diff` 확인. 색 절제([색 스펙](../specs/2026-06-27-stock-home-signals-color-design.md))는 이미 적용돼 있으니 유지.

- [ ] **Step 1: 현재 홈 영역 구조 확인**

Run: `grep -n 'home-main\|home-side\|sig-rank-rows\|sector-chips\|etf-signal-block\|sig-rows' web/stocks/index.html`
좌(`home-main`)에 `오늘의 특이 신호`(sig-rows) + `신호별 랭킹`(sig-rank-rows) + `섹터별 보기`(sector-chips) 순으로, 우(`home-side`)에 ETF 4카드 컨테이너가 오도록 마크업을 옮긴다.

- [ ] **Step 2: 마크업 재배치**

`home-side`의 ETF 영역을 프로토타입 [2026-06-27-stock-etf-sidebar.html](../../prototypes/2026-06-27-stock-etf-sidebar.html)의 4카드 골격(빈 컨테이너 + id)으로 교체한다.

```html
<!-- web/stocks/index.html — home-side 내부 -->
<div class="block"><div class="block__h"><span class="block__t"><span class="ic">📊</span>ETF로 읽는 시황</span><span class="block__s"><span class="upd-badge" id="etf-upd-badge"></span></span></div>
  <div class="etf-head" id="etf-lead" style="margin-bottom:14px;"></div></div>
<div class="block"><div class="block__h"><span class="block__t"><span class="ic">⚖️</span>ETF 베팅 흐름</span></div><div class="gauge-wrap" id="etf-betting"></div></div>
<div class="block"><div class="block__h"><span class="block__t"><span class="ic">🔁</span>섹터 로테이션</span></div><div id="etf-sector"></div></div>
<div class="block"><div class="block__h"><span class="block__t"><span class="ic">🛟</span>안전자산 선호도</span><span class="block__s"></span></div><div id="etf-safehaven"></div></div>
```

신호별 랭킹(`sig-rank-rows` 포함 block)과 섹터칩 block 마크업을 `home-main` 안 `오늘의 특이 신호` 아래로 이동한다. 프로토타입의 카드 CSS(`.etf-head`,`.bet-split`,`.etf-row`,`.sh-row` 등)를 `web/assets/style.css` 또는 인라인 `<style>`에 추가한다(프로토타입에서 복사).

- [ ] **Step 3: 시각 확인 (preview)**

preview_start(daily30-web) → `/stocks/` → preview_screenshot. 좌측에 특이신호→랭킹→섹터칩, 우측에 ETF 4카드(빈 상태)가 보이는지 확인.

- [ ] **Step 4: Commit**

```bash
git add web/stocks/index.html web/assets/style.css
git commit -m "feat(종목): 홈 레이아웃 재배치 — 좌(신호·랭킹·섹터)+우측사이드 ETF 4카드 골격"
```

---

### Task 8: 프런트 — `/api/signals` 배선 + phase 라벨

**Files:**
- Modify: `web/stocks/index.html` (`renderSignals`/`renderSignalRank`/`renderEtfSignal`을 fetch 기반으로)

- [ ] **Step 1: PROTO_* 제거 + fetch 배선**

`web/stocks/index.html`의 `PROTO_SIGNALS`/`PROTO_ETF_SIGNAL`/`SIGNAL_META` 하드코딩과 `renderSignals()`/`renderSignalRank()`/`renderEtfSignal()` 직접호출을 `/api/signals` fetch 결과로 그리도록 교체한다.

```javascript
// web/stocks/index.html — 기존 renderSignals/renderSignalRank/renderEtfSignal 호출부 대체
function badgeHtml(b){return '<span class="bdg">'+b+'</span>';}
function applySignals(d){
  var phase=d.phase; var lab=phase==='intraday'?'<span class="dot"></span>장중 실시간':'장 마감 기준';
  var ub=document.getElementById('sig-upd-badge'); if(ub){ub.className=phase==='intraday'?'upd-badge':'close-pill';ub.innerHTML=lab;}
  // 특이 신호
  var w=document.getElementById('sig-rows');
  if(w) w.innerHTML=d.signals.map(function(s){
    var lc=s.dir==='up'?'var(--up)':'var(--dn)', sign=s.pct>=0?'+':'';
    return '<a class="sig" style="border-left:3px solid '+lc+';" onclick="goStock(\''+s.code+'\')">'
      +'<div class="sig-top"><span class="sig-nm">'+s.name+' <small>'+s.code+' · '+s.sector+'</small></span>'
      +'<span class="sig-pct" style="color:'+lc+';">'+sign+s.pct.toFixed(1)+'%</span></div>'
      +'<div class="sig-badges">'+s.badges.map(badgeHtml).join('')+'</div>'
      +'<div class="sig-why">'+s.why+'</div></a>';
  }).join('');
  // 신호별 랭킹
  var rw=document.getElementById('sig-rank-rows');
  if(rw) rw.innerHTML=d.rank.map(function(g){
    var rows=g.items.map(function(s){var pc=s.dir==='up'?'var(--up)':'var(--dn)',sg=s.pct>=0?'+':'';
      return '<a class="srk-row" onclick="goStock(\''+s.code+'\')"><span class="srk-nm">'+s.name+'</span><span class="srk-pct" style="color:'+pc+';">'+sg+s.pct.toFixed(1)+'%</span></a>';}).join('');
    return '<div class="srk-grp"><div class="srk-hd"><span class="srk-ic">'+g.ic+'</span><span class="srk-lb">'+g.label+'</span><span class="srk-cnt">'+g.items.length+'</span></div>'+rows+'</div>';
  }).join('');
}
fetch('/api/signals',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).then(function(d){ if(d) { applySignals(d); applyEtf(d.etf,d.phase); } }).catch(function(){});
```

- [ ] **Step 2: 시각 확인 (preview)**

preview reload → screenshot. 특이신호·랭킹이 `/api/signals` 데이터로 채워지고, phase 라벨(`장중 실시간`/`장 마감 기준`)이 맞게 뜨는지.

- [ ] **Step 3: Commit**

```bash
git add web/stocks/index.html
git commit -m "feat(종목): 특이신호·신호별랭킹 /api/signals 배선 + phase 라벨"
```

---

### Task 9: 프런트 — ETF 4카드 렌더 + (마감판) 수급 신호

**Files:**
- Modify: `web/stocks/index.html` (`applyEtf` 함수)
- Modify: `api/signals.mjs` (closed phase 수급 enrich)
- Modify: `api/_signals-core.mjs` (수급 분류 함수) + test

- [ ] **Step 1: ETF 4카드 렌더 함수**

```javascript
// web/stocks/index.html
function applyEtf(etf, phase){
  var lab=phase==='intraday'?'<span class="dot"></span>장중 실시간':'장 마감 기준';
  document.querySelectorAll('#etf-upd-badge').forEach(function(b){b.innerHTML=lab;});
  // ⓪ 리드
  var lead=document.getElementById('etf-lead');
  if(lead&&etf.lead) lead.innerHTML='<div class="etf-head-t">'+etf.lead.title+'</div><div class="etf-head-b">'+etf.lead.body+'</div>';
  // ① 베팅 흐름
  var b=etf.betting, bw=document.getElementById('etf-betting');
  if(bw&&b) bw.innerHTML='<div class="bet-label">레버리지·인버스 ETF 거래대금</div>'
    +'<div class="bet-split"><div class="bet-dn" style="width:'+b.downRatio+'%">하락 베팅 '+b.downRatio+'%</div><div class="bet-up" style="width:'+b.upRatio+'%">저점매수 '+b.upRatio+'%</div></div>'
    +'<div class="bet-fact"><div class="bet-fact-row"><span>인버스 거래량</span><b>KODEX 200의 '+b.invVolMultiple+'배</b></div>'
    +'<div class="bet-fact-row"><span>레버리지 등락률</span><b style="color:var(--dn)">'+(b.levPct!=null?b.levPct.toFixed(2)+'%':'—')+'</b></div></div>'
    +'<div class="gauge-note">거래<b>대금</b>과 거래<b>량</b> 신호가 엇갈려 한쪽으로 단정하긴 일러요.</div>';
  // ② 섹터 로테이션
  var sw=document.getElementById('etf-sector');
  if(sw){var top=etf.sector.slice(0,3),bot=etf.sector.slice(-3);
    var row=function(x){var c=x.pct>=0?'var(--up)':'var(--dn)',sg=x.pct>=0?'+':'';return '<div class="etf-row"><span class="etf-nm">'+x.label+'</span><span class="etf-pct" style="color:'+c+'">'+sg+x.pct.toFixed(2)+'%</span></div>';};
    sw.innerHTML='<div class="sec-divider">상대 선방 ▲</div>'+top.map(row).join('')+'<div class="sec-divider">상대 약세 ▼</div>'+bot.map(row).join('');}
  // ③ 안전자산
  var hw=document.getElementById('etf-safehaven');
  if(hw&&etf.safeHaven){var rs=etf.safeHaven.rows.map(function(x){var c=x.pct>=0?'var(--up)':'var(--dn)',sg=x.pct>=0?'+':'';
    return '<div class="sh-row"><span class="sh-nm">'+x.label+'</span><span class="sh-pct" style="color:'+c+'">'+sg+x.pct.toFixed(2)+'%</span></div>';}).join('');
    var m=etf.safeHaven.market,mc=m>=0?'var(--up)':'var(--dn)',ms=m>=0?'+':'';
    hw.innerHTML=rs+'<div class="sh-row"><span class="sh-nm">코스피200 (주식)</span><span class="sh-pct" style="color:'+mc+'">'+ms+m.toFixed(2)+'%</span></div>';}
}
```

- [ ] **Step 2: 수급 분류 함수 + 테스트 (코어)**

```javascript
// api/_signals-core.test.mjs 추가
import { classifySupply } from './_signals-core.mjs';
test('수급: 외국인 3일 연속 순매수 → foreign_buy', () => {
  const trend = [{ foreign: 100 }, { foreign: 50 }, { foreign: 30 }]; // 최신순
  const r = classifySupply(trend);
  assert.ok(r.cats.includes('foreign_buy'));
});
test('수급: 기관 전일 매도→당일 매수 전환', () => {
  const trend = [{ organ: 100 }, { organ: -50 }];
  const r = classifySupply(trend);
  assert.ok(r.cats.includes('inst_buy'));
});
```

```javascript
// api/_signals-core.mjs 추가
export const SUPPLY_STREAK_MIN = 3;
// trend: 최신순 [{foreign, organ}] (순매수 수량). 연속 순매수 또는 전환 판정.
export function classifySupply(trend) {
  const cats = [], badges = [];
  const streak = (key) => { let n = 0; for (const r of trend) { if ((r[key] || 0) > 0) n++; else break; } return n; };
  const fb = streak('foreign'); if (fb >= SUPPLY_STREAK_MIN) { cats.push('foreign_buy'); badges.push(`외국인 ${fb}일 연속 순매수`); }
  const ib = streak('organ'); if (ib >= SUPPLY_STREAK_MIN) { cats.push('inst_buy'); badges.push(`기관 ${ib}일 연속 순매수`); }
  // 전환: 최신>0 이고 직전<0
  if (trend.length >= 2) {
    if ((trend[0].foreign || 0) > 0 && (trend[1].foreign || 0) < 0 && !cats.includes('foreign_buy')) { cats.push('foreign_buy'); badges.push('외국인 순매수 전환'); }
    if ((trend[0].organ || 0) > 0 && (trend[1].organ || 0) < 0 && !cats.includes('inst_buy')) { cats.push('inst_buy'); badges.push('기관 순매수 전환'); }
  }
  return { cats, badges };
}
```

- [ ] **Step 3: 핸들러 closed phase에서 수급 enrich**

```javascript
// api/signals.mjs — phase 계산 후, closed면 종목별 trend fetch
async function trendOne(code){
  try{const r=await fetch(`https://m.stock.naver.com/api/stock/${code}/trend`,{headers:{'User-Agent':'Mozilla/5.0','Referer':'https://m.stock.naver.com/'},signal:AbortSignal.timeout(6000)});
    if(!r.ok)return null;const rows=await r.json();
    return rows.slice(0,5).map(x=>({foreign:parseInt(String(x.foreignerPureBuyQuant||'0').replace(/[,+]/g,''),10),organ:parseInt(String(x.organPureBuyQuant||'0').replace(/[,+]/g,''),10)}));
  }catch{return null;}
}
// buildSignals 호출 전:
const phase = krMarketOpen() ? 'intraday' : 'closed';
let enrich;
if (phase === 'closed') {
  const trends = await Promise.all(stocks.map(s => trendOne(s.code)));
  const byTrend = {}; stocks.forEach((s,i)=>{ if(trends[i]) byTrend[s.code]=trends[i]; });
  enrich = (s) => byTrend[s.code] ? classifySupply(byTrend[s.code]) : { cats: [], badges: [] };
}
const { signals, rank } = buildSignals(stocks, kPct, { enrich });
```

`api/signals.mjs` 상단 import에 `classifySupply` 추가.

- [ ] **Step 4: 코어 테스트 + 시각 확인**

Run: `node --test api/_signals-core.test.mjs`
Expected: PASS — 13 tests
그 후 preview reload → screenshot으로 ETF 4카드가 실데이터로 채워지는지 확인.

- [ ] **Step 5: Commit**

```bash
git add web/stocks/index.html api/signals.mjs api/_signals-core.mjs api/_signals-core.test.mjs
git commit -m "feat(종목): ETF 4카드 렌더 + 마감판 종목별 수급 신호(연속·전환)"
```

---

## 검증 (전체 완료 후)

- [ ] `node --test api/_signals-core.test.mjs` 전체 PASS (13 tests)
- [ ] `vercel dev`로 `/api/signals` 200 + `{phase, signals, rank, etf:{lead,betting,sector,safeHaven}}` 구조 확인
- [ ] preview로 `/stocks/`: 좌(특이신호·랭킹·섹터) + 우(ETF 4카드) 실데이터, phase 라벨 정확
- [ ] 거래대금 1종목을 `itemSummary.amount` 실측과 대조
- [ ] 색 절제 유지(뱃지 회색, 채도색은 등락 방향만)
- [ ] **푸시·배포는 사용자 지시 시에만** (`deploy.yml` 자동 배포)
