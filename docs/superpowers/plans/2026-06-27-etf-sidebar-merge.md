# ETF 사이드바 블록 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `web/stocks/index.html` 우측 사이드바의 "ETF로 읽는 시황" + "ETF 베팅 흐름"을 한 블록으로 합치고, 그 안에 거래량 톱5 ETF 행(실측)을 추가한다.

**Architecture:** 순수 프런트엔드 변경(HTML 구조 병합 + CSS 행 스타일 + JS 행 렌더 함수 1개 수정). 데이터 배선은 이미 존재한다 — `/api/vol-top`이 `etf` 배열을 반환하고, `renderTops(d)`가 `if(d.etf) renderEtf(d.etf)`로 `#etf-top-rows`를 채운다. 지금은 DOM에 `#etf-top-rows`가 없어 no-op일 뿐이다. DOM 타깃을 추가하고 행 형식을 4요소(순위·이름·거래량·등락률, 클릭 비활성)로 바꾼다.

**Tech Stack:** 정적 HTML/CSS/JS (단일 파일 `web/stocks/index.html`), node:test (기존 `api/_signals-core.test.mjs`, 데이터 계층 회귀 확인용)

설계 문서: `docs/superpowers/specs/2026-06-27-etf-sidebar-merge-design.md`

---

## 파일 변경 목록

| 파일 | 역할 | 변경 |
|------|------|------|
| `web/stocks/index.html` (CSS, ~line 180 부근) | 거래량 톱5 행 스타일 | `.etf-top5-*`, `.etf-top5-cap` 규칙 추가 |
| `web/stocks/index.html` (HTML, line 977–998) | 사이드바 블록 | ⓪+① 블록 병합, `#etf-top-rows`+캡션+"전체 랭킹" 링크 통합, 안전자산 블록의 링크 제거 |
| `web/stocks/index.html` (JS, line 2407–2409) | `etfVolRow` | 4요소 행·클릭 비활성·등락률 컬럼으로 재작성 |

