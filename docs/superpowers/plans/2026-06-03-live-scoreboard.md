# 라이브 예측 스코어보드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 브리핑 메인 컬럼 최상단에 장중(09:00~15:30 KST) 실시간 판정 스코어보드를 추가한다.

**Architecture:** Jinja2 정적 템플릿(`_live_scoreboard.html`)으로 예측 데이터를 HTML에 심고, 클라이언트 JS(`initLiveScoreboard()`)가 장중 여부를 판단해 카드를 노출·갱신한다. 지수는 기존 `/api/kospi-live` 30초 폴링, 뉴스 이슈는 새로 추가하는 `kospi-news-live.json`을 5분 폴링한다. 뉴스 JSON은 GitHub Actions `kospi-news-live` 잡이 장중 매 정시(09~15시) Gemini로 갱신한다.

**Tech Stack:** Jinja2, Vanilla JS (ES5), CSS custom properties, Python 3 + google-genai, GitHub Actions

---

## 파일 맵

| 상태 | 파일 | 역할 |
|------|------|------|
| 신규 | `scripts/templates/sections/_live_scoreboard.html` | 스코어보드 HTML (Jinja2) |
| 수정 | `web/assets/style.css` | `.lsb-*` CSS + `--gold`/`--gold-bg` 토큰 추가 |
| 수정 | `web/assets/main.js` | `initLiveScoreboard()` + `lsbToggleAccordion()` 추가 |
| 수정 | `scripts/templates/briefings/kospi.html` | 스코어보드 include (메인 최상단) |
| 신규 | `web/data/kospi-news-live.json` | 장중 뉴스 이슈 (초기값 → cron 갱신) |
| 신규 | `scripts/fetch_news_live.py` | Gemini 장중 뉴스 수집 스크립트 |
| 수정 | `.github/workflows/daily_report.yml` | `kospi-news-live` 잡 추가 |
| 수정 | `api/trigger.mjs` | `VALID_TYPES`에 `kospi-news-live` 추가 |

---

## Task 1: HTML 템플릿 — `_live_scoreboard.html`

**Files:**
- Create: `scripts/templates/sections/_live_scoreboard.html`

- [ ] **Step 1: 파일 생성**

```jinja2
{# 라이브 예측 스코어보드 — 장중(09:00~15:30 KST)에만 활성화, 메인 컬럼 최상단 #}
<div id="live-scoreboard"
     data-dir="{{ dir_cls }}"
     data-pred-pct="{{ up_pct }}"
     data-pred-label="{{ dir_arrow }} {{ direction }}"
     style="display:none;margin-bottom:12px;">
  <div class="lsb-card">

    <div class="lsb-head">
      <span class="lsb-title">예측 vs 실제 · 코스피</span>
      <span class="lsb-live-badge" id="lsb-badge">
        <span class="lsb-live-dot"></span>LIVE
      </span>
    </div>

    <div class="lsb-verdict" id="lsb-headline">로딩 중…</div>
    <div class="lsb-sub" id="lsb-sub">
      아침 "{{ dir_arrow }} {{ direction }}(신뢰도 {{ confidence_label }})" 예측을 추적 중입니다.
    </div>

    <div class="lsb-gauge" aria-hidden="true">
      <div class="lsb-gauge-track">
        <div class="lsb-gauge-needle" id="lsb-needle" style="left:50%"></div>
      </div>
      <div class="lsb-gauge-zones">
        <span>이탈</span><span>박빙</span><span>적중</span>
      </div>
    </div>

    <div class="lsb-now-row">
      <span class="lsb-idx" id="lsb-idx">—</span>
      <span class="lsb-chg" id="lsb-chg">—</span>
      <span class="lsb-pred-tag" id="lsb-pred-tag">{{ dir_arrow }} {{ direction }}</span>
      <span class="lsb-refresh">↻ 30초</span>
    </div>

    <div class="lsb-divider"></div>

    <div class="lsb-news">
      <div class="lsb-news-header">
        <span class="lsb-news-dot"></span>
        <span id="lsb-news-stamp">업데이트 대기 중…</span>
      </div>
      <div id="lsb-news-latest"></div>
      <div class="lsb-accordion" id="lsb-accordion" style="display:none">
        <button class="lsb-accordion-toggle" id="lsb-accordion-btn"
                onclick="lsbToggleAccordion()" type="button">
          <span class="lsb-ac-left">
            <span class="lsb-ac-prev-time" id="lsb-ac-prev-time"></span>
            <span class="lsb-ac-prev-title" id="lsb-ac-prev-title"></span>
          </span>
          <span class="lsb-chevron"></span>
        </button>
        <div class="lsb-accordion-body" id="lsb-accordion-body"></div>
      </div>
    </div>

    <div class="lsb-foot">
      마감까지 <strong id="lsb-countdown">—</strong>
    </div>

  </div>
</div>
```

