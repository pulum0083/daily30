# Double-Shot Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Config-driven section assembly 아키텍처로 브리핑 3종(코스피 예측·마감·미국 시장) 및 웹 페이지를 전면 재구축한다.

**Architecture:** `scripts/config/{type}.json`이 섹션 목록·순서를 선언 → `generate_html.py`가 Jinja2 섹션 템플릿을 조립 → `web/briefings/{date}/{type}/index.html` 정적 파일 출력. 기존 1,086줄 generate_html.py를 ~200줄 조립기로 교체한다.

**Tech Stack:** Python 3.11+, Jinja2 3.x, pytz, GitHub Actions, Vercel (static)

---

## ⚠️ vibecoding-starter-kit 활용 안내

이 프로젝트는 Python + Jinja2 정적 생성 스택이라 `nextjs-frontend-guidelines` / `fastapi-backend-guidelines`의 프레임워크별 규칙은 직접 적용되지 않는다. 단, 구현 중 아래 원칙을 검토할 때 해당 스킬을 참고할 수 있다:

- **컴포넌트 격리** (`nextjs-frontend-guidelines`) → Jinja2 섹션 템플릿 분리 기준
- **서비스 계층** (`fastapi-backend-guidelines`) → generate_html.py의 데이터 로딩·렌더링 계층 분리
- **파일 조직** → scripts/templates/, scripts/config/ 디렉터리 구조 설계

검토 방법: 구현 중 `Skill("vibecoding-starter-kit:nextjs-frontend-guidelines")` 또는 `Skill("vibecoding-starter-kit:fastapi-backend-guidelines")`를 호출해 해당 섹션의 원칙과 비교한다.

---

## 확정된 프로토타입 파일 (디자인 소스)

| 프로토타입 | 역할 |
|-----------|------|
| `docs/prototypes/briefing-kospi.html` | 코스피 예측 브리핑 전체 디자인 |
| `docs/prototypes/briefing-close.html` | 코스피 마감 브리핑 전체 디자인 |
| `docs/prototypes/briefing-us.html` | 미국 시장 브리핑 전체 디자인 |
| `docs/prototypes/page-briefings-index.html` | `/briefings` 진입 페이지 |
| `docs/prototypes/page-briefings-viewer.html` | 브리핑 뷰어 페이지 |

> 각 태스크에서 "프로토타입 참조"라고 표기된 곳은 위 파일에서 해당 섹션 HTML+CSS를 그대로 복사해 Jinja2 변수로 치환한다.

---

## 파일 구조 (완성 목표)

```
scripts/
├── templates/
│   ├── base.html                        # GNB·레이아웃·다크모드 (NEW)
│   ├── sections/
│   │   ├── prediction.html              # 예측 게이지 (NEW)
│   │   ├── reasons.html                 # 왜 오를까 근거 (NEW)
│   │   ├── stock_picks.html             # 종목픽 (코스피용) (NEW)
│   │   ├── watchpoints.html             # 오늘밤 관전 포인트 (US용) (NEW)
│   │   ├── nh_stock.html                # 52주 신고가 (US용) (NEW)
│   │   ├── spill.html                   # 미국→코스피 낙수효과 (US용) (NEW)
│   │   ├── momentum.html                # 상승 모멘텀 종목+차트 (US용) (NEW)
│   │   ├── market_data.html             # 시장 지표 (US용) (NEW)
│   │   ├── close_hero.html              # 마감 스냅샷 차트 (NEW)
│   │   ├── close_index.html             # 마감 지수 (NEW)
│   │   ├── close_supply.html            # 수급 (NEW)
│   │   ├── close_sector.html            # 섹터 (NEW)
│   │   ├── accuracy.html                # AI 예측 정확도 (NEW)
│   │   └── briefing_list.html           # 브리핑 목록 (공유) (NEW)
│   ├── briefings/
│   │   ├── kospi.html                   # 코스피 예측 조립 (NEW)
│   │   ├── close.html                   # 마감 조립 (NEW)
│   │   └── us.html                      # 미국 시장 조립 (NEW)
│   └── pages/
│       └── briefings_index.html         # /briefings 페이지 (NEW)
├── config/
│   ├── kospi.json                       # 섹션 목록·순서 (NEW)
│   ├── close.json                       # (NEW)
│   └── us.json                          # (NEW)
└── generate_html.py                     # 조립 전용 리팩터 (MODIFY)

web/
├── assets/
│   ├── style.css                        # 전면 재작성 (MODIFY)
│   └── main.js                          # 재작성 (MODIFY)
├── briefings/
│   ├── index.html                       # 자동 생성 (MODIFY)
│   └── {YYYY-MM-DD}/
│       ├── kospi/index.html             # NEW URL 구조
│       ├── close/index.html
│       └── us/index.html
└── favicon.svg                          # 새 B심볼 (MODIFY)

vercel.json                              # 라우팅 업데이트 (MODIFY)
scripts/call_claude.py                   # 어조 프롬프트 수정 (MODIFY)
```

---

## Phase 1: 디자인 시스템 + base.html + GNB

### Task 1: style.css 재작성

**Files:**
- Modify: `web/assets/style.css`

프로토타입 HTML 3종의 `<style>` 블록에서 CSS를 추출해 단일 `style.css`로 통합한다. 섹션별로 주석 블록으로 구분한다.

- [ ] **Step 1: 기존 style.css 백업**

```bash
cp web/assets/style.css web/assets/style.css.bak
```

- [ ] **Step 2: 디자인 토큰 + 리셋 + 기본 타이포 작성**

`web/assets/style.css`를 아래 내용으로 시작한다. (기존 내용 전체 교체)

```css
/* ── 디자인 토큰 ── */
:root {
  --canvas:#FFFFFF;--surface-soft:#F9FAFB;--surface-inset:#EEF1F5;
  --hairline:#E5E7EB;--ink:#13151A;--muted:#6B7280;
  --primary:#006EFF;--primary-bg:#E8F4FF;
  --up:#E03131;--up-bg:#FFE8E8;--dn:#2775ED;--dn-bg:#DBE8FE;
  --gold:#B7791F;--gold-bg:#FEF3C7;
  --s1:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);
  --s2:0 4px 8px rgba(0,0,0,.08),0 2px 4px rgba(0,0,0,.04);
  --r-sm:6px;--r-md:10px;--r-lg:16px;
  --gnb-bg:#16181A;--gnb-h:52px;
}
html.dark {
  --canvas:#1C1D1F;--surface-soft:#242628;--surface-inset:#2A2B2D;
  --hairline:#3C3E40;--ink:#F3F5F7;--muted:#888B90;
  --primary:#3B8BFF;--primary-bg:rgba(59,139,255,.12);
  --up-bg:rgba(224,49,49,.14);--dn:#4A8FF5;--dn-bg:rgba(39,117,237,.14);
  --gold:#E0B252;--gold-bg:rgba(224,178,82,.14);
  --s1:0 1px 4px rgba(0,0,0,.35);--s2:0 4px 12px rgba(0,0,0,.45);
}

/* ── 리셋 ── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
html{font-size:15px;-webkit-font-smoothing:antialiased;}
body{
  font-family:'Pretendard Variable','Pretendard',-apple-system,sans-serif;
  background:var(--surface-soft);color:var(--ink);min-height:100vh;word-break:keep-all;
}
a{color:inherit;text-decoration:none;}
button{cursor:pointer;border:none;background:none;font:inherit;}
```

