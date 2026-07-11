# 종목 신호 사이드바 위젯 Implementation Plan (Stage B 슬라이스8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 오전 브리핑 사이드바에 `/api/signals`를 소비하는 라이브 종목 신호 위젯(상위 3개)을 성적표 카드 아래에 추가한다.

**Architecture:** 서버(Python) 변경 없음. 신규 껍데기 템플릿(`_stock_signals.html`)을 kospi.html 사이드바에 include하고, `main.js`의 `initStockSignals()`가 페이지 로드 시 `/api/signals`를 fetch(장중 60초 폴링)해 `phase`로 헤더/힌트를 토글하고 상위 3개 신호를 렌더한다. 상태 판정(과거/미래 브리핑 숨김)은 기존 `initNowBand`의 URL 날짜 파싱 패턴을 그대로 재사용한다.

**Tech Stack:** Jinja2 템플릿, 바닐라 JS(ES5 스타일, 기존 main.js 관례), CSS 변수 테마(style.css).

---

## 배경: 기존 코드 재사용 지점

- **`/api/signals` 응답 형태** (`api/signals.mjs` handler):
  ```
  { phase: 'intraday'|'closed', asOf:{date,label,isToday}, kospiPct,
    signals: [{code,name,sector,pct,dir:'up'|'dn',cats:[..],badges:[..],why}],  // 점수순 정렬됨
    signalsAll: [...], etf:{...}, ... }
  ```
  - `cats` 카테고리 키: `vol_surge`/`counter_up`/`near_high`/`turnover`/`inst_buy`/`foreign_buy`/`foreign_sell` (`api/_signals-core.mjs` `SIGNAL_META`)
  - `badges[i]`는 `cats[i]`에 대응하는 한글 라벨(예: "거래량 급증", "기관 순매수").
- **URL 날짜 파싱 + isPast 판정**: `main.js:1928-1931` (`initNowBand` 내부) 패턴을 복제.
- **load 핸들러 등록**: `main.js:828` `initNowBand();` 다음 줄에 `initStockSignals();` 추가.
- **escHtml**: main.js에 이미 정의된 전역 헬퍼(밴드 이슈 렌더에서 사용 중, `main.js:2039`).
- **CSS 변수**: `--gold`/`--gold-bg`, `--primary`/`--primary-bg`, `--up`/`--dn`, `--muted`, `--hairline`, `--surface-soft`, `--canvas` (style.css:7-22). 초록은 `#16A34A`(style.css 여러 곳에서 사용하는 관례값) 사용.

## File Structure

- **Create** `scripts/templates/sections/_stock_signals.html` — 껍데기 마크업(초기 hidden). 행은 JS가 채움.
- **Modify** `scripts/templates/briefings/kospi.html:51` — scorecard include 다음 줄에 신규 include 추가.
- **Modify** `web/assets/style.css` — `.ssig-*`(카드·행·배지·힌트) 클래스 추가.
- **Modify** `web/assets/main.js` — `initStockSignals()` 함수 추가 + load 핸들러(:828)에 호출 등록.
- **정적 산출물 재생성**: 기존 코스피 브리핑 HTML은 `generate_html.py`로 재생성해야 include가 반영됨(검증 단계에서 확인).

## 검증 전략 (mock 하니스)

라이브 폴링은 Vercel serverless가 필요해 로컬에서 직접 못 돈다. 슬라이스6과 동일하게
`window.fetch`를 mock해 `/api/signals` 샘플 JSON을 주입하는 standalone HTML 하니스로 렌더를 검증한다.
하니스는 스크래치패드에 만들고 커밋하지 않는다.

---

### Task 1: 껍데기 템플릿 생성

**Files:**
- Create: `scripts/templates/sections/_stock_signals.html`

- [ ] **Step 1: 템플릿 파일 작성**

```html
{# 종목 신호 사이드바 위젯 — /api/signals 상위 3개 라이브 렌더. 코스피 전용. #}
{# 기본 hidden. main.js initStockSignals()가 과거/미래 브리핑·주말·데이터 없음이면 계속 숨기고, #}
{# 데이터가 있을 때만 phase(장중/마감)로 헤더·힌트를 토글해 노출한다. 날짜는 URL에서 파싱. #}
<div class="ssig" id="stock-signals" hidden>
  <div class="ssig__h"><span class="ssig__dot"></span><span id="ssig-title">오늘의 종목 신호</span><small class="ssig__note" id="ssig-note" hidden>지난 마감 기준</small></div>
  <div class="ssig__list" id="ssig-list"></div>
  <div class="ssig__hint" id="ssig-hint" hidden>실시간 신호는 09:00 장 시작부터 갱신돼요.</div>
  <a class="ssig__cta" href="/stocks/#signals-all">종목 신호 전체 보기 <span>→</span></a>
</div>
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/sections/_stock_signals.html
git commit -m "feat(코스피 브리핑): 종목 신호 위젯 껍데기 템플릿 — Stage B 슬라이스8"
```