- [ ] **Step 2: 프리뷰 서버에서 HTML 구조 확인**

`scripts/generate_html.py`가 kospi.html을 렌더링하기 전에는 실제 변수가 없으므로, 우선 구조만 확인한다. 실제 렌더링은 Task 4 이후.

---

## Task 2: CSS — `style.css`에 `.lsb-*` 및 `--gold` 토큰 추가

**Files:**
- Modify: `web/assets/style.css` (끝에 추가)

- [ ] **Step 1: `:root` 블록에 gold 토큰 추가**

`style.css` 7번 줄 `:root { ... }` 블록 안의 `--dn-bg:#DBE8FE;` 뒤에 추가:

```css
--gold:#B7791F;--gold-bg:#FEF9C3;
```

`html.dark { ... }` 블록 안의 `--dn-bg:rgba(39,117,237,.14);` 뒤에 추가:

```css
--gold:#D97706;--gold-bg:rgba(217,119,6,.15);
```

- [ ] **Step 2: 파일 맨 끝에 스코어보드 CSS 블록 추가**

```css
/* ── 라이브 스코어보드 ── */
.lsb-card{background:var(--canvas);border:1px solid var(--hairline);border-radius:var(--r-lg);box-shadow:var(--s2);overflow:hidden;}
.lsb-head{display:flex;align-items:center;justify-content:space-between;padding:14px 18px 0;margin-bottom:12px;}
.lsb-title{font-size:13px;font-weight:700;color:var(--muted);}
.lsb-live-badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:700;color:#1a7f37;background:#dafbe1;padding:3px 9px;border-radius:999px;}
html.dark .lsb-live-badge{background:rgba(45,164,78,.18);color:#4ac26b;}
.lsb-live-dot{width:6px;height:6px;border-radius:50%;background:#2da44e;animation:lsb-pulse 1.4s infinite;}
html.dark .lsb-live-dot{background:#4ac26b;}
@keyframes lsb-pulse{0%,100%{opacity:1}50%{opacity:.3}}
.lsb-closed-badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:700;color:var(--muted);background:var(--surface-inset);padding:3px 9px;border-radius:999px;}
.lsb-verdict{padding:0 18px;font-size:19px;font-weight:700;letter-spacing:-.3px;margin-bottom:4px;}
.lsb-sub{padding:0 18px;font-size:12.5px;color:var(--muted);margin-bottom:14px;line-height:1.45;}
.lsb-gauge{position:relative;height:40px;margin:0 20px;}
.lsb-gauge-track{position:absolute;top:14px;left:0;right:0;height:8px;border-radius:4px;background:linear-gradient(90deg,var(--primary-bg) 0%,var(--primary-bg) 33%,var(--surface-inset) 33%,var(--surface-inset) 67%,var(--up-bg) 67%,var(--up-bg) 100%);}
.lsb-gauge-needle{position:absolute;top:4px;width:3px;height:28px;border-radius:2px;background:var(--ink);transform:translateX(-50%);transition:left .5s ease;}
.lsb-gauge-needle::after{content:'';position:absolute;top:-6px;left:50%;transform:translateX(-50%);border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid var(--ink);border-radius:1px;}
.lsb-gauge-zones{display:flex;font-size:10px;color:var(--muted);margin:2px 0 0;}
.lsb-gauge-zones span{flex:1;}
.lsb-gauge-zones span:nth-child(2){text-align:center;}
.lsb-gauge-zones span:last-child{text-align:right;}
.lsb-now-row{display:flex;align-items:center;gap:10px;margin:14px 18px 0;padding:11px 14px;background:var(--surface-soft);border-radius:var(--r-md);}
.lsb-idx{font-size:20px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap;}
.lsb-chg{font-size:14px;font-weight:700;}
.lsb-pred-tag{margin-left:auto;font-size:11px;font-weight:700;padding:3px 9px;border-radius:var(--r-sm);white-space:nowrap;}
.lsb-refresh{font-size:10px;color:var(--muted);white-space:nowrap;flex-shrink:0;}
.lsb-divider{height:1px;background:var(--hairline);margin:14px 0 0;}
.lsb-news{padding:14px 18px 12px;}
.lsb-news-header{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--muted);margin-bottom:10px;font-weight:600;letter-spacing:.3px;}
.lsb-news-dot{width:5px;height:5px;border-radius:50%;background:var(--primary);flex-shrink:0;}
.lsb-news-card{background:var(--primary-bg);border:1px solid rgba(0,110,255,.15);border-radius:var(--r-md);padding:13px 14px;}
html.dark .lsb-news-card{border-color:rgba(59,139,255,.2);}
.lsb-news-title{font-size:14px;font-weight:600;color:var(--ink);margin-bottom:6px;line-height:1.35;}
.lsb-news-body{font-size:12.5px;color:var(--muted);line-height:1.55;}
.lsb-accordion{border-top:1px solid var(--hairline);margin-top:10px;}
.lsb-accordion-toggle{display:flex;align-items:center;justify-content:space-between;width:100%;background:none;border:none;cursor:pointer;padding:10px 0;font-family:inherit;}
.lsb-accordion-toggle:hover{opacity:.75;}
.lsb-ac-left{display:flex;align-items:center;gap:8px;overflow:hidden;flex:1;min-width:0;}
.lsb-ac-prev-time{font-size:11px;color:var(--muted);font-weight:700;flex-shrink:0;font-variant-numeric:tabular-nums;}
.lsb-ac-prev-title{font-size:13px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.lsb-chevron{width:16px;height:16px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;transition:transform .25s;}
.lsb-chevron::after{content:'';display:block;width:8px;height:8px;border-right:1.5px solid var(--muted);border-bottom:1.5px solid var(--muted);transform:rotate(45deg) translateY(-2px);border-radius:1px;}
.lsb-accordion-toggle.open .lsb-chevron{transform:rotate(180deg);}
.lsb-accordion-body{display:none;padding-bottom:4px;}
.lsb-accordion-body.open{display:block;}
.lsb-news-item{display:flex;gap:12px;padding:11px 0;border-bottom:1px solid var(--hairline);}
.lsb-news-item:last-child{border-bottom:none;}
.lsb-ni-time{font-size:10px;color:var(--muted);font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap;padding-top:2px;width:36px;flex-shrink:0;}
.lsb-ni-title{font-size:13px;font-weight:600;color:var(--ink);line-height:1.35;}
.lsb-foot{display:flex;align-items:center;padding:11px 18px;border-top:1px solid var(--hairline);font-size:11px;color:var(--muted);background:var(--surface-soft);}
.lsb-foot strong{font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums;}
```