- [ ] **Step 3: GNB CSS 추가** (프로토타입 `.gnb*` 클래스 복사)

```css
/* ── GNB ── */
.gnb{position:sticky;top:0;z-index:100;height:var(--gnb-h);background:var(--gnb-bg);
     border-bottom:1px solid rgba(255,255,255,.06);padding:0 32px;display:flex;align-items:center;}
.gnb__inner{width:100%;display:flex;align-items:center;justify-content:space-between;}
.gnb__left{display:flex;align-items:center;}
.gnb__logo{display:flex;align-items:center;gap:8px;}
.gnb__logo-mark{width:28px;height:28px;border-radius:7px;
  background:linear-gradient(135deg,#E03131,#FF6A6A);display:flex;align-items:center;justify-content:center;}
.gnb__logo-mark svg{width:18px;height:18px;}
.gnb__title{font-size:16px;font-weight:700;color:#fff;letter-spacing:-0.01em;}
.gnb__title span{color:var(--primary);}
.gnb__chips-link{font-size:12px;font-weight:600;color:rgba(255,255,255,.5);
  padding-left:12px;margin-left:10px;border-left:1px solid rgba(255,255,255,.18);}
.gnb__chips-link:hover{color:rgba(255,255,255,.9);}
.gnb__meta{display:flex;align-items:center;gap:14px;}
.gnb__date{font-size:12px;color:rgba(255,255,255,.42);}
.gnb__theme-toggle{width:30px;height:30px;border-radius:var(--r-sm);
  background:rgba(255,255,255,.08);color:rgba(255,255,255,.6);display:flex;align-items:center;justify-content:center;}
.gnb__theme-toggle:hover{background:rgba(255,255,255,.16);color:#fff;}
.icon-sun,.icon-moon{display:none;}
html.dark .icon-sun{display:block;}html.light .icon-moon{display:block;}
```

- [ ] **Step 4: 레이아웃 CSS 추가**

```css
/* ── 레이아웃 ── */
.layout-wrapper{max-width:1200px;margin:0 auto;padding:24px 32px 72px;}
.layout-grid{display:grid;grid-template-columns:1fr 336px;column-gap:20px;align-items:start;}
.layout-grid__main{min-width:0;}
.layout-grid__right{display:flex;flex-direction:column;gap:12px;}
@media(max-width:900px){
  .layout-wrapper{padding:16px 16px 56px;}
  .layout-grid{grid-template-columns:1fr;row-gap:16px;}
  .gnb__date{display:none;}
}
```

- [ ] **Step 5: 공통 컴포넌트 CSS 추가** (섹션 카드, 뱃지, 타이포 유틸 등)

프로토타입 HTML 3종에서 공통으로 쓰이는 클래스(`.section-card`, `.section-title`, `.badge-up`, `.badge-dn`, `.t-caption` 등)를 추출해 추가한다. 각 프로토타입 `<style>` 블록을 열어 `.section-`, `.badge-`, `.pred-`, `.t-` 접두사 규칙을 복사한다.

- [ ] **Step 6: 브리핑 목록 CSS 추가** (`.bl-*`, `.bottom-list` 등)

프로토타입 `briefing-us.html`의 `.bl-*` 클래스 전체를 복사해 `/* ── 브리핑 목록 ── */` 주석 블록 아래 추가한다. 이미 모바일 수정이 완료된 코드(`bl-row__date`, `bl-row{grid-template-columns:auto 1fr 1fr}`)를 사용한다.

- [ ] **Step 7: 변경사항 커밋**

```bash
git add web/assets/style.css
git commit -m "style: 디자인 시스템 CSS 전면 재작성 (토큰·GNB·레이아웃·공통 컴포넌트)"
```

---

### Task 2: main.js 재작성 + base.html 작성

**Files:**
- Modify: `web/assets/main.js`
- Create: `scripts/templates/base.html`

- [ ] **Step 1: main.js 재작성**

`web/assets/main.js` 전체를 아래 내용으로 교체한다.

```javascript
// 다크모드·GNB 날짜·아코디언 공통 JS

(function () {
  // 다크모드
  const root = document.documentElement;
  const saved = localStorage.getItem('theme');
  if (saved === 'dark') root.classList.replace('light', 'dark');

  function toggleTheme() {
    const isDark = root.classList.contains('dark');
    root.classList.replace(isDark ? 'dark' : 'light', isDark ? 'light' : 'dark');
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
  }

  // GNB 날짜
  function updateGnbDate() {
    const el = document.getElementById('gnb-date');
    if (!el) return;
    const now = new Date();
    const kst = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
    const pad = n => String(n).padStart(2, '0');
    const days = ['일', '월', '화', '수', '목', '금', '토'];
    el.textContent =
      `${kst.getFullYear()}.${pad(kst.getMonth()+1)}.${pad(kst.getDate())} ` +
      `(${days[kst.getDay()]}) ${pad(kst.getHours())}:${pad(kst.getMinutes())}`;
  }

  // 아코디언 (브리핑 뷰어 내 헤더 접기/펼치기)
  function initAccordions() {
    document.querySelectorAll('.accordion-header').forEach(header => {
      header.addEventListener('click', () => {
        const item = header.closest('.accordion-item');
        item.classList.toggle('is-open');
      });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.js-theme-toggle').forEach(btn => {
      btn.addEventListener('click', toggleTheme);
    });
    updateGnbDate();
    setInterval(updateGnbDate, 30000);
    initAccordions();
  });
})();
```

- [ ] **Step 2: base.html 작성**

`scripts/templates/base.html`을 생성한다. 이 파일이 GNB + 레이아웃 + JS/CSS 로드를 담당한다.

```html
<!DOCTYPE html>
<html lang="ko" class="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}Double-Shot{% endblock %}</title>
<meta property="og:type" content="website">
<meta property="og:title" content="{% block og_title %}Double-Shot — AI 투자 브리핑{% endblock %}">
<meta property="og:description" content="{% block og_desc %}매일 아침·저녁 AI 시장 예측 브리핑{% endblock %}">
{% if og_image %}<meta property="og:image" content="{{ og_image }}">{% endif %}
<link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css" rel="stylesheet">
<link rel="stylesheet" href="{{ css_path | default('/assets/style.css') }}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-PW9RHHFPM4"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-PW9RHHFPM4');</script>
{% block head_extra %}{% endblock %}
</head>
<body>

<nav class="gnb">
  <div class="gnb__inner">
    <div class="gnb__left">
      <div class="gnb__logo">
        <div class="gnb__logo-mark">
          <!-- B심볼 SVG (favicon.svg 인라인) -->
          <svg viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="2" y="4" width="4" height="10" rx="1" fill="white" opacity="0.7"/>
            <rect x="8" y="1" width="4" height="16" rx="1" fill="white"/>
          </svg>
        </div>
        <span class="gnb__title">Double-<span>Shot</span></span>
      </div>
      <a class="gnb__chips-link" href="/chips">Chip-Board →</a>
    </div>
    <div class="gnb__meta">
      <span class="gnb__date" id="gnb-date"></span>
      <button class="gnb__theme-toggle js-theme-toggle" aria-label="다크모드 전환">
        <svg class="icon-moon" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
        <svg class="icon-sun" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
      </button>
    </div>
  </div>
</nav>

{% block body %}{% endblock %}

<script src="{{ js_path | default('/assets/main.js') }}"></script>
{% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 3: 로컬 확인**

프로토타입 서버에서 `http://localhost:8789/briefing-us.html`을 열어 GNB 디자인이 base.html 마크업과 일치하는지 육안으로 대조한다.

