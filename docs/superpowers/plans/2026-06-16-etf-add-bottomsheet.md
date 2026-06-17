# ETF 추가 바텀시트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 인컴 설계기의 ETF 선택(사이드바 irow, 전체 보기 trow) 시 바텀시트가 올라와 ETF 정보 확인 + 수량 입력 후 시뮬레이터에 추가하는 UX를 구현한다.

**Architecture:** `income-designer.html` 단일 파일 안에 HTML(시트 DOM) + CSS(애니메이션) + JS(열기/닫기/렌더) 세 블록을 추가한다. 기존 `addFromRanking(code)` 시그니처를 `addFromRanking(code, qty)` 로 확장하고, irow·trow onclick을 `openAddSheet(code)` 로 변경한다.

**Tech Stack:** Vanilla JS, CSS transition, 기존 income-designer.html 인라인 스타일 컨벤션

---

## 파일 맵

| 역할 | 위치 |
|------|------|
| 수정 대상 | `docs/superpowers/specs/mockups/income-designer.html` |

---

### Task 1: 바텀시트 HTML 구조 추가

**Files:**
- Modify: `docs/superpowers/specs/mockups/income-designer.html` — `</body>` 바로 위에 삽입

- [ ] **Step 1: `</body>` 바로 위에 오버레이 + 시트 DOM 추가**

`</body>` 태그를 찾아 바로 위에 아래 HTML을 삽입한다.

```html
<!-- ===== ETF 추가 바텀시트 ===== -->
<div id="add-sheet-overlay" onclick="closeAddSheet()" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:299;"></div>
<div id="add-sheet" style="display:none;position:fixed;bottom:0;left:0;right:0;background:#fff;border-radius:16px 16px 0 0;z-index:300;transform:translateY(100%);transition:transform .25s ease-out;padding:0 0 env(safe-area-inset-bottom);">
  <div style="width:36px;height:4px;background:#E5E7EB;border-radius:2px;margin:10px auto 0;"></div>
  <div id="add-sheet-body" style="padding:16px 20px 20px;"></div>
</div>
```

- [ ] **Step 2: 브라우저에서 확인**

`http://localhost:8791/income-designer.html` 을 열어 DOM에 `#add-sheet`, `#add-sheet-overlay` 가 존재하는지 콘솔에서 확인한다.

```js
document.getElementById('add-sheet')  // → <div id="add-sheet" ...>
```

- [ ] **Step 3: 커밋**

```bash
git add docs/superpowers/specs/mockups/income-designer.html
git commit -m "feat: 인컴 설계기 — 바텀시트 HTML 구조 추가"
```

---

### Task 2: openAddSheet / closeAddSheet 함수 구현

**Files:**
- Modify: `income-designer.html` — 기존 `<script>` 블록 내 `addFromRanking` 함수 바로 위에 삽입

- [ ] **Step 1: `openAddSheet(code)` 함수 작성**

`addFromRanking` 함수(line ~945) 바로 위에 아래 코드를 삽입한다.