- [ ] **Step 3: 커밋**

```bash
git add web/assets/style.css
git commit -m "style: 라이브 스코어보드 CSS 추가 + gold 토큰"
```

---

## Task 3: JS — `main.js`에 `initLiveScoreboard()` 추가

**Files:**
- Modify: `web/assets/main.js`

`window.addEventListener('load', ...)` 블록 안 `loadChipWidget();` 바로 앞에 `initLiveScoreboard();` 호출을 추가하고, 함수 본체를 파일 끝 `loadChipWidget` 함수 위에 삽입한다.

- [ ] **Step 1: load 핸들러에 호출 추가**

기존:
```javascript
    loadChipWidget();
```
→ 변경:
```javascript
    initLiveScoreboard();
    loadChipWidget();
```

- [ ] **Step 2: `lsbToggleAccordion` 전역 함수 추가 (파일 끝 `loadChipWidget` 함수 바로 위)**

```javascript
  /* ── 라이브 스코어보드 아코디언 ── */
  function lsbToggleAccordion() {
    var btn  = document.getElementById('lsb-accordion-btn');
    var body = document.getElementById('lsb-accordion-body');
    if (!btn || !body) return;
    var isOpen = body.classList.contains('open');
    body.classList.toggle('open', !isOpen);
    btn.classList.toggle('open', !isOpen);
  }
  window.lsbToggleAccordion = lsbToggleAccordion;
```

