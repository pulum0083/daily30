# GNB 업데이트 로그 연결 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미 `web/landing.html`에서 동작 중인 GNB 공지·게시판 패널(🔔 버튼, `main.js`의 `openNoticePanel()`, `data/notices.json`)을 브리핑 페이지(`base.html`)와 종목 대시보드(`stocks/index.html`)에도 연결하고, 최신 작업 내역을 `notices.json`에 추가한다.

**Architecture:** 신규 파일 없음. `main.js`는 IIFE + DOM 가드 패턴이라 다른 페이지에 추가 로드해도 안전(조사로 확인 완료, [설계 문서](../specs/2026-07-24-gnb-updates-design.md) 참고). `base.html`은 이미 `main.js`를 로드하므로 버튼 마크업만 추가하면 되고, `stocks/index.html`은 `main.js` 스크립트 태그 + 버튼 마크업 + CSS 49줄(변수명 2개 치환)을 추가한다.

**Tech Stack:** 정적 HTML/CSS/JS (Jinja2 템플릿 + vanilla JS), 자동 테스트 없음 — 브라우저 수동 검증.

---

### Task 1: base.html GNB에 🔔 버튼 추가

**Files:**
- Modify: `scripts/templates/briefings/../../base.html` → 정확 경로 `scripts/templates/base.html:44`

- [ ] **Step 1: 현재 GNB 블록 확인**

`scripts/templates/base.html`의 44번째 줄(`{% block gnb %}` 안)에 아래와 같은 한 줄짜리 마크업이 있다:

```html
<div class="gnb"><div class="gnb__in"><a class="gnb__logo" href="/stocks/">...</a><span class="gnb__subs">...</span><span class="right"><span class="sbtn" onclick="location.href='/stocks/'"><svg .../>검색</span></span></div></div>
```

- [ ] **Step 2: `<span class="right">` 안, `<span class="sbtn"` 앞에 버튼 삽입**

`<span class="right">` 뒤에 오는 기존 부분:

```html
<span class="right"><span class="sbtn" onclick="location.href='/stocks/'">
```

이것을 아래로 교체(버튼 삽입, 뒤 내용은 그대로 유지):

```html
<span class="right"><button class="gnb__notif-btn" id="gnb-notif-btn" onclick="openNoticePanel()" aria-label="공지 및 게시판"><svg viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/><rect x="13" y="1" width="9" height="7" rx="2" fill="currentColor" opacity=".75"/><path d="M15.5 3.5h4M15.5 5.5h2.5" stroke="var(--gnb-bg,#16181A)" stroke-width="1.1" stroke-linecap="round"/><path d="M13 8l1.8 2" stroke="currentColor" stroke-width="1.1" opacity=".75" fill="none"/></svg><span class="gnb__notif-dot" id="gnb-notif-dot"></span></button><span class="sbtn" onclick="location.href='/stocks/'">
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/templates/base.html
git commit -m "브리핑 GNB에 공지·게시판 버튼 연결 (기존 main.js 재사용)"
```

---

### Task 2: stocks/index.html에 🔔 버튼 + main.js 로드 추가

**Files:**
- Modify: `web/stocks/index.html:22-25` (script/link 태그 영역), `web/stocks/index.html:28` (GNB 마크업)

- [ ] **Step 1: `main.js` 스크립트 태그 추가**

`web/stocks/index.html:23` 근처, 기존:

```html
<script src="/assets/pwa-install.js" defer></script>
<script src="/assets/stocks-home.js?v=5" defer></script>
```

아래로 교체(한 줄 추가):

```html
<script src="/assets/pwa-install.js" defer></script>
<script src="/assets/main.js" defer></script>
<script src="/assets/stocks-home.js?v=5" defer></script>
```

- [ ] **Step 2: GNB에 버튼 삽입**

`web/stocks/index.html:28`의 `<span class="right"><span class="sbtn" onclick="openSearch()">`를
Task 1과 동일한 패턴으로 교체:

```html
<span class="right"><button class="gnb__notif-btn" id="gnb-notif-btn" onclick="openNoticePanel()" aria-label="공지 및 게시판"><svg viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/><rect x="13" y="1" width="9" height="7" rx="2" fill="currentColor" opacity=".75"/><path d="M15.5 3.5h4M15.5 5.5h2.5" stroke="var(--gnb-bg,#16181A)" stroke-width="1.1" stroke-linecap="round"/><path d="M13 8l1.8 2" stroke="currentColor" stroke-width="1.1" opacity=".75" fill="none"/></svg><span class="gnb__notif-dot" id="gnb-notif-dot"></span></button><span class="sbtn" onclick="openSearch()">
```

- [ ] **Step 3: 커밋 (CSS는 Task 3에서 같이 커밋하지 않고 분리 — 이 스텝은 마크업/스크립트만)**

Task 3 완료 후 함께 커밋한다(마크업만 있고 CSS가 없으면 스타일 깨진 상태로 커밋되므로 분리하지 않음). Task 3로 진행.

---