```js
function openAddSheet(code){
  const d=UNIV[code];
  if(!d)return;
  const [hc,hl]=incomeHealth(d);
  const ex=simHoldings.findIndex(h=>h.code===code);
  const alreadyQty=ex>=0?simHoldings[ex].qty:null;
  const ePct=d.r!=null?Math.round(d.r-d.y):null;
  const priceTxt=ePct==null?'—':`${ePct>=0?'+':''}${ePct}%`;
  const priceColor=ePct==null?'var(--muted)':ePct>=0?'#00ae1a':'#f33942';
  const metaTxt=d.mk==='US'
    ?`<span class="mk mk-us">US</span> ${d.code} · 순자산 ${d.aumLabel}`
    :`<span class="mk mk-kr">KR</span> ${d.code} · 순자산 ${d.aum.toFixed(1)}조`;
  const hcColors={ok:'background:#DCFCE7;color:#15803D',warn:'background:#FEF3C7;color:#92400E',bad:'background:#FEE2E2;color:#B91C1C',na:'background:#F3F4F6;color:#6B7280'};
  const alreadyNote=alreadyQty!=null
    ?`<div style="font-size:11px;color:#4F46E5;background:#EEF2FF;border-radius:6px;padding:6px 10px;margin-bottom:8px;">이미 ${alreadyQty}주 담겨 있어요. 수량을 변경할까요?</div>`
    :'';
  document.getElementById('add-sheet-body').innerHTML=`
    <div style="font-size:14px;font-weight:700;line-height:1.35;margin-bottom:4px;word-break:keep-all;">${d.name}</div>
    <div style="font-size:11px;color:var(--muted);margin-bottom:12px;">${metaTxt}</div>
    <div style="display:flex;gap:8px;margin-bottom:14px;">
      <div style="flex:1;background:#EEF2FF;border-radius:8px;padding:8px;text-align:center;">
        <div style="font-size:14px;font-weight:700;color:#4F46E5;">${d.y}%</div>
        <div style="font-size:10px;color:var(--muted);margin-top:2px;">연 분배율</div>
      </div>
      <div style="flex:1;background:#F8F9FA;border-radius:8px;padding:8px;text-align:center;">
        <div style="font-size:14px;font-weight:700;color:${priceColor};">${priceTxt}</div>
        <div style="font-size:10px;color:var(--muted);margin-top:2px;">1년 가격변화</div>
      </div>
      <div style="flex:1;border-radius:8px;padding:8px;text-align:center;${hcColors[hc]}">
        <div style="font-size:14px;font-weight:700;">${hl}</div>
        <div style="font-size:10px;margin-top:2px;opacity:.8;">건전성</div>
      </div>
    </div>
    ${alreadyNote}
    <div style="font-size:12px;font-weight:600;color:var(--ink);margin-bottom:6px;">몇 주 담을까요?</div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
      <input id="add-sheet-qty" type="number" min="1" step="1" value="100"
        style="flex:1;border:1.5px solid #4F46E5;border-radius:8px;padding:10px 12px;font-size:16px;font-weight:700;text-align:right;outline:none;font-family:inherit;"
        oninput="document.getElementById('add-sheet-confirm').disabled=!(+this.value>=1)">
      <span style="font-size:13px;color:var(--muted);">주</span>
    </div>
    <div style="display:flex;gap:8px;">
      <button onclick="closeAddSheet()" style="flex:1;background:#F3F4F6;color:#6B7280;border:none;border-radius:10px;padding:13px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;">취소</button>
      <button id="add-sheet-confirm" onclick="confirmAddSheet('${code}')"
        style="flex:2;background:#4F46E5;color:#fff;border:none;border-radius:10px;padding:13px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit;">시뮬레이터에 추가</button>
    </div>
  `;
  const overlay=document.getElementById('add-sheet-overlay');
  const sheet=document.getElementById('add-sheet');
  overlay.style.display='block';
  sheet.style.display='block';
  requestAnimationFrame(()=>requestAnimationFrame(()=>{sheet.style.transform='translateY(0)';}));
  setTimeout(()=>document.getElementById('add-sheet-qty')?.select(),300);
}
```

- [ ] **Step 2: `closeAddSheet()` 함수 작성**

`openAddSheet` 바로 아래에 추가한다.

```js
function closeAddSheet(){
  const sheet=document.getElementById('add-sheet');
  sheet.style.transform='translateY(100%)';
  setTimeout(()=>{
    sheet.style.display='none';
    document.getElementById('add-sheet-overlay').style.display='none';
  },260);
}
```

- [ ] **Step 3: `confirmAddSheet(code)` 함수 작성**

`closeAddSheet` 바로 아래에 추가한다.

```js
function confirmAddSheet(code){
  const qty=+document.getElementById('add-sheet-qty').value;
  if(qty<1)return;
  addFromRanking(code,qty);
  closeAddSheet();
}
```