- [ ] **Step 3: `initLiveScoreboard` 함수 추가 (바로 아래)**

```javascript
  /* ── 라이브 스코어보드 초기화 ── */
  function initLiveScoreboard() {
    var el = document.getElementById('live-scoreboard');
    if (!el) return;

    var dir     = el.dataset.dir || 'up';   // 'up' | 'dn'

    function kstNow() {
      return new Date(Date.now() + 9 * 3600 * 1000);
    }
    function isMarketHours() {
      var k = kstNow(), day = k.getUTCDay();
      if (day === 0 || day === 6) return false;
      var mins = k.getUTCHours() * 60 + k.getUTCMinutes();
      return mins >= 540 && mins < 930;   // 09:00~15:29
    }
    function isAfterMarket() {
      var k = kstNow(), day = k.getUTCDay();
      if (day === 0 || day === 6) return false;
      var mins = k.getUTCHours() * 60 + k.getUTCMinutes();
      return mins >= 930;
    }

    if (!isMarketHours() && !isAfterMarket()) return;
    el.style.display = '';

    if (isAfterMarket()) {
      var badge = document.getElementById('lsb-badge');
      if (badge) {
        badge.className = 'lsb-closed-badge';
        badge.textContent = '마감';
      }
    }

    function calcVerdict(changePct) {
      if (Math.abs(changePct) <= 0.1) return 'tight';
      if (dir === 'up'  && changePct >  0.1) return 'hit';
      if (dir === 'dn'  && changePct < -0.1) return 'hit';
      return 'miss';
    }

    var VERDICT = {
      hit:   { headline: '예측대로 순항 중',  color: 'var(--up)', bg: 'var(--up-bg)' },
      tight: { headline: '팽팽한 접전',        color: 'var(--gold)', bg: 'var(--gold-bg)' },
      miss:  { headline: '빗나가는 중',        color: 'var(--dn)', bg: 'var(--dn-bg)' },
    };

    function updateDisplay(price, changePct) {
      var verdict = calcVerdict(changePct);
      var v = VERDICT[verdict];

      var idxEl     = document.getElementById('lsb-idx');
      var chgEl     = document.getElementById('lsb-chg');
      var headEl    = document.getElementById('lsb-headline');
      var needleEl  = document.getElementById('lsb-needle');
      var predTagEl = document.getElementById('lsb-pred-tag');

      if (idxEl) idxEl.textContent = price.toLocaleString('ko-KR', {minimumFractionDigits:2, maximumFractionDigits:2});

      var sign = changePct >= 0 ? '+' : '';
      if (chgEl) {
        chgEl.textContent = sign + changePct.toFixed(2) + '%';
        chgEl.style.color = changePct >= 0 ? 'var(--up)' : 'var(--dn)';
      }

      if (headEl) { headEl.textContent = v.headline; headEl.style.color = v.color; }

      // 바늘 위치: 예측 방향 기준으로 0(이탈)~100(적중) 매핑, ±2% 포화
      var rawPos;
      if (dir === 'up') {
        rawPos = Math.max(0, Math.min(100, (changePct + 2) / 4 * 100));
      } else {
        rawPos = Math.max(0, Math.min(100, (-changePct + 2) / 4 * 100));
      }
      if (needleEl) needleEl.style.left = rawPos + '%';

      if (predTagEl) {
        predTagEl.style.background = v.bg;
        predTagEl.style.color = v.color;
      }
    }

    function fetchKospi() {
      fetch('/api/kospi-live')
        .then(function(r) { return r.json(); })
        .then(function(d) { if (d && d.price) updateDisplay(d.price, d.changePct || 0); })
        .catch(function() {});
    }

    function escHtml(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function renderNews(d) {
      if (!d || !d.latest) return;
      var stampEl    = document.getElementById('lsb-news-stamp');
      var latestEl   = document.getElementById('lsb-news-latest');
      var accordionEl = document.getElementById('lsb-accordion');
      var bodyEl     = document.getElementById('lsb-accordion-body');
      var prevTimeEl = document.getElementById('lsb-ac-prev-time');
      var prevTitleEl= document.getElementById('lsb-ac-prev-title');

      if (stampEl) {
        stampEl.innerHTML = '<span style="color:var(--primary);font-weight:700">방금 업데이트</span>'
          + ' · ' + escHtml(d.updated_at) + ' 기준 · 매 1시간 갱신';
      }
      if (latestEl) {
        latestEl.innerHTML = '<div class="lsb-news-card">'
          + '<div class="lsb-news-title">' + escHtml(d.latest.title) + '</div>'
          + '<div class="lsb-news-body">'  + escHtml(d.latest.summary) + '</div>'
          + '</div>';
      }

      var hist = d.history || [];
      if (hist.length > 0 && accordionEl) {
        accordionEl.style.display = '';
        if (prevTimeEl)  prevTimeEl.textContent  = hist[0].time;
        if (prevTitleEl) prevTitleEl.textContent = hist[0].title;
        if (bodyEl) {
          bodyEl.innerHTML = hist.map(function(item) {
            return '<div class="lsb-news-item">'
              + '<span class="lsb-ni-time">' + escHtml(item.time) + '</span>'
              + '<div class="lsb-ni-title">' + escHtml(item.title) + '</div>'
              + '</div>';
          }).join('');
        }
      }
    }

    function fetchNews() {
      fetch('/data/kospi-news-live.json?t=' + Date.now())
        .then(function(r) { return r.json(); })
        .then(renderNews)
        .catch(function() {});
    }

    function updateCountdown() {
      var k = kstNow();
      var close = new Date(k);
      close.setUTCHours(6, 30, 0, 0);   // 15:30 KST = 06:30 UTC
      if (close <= k) { document.getElementById('lsb-countdown').textContent = '마감'; return; }
      var diff = close - k;
      var h = Math.floor(diff / 3600000);
      var m = Math.floor((diff % 3600000) / 60000);
      var s = Math.floor((diff % 60000) / 1000);
      var el2 = document.getElementById('lsb-countdown');
      if (el2) el2.textContent = h + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
    }

    fetchKospi();
    fetchNews();
    updateCountdown();

    if (isMarketHours()) {
      setInterval(fetchKospi, 30000);
      setInterval(fetchNews, 5 * 60000);
      setInterval(updateCountdown, 1000);
    }
  }
```

