# 섹터 브리핑 → 미국 연계 종목 소식 교체 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 예측 브리핑의 섹터 로테이션 브리핑(sector_focus)을 삭제하고, 미국 연계 종목 소식(us_linked_story) 섹션으로 교체한다.

**Architecture:** call_claude.py 시스템 프롬프트에서 sector_focus 규칙을 us_linked_story 규칙으로 교체. generate_html.py에서 컨텍스트 매핑 변경. 새 Jinja2 템플릿과 CSS 추가. sector 관련 함수 4개와 상수 2개 삭제.

**Tech Stack:** Python (Anthropic API), Jinja2 템플릿, CSS

---

### Task 1: call_claude.py — 섹터 상수·함수 삭제 + us_linked_story 프롬프트 교체

**Files:**
- Modify: `scripts/call_claude.py:34-46` (SECTOR_POOL, SECTOR_BY_KEY 삭제)
- Modify: `scripts/call_claude.py:257-293` (KOSPI_SYSTEM_PROMPT sector_focus 규칙 → us_linked_story 규칙)
- Modify: `scripts/call_claude.py:299` (필수 필드 목록 변경)
- Modify: `scripts/call_claude.py:342-352` (JSON 예시 sector_focus → us_linked_story)
- Modify: `scripts/call_claude.py:211,217,220` (프롬프트 내 sector_focus 언급 정리)
- Modify: `scripts/call_claude.py:595-661` (US_SYSTEM_PROMPT sector_semicon 규칙+예시 삭제)
- Modify: `scripts/call_claude.py:809-870` (함수 4개 삭제: load_sector_history, save_sector_to_history, build_sector_avoidance_hint, pick_sector)
- Modify: `scripts/call_claude.py:1164-1170` (섹터 로테이션 가이드 주입부 삭제)
- Modify: `scripts/call_claude.py:1227-1236` (sector_focus 검증·보정 블록 삭제)

- [ ] **Step 1: SECTOR_POOL, SECTOR_BY_KEY 상수 삭제**

`scripts/call_claude.py:34-46`의 섹터 상수 블록을 삭제한다.

삭제 대상:
```python
# 섹터 로테이션 풀 (코스피 아침 브리핑 — sector_focus)
# ─────────────────────────────────────────────────────────────────────────────
SECTOR_POOL = [
    {"key": "semicon", "name": "반도체",     "emoji": "🏭"},
    {"key": "power",   "name": "AI전력기기", "emoji": "⚡"},
    {"key": "defense", "name": "방산",       "emoji": "🛡️"},
    {"key": "ship",    "name": "조선",       "emoji": "🚢"},
    {"key": "battery", "name": "2차전지",    "emoji": "🔋"},
    {"key": "auto",    "name": "자동차",     "emoji": "🚗"},
    {"key": "bio",     "name": "바이오",     "emoji": "💊"},
    {"key": "finance", "name": "금융",       "emoji": "🏦"},
]
SECTOR_BY_KEY = {s["key"]: s for s in SECTOR_POOL}
```

- [ ] **Step 2: KOSPI_SYSTEM_PROMPT — sector_focus 규칙을 us_linked_story 규칙으로 교체**

`scripts/call_claude.py:257-293`의 "오늘의 섹터 브리핑(sector_focus) 작성 규칙" 블록 전체를 아래로 교체:

