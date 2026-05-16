# Briefing UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 브리핑 페이지 우측 사이드바 개편(정확도 카드 Option C + 시장 지표 유형별 슬림화 + 조용한 CTA)과 아카이브 섹션을 아코디언에서 카드 리스트로 교체한다.

**Architecture:** `generate_html.py`에서 streak/accuracy lookup/sidebar_items 계산을 확장하고, `main.js`에 CTA 구독 핸들러를 추가한 뒤, 두 Jinja2 템플릿(`index.html`, `briefing.html`)과 `style.css`를 수정해 새 UI를 적용한다.

**Tech Stack:** Python(Jinja2, generate_html.py), Vanilla JS(main.js), CSS(style.css), HTML templates

---

## 변경 파일 맵

| 파일 | 역할 |
|------|------|
| `web/assets/style.css` | Option C 정확도 카드 스타일, 아카이브 카드 스타일, CTA 스타일 추가 |
| `scripts/generate_html.py` | streak 계산, accuracy lookup, sidebar_items 유형별 분기 |
| `web/assets/main.js` | ctaSubscribe 함수 추가 |
| `scripts/templates/index.html` | 정확도 카드 → Option C, 아카이브 → 카드 리스트, CTA |
| `scripts/templates/briefing.html` | 정확도 카드 → Option C, CTA |

---

## Task 1: CSS — 새 스타일 추가

**Files:**
- Modify: `web/assets/style.css`

- [ ] **Step 1-1: 정확도 카드 Option C 스타일 추가**

`style.css`의 `.acc-dot.wrong { background: #E03131; }` 아래 (line 1840)에 추가:

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

Step 1-1 추가 블록 아래에 이어서 추가:

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

- [ ] **Step 1-3: 시장 지표 행 간격 확대**

`style.css`의 `.mkt-row {` 블록 (line 1611)에서 `padding: 11px 0` → `padding: 15px 0` 으로 수정:

```css
.mkt-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px 0;   /* 11px → 15px */
}
```

같은 파일 안 반응형 블록 (line ~985)의 `.mkt-row { padding: 11px 0; }` 도 동일하게 `15px`로 수정.

`.mkt-name { margin-bottom: 5px; }` 도 `6px`로 변경:

```css
.mkt-name {
  ...
  margin-bottom: 6px;   /* 5px → 6px */
}
```

- [ ] **Step 1-4: CTA 스타일 추가**

Step 1-2 블록 아래에 이어서 추가:

```css
/* ── 사이드바 CTA ── */
.sidebar-cta {
  padding: 14px 16px;
  border-top: 1px solid var(--line-secondary);
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.sidebar-cta__tg {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  background: #F5F8FA;
  border: 1px solid #D1DCE5;
  border-radius: 10px;
  text-decoration: none;
  transition: background .15s;
}
.sidebar-cta__tg:hover { background: #EBF1F6; }
.sidebar-cta__tg-icon {
  width: 30px;
  height: 30px;
  background: #5BA4CF;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.sidebar-cta__tg-text { display: flex; flex-direction: column; gap: 2px; }
.sidebar-cta__tg-title { font-size: 13px; font-weight: 700; color: #2C5F7A; }
.sidebar-cta__tg-sub   { font-size: 10px; color: #5C8DA8; }
.sidebar-cta__divider {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: var(--text-tertiary);
}
.sidebar-cta__divider::before,
.sidebar-cta__divider::after { content: ''; flex: 1; height: 1px; background: var(--line-secondary); }
.sidebar-cta__email-form { display: flex; gap: 6px; }
.sidebar-cta__input {
  flex: 1;
  font-size: 12px;
  padding: 7px 10px;
  border: 1px solid var(--line-secondary);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text-primary);
  outline: none;
}
.sidebar-cta__input:focus { border-color: var(--line-primary); }
.sidebar-cta__btn {
  font-size: 12px;
  padding: 7px 12px;
  border-radius: 8px;
  background: var(--text-primary);
  color: var(--surface);
  border: none;
  cursor: pointer;
  white-space: nowrap;
}
```

- [ ] **Step 1-5: CSS 변수 확인 및 추가**

`style.css` 상단 `:root` 블록을 확인. `--surface-secondary`, `--surface-hover`가 없으면 추가:

```css
/* :root에 추가 */
--surface-secondary: #F9FAFB;
--surface-hover: #F3F4F6;
```

`.dark` 블록에도 없으면 추가:

```css
--surface-secondary: #1C1D1F;
--surface-hover: #2A2B2D;
```

- [ ] **Step 1-6: 커밋**

```bash
git add web/assets/style.css
git commit -m "style: 정확도 카드 Option C + 아카이브 카드 + CTA 스타일 추가"
```

---

## Task 2: generate_html.py — 데이터 계산 확장

