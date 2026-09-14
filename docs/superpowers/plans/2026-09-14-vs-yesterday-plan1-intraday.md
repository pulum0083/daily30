# 종목 시그널 '어제랑 비교해서' — 계획 1: 공통 기반 + 장중 대결판 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 평일 09:01~15:30에 `/stocks/` 맨 위에 "직전 거래일 같은 시각 vs 지금" 장중 대결판(결론 한 줄 · 코스피 곡선 · 비교 칸 3개 · 달라진 것 카드)을 실측으로 보여주고, 페이지 제목을 "종목 시그널, 어제랑 비교해서"로 바꾼다.

**Architecture:** 서버는 기존 라우트 `api/intraday.mjs`에 `?vs=intraday` 분기만 추가한다(라우트 12/12 한도). 계산은 `_` 접두 순수 모듈 4개(`_vs-core` · `_vs-flow` · `_vs-prices` · `_vs-issues`)와 조립 모듈 `_vs-intraday`로 나누고, 네트워크는 주입받은 `fetchJson`·`fetchText`로만 해서 네트워크 없이 테스트한다. 화면은 새 에셋 `web/assets/vs-yesterday.js`·`.css`가 응답을 받아 `#vs-root`에 그린다. 판정·문장은 전부 서버의 결정론 규칙이고 화면은 그리기만 한다.

**Tech Stack:** Node 22 ESM(Vercel 서버리스), 브라우저 ES5 스크립트(IIFE), `node:test` + `node:vm`, eslint 9, 네이버 금융 공개 엔드포인트.

**Spec:** `docs/superpowers/specs/2026-09-14-stocks-vs-yesterday-design.md` (확정 시안 `docs/prototypes/2026-09-14-vs-yesterday.html` v4)

## Global Constraints