> 단일 논리적 변경이므로 **마지막에 한 커밋**으로 묶는다 (CLAUDE.md #9).
> TDD 노트: 이 작업은 DOM/CSS 리팩터로 새 순수함수가 없다. 검증은 (1) 기존 node 테스트가 그대로 green (데이터 계층 무변경 확인) + (2) 프리뷰에서 mock 데이터 주입 렌더 확인으로 한다.

---

## Task 1: CSS — 거래량 톱5 행 스타일 추가

**Files:**
- Modify: `web/stocks/index.html` (CSS 블록, line 180 "ETF로 읽는 시황" CSS 그룹 끝 부근)

- [ ] **Step 1: `.etf-head-b b` 줄(line 179) 바로 뒤에 거래량 톱5 행 스타일 추가**

`web/stocks/index.html`의 line 179 (`.etf-head-b b{color:#0F172A;}`) 다음 줄에 아래를 삽입한다.

```css
/* ETF 거래량 톱5 행 (합친 시황 블록 내부) */
.etf-top5-cap{font-size:11px;font-weight:700;color:#94A3B8;padding:10px 16px 4px;background:var(--canvas);border-top:1px solid #F1F5F9;}
.row.etf-top5{cursor:default;}
.row.etf-top5:hover{background:var(--canvas);}
.etf-top5-nm{flex:1;min-width:0;font-size:13px;font-weight:700;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.etf-top5-vol{flex-shrink:0;font-size:11px;color:var(--muted);white-space:nowrap;}
.etf-top5-pct{flex-shrink:0;min-width:50px;text-align:right;font-size:12.5px;font-weight:800;white-space:nowrap;}
```

근거: `.row`(line 122)가 flex·gap·border·padding을 제공한다. `.row.etf-top5`로 hover 배경(`--primary-bg`)과 pointer를 무력화해 비클릭 행임을 표현한다. `.barwrap`은 사용하지 않으므로 `.home-side .barwrap{display:none}`(line 145) 영향 없음.

- [ ] **Step 2: 삽입 위치 확인**

Run: `grep -n "etf-top5-cap\|etf-top5-pct" "web/stocks/index.html"`
Expected: 2개 매치(CSS 정의). 아직 HTML/JS에는 없음.

---

## Task 2: HTML — 블록 병합 + DOM 타깃 추가

**Files:**
- Modify: `web/stocks/index.html` (line 977–998, `.home-side` 내부)

- [ ] **Step 1: ⓪ 시황 블록 + ① 베팅 흐름 블록을 하나로 병합**

아래 기존 블록(line 977–986)을

```html
    <!-- ⓪ ETF로 읽는 시황 (리드) -->
    <div class="block">
      <div class="block__h"><span class="block__t etf"><span class="ic">📊</span>ETF로 읽는 시황</span><span class="block__s"><span class="upd-badge" id="etf-upd-badge"></span></span></div>
      <div class="etf-head" id="etf-lead" style="margin-bottom:14px;"></div>
    </div>
    <!-- ① ETF 베팅 흐름 -->
    <div class="block">
      <div class="block__h"><span class="block__t etf"><span class="ic">⚖️</span>ETF 베팅 흐름</span></div>
      <div class="gauge-wrap" id="etf-betting"></div>
    </div>
```

다음으로 교체한다.

```html
    <!-- ⓪+① ETF로 읽는 시황 (시황 + 베팅 흐름 + 거래량 톱5 통합) -->
    <div class="block">
      <div class="block__h"><span class="block__t etf"><span class="ic">📊</span>ETF로 읽는 시황</span><span class="block__s"><span class="upd-badge" id="etf-upd-badge"></span></span></div>
      <div class="etf-head" id="etf-lead"></div>
      <div class="gauge-wrap" id="etf-betting"></div>
      <div class="etf-top5-cap">거래량 톱5 ETF · 실측</div>
      <div id="etf-top-rows"></div>
      <a class="more" onclick="go('ranking')">ETF 전체 랭킹 →</a>
    </div>
```

변경점: 두 `.block`을 한 `.block`으로 합침. `#etf-lead`의 인라인 `margin-bottom:14px` 제거(이제 마지막 요소가 아님). `⚖️ ETF 베팅 흐름` 서브헤더 제거(게이지 내부 `.bet-label`이 이미 "레버리지·인버스 ETF 거래대금"으로 설명). 신규 캡션 + `#etf-top-rows` + "전체 랭킹" 링크 추가.

- [ ] **Step 2: 안전자산 블록의 "ETF 전체 랭킹 →" 링크 제거**

블록 ③(안전자산 선호도) 내부의 아래 줄(기존 line 997)을 삭제한다.

```html
      <a class="more" onclick="go('ranking')">ETF 전체 랭킹 →</a>
```

삭제 후 안전자산 블록은 다음 형태가 된다.

```html
    <!-- ③ 안전자산 선호도 -->
    <div class="block">
      <div class="block__h"><span class="block__t etf"><span class="ic">🛟</span>안전자산 선호도</span></div>
      <div id="etf-safehaven"></div>
    </div>
```

- [ ] **Step 3: 구조 확인**

Run: `grep -c 'go(.ranking.)' "web/stocks/index.html"`
Expected: 사이드바 "ETF 전체 랭킹" 링크는 1개여야 함(합친 블록으로 이동, 안전자산에서 제거). 단, `go('ranking')`은 메인 컬럼의 "전체 랭킹 보기 →"(line 965)와 시그널 블록에도 쓰이므로 총 개수는 그대로 확인만 한다. `#etf-top-rows` 1개 존재 확인:
Run: `grep -c 'id="etf-top-rows"' "web/stocks/index.html"`
Expected: `1`

---

## Task 3: JS — `etfVolRow` 4요소 행으로 재작성

**Files:**
- Modify: `web/stocks/index.html` (line 2407–2409, `etfVolRow` 함수)

- [ ] **Step 1: `etfVolRow` 교체**

기존 함수(line 2407–2409)를

```js
  function etfVolRow(x,i){
    return '<a class="row" onclick="go(\'etf-detail\')"><span class="'+(i<3?'rk t num':'rk num')+'">'+(i+1)+'</span><div class="nm"><b>'+x.name+'</b><small class="num">'+x.code+' · ETF</small></div><div class="barwrap"><div class="bar vol" style="width:'+(x.barPct||0)+'%"></div></div><span class="barval num">'+manju(x.vol)+'</span></a>';
  }
```

다음으로 교체한다.

```js
  function etfVolRow(x,i){
    var pc=x.changePct>=0?'var(--up)':'var(--dn)',sg=x.changePct>=0?'+':'';
    return '<div class="row etf-top5">'
      +'<span class="'+(i<3?'rk t num':'rk num')+'">'+(i+1)+'</span>'
      +'<span class="etf-top5-nm">'+x.name+'</span>'
      +'<span class="etf-top5-vol num">'+manju(x.vol)+'</span>'
      +'<span class="etf-top5-pct num" style="color:'+pc+'">'+sg+x.changePct.toFixed(1)+'%</span>'
      +'</div>';
  }
```

변경점: `<a onclick="go('etf-detail')">` → `<div>` (클릭 비활성). `.barwrap`/`.bar.vol` 제거(사이드바에서 숨겨지므로 무의미). 등락률 컬럼(`.etf-top5-pct`, 색상 — 상승 `--up` 빨강 / 하락 `--dn` 파랑) 추가. 거래량은 `manju(x.vol)` 유지(기존 거래량 톱 표기와 일관). 억주 포맷은 범위 밖.

> `etfVolRow`는 `renderEtf`(line 2415–2417)의 `#etf-top-rows`에서만 사용된다. 다른 호출처 없음(`#etf-rise-rows`/`#etf-fall-rows`는 `etfChgRow`가 담당하며 홈 DOM에 없어 no-op).

- [ ] **Step 2: 함수 교체 확인**

Run: `grep -n "etf-top5-pct\|go(.etf-detail.)" "web/stocks/index.html"`
Expected: `etf-top5-pct`는 CSS 1 + JS 1 매치. `etfVolRow` 내부에는 `go('etf-detail')`가 더 이상 없음(다른 `etfChgRow` 등에는 남아 있을 수 있음 — `etfVolRow` 줄에 없으면 통과).

---

## Task 4: 검증 — 회귀 테스트 + 프리뷰 렌더

**Files:** (변경 없음 — 검증만)

- [ ] **Step 1: 데이터 계층 회귀 테스트**

Run: `node --test api/_signals-core.test.mjs`
Expected: 전부 PASS. (이 작업은 `etfBettingFlow`/`etfLead` 등 데이터 계층을 건드리지 않으므로 그대로 green이어야 함. 만약 fail이면 의도치 않은 변경.)

- [ ] **Step 2: 프리뷰 시작 + 페이지 로드**

`web/stocks/index.html`을 정적 서버로 프리뷰 시작한다(preview_start). 로컬에는 `/api/vol-top` 서버리스가 없어 실데이터는 안 들어오므로, 다음 Step에서 mock을 주입해 행 렌더를 검증한다.

- [ ] **Step 3: mock ETF 데이터 주입 후 거래량 톱5 렌더 확인**

preview_eval로 아래를 실행한다.

```js
renderEtf([
  {code:'114800',name:'KODEX 인버스',sector:'ETF',vol:1240000000,changePct:6.1},
  {code:'122630',name:'KODEX 레버리지',sector:'ETF',vol:320000000,changePct:-12.0},
  {code:'069500',name:'KODEX 200',sector:'ETF',vol:27000000,changePct:-6.0},
  {code:'305720',name:'KODEX 2차전지',sector:'ETF',vol:21000000,changePct:1.4},
  {code:'132030',name:'KODEX 골드선물',sector:'ETF',vol:18000000,changePct:0.9}
]);
document.getElementById('etf-top-rows').children.length;
```

Expected: 반환값 `5` (5개 행 렌더). preview_snapshot으로 순위·이름·거래량·등락률 4컬럼이 보이고, +6.1%는 빨강·-12.0%는 파랑인지 확인. 행 클릭 시 이동 없음(div, onclick 없음).

- [ ] **Step 4: 레이아웃 순서 + 링크 위치 시각 확인**

preview_screenshot으로 합친 블록이 `헤드라인(#etf-lead) → 게이지(#etf-betting) → 캡션 → 거래량 톱5 → "ETF 전체 랭킹 →"` 순인지, 그 아래 섹터 로테이션·안전자산 블록이 유지되는지, 안전자산 블록 끝에 더 이상 "전체 랭킹" 링크가 없는지 확인.

---

## Task 5: 커밋

**Files:** (위 변경 전체)

- [ ] **Step 1: 한 커밋으로 묶기**

```bash
git add web/stocks/index.html docs/superpowers/plans/2026-06-27-etf-sidebar-merge.md
git commit -m "$(cat <<'EOF'
feat(종목): ETF 사이드바 시황+베팅 흐름 통합 + 거래량 톱5 추가

- ETF로 읽는 시황 + ETF 베팅 흐름을 한 블록으로 병합
- 거래량 톱5 ETF 행(순위·이름·거래량·등락률 실측, 클릭 비활성) 추가
- etfVolRow 4요소 재작성, #etf-top-rows DOM 타깃 추가
- "ETF 전체 랭킹 →" 링크를 합친 블록으로 이전

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

> 푸시는 하지 않는다. 푸시 시 deploy.yml 자동 배포되므로 사용자 지시 시에만(메모리: feedback_commit_push_policy).

---

## Self-Review 결과

- **스펙 커버리지:** 헤드라인→게이지→톱5→링크 순서(Task 2), 톱5 4요소 실측·클릭 비활성(Task 1·3), 안전자산 링크 이전(Task 2 Step 2), 섹터/안전자산 유지(무변경) — 모두 태스크 존재.
- **Placeholder:** 없음. 모든 코드 블록은 실제 교체 문자열.
- **타입 일관성:** `etfVolRow`가 쓰는 `x.changePct`·`x.vol`·`x.name`은 `/api/vol-top` 반환 형(vol-top.mjs:28·48)과 일치. `renderEtf`의 `byVol` 정렬 입력과도 일치.
- **데이터 흐름:** `#etf-top-rows` DOM 추가만으로 기존 `renderTops→renderEtf` 배선이 활성화됨(검증: Task 4 Step 3 mock 주입).