**Files:**
- Modify: `scripts/generate_html.py`

- [ ] **Step 2-1: `_load_accuracy_lookup` + `_compute_streak` 헬퍼 추가**

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

- [ ] **Step 2-2: `compute_accuracy_stats` 반환값에 streak 추가**

`compute_accuracy_stats` 함수의 return dict (line ~278)를 아래로 교체:

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
        "streak":         _compute_streak(recent_dots),
    }
```

- [ ] **Step 2-3: `build_sidebar_data` 교체**

`build_sidebar_data` 함수(line 289) 전체를 아래로 교체:

```python
def build_sidebar_data(briefing_type: str) -> list:
    """브리핑 발송 시각 기준으로 유용한 지표만 반환한다.
    - kospi (08:30): 전날 미국 마감 + NQ선물 + USD/KRW → 코스피 시초가 예측에 직접 활용
    - us (21:20): NQ선물(프리마켓) + 전일 미국 지수 + VIX
    """
    if briefing_type == "kospi":
        return [
            {"type": "market", "name": "나스닥",            "val_id": "nasdaq-val", "badge_id": "nasdaq-badge", "canvas_id": "c-nasdaq"},
            {"type": "market", "name": "필라델피아 반도체", "val_id": "sox-val",    "badge_id": "sox-badge",    "canvas_id": "c-sox"},
            {"type": "market", "name": "나스닥100 선물",    "val_id": "nq-val",     "badge_id": "nq-badge",     "canvas_id": "c-nq"},
            {"type": "market", "name": "원/달러",           "val_id": "usd-val",    "badge_id": "usd-badge",    "canvas_id": "c-usd"},
        ]
    else:  # us
        return [
            {"type": "market", "name": "나스닥100 선물",    "val_id": "nq-val",     "badge_id": "nq-badge",     "canvas_id": "c-nq"},
            {"type": "market", "name": "나스닥",            "val_id": "nasdaq-val", "badge_id": "nasdaq-badge", "canvas_id": "c-nasdaq"},
            {"type": "market", "name": "필라델피아 반도체", "val_id": "sox-val",    "badge_id": "sox-badge",    "canvas_id": "c-sox"},
            {"type": "vix"},
        ]
```

- [ ] **Step 2-4: archive_items에 accuracy result 필드 추가**

`build_index_html_multi` 함수 안에서 `archive_items = load_briefing_summaries(...)` 호출이 두 곳 있다 (kospi-close 분기 ~line 635, us/kospi 분기 ~line 674). 각 호출 바로 아래에 동일하게 추가:

```python
        archive_items = load_briefing_summaries(date_str, briefing_type, n=10)
        _acc_lookup = _load_accuracy_lookup()
        for _item in archive_items:
            _ic = _acc_lookup.get((_item["date"], _item["type"]))
            _item["result"]     = "✓" if _ic is True else ("✗" if _ic is False else "-")
            _item["result_cls"] = "hit" if _ic is True else ("miss" if _ic is False else "")
```

- [ ] **Step 2-5: 동작 확인**

```bash
cd "/Users/luke/Service App/DailyB"
python -c "
import sys; sys.path.insert(0, 'scripts')
from generate_html import compute_accuracy_stats, build_sidebar_data
stats = compute_accuracy_stats('kospi')
print('streak:', stats.get('streak'))
print('kospi sidebar:', [i.get('name', i['type']) for i in build_sidebar_data('kospi')])
print('us sidebar:',    [i.get('name', i['type']) for i in build_sidebar_data('us')])
"
```

기대 출력:
```
streak: <정수>
kospi sidebar: ['나스닥', '필라델피아 반도체', '나스닥100 선물', '원/달러']
us sidebar: ['나스닥100 선물', '나스닥', '필라델피아 반도체', 'vix']
```

- [ ] **Step 2-6: 커밋**

```bash
git add scripts/generate_html.py
git commit -m "feat(generate_html): streak 계산 + accuracy lookup + sidebar 유형별 슬림화"
```

---

## Task 3: main.js — CTA 구독 핸들러 추가

**Files:**
- Modify: `web/assets/main.js`

- [ ] **Step 3-1: `ctaSubscribe` 함수 추가**

`main.js` 끝의 `document.addEventListener('keydown', ...)` 블록 아래에 추가:

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
    .finally(() => {
      setTimeout(() => { btn.disabled = false; btn.textContent = '구독'; }, 3000);
    });
}
```

- [ ] **Step 3-2: 커밋**

```bash
git add web/assets/main.js
git commit -m "feat(main.js): CTA 이메일 구독 핸들러 추가"
```

---

## Task 4: index.html 템플릿 — 정확도 카드 + 아카이브 교체 + CTA