- [ ] **Step 4: 커밋**

```bash
git add web/assets/main.js scripts/templates/base.html
git commit -m "feat: main.js 재작성 + base.html 공통 GNB 템플릿 작성"
```

---

## Phase 2: 섹션 템플릿

> 각 섹션 템플릿은 프로토타입 HTML에서 해당 블록의 HTML을 복사하고, 하드코딩된 값을 Jinja2 `{{ 변수 }}`로 치환한다.
> CSS는 Task 1에서 이미 style.css에 통합했으므로 섹션 파일엔 스타일을 넣지 않는다.

### Task 3: 공통 섹션 — prediction, reasons, accuracy

**Files:**
- Create: `scripts/templates/sections/prediction.html`
- Create: `scripts/templates/sections/reasons.html`
- Create: `scripts/templates/sections/accuracy.html`

각 섹션이 받는 Jinja2 컨텍스트 변수:

| 섹션 | 핵심 변수 |
|------|---------|
| prediction | `direction`, `up_pct`, `confidence`, `generated_time`, `prev_url`, `next_url`, `date_label` |
| reasons | `reason_title`, `reasons` (리스트) |
| accuracy | `acc_7d_pct`, `acc_30d_pct`, `acc_dots` (리스트: `{status, date}`), `hit`, `miss`, `pending` |

- [ ] **Step 1: prediction.html 작성**

`scripts/templates/sections/prediction.html` 생성. 프로토타입 `briefing-kospi.html`에서 `.accordion-header` + `.pred-gauge` + `.pred-gauge__score` 블록 HTML 복사 후 변수 치환:

```html
{# 예측 게이지 섹션 #}
<div class="accordion-item is-today is-open">
  <div class="accordion-header">
    <div class="accordion-header__left">
      <span class="badge-{{ 'up' if direction == '상승 우위' else 'dn' }}">
        {{ '▲' if direction == '상승 우위' else '▼' }} {{ direction }}
      </span>
      <span class="accordion-header__summary">
        {{ index_name }} 예측 {{ up_pct }}% · {{ generated_time }} 생성
      </span>
    </div>
    <svg class="accordion-chevron" ...>...</svg>
  </div>
  <div class="accordion-body">
    <div class="section-card">
      <div class="section-title-row">
        <span class="section-title">{{ index_name }} 방향 예측</span>
        <span class="t-caption">{{ generated_time }} KST 생성</span>
      </div>
      <div class="pred-gauge">
        <div class="badge-{{ 'up' if direction == '상승 우위' else 'dn' }} pred-gauge__badge">
          {{ '▲' if direction == '상승 우위' else '▼' }} {{ direction }}
        </div>
        <div class="pred-gauge__bar-wrap">
          <div class="pred-gauge__bar-fill" style="left:calc({{ up_pct }}% - 8px)"></div>
        </div>
        <div class="pred-gauge__scale">
          <span>하락</span><span>중립 50</span><span>상승</span>
        </div>
      </div>
      <div class="pred-gauge__score">
        <span class="pred-gauge__num {{ 'up' if direction == '상승 우위' else 'dn' }}">{{ up_pct }}</span>
        <span class="pred-gauge__label">% 상승</span>
        <span class="pred-gauge__strength">신호 강도
          {% for i in range(5) %}
          <span class="dot {{ 'filled' if i < confidence_dots else '' }}"></span>
          {% endfor %}
          {{ confidence_label }}
        </span>
      </div>
    </div>
  </div>
</div>
```

실제 클래스명과 HTML 구조는 프로토타입 파일을 열어 정확히 일치시킨다.

- [ ] **Step 2: reasons.html 작성**

`scripts/templates/sections/reasons.html` 생성. 프로토타입의 `왜 오를까?` 섹션 복사:

```html
{# 근거 섹션 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">💬 {{ reason_title }}</span>
  </div>
  <ul class="reasons-list">
    {% for reason in reasons %}
    <li class="reasons-list__item">{{ reason | safe }}</li>
    {% endfor %}
  </ul>
</div>
```

- [ ] **Step 3: accuracy.html 작성**

`scripts/templates/sections/accuracy.html` 생성:

```html
{# AI 예측 정확도 섹션 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">AI 예측 정확도 <span class="help-icon" title="최근 30일 기준">?</span></span>
    <span class="t-caption">최근 30일</span>
  </div>
  <div class="acc-scores">
    <div class="acc-score">
      <span class="acc-score__num {{ acc_7d_pct | acc_cls }}">{{ acc_7d_pct }}%</span>
      <span class="acc-score__label">최근 7일</span>
    </div>
    <div class="acc-score">
      <span class="acc-score__num {{ acc_30d_pct | acc_cls }}">{{ acc_30d_pct }}%</span>
      <span class="acc-score__label">최근 30일</span>
    </div>
  </div>
  <div class="acc-bar">
    {% for dot in acc_dots %}
    <span class="acc-dot acc-dot--{{ dot.status }}" title="{{ dot.date }}"></span>
    {% endfor %}
  </div>
  <div class="acc-legend">
    <span class="acc-legend__item hit">적중 {{ hit }}</span>
    <span class="acc-legend__item miss">오류 {{ miss }}</span>
    <span class="acc-legend__item pending">미결 {{ pending }}</span>
  </div>
</div>
```

- [ ] **Step 4: 커밋**

```bash
git add scripts/templates/sections/prediction.html scripts/templates/sections/reasons.html scripts/templates/sections/accuracy.html
git commit -m "feat: 공통 섹션 템플릿 작성 (prediction, reasons, accuracy)"
```

---

### Task 4: 코스피 예측 전용 섹션 — stock_picks

**Files:**
- Create: `scripts/templates/sections/stock_picks.html`

- [ ] **Step 1: stock_picks.html 작성**

프로토타입 `briefing-kospi.html`의 `종목 픽` 섹션 복사. 핵심 변수:
- `stock_picks`: 리스트, 각 항목 `{name, ticker, scenario_tag, guide, signal_strength}`

```html
{# 종목픽 섹션 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">종목 픽</span>
  </div>
  {% for pick in stock_picks %}
  <div class="pick-card">
    <div class="pick-card__header">
      <span class="pick-card__ticker">{{ pick.ticker }}</span>
      <span class="pick-card__name">{{ pick.name }}</span>
      <span class="pick-card__tag">{{ pick.scenario_tag }}</span>
    </div>
    <p class="pick-card__guide">{{ pick.guide }}</p>
  </div>
  {% endfor %}
</div>
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/sections/stock_picks.html
git commit -m "feat: stock_picks 섹션 템플릿 작성"
```

---

### Task 5: 미국 브리핑 전용 섹션 — watchpoints, nh_stock, spill, momentum, market_data

**Files:**
- Create: `scripts/templates/sections/watchpoints.html`
- Create: `scripts/templates/sections/nh_stock.html`
- Create: `scripts/templates/sections/spill.html`
- Create: `scripts/templates/sections/momentum.html`
- Create: `scripts/templates/sections/market_data.html`

모든 섹션은 프로토타입 `briefing-us.html`에서 해당 블록 HTML을 복사 후 변수 치환한다.

