# 밤사이 미국 반도체 시황 섹션 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 허브에서 17:00~익일 07:30 KST 동안 `상승 모멘텀 종목` 자리를 삼성·SK 연계 미국 반도체 시황(8종목 + 매크로 스트립 + 원/달러 토글)으로 교체한다.

**Architecture:** `web/stocks/index.html` 단일 파일에 인라인 섹션(`#us-evening`) 마크업 + IIFE JS를 추가한다. 데이터는 기존 `/api/stocks-live?us=`(미국 시세)와 `/api/market`(환율)만 사용 — 백엔드 변경 없음. 시간 게이트가 `#mom-track`↔`#us-evening`을 5분마다 토글한다. 정적 스냅샷 폴백은 두지 않고, 로딩 스켈레톤 + 라이브 fetch로 동작한다(스펙의 스코프 축소 옵션 채택).

**Tech Stack:** 바닐라 JS(허브 인라인 스크립트 관례), 기존 Vercel 서버리스 API, 프리뷰 기반 검증(허브 인라인 JS는 단위 테스트 하네스가 없어 `preview_*` 워크플로우로 검증 — 코드베이스 관례 준수).

---

## 검증 방식 안내

허브(`web/stocks/index.html`)의 UI 로직은 전부 인라인 스크립트라 단위 테스트 하네스가 없다. 본 프로젝트의 허브 UI 검증 표준은 `preview_start` → `preview_eval`(상태/시각 모킹) → `preview_screenshot`/`preview_console_logs`다. 각 태스크는 이 워크플로우로 검증한다.

서버는 정적(`python3 -m http.server --directory web`)이라 `/api/*`가 없다. 데이터 렌더 검증은 `preview_eval`로 `window.fetch`를 스텁해 정해진 응답을 주입하고 결과 DOM을 확인한다.

---

## 파일 구조

- Modify: `web/stocks/index.html`
  - 추가: `#us-evening` 섹션 마크업 + `<style>` + 렌더/토글/게이트 IIFE — `#mom-track` 블록(약 line 908~1006) 직후에 삽입.
  - 수정: `#mom-track`의 `loadPicks`(약 line 970~985) — 자체 `display` 제어를 `window.ueGate()`에 위임.
- 신규 파일 없음. 백엔드/스냅샷 변경 없음.

---

### Task 1: 섹션 마크업 + 스타일 (정적, 숨김)

**Files:**
- Modify: `web/stocks/index.html` (`#mom-track` 닫는 `</div>`와 그 `<script>` IIFE 종료 직후)

- [ ] **Step 1: `#mom-track` 블록의 끝 위치 확인**

Run: `grep -n "id=\"mom-track\"\|loadPicks\|momentum\|상승 모멘텀" web/stocks/index.html | head`
Expected: `#mom-track` 마크업과 그 IIFE `<script>`의 위치가 보인다. IIFE를 닫는 `})();` + `</script>` 바로 다음 줄을 삽입 지점으로 삼는다.

- [ ] **Step 2: 섹션 마크업 + 스타일 삽입**

`#mom-track` IIFE의 `</script>` 직후에 아래를 추가한다.