- [ ] **Step 4: 커밋**

```bash
git add web/assets/main.js
git commit -m "feat: initLiveScoreboard() 추가 — 30초 지수 폴링 + 뉴스 렌더링"
```

---

## Task 4: 코스피 템플릿 — `kospi.html`에 include 추가

**Files:**
- Modify: `scripts/templates/briefings/kospi.html`

- [ ] **Step 1: `<main class="layout-grid__main">` 바로 아래에 include 삽입**

기존:
```jinja2
    <main class="layout-grid__main">
      <div class="accordion-item is-open is-today">
```
→ 변경:
```jinja2
    <main class="layout-grid__main">
      {% include "sections/_live_scoreboard.html" %}
      <div class="accordion-item is-open is-today">
```

- [ ] **Step 2: `generate_html.py`로 오늘 브리핑 재생성하여 HTML 확인**

```bash
cd /Users/luke/Service\ App/double-shot
# 최근 생성된 코스피 분석 파일 확인
ls -la data/analysis_kospi.json

# HTML 재생성 (analysis 파일이 있는 경우)
python3 scripts/generate_html.py --type kospi --date $(date +%Y-%m-%d) \
  --data-file data/analysis_kospi.json
```

생성된 HTML에서 `live-scoreboard` div가 `.accordion-item` 위에 있는지 확인:
```bash
grep -n "live-scoreboard\|accordion-item is-open" \
  web/briefings/$(date +%Y-%m-%d)/kospi/index.html | head -5
```
Expected: `live-scoreboard` 줄 번호 < `accordion-item is-open` 줄 번호

- [ ] **Step 3: 브라우저 프리뷰에서 layout 확인**

`http://localhost:8789`에서 코스피 브리핑 열기.
장 외 시간에는 스코어보드가 숨겨져(`display:none`) 기존 레이아웃과 동일해야 함.
브라우저 콘솔에서 장중 시뮬레이션:

```javascript
// 콘솔에서 강제 노출 테스트
document.getElementById('live-scoreboard').style.display = '';
```

카드 레이아웃이 깨지지 않는지, 모바일(375px)에서 최상단에 표시되는지 확인.

- [ ] **Step 4: 커밋**