- [ ] **Step 4: 브라우저에서 콘솔 테스트**

`http://localhost:8791/income-designer.html` 콘솔에서:

```js
openAddSheet('476550')   // TIGER 미국30년국채커버드콜액티브(H)
// → 바텀시트가 하단에서 올라오면 PASS
// → 분배율·1년 가격변화·건전성 칩 3개 보이면 PASS
closeAddSheet()
// → 시트가 내려가면 PASS
```

- [ ] **Step 5: 커밋**

```bash
git add docs/superpowers/specs/mockups/income-designer.html
git commit -m "feat: 인컴 설계기 — 바텀시트 open/close/confirm 함수 구현"
```

---

### Task 3: addFromRanking qty 파라미터 확장

**Files:**
- Modify: `income-designer.html` line ~945 `addFromRanking` 함수

- [ ] **Step 1: 함수 시그니처와 내부 로직 변경**

기존 코드:
```js
function addFromRanking(code){
  const ex=simHoldings.findIndex(h=>h.code===code);
  if(ex>=0)simHoldings[ex].qty+=100; else simHoldings.push({code,qty:100});
```

변경 후:
```js
function addFromRanking(code,qty=100){
  const ex=simHoldings.findIndex(h=>h.code===code);
  if(ex>=0)simHoldings[ex].qty=qty; else simHoldings.push({code,qty});
```

나머지 부분(saveHoldings·simRowsRender·simOut·하이라이트 애니메이션)은 그대로 유지.

- [ ] **Step 2: 브라우저에서 동작 확인**

콘솔에서:
```js
// 새 종목 추가
addFromRanking('JEPI', 300)
simHoldings.find(h=>h.code==='JEPI').qty  // → 300

// 기존 종목 수량 변경
addFromRanking('JEPI', 500)
simHoldings.find(h=>h.code==='JEPI').qty  // → 500 (합산 아님)
```

- [ ] **Step 3: 커밋**

```bash
git add docs/superpowers/specs/mockups/income-designer.html
git commit -m "feat: addFromRanking qty 파라미터 추가 — 바텀시트 수량 전달 지원"
```

---

### Task 4: irow · trow onclick을 openAddSheet로 교체

**Files:**
- Modify: `income-designer.html` — `incomeRender`의 `irow` (line ~822), `incomeAllPageRow`의 `trow` (line ~862)

- [ ] **Step 1: irow onclick 변경**

기존:
```js
return `<a class="irow" onclick="addFromRanking('${d.code}')">
```

변경 후:
```js
return `<a class="irow" onclick="openAddSheet('${d.code}')">
```

- [ ] **Step 2: trow onclick 변경**

기존:
```js
return `<a class="trow" onclick="addFromRankingPage('${d.code}')" ...>
```

변경 후:
```js
return `<a class="trow" onclick="openAddSheet('${d.code}')" ...>
```

`addFromRankingPage` 함수는 갈아타기·목표 전략 버튼에서 사용하지 않으므로 삭제하지 않고 그대로 둔다.

- [ ] **Step 3: 브라우저에서 전체 흐름 확인**

1. `http://localhost:8791/income-designer.html` 모바일 뷰(375px)로 열기
2. 사이드바 ETF 행 클릭 → 바텀시트 열림, ETF 정보 정확, 수량 입력 후 "추가" → 시뮬레이터에 반영 확인
3. "전체 보기" 열기 → ETF 행 클릭 → 바텀시트 열림, 추가 후 전체 보기 페이지 유지 확인
4. 이미 담긴 종목 재선택 → "이미 N주 담겨 있어요" 안내 문구 확인
5. 수량 0 입력 → "추가" 버튼 비활성화 확인
6. 딤 오버레이 클릭 → 시트 닫힘 확인

- [ ] **Step 4: 커밋**

```bash
git add docs/superpowers/specs/mockups/income-designer.html
git commit -m "feat: 인컴 설계기 ETF 선택 → 바텀시트 흐름 완성"
```