- [ ] **Step 1: watchpoints.html 작성** (오늘밤 관전 포인트)

핵심 변수: `watch_items` 리스트, 각 항목 `{icon, label, content}`

```html
{# 오늘밤 관전 포인트 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">👁 오늘밤 관전 포인트</span>
  </div>
  <div class="watch-list">
    {% for item in watch_items %}
    <div class="watch-item">
      <span class="watch-item__icon">{{ item.icon }}</span>
      <div class="watch-item__body">
        <span class="watch-item__label">{{ item.label }}</span>
        <p class="watch-item__content">{{ item.content | safe }}</p>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
```

- [ ] **Step 2: nh_stock.html 작성** (52주 신고가)

핵심 변수: `nh_stocks` 리스트, 각 항목 `{ticker, name, tag, prev_high, price, chg_pct, note}`

```html
{# 52주 신고가 종목 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">🏆 프리장 신고가 종목</span>
  </div>
  <p class="t-caption">오늘 프리장에서 52주 신고가 또는 역대 최고가를 기록한 종목.</p>
  {% for s in nh_stocks %}
  <div class="nh-card">
    <div class="nh-card__left">
      <span class="nh-card__ticker">{{ s.ticker }}</span>
      <span class="nh-card__name">{{ s.name }}</span>
      <span class="nh-card__tag">{{ s.tag }}</span>
      <p class="nh-card__note">{{ s.note }}</p>
    </div>
    <div class="nh-card__right">
      <span class="nh-card__price">${{ s.price }}</span>
      <span class="nh-card__chg {{ 'up' if s.chg_pct > 0 else 'dn' }}">
        {{ '+' if s.chg_pct > 0 else '' }}{{ s.chg_pct }}%
      </span>
    </div>
  </div>
  {% endfor %}
</div>
```

- [ ] **Step 3: spill.html 작성** (미국→코스피 낙수효과)

핵심 변수: `spill_rows` 리스트, 각 항목 `{us_sector, us_tickers, ko_stocks, strength}`

```html
{# 낙수효과 섹션 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">🇰🇷 내일 코스피 낙수 종목</span>
  </div>
  <p class="t-caption">오늘밤 미국이 예측대로 움직이면, 내일 아침 코스피에서 어떤 종목이 영향을 받을지 매핑했어요. (별도 데이터 없이 AI 분석으로 생성)</p>
  <div class="spill-list">
    {% for row in spill_rows %}
    <div class="spill-row">
      <div class="spill-us">
        <div class="spill-us__sector">{{ row.us_sector }}
          {% if row.us_tag %}<span class="us-chg">{{ row.us_tag }}</span>{% endif %}
        </div>
        <div class="spill-us__tickers">{{ row.us_tickers }}</div>
      </div>
      <div class="spill-arrow">→</div>
      <div class="spill-ko">
        <div class="spill-ko__stocks">
          {% for s in row.ko_stocks %}
          <span class="ko-chip">{{ s }}</span>
          {% endfor %}
        </div>
      </div>
      <div class="spill-strength">
        <span class="strength-badge {{ row.strength_cls }}">{{ row.strength }}</span>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
```

- [ ] **Step 4: momentum.html 작성** (상승 모멘텀 종목 + 미니차트)

핵심 변수: `momentum_stocks` 리스트, 각 항목 `{rank, ticker, name, tag, price, chg_pct, note, ma200_pct, entry, target, target_pct, stop, stop_pct, chart_id, prices_20, ma20, ma200}`

```html
{# 상승 모멘텀 종목 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">상승 모멘텀 종목 <span class="help-icon">?</span></span>
  </div>
  <p class="t-caption">20일선을 상향 돌파하거나 정확히 지지 반등한 종목 중 거래량 급증을 동반한 종목만 선별했어요.</p>
  <div class="mom-legend">
    <span class="mom-legend__item price">— 주가</span>
    <span class="mom-legend__item ma20">··· 20일선</span>
    <span class="mom-legend__item ma200">- - 200일선</span>
  </div>
  {% for s in momentum_stocks %}
  <div class="mom-card">
    <div class="mom-card__rank">{{ s.rank }}</div>
    <div class="mom-card__header">
      <span class="mom-card__ticker">{{ s.ticker }}</span>
      <span class="mom-card__name">{{ s.name }}</span>
      <span class="mom-card__tag">{{ s.tag }}</span>
    </div>
    <div class="mom-card__price">
      ${{ s.price }} <span class="chg-pct {{ 'up' if s.chg_pct >= 0 else 'dn' }}">
        {{ '+' if s.chg_pct >= 0 else '' }}{{ s.chg_pct }}%
      </span>
    </div>
    <p class="mom-card__note">{{ s.note }}</p>
    <div class="ma200-gauge-wrap">
      <span class="t-caption">200일선 대비</span>
      <div class="ma200-gauge__bar">
        <div class="ma200-gauge__fill" style="width:{{ [s.ma200_pct|abs, 60]|min / 60 * 50 + 50 }}%"></div>
      </div>
      <span class="ma200-gauge__val {{ 'up' if s.ma200_pct >= 0 else 'dn' }}">
        {{ '+' if s.ma200_pct >= 0 else '' }}{{ s.ma200_pct }}%
      </span>
    </div>
    <canvas id="{{ s.chart_id }}" class="mom-chart" height="80"></canvas>
    <div class="pick-nums__grid">
      <div class="pick-num"><span class="pick-num__label">진입 (시가 이내)</span><span class="pick-num__val">${{ s.entry }}</span></div>
      <div class="pick-num"><span class="pick-num__label">목표</span><span class="pick-num__val up">${{ s.target }}</span><span class="pick-num__sub">+{{ s.target_pct }}%</span></div>
      <div class="pick-num"><span class="pick-num__label">손절</span><span class="pick-num__val dn">${{ s.stop }}</span><span class="pick-num__sub">{{ s.stop_pct }}%</span></div>
    </div>
  </div>
  {% endfor %}
</div>
<script>
// 미니차트 데이터 주입 (generate_html.py가 JSON으로 렌더링)
document.addEventListener('DOMContentLoaded', () => {
  {% for s in momentum_stocks %}
  drawMiniChart('{{ s.chart_id }}', {{ s.prices_20 | tojson }}, {{ s.ma20 | tojson }}, {{ s.ma200 | tojson }});
  {% endfor %}
});
</script>
```

`drawMiniChart` 함수는 기존 프로토타입에서 그대로 main.js로 이동한다.

- [ ] **Step 5: market_data.html 작성** (시장 지표)

핵심 변수: `market_items` 리스트, 각 항목 `{label, value, chg, chg_cls, vix_badge, chart_id, chart_prices, chart_color}`

```html
{# 시장 지표 섹션 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">시장 지표</span>
    <span class="t-caption">{{ generated_time }} KST</span>
  </div>
  <div class="mkt-list">
    {% for item in market_items %}
    <div class="mkt-row">
      <div class="mkt-row__left">
        <span class="mkt-row__label">{{ item.label }}</span>
        <span class="mkt-row__val">{{ item.value }}
          <span class="mkt-row__chg {{ item.chg_cls }}">{{ item.chg }}</span>
        </span>
      </div>
      {% if item.chart_id %}
      <canvas id="{{ item.chart_id }}" class="mkt-chart" width="88" height="52"></canvas>
      {% elif item.vix_badge %}
      <span class="vix-badge {{ item.vix_badge_cls }}">{{ item.vix_badge }}</span>
      {% endif %}
    </div>
    {% endfor %}
  </div>
</div>
<script>
document.addEventListener('DOMContentLoaded', () => {
  {% for item in market_items if item.chart_id %}
  drawMiniChart('{{ item.chart_id }}', {{ item.chart_prices | tojson }}, [], null, '{{ item.chart_color | default("#E03131") }}');
  {% endfor %}
});
</script>
```

