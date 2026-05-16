# Briefing UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 브리핑 페이지 우측 사이드바 개편(정확도 카드 Option C + 시장 지표 유형별 슬림화 + 공포탐욕지수 + 조용한 CTA)과 아카이브 섹션을 아코디언에서 카드 리스트로 교체한다.

**Architecture:** `generate_html.py`에서 streak/accuracy lookup/sidebar_items 계산을 확장하고, `main.js`에 공포탐욕지수 렌더링 함수를 추가한 뒤, 두 Jinja2 템플릿(`index.html`, `briefing.html`)과 `style.css`를 수정해 새 UI를 적용한다.

**Tech Stack:** Python(Jinja2, generate_html.py), Vanilla JS(main.js), CSS(style.css), HTML templates

---

## 변경 파일 맵

| 파일 | 역할 |
|------|------|
| `web/assets/style.css` | Option C 정확도 카드 스타일, 아카이브 카드 스타일, CTA 스타일 추가 |
| `scripts/generate_html.py` | streak 계산, accuracy lookup, sidebar_items 유형별 분기, fearGreed pop 제거 |
| `web/assets/main.js` | FG 모달 함수, renderFG/drawFGGauge, ctaSubscribe 추가 |
| `scripts/templates/index.html` | 정확도 카드 → Option C, 아카이브 → 카드 리스트, FG 모달, CTA |
| `scripts/templates/briefing.html` | 정확도 카드 → Option C, FG 블록 + 모달, CTA |

---

## Task 1: CSS — 새 스타일 추가

**Files:**
- Modify: `web/assets/style.css` (기존 acc-* 클래스 근처에 추가)

- [ ] **Step 1-1: 정확도 카드 Option C 스타일 추가**

`style.css`의 `.acc-dot.wrong   { background: #E03131; }` 아래 (line 1840)에 추가:

```css
/* ── 정확도 카드 Option C ── */
.accuracy-standalone__stats {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.acc-stat-tile {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  border-radius: 8px;
  padding: 8px 10px;
}
.acc-stat-tile.acc-good { background: #F0FDF4; }
.acc-stat-tile.acc-mid  { background: #FEFCE8; }
.acc-stat-tile.acc-bad  { background: #FEF2F2; }

.acc-streak {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  background: var(--surface-secondary);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text-primary);
  margin-bottom: 10px;
}
.acc-streak__icon { font-size: 14px; }
.acc-streak__text strong { color: #16A34A; }

/* 점 모양: 원형 → 둥근 사각형 */
.acc-dot { border-radius: 3px; }
```

- [ ] **Step 1-2: 아카이브 카드 리스트 스타일 추가**

`.acc-streak__text strong { ... }` 아래에 추가:

```css
/* ── 아카이브 카드 리스트 ── */
.briefing-archive {
  display: flex;
  flex-direction: column;
  gap: 6px;
  grid-column: 1 / -1;
}
.archive-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--line-secondary);
  text-decoration: none;
  color: inherit;
  transition: background .15s, border-color .15s;
}
.archive-card:hover {
  background: var(--surface-hover);
  border-color: var(--line-primary);
}
.archive-card__date {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 72px;
  flex-shrink: 0;
}
.archive-card__badges {
  display: flex;
  gap: 5px;
  flex: 1;
  flex-wrap: wrap;
}
.archive-card__result {
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
  min-width: 16px;
  text-align: right;
}
.archive-card__result.hit  { color: #16A34A; }
.archive-card__result.miss { color: #E03131; }
.archive-card__arrow {
  font-size: 12px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}
```

- [ ] **Step 1-3: CTA 스타일 추가**

아카이브 스타일 아래에 추가:

```css
/* ── 사이드바 CTA ── */
.sidebar-cta {
  border-top: 1px solid var(--line-secondary);
  padding-top: 14px;
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sidebar-cta__tg {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--text-secondary);
  text-decoration: none;
}
.sidebar-cta__tg:hover { color: var(--text-primary); }
.sidebar-cta__email-form {
  display: flex;
  gap: 6px;
}
.sidebar-cta__input {
  flex: 1;
  font-size: 12px;
  padding: 6px 10px;
  border: 1px solid var(--line-secondary);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text-primary);
  outline: none;
}
.sidebar-cta__input:focus { border-color: var(--line-primary); }
.sidebar-cta__btn {
  font-size: 12px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--text-primary);
  color: var(--surface);
  border: none;
  cursor: pointer;
  white-space: nowrap;
}
```