```html
<style>
#us-evening .ue-h{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;}
#us-evening #ue-toggle button{border:none;border-radius:0;padding:5px 12px;font-size:12px;font-weight:700;background:transparent;color:#64748B;cursor:pointer;}
#us-evening #ue-toggle button.on{background:#0F172A;color:#fff;}
#us-evening .ue-macro{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px;}
#us-evening .ue-mtile{background:#F7F9FC;border-radius:8px;padding:9px 11px;}
#us-evening .ue-mtile .l{font-size:12px;color:#64748B;}
#us-evening .ue-mtile .v{font-size:16px;font-weight:800;color:#0F172A;}
#us-evening .ue-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:0 18px;background:#FBFCFE;border:1px solid #EEF2F7;border-radius:12px;padding:6px 14px;}
#us-evening .ue-row{display:flex;align-items:center;justify-content:space-between;font-size:13px;padding:7px 0;border-bottom:1px solid #F1F5F9;}
#us-evening .ue-row .nm{flex:1;color:#0F172A;}
#us-evening .ue-row .tk{color:#94A3B8;font-size:12px;}
#us-evening .ue-row .lead{font-size:11px;color:#7C3AED;background:#F5F3FF;padding:1px 6px;border-radius:4px;margin-left:4px;}
#us-evening .ue-row .px{min-width:92px;text-align:right;color:#0F172A;font-weight:700;}
#us-evening .ue-row .cg{min-width:60px;text-align:right;}
#us-evening .ue-skel{height:13px;border-radius:5px;background:#EEF2F7;animation:uePulse 1.1s ease-in-out infinite;}
@keyframes uePulse{0%,100%{opacity:.45}50%{opacity:.9}}
</style>
<div id="us-evening" style="display:none;background:#fff;border:1px solid #E5E7EB;border-radius:14px;box-shadow:var(--s1);padding:15px 16px;margin-bottom:16px;">
  <div class="ue-h">
    <span style="font-size:15px;font-weight:800;color:#0F172A;">🌙 밤사이 미국 반도체 시황</span>
    <span style="font-size:11px;color:#94A3B8;">삼성전자·SK하이닉스 연계 · 17:00–07:30</span>
    <div id="ue-toggle" style="margin-left:auto;display:inline-flex;border:1px solid #CBD5E1;border-radius:8px;overflow:hidden;">
      <button type="button" data-cur="krw" class="on">원화</button>
      <button type="button" data-cur="usd">달러</button>
    </div>
  </div>
  <div class="ue-macro" id="ue-macro"></div>
  <div class="ue-grid" id="ue-grid"></div>
  <div id="ue-cap" style="font-size:11px;color:#94A3B8;margin-top:9px;">미국 장 시작 전엔 전일 종가, 장중엔 실시간 · DRAM ETF는 메모리·HBM 선행지표</div>
</div>
```

- [ ] **Step 3: 프리뷰로 마크업 존재 확인**

Run (preview): `preview_eval` →
```js
(function(){var e=document.getElementById('us-evening');return {exists:!!e, display:e&&getComputedStyle(e).display, hasGrid:!!document.getElementById('ue-grid'), toggleBtns:document.querySelectorAll('#ue-toggle button').length};})()
```
Expected: `{exists:true, display:"none", hasGrid:true, toggleBtns:2}`

- [ ] **Step 4: Commit**

```bash
git add web/stocks/index.html
git commit -m "feat(종목): 밤사이 미국 반도체 시황 섹션 마크업·스타일(숨김)"
```

---

### Task 2: 데이터 렌더 (스켈레톤 → fetch → 채움)

**Files:**
- Modify: `web/stocks/index.html` (Task 1에서 추가한 `#us-evening` 마크업 직후, 새 `<script>`)

- [ ] **Step 1: 렌더 IIFE 삽입**

`#us-evening` 닫는 `</div>` 직후에 아래 `<script>`를 추가한다. (게이트·토글·폴링은 Task 3·4에서 같은 IIFE에 덧붙인다 — 이 단계는 상수/스켈레톤/fetch/렌더까지.)