- [ ] **Step 6: 커밋**

```bash
git add scripts/templates/sections/watchpoints.html scripts/templates/sections/nh_stock.html \
        scripts/templates/sections/spill.html scripts/templates/sections/momentum.html \
        scripts/templates/sections/market_data.html
git commit -m "feat: 미국 브리핑 전용 섹션 템플릿 5종 작성"
```

---

### Task 6: 마감 브리핑 전용 섹션

**Files:**
- Create: `scripts/templates/sections/close_hero.html`
- Create: `scripts/templates/sections/close_index.html`
- Create: `scripts/templates/sections/close_supply.html`
- Create: `scripts/templates/sections/close_sector.html`

모든 섹션은 프로토타입 `briefing-close.html`에서 해당 블록 복사 후 변수 치환.

- [ ] **Step 1: close_hero.html 작성** (마감 스냅샷 차트)

핵심 변수: `close_pct`, `chart_prices` (리스트), `prev_close`, `low`, `low_label`, `high`, `high_label`, `volume_vs_avg`

```html
{# 마감 스냅샷 차트 #}
<div class="section-card close-hero">
  <div class="close-hero__header">
    <span class="close-hero__label">KOSPI 종가</span>
    <span class="close-hero__chg {{ 'up' if close_pct >= 0 else 'dn' }}">
      {{ '+' if close_pct >= 0 else '' }}{{ close_pct }}%
    </span>
  </div>
  <canvas id="close-chart-main" class="close-chart" height="140"></canvas>
  <div class="close-chart__meta">
    <span class="close-chart__stat">저점 <strong>{{ low }}</strong> {{ low_label }}</span>
    <span class="close-chart__stat">고점 <strong>{{ high }}</strong> {{ high_label }}</span>
    <span class="close-chart__stat">거래량 평균 대비 <strong>{{ volume_vs_avg }}</strong></span>
  </div>
</div>
<script>
document.addEventListener('DOMContentLoaded', () => {
  drawCloseChart('close-chart-main', {{ chart_prices | tojson }}, {{ prev_close }});
});
</script>
```

`drawCloseChart` 함수는 프로토타입 `briefing-close.html`에서 main.js로 이동한다.

- [ ] **Step 2: close_index.html 작성** (마감 지수)

핵심 변수: `close_indices` 리스트, 각 항목 `{label, value, chg, chg_cls}`

```html
{# 마감 지수 섹션 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">마감 지수</span>
    <span class="t-caption">{{ generated_time }} KST</span>
  </div>
  <div class="idx-grid">
    {% for idx in close_indices %}
    <div class="idx-item">
      <span class="idx-item__label">{{ idx.label }}</span>
      <span class="idx-item__val">{{ idx.value }}</span>
      <span class="idx-item__chg {{ idx.chg_cls }}">{{ idx.chg }}</span>
    </div>
    {% endfor %}
  </div>
</div>
```

- [ ] **Step 3: close_supply.html 작성** (수급)

핵심 변수: `supply_rows` 리스트, 각 항목 `{player, net_amount, chart_data}`

```html
{# 수급 섹션 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">수급</span>
  </div>
  <div class="supply-list">
    {% for row in supply_rows %}
    <div class="supply-row">
      <span class="supply-row__player">{{ row.player }}</span>
      <span class="supply-row__amount {{ 'up' if row.net_amount > 0 else 'dn' }}">
        {{ '+' if row.net_amount > 0 else '' }}{{ row.net_amount | int }}억
      </span>
      <canvas class="supply-mini-chart" id="supply-{{ loop.index }}" height="28"></canvas>
    </div>
    {% endfor %}
  </div>
</div>
<script>
document.addEventListener('DOMContentLoaded', () => {
  {% for row in supply_rows %}
  drawSupplyChart('supply-{{ loop.index }}', {{ row.chart_data | tojson }});
  {% endfor %}
});
</script>
```

- [ ] **Step 4: close_sector.html 작성** (섹터)

핵심 변수: `sectors` 리스트, 각 항목 `{rank, name, chg_pct, chg_cls, stocks_text}`

```html
{# 섹터 섹션 #}
<div class="section-card">
  <div class="section-title-row">
    <span class="section-title">섹터</span>
  </div>
  <div class="sector-list">
    {% for s in sectors %}
    <div class="sector-row">
      <span class="sector-row__rank">{{ s.rank }}</span>
      <span class="sector-row__name">{{ s.name }}</span>
      <span class="sector-row__chg {{ s.chg_cls }}">{{ s.chg_pct }}%</span>
      <span class="sector-row__stocks t-caption">{{ s.stocks_text }}</span>
    </div>
    {% endfor %}
  </div>
</div>
```

- [ ] **Step 5: 커밋**

```bash
git add scripts/templates/sections/close_hero.html scripts/templates/sections/close_index.html \
        scripts/templates/sections/close_supply.html scripts/templates/sections/close_sector.html
git commit -m "feat: 마감 브리핑 전용 섹션 템플릿 4종 작성"
```

---

### Task 7: briefing_list.html (공유 섹션)

**Files:**
- Create: `scripts/templates/sections/briefing_list.html`

- [ ] **Step 1: briefing_list.html 작성**

핵심 변수: `today_card` (dict), `past_rows` (리스트), `active_date` (현재 선택된 날짜 — 하이라이트용), `active_type`

```html
{# 브리핑 목록 섹션 (모든 브리핑 페이지 공유) #}
<section class="bottom-list">
  <div class="bl-section-title">브리핑 목록</div>

  {# TODAY 카드 #}
  <div class="bl-today">
    <div class="bl-today__header">
      <span class="bl-today__date">{{ today_card.date }}</span>
      <span class="bl-today__day">{{ today_card.day_label }}</span>
    </div>
    <div class="bl-today__body">
      {% for slot in today_card.slots %}
      <div class="bl-slot {% if slot.ready %}is-ready{% endif %}
                          {% if slot.type == active_type and today_card.date == active_date %}is-active{% endif %}"
           {% if slot.ready %}onclick="location.href='{{ slot.url }}'"{% endif %}>
        <span class="bl-slot__label">{{ slot.label }}</span>
        {% if slot.ready %}
          <span class="bl-slot__headline">{{ slot.headline }}</span>
          <div class="bl-slot__meta">
            {% if slot.badge_cls %}<span class="bl-pill {{ slot.badge_cls }}">{{ slot.badge_dir }}</span>{% endif %}
            <span class="bl-slot__time">{{ slot.time }}</span>
          </div>
        {% else %}
          <div class="bl-slot__pending">
            <span class="bl-dot"></span> 예정 {{ slot.scheduled_time }}
          </div>
        {% endif %}
      </div>
      {% endfor %}
    </div>
  </div>

  {# 날짜 1행 목록 (최근 30일) #}
  {% if past_rows %}
  <div class="bl-month">{{ past_rows[0].month_label }}</div>
  {% for row in past_rows %}
    {% if row.month_label != loop.previtem.month_label if not loop.first else false %}
    <div class="bl-month">{{ row.month_label }}</div>
    {% endif %}
    <div class="bl-row">
      <div class="bl-row__date">
        <span class="bl-row__num">{{ row.date_short }}</span>
        <span class="bl-row__day">{{ row.day_label }}</span>
      </div>
      {% for cell in row.cells %}
      <div class="bl-cell {% if cell.ready %}is-ready{% else %}is-empty{% endif %}
                          {% if cell.type == active_type and row.date == active_date %}is-active{% endif %}"
           {% if cell.ready %}onclick="location.href='{{ cell.url }}'"{% endif %}>
        <span class="bl-cell__label">{{ cell.label }}</span>
        {% if cell.ready %}
        <div class="bl-cell__bottom">
          {% if cell.badge_cls %}<span class="bl-pill {{ cell.badge_cls }}">{{ cell.badge_dir }}</span>{% endif %}
          <span class="bl-cell__time">{{ cell.time }}</span>
        </div>
        {% else %}
        <span class="bl-cell__empty">미생성</span>
        {% endif %}
      </div>
      {% endfor %}
    </div>
  {% endfor %}
  {% endif %}
</section>
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/sections/briefing_list.html
git commit -m "feat: 공유 브리핑 목록 섹션 템플릿 작성"
```