```bash
git add scripts/templates/briefings/kospi.html
git commit -m "feat: 코스피 브리핑 메인 최상단에 라이브 스코어보드 include 추가"
```

---

## Task 5: 초기 JSON — `web/data/kospi-news-live.json`

**Files:**
- Create: `web/data/kospi-news-live.json`

- [ ] **Step 1: 파일 생성**

```json
{
  "updated_at": "—",
  "latest": {
    "title": "오늘의 이슈 준비 중",
    "summary": "장 시작 후 첫 정시(09:00)에 업데이트됩니다."
  },
  "history": []
}
```

- [ ] **Step 2: 커밋**

```bash
git add web/data/kospi-news-live.json
git commit -m "data: kospi-news-live.json 초기값 추가"
```

---

## Task 6: Gemini 뉴스 스크립트 — `scripts/fetch_news_live.py`

**Files:**
- Create: `scripts/fetch_news_live.py`

- [ ] **Step 1: 파일 생성**

```python
# 장중 코스피 핵심 이슈를 Gemini Google Search로 수집해 kospi-news-live.json을 갱신하는 스크립트
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).parent.parent
OUT_PATH = REPO_ROOT / "web" / "data" / "kospi-news-live.json"
MAX_HISTORY = 6

PROMPT = """
지금 {today} {time} KST 기준, 코스피 장중에 가장 큰 영향을 주는 핵심 이슈 1개를 알려주세요.

아래 JSON 형식만 출력하세요 (마크다운·추가 텍스트 없이):
{{
  "title": "이슈 제목 (15자 이내)",
  "summary": "한 줄 요약 (40자 이내)"
}}
"""


def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        cfg = REPO_ROOT / "config.json"
        if cfg.exists():
            key = json.loads(cfg.read_text()).get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found in env or config.json")
    return key


def fetch_latest_issue(today: str, time_str: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=get_gemini_api_key())
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=PROMPT.format(today=today, time=time_str),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.3,
            max_output_tokens=256,
        ),
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    m = re.search(r"\{[\s\S]*?\}", raw)
    if m:
        raw = m.group(0)
    return json.loads(raw)


def main() -> None:
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    print(f"[fetch_news_live] {today} {time_str} KST — Gemini 이슈 수집 시작")

    try:
        latest = fetch_latest_issue(today, time_str)
    except Exception as e:
        print(f"[fetch_news_live] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # 기존 latest를 history 맨 앞에 추가
    history: list = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            prev = existing.get("latest")
            if prev and prev.get("title"):
                history = [{"time": existing.get("updated_at", ""), **prev}]
            history += existing.get("history", [])
            history = history[:MAX_HISTORY]
        except Exception:
            pass

    data = {"updated_at": time_str, "latest": latest, "history": history}
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_news_live] Saved → {OUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 로컬 실행 테스트 (GEMINI_API_KEY 환경변수 필요)**

```bash
cd /Users/luke/Service\ App/double-shot
GEMINI_API_KEY=$(python3 -c "import json; print(json.load(open('config.json'))['GEMINI_API_KEY'])") \
  python3 scripts/fetch_news_live.py
```

Expected 출력:
```
[fetch_news_live] 2026-06-03 HH:MM KST — Gemini 이슈 수집 시작
[fetch_news_live] Saved → .../web/data/kospi-news-live.json
```

Expected JSON 구조:
```bash
cat web/data/kospi-news-live.json
# { "updated_at": "HH:MM", "latest": { "title": "...", "summary": "..." }, "history": [] }
```

- [ ] **Step 3: 두 번 실행하여 history 누적 확인**

```bash
GEMINI_API_KEY=... python3 scripts/fetch_news_live.py
cat web/data/kospi-news-live.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('history:', len(d['history']))"
```

Expected: `history: 1`

- [ ] **Step 4: 커밋**

```bash
git add scripts/fetch_news_live.py web/data/kospi-news-live.json
git commit -m "feat: fetch_news_live.py — Gemini 장중 뉴스 이슈 수집"
```

---

## Task 7: GitHub Actions — `kospi-news-live` 잡 추가

**Files:**
- Modify: `.github/workflows/daily_report.yml`
- Modify: `api/trigger.mjs`

- [ ] **Step 1: `trigger.mjs` VALID_TYPES에 추가**

기존:
```javascript
const VALID_TYPES = ['kospi', 'kospi-close', 'us', 'accuracy'];
```
→ 변경:
```javascript
const VALID_TYPES = ['kospi', 'kospi-close', 'us', 'accuracy', 'kospi-news-live'];
```

- [ ] **Step 2: `daily_report.yml` workflow inputs choices에 추가**

`briefing_type` options 목록에 `kospi-news-live` 추가:

```yaml
        options:
          - kospi
          - us
          - kospi-close
          - accuracy
          - kospi-news-live