- [ ] **Step 1-4: CSS 변수 확인**

아래 변수가 `:root` / `.dark`에 없으면 추가. `style.css` 상단 `:root` 블록을 확인 후, 없는 변수만 추가한다.

```css
/* 없는 경우에만 :root에 추가 */
--surface-secondary: #F9FAFB;
--surface-hover: #F3F4F6;
```

`.dark` 블록에는:
```css
--surface-secondary: #1C1D1F;
--surface-hover: #2A2B2D;
```

- [ ] **Step 1-5: 커밋**

```bash
git add web/assets/style.css
git commit -m "style: 정확도 카드 Option C + 아카이브 카드 리스트 + CTA 스타일 추가"
```

---

## Task 2: generate_html.py — 데이터 계산 확장

**Files:**
- Modify: `scripts/generate_html.py`

- [ ] **Step 2-1: `_load_accuracy_lookup` 헬퍼 추가**

`compute_accuracy_stats` 함수(line 251) 바로 위에 삽입:

```python
def _load_accuracy_lookup() -> dict:
    """briefings.json에서 {(date, btype): is_correct} 딕셔너리를 반환한다."""
    path = DATA_DIR / "briefings.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        (b["date"], b["type"]): b["is_correct"]
        for b in data.get("briefings", [])
        if b.get("is_correct") is not None
    }


def _compute_streak(dots: list) -> int:
    """recent_dots 끝에서부터 연속 correct=True 개수를 반환한다."""
    streak = 0
    for dot in reversed(dots):
        if dot.get("correct"):
            streak += 1
        else:
            break
    return streak
```

- [ ] **Step 2-2: `compute_accuracy_stats`에 streak 추가**

`compute_accuracy_stats` 함수의 return dict (line ~278)에 `streak` 필드 추가:

```python
    recent_dots = [{"correct": e["is_correct"], "date": e["date"]} for e in last7]
    return {
        "last7_correct":  correct7,
        "last7_total":    len(last7),
        "last7_pct":      pct(correct7, len(last7)),
        "last30_correct": correct30,
        "last30_total":   len(last30),
        "last30_pct":     pct(correct30, len(last30)),
        "recent_dots":    recent_dots,
        "streak":         _compute_streak(recent_dots),   # ← 추가
    }
```

- [ ] **Step 2-3: `build_sidebar_data` 교체**

`build_sidebar_data` 함수(line 289) 전체를 아래로 교체:

```python
def build_sidebar_data(briefing_type: str) -> list:
    """브리핑 유형에 따라 사이드바 지표 목록을 반환한다."""
    if briefing_type == "kospi":
        return [
            {"type": "market", "name": "코스피",           "val_id": "kospi-val",  "badge_id": "kospi-badge",  "canvas_id": "c-kospi"},
            {"type": "market", "name": "코스닥",           "val_id": "kosdaq-val", "badge_id": "kosdaq-badge", "canvas_id": "c-kosdaq"},
            {"type": "market", "name": "원/달러",          "val_id": "usd-val",    "badge_id": "usd-badge",    "canvas_id": "c-usd"},
            {"type": "fg"},
        ]
    else:  # us
        return [
            {"type": "market", "name": "나스닥",            "val_id": "nasdaq-val", "badge_id": "nasdaq-badge", "canvas_id": "c-nasdaq"},
            {"type": "market", "name": "나스닥100 선물",    "val_id": "nq-val",     "badge_id": "nq-badge",     "canvas_id": "c-nq"},
            {"type": "market", "name": "필라델피아 반도체", "val_id": "sox-val",    "badge_id": "sox-badge",    "canvas_id": "c-sox"},
            {"type": "fg"},
        ]
```

- [ ] **Step 2-4: `fearGreed` pop 제거**

`build_full_html` (line ~351)과 `build_index_html_multi` (line ~610)에 있는 아래 줄을 삭제:

```python
market_data_js.pop("fearGreed", None)   # ← 이 줄을 두 곳 모두 삭제
```

- [ ] **Step 2-5: archive_items에 accuracy result 필드 추가**

`build_index_html_multi` 함수에서 `archive_items = load_briefing_summaries(...)` 호출이 두 곳 있다 (line ~635, ~674). 각 호출 바로 아래에 추가:

```python
        archive_items = load_briefing_summaries(date_str, briefing_type, n=10)
        # ── 각 아카이브 항목에 예측 결과(✓/✗/-) 필드 추가 ──
        _acc_lookup = _load_accuracy_lookup()
        for _item in archive_items:
            _ic = _acc_lookup.get((_item["date"], _item["type"]))
            _item["result"]     = "✓" if _ic is True else ("✗" if _ic is False else "-")
            _item["result_cls"] = "hit" if _ic is True else ("miss" if _ic is False else "")
```

(두 곳 모두 동일하게 추가)

- [ ] **Step 2-6: 동작 확인**

```bash
cd "/Users/luke/Service App/DailyB"
python scripts/generate_html.py --type kospi --date 2026-05-16 --dry-run 2>&1 | head -20
```

`--dry-run` 옵션이 없으면 실제 파일에 영향을 주지 않도록 아래로 확인:

```bash
python -c "
from scripts.generate_html import compute_accuracy_stats, _compute_streak, build_sidebar_data
stats = compute_accuracy_stats('kospi')
print('streak:', stats.get('streak'))
print('kospi sidebar:', [i['name'] if i['type']=='market' else i['type'] for i in build_sidebar_data('kospi')])
print('us sidebar:',    [i['name'] if i['type']=='market' else i['type'] for i in build_sidebar_data('us')])
"
```

기대 출력:
```
streak: <정수>
kospi sidebar: ['코스피', '코스닥', '원/달러', 'fg']
us sidebar: ['나스닥', '나스닥100 선물', '필라델피아 반도체', 'fg']
```

- [ ] **Step 2-7: 커밋**

```bash
git add scripts/generate_html.py
git commit -m "feat(generate_html): streak 계산 + accuracy lookup + sidebar 유형별 슬림화 + fg data 복원"
```

---

## Task 3: main.js — FG 렌더링 + CTA 구독 핸들러

**Files:**
- Modify: `web/assets/main.js`

- [ ] **Step 3-1: FG 모달 함수 추가**

`main.js` 끝의 `document.addEventListener('keydown', ...)` 블록 (line ~455)을 아래로 교체:

```javascript
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeKelloggModal();
    closeAccModal();
    closeVixModal();
    closePredModal();
    closeSectorModal();
    closeFGModal();      // ← 추가
  }
});

function openFGModal() {
  const el = document.getElementById('fg-modal');
  if (el) el.classList.add('is-open');
}
function closeFGModal() {
  const el = document.getElementById('fg-modal');
  if (el) el.classList.remove('is-open');
}
```

- [ ] **Step 3-2: `drawFGGauge` 함수 추가**

`closeFGModal` 아래에 추가:

```javascript
function drawFGGauge(value) {
  const canvas = document.getElementById('fg-gauge-canvas');
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const W = 118, H = 64;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const cx = W / 2, cy = H - 6, r = 46;

  // 배경 호
  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI, 0, false);
  ctx.lineWidth = 10;
  ctx.strokeStyle = 'rgba(0,0,0,.08)';
  ctx.lineCap = 'round';
  ctx.stroke();

  // 값 호 (0→100 = π→0)
  const pct = Math.max(0, Math.min(100, value)) / 100;
  const fillEnd = Math.PI * (1 - pct);
  const color = value <= 24 ? '#1D4ED8'
              : value <= 44 ? '#2563EB'
              : value <= 54 ? '#CA8A04'
              : value <= 74 ? '#E03131'
              :               '#B91C1C';
  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI, fillEnd, false);
  ctx.lineWidth = 10;
  ctx.strokeStyle = color;
  ctx.lineCap = 'round';
  ctx.stroke();

  // 중앙 숫자
  ctx.font = "700 16px 'Pretendard',-apple-system,sans-serif";
  ctx.fillStyle = color;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(String(value), cx, cy - 16);
}
```

- [ ] **Step 3-3: `renderFG` 함수 추가**

`drawFGGauge` 아래에 추가:

```javascript
function renderFG() {
  const fg = (window.MARKET_DATA && window.MARKET_DATA.fearGreed) || {};
  if (fg.value === undefined) return;

  const fgMeta = (v) => {
    if (v <= 24) return { text: '극단적 공포', cls: 'extreme-fear' };
    if (v <= 44) return { text: '공포',        cls: 'fear' };
    if (v <= 54) return { text: '중립',        cls: 'neutral' };
    if (v <= 74) return { text: '탐욕',        cls: 'greed' };
    return               { text: '극단적 탐욕', cls: 'extreme-greed' };
  };
  const m = fgMeta(fg.value);

  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  const badgeEl = document.getElementById('fg-badge');
  const labelEl = document.getElementById('fg-label');

  if (badgeEl) { badgeEl.textContent = m.text; badgeEl.className = `fg-badge ${m.cls}`; }
  set('fg-value', fg.value);
  if (labelEl) { labelEl.textContent = m.text; labelEl.className = `fg-now-lbl ${m.cls}`; }
  if (fg.prev !== undefined) set('fg-hist-prev', fg.prev);
  if (fg['1w'] !== undefined) set('fg-hist-1w', fg['1w']);
  if (fg['1m'] !== undefined) set('fg-hist-1m', fg['1m']);
  if (fg['1y'] !== undefined) set('fg-hist-1y', fg['1y']);

  drawFGGauge(fg.value);
}
```

- [ ] **Step 3-4: `ctaSubscribe` 함수 추가**

`renderFG` 아래에 추가:

```javascript
function ctaSubscribe(e) {
  e.preventDefault();
  const input = e.target.querySelector('input[type="email"]');
  const btn   = e.target.querySelector('button');
  const email = input.value.trim();
  if (!email) return;
  btn.disabled = true;
  fetch('/api/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  }).then(r => {
    btn.textContent = r.ok ? '완료!' : '오류';
    if (r.ok) input.value = '';
  }).catch(() => { btn.textContent = '오류'; })
    .finally(() => { setTimeout(() => { btn.disabled = false; btn.textContent = '구독'; }, 3000); });
}
```

- [ ] **Step 3-5: `renderFG` boot 호출 추가**

`window.addEventListener('load', ...)` 블록 (line ~398)에 `renderFG()` 추가:

```javascript
window.addEventListener('load', () => {
  renderAll();
  renderVix();
  renderFG();   // ← 추가
  Object.entries(marketData).forEach(([key, d]) => attachSparkTooltip(d.canvasId, key));
  requestAnimationFrame(() => {
    Object.entries(stockMiniData).forEach(([id, d]) => drawStockMiniChart(id, d.prices, d.ma20, d.ma200));
  });
});
```

- [ ] **Step 3-6: 커밋**

```bash
git add web/assets/main.js
git commit -m "feat(main.js): FG 게이지 렌더링 + CTA 구독 핸들러 추가"
```

---

## Task 4: index.html 템플릿 — 정확도 카드 + 아카이브 교체

**Files:**
- Modify: `scripts/templates/index.html`

- [ ] **Step 4-1: 정확도 카드 마크업 교체**

`index.html`에서 `{% if accuracy %}` 블록 전체 (line ~333~358)를 아래로 교체:

```html
{% if accuracy %}
<div class="accuracy-standalone">
  <div class="accuracy-standalone__header">
    <span class="accuracy-standalone__title" style="display:flex;align-items:center;gap:4px;">
      예측 정확도
      <button class="info-icon-btn" onclick="openAccModal()" aria-label="예측 정확도 설명">?</button>
    </span>
    <span class="accuracy-standalone__sub">코스피 시초가</span>
  </div>
  <div class="accuracy-standalone__stats">
    <div class="acc-stat-tile {{ accuracy.last7_pct | acc_cls }}">
      <span class="acc-val {{ accuracy.last7_pct | acc_cls }}">{{ accuracy.last7_pct }}%</span>
      <span class="acc-lbl">최근 {{ accuracy.last7_total }}일</span>
    </div>
    <div class="acc-stat-tile {{ accuracy.last30_pct | acc_cls }}">
      <span class="acc-val {{ accuracy.last30_pct | acc_cls }}">{{ accuracy.last30_pct }}%</span>
      <span class="acc-lbl">최근 {{ accuracy.last30_total }}일</span>
    </div>
  </div>
  {% if accuracy.streak is defined and accuracy.streak >= 2 %}
  <div class="acc-streak">
    <span class="acc-streak__icon">🔥</span>
    <span class="acc-streak__text">최근 <strong>{{ accuracy.streak }}연속</strong> 적중</span>
  </div>
  {% endif %}
  <div class="accuracy-standalone__dots">
    {% for dot in accuracy.recent_dots %}
    <span class="acc-dot {{ 'correct' if dot.correct else 'wrong' }}" title="{{ dot.date }} {{ '맞음' if dot.correct else '틀림' }}"></span>
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 4-2: 아카이브 섹션 교체**

`{% if archive_items %}` 블록 전체 (line ~399~508)를 아래로 교체:

```html
{% if archive_items %}
<div class="briefing-archive">
  {% for item in archive_items %}
  <a class="archive-card" href="{{ item.url }}">
    <span class="archive-card__date">{{ item.date }}</span>
    <span class="archive-card__badges">
      <span class="acc-type-badge {{ item.type }}">{{ item.badge_text }}</span>
      {% if item.is_closing %}
      <span class="pred-badge">마감 시황</span>
      {% else %}
      <span class="pred-badge {{ item.dir_cls }}">{{ item.direction }}</span>
      {% endif %}
    </span>
    <span class="archive-card__result {{ item.result_cls }}">{{ item.result }}</span>
    <span class="archive-card__arrow">→</span>
  </a>
  {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 4-3: 사이드바 FG 블록 확인**

`index.html`의 `mkt-list` 루프 (line ~366) 안에 `{% elif item.type == 'fg' %}` 블록이 이미 있는지 확인. 있으면 그대로 유지.

- [ ] **Step 4-4: 사이드바 CTA 블록 추가**

`</aside>` 태그 바로 위(사이드바 닫기 전)에 추가:

```html
        <div class="sidebar-cta">
          <a class="sidebar-cta__tg" href="https://t.me/doubleshot30" target="_blank" rel="noopener">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            텔레그램 채널 구독
          </a>
          <form class="sidebar-cta__email-form" onsubmit="ctaSubscribe(event)">
            <input class="sidebar-cta__input" type="email" placeholder="이메일 주소" required />
            <button class="sidebar-cta__btn" type="submit">구독</button>
          </form>
        </div>
```

- [ ] **Step 4-5: FG 모달 HTML 확인**

`index.html` 하단에 `id="fg-modal"` 블록이 있는지 확인 (line ~580). 없으면 `acc-modal` 블록 위에 추가:

```html
  <!-- 공포탐욕지수 모달 -->
  <div class="info-modal-backdrop" id="fg-modal" onclick="if(event.target===this)closeFGModal()">
    <div class="info-modal" role="dialog" aria-modal="true" aria-labelledby="fg-modal-title">
      <button class="info-modal__close" onclick="closeFGModal()" aria-label="닫기">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <div class="info-modal__title" id="fg-modal-title">공포탐욕지수(Fear &amp; Greed Index)</div>
      <div class="info-modal__body">
        <p>시장의 7가지 요인을 분석하여 현재 투자자의 심리를 극단적인 공포(0)부터 극단적인 탐욕(100)까지 측정하는 심리지표입니다.</p>
        <br>
        <ul style="padding-left:16px; margin-top:0; display:flex; flex-direction:column; gap:8px;">
          <li><strong style="color:#1D4ED8">0~24</strong> : 극단적 공포(Extreme Fear)</li>
          <li><strong style="color:#2563EB">25~44</strong> : 공포(Fear)</li>
          <li><strong style="color:#CA8A04">45~54</strong> : 중립(Neutral)</li>
          <li><strong style="color:#E03131">55~74</strong> : 탐욕(Greed)</li>
          <li><strong style="color:#B91C1C">75~100</strong> : 극단적 탐욕(Extreme Greed)</li>
        </ul>
      </div>
    </div>
  </div>
```

- [ ] **Step 4-6: 렌더링 확인**

```bash
cd "/Users/luke/Service App/DailyB"
python -c "
import json, sys
sys.path.insert(0, 'scripts')
from generate_html import build_index_html_multi, load_analysis
import pathlib

date_str = '2026-05-16'
btype = 'us'
data_file = pathlib.Path('data/latest_us.json')
if not data_file.exists():
    print('data file not found, skipping')
    sys.exit(0)
with open(data_file) as f:
    data = json.load(f)
analysis = load_analysis(btype)
html = build_index_html_multi(data, analysis, date_str, btype)
assert 'acc-stat-tile' in html, 'Option C 정확도 카드 없음'
assert 'archive-card' in html, '아카이브 카드 없음'
assert 'sidebar-cta' in html, 'CTA 없음'
print('OK: index.html 렌더링 성공')
"
```

- [ ] **Step 4-7: 커밋**

```bash
git add scripts/templates/index.html
git commit -m "feat(index.html): 정확도 카드 Option C + 아카이브 카드 리스트 + CTA 적용"
```

---

## Task 5: briefing.html 템플릿 — 정확도 카드 + FG + CTA

**Files:**
- Modify: `scripts/templates/briefing.html`

- [ ] **Step 5-1: 정확도 카드 마크업 교체**

`briefing.html`의 `{% if accuracy %}` 블록 (line ~240~265)을 index.html에서 적용한 것과 동일한 Option C 마크업으로 교체:

```html
{% if accuracy %}
<div class="accuracy-standalone">
  <div class="accuracy-standalone__header">
    <span class="accuracy-standalone__title" style="display:flex;align-items:center;gap:4px;">
      예측 정확도
      <button class="info-icon-btn" onclick="openAccModal()" aria-label="예측 정확도 설명">?</button>
    </span>
    <span class="accuracy-standalone__sub">코스피 시초가</span>
  </div>
  <div class="accuracy-standalone__stats">
    <div class="acc-stat-tile {{ accuracy.last7_pct | acc_cls }}">
      <span class="acc-val {{ accuracy.last7_pct | acc_cls }}">{{ accuracy.last7_pct }}%</span>
      <span class="acc-lbl">최근 {{ accuracy.last7_total }}일</span>
    </div>
    <div class="acc-stat-tile {{ accuracy.last30_pct | acc_cls }}">
      <span class="acc-val {{ accuracy.last30_pct | acc_cls }}">{{ accuracy.last30_pct }}%</span>
      <span class="acc-lbl">최근 {{ accuracy.last30_total }}일</span>
    </div>
  </div>
  {% if accuracy.streak is defined and accuracy.streak >= 2 %}
  <div class="acc-streak">
    <span class="acc-streak__icon">🔥</span>
    <span class="acc-streak__text">최근 <strong>{{ accuracy.streak }}연속</strong> 적중</span>
  </div>
  {% endif %}
  <div class="accuracy-standalone__dots">
    {% for dot in accuracy.recent_dots %}
    <span class="acc-dot {{ 'correct' if dot.correct else 'wrong' }}" title="{{ dot.date }} {{ '맞음' if dot.correct else '틀림' }}"></span>
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 5-2: mkt-list에 FG 블록 추가**

`briefing.html`의 `mkt-list` 루프 (line ~272~294)에서 `{% elif item.type == 'vix' %}` 블록 아래에 FG 블록 추가:

```html
            {% elif item.type == 'fg' %}
            <div class="fg-block">
              <div class="fg-block-header">
                <span class="mkt-name" style="display:flex;align-items:center;gap:4px;">
                  공포탐욕지수
                  <button class="info-icon-btn" onclick="openFGModal()" aria-label="공포탐욕지수 설명">?</button>
                </span>
                <span class="fg-badge" id="fg-badge">-</span>
              </div>
              <div class="fg-body">
                <div class="fg-gauge-mini"><canvas id="fg-gauge-canvas" style="width:118px;height:64px;display:block;"></canvas></div>
                <div class="fg-info">
                  <div class="fg-now"><span class="fg-now-val" id="fg-value">-</span><span class="fg-now-lbl" id="fg-label">-</span></div>
                  <div class="fg-hist-grid">
                    <div class="fg-hist-item"><span class="lbl">전일</span><span class="val" id="fg-hist-prev">-</span></div>
                    <div class="fg-hist-item"><span class="lbl">1주</span><span class="val" id="fg-hist-1w">-</span></div>
                    <div class="fg-hist-item"><span class="lbl">1달</span><span class="val" id="fg-hist-1m">-</span></div>
                    <div class="fg-hist-item"><span class="lbl">1년</span><span class="val" id="fg-hist-1y">-</span></div>
                  </div>
                  <div id="fg-date" style="font-size:10px;color:var(--text-tertiary);margin-top:4px;"></div>
                </div>
              </div>
            </div>
```

- [ ] **Step 5-3: CTA 블록 추가**

`briefing.html`의 `</aside>` 직전에 추가 (index.html Step 4-4와 동일):

```html
        <div class="sidebar-cta">
          <a class="sidebar-cta__tg" href="https://t.me/doubleshot30" target="_blank" rel="noopener">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            텔레그램 채널 구독
          </a>
          <form class="sidebar-cta__email-form" onsubmit="ctaSubscribe(event)">
            <input class="sidebar-cta__input" type="email" placeholder="이메일 주소" required />
            <button class="sidebar-cta__btn" type="submit">구독</button>
          </form>
        </div>
```

- [ ] **Step 5-4: FG 모달 추가**

`briefing.html` 하단 모달 블록 목록(line ~300 이후)에 추가 (index.html Step 4-5와 동일한 FG 모달 HTML):

```html
  <!-- 공포탐욕지수 모달 -->
  <div class="info-modal-backdrop" id="fg-modal" onclick="if(event.target===this)closeFGModal()">
    <div class="info-modal" role="dialog" aria-modal="true" aria-labelledby="fg-modal-title">
      <button class="info-modal__close" onclick="closeFGModal()" aria-label="닫기">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <div class="info-modal__title" id="fg-modal-title">공포탐욕지수(Fear &amp; Greed Index)</div>
      <div class="info-modal__body">
        <p>시장의 7가지 요인을 분석하여 현재 투자자의 심리를 극단적인 공포(0)부터 극단적인 탐욕(100)까지 측정하는 심리지표입니다.</p>
        <br>
        <ul style="padding-left:16px; margin-top:0; display:flex; flex-direction:column; gap:8px;">
          <li><strong style="color:#1D4ED8">0~24</strong> : 극단적 공포(Extreme Fear)</li>
          <li><strong style="color:#2563EB">25~44</strong> : 공포(Fear)</li>
          <li><strong style="color:#CA8A04">45~54</strong> : 중립(Neutral)</li>
          <li><strong style="color:#E03131">55~74</strong> : 탐욕(Greed)</li>
          <li><strong style="color:#B91C1C">75~100</strong> : 극단적 탐욕(Extreme Greed)</li>
        </ul>
      </div>
    </div>
  </div>
```

- [ ] **Step 5-5: 렌더링 확인**

```bash
cd "/Users/luke/Service App/DailyB"
python -c "
import json, sys
sys.path.insert(0, 'scripts')
from generate_html import build_full_html, load_analysis
import pathlib

btype = 'kospi'
date_str = '2026-05-16'
data_file = pathlib.Path('data/latest_kospi.json')
if not data_file.exists():
    print('data file not found, skipping')
    sys.exit(0)
with open(data_file) as f:
    data = json.load(f)
analysis = load_analysis(btype)
html = build_full_html(data, analysis, date_str, btype)
assert 'acc-stat-tile' in html, 'Option C 정확도 카드 없음'
assert 'fg-gauge-canvas' in html, 'FG 게이지 없음'
assert 'sidebar-cta' in html, 'CTA 없음'
assert 'fearGreed' in html, 'fearGreed 데이터 없음'
print('OK: briefing.html 렌더링 성공')
"
```

- [ ] **Step 5-6: 커밋**

```bash
git add scripts/templates/briefing.html
git commit -m "feat(briefing.html): 정확도 카드 Option C + FG 블록/모달 + CTA 적용"
```

---

## Task 6: 전체 검증 및 실제 HTML 재생성

**Files:**
- Run: `scripts/generate_html.py`

- [ ] **Step 6-1: 최신 브리핑 index.html 재생성**

가장 최근 생성된 브리핑 유형에 맞춰 실행 (us 또는 kospi):

```bash
cd "/Users/luke/Service App/DailyB"
# us 브리핑이 최신인 경우:
python scripts/generate_html.py --type us --date 2026-05-16
# kospi 브리핑이 최신인 경우:
python scripts/generate_html.py --type kospi --date 2026-05-16
```

- [ ] **Step 6-2: 생성된 HTML 핵심 요소 확인**

```bash
grep -c "acc-stat-tile\|archive-card\|sidebar-cta\|fg-gauge-canvas" \
  web/briefings/2026-05-16/index.html
```

기대: 4개 이상 매칭 (각 요소 최소 1회 이상 존재)

- [ ] **Step 6-3: 최종 커밋**

```bash
git add web/briefings/2026-05-16/
git commit -m "chore: 2026-05-16 브리핑 UI 개편 적용 재생성"
```