---

## Phase 3: Config + 조립 템플릿 + generate_html.py 리팩터

### Task 8: config JSON 3종 + 브리핑 조립 템플릿 3종

**Files:**
- Create: `scripts/config/kospi.json`
- Create: `scripts/config/us.json`
- Create: `scripts/config/close.json`
- Create: `scripts/templates/briefings/kospi.html`
- Create: `scripts/templates/briefings/us.html`
- Create: `scripts/templates/briefings/close.html`

- [ ] **Step 1: config JSON 작성**

`scripts/config/kospi.json`:
```json
{
  "type": "kospi",
  "index_name": "KOSPI",
  "template": "briefings/kospi.html",
  "sections_main": ["prediction", "reasons", "stock_picks"],
  "sections_sidebar": ["accuracy"],
  "url_prefix": "kospi",
  "scheduled_time": "07:30"
}
```

`scripts/config/us.json`:
```json
{
  "type": "us",
  "index_name": "S&P500",
  "template": "briefings/us.html",
  "sections_main": ["prediction", "reasons", "watchpoints", "nh_stock", "spill", "momentum"],
  "sections_sidebar": ["accuracy", "market_data"],
  "url_prefix": "us",
  "scheduled_time": "21:20"
}
```

`scripts/config/close.json`:
```json
{
  "type": "close",
  "index_name": "KOSPI",
  "template": "briefings/close.html",
  "sections_main": ["close_hero", "close_index", "close_supply", "close_sector"],
  "sections_sidebar": [],
  "url_prefix": "close",
  "scheduled_time": "15:40"
}
```

- [ ] **Step 2: 코스피 조립 템플릿 작성**

`scripts/templates/briefings/kospi.html`:
```html
{% extends "base.html" %}
{% block title %}{{ date_label }} 코스피 예측 — Double-Shot{% endblock %}
{% block body %}
<div class="layout-wrapper">
  <div class="layout-grid">
    <div class="layout-grid__main">
      {% include "sections/prediction.html" %}
      {% include "sections/reasons.html" %}
      {% include "sections/stock_picks.html" %}
      {% include "sections/briefing_list.html" %}
    </div>
    <div class="layout-grid__right">
      {% include "sections/accuracy.html" %}
      {% include "sections/chip_board_link.html" %}
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: 미국 시장 조립 템플릿 작성**

`scripts/templates/briefings/us.html`:
```html
{% extends "base.html" %}
{% block title %}{{ date_label }} 미국 시장 — Double-Shot{% endblock %}
{% block body %}
<div class="layout-wrapper">
  <div class="layout-grid">
    <div class="layout-grid__main">
      {% include "sections/prediction.html" %}
      {% include "sections/reasons.html" %}
      {% include "sections/watchpoints.html" %}
      {% include "sections/nh_stock.html" %}
      {% include "sections/spill.html" %}
      {% include "sections/momentum.html" %}
      {% include "sections/briefing_list.html" %}
    </div>
    <div class="layout-grid__right">
      {% include "sections/accuracy.html" %}
      {% include "sections/market_data.html" %}
      {% include "sections/chip_board_link.html" %}
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: 마감 조립 템플릿 작성**

`scripts/templates/briefings/close.html`:
```html
{% extends "base.html" %}
{% block title %}{{ date_label }} KOSPI 마감 — Double-Shot{% endblock %}
{% block body %}
<div class="layout-wrapper">
  <div class="layout-grid">
    <div class="layout-grid__main">
      {% include "sections/close_hero.html" %}
      {% include "sections/close_index.html" %}
      {% include "sections/close_supply.html" %}
      {% include "sections/close_sector.html" %}
      {% include "sections/briefing_list.html" %}
    </div>
    <div class="layout-grid__right">
      {% include "sections/chip_board_link.html" %}
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: 커밋**

```bash
git add scripts/config/ scripts/templates/briefings/
git commit -m "feat: config JSON 3종 + 브리핑 조립 템플릿 3종 작성"
```

---

### Task 9: generate_html.py 리팩터

**Files:**
- Modify: `scripts/generate_html.py` (1,086줄 → ~250줄)

기존 파일은 수정 전 내용 파악 후 전면 교체한다.

- [ ] **Step 1: generate_html.py 전면 교체**

```python
#!/usr/bin/env python3
"""브리핑 HTML 조립기 — config-driven section assembly."""

import argparse
import json
import os
from datetime import datetime, date
from pathlib import Path

import pytz
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
BRIEFINGS_DIR = WEB_DIR / "briefings"
TEMPLATES_DIR = Path(__file__).parent / "templates"
CONFIG_DIR = Path(__file__).parent / "config"
KST = pytz.timezone("Asia/Seoul")

BRIEFING_LABELS = {
    "kospi": "코스피 예측",
    "close": "코스피 마감",
    "us": "미국 시장",
}
SCHEDULED_TIMES = {"kospi": "07:30", "close": "15:40", "us": "21:20"}


def make_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)

    def acc_cls(p: int) -> str:
        return "acc-good" if p >= 70 else ("acc-mid" if p >= 50 else "acc-bad")

    env.filters["acc_cls"] = acc_cls
    env.filters["tojson"] = json.dumps
    return env


def fmt_time(generated_at: str) -> str:
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00")).astimezone(KST)
        return dt.strftime("%H:%M")
    except Exception:
        return "--:--"


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_adjacent(briefing_type: str, target_date: str) -> tuple[str | None, str | None]:
    """같은 타입에서 이전/다음 날짜 URL 반환."""
    dirs = sorted(
        d.name for d in BRIEFINGS_DIR.iterdir()
        if d.is_dir() and (d / briefing_type / "index.html").exists()
    )
    if target_date not in dirs:
        return None, None
    idx = dirs.index(target_date)
    prev_url = f"/briefings/{dirs[idx-1]}/{briefing_type}/" if idx > 0 else None
    next_url = f"/briefings/{dirs[idx+1]}/{briefing_type}/" if idx < len(dirs) - 1 else None
    return prev_url, next_url