### Task 3: stocks-home.css에 공지·게시판 패널 CSS 추가

**Files:**
- Modify: `web/assets/stocks-home.css` (파일 끝에 새 블록 추가)

- [ ] **Step 1: `web/assets/style.css:76-124`의 아래 블록을 그대로 복사**

원본(참고용, 수정하지 않음):

```css
.gnb__notif-btn{width:30px;height:30px;border-radius:var(--r-sm);background:rgba(255,255,255,.08);color:rgba(255,255,255,.6);display:flex;align-items:center;justify-content:center;position:relative;cursor:pointer;border:none;}
.gnb__notif-btn:hover{background:rgba(255,255,255,.16);color:#fff;}
.gnb__notif-btn svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;}
.gnb__notif-dot{position:absolute;top:4px;right:4px;width:7px;height:7px;border-radius:50%;background:#E03131;border:1.5px solid var(--gnb-bg);display:none;}
.gnb__notif-dot.is-visible{display:block;}
```

- [ ] **Step 2: `web/assets/stocks-home.css` 끝에 아래 블록 추가 (변수명 치환 완료본 — 이대로 붙여넣기)**

`web/assets/stocks-home.css` 파일 맨 끝에 추가:

```css

/* ── 공지·게시판 패널 (main.js 재사용, style.css:76-124와 동일 — --hairline→--hair, --gnb-bg→--gnb 치환) ── */
.gnb__notif-btn{width:30px;height:30px;border-radius:8px;background:rgba(255,255,255,.08);color:rgba(255,255,255,.6);display:flex;align-items:center;justify-content:center;position:relative;cursor:pointer;border:none;}
.gnb__notif-btn:hover{background:rgba(255,255,255,.16);color:#fff;}
.gnb__notif-btn svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;}
.gnb__notif-dot{position:absolute;top:4px;right:4px;width:7px;height:7px;border-radius:50%;background:#E03131;border:1.5px solid var(--gnb);display:none;}
.gnb__notif-dot.is-visible{display:block;}
.notice-overlay{position:fixed;inset:0;background:rgba(0,0,0,.3);z-index:400;opacity:0;pointer-events:none;transition:opacity .2s;}
.notice-overlay.is-open{opacity:1;pointer-events:auto;}
.notice-panel{position:fixed;top:0;right:0;bottom:0;width:320px;background:var(--canvas);border-left:1px solid var(--hair);z-index:401;display:flex;flex-direction:column;transform:translateX(100%);transition:transform .22s cubic-bezier(.4,0,.2,1);box-shadow:-4px 0 24px rgba(0,0,0,.12);}
.notice-panel.is-open{transform:translateX(0);}
.notice-panel__header{padding:16px 16px 13px;border-bottom:1px solid var(--hair);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.notice-panel__title{font-size:15px;font-weight:700;color:var(--ink);}
.notice-panel__close{width:28px;height:28px;border-radius:8px;background:var(--soft);border:1px solid var(--hair);display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--muted);font-size:13px;}
.notice-panel__body{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px;}
.notice-panel__footer{padding:10px;border-top:1px solid var(--hair);flex-shrink:0;}
.notice-panel__empty{text-align:center;padding:40px 16px;font-size:13px;color:var(--muted);}
.notice-panel__tabs{display:flex;border-bottom:1px solid var(--hair);flex-shrink:0;}
.notice-tab{flex:1;padding:10px 0;font-size:13px;font-weight:600;color:var(--muted);background:none;border:none;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;}
.notice-tab.is-active{color:var(--primary);border-bottom-color:var(--primary);}
.board-panel{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px;}
.board-post{border-radius:10px;border:1px solid var(--hair);padding:11px 13px;background:var(--canvas);}
.board-post__header{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;}
.board-post__author{font-size:12px;font-weight:700;color:var(--ink);}
.board-post__time{font-size:11px;color:var(--muted);}
.board-post__content{font-size:13px;color:var(--ink);line-height:1.55;word-break:break-all;}
.board-reply{margin-top:4px;padding:9px 12px 9px 20px;border-left:2px solid var(--primary);background:var(--soft);border-radius:0 8px 8px 0;}
.board-reply__author{font-size:11px;font-weight:700;color:var(--primary);margin-bottom:4px;}
.board-reply__content{font-size:13px;color:var(--ink);line-height:1.5;word-break:break-all;}
.board-reply__time{font-size:11px;color:var(--muted);margin-top:4px;}
.board-input{padding:10px;border-top:1px solid var(--hair);flex-shrink:0;display:flex;gap:6px;}
.board-input__textarea{flex:1;padding:8px 10px;border-radius:8px;border:1.5px solid var(--hair);font-size:13px;color:var(--ink);background:var(--canvas);resize:none;height:60px;font-family:inherit;line-height:1.5;}
.board-input__textarea:focus{outline:none;border-color:var(--primary);}
.board-input__submit{padding:0 14px;border-radius:8px;font-size:13px;font-weight:700;color:#fff;background:var(--primary);border:none;cursor:pointer;flex-shrink:0;align-self:flex-end;height:36px;}
.board-input__submit:disabled{opacity:.5;cursor:default;}
.notice-card{border-radius:10px;border:1px solid var(--hair);padding:12px 13px;background:var(--canvas);position:relative;}
.notice-card.is-unread{border-color:#BFDBFE;background:#F0F7FF;position:relative;}
.notice-card__dot{position:absolute;top:12px;right:12px;width:6px;height:6px;border-radius:50%;background:var(--primary);}
.notice-card__meta{display:flex;align-items:center;gap:6px;margin-bottom:6px;}
.notice-badge{font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;line-height:1.4;}
.notice-badge--update{background:var(--primary-bg);color:var(--primary);}
.notice-badge--ops{background:var(--gold-bg);color:var(--gold);}
.notice-badge--urgent{background:var(--up-bg);color:var(--up);}
.notice-card__date{font-size:11px;color:var(--muted);margin-left:auto;}
.notice-card__title{font-size:13px;font-weight:700;color:var(--ink);margin-bottom:4px;line-height:1.4;}
.notice-card__body{font-size:12px;color:var(--muted);line-height:1.6;}
```