```html
<script>
(function(){
  var box=document.getElementById('us-evening');
  if(!box) return;
  var gridEl=document.getElementById('ue-grid'), macroEl=document.getElementById('ue-macro');
  var TICKERS=[
    {nm:'메모리·HBM', tk:'DRAM', sym:'DRAM.K', lead:true},
    {nm:'브로드컴',   tk:'AVGO', sym:'AVGO.O'},
    {nm:'엔비디아',   tk:'NVDA', sym:'NVDA.O'},
    {nm:'AMD',       tk:'AMD',  sym:'AMD.O'},
    {nm:'마이크론',   tk:'MU',   sym:'MU.O'},
    {nm:'ASML',      tk:'ASML', sym:'ASML.O'},
    {nm:'반도체ETF',  tk:'SOXX', sym:'SOXX.O'},
    {nm:'반도체ETF',  tk:'SMH',  sym:'SMH.O'}
  ];
  var NASDAQ='QQQ.O';
  var cur='krw', fx=null, dataBySym={}, loaded=false;
  function fmtPx(usd){
    if(typeof usd!=='number'||!isFinite(usd)) return '—';
    if(cur==='usd') return '$'+usd.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    if(!fx) return '—';
    return Math.round(usd*fx).toLocaleString('en-US')+'원';
  }
  function cgHtml(pct){
    if(typeof pct!=='number'||!isFinite(pct)) return '<span class="cg" style="color:#94A3B8">—</span>';
    var up=pct>0, col=up?'#E03131':(pct<0?'#2775ED':'#64748B'), s=up?'+':'';
    return '<span class="cg" style="color:'+col+'">'+s+pct.toFixed(2)+'%</span>';
  }
  function skeleton(){
    gridEl.innerHTML=TICKERS.map(function(){return '<div class="ue-row"><span class="nm"><span class="ue-skel" style="display:inline-block;width:90px;"></span></span><span class="ue-skel" style="width:70px;"></span></div>';}).join('');
    macroEl.innerHTML=['원/달러','나스닥 QQQ','필라델피아 반도체'].map(function(l){return '<div class="ue-mtile"><div class="l">'+l+'</div><div class="v"><span class="ue-skel" style="display:inline-block;width:54px;"></span></div></div>';}).join('');
  }
  function render(){
    gridEl.innerHTML=TICKERS.map(function(t){
      var d=dataBySym[t.sym]||{};
      return '<div class="ue-row"><span class="nm">'+t.nm+' <span class="tk">'+t.tk+'</span>'+(t.lead?' <span class="lead">선행</span>':'')+'</span>'
        +'<span class="px" data-usd="'+(d.price!=null?d.price:'')+'">'+fmtPx(d.price)+'</span>'+cgHtml(d.changePct)+'</div>';
    }).join('');
    var qq=dataBySym[NASDAQ]||{}, soxx=dataBySym['SOXX.O']||{};
    macroEl.innerHTML=''
      +'<div class="ue-mtile"><div class="l">원/달러</div><div class="v">'+(fx?fx.toLocaleString('en-US')+'원':'—')+'</div></div>'
      +'<div class="ue-mtile"><div class="l">나스닥 QQQ</div><div class="v">'+cgHtml(qq.changePct)+'</div></div>'
      +'<div class="ue-mtile"><div class="l">필라델피아 반도체</div><div class="v">'+cgHtml(soxx.changePct)+'</div></div>';
  }
  function load(){
    skeleton();
    var syms=TICKERS.map(function(t){return t.sym;}).concat([NASDAQ]).join(',');
    Promise.all([
      fetch('/api/stocks-live?us='+encodeURIComponent(syms),{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;}),
      fetch('/api/market',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;})
    ]).then(function(res){
      var live=res[0], mkt=res[1];
      if(live&&Array.isArray(live.us)) live.us.forEach(function(x){ dataBySym[x.sym]={price:x.price,changePct:x.changePct}; });
      if(mkt&&mkt.forex&&typeof mkt.forex.price==='number') fx=mkt.forex.price;
      if(!fx){ cur='usd'; syncToggle(); }
      loaded=true; render();
    });
  }
  window.__ueLoad=function(){ if(!loaded) load(); };
  function syncToggle(){}             // Task 3에서 실제 구현으로 교체
})();
</script>
```

- [ ] **Step 2: 프리뷰에서 fetch 스텁으로 렌더 검증**

정적 서버엔 `/api/*`가 없으므로 `window.fetch`를 스텁한 뒤 `window.__ueLoad()`를 호출한다.

Run (preview): `preview_eval` →
```js
(function(){
  var orig=window.fetch;
  window.fetch=function(u){
    if(u.indexOf('/api/stocks-live')>-1) return Promise.resolve({ok:true,json:function(){return Promise.resolve({us:[
      {sym:'DRAM.K',price:71.88,changePct:-6.52},{sym:'NVDA.O',price:192.53,changePct:-1.64},
      {sym:'SOXX.O',price:589.94,changePct:-5.64},{sym:'QQQ.O',price:706.52,changePct:-1.38}
    ]});}});
    if(u.indexOf('/api/market')>-1) return Promise.resolve({ok:true,json:function(){return Promise.resolve({forex:{price:1538}});}});
    return orig.apply(this,arguments);
  };
  document.getElementById('us-evening').style.display='';
  window.__ueLoad();
  return new Promise(function(res){ setTimeout(function(){
    var rows=document.querySelectorAll('#ue-grid .ue-row');
    res({rows:rows.length, firstPx:rows[0].querySelector('.px').textContent, nvdaPx:rows[2].querySelector('.px').textContent, macroFx:document.querySelector('#ue-macro .ue-mtile .v').textContent});
  },300); });
})()
```
Expected: `{rows:8, firstPx:"110,553원" (71.88*1538 반올림), nvdaPx:"296,111원", macroFx:"1,538원"}` (정확 값은 반올림에 따라 ±1)

- [ ] **Step 3: 콘솔 에러 없음 확인**

Run (preview): `preview_console_logs` level=error
Expected: 없음

- [ ] **Step 4: Commit**

```bash
git add web/stocks/index.html
git commit -m "feat(종목): 미국 반도체 시황 종목·매크로 렌더(스켈레톤+stocks-live+market)"
```

---

### Task 3: 원화/달러 토글