- 모든 수치는 실측이다. 없으면 그 칸·섹션을 비운다. 추정·보간·LLM 생성 금지(SERVICE_RULES §0).
- "어제" = 직전 한국 거래일. 라벨은 날짜로 계산한다("어제" / "지난 금요일"). 상수로 박지 않는다(§24).
- 날짜 고정 조회: 그 날짜 그 시각 이하의 행만 쓴다. 없으면 null, 다른 날짜·최신 행으로 폴백하지 않는다(§45).
- 판정 임계: 코스피 등락률·주도주 평균 차이 ±0.3%p 이내 = "비슷해요", 외국인 누적 순매수 차이 ±1,000억 원 이내 = "비슷해요". 차이 > 0 → "오늘이 셈".
- 결론 한 줄은 코스피 판정으로 정한다. 외국인 판정이 "비슷해요"가 아니면 근거 줄에 덧붙인다.
- 전일 종가는 과거 일봉 종가를 쓴다(과거 봉은 공식 종가와 일치, §48). 당일 봉 종가는 쓰지 않는다.
- 1분봉 가격을 화면에 숫자로 적을 땐 KRX 호가 단위 검사를 통과한 값만 쓴다. 곡선 모양에는 그대로 쓴다(설계 §6 #6).
- 수급 표 열 순서: 개인·외국인·기관계·기관 세부 6칸·기타법인. 개인+외국인+기관계+기타법인 합이 ±5억 밖이면 그 행을 버린다(설계 §6 #4).
- `api/` 라우트는 12개 한도다. 새 파일은 반드시 `_` 접두(`api/_route-budget.test.mjs`).
- 새 소스 파일 첫 줄은 역할을 적은 한국어 주석 한 줄.
- 커밋 메시지 끝: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- `web/` 생성물·`web/stocks/index.html` 푸시 금지 시간: 07:25~07:45 · 16:25~16:50 · 21:15~21:40 KST(§43).
- 화면 문구는 해요체, 문장 끝에 콜론을 쓰지 않는다.
- CI 명령: `python3 -m pytest scripts/ -q` · `node --test api/*.test.mjs` · `node --test web/assets/*.test.mjs` · `npx --yes eslint@9 web/assets/ api/`.

## 파일 구조

| 파일 | 책임 |
| --- | --- |
| Create `api/_vs-core.mjs` | 직전 거래일·상대 라벨·날짜 고정 조회·등락률·판정·호가 단위·결론 문장(순수) |
| Create `api/_vs-flow.mjs` | 네이버 시간대별 투자자 표 파싱 + 시각 이하 마지막 행 찾기(페이지 이진 탐색) |
| Create `api/_vs-prices.mjs` | 지수·종목 1분봉, 직전 거래일 종가, 곡선 샘플링 |
| Create `api/_vs-issues.mjs` | 이슈 아카이브에서 시각 이하 제목 뽑기, 키워드 사전 대조 |
| Create `web/data/issue-keywords.json` | 이슈 키워드 사전(설정 파일, 코드 리터럴 금지) |
| Create `api/_vs-intraday.mjs` | 위 모듈을 조립해 장중 대결판 응답을 만든다 + 실제 fetch 기본값 |
| Modify `api/intraday.mjs` | `?vs=intraday` 분기 |
| Modify `api/_cache-headers.test.mjs` | 새 분기의 엣지 캐시 검사 추가 |
| Create `web/assets/vs-yesterday.js` | 응답 폴링 + `#vs-root` 렌더 |
| Create `web/assets/vs-yesterday.css` | 대결판 스타일(`vs-` 접두 — 자금 지도의 `.flow-row`와 충돌 방지) |
| Modify `web/stocks/index.html` | 제목·설명 변경, BETA 제거, `#vs-root` 자리, CSS·JS 연결 |
| Create 테스트 `api/_vs-*.test.mjs` 5개, `web/assets/vs-yesterday.test.mjs` | |
| Modify `docs/SERVICE_RULES.md` | §49 운영 규칙 |

---

### Task 1: `_vs-core.mjs` — 직전 거래일·판정·결론 문장

**Files:**
- Create: `api/_vs-core.mjs`
- Test: `api/_vs-core.test.mjs`

**Interfaces:**
- Consumes: `lastTradingDay(dash)`, `labelFromYmd(dash)` from `api/_market-calendar.mjs`
- Produces:
  - `TH = { pctPoint: 0.3, eok: 1000 }`
  - `prevTradingDay(dash: 'YYYY-MM-DD'): 'YYYY-MM-DD'`
  - `relLabel(prevDash, todayDash): string` — `'어제'` | `'지난 금요일'`
  - `withJosa(word, pair: '와과'|'이가'): string`
  - `atOrBefore(bars: {t:'HHMM', v:number}[], hhmm: 'HHMM'): {t,v}|null`
  - `pct(v, base): number|null` (소수 둘째 자리)
  - `round2(n): number`
  - `judge(diff, th): 'same'|'strong'|'weak'|null`
  - `eokText(e: number): string` — 부호 없음, `'8,693억'` / `'2.09조'`
  - `tickOk(price): boolean`
  - `verdict({ yLabel, kospiDiff, foreignDiff }): {title, sub, judge}|null`

- [ ] **Step 1: 실패하는 테스트 작성**

```js
// '어제랑 비교해서' 공용 순수 함수 회귀 테스트 — 직전 거래일·판정·결론 문장(설계 §2·§5)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TH, prevTradingDay, relLabel, withJosa, atOrBefore, pct, judge, eokText, tickOk, verdict } from './_vs-core.mjs';

test('직전 거래일 — 월요일은 금요일, 추석 연휴 뒤는 연휴 전 거래일', () => {
  assert.equal(prevTradingDay('2026-09-14'), '2026-09-11');
  assert.equal(prevTradingDay('2026-09-15'), '2026-09-14');
  assert.equal(prevTradingDay('2026-09-28'), '2026-09-23'); // 9/24~26 휴장 + 주말
});

test('상대 라벨은 날짜로 계산한다', () => {
  assert.equal(relLabel('2026-09-14', '2026-09-15'), '어제');
  assert.equal(relLabel('2026-09-11', '2026-09-14'), '지난 금요일');
  assert.equal(relLabel('2026-09-23', '2026-09-28'), '지난 수요일');
});

test('조사는 받침으로 고른다', () => {
  assert.equal(withJosa('어제', '와과'), '어제와');
  assert.equal(withJosa('지난 금요일', '와과'), '지난 금요일과');
});

test('날짜 고정 조회 — 시각 이하 마지막 봉, 없으면 null', () => {
  const bars = [{ t: '0900', v: 1 }, { t: '1059', v: 2 }, { t: '1101', v: 3 }];
  assert.deepEqual(atOrBefore(bars, '1100'), { t: '1059', v: 2 });
  assert.equal(atOrBefore(bars, '0859'), null);
  assert.equal(atOrBefore([], '1100'), null);
});

test('등락률은 소수 둘째 자리, 기준이 없으면 null', () => {
  assert.equal(pct(6732.94, 6909.91), -2.56);
  assert.equal(pct(6863.70, 7033.92), -2.42);
  assert.equal(pct(100, null), null);
});

test('판정 — 경계값은 비슷해요', () => {
  assert.equal(judge(0.3, TH.pctPoint), 'same');
  assert.equal(judge(-0.31, TH.pctPoint), 'weak');
  assert.equal(judge(1001, TH.eok), 'strong');
  assert.equal(judge(null, TH.eok), null);
});

test('억 표기', () => {
  assert.equal(eokText(-8693), '8,693억');
  assert.equal(eokText(-20900), '2.09조');
});

test('호가 단위 — 1분봉 off-tick 값은 화면 숫자로 쓰지 않는다', () => {
  assert.equal(tickOk(259250), false); // 9/11 삼성전자 1분봉 실측
  assert.equal(tickOk(252000), true);
  assert.equal(tickOk(1733000), true);
  assert.equal(tickOk(1733500), false);
});

test('결론 문장 — 9/14 11:00 실측 리플레이', () => {
  const v = verdict({ yLabel: '지난 금요일', kospiDiff: -0.14, foreignDiff: -8693 });
  assert.equal(v.judge, 'same');
  assert.equal(v.title, '지난 금요일과 비슷해요');
  assert.equal(v.sub, '코스피가 같은 시각 기준 거의 같은 자리예요(−0.14%p) · 외국인 누적 순매수는 8,693억 원 적어요');
});

test('결론 문장 — 코스피가 없으면 결론을 만들지 않는다', () => {
  assert.equal(verdict({ yLabel: '어제', kospiDiff: null, foreignDiff: -5000 }), null);
});

test('결론 문장 — 외국인이 비슷하면 근거 줄에 붙이지 않는다', () => {
  const v = verdict({ yLabel: '어제', kospiDiff: 0.52, foreignDiff: 300 });
  assert.equal(v.title, '오늘이 어제보다 세요');
  assert.equal(v.sub, '코스피가 같은 시각 기준 0.52%p 높아요');
});
```

- [ ] **Step 2: 실패 확인**

Run: `node --test api/_vs-core.test.mjs`
Expected: FAIL — `Cannot find module './_vs-core.mjs'`

- [ ] **Step 3: 구현**

```js
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
```

- [ ] **Step 4: 통과 확인**

Run: `node --test api/_vs-core.test.mjs`
Expected: PASS (11 tests)

- [ ] **Step 5: 커밋**

```bash
git add api/_vs-core.mjs api/_vs-core.test.mjs
git commit -m "feat: '어제랑 비교해서' 공용 판정 모듈 — 직전 거래일·날짜 고정 조회·결론 문장

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `_vs-flow.mjs` — 시간대별 투자자 순매수

**Files:**
- Create: `api/_vs-flow.mjs`
- Test: `api/_vs-flow.test.mjs`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `parseInvestorTimePage(html: string): {t:'HH:MM', 개인:number, 외국인:number, 기관:number}[]` — 최신 시각이 먼저, 단위 억 원
  - `lastPage(html): number`
  - `flowAt(ymd: 'YYYYMMDD', hhmm: 'HHMM', fetchText: (url)=>Promise<string>): Promise<row|null>`

원천: `https://finance.naver.com/sise/investorDealTrendTime.naver?bizdate={YYYYMMDD}&sosok=01&page={n}` (EUC-KR HTML, 페이지당 10행, 최신 시각이 1페이지). 2026-09-14 실측 행 예: `18:06 | 18,675 | -22,984 | -12,184 | -10,345 | -17 | -4,703 | 7 | 216 | 2,659 | 16,493` (개인·외국인·기관계·기관 세부 6칸·기타법인).

- [ ] **Step 1: 실패하는 테스트 작성**

```js
// 네이버 시간대별 투자자 매매동향 파서·시각 조회 회귀 테스트(설계 §6 #4)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseInvestorTimePage, lastPage, flowAt } from './_vs-flow.mjs';

function row(t, v) { return `<tr><td class="date">${t}</td>${v.map((x) => `<td class="rate_up">${x}</td>`).join('')}</tr>`; }
function page(rows, last = 3) {
  return '<table><tr><th>시간</th><th>개인</th><th>외국인</th><th>기관계</th><th colspan="6">기관</th><th>기타법인</th></tr>'
    + rows.join('') + '</table>' + Array.from({ length: last }, (_, i) => `<a href="?page=${i + 1}">${i + 1}</a>`).join('');
}
// 합계 0: 18675 − 22984 − 12184 + 16493 = 0 (9/11 18:06 실측)
const OK = ['18,675', '-22,984', '-12,184', '-10,345', '-17', '-4,703', '7', '216', '2,659', '16,493'];

test('열 순서대로 개인·외국인·기관계를 읽는다', () => {
  assert.deepEqual(parseInvestorTimePage(page([row('18:06', OK)])), [{ t: '18:06', 개인: 18675, 외국인: -22984, 기관: -12184 }]);
});

test('합계 0 검사를 통과하지 못한 행은 버린다(열 밀림 방어)', () => {
  const broken = ['18,675', '-22,984', '-12,184', '-10,345', '-17', '-4,703', '7', '216', '2,659', '99,999'];
  assert.deepEqual(parseInvestorTimePage(page([row('18:05', broken), row('18:04', OK)])).map((r) => r.t), ['18:04']);
});

test('머리글·빈 행은 건너뛴다', () => {
  assert.deepEqual(parseInvestorTimePage('<tr><td></td></tr>' + page([])), []);
});

test('마지막 페이지 번호', () => {
  assert.equal(lastPage(page([], 37)), 37);
  assert.equal(lastPage('<table></table>'), 1);
});

test('시각 이하 마지막 행을 페이지 이진 탐색으로 찾는다', async () => {
  // 1페이지 11:30~11:02 · 2페이지 11:01~10:59 · 3페이지 10:58~09:01
  const pages = {
    1: page([row('11:30', OK), row('11:02', OK)]),
    2: page([row('11:01', OK), row('10:59', OK)]),
    3: page([row('10:58', OK), row('09:01', OK)]),
  };
  const seen = [];
  const fetchText = async (url) => { const p = Number(url.match(/page=(\d+)/)[1]); seen.push(p); return pages[p]; };
  const hit = await flowAt('20260914', '1100', fetchText);
  assert.equal(hit.t, '10:59');
  assert.ok(seen.length <= 4, `페이지를 ${seen.length}번 읽었다`);
});

test('그 시각 이전 행이 없으면 null — 다른 시각으로 폴백하지 않는다', async () => {
  const fetchText = async () => page([row('09:05', OK)], 1);
  assert.equal(await flowAt('20260914', '0900', fetchText), null);
});

test('URL에 날짜·코스피(sosok=01)를 고정한다', async () => {
  let u = '';
  await flowAt('20260911', '1100', async (url) => { u = url; return page([row('10:00', OK)], 1); });
  assert.match(u, /bizdate=20260911&sosok=01&page=1$/);
});
```

- [ ] **Step 2: 실패 확인**

Run: `node --test api/_vs-flow.test.mjs`
Expected: FAIL — `Cannot find module './_vs-flow.mjs'`

- [ ] **Step 3: 구현**

```js
// 네이버 금융 시간대별 투자자 매매동향(코스피) — 표 파싱과 '그 시각 이하 마지막 행' 조회(설계 §6 #4)
const URL_BASE = 'https://finance.naver.com/sise/investorDealTrendTime.naver';

export function parseInvestorTimePage(html) {
  const rows = [];
  for (const tr of String(html).match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || []) {
    const cells = [...tr.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map((m) => m[1].replace(/<[^>]+>|&nbsp;/g, '').trim());
    if (cells.length !== 11 || !/^\d{2}:\d{2}$/.test(cells[0])) continue;
    const v = cells.slice(1).map((x) => Number(x.replace(/,/g, '')));
    if (v.some((n) => !Number.isFinite(n))) continue;
    // 개인+외국인+기관계+기타법인 = 0(반올림 최대 2억). 벗어나면 열이 밀린 것이라 쓰지 않는다
    if (Math.abs(v[0] + v[1] + v[2] + v[9]) > 5) continue;
    rows.push({ t: cells[0], 개인: v[0], 외국인: v[1], 기관: v[2] });
  }
  return rows;
}

export function lastPage(html) {
  const nums = [...String(html).matchAll(/page=(\d+)/g)].map((m) => Number(m[1]));
  return nums.length ? Math.max(...nums) : 1;
}

// 페이지는 최신 시각부터. 어떤 페이지에 target 이하 행이 있으면 답은 그 페이지거나 더 앞 페이지다
export async function flowAt(ymd, hhmm, fetchText) {
  const url = (p) => `${URL_BASE}?bizdate=${ymd}&sosok=01&page=${p}`;
  const firstHtml = await fetchText(url(1));
  const cache = new Map([[1, parseInvestorTimePage(firstHtml)]]);
  const rowsOf = async (p) => {
    if (!cache.has(p)) cache.set(p, parseInvestorTimePage(await fetchText(url(p))));
    return cache.get(p);
  };
  let lo = 1, hi = lastPage(firstHtml), found = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const rows = await rowsOf(mid);
    if (!rows.length) return found;
    const hit = rows.find((r) => r.t.replace(':', '') <= hhmm);
    if (hit) { found = hit; hi = mid - 1; } else lo = mid + 1;
  }
  return found;
}
```

- [ ] **Step 4: 통과 확인**

Run: `node --test api/_vs-flow.test.mjs`
Expected: PASS (7 tests)

- [ ] **Step 5: 실측 한 번 확인(네트워크)**

Run:
```bash
node --input-type=module -e "
import { flowAt } from './api/_vs-flow.mjs';
const t = async (u) => new TextDecoder('euc-kr').decode(await (await fetch(u,{headers:{'User-Agent':'Mozilla/5.0','Referer':'https://finance.naver.com/'}})).arrayBuffer());
console.log(await flowAt('20260911','1100',t), await flowAt('20260914','1100',t));"
```
Expected: 두 날짜 모두 `t`가 `11:00` 이하인 행이 나오고 `외국인`이 음수(9/11 약 −12,300억대, 9/14 약 −20,900억대 — 설계 §6 #4의 −1.23조·−2.09조와 같은 자릿수)

- [ ] **Step 6: 커밋**

```bash
git add api/_vs-flow.mjs api/_vs-flow.test.mjs
git commit -m "feat: 시간대별 투자자 순매수 파서 — 합계 0 검사 + 시각 이하 마지막 행 이진 탐색

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `_vs-prices.mjs` — 1분봉·직전 종가·곡선

**Files:**
- Create: `api/_vs-prices.mjs`
- Test: `api/_vs-prices.test.mjs`

**Interfaces:**
- Consumes: `pct` from `api/_vs-core.mjs`
- Produces:
  - `minuteBars(kind: 'index'|'item', code, ymd: 'YYYYMMDD', fetchJson, from='0900', to='1530'): Promise<{t:'HHMM', v:number}[]>`
  - `prevClose(kind, code, ymd, fetchJson): Promise<number|null>` — ymd보다 앞선 마지막 일봉 종가
  - `curve(bars, base, untilHHMM): [minuteFrom0900:number, pct:number][]` — 5분 샘플 + 마지막 점

원천(2026-09-14 실측): `https://api.stock.naver.com/chart/domestic/index/KOSPI/minute?startDateTime=202609111000&endDateTime=202609111005` → `[{localDateTime:'20260911100000', currentPrice:6863.54, ...}]`. 종목은 `item/{code}`. 일봉은 `/day?startDateTime=YYYYMMDD0000&endDateTime=YYYYMMDD0000` → `[{localDate:'20260911', closePrice:6909.91}]`.

- [ ] **Step 1: 실패하는 테스트 작성**

```js
// 지수·종목 1분봉과 직전 종가 조회 회귀 테스트(설계 §6 #1·#2·#7)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { minuteBars, prevClose, curve } from './_vs-prices.mjs';

const fake = (map) => async (url) => { for (const [re, v] of map) if (re.test(url)) return v; throw new Error('unexpected ' + url); };

test('지수 1분봉 — 그 날짜 봉만 오름차순으로', async () => {
  const f = fake([[/index\/KOSPI\/minute\?startDateTime=202609141000&endDateTime=202609141100$/, [
    { localDateTime: '20260914100000', currentPrice: 6750.1 },
    { localDateTime: '20260913235900', currentPrice: 1 },          // 다른 날짜 — 버린다
    { localDateTime: '20260914110000', currentPrice: 6732.94 },
  ]]]);
  assert.deepEqual(await minuteBars('index', 'KOSPI', '20260914', f, '1000', '1100'),
    [{ t: '1000', v: 6750.1 }, { t: '1100', v: 6732.94 }]);
});

test('종목 경로는 item/{code}', async () => {
  let u = '';
  await minuteBars('item', '005930', '20260911', async (url) => { u = url; return []; });
  assert.match(u, /item\/005930\/minute\?startDateTime=202609110900&endDateTime=202609111530$/);
});

test('직전 종가 — 기준일 당일 봉은 쓰지 않는다(장 마감 뒤엔 애프터장 가격, §48)', async () => {
  const f = fake([[/index\/KOSPI\/day/, [
    { localDate: '20260910', closePrice: 7033.92 },
    { localDate: '20260911', closePrice: 6909.91 },
    { localDate: '20260914', closePrice: 6684.37 },
  ]]]);
  assert.equal(await prevClose('index', 'KOSPI', '20260914', f), 6909.91);
  assert.equal(await prevClose('index', 'KOSPI', '20260911', f), 7033.92);
});

test('직전 종가가 없으면 null', async () => {
  assert.equal(await prevClose('item', '005930', '20260914', async () => []), null);
});

test('곡선 — 09:00 기준 경과 분, 5분 샘플, 마지막 점은 항상', () => {
  const bars = [{ t: '0900', v: 100 }, { t: '0903', v: 99 }, { t: '0905', v: 98 }, { t: '0907', v: 97 }, { t: '0910', v: 96 }];
  assert.deepEqual(curve(bars, 100, '0907'), [[0, 0], [5, -2], [7, -3]]);
});
```

- [ ] **Step 2: 실패 확인**

Run: `node --test api/_vs-prices.test.mjs`
Expected: FAIL — `Cannot find module './_vs-prices.mjs'`

- [ ] **Step 3: 구현**

```js
// 네이버 지수·종목 1분봉과 직전 거래일 종가 — 날짜 고정 조회(설계 §6·§45)
import { pct } from './_vs-core.mjs';

const BASE = 'https://api.stock.naver.com/chart/domestic';
const path = (kind, code) => (kind === 'index' ? `index/${code}` : `item/${code}`);

function shiftYmd(ymd, days) {
  const d = new Date(Date.UTC(+ymd.slice(0, 4), +ymd.slice(4, 6) - 1, +ymd.slice(6, 8) + days));
  return d.toISOString().slice(0, 10).replace(/-/g, '');
}

export async function minuteBars(kind, code, ymd, fetchJson, from = '0900', to = '1530') {
  const rows = await fetchJson(`${BASE}/${path(kind, code)}/minute?startDateTime=${ymd}${from}&endDateTime=${ymd}${to}`);
  return (Array.isArray(rows) ? rows : [])
    .filter((r) => String(r.localDateTime).slice(0, 8) === ymd && typeof r.currentPrice === 'number')
    .map((r) => ({ t: String(r.localDateTime).slice(8, 12), v: r.currentPrice }))
    .sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0));
}

// ymd보다 앞선 마지막 일봉 종가. 과거 봉은 공식 종가와 일치한다(§48)
export async function prevClose(kind, code, ymd, fetchJson) {
  const rows = await fetchJson(`${BASE}/${path(kind, code)}/day?startDateTime=${shiftYmd(ymd, -14)}0000&endDateTime=${ymd}0000`);
  const past = (Array.isArray(rows) ? rows : []).filter((r) => String(r.localDate) < ymd && typeof r.closePrice === 'number');
  return past.length ? past[past.length - 1].closePrice : null;
}

const minFrom0900 = (t) => Number(t.slice(0, 2)) * 60 + Number(t.slice(2)) - 540;

export function curve(bars, base, untilHHMM) {
  const pts = (bars || []).filter((b) => b.t <= untilHHMM);
  return pts
    .filter((b, i) => Number(b.t.slice(2)) % 5 === 0 || i === pts.length - 1)
    .map((b) => [minFrom0900(b.t), pct(b.v, base)])
    .filter((p) => p[1] != null);
}
```

- [ ] **Step 4: 통과 확인**

Run: `node --test api/_vs-prices.test.mjs`
Expected: PASS (5 tests)

- [ ] **Step 5: 커밋**

```bash
git add api/_vs-prices.mjs api/_vs-prices.test.mjs
git commit -m "feat: 지수·종목 1분봉과 직전 거래일 종가 조회 — 당일 봉 종가 제외

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `_vs-issues.mjs` + 키워드 사전

**Files:**
- Create: `api/_vs-issues.mjs`
- Create: `web/data/issue-keywords.json`
- Test: `api/_vs-issues.test.mjs`

**Interfaces:**
- Consumes: `web/data/kospi-news-{YYYY-MM-DD}.json` 모양 `{history:[{time:'HH:MM', market:{title}, stock:{title}}]}`
- Produces:
  - `issuesUntil(archive, hhmm: 'HHMM'): {t:'HH:MM', title:string}[]` — 시각 오름차순
  - `keywordDiff(yItems, tItems, words: string[]): {new:string[], keep:string[], gone:string[]}` — 사전 순서 유지

- [ ] **Step 1: 사전 파일 작성**

`web/data/issue-keywords.json`:
```json
{
  "note": "장중 이슈 제목에서 찾는 소재 사전 — 설계 §5 '이슈 키워드'. 사전에 없는 소재는 잡히지 않는다. 소재를 추가·삭제할 땐 이 파일만 고친다.",
  "updated": "2026-09-14",
  "keywords": ["AI 속도 조절론", "중동", "유가", "금리", "환율", "관세", "CPI", "FOMC", "반도체", "2차전지", "조선", "방산", "외국인", "기관", "개인", "매도", "매수", "삼성전자", "SK하이닉스", "현대차", "애프터마켓", "공매도"]
}
```

- [ ] **Step 2: 실패하는 테스트 작성**

```js
// 장중 이슈 시각 필터·키워드 대조 회귀 테스트 — 9/11·9/14 실제 아카이브 리플레이(설계 §4.2·§5)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { issuesUntil, keywordDiff } from './_vs-issues.mjs';

const read = (f) => JSON.parse(readFileSync(new URL(`../web/data/${f}`, import.meta.url), 'utf8'));
const WORDS = read('issue-keywords.json').keywords;

test('그 시각 이하 이슈만, market·stock 제목을 모두', () => {
  const a = { history: [
    { time: '11:01', market: { title: '늦은 이슈' }, stock: { title: '늦은 종목' } },
    { time: '10:00', market: { title: '시장 A' }, stock: { title: '종목 A' } },
    { time: 'x', market: { title: '시각 없음' } },
  ] };
  assert.deepEqual(issuesUntil(a, '1100'), [{ t: '10:00', title: '시장 A' }, { t: '10:00', title: '종목 A' }]);
  assert.deepEqual(issuesUntil(null, '1100'), []);
});

test('9/11 vs 9/14 11:00 — 중동·AI 속도 조절론이 새로 떠올랐다(시안 v4와 같은 결과)', () => {
  const y = issuesUntil(read('kospi-news-2026-09-11.json'), '1100');
  const t = issuesUntil(read('kospi-news-2026-09-14.json'), '1100');
  const d = keywordDiff(y, t, WORDS);
  assert.deepEqual(d.new, ['AI 속도 조절론', '중동']);
  for (const w of ['유가', '금리', '외국인', '기관', '매도', '삼성전자', 'SK하이닉스']) assert.ok(d.keep.includes(w), w);
});

test('어제에만 있던 소재는 gone', () => {
  const d = keywordDiff([{ t: '10:00', title: '관세 우려' }], [{ t: '10:00', title: '금리 부담' }], ['관세', '금리']);
  assert.deepEqual(d, { new: ['금리'], keep: [], gone: ['관세'] });
});
```

- [ ] **Step 3: 실패 확인**

Run: `node --test api/_vs-issues.test.mjs`
Expected: FAIL — `Cannot find module './_vs-issues.mjs'`

- [ ] **Step 4: 구현**

```js
// 장중 이슈 아카이브에서 그 시각까지의 제목을 뽑고 키워드 사전으로 두 날을 대조한다(설계 §5)
export function issuesUntil(archive, hhmm) {
  const out = [];
  for (const h of (archive && archive.history) || []) {
    const t = String(h.time || '');
    if (!/^\d{2}:\d{2}$/.test(t) || t.replace(':', '') > hhmm) continue;
    for (const k of ['market', 'stock']) {
      const title = h[k] && h[k].title;
      if (title) out.push({ t, title: String(title) });
    }
  }
  return out.sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0));
}

export function keywordDiff(yItems, tItems, words) {
  const has = (items, w) => items.some((i) => i.title.includes(w));
  const res = { new: [], keep: [], gone: [] };
  for (const w of words || []) {
    const y = has(yItems, w), t = has(tItems, w);
    if (t && !y) res.new.push(w);
    else if (t && y) res.keep.push(w);
    else if (y) res.gone.push(w);
  }
  return res;
}
```

- [ ] **Step 5: 통과 확인**

Run: `node --test api/_vs-issues.test.mjs`
Expected: PASS (3 tests)

- [ ] **Step 6: 커밋**

```bash
git add api/_vs-issues.mjs api/_vs-issues.test.mjs web/data/issue-keywords.json
git commit -m "feat: 장중 이슈 시각 필터·키워드 사전 대조 — 사전은 설정 파일로

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `_vs-intraday.mjs` 조립 + `api/intraday.mjs?vs=intraday`

**Files:**
- Create: `api/_vs-intraday.mjs`
- Modify: `api/intraday.mjs` (import 한 줄 + `handler` 맨 앞 분기)
- Modify: `api/_cache-headers.test.mjs` (`POLLED` 배열에 한 줄)
- Test: `api/_vs-intraday.test.mjs`

**Interfaces:**
- Consumes: Task 1~4의 모든 export, `isKospiHoliday`·`labelFromYmd` from `_market-calendar.mjs`
- Produces:
  - `LEADERS = [['005930','삼성전자'],['000660','SK하이닉스'],['005380','현대차']]`
  - `getJson(url): Promise<any>`, `getEucKr(url): Promise<string>` — 실제 네트워크 기본값
  - `buildIntradayVs({ now?: number, fetchJson, fetchText, origin }): Promise<Payload>`
  - `Payload` (프런트 Task 6이 그대로 쓴다):

```ts
{ status: 'closed' | 'waiting' }
| { status: 'ok',
    time: 'HH:MM',
    today: { date: 'YYYY-MM-DD', label: '9/14(월)' },
    prev:  { date: 'YYYY-MM-DD', label: '9/11(금)', rel: '지난 금요일' },
    verdict: { title, sub, judge } | null,
    kospi: { t: number|null, y: number|null, diff: number|null, judge, curveT: [m,p][], curveY: [m,p][] },
    flow:  { t: {개인,외국인,기관}, y: {개인,외국인,기관}, foreignDiff: number, judge } | null,
    leaders: { code, name, t: number|null, y: number|null, diff: number|null, pxT: number|null, pxY: number|null }[],
    avg:   { t: number, y: number, diff: number, judge } | null,
    issues: { y: {t,title}[], t: {t,title}[], new: string[], keep: string[] } | null }
```

- [ ] **Step 1: 실패하는 테스트 작성**

```js
// 장중 대결판 응답 조립 회귀 테스트 — 네트워크 없이 9/14 11:00 실측 값으로 리플레이
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildIntradayVs } from './_vs-intraday.mjs';

const kst = (s) => Date.parse(s + 'Z') - 9 * 3600 * 1000;
const OK = (f) => ['0', String(f), '0', '0', '0', '0', '0', '0', '0', String(-f)];
const flowPage = (t, f) => `<table><tr><td>${t}</td>${OK(f).map((x) => `<td>${x}</td>`).join('')}</tr></table>`;
const minute = (ymd, hhmm, v) => [{ localDateTime: `${ymd}${hhmm}00`, currentPrice: v }];

function fakes() {
  const fetchJson = async (url) => {
    if (/KOSPI\/day/.test(url)) return [{ localDate: '20260910', closePrice: 7033.92 }, { localDate: '20260911', closePrice: 6909.91 }];
    if (/KOSPI\/minute\?startDateTime=20260914/.test(url)) return minute('20260914', '1100', 6732.94);
    if (/KOSPI\/minute\?startDateTime=20260911/.test(url)) return minute('20260911', '1100', 6863.70);
    if (/005930\/day/.test(url)) return [{ localDate: '20260910', closePrice: 269000 }, { localDate: '20260911', closePrice: 259500 }];
    if (/005930\/minute\?startDateTime=20260914/.test(url)) return minute('20260914', '1100', 252000);
    if (/005930\/minute\?startDateTime=20260911/.test(url)) return minute('20260911', '1100', 257500);
    if (/\/(000660|005380)\//.test(url)) return [];
    if (/kospi-news-2026-09-14/.test(url)) return { history: [{ time: '10:30', market: { title: '코스피, AI 속도 조절론·중동 불안에 급락' } }] };
    if (/kospi-news-2026-09-11/.test(url)) return { history: [{ time: '10:00', market: { title: '국제유가 급등 여파' } }] };
    if (/issue-keywords/.test(url)) return { keywords: ['AI 속도 조절론', '중동', '유가'] };
    throw new Error('unexpected ' + url);
  };
  const fetchText = async (url) => (/bizdate=20260914/.test(url) ? flowPage('11:00', -20900) : flowPage('11:00', -12207));
  return { fetchJson, fetchText, origin: 'https://doubleshot.space' };
}

test('주말·장 전·장 후엔 closed — 네트워크를 부르지 않는다', async () => {
  const boom = async () => { throw new Error('호출되면 안 된다'); };
  for (const s of ['2026-09-13T11:00:00', '2026-09-14T08:59:00', '2026-09-14T15:31:00', '2026-09-24T11:00:00']) {
    assert.deepEqual(await buildIntradayVs({ now: kst(s), fetchJson: boom, fetchText: boom, origin: '' }), { status: 'closed' }, s);
  }
});

test('9/14 11:00 리플레이 — 코스피·외국인·결론', async () => {
  const d = await buildIntradayVs({ now: kst('2026-09-14T11:00:30'), ...fakes() });
  assert.equal(d.status, 'ok');
  assert.equal(d.time, '11:00');
  assert.equal(d.prev.rel, '지난 금요일');
  assert.equal(d.prev.label, '9/11(금)');
  assert.deepEqual([d.kospi.t, d.kospi.y, d.kospi.diff, d.kospi.judge], [-2.56, -2.42, -0.14, 'same']);
  assert.equal(d.flow.foreignDiff, -8693);
  assert.equal(d.flow.judge, 'weak');
  assert.equal(d.verdict.title, '지난 금요일과 비슷해요');
  assert.deepEqual(d.issues.new, ['AI 속도 조절론', '중동']);
});

test('주도주 — 한 종목이라도 비면 평균을 만들지 않는다(§0)', async () => {
  const d = await buildIntradayVs({ now: kst('2026-09-14T11:00:30'), ...fakes() });
  const s = d.leaders.find((l) => l.code === '005930');
  assert.deepEqual([s.t, s.y, s.diff, s.pxT], [-2.89, -4.28, 1.39, 252000]);
  assert.equal(d.leaders.find((l) => l.code === '000660').t, null);
  assert.equal(d.avg, null);
});

test('오늘 1분봉이 아직 없으면 waiting', async () => {
  const f = fakes();
  const fetchJson = async (url) => (/minute\?startDateTime=20260914/.test(url) ? [] : f.fetchJson(url));
  assert.deepEqual(await buildIntradayVs({ now: kst('2026-09-14T09:01:10'), ...f, fetchJson }), { status: 'waiting' });
});

test('수급 원천이 실패해도 나머지는 그린다 — flow만 null', async () => {
  const f = fakes();
  const d = await buildIntradayVs({ now: kst('2026-09-14T11:00:30'), ...f, fetchText: async () => { throw new Error('down'); } });
  assert.equal(d.status, 'ok');
  assert.equal(d.flow, null);
  assert.equal(d.verdict.sub, '코스피가 같은 시각 기준 거의 같은 자리예요(−0.14%p)');
});
```

- [ ] **Step 2: 실패 확인**

Run: `node --test api/_vs-intraday.test.mjs`
Expected: FAIL — `Cannot find module './_vs-intraday.mjs'`

- [ ] **Step 3: 조립 모듈 구현**

```js
// '어제랑 비교해서' 장중 대결판 응답 조립 — 코스피·수급·주도주·이슈를 직전 거래일 같은 시각과 맞댄다(설계 §4.2)
import { TH, prevTradingDay, relLabel, atOrBefore, pct, round2, judge, tickOk, verdict } from './_vs-core.mjs';
import { flowAt } from './_vs-flow.mjs';
import { minuteBars, prevClose, curve } from './_vs-prices.mjs';
import { issuesUntil, keywordDiff } from './_vs-issues.mjs';
import { isKospiHoliday, labelFromYmd } from './_market-calendar.mjs';

export const LEADERS = [['005930', '삼성전자'], ['000660', 'SK하이닉스'], ['005380', '현대차']];
const HDR = { 'User-Agent': 'Mozilla/5.0', Referer: 'https://finance.naver.com/' };

export async function getJson(url) {
  const r = await fetch(url, { headers: HDR, signal: AbortSignal.timeout(6000) });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return r.json();
}

export async function getEucKr(url) {
  const r = await fetch(url, { headers: HDR, signal: AbortSignal.timeout(6000) });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return new TextDecoder('euc-kr').decode(await r.arrayBuffer());
}

const settle = (p, fallback) => Promise.resolve().then(() => p).catch(() => fallback);

export async function buildIntradayVs({ now = Date.now(), fetchJson, fetchText, origin }) {
  const k = new Date(now + 9 * 3600 * 1000);
  const dash = k.toISOString().slice(0, 10);
  const hhmm = k.toISOString().slice(11, 16).replace(':', '');
  if (isKospiHoliday(k) || hhmm < '0901' || hhmm > '1530') return { status: 'closed' };

  const yDash = prevTradingDay(dash);
  const T = dash.replace(/-/g, ''), Y = yDash.replace(/-/g, '');
  const rel = relLabel(yDash, dash);

  const [kT, kY, baseT, baseY] = await Promise.all([
    settle(minuteBars('index', 'KOSPI', T, fetchJson, '0900', hhmm), []),
    settle(minuteBars('index', 'KOSPI', Y, fetchJson), []),
    settle(prevClose('index', 'KOSPI', T, fetchJson), null),
    settle(prevClose('index', 'KOSPI', Y, fetchJson), null),
  ]);
  if (!kT.length) return { status: 'waiting' };
  const at = kT[kT.length - 1].t;                       // 비교 시각 = 오늘 마지막 1분봉
  const kyAt = atOrBefore(kY, at);
  const kospi = { t: pct(kT[kT.length - 1].v, baseT), y: kyAt ? pct(kyAt.v, baseY) : null };
  kospi.diff = kospi.t != null && kospi.y != null ? round2(kospi.t - kospi.y) : null;
  kospi.judge = judge(kospi.diff, TH.pctPoint);
  kospi.curveT = curve(kT, baseT, at);
  kospi.curveY = curve(kY, baseY, at);

  const [fT, fY] = await Promise.all([settle(flowAt(T, at, fetchText), null), settle(flowAt(Y, at, fetchText), null)]);
  const flow = fT && fY ? { t: fT, y: fY, foreignDiff: fT.외국인 - fY.외국인 } : null;
  if (flow) flow.judge = judge(flow.foreignDiff, TH.eok);

  const leaders = await Promise.all(LEADERS.map(async ([code, name]) => {
    const [bT, bY, pT, pY] = await Promise.all([
      settle(minuteBars('item', code, T, fetchJson, '0900', at), []),
      settle(minuteBars('item', code, Y, fetchJson, '0900', at), []),
      settle(prevClose('item', code, T, fetchJson), null),
      settle(prevClose('item', code, Y, fetchJson), null),
    ]);
    const tb = atOrBefore(bT, at), yb = atOrBefore(bY, at);
    const t = tb ? pct(tb.v, pT) : null, y = yb ? pct(yb.v, pY) : null;
    return {
      code, name, t, y, diff: t != null && y != null ? round2(t - y) : null,
      pxT: tb && tickOk(tb.v) ? tb.v : null, pxY: yb && tickOk(yb.v) ? yb.v : null,
    };
  }));
  const full = leaders.every((l) => l.t != null && l.y != null);
  const avg = full ? (() => {
    const t = round2(leaders.reduce((s, l) => s + l.t, 0) / leaders.length);
    const y = round2(leaders.reduce((s, l) => s + l.y, 0) / leaders.length);
    return { t, y, diff: round2(t - y), judge: judge(round2(t - y), TH.pctPoint) };
  })() : null;

  const [aT, aY, dict] = await Promise.all([
    settle(fetchJson(`${origin}/data/kospi-news-${dash}.json`), null),
    settle(fetchJson(`${origin}/data/kospi-news-${yDash}.json`), null),
    settle(fetchJson(`${origin}/data/issue-keywords.json`), null),
  ]);
  let issues = null;
  if (aT && aY && dict && Array.isArray(dict.keywords)) {
    const it = issuesUntil(aT, at), iy = issuesUntil(aY, at);
    const d = keywordDiff(iy, it, dict.keywords);
    issues = { y: iy, t: it, new: d.new, keep: d.keep };
  }

  return {
    status: 'ok',
    time: at.slice(0, 2) + ':' + at.slice(2),
    today: { date: dash, label: labelFromYmd(dash) },
    prev: { date: yDash, label: labelFromYmd(yDash), rel },
    verdict: verdict({ yLabel: rel, kospiDiff: kospi.diff, foreignDiff: flow ? flow.foreignDiff : null }),
    kospi, flow, leaders, avg, issues,
  };
}
```

- [ ] **Step 4: 통과 확인**

Run: `node --test api/_vs-intraday.test.mjs`
Expected: PASS (5 tests)

- [ ] **Step 5: 라우트 분기 추가**

`api/intraday.mjs` 두 번째 import 줄 아래에 추가:
```js
import { buildIntradayVs, getJson, getEucKr } from './_vs-intraday.mjs';
```

`export default async function handler(req, res) {` 바로 아래, 기존 `res.setHeader('Cache-Control', 's-maxage=30, ...')` 줄보다 **앞에** 추가:
```js
  // '어제랑 비교해서' 장중 대결판 — 라우트 12개 한도라 새 파일 대신 이 라우트에 분기한다(api/_route-budget.test.mjs)
  if (req.query && req.query.vs === 'intraday') {
    res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=60');
    res.setHeader('Access-Control-Allow-Origin', '*');
    try {
      const h = req.headers || {};
      const origin = `${h['x-forwarded-proto'] || 'https'}://${h['x-forwarded-host'] || h.host || 'doubleshot.space'}`;
      return res.status(200).json(await buildIntradayVs({ fetchJson: getJson, fetchText: getEucKr, origin }));
    } catch (e) {
      return res.status(502).json({ status: 'error', error: String(e) });
    }
  }