주의: 원본의 `border-radius:var(--r-sm)`은 stocks-home.css에 `--r-sm` 변수가 없으므로
`8px` 고정값으로, `background:var(--surface-soft)`/`var(--surface-inset)` 계열도
stocks-home.css 명명 규칙에 맞춰 `var(--soft)`로 치환했다(위 블록에 이미 반영됨).
`html.dark .notice-card.is-unread{...}` 규칙은 stocks-home.css에 다크모드가 없으므로 제외.

- [ ] **Step 2: 브라우저로 검증**

로컬 정적 서버(`daily30-web`, 8788포트)로 `http://localhost:8788/stocks/index.html` 새로고침 후:
- GNB 우측에 🔔 버튼이 검색 버튼 왼쪽에 나타나는지 확인
- 버튼 클릭 → 우측에서 패널이 슬라이드인되는지 확인 (`.notice-panel.is-open`)
- 패널에 `web/data/notices.json` 내용이 카드로 렌더되는지 확인
- 바깥(오버레이) 클릭 → 패널이 닫히는지 확인
- 기존 종목 대시보드 기능(섹터 탭·자금 지도 등)이 `main.js` 추가 로드 후에도 정상 동작하는지 확인(회귀 없음)

- [ ] **Step 3: Task 2 + Task 3 함께 커밋**

```bash
git add web/stocks/index.html web/assets/stocks-home.css
git commit -m "종목 대시보드 GNB에 공지·게시판 버튼 연결 (main.js 추가 로드 + CSS 이식)"
```

---

### Task 4: notices.json 최신 항목 추가

**Files:**
- Modify: `web/data/notices.json`

- [ ] **Step 1: 배열 맨 앞에 아래 3개 항목 추가 (최신순 유지)**

`web/data/notices.json`의 `"notices": [` 바로 다음에 삽입:

```json
    {
      "id": "2026-07-24-flow-map-anim",
      "type": "update",
      "date": "2026-07-24",
      "title": "자금 지도 타일 펼침 애니메이션 추가",
      "body": "이번 주 자금 지도에서 테마 타일을 누르면 상위 ETF 목록이 부드럽게 펼쳐져요."
    },
    {
      "id": "2026-07-24-sbx-sticky",
      "type": "update",
      "date": "2026-07-24",
      "title": "섹터별 대표 종목 탭 PC 스티키 고정",
      "body": "PC에서도 섹터 탭이 스크롤 중 상단에 고정되고, 섹션을 벗어나면 자연스럽게 해제돼요."
    },
    {
      "id": "2026-07-24-close-sidebar-unify",
      "type": "update",
      "date": "2026-07-24",
      "title": "마감 브리핑 사이드바 위젯 통일",
      "body": "코스피 마감 브리핑의 텔레그램 구독·월배당 계산기 영역을 아침 브리핑과 동일한 디자인으로 정리했어요."
    },
```

- [ ] **Step 2: JSON 문법 확인**

```bash
python3 -m json.tool web/data/notices.json > /dev/null && echo "JSON OK"
```

- [ ] **Step 3: 커밋**

```bash
git add web/data/notices.json
git commit -m "data: 오늘 작업 내역 3건을 공지 업데이트 항목으로 추가"
```

---

### Task 5: 랜딩페이지 회귀 확인

**Files:** 없음 (검증만)

- [ ] **Step 1: 랜딩페이지에서 기존 동작 그대로인지 확인**

`http://localhost:8788/landing.html`에서 🔔 버튼 클릭 → 새로 추가된 3개 항목이 최상단에
보이는지, 기존 항목(2026-06-05 등)도 그 아래 정상 표시되는지 확인. 이 페이지는 코드 변경이
없으므로 데이터만 반영되면 끝.

- [ ] **Step 2: 완료 보고**

3개 페이지(랜딩·종목 대시보드·브리핑 다음 발행분)에서 배지·패널 정상 동작 확인 후 완료.