```

- [ ] **Step 3: `daily_report.yml` 끝에 신규 잡 추가**

파일 끝(마지막 job 다음)에 아래 잡 추가:

```yaml
  kospi-news-live:
    name: "📰 코스피 장중 뉴스 갱신"
    runs-on: ubuntu-latest
    if: >-
      github.event_name == 'workflow_dispatch' &&
      github.event.inputs.briefing_type == 'kospi-news-live'

    steps:
      - name: 📥 체크아웃
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GH_PAT }}

      - name: 🐍 Python 세팅
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: 📦 의존성 설치
        run: pip install google-genai

      - name: 📰 뉴스 이슈 수집
        run: python3 scripts/fetch_news_live.py

      - name: 💾 JSON 커밋 & 푸시
        run: |
          git config user.name  "DailyB Bot"
          git config user.email "bot@doubleshot.space"
          git add web/data/kospi-news-live.json
          if git diff --cached --quiet; then
            echo "변경 없음, 커밋 스킵"
          else
            git commit -m "data: 코스피 장중 뉴스 갱신 $(date +'%H:%M' -d '+9 hours') KST"
            git push
          fi

      - name: 🚀 GitHub Pages 배포
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./web
          keep_files: true
```

- [ ] **Step 4: Vercel cron 스케줄 확인**

`vercel.json`에 장중 매 정시(KST 09~15시 = UTC 00~06시) cron 트리거 추가.
기존 cron 패턴을 확인한 뒤:

```bash
cat vercel.json | python3 -c "import json,sys; d=json.load(sys.stdin); [print(c) for c in d.get('crons',[])]"
```

아직 없으면 `vercel.json`의 `crons` 배열에 추가:

```json
{ "path": "/api/trigger?type=kospi-news-live", "schedule": "0 0-6 * * 1-5" }
```

(UTC 00:00~06:00 매 정시, 월~금 = KST 09:00~15:00)

- [ ] **Step 5: 커밋**

```bash
git add .github/workflows/daily_report.yml api/trigger.mjs vercel.json
git commit -m "feat: GitHub Actions kospi-news-live 잡 + Vercel cron 추가"
```

---

## Task 8: 통합 검증

- [ ] **Step 1: 장중 시뮬레이션 (브라우저 콘솔)**

오늘 코스피 브리핑 페이지(`http://localhost:8788/briefings/YYYY-MM-DD/kospi/`)를 열고:

```javascript
// 장중 강제 노출
document.getElementById('live-scoreboard').style.display = '';
// 지수 수동 업데이트
document.getElementById('lsb-idx').textContent = '2,718.40';
document.getElementById('lsb-chg').textContent = '+0.42%';
document.getElementById('lsb-chg').style.color = 'var(--up)';
document.getElementById('lsb-headline').textContent = '예측대로 순항 중';
document.getElementById('lsb-headline').style.color = 'var(--up)';
document.getElementById('lsb-needle').style.left = '76%';
```

확인 항목:
- 카드가 아코디언 위에 표시됨
- 모바일(375px resize)에서 최상단에 표시됨
- 다크모드 토글 시 색상 깨짐 없음

- [ ] **Step 2: `/api/kospi-live` 실제 응답 확인**

```bash
curl https://doubleshot.space/api/kospi-live
# Expected: { "price": ..., "changePct": ..., "marketStatus": "...", ... }
```

- [ ] **Step 3: GitHub Actions 수동 트리거 테스트 (dry_run=false)**

GitHub Actions 탭 → `Daily 30 Report` → Run workflow → `briefing_type: kospi-news-live` → 실행

완료 후 확인:
```bash
git pull
cat web/data/kospi-news-live.json
# updated_at이 갱신됐는지 확인
```

- [ ] **Step 4: 최종 커밋 확인**

```bash
git log --oneline -6
```