**Files:**
- Modify: `scripts/templates/index.html`

- [ ] **Step 4-1: 정확도 카드 마크업 교체**

`{% if accuracy %}` 블록 전체 (~line 333~358)를 아래로 교체:

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

`{% if archive_items %}` 블록 전체 (~line 399~508)를 아래로 교체:

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

- [ ] **Step 4-3: CTA 블록 추가**

`</aside>` 직전에 추가:

```html
        <div class="sidebar-cta">
          <a class="sidebar-cta__tg" href="https://t.me/doubleshot30" target="_blank" rel="noopener">
            <div class="sidebar-cta__tg-icon">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            </div>
            <div class="sidebar-cta__tg-text">
              <span class="sidebar-cta__tg-title">텔레그램 채널 구독</span>
              <span class="sidebar-cta__tg-sub">매일 아침·저녁 브리핑 수신</span>
            </div>
          </a>
          <div class="sidebar-cta__divider">또는 이메일로</div>
          <form class="sidebar-cta__email-form" onsubmit="ctaSubscribe(event)">
            <input class="sidebar-cta__input" type="email" placeholder="이메일 주소" required />
            <button class="sidebar-cta__btn" type="submit">구독</button>
          </form>
        </div>
```

- [ ] **Step 4-4: 렌더링 확인**

```bash
cd "/Users/luke/Service App/DailyB"
python -c "
import json, sys, pathlib
sys.path.insert(0, 'scripts')
from generate_html import build_index_html_multi, load_analysis

btype = 'us'
date_str = '2026-05-16'
data_file = pathlib.Path('data/latest_us.json')
if not data_file.exists():
    btype = 'kospi'; data_file = pathlib.Path('data/latest_kospi.json')
if not data_file.exists():
    print('data file not found, skip'); exit()
with open(data_file) as f: data = json.load(f)
analysis = load_analysis(btype)
html = build_index_html_multi(data, analysis, date_str, btype)
assert 'acc-stat-tile' in html, 'Option C 카드 없음'
assert 'archive-card'  in html, '아카이브 카드 없음'
assert 'sidebar-cta'   in html, 'CTA 없음'
print('OK')
"
```

- [ ] **Step 4-5: 커밋**

```bash
git add scripts/templates/index.html
git commit -m "feat(index.html): 정확도 카드 Option C + 아카이브 카드 리스트 + CTA"
```

---

## Task 5: briefing.html 템플릿 — 정확도 카드 + CTA

**Files:**
- Modify: `scripts/templates/briefing.html`

- [ ] **Step 5-1: 정확도 카드 마크업 교체**

`briefing.html`의 `{% if accuracy %}` 블록 (~line 240~265)을 Task 4 Step 4-1과 동일한 마크업으로 교체.

- [ ] **Step 5-2: CTA 블록 추가**

`briefing.html`의 `</aside>` 직전에 Task 4 Step 4-3과 동일한 CTA HTML 추가.

- [ ] **Step 5-3: 렌더링 확인**

```bash
cd "/Users/luke/Service App/DailyB"
python -c "
import json, sys, pathlib
sys.path.insert(0, 'scripts')
from generate_html import build_full_html, load_analysis

btype = 'kospi'
date_str = '2026-05-16'
data_file = pathlib.Path('data/latest_kospi.json')
if not data_file.exists():
    btype = 'us'; data_file = pathlib.Path('data/latest_us.json')
if not data_file.exists():
    print('data file not found, skip'); exit()
with open(data_file) as f: data = json.load(f)
analysis = load_analysis(btype)
html = build_full_html(data, analysis, date_str, btype)
assert 'acc-stat-tile' in html, 'Option C 카드 없음'
assert 'sidebar-cta'   in html, 'CTA 없음'
print('OK')
"
```

- [ ] **Step 5-4: 커밋**

```bash
git add scripts/templates/briefing.html
git commit -m "feat(briefing.html): 정확도 카드 Option C + CTA"
```

---

## Task 6: 최신 브리핑 재생성 및 최종 확인

**Files:**
- Run: `scripts/generate_html.py`

- [ ] **Step 6-1: 최신 브리핑 index.html 재생성**

```bash
cd "/Users/luke/Service App/DailyB"
# 가장 최신 브리핑 유형에 맞춰 실행
python scripts/generate_html.py --type us --date 2026-05-16
```

- [ ] **Step 6-2: 생성 결과 확인**

```bash
grep -c "acc-stat-tile\|archive-card\|sidebar-cta" \
  web/briefings/2026-05-16/index.html
```

기대: 3 이상 (각 요소 최소 1회)

- [ ] **Step 6-3: 최종 커밋**

```bash
git add web/briefings/2026-05-16/
git commit -m "chore: 2026-05-16 브리핑 UI 개편 재생성"
```