---

### Task 2: CSS 추가

**Files:**
- Modify: `web/assets/style.css` (파일 끝에 블록 추가)

- [ ] **Step 1: 스타일 블록 추가**

`style.css` 맨 끝에 다음을 추가한다(기존 `.sc-card`·`.subcard` 사이드바 카드 관례와 동일한 톤):

```css
/* 종목 신호 사이드바 위젯 (코스피 브리핑) — /api/signals 상위 3개 라이브 */
.ssig{border:1px solid var(--hairline);border-radius:var(--r-lg);background:var(--canvas);box-shadow:var(--s1);overflow:hidden;}
.ssig__h{display:flex;align-items:center;gap:6px;padding:13px 16px 4px;font-size:13px;font-weight:800;color:var(--ink);}
.ssig__dot{width:6px;height:6px;border-radius:50%;background:var(--gold);flex:none;}
.ssig__note{margin-left:auto;font-size:10.5px;font-weight:600;color:var(--muted);}
.ssig__list{display:flex;flex-direction:column;padding:6px 0 2px;}
.ssig-row{display:flex;align-items:center;gap:9px;padding:9px 16px;text-decoration:none;border-top:1px solid var(--hairline);}
.ssig-row:first-child{border-top:none;}
.ssig-row:hover{background:var(--surface-soft);}
.ssig-name{font-size:13px;font-weight:700;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:96px;}
.ssig-badge{font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:5px;white-space:nowrap;}
.ssig-badge.gold{background:var(--gold-bg);color:var(--gold);}
.ssig-badge.blue{background:var(--primary-bg);color:var(--primary);}
.ssig-badge.green{background:rgba(22,163,74,.12);color:#16A34A;}
.ssig-chg{margin-left:auto;font-size:12.5px;font-weight:800;font-variant-numeric:tabular-nums;}
.ssig-chg.up{color:var(--up);}.ssig-chg.dn{color:var(--dn);}
.ssig__hint{font-size:11px;color:var(--muted);padding:6px 16px 2px;font-style:italic;line-height:1.5;}
.ssig__cta{display:flex;align-items:center;justify-content:space-between;padding:11px 16px;font-size:12px;font-weight:700;color:var(--primary);text-decoration:none;border-top:1px solid var(--hairline);}
.ssig__cta:hover{background:var(--surface-soft);}
```

- [ ] **Step 2: 커밋**

```bash
git add web/assets/style.css
git commit -m "feat(코스피 브리핑): 종목 신호 위젯 스타일 — Stage B 슬라이스8"
```

---

### Task 3: initStockSignals() JS 구현 + 배선

**Files:**
- Modify: `web/assets/main.js` (신규 함수 추가 + `:828` 호출 등록)

- [ ] **Step 1: `initNowBand` 함수 정의 끝(`main.js:2075` `}` 다음)에 `initStockSignals` 추가**

```javascript
  /* ── 종목 신호 사이드바 위젯 — /api/signals 상위 3개. 코스피 브리핑 전용.
     과거/미래 브리핑·데이터 없음이면 숨김. phase로 장중/마감 헤더·힌트 토글. ── */
  function initStockSignals() {
    var box = document.getElementById('stock-signals');
    if (!box) return;

    function kstNow() { return new Date(Date.now() + 9 * 3600 * 1000); }
    var k0 = kstNow();
    var todayKst = k0.getUTCFullYear() + '-' +
      String(k0.getUTCMonth() + 1).padStart(2, '0') + '-' +
      String(k0.getUTCDate()).padStart(2, '0');
    var m = location.pathname.match(/\/briefings\/(\d{4}-\d{2}-\d{2})\//);
    var urlDate = m ? m[1] : todayKst;
    if (urlDate !== todayKst) return;   // 과거·미래 브리핑: 신호는 '오늘' 값만 의미 → 숨김

    var CAT_COLOR = {
      vol_surge: 'gold', turnover: 'gold',
      inst_buy: 'blue', foreign_buy: 'blue', foreign_sell: 'blue',
      near_high: 'green', counter_up: 'green'
    };

    function render(data) {
      if (!data || !Array.isArray(data.signals) || !data.signals.length) return;
      var top = data.signals.slice(0, 3);
      var closed = data.phase === 'closed';

      var title = document.getElementById('ssig-title');
      var note = document.getElementById('ssig-note');
      var hint = document.getElementById('ssig-hint');
      if (title) title.textContent = closed ? '지난 장 포착 신호' : '오늘의 종목 신호';
      if (note) note.hidden = !closed;
      if (hint) hint.hidden = !closed;

      var rows = top.map(function (s) {
        var color = CAT_COLOR[(s.cats || [])[0]] || 'gold';
        var badge = (s.badges || [])[0] || '';
        var pct = Number(s.pct) || 0;
        var dir = pct >= 0 ? 'up' : 'dn';
        var pctTxt = (pct > 0 ? '+' : '') + pct.toFixed(1) + '%';
        return '<a class="ssig-row" href="/stocks/' + encodeURIComponent(s.code) + '/">'
          + '<span class="ssig-name">' + escHtml(s.name || '') + '</span>'
          + '<span class="ssig-badge ' + color + '">' + escHtml(badge) + '</span>'
          + '<span class="ssig-chg ' + dir + '">' + pctTxt + '</span></a>';
      }).join('');
      var list = document.getElementById('ssig-list');
      if (list) list.innerHTML = rows;
      box.hidden = false;
    }

    function poll() {
      fetch('/api/signals', { signal: AbortSignal.timeout(8000) })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(render).catch(function () {});
    }
    poll();
    setInterval(poll, 60000);
  }
```