```

- [ ] **Step 6: 캐시 헤더 테스트에 새 분기 등록**

`api/_cache-headers.test.mjs`의 `POLLED` 배열 마지막 항목 뒤에 추가:
```js
  { name: 'intraday?vs', mod: './intraday.mjs', pollSec: 60, req: { query: { vs: 'intraday' }, headers: {} } },   // vs-yesterday.js 60초
```

- [ ] **Step 7: API 테스트 전체 + 린트**

Run: `node --test api/*.test.mjs && npx --yes eslint@9 api/`
Expected: 전부 PASS, 라우트 예산 테스트 그대로 통과(12개), eslint 오류 0

- [ ] **Step 8: 실측 한 번 확인(장중에만 의미 있다)**

평일 09:01~15:30에 실행:
```bash
node --input-type=module -e "
import { buildIntradayVs, getJson, getEucKr } from './api/_vs-intraday.mjs';
const d = await buildIntradayVs({ fetchJson: getJson, fetchText: getEucKr, origin: 'https://doubleshot.space' });
console.log(JSON.stringify({ s: d.status, time: d.time, prev: d.prev, verdict: d.verdict, kospi: d.kospi && [d.kospi.t, d.kospi.y, d.kospi.diff], flow: d.flow && d.flow.foreignDiff, avg: d.avg, issues: d.issues && d.issues.new }, null, 1));"
```
Expected: `status: 'ok'`. 코스피 `t`를 네이버 증권 화면의 코스피 등락률과 대조해 ±0.01%p 이내. 장 밖이면 `closed`.

- [ ] **Step 9: 커밋**

```bash
git add api/_vs-intraday.mjs api/_vs-intraday.test.mjs api/intraday.mjs api/_cache-headers.test.mjs
git commit -m "feat: 장중 대결판 API — /api/intraday?vs=intraday (라우트 추가 없이 분기)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: `web/assets/vs-yesterday.js` — 대결판 렌더와 폴링

**Files:**
- Create: `web/assets/vs-yesterday.js`
- Test: `web/assets/vs-yesterday.test.mjs`

**Interfaces:**
- Consumes: Task 5의 `Payload`, 페이지의 `<section id="vs-root" hidden>`
- Produces: `window.__vsIntraday = { render(payload), shouldPoll(), chartSvg(curveY, curveT) }`

- [ ] **Step 1: 실패하는 테스트 작성**

```js
// vs-yesterday.js 렌더·폴링 창 회귀 테스트 — node:vm 샌드박스에서 실제 파일을 로드한다(stocks-home.test.mjs와 같은 방식)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';

const noop = () => {};
function load(nowMs) {
  const root = { hidden: true, innerHTML: '' };
  const FixedDate = class extends Date { constructor(...a) { super(...(a.length ? a : [nowMs])); } static now() { return nowMs; } };
  const sb = {
    document: { getElementById: (id) => (id === 'vs-root' ? root : null), hidden: false, addEventListener: noop },
    fetch: () => Promise.reject(new Error('no network')),
    setInterval: noop, clearInterval: noop, setTimeout: noop, console: { log: noop, warn: noop, error: noop },
    Date: nowMs ? FixedDate : Date, Intl, Math, JSON, String, Number,
  };
  sb.window = sb;
  runInContext(readFileSync(new URL('./vs-yesterday.js', import.meta.url), 'utf8'), createContext(sb));
  return { api: sb.window.__vsIntraday, root };
}
const kst = (s) => Date.parse(s + 'Z') - 9 * 3600 * 1000;

const PAYLOAD = {
  status: 'ok', time: '11:00',
  today: { date: '2026-09-14', label: '9/14(월)' }, prev: { date: '2026-09-11', label: '9/11(금)', rel: '지난 금요일' },
  verdict: { title: '지난 금요일과 비슷해요', sub: '코스피가 같은 시각 기준 거의 같은 자리예요(−0.14%p) · 외국인 누적 순매수는 8,693억 원 적어요', judge: 'same' },
  kospi: { t: -2.56, y: -2.42, diff: -0.14, judge: 'same', curveT: [[0, -2], [120, -2.56]], curveY: [[0, -1.5], [120, -2.42]] },
  flow: { t: { 개인: 22500, 외국인: -20900, 기관: -6453 }, y: { 개인: 17100, 외국인: -12300, 기관: -10600 }, foreignDiff: -8600, judge: 'weak' },
  leaders: [{ code: '005930', name: '삼성전자', t: -2.89, y: -4.28, diff: 1.39, pxT: 252000, pxY: 257500 }],
  avg: null,
  issues: { y: [{ t: '10:00', title: '국제유가 급등 여파' }], t: [{ t: '10:30', title: '코스피, AI 속도 조절론·중동 불안에 급락' }], new: ['AI 속도 조절론', '중동'], keep: ['유가'] },
};

test('ok 응답이면 결론·비교 칸·달라진 것을 그린다', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  assert.equal(root.hidden, false);
  for (const s of ['지난 금요일 11:00 vs 오늘 11:00', '지난 금요일과 비슷해요', '오늘이 약함', '−2.56%', '252,000', 'vs-chip new', '<mark>중동</mark>', '외국인']) {
    assert.ok(root.innerHTML.includes(s), `빠짐: ${s}`);
  }
});

test('주도주 평균이 없으면 그 칸을 그리지 않는다(§0)', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  api.render(PAYLOAD);
  assert.ok(!root.innerHTML.includes('주도주 3종목 평균'));
});

test('closed·waiting·실패는 영역을 숨긴다', () => {
  const { api, root } = load(kst('2026-09-14T11:00:00'));
  for (const p of [{ status: 'closed' }, { status: 'waiting' }, null]) {
    root.hidden = false; api.render(p);
    assert.equal(root.hidden, true);
    assert.equal(root.innerHTML, '');
  }
});

test('폴링 창 — 평일 09:00~15:31만', () => {
  assert.equal(load(kst('2026-09-14T08:59:00')).api.shouldPoll(), false);
  assert.equal(load(kst('2026-09-14T09:00:00')).api.shouldPoll(), true);
  assert.equal(load(kst('2026-09-14T15:31:00')).api.shouldPoll(), true);
  assert.equal(load(kst('2026-09-14T15:32:00')).api.shouldPoll(), false);
  assert.equal(load(kst('2026-09-13T11:00:00')).api.shouldPoll(), false);
});

test('곡선 SVG — 두 선을 그린다', () => {
  const svg = load(kst('2026-09-14T11:00:00')).api.chartSvg(PAYLOAD.kospi.curveY, PAYLOAD.kospi.curveT);
  assert.equal((svg.match(/<path /g) || []).length, 2);
});
```

- [ ] **Step 2: 실패 확인**

Run: `node --test web/assets/vs-yesterday.test.mjs`
Expected: FAIL — `ENOENT ... vs-yesterday.js`

- [ ] **Step 3: 구현**

```js
// '어제랑 비교해서' 장중 대결판 — /api/intraday?vs=intraday 응답을 #vs-root에 그린다(설계 §4.2, 시안 v4)
(function () {
  var root = document.getElementById('vs-root');
  var JL = { same: '비슷해요', strong: '오늘이 셈', weak: '오늘이 약함' };
  var JC = { same: 'neutral', strong: 'up', weak: 'dn' };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function f2(n) { return n == null ? '—' : (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(2); }
  function cls(n) { return n > 0 ? 'up' : n < 0 ? 'dn' : ''; }
  function fmt(n) { return Number(n).toLocaleString('en-US'); }
  function eok(e) { var a = Math.abs(e), s = e > 0 ? '+' : e < 0 ? '−' : ''; return a >= 10000 ? s + (a / 10000).toFixed(2) + '조' : s + fmt(a) + '억'; }
  function pill(j) { return j ? '<span class="vs-pill ' + JC[j] + '">' + JL[j] + '</span>' : ''; }

  function chartSvg(yPts, tPts) {
    var W = 600, H = 180, all = [0];
    (yPts || []).concat(tPts || []).forEach(function (p) { all.push(p[1]); });
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), pad = (hi - lo) * 0.12 || 0.4;
    lo -= pad; hi += pad;
    function x(m) { return (m / 390 * W).toFixed(1); }
    function y(v) { return ((hi - v) / (hi - lo) * H).toFixed(1); }
    function path(pts) { return pts.map(function (p, i) { return (i ? 'L' : 'M') + x(p[0]) + ' ' + y(p[1]); }).join(''); }
    var zero = '<line x1="0" x2="' + W + '" y1="' + y(0) + '" y2="' + y(0) + '" class="vs-zero"/>';
    return '<svg class="vs-chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="코스피 곡선">' + zero +
      '<path d="' + path(yPts || []) + '" class="vs-line-y" vector-effect="non-scaling-stroke"/>' +
      '<path d="' + path(tPts || []) + '" class="vs-line-t" vector-effect="non-scaling-stroke"/></svg>';
  }

  function stat(title, j, yl, yv, yc, tv, tc, diff) {
    return '<div class="vs-stat"><div class="vs-stat-h"><span>' + title + '</span>' + pill(j) + '</div>' +
      '<div class="vs-stat-r"><span>' + esc(yl) + '</span><b class="' + yc + '">' + yv + '</b></div>' +
      '<div class="vs-stat-r"><span>오늘</span><b class="vs-big ' + tc + '">' + tv + '</b></div>' +
      '<p class="vs-diff">차이 ' + diff + '</p></div>';
  }

  function flowRows(d) {
    var keys = ['개인', '외국인', '기관'], mx = 1;
    keys.forEach(function (k) { mx = Math.max(mx, Math.abs(d.flow.t[k]), Math.abs(d.flow.y[k])); });
    function bar(v, kind) {
      var w = (Math.abs(v) / mx * 50).toFixed(2);
      return '<div class="vs-frow"><span class="vs-fl ' + (v < 0 ? (kind === 'now' ? 'dn' : 'muted') : '') + '">' + (v < 0 ? eok(v) : '') + '</span>' +
        '<div class="vs-ftrack"><i class="vs-fbar ' + kind + ' ' + cls(v) + '" style="' + (v >= 0 ? 'left' : 'right') + ':50%;width:' + w + '%"></i></div>' +
        '<span class="vs-fr ' + (v >= 0 ? (kind === 'now' ? 'up' : 'muted') : '') + '">' + (v >= 0 ? eok(v) : '') + '</span></div>';
    }
    return '<div class="vs-flow">' + keys.map(function (k) {
      return '<div class="vs-fgroup"><p class="vs-fname">' + k + '</p>' + bar(d.flow.t[k], 'now') + bar(d.flow.y[k], 'prev') + '</div>';
    }).join('') + '<p class="vs-flegend"><span><i class="now"></i>위 오늘 ' + d.time + '</span><span><i></i>아래 ' + esc(d.prev.rel) + ' ' + d.time + '</span></p></div>';
  }

  function render(d) {
    if (!root) return;
    if (!d || d.status !== 'ok') { root.hidden = true; root.innerHTML = ''; return; }
    var rel = esc(d.prev.rel), html = '';
    if (d.verdict) {
      html += '<div class="vs-hero"><p class="vs-eyebrow">🕘 ' + rel + ' ' + d.time + ' vs 오늘 ' + d.time + '</p>' +
        '<h2 class="' + (d.verdict.judge === 'strong' ? 'up' : d.verdict.judge === 'weak' ? 'dn' : '') + '">' + esc(d.verdict.title) + '</h2>' +
        '<p class="vs-sub">' + esc(d.verdict.sub) + '</p></div>';
    }
    var stats = '';
    if (d.kospi.diff != null) stats += stat('코스피', d.kospi.judge, d.prev.rel, f2(d.kospi.y) + '%', cls(d.kospi.y), f2(d.kospi.t) + '%', cls(d.kospi.t), f2(d.kospi.diff) + '%p');
    if (d.flow) stats += stat('외국인 누적 순매수', d.flow.judge, d.prev.rel, eok(d.flow.y['외국인']), cls(d.flow.y['외국인']), eok(d.flow.t['외국인']), cls(d.flow.t['외국인']), eok(d.flow.foreignDiff));
    if (d.avg) stats += stat('주도주 3종목 평균', d.avg.judge, d.prev.rel, f2(d.avg.y) + '%', cls(d.avg.y), f2(d.avg.t) + '%', cls(d.avg.t), f2(d.avg.diff) + '%p');
    html += '<div class="vs-card"><div class="vs-legend"><span><i class="y"></i>' + rel + ' 같은 시각까지</span><span><i class="t"></i>오늘</span><span class="r">코스피 · 전일 종가 대비</span></div>' +
      chartSvg(d.kospi.curveY, d.kospi.curveT) + '<div class="vs-axis"><span>09:00</span><span>11:00</span><span>13:00</span><span>15:30</span></div>' +
      (stats ? '<div class="vs-stats">' + stats + '</div>' : '') + '</div>';

    var changed = '';
    if (d.issues) {
      var mark = function (t) { var o = esc(t); d.issues.new.forEach(function (w) { o = o.split(esc(w)).join('<mark>' + esc(w) + '</mark>'); }); return o; };
      var list = function (a) { return a.length ? '<ul class="vs-issues">' + a.map(function (x) { return '<li><span>' + x.t + '</span><span>' + mark(x.title) + '</span></li>'; }).join('') + '</ul>' : '<p class="vs-empty">이 시각까지 수집된 이슈가 없어요.</p>'; };
      var chips = function (a, k) { return a.length ? a.map(function (w) { return '<span class="vs-chip ' + k + '">' + esc(w) + '</span>'; }).join('') : '<span class="vs-chip">없음</span>'; };
      changed += '<p class="vs-lbl">📰 장중 이슈</p>' +
        '<div class="vs-chips"><span class="vs-chips-k">새로 떠오름</span>' + chips(d.issues.new, 'new') + '</div>' +
        '<div class="vs-chips"><span class="vs-chips-k">계속 이어짐</span>' + chips(d.issues.keep, 'keep') + '</div>' +
        '<div class="vs-issue-cols"><div><p class="vs-col-h">' + rel + ' ' + esc(d.prev.label) + '</p>' + list(d.issues.y) + '</div>' +
        '<div><p class="vs-col-h">오늘 ' + esc(d.today.label) + '</p>' + list(d.issues.t) + '</div></div>';
    }
    var rows = d.leaders.filter(function (l) { return l.t != null || l.y != null; });
    if (rows.length) {
      changed += '<p class="vs-lbl">주도주 · 전일 종가 대비</p><div class="vs-table"><table><thead><tr><th>종목</th><th>' + rel + '</th><th>오늘</th><th>차이</th></tr></thead><tbody>' +
        rows.map(function (l) {
          return '<tr><td><b>' + esc(l.name) + '</b></td>' +
            '<td><span class="' + cls(l.y) + '">' + f2(l.y) + '%</span>' + (l.pxY != null ? '<small>' + fmt(l.pxY) + '</small>' : '') + '</td>' +
            '<td><span class="' + cls(l.t) + '">' + f2(l.t) + '%</span>' + (l.pxT != null ? '<small>' + fmt(l.pxT) + '</small>' : '') + '</td>' +
            '<td class="' + cls(l.diff) + '">' + (l.diff != null ? f2(l.diff) + '%p' : '—') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    if (d.flow) changed += '<p class="vs-lbl vs-center">투자자별 누적 순매수</p>' + flowRows(d);
    if (changed) html += '<div class="vs-card"><div class="vs-card-h"><p>' + withJosa(d.prev.rel) + ' 달라진 것</p><span>' + d.time + '까지 기준</span></div>' + changed + '</div>';

    root.innerHTML = html;
    root.hidden = false;
  }

  function withJosa(w) { var c = w.charCodeAt(w.length - 1) - 0xac00; return w + (c >= 0 && c < 11172 && c % 28 ? '과' : '와'); }

  function shouldPoll() {
    var k = new Date(Date.now() + 9 * 3600 * 1000), dow = k.getUTCDay(), m = k.getUTCHours() * 60 + k.getUTCMinutes();
    return dow >= 1 && dow <= 5 && m >= 540 && m <= 931;
  }

  function load() {
    if (!shouldPoll()) { render(null); return; }
    if (document.hidden) return;                       // 백그라운드 탭은 부르지 않는다(2026-08-16 차단 사고)
    fetch('/api/intraday?vs=intraday', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(render)
      .catch(function () { render(null); });
  }

  window.__vsIntraday = { render: render, shouldPoll: shouldPoll, chartSvg: chartSvg };
  if (!root) return;
  load();
  setInterval(load, 60000);
})();
```

- [ ] **Step 4: 통과 확인 + 린트**

Run: `node --test web/assets/vs-yesterday.test.mjs && npx --yes eslint@9 web/assets/vs-yesterday.js`
Expected: PASS (5 tests), eslint 오류 0

- [ ] **Step 5: 커밋**

```bash
git add web/assets/vs-yesterday.js web/assets/vs-yesterday.test.mjs
git commit -m "feat: 장중 대결판 화면 — 결론·코스피 곡선·비교 칸·달라진 것 렌더, 60초 폴링

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: 스타일 + 페이지 연결 + 제목 변경

**Files:**
- Create: `web/assets/vs-yesterday.css`
- Modify: `web/stocks/index.html:42` (h1), `:45` (설명), `:30` 뒤(CSS 링크), `:26` 뒤(JS), `#brief-strip` 바로 앞(`#vs-root`)

**Interfaces:**
- Consumes: Task 6의 클래스 이름(`vs-hero`, `vs-card`, `vs-stat`, `vs-pill`, `vs-chip`, `vs-issues`, `vs-table`, `vs-frow`, `vs-ftrack`, `vs-fbar`…), 사이트 변수 `--canvas --hair --ink --muted --primary --up --dn --up-bg --dn-bg --inset --s1`
- Produces: `/stocks/` 화면

- [ ] **Step 1: CSS 작성**

`web/assets/vs-yesterday.css` — 값은 시안 v4(지금 사이트 디자인)와 같다:
```css
/* '어제랑 비교해서' 장중 대결판 스타일 — 지금 사이트(stocks-home.css) 값 기준, vs- 접두로 기존 클래스와 분리 */
#vs-root{margin-bottom:12px}
.vs-hero,.vs-card{background:var(--canvas);border:1px solid var(--hair);border-radius:14px;box-shadow:var(--s1);padding:14px 16px}
.vs-hero + .vs-card,.vs-card + .vs-card{margin-top:12px}
.vs-eyebrow{font-size:12px;font-weight:700;color:var(--muted);margin:0 0 4px}
.vs-hero h2{font-size:18px;font-weight:800;letter-spacing:-.3px;line-height:1.35;color:#0F172A;margin:0}
.vs-hero h2.up,.up{color:var(--up)} .vs-hero h2.dn,.dn{color:var(--dn)}
.vs-sub{font-size:12px;color:var(--muted);margin:4px 0 0;line-height:1.55}
.vs-legend{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;font-size:11px;color:var(--muted);margin-bottom:8px}
.vs-legend i{display:inline-block;width:18px;border-top:2px solid #0F172A;vertical-align:middle;margin-right:6px}
.vs-legend i.y{border-top:2px dashed #CBD5E1}
.vs-legend .r{margin-left:auto}
.vs-chart{display:block;width:100%;height:180px}
.vs-zero{stroke:#CBD5E1;stroke-width:1}
.vs-line-y{fill:none;stroke:#CBD5E1;stroke-width:2;stroke-dasharray:6 5}
.vs-line-t{fill:none;stroke:#0F172A;stroke-width:2.5;stroke-linejoin:round}
.vs-axis{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-top:4px}
.vs-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px}
.vs-stat{background:#F7F9FC;border:1px solid var(--inset);border-radius:10px;padding:10px 12px}
.vs-stat-h{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:6px;font-size:11px;font-weight:600;color:var(--muted)}
.vs-stat-r{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font-size:11px;color:var(--muted)}
.vs-stat-r b{font-size:13px;font-variant-numeric:tabular-nums}
.vs-stat-r b.vs-big{font-size:17px;font-weight:800}
.vs-diff{margin:4px 0 0;text-align:right;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.vs-pill{font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;white-space:nowrap}
.vs-pill.neutral{color:var(--muted);background:#F1F5F9} .vs-pill.up{color:var(--up);background:var(--up-bg)} .vs-pill.dn{color:var(--dn);background:var(--dn-bg)}
.vs-card-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:11px}
.vs-card-h p{margin:0;font-size:15px;font-weight:800;color:#0F172A}
.vs-card-h span{font-size:11px;color:var(--muted)}
.vs-lbl{font-size:13px;font-weight:700;color:#0F172A;margin:16px 0 8px}
.vs-lbl:first-of-type{margin-top:0}
.vs-center{text-align:center}
.vs-chips{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.vs-chips + .vs-chips{margin-top:10px}
.vs-chips-k{width:84px;font-size:11px;color:var(--muted)}
.vs-chip{font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;color:var(--muted);background:#F1F5F9}
.vs-chip.new{color:#fff;background:#0F172A}
.vs-issue-cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px;margin-top:14px}
.vs-col-h{font-size:11px;color:var(--muted);margin:0 0 6px}
.vs-issues{list-style:none;margin:0;padding:0}
.vs-issues li{display:grid;grid-template-columns:40px minmax(0,1fr);gap:10px;padding:8px 0;border-top:1px solid #F1F5F9;font-size:13px}
.vs-issues li:first-child{border-top:0;padding-top:2px}
.vs-issues li span:first-child{font-size:11px;color:var(--muted)}
.vs-issues li span:last-child{font-weight:600;color:#0F172A;line-height:1.5}
.vs-issues mark{background:var(--up-bg);color:var(--up);border-radius:3px;padding:0 2px}
.vs-empty{font-size:13px;color:var(--muted);margin:0}
.vs-table{border:1px solid #EEF2F6;border-radius:10px;overflow-x:auto}
.vs-table table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
.vs-table th{padding:7px 10px;background:#FAFBFC;font-size:11px;font-weight:800;color:var(--muted);text-align:right;border-bottom:1px solid #EEF2F6;white-space:nowrap}
.vs-table td{padding:8px 10px;border-bottom:1px solid #EEF2F6;text-align:right;white-space:nowrap}
.vs-table tr:last-child td{border-bottom:0}
.vs-table th:first-child,.vs-table td:first-child{text-align:left}
.vs-table small{display:block;font-size:11px;color:#94A3B8}
.vs-flow{max-width:760px;margin:0 auto}
.vs-fgroup + .vs-fgroup{margin-top:14px}
.vs-fname{text-align:center;font-size:13px;font-weight:700;color:#0F172A;margin:0 0 6px}
.vs-frow{display:grid;grid-template-columns:72px minmax(0,1fr) 72px;align-items:center;column-gap:10px;font-size:11px;font-weight:700;font-variant-numeric:tabular-nums}
.vs-frow + .vs-frow{margin-top:5px}
.vs-fl{text-align:right} .vs-fr{text-align:left} .muted{color:var(--muted)}
.vs-ftrack{position:relative;height:8px;background:#F1F5F9;border-radius:999px}
.vs-ftrack::after{content:"";position:absolute;left:50%;top:-4px;bottom:-4px;width:1px;background:#CBD5E1}
.vs-fbar{position:absolute;top:0;bottom:0;border-radius:999px}
.vs-fbar.prev{background:#CBD5E1} .vs-fbar.now.up{background:var(--up)} .vs-fbar.now.dn{background:var(--dn)}
.vs-flegend{display:flex;justify-content:center;gap:14px;margin:14px 0 0;font-size:11px;color:var(--muted)}
.vs-flegend i{display:inline-block;width:12px;height:7px;border-radius:999px;background:#CBD5E1;margin-right:6px;vertical-align:middle}
.vs-flegend i.now{background:linear-gradient(90deg,var(--dn) 50%,var(--up) 50%)}
@media (max-width:760px){
  .vs-stats,.vs-issue-cols{grid-template-columns:minmax(0,1fr)}
  .vs-frow{grid-template-columns:60px minmax(0,1fr) 60px;column-gap:8px}
}
```

- [ ] **Step 2: index.html 수정**

42행 h1 전체를 교체:
```html
        <h1>종목 <span class="a">시그널</span>, 어제랑 비교해서</h1>
```
45행 설명을 교체:
```html
      <p>지금을 직전 거래일 같은 시각과 나란히 봐요</p>
```
`<link rel="stylesheet" href="/assets/flow-map.css?v=1">` 줄 아래에 추가:
```html
<link rel="stylesheet" href="/assets/vs-yesterday.css?v=1">
```
`<script src="/assets/flow-map.js?v=1" defer></script>` 줄 아래에 추가:
```html
<script src="/assets/vs-yesterday.js?v=1" defer></script>
```
`<a class="brief-card" id="brief-strip"` 바로 윗줄(`<!-- 더블샷 브리핑 커넥터 ...` 주석 위)에 추가:
```html
    <!-- '어제랑 비교해서' 장중 대결판 — 평일 09:01~15:30에만 vs-yesterday.js가 채운다. 그 밖엔 숨김(설계 §4.2) -->
    <section id="vs-root" hidden></section>
```

- [ ] **Step 3: 전체 테스트·린트**

Run:
```bash
node --test api/*.test.mjs && node --test web/assets/*.test.mjs && npx --yes eslint@9 web/assets/ api/ && python3 -m pytest scripts/ -q
```
Expected: 전부 PASS, eslint 오류 0. `ds-subnav.test.mjs`(index.html의 screen id 검사)도 그대로 통과한다 — `#vs-root`는 `.screen`이 아니다.

- [ ] **Step 4: 브라우저 확인**

`.claude/launch.json`에 정적 서버가 없으면 추가하고 `preview_start`로 연다(설정 예: `{"name":"stocks","runtimeExecutable":"npx","runtimeArgs":["--yes","vercel","dev","--listen","8790"],"port":8790}` — `api/`가 함께 돌아야 한다).
1. 장중(평일 09:01~15:30)이면 `/stocks/` 맨 위에 결론 카드 → 코스피 곡선 카드 → 달라진 것 카드가 보인다.
2. 장 밖이면 브라우저 콘솔에서 시안 응답을 넣어 모양을 확인한다.
   ```js
   fetch('/api/intraday?vs=intraday').then(r=>r.json()).then(console.log)   // 장 밖: {status:'closed'}
   ```
   그리고 Task 6 테스트의 `PAYLOAD`를 `window.__vsIntraday.render(PAYLOAD)`로 넣어 그린다.
3. 제목이 "종목 시그널, 어제랑 비교해서"이고 BETA가 없다.
4. 모바일(375px) — 가로 스크롤 없음(`document.documentElement.scrollWidth === innerWidth`), 비교 칸 1열.
5. 기존 하단 섹션(섹터별 대표 종목 · 자금 지도 · 특이 신호)이 그대로 아래에 있다.
6. 콘솔 오류 0.

- [ ] **Step 5: 커밋**

```bash
git add web/assets/vs-yesterday.css web/stocks/index.html .claude/launch.json
git commit -m "feat: /stocks/ 장중 대결판 연결 + 제목 '종목 시그널, 어제랑 비교해서'

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: 운영 규칙 문서 + 배포 + 실측 확인

**Files:**
- Modify: `docs/SERVICE_RULES.md` (파일 끝에 §49)

- [ ] **Step 1: §49 작성**

`docs/SERVICE_RULES.md` 끝에 추가:
```markdown
### 49. 종목 시그널 '어제랑 비교해서' — 장중 대결판 (2026-09-14 신설)

`/stocks/` 맨 위 `#vs-root`가 평일 09:01~15:30에 **직전 거래일 같은 시각**과 지금을 맞대 보여준다.
설계는 `docs/superpowers/specs/2026-09-14-stocks-vs-yesterday-design.md`, 구현 계획은 `docs/superpowers/plans/2026-09-14-vs-yesterday-plan1-intraday.md`.

- **라우트를 늘리지 않는다.** `/api/intraday?vs=intraday` 분기다(12/12 한도, §46). 계산은 `_vs-core`·`_vs-flow`·`_vs-prices`·`_vs-issues`·`_vs-intraday`.
- **판정·문장은 결정론이다.** ±0.3%p · ±1,000억 원 = "비슷해요". LLM이 끼지 않는다.
- **날짜 고정 조회.** 어제 값은 어제 날짜의 그 시각 이하 행만 쓴다. 없으면 그 칸을 비운다(§45).
- **수급은 합계 0 검사를 통과한 행만.** 개인+외국인+기관계+기타법인이 ±5억 밖이면 버린다 — 네이버 표의 열이 밀리면 여기서 걸린다.
- **1분봉 가격은 호가 단위 검사를 통과해야 숫자로 적는다.** 곡선에는 그대로 쓴다.
- **이슈 키워드 사전은 `web/data/issue-keywords.json`이다.** 사전에 없는 소재는 잡히지 않는다.
- **주도주 평균은 3종목이 모두 있을 때만.** 한 종목이라도 비면 칸을 그리지 않는다.
- **재발 시 진단 순서**: ① `/api/intraday?vs=intraday` 응답의 `status`와 null인 필드를 본다. ② 코스피 `kospi.t`를 네이버 증권 화면과 대조. ③ `flow`가 null이면 `investorDealTrendTime` 표 모양이 바뀌었는지(열 수 11, 합계 0) 확인.
```

- [ ] **Step 2: 커밋·푸시(작업 시간대 확인)**

```bash
TZ=Asia/Seoul date '+%H:%M'   # 07:25~07:45 · 16:25~16:50 · 21:15~21:40이면 기다린다(§43)
git add docs/SERVICE_RULES.md
git commit -m "docs: SERVICE_RULES §49 — '어제랑 비교해서' 장중 대결판 운영 규칙

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git pull --rebase origin main && git push origin main
```

- [ ] **Step 3: 배포 확인**

```bash
id=$(gh run list --workflow vercel-deploy.yml --limit 1 --json databaseId -q '.[0].databaseId'); gh run watch "$id" --exit-status
curl -s "https://doubleshot.space/api/intraday?vs=intraday" | python3 -m json.tool | head -30
curl -sI "https://doubleshot.space/api/intraday?vs=intraday" | grep -i cache-control
```
Expected: 배포 성공, 응답이 장중이면 `status: "ok"`·장 밖이면 `"closed"`, `cache-control`에 `s-maxage=60`.

- [ ] **Step 4: 다음 거래일 장중 실측 확인**

다음 평일 10:00 이후 `https://doubleshot.space/stocks/`를 열어 결론 카드의 코스피 차이와 네이버 증권 코스피 등락률(오늘·어제 같은 시각)을 대조한다. 어긋나면 §49 진단 순서대로 본다.

---

## 이 계획 다음(별도 계획으로 작성)

설계 문서 §3의 나머지 시간대는 각자 독립적으로 배포 가능한 단위라 계획을 나눈다. 모두 이 계획의 `_vs-core`·`_vs-prices`를 재사용한다.

| 계획 | 범위 | 먼저 필요한 것 |
| --- | --- | --- |
| 2. 애프터장 + 밤(17:00) | 15:40~17:00 애프터장 대결판, 17:00부터 미국 반도체 아래 애프터장 흐름 카드, 표의 "그 전 밤" 열 | 애프터장 1분봉·20:00 최종값 **저장 잡**(전 거래일 애프터장 1분봉 조회 여부 미확인 — 설계 §6 "새로 쌓아야 하는 기록") |
| 3. 장 시작 직후 | 07:30~09:00 저녁 신호 표, 09:00 시초가 방향 비교, 방향 일치 기록 | 계획 2의 애프터장 최종값 기록 |
| 4. 주말 | 이번 주 vs 지난주 비교 카드(추정가 타일·뉴스는 이미 사이트에 있음) | 없음 |
| 5. 시간대 탭 | 둘 이상 시간대가 생기면 밑줄형 탭으로 다른 시간대를 눌러 보기 | 계획 2 이상 완료 |

열린 질문(설계 §10) 1·2·6은 계획 2·3 작성 전에 정한다 — 주도주 타일과 대결판 주도주 표의 관계, 밤사이 브리지 흡수 여부, 평일 관련 뉴스·목표주가 위치.