```
### 미국 연계 종목 소식(us_linked_story) 작성 규칙
코스피 아침 브리핑 하단에 붙는, 오늘 한국 시장에 가장 임팩트가 큰 미국 이벤트 1건 심층 분석.

- **주제 선택**: 뉴스 요약·시장 데이터에서 한국 종목에 직접 영향을 주는 미국 이벤트를 1건 고른다.
  - 실적 발표 (마이크론→SK하이닉스, 애플→LG이노텍 등)
  - 정책·규제 (미국 반도체 수출규제→반도체주, FOMC→금융주 등)
  - 미국 종목 급등락 (테슬라→2차전지, 엔비디아→반도체 등)
  - 해당 이벤트가 한국 시장에 왜 중요한지가 핵심.
- **title**: 이벤트 핵심을 한 줄로. 30~50자. 마침표 종결 아닌 헤드라인 스타일.
  예시: "마이크론 실적 발표 — 내일 새벽, HBM 가이던스가 핵심"
- **paragraphs**: 3개 문단, 각 문단 해요체 1~2문장.
  - **각 문단 작성 원칙**: 판단·주장 문장을 먼저 쓴다. 데이터는 그 뒤에 붙이거나, 판단만 이어가도 된다.
  - 1문단: 이벤트 핵심 — 무엇이, 언제 일어나는지
  - 2문단: 한국 연관 종목에 미치는 영향 — 수치 근거(<b> 강조)
  - 3문단: 리스크 시나리오 또는 반대 방향 가능성
- **related_stocks**: 이 이벤트와 직접 연관된 종목 2~4개. 한국 종목과 미국 티커 모두 가능.
  - name: 종목명 (한국은 한글, 미국은 티커)
  - code: 종목 코드 (한국 6자리, 미국 티커)
- 수치는 <b> 태그로 강조한다.
- 뉴스 요약에 마땅한 미국 이벤트가 없으면 `us_linked_story`를 null로 출력한다. 억지로 만들지 않는다.
```

- [ ] **Step 3: KOSPI_SYSTEM_PROMPT — 필수 필드 목록 변경**

`scripts/call_claude.py:299` 변경:

Before:
```
**[필수] JSON에 반드시 포함해야 하는 필드: prediction, reason_title, reasons, stock_picks, sector_focus, comfort_line**
```

After:
```
**[필수] JSON에 반드시 포함해야 하는 필드: prediction, reason_title, reasons, stock_picks, us_linked_story, comfort_line**
```

- [ ] **Step 4: KOSPI_SYSTEM_PROMPT — JSON 예시의 sector_focus를 us_linked_story로 교체**

`scripts/call_claude.py:342-352`의 `"sector_focus": { ... }` 블록을 아래로 교체:

```json
  "us_linked_story": {
    "title": "마이크론 실적 발표 — 내일 새벽, HBM 가이던스가 핵심",
    "paragraphs": [
      "마이크론이 한국시간 내일 새벽 실적을 발표해요. 시장이 주목하는 건 HBM 매출 가이던스예요.",
      "월가 컨센서스는 매출 <b>$8.8B</b>(YoY +50%)이에요. HBM 매출이 <b>$2.5B+</b> 가이던스가 나오면 SK하이닉스에 직접 호재예요.",
      "반대로 DRAM 재고 증가 시그널이 나오면 반도체 섹터 전체가 눌릴 수 있어요."
    ],
    "related_stocks": [
      {"name": "SK하이닉스", "code": "000660"},
      {"name": "삼성전자", "code": "005930"},
      {"name": "MU", "code": "MU"}
    ]
  }
```

- [ ] **Step 5: KOSPI_SYSTEM_PROMPT — 프롬프트 내 sector_focus 텍스트 참조 정리**

line 211: `sector_focus` → `us_linked_story`
```
reasons, watch_items, us_linked_story 등 모든 출력에서, ...
```

line 217: `sector_focus` 제거 (이미 `scenario 등`으로 커버됨)
```
어떤 섹션(reasons, watch_items, us_linked_story, scenario 등)에서도 ...
```

line 220: `sector_focus` → `us_linked_story`
```
환율을 언급해야 하는 모든 섹션(reasons, us_linked_story, watch_items 등)에서 ...
```

- [ ] **Step 6: US_SYSTEM_PROMPT — sector_semicon 규칙·예시 삭제**

`scripts/call_claude.py:595-605`의 "반도체 섹터 브리핑(sector_semicon) 작성 규칙" 블록 전체 삭제.

`scripts/call_claude.py:654-661`의 JSON 예시에서 `"sector_semicon": { ... }` 블록 삭제.