- [ ] **Step 2: load 핸들러에 호출 등록 — `main.js:828`**

`initNowBand();` 다음 줄에 추가:

```javascript
    initNowBand();
    initStockSignals();
    loadLeadersWidget();
```

- [ ] **Step 3: 커밋**

```bash
git add web/assets/main.js
git commit -m "feat(코스피 브리핑): initStockSignals — /api/signals 상위 3개 라이브 배선 — Stage B 슬라이스8"
```

---

### Task 4: kospi.html에 include

**Files:**
- Modify: `scripts/templates/briefings/kospi.html:51`

- [ ] **Step 1: scorecard include 다음 줄에 신규 include 추가**

현재(kospi.html:49-53):
```jinja
    <aside class="layout-grid__right">
      {% if market_items %}{% include "sections/market_data.html" %}{% endif %}
      {% if scorecard %}{% include "sections/_scorecard.html" %}{% elif accuracy %}{% include "sections/accuracy.html" %}{% endif %}
      {% include "sections/_sidebar_kospi.html" %}
    </aside>
```

변경 후 — scorecard 줄과 _sidebar_kospi 줄 사이에 삽입:
```jinja
    <aside class="layout-grid__right">
      {% if market_items %}{% include "sections/market_data.html" %}{% endif %}
      {% if scorecard %}{% include "sections/_scorecard.html" %}{% elif accuracy %}{% include "sections/accuracy.html" %}{% endif %}
      {% include "sections/_stock_signals.html" %}
      {% include "sections/_sidebar_kospi.html" %}
    </aside>
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/briefings/kospi.html
git commit -m "feat(코스피 브리핑): 종목 신호 위젯 사이드바 배치(scorecard 아래) — Stage B 슬라이스8"
```

---

### Task 5: mock 하니스로 렌더 검증

**Files:**
- Create(비커밋): 스크래치패드 `ssig-harness.html`

- [ ] **Step 1: 하니스 작성**

스크래치패드(`/private/tmp/.../scratchpad/ssig-harness.html`)에 작성. `window.fetch`를 mock해
`/api/signals`에 intraday 샘플을 반환하고, `_stock_signals.html` 마크업 + `.ssig-*` CSS +
`initStockSignals()`만 인라인으로 로드한다. `location.pathname`은 오늘 날짜 브리핑 경로로 설정
(하니스에서 `initStockSignals` 내부 `urlDate===todayKst`를 통과시키기 위해 함수 상단의
`location.pathname.match(...)`가 today로 잡히도록 경로 없이 두면 `urlDate=todayKst`가 되어 통과).

샘플 intraday JSON:
```json
{ "phase":"intraday",
  "signals":[
    {"code":"042700","name":"한미반도체","pct":5.2,"dir":"up","cats":["vol_surge"],"badges":["거래량 급증"]},
    {"code":"034020","name":"두산에너빌리티","pct":3.1,"dir":"up","cats":["foreign_buy"],"badges":["외국인 순매수"]},
    {"code":"196170","name":"알테오젠","pct":-2.4,"dir":"dn","cats":["near_high"],"badges":["52주 신고가 근접"]},
    {"code":"005930","name":"삼성전자","pct":1.0,"dir":"up","cats":["turnover"],"badges":["거래대금 상위"]}
  ] }
```

- [ ] **Step 2: 브라우저 프리뷰로 렌더 확인**