def build_list_context(target_date: str, target_type: str) -> dict:
    """브리핑 목록 섹션용 컨텍스트 빌드."""
    briefings_data = load_json(DATA_DIR / "briefings.json").get("briefings", [])
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")

    def slot_for(d: str, btype: str) -> dict:
        match = next((b for b in briefings_data if b["date"] == d and b["type"] == btype), None)
        exists = (BRIEFINGS_DIR / d / btype / "index.html").exists()
        if exists and match:
            direction = match.get("predicted_direction", "")
            if btype == "close":
                chg = match.get("actual_change_pct", 0)
                headline = f"KOSPI {'+' if chg >= 0 else ''}{chg:.2f}%"
                badge_cls, badge_dir = None, None
            else:
                badge_cls = "up" if "상승" in direction else "dn"
                badge_dir = ("▲ 상승" if badge_cls == "up" else "▼ 하락")
                headline = direction
            time_str = fmt_time(match.get("generated_at", ""))
            return {"type": btype, "label": BRIEFING_LABELS[btype], "ready": True,
                    "headline": headline, "badge_cls": badge_cls, "badge_dir": badge_dir,
                    "time": time_str, "url": f"/briefings/{d}/{btype}/"}
        return {"type": btype, "label": BRIEFING_LABELS[btype], "ready": False,
                "scheduled_time": SCHEDULED_TIMES[btype]}

    day_names = ["월", "화", "수", "목", "금", "토", "일"]

    def day_label(d: str) -> str:
        try:
            return day_names[date.fromisoformat(d).weekday()]
        except Exception:
            return ""

    today_card = {
        "date": today_kst,
        "day_label": ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"][
            date.fromisoformat(today_kst).weekday()],
        "slots": [slot_for(today_kst, t) for t in ["kospi", "close", "us"]],
    }

    past_dates = sorted(
        {b["date"] for b in briefings_data if b["date"] != today_kst}, reverse=True
    )[:30]

    past_rows = []
    for d in past_dates:
        try:
            dt = date.fromisoformat(d)
        except ValueError:
            continue
        past_rows.append({
            "date": d,
            "date_short": d[5:],   # MM-DD
            "day_label": day_label(d),
            "month_label": f"{dt.year}년 {dt.month}월",
            "cells": [slot_for(d, t) for t in ["kospi", "close", "us"]],
        })

    return {"today_card": today_card, "past_rows": past_rows,
            "active_date": target_date, "active_type": target_type}


def build_accuracy_context(briefing_type: str) -> dict:
    """정확도 섹션 컨텍스트."""
    data = load_json(DATA_DIR / "briefings.json").get("briefings", [])
    typed = [b for b in data if b["type"] == briefing_type and b.get("is_correct") is not None]
    recent_30 = typed[-30:]
    recent_7 = typed[-7:]

    def pct(lst):
        hits = sum(1 for b in lst if b["is_correct"])
        return round(hits / len(lst) * 100) if lst else 0

    dots = [{"status": "hit" if b["is_correct"] else "miss", "date": b["date"]}
            for b in recent_30]
    pending_count = sum(1 for b in data if b["type"] == briefing_type and b.get("is_correct") is None)

    return {
        "acc_7d_pct": pct(recent_7),
        "acc_30d_pct": pct(recent_30),
        "acc_dots": dots,
        "hit": sum(1 for b in recent_30 if b["is_correct"]),
        "miss": sum(1 for b in recent_30 if not b["is_correct"]),
        "pending": pending_count,
    }


def render_briefing(briefing_type: str, target_date: str, analysis: dict) -> str:
    """메인 렌더링 진입점."""
    env = make_env()
    config = load_json(CONFIG_DIR / f"{briefing_type}.json")
    prev_url, next_url = find_adjacent(briefing_type, target_date)

    ctx = {
        **analysis,
        "date_label": target_date,
        "generated_time": fmt_time(analysis.get("generated_at", "")),
        "index_name": config["index_name"],
        "prev_url": prev_url,
        "next_url": next_url,
        "briefing_type": briefing_type,
        **build_accuracy_context(briefing_type),
        **build_list_context(target_date, briefing_type),
        "css_path": "/assets/style.css",
        "js_path": "/assets/main.js",
    }

    template = env.get_template(config["template"])
    return template.render(**ctx)


def write_output(html: str, briefing_type: str, target_date: str):
    out_dir = BRIEFINGS_DIR / target_date / briefing_type
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate_html] wrote {out_dir}/index.html")


def regenerate_index():
    """web/briefings/index.html 재생성 (최신 브리핑 표시)."""
    env = make_env()
    ctx = build_list_context("", "")
    ctx["css_path"] = "/assets/style.css"
    ctx["js_path"] = "/assets/main.js"
    template = env.get_template("pages/briefings_index.html")
    html = template.render(**ctx)
    (BRIEFINGS_DIR / "index.html").write_text(html, encoding="utf-8")
    print("[generate_html] wrote web/briefings/index.html")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=["kospi", "us", "close"])
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--data", required=True, help="analysis JSON 경로")
    args = parser.parse_args()

    analysis = load_json(Path(args.data))
    html = render_briefing(args.type, args.date, analysis)
    write_output(html, args.type, args.date)
    regenerate_index()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 로컬 실행 검증**

```bash
cd /path/to/double-shot
python scripts/generate_html.py \
  --type kospi \
  --date 2026-05-29 \
  --data data/analysis_kospi.json
# 예상 출력:
# [generate_html] wrote web/briefings/2026-05-29/kospi/index.html
# [generate_html] wrote web/briefings/index.html
```

- [ ] **Step 3: 생성된 파일 브라우저 확인**

프로토타입 서버(`http://localhost:8788/briefings/2026-05-29/kospi/`)에서 HTML이 깨짐 없이 표시되는지 확인한다.

- [ ] **Step 4: 커밋**

```bash
git add scripts/generate_html.py
git commit -m "refactor: generate_html.py 1086줄 → 250줄 config-driven 조립기로 교체"
```

---

## Phase 4: 페이지 + 라우팅 업데이트

### Task 10: /briefings 진입 페이지 템플릿

**Files:**
- Create: `scripts/templates/pages/briefings_index.html`

- [ ] **Step 1: briefings_index.html 작성**

프로토타입 `page-briefings-index.html` 참조. `regenerate_index()`가 이 템플릿을 렌더링한다.

```html
{% extends "base.html" %}
{% block title %}브리핑 목록 — Double-Shot{% endblock %}
{% block body %}
<div class="layout-wrapper">
  {# 최신 브리핑 인라인 임베드 자리 (JS로 로드 or SSG) #}
  <div class="latest-bar">
    <span class="latest-bar__label">LATEST</span>
    <span class="latest-bar__info" id="latest-info"></span>
    <button class="latest-bar__copy" onclick="copyLatestUrl()">URL 복사</button>
  </div>
  {# 브리핑 목록만 표시 — 최신 브리핑 콘텐츠는 아이프레임 없이 직접 링크 #}
  {% include "sections/briefing_list.html" %}
</div>
<script>
function copyLatestUrl() {
  const url = window.location.origin + '{{ latest_url | default("/briefings/") }}';
  navigator.clipboard.writeText(url).then(() => alert('URL 복사됨'));
}
</script>
{% endblock %}
```