**Files:**
- Modify: `web/stocks/index.html` (Task 2 IIFE 내부 — `syncToggle` 실제 구현 + 버튼 바인딩)

- [ ] **Step 1: 토글 구현으로 교체**

Task 2 IIFE에서 `function syncToggle(){}` 한 줄을 아래로 교체하고, 그 아래(같은 IIFE의 닫기 `})();` 직전)에 바인딩을 추가한다.

```js
  function syncToggle(){
    document.querySelectorAll('#ue-toggle button').forEach(function(b){
      b.classList.toggle('on', b.getAttribute('data-cur')===cur);
    });
  }
  document.querySelectorAll('#ue-toggle button').forEach(function(b){
    b.addEventListener('click',function(){ cur=b.getAttribute('data-cur'); syncToggle(); render(); });
  });
  syncToggle();
```

(Task 2의 `function syncToggle(){}` 빈 껍데기를 위 실제 구현으로 교체하는 것이다. `window.__ueLoad`는 그대로 둔다.)

- [ ] **Step 2: 프리뷰에서 토글 동작 검증**

(Task 2 Step 2의 스텁 렌더가 끝난 상태에서 이어 실행)

Run (preview): `preview_eval` →
```js
(function(){
  function px(){return document.querySelector('#ue-grid .ue-row .px').textContent;}
  var krw=px();
  document.querySelector('#ue-toggle button[data-cur="usd"]').click();
  var usd=px();
  document.querySelector('#ue-toggle button[data-cur="krw"]').click();
  return {krw:krw, usd:usd, backToKrw:px(),
    usdOn:document.querySelector('#ue-toggle button[data-cur="krw"]').classList.contains('on')};
})()
```
Expected: `{krw:"110,553원", usd:"$71.88", backToKrw:"110,553원", usdOn:true}`

- [ ] **Step 3: Commit**

```bash
git add web/stocks/index.html
git commit -m "feat(종목): 미국 반도체 시황 원화/달러 토글"
```

---

### Task 4: 시간 게이트(#mom-track ↔ #us-evening) + 폴링

**Files:**
- Modify: `web/stocks/index.html`
  - Task 2 IIFE: 게이트 함수 + 폴링 추가.
  - `#mom-track`의 `loadPicks`(약 line 977~984): 자체 `display` 제어를 게이트에 위임.

- [ ] **Step 1: 게이트 + 폴링을 Task 2 IIFE에 추가**

Task 2 IIFE의 닫기 `})();` 직전에 추가한다.

```js
  function kstHm(){ var d=new Date(Date.now()+9*3600*1000); return d.getUTCHours()*60+d.getUTCMinutes(); }
  function isEvening(hm){ return hm>=1020 || hm<450; }   // 17:00~익일 07:30
  window.ueGate=function(){
    var ev=isEvening(kstHm());
    box.style.display = ev ? '' : 'none';
    var mt=document.getElementById('mom-track');
    if(mt) mt.style.display = ev ? 'none' : (window.__momHasPicks ? '' : 'none');
    if(ev) window.__ueLoad();
  };
  window.ueGate();
  setInterval(window.ueGate, 5*60*1000);   // 5분마다 재평가(허브 표준 주기)
  setInterval(function(){ if(isEvening(kstHm()) && loaded) load(); }, 60000); // 미국 장중 가격 갱신
```

- [ ] **Step 2: `#mom-track` loadPicks를 게이트에 위임**

`web/stocks/index.html`의 `loadPicks` 내부에서 `box.style.display`를 직접 만지는 곳을 수정한다. 현재 코드:

```js
            if(!PICKS.length){ box.style.display='none'; return; }
            grid.innerHTML=PICKS.map(cardHTML).join('');
            box.style.display='';
```
를 아래로 바꾼다(여기서 `box`는 mom-track 자신의 변수다):

```js
            window.__momHasPicks = PICKS.length>0;
            if(!PICKS.length){ window.ueGate&&window.ueGate(); return; }
            grid.innerHTML=PICKS.map(cardHTML).join('');
            window.ueGate ? window.ueGate() : (box.style.display='');
```

그리고 같은 함수의 실패 콜백 `.catch(function(){ box.style.display='none'; });` 을 아래로 바꾼다:

```js
          }).catch(function(){ window.__momHasPicks=false; window.ueGate&&window.ueGate(); });
```

- [ ] **Step 3: 프리뷰에서 시간 게이트 토글 검증**