`preview_start`로 하니스 열기 → `read_page`로 확인:
- Expected: 헤더 "오늘의 종목 신호", 힌트 숨김, 3행만 표시(4번째 삼성전자 제외),
  배지 색 gold/blue/green, 등락률 up(+5.2%)/dn(−값), 종목명 링크 `/stocks/042700/`.

- [ ] **Step 3: closed·빈 signals 케이스 확인**

하니스의 mock 응답을 `phase:"closed"`로 바꿔 재확인:
- Expected: 헤더 "지난 장 포착 신호" + note "지난 마감 기준" 노출 + 힌트 노출.

`signals:[]`로 바꿔 재확인:
- Expected: `#stock-signals`가 계속 `hidden`(box.hidden=false 호출 안 됨).

- [ ] **Step 4: 다크 모드 확인**

`resize_window`로 `colorScheme:'dark'` → 배지·행 대비 확인.

---

### Task 6: 실제 코스피 브리핑 HTML 재생성 확인

**Files:**
- (검증만) 최신 코스피 브리핑 `web/briefings/{date}/kospi/index.html`

- [ ] **Step 1: 최신 코스피 브리핑 날짜 확인**

```bash
ls -d web/briefings/*/kospi 2>/dev/null | tail -3
```

- [ ] **Step 2: 스냅샷 있는 최신 날짜로 재생성(정정 아님 → --force 불필요, 스냅샷 우선 정상)**

```bash
python3 scripts/generate_html.py --type kospi --date <최신날짜> --data-file data/latest_kospi.json
```
- 데이터 파일이 없으면(다음 워크플로우 전) 이 단계는 배포된 라이브에서 자동 반영되므로 스킵 가능.
  대신 include가 템플릿에 들어갔는지만 grep으로 확인:
```bash
grep -c "stock-signals" web/briefings/<최신날짜>/kospi/index.html
```

- [ ] **Step 3: 생성물에 위젯 마크업·`/v2/` 경로 없음 확인**

```bash
grep -n "stock-signals" web/briefings/<최신날짜>/kospi/index.html
grep -c "/v2/" web/briefings/<최신날짜>/kospi/index.html   # 0이어야 함
```

- [ ] **Step 4: 재생성된 HTML이 있으면 커밋**

```bash
git add web/briefings/<최신날짜>/kospi/index.html
git commit -m "chore(코스피 브리핑): 종목 신호 위젯 반영 재생성 — Stage B 슬라이스8"
```

---

### Task 7: 체크리스트·컨텍스트 노트 갱신

**Files:**
- Modify: `.context/todays-view-band/context-notes.md`(슬라이스 진행 상황에 슬라이스8 추가)

- [ ] **Step 1: 슬라이스8 완료 기록 추가**

`.context/todays-view-band/context-notes.md`의 "슬라이스 진행 상황" 목록에 추가:
```
- 슬라이스8(종목신호): /api/signals 상위 3개 사이드바 위젯. 과거 브리핑·빈 signals 숨김. 60초 폴링.
```

- [ ] **Step 2: 커밋**

```bash
git add .context/todays-view-band/context-notes.md
git commit -m "docs(plan): 종목 신호 위젯(슬라이스8) 완료 기록"
```

---

## Self-Review 결과

- **Spec coverage**: 데이터소스(Task3 fetch/60초), 표시규칙 헤더·배지·CTA(Task1/2/3), 적용범위 코스피만(Task4 kospi.html만), 과거 숨김(Task3 `urlDate!==todayKst`), 빈 signals 숨김(Task3 render 가드), 위치 scorecard 아래(Task4), 구현구성 템플릿/CSS/JS(Task1-3), 검증(Task5) — 모두 태스크 존재.
- **Placeholder scan**: 코드 블록 전부 실제 내용. Task6의 `<최신날짜>`는 런타임에 확인해야 하는 실제 파라미터(플레이스홀더 아님) — Step1에서 조회 방법 제시.
- **Type consistency**: `#stock-signals`/`#ssig-title`/`#ssig-note`/`#ssig-hint`/`#ssig-list` id가 템플릿(Task1)·JS(Task3) 간 일치. `.ssig-*` 클래스가 CSS(Task2)·JS 렌더(Task3) 간 일치. `CAT_COLOR` 키가 `SIGNAL_META` 카테고리 키와 일치.
- **한 가지 주의**: 프로토타입은 성적표 아래에 "종목 신호 → 월배당 → 텔레그램" 순이나, 현재 라이브 `_sidebar_kospi.html`이 텔레그램+월배당+footer를 한 덩어리로 묶고 있어 위젯을 그 위(scorecard 아래)에 두는 것으로 근사. 프로토타입과 카드 순서 완전 일치는 범위 밖(별도 슬라이스).