`regenerate_index()`에서 `latest_url`을 컨텍스트에 주입한다 (가장 최신 브리핑 URL).

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/pages/briefings_index.html
git commit -m "feat: /briefings 진입 페이지 템플릿 작성"
```

---

### Task 11: vercel.json 라우팅 업데이트

**Files:**
- Modify: `vercel.json`

- [ ] **Step 1: vercel.json 수정**

새 URL 구조 `/briefings/{date}/{type}/` 추가 + 레거시 리다이렉트 유지:

```json
{
  "framework": null,
  "outputDirectory": "web",
  "buildCommand": "",
  "installCommand": "npm install",
  "routes": [
    { "src": "^/$", "dest": "/landing.html" },
    { "src": "^/briefings/?$", "dest": "/briefings/index.html" },
    {
      "src": "^/briefings/([0-9]{4}-[0-9]{2}-[0-9]{2})/(kospi|close|us)/?$",
      "dest": "/briefings/$1/$2/index.html"
    },
    { "src": "^/briefings/ko/([^/]+)/?$", "dest": "/briefings/$1/kospi/index.html" },
    { "src": "^/briefings/us/([^/]+)/?$", "dest": "/briefings/$1/us/index.html" },
    { "src": "^/briefings/ko-close/([^/]+)/?$", "dest": "/briefings/$1/close/index.html" },
    { "src": "^/chips$", "dest": "https://chipboard.vercel.app/chips" },
    { "src": "^/chips/(.*)", "dest": "https://chipboard.vercel.app/chips/$1" },
    { "handle": "filesystem" }
  ]
}
```

- [ ] **Step 2: 커밋**

```bash
git add vercel.json
git commit -m "feat: vercel.json 새 URL 구조 추가 + 레거시 리다이렉트 유지"
```

---

## Phase 5: 마무리

### Task 12: favicon.svg 업데이트 (새 B심볼)

**Files:**
- Modify: `web/favicon.svg`

- [ ] **Step 1: favicon.svg 교체**

프로토타입 `docs/prototypes/favicon-b.svg` 내용을 `web/favicon.svg`로 복사한다:

```bash
cp docs/prototypes/favicon-b.svg web/favicon.svg
```

- [ ] **Step 2: 커밋**

```bash
git add web/favicon.svg
git commit -m "style: favicon.svg → 새 B심볼 (상승 듀얼 캔들)"
```

---

### Task 13: call_claude.py 어조 프롬프트 수정

**Files:**
- Modify: `scripts/call_claude.py`

- [ ] **Step 1: 기존 어조 지침 위치 확인**

```bash
grep -n "해요\|어요\|Bloomberg\|어조\|tone\|선언" scripts/call_claude.py | head -20
```

- [ ] **Step 2: 시스템 프롬프트에서 어조 지침 교체**

`~해요/~거든요` 스타일 지침을 찾아 아래로 교체한다:

```python
# 기존 어조 지침 제거 후 아래 추가
TONE_INSTRUCTION = """
어조 원칙:
- 대상: 15년차+ 전문 투자자. 투자 판단은 독자가 한다.
- 문체: 선언형. Bloomberg/Reuters 헤드라인 스타일.
  예) "S&P500 +0.58%. 기술주 중심 강세로 코스피 갭업 출발이 기대된다."
- 금지: ~해요, ~어요, ~거든요, ~이에요 등 친근체.
- 문장은 짧고 밀도 높게. 수치를 앞에 배치.
"""
```

프롬프트 구성 코드에서 `TONE_INSTRUCTION`을 시스템 프롬프트 또는 유저 메시지 앞에 삽입한다.

- [ ] **Step 3: 테스트 실행 (dry_run)**

```bash
python scripts/call_claude.py --type kospi --dry-run 2>&1 | head -50
# 예상: Claude가 반환한 JSON에 "해요" 대신 선언형 문체가 사용됨
```

- [ ] **Step 4: 커밋**

```bash
git add scripts/call_claude.py
git commit -m "feat: AI 어조 친근체 → Bloomberg 선언형으로 변경"
```

---

### Task 14: E2E 검증

- [ ] **Step 1: 브리핑 3종 전체 생성**

```bash
# kospi
python scripts/generate_html.py --type kospi --date 2026-05-29 --data data/analysis_kospi.json

# close
python scripts/generate_html.py --type close --date 2026-05-29 --data data/analysis_kospi.json

# us
python scripts/generate_html.py --type us --date 2026-05-29 --data data/analysis_us.json
```

- [ ] **Step 2: 출력 파일 구조 확인**

```bash
find web/briefings/2026-05-29 -type f
# 예상:
# web/briefings/2026-05-29/kospi/index.html
# web/briefings/2026-05-29/close/index.html
# web/briefings/2026-05-29/us/index.html
```

- [ ] **Step 3: 로컬 서버로 브라우저 점검**

```bash
python3 -m http.server 8788 --directory web
```

점검 체크리스트:
- [ ] `http://localhost:8788/briefings/` — 목록 페이지 표시 확인
- [ ] `http://localhost:8788/briefings/2026-05-29/kospi/` — 코스피 예측 표시
- [ ] `http://localhost:8788/briefings/2026-05-29/close/` — 마감 브리핑 표시
- [ ] `http://localhost:8788/briefings/2026-05-29/us/` — 미국 시장 표시
- [ ] 각 페이지 모바일 375px 뷰포트에서 레이아웃 깨짐 없음
- [ ] ‹ › 네비게이션 클릭 시 이전/다음 날짜로 이동
- [ ] 다크모드 토글 동작
- [ ] 콘솔 에러 없음

- [ ] **Step 4: GitHub Actions 워크플로 파라미터 확인**

```bash
grep -A5 "generate_html" .github/workflows/daily_report.yml
```

기존 워크플로에서 `generate_html.py`를 호출하는 인수가 새 시그니처 `--type --date --data`와 일치하는지 확인하고 불일치 시 수정.

- [ ] **Step 5: 레거시 URL 리다이렉트 검증**

```bash
# Vercel preview 배포 후 아래 URL들이 올바르게 리다이렉트 되는지 확인
curl -I https://doubleshot.space/briefings/ko/2026-05-29/
# Location: /briefings/2026-05-29/kospi/index.html (302)
```

- [ ] **Step 6: 최종 커밋**

```bash
git add .
git commit -m "feat: Double-Shot 전면 재구축 완료 — config-driven section assembly"
```

---

## 주요 주의사항

| 항목 | 내용 |
|------|------|
| 기존 URL 유지 | `/briefings/ko/{date}/`, `/briefings/us/{date}/`, `/briefings/ko-close/{date}/` 레거시 3종은 vercel.json 리다이렉트로 유지 |
| briefings.json 기존 데이터 | 구조 변경 없이 유지. close 타입 항목의 `is_correct`는 None일 수 있음 |
| 차트 함수 이동 | `drawMiniChart`, `drawCloseChart`, `drawSupplyChart` — 프로토타입 인라인 `<script>`에서 `main.js`로 이동 |
| CSS 경로 | 생성된 HTML이 `/assets/style.css` (절대 경로)를 참조해야 함. 상대 경로 주의 |
| 텔레그램 발송 | 이 플랜 범위 밖. `send_telegram.py`는 현행 유지 |
| patch_fg.py 등 임시 픽스 | 이 플랜에서 제거하지 않음. 새 구조 안정화 후 별도 PR로 정리 |