- [ ] **Step 7: 섹터 관련 함수 4개 삭제**

`scripts/call_claude.py:809-870`의 아래 함수 4개를 삭제:
- `load_sector_history()` (line 809-815)
- `save_sector_to_history()` (line 818-827)
- `build_sector_avoidance_hint()` (line 830-844)
- `pick_sector()` (line 847-870)

- [ ] **Step 8: main 함수 — 섹터 로테이션 가이드 주입부 삭제**

`scripts/call_claude.py:1164-1170`의 블록 삭제:

```python
    # 섹터 로테이션 가이드: 최근 선정 섹터 회피 (kospi 아침만)
    if briefing_type == "kospi":
        sector_history = [h for h in load_sector_history("kospi") if h.get("date") != date_str]
        sector_hint = build_sector_avoidance_hint(sector_history, days=5)
        if sector_hint:
            user_content += sector_hint
            print(f"[call_claude] Sector rotation hint injected ({len(sector_history[:5])} recent)")
```

- [ ] **Step 9: main 함수 — sector_focus 검증·보정 블록 삭제**

`scripts/call_claude.py:1227-1236`의 블록 삭제:

```python
    # sector_focus 검증·보정 후 이력 저장 (kospi 아침만)
    if briefing_type == "kospi":
        recent_keys = [
            h.get("sector_key")
            for h in load_sector_history("kospi")
            if h.get("date") != date_str
        ][:5]
        analysis["sector_focus"] = pick_sector(analysis.get("sector_focus"), recent_keys)
        save_sector_to_history("kospi", date_str, analysis["sector_focus"]["sector_key"])
        print(f"[call_claude] Sector focus → {analysis['sector_focus']['sector_key']}")
```

- [ ] **Step 10: 커밋**

```bash
git add scripts/call_claude.py
git commit -m "refactor(call_claude): sector_focus 삭제, us_linked_story 프롬프트 교체"
```

---

### Task 2: 템플릿 + CSS 추가

**Files:**
- Delete: `scripts/templates/sections/sector_focus.html`
- Create: `scripts/templates/sections/us_linked_story.html`
- Modify: `scripts/templates/briefings/kospi.html:36`
- Modify: `web/assets/style.css:165-166`

- [ ] **Step 1: sector_focus.html 삭제**

```bash
rm scripts/templates/sections/sector_focus.html
```

- [ ] **Step 2: us_linked_story.html 생성**

`scripts/templates/sections/us_linked_story.html`:

```html
{# 미국 연계 종목 소식 — 코스피 브리핑 전용 #}
<div class="open-section">
  <div class="open-section__title us-linked-title">
    <span class="us-badge">🇺🇸 US</span> {{ us_linked_title }}
  </div>
  <div class="reason-block">
    <ul>
      {% for para in us_linked_paragraphs %}
      <li>{{ para | safe }}</li>
      {% endfor %}
    </ul>
  </div>
  {% if us_linked_stocks %}
  <div class="us-linked-chips">
    {% for s in us_linked_stocks %}
    <span class="us-linked-chip">{{ s.name }} {{ s.code }}</span>
    {% endfor %}
  </div>
  {% endif %}
</div>
```

- [ ] **Step 3: kospi.html 템플릿 변경**

`scripts/templates/briefings/kospi.html:36` 변경:

Before:
```html
            {% if sector_signal %}{% include "sections/sector_focus.html" %}<div class="divider"></div>{% endif %}
```

After:
```html
            {% if us_linked_title %}{% include "sections/us_linked_story.html" %}<div class="divider"></div>{% endif %}
```

- [ ] **Step 4: CSS 추가**

`web/assets/style.css`의 `.semicon-section-title` 블록(line 165-166) 뒤에 추가:

```css
.us-linked-title{font-size:14px!important;font-weight:700!important;color:var(--ink)!important;text-transform:none!important;letter-spacing:-0.2px;}
.us-linked-title::before{display:none!important;}
.us-badge{display:inline-flex;align-items:center;gap:4px;background:var(--primary-bg);color:var(--primary);font-size:11px;font-weight:700;padding:3px 8px;border-radius:4px;margin-right:6px;}
.us-linked-chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;}
.us-linked-chip{font-size:11px;color:var(--muted);background:var(--surface-soft);border:1px solid var(--hairline);padding:3px 8px;border-radius:12px;}
```

- [ ] **Step 5: 커밋**

```bash
git add scripts/templates/sections/ scripts/templates/briefings/kospi.html web/assets/style.css
git commit -m "feat(template): us_linked_story 템플릿·CSS 추가, sector_focus.html 삭제"
```

---

### Task 3: generate_html.py — 컨텍스트 매핑 변경

**Files:**
- Modify: `scripts/generate_html.py:718-724`

- [ ] **Step 1: sector_focus 컨텍스트 빌드를 us_linked_story로 교체**

`scripts/generate_html.py:718-724` 변경:

Before:
```python
        if internal_type == "kospi":
            sf = analysis.get("sector_focus") or analysis.get("sector_semicon") or {}
            if sf.get("signal"):
                ctx["sector_emoji"] = sf.get("emoji", "🏭")
                ctx["sector_name"] = sf.get("sector_name", "반도체")
                ctx["sector_signal"] = sf["signal"]
                ctx["sector_paragraphs"] = sf.get("paragraphs", [])
```

After:
```python
        if internal_type == "kospi":
            uls = analysis.get("us_linked_story") or {}
            if uls.get("title"):
                ctx["us_linked_title"] = uls["title"]
                ctx["us_linked_paragraphs"] = uls.get("paragraphs", [])
                ctx["us_linked_stocks"] = uls.get("related_stocks", [])
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/generate_html.py
git commit -m "feat(generate_html): sector_focus → us_linked_story 컨텍스트 매핑 교체"
```

---

### Task 4: SERVICE_RULES.md 업데이트

**Files:**
- Modify: `docs/SERVICE_RULES.md`

- [ ] **Step 1: SERVICE_RULES.md에서 sector_focus 관련 언급 업데이트**

`docs/SERVICE_RULES.md`에서 `sector_focus` / `sector_semicon` 관련 언급을 검색하고, `us_linked_story`로 업데이트하거나 해당 문단을 삭제한다.

확인 대상:
```bash
grep -n "sector_focus\|sector_semicon\|섹터 로테이션\|sector_stocks" docs/SERVICE_RULES.md
```

- [ ] **Step 2: 커밋**

```bash
git add docs/SERVICE_RULES.md
git commit -m "docs: SERVICE_RULES.md sector_focus → us_linked_story 반영"
```

---

### Task 5: 수동 검증 — 오늘자 브리핑 재생성 테스트

**Files:** (변경 없음, 검증만)

- [ ] **Step 1: call_claude.py 구문 검증**

```bash
python3 -c "import scripts.call_claude as cc; print('OK')"
```

Expected: `OK` (import 에러 없음)

- [ ] **Step 2: generate_html.py 구문 검증**

```bash
python3 -c "import scripts.generate_html as gh; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 기존 analysis_snapshot.json에 us_linked_story가 없어도 에러 없이 렌더링되는지 확인**

오늘자 스냅샷으로 재생성 테스트:
```bash
python3 scripts/generate_html.py --type kospi --date 2026-06-24 --data-file data/latest_kospi.json 2>&1 | tail -5
```

Expected: HTML 생성 성공 (us_linked_story가 null/없으면 섹션이 생략되어야 함)

- [ ] **Step 4: 생성된 HTML에 sector_focus 잔재가 없는지 확인**

```bash
grep -c "sector_focus\|sector_signal\|semicon-section-title" web/briefings/2026-06-24/kospi/index.html
```

Expected: `0`

- [ ] **Step 5: .semicon-section-title CSS 삭제 여부 결정**

`.semicon-section-title` CSS는 과거 브리핑 HTML에서 아직 참조할 수 있으므로 유지한다. 삭제하지 않는다.