`kstHm`/`isEvening`은 IIFE 클로저라 직접 못 부르므로, `window.ueGate`가 실제 KST에 따라 토글하는지 확인하고, 시각 경계 로직은 별도 순수 검증으로 확인한다.

Run (preview): `preview_eval` →
```js
(function(){
  function isEvening(hm){ return hm>=1020||hm<450; }
  return {
    at1659:isEvening(16*60+59), at1700:isEvening(17*60),
    at0729:isEvening(7*60+29), at0730:isEvening(7*60+30),
    momDisplay:(document.getElementById('mom-track')||{}).style ? getComputedStyle(document.getElementById('mom-track')).display : 'n/a',
    ueDisplay:getComputedStyle(document.getElementById('us-evening')).display
  };
})()
```
Expected: `{at1659:false, at1700:true, at0729:true, at0730:false, ...}` — 현재 KST가 저녁창이면 `ueDisplay!=="none"` & `momDisplay==="none"`, 아니면 반대.

- [ ] **Step 4: 저녁창 강제 스크린샷(증빙)**

Run (preview): `preview_eval` → (Task 2 Step 2 스텁이 적용된 상태에서) `document.getElementById('us-evening').scrollIntoView({block:'center'}); 'ok'`
Run (preview): `preview_screenshot`
Expected: 매크로 스트립 3타일 + 종목 8행이 보이고, `#mom-track`은 숨김.

- [ ] **Step 5: 콘솔 에러 없음 + Commit**

Run (preview): `preview_console_logs` level=error → 없음
```bash
git add web/stocks/index.html
git commit -m "feat(종목): 미국 반도체 시황 시간게이트(17:00~07:30)·폴링·모멘텀 자리 교체"
```

---

### Task 5: 반응형·통합 최종 확인

**Files:** 없음(검증 전용)

- [ ] **Step 1: PC 2단 / 모바일 1단 확인**

Run (preview): `preview_resize` preset=mobile → `preview_screenshot` (1단 스택 확인)
Run (preview): `preview_resize` preset=desktop → `preview_screenshot` (그리드 2단 확인)
Expected: 모바일에서 `.ue-grid`가 1열, 데스크톱에서 2열. 카드가 컨테이너를 넘지 않음.

- [ ] **Step 2: 주간 시간대에서 모멘텀 복귀 확인**

`window.ueGate`가 저녁이 아닐 때 `#us-evening`을 숨기고 `#mom-track`을 `__momHasPicks`에 따라 보이는지 확인(실제 KST가 주간이면 자연 검증, 저녁이면 코드 리뷰로 확인).

Run (preview): `preview_eval` →
```js
(function(){ return {momHasPicks:window.__momHasPicks, ue:getComputedStyle(document.getElementById('us-evening')).display, mt:getComputedStyle(document.getElementById('mom-track')).display}; })()
```
Expected: 저녁창이면 `ue!=="none" && mt==="none"`, 주간이면 `ue==="none"` 이고 `mt`는 picks 유무에 따름.

- [ ] **Step 3: 최종 Commit (변경 없으면 생략)**

검증만이면 커밋 없음. 미세 수정이 있었으면:
```bash
git add web/stocks/index.html
git commit -m "fix(종목): 미국 반도체 시황 반응형·통합 보정"
```

---

## 자가 점검 결과

- **스펙 커버리지**: 시간게이팅(Task 4) · 종목 8개+심볼 매핑(Task 2) · 매크로 스트립(Task 2) · 원/달러 토글(Task 3) · 데이터 소스 stocks-live+market(Task 2) · PC2단/모바일1단(Task 1 스타일+Task 5) · 모멘텀 자리 교체(Task 4) — 모두 태스크 존재.
- **정적 폴백(스냅샷 확장)**: 스펙의 스코프 축소 옵션을 채택해 제외(스켈레톤+라이브로 대체). 추후 필요 시 별도 계획.
- **타입 일관성**: `dataBySym[sym]={price,changePct}`, `fx`(number), `cur`('krw'|'usd'), `window.ueGate`/`window.__ueLoad`/`window.__momHasPicks` — 태스크 간 명칭 일치. Task 3에서 Task 2의 임시 헬퍼(`__ueRerender`·`__ueSetCur`·`__ueSyncToggle`) 제거를 명시.
- **플레이스홀더 없음**: 모든 코드 단계에 실제 코드 포함.

## 비범위 (YAGNI)

- 스냅샷 정적 폴백, 미국 휴장 캘린더 정밀 판정, 종목별 미니차트, 타 섹터(자동차·로봇) 연계.
