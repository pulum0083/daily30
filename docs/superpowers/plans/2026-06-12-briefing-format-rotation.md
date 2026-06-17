# Briefing Format Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피·미국·마감 3종 브리핑에 불릿(bullet) / WHY-WHAT-SO / 시나리오분기(scenario) 3가지 근거 섹션 형식을 랜덤으로 적용한다.

**Architecture:** Python이 매 실행 시 3가지 형식 중 하나를 `random.choice`로 선택해 Claude에게 지시한다. Claude는 해당 형식에 맞는 JSON 필드를 반환하고, `generate_html.py`가 `analysis_format` 값을 읽어 Jinja 템플릿 분기로 올바른 섹션을 렌더링한다.

**Tech Stack:** Python 3.12, Jinja2, CSS (`.sc-card` 이미 main 배포 완료)

---

## 파일 변경 목록

| 상태 | 경로 | 역할 |
|------|------|------|
| 수정 | `scripts/call_claude.py` | 형식 랜덤 선택 + 3개 시스템 프롬프트에 형식별 JSON 명세 추가 |
| 수정 | `scripts/generate_html.py` | `build_reasons()` 확장, `build_scenario_context()` 추가, close 섹션에 형식 분기 추가 |
| 신규 | `scripts/templates/sections/scenario_split.html` | 시나리오분기 형식 (모든 브리핑 타입 공용) |
| 신규 | `scripts/templates/sections/why_what_so.html` | WHY/WHAT/SO 형식 (코스피·미국용, 마감은 기존 close_reason.html 재사용) |
| 수정 | `scripts/templates/briefings/kospi.html` | reasons include → 형식 분기 조건문 |
| 수정 | `scripts/templates/briefings/us.html` | reasons include → 형식 분기 조건문 |
| 수정 | `scripts/templates/briefings/close.html` | close_reason include → 형식 분기 조건문 |

---

## Task 1: scenario_split.html 템플릿 생성

**Files:**
- Create: `scripts/templates/sections/scenario_split.html`

- [ ] **Step 1: 파일 생성**

```html
{# 시나리오 분기 형식 — 상승/하락 대비 2컬럼 (모든 브리핑 타입 공용) #}
<div class="sc-card">
  <div class="sc-head">{{ reason_title }}</div>
  <div class="sc-summary">{{ sc_summary | safe }}</div>
  <div class="sc-cols">
    <div class="sc-col">
      <div class="sc-tag up">{{ sc_left_label }}</div>
      {% for item in sc_left_items %}
      <div class="sc-row"><div class="sc-dot up"></div><span>{{ item | safe }}</span></div>
      {% endfor %}
    </div>
    <div class="sc-col">
      <div class="sc-tag dn">{{ sc_right_label }}</div>
      {% for item in sc_right_items %}
      <div class="sc-row"><div class="sc-dot dn"></div><span>{{ item | safe }}</span></div>
      {% endfor %}
    </div>
  </div>
  <div class="sc-footer">{{ sc_footer | safe }}</div>
</div>
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/sections/scenario_split.html
git commit -m "feat: scenario_split.html 템플릿 추가"
```

---

## Task 2: why_what_so.html 템플릿 생성 (코스피·미국용)

마감 브리핑은 기존 `close_reason.html`을 그대로 사용한다. 코스피·미국 브리핑에서 WHY/WHAT/SO 형식을 쓸 때 사용하는 별도 템플릿.

**Files:**
- Create: `scripts/templates/sections/why_what_so.html`

- [ ] **Step 1: 파일 생성**

```html
{# WHY / WHAT / SO WHAT 형식 — 코스피·미국 브리핑용 #}
<div class="open-section">
  <div class="open-section__title reason-section-title">{{ reason_title }}</div>
  <div class="section-card" style="margin-top:10px;">
    {% if reason_lead %}
    <div class="reason-body" style="padding:12px 16px 0;">
      <p style="font-size:14px;color:var(--muted);line-height:1.75;margin-bottom:0;">{{ reason_lead | safe }}</p>
    </div>
    {% endif %}
    <div class="section-card__body">
      <div class="b-format">
        {% for row in b_rows %}
        <div class="b-row{% if row.so_what %} so-what{% endif %}">
          <span class="b-label">{{ row.label }}</span>
          <p class="b-text">{{ row.text | safe }}</p>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>
</div>
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/sections/why_what_so.html
git commit -m "feat: why_what_so.html 템플릿 추가 (코스피·미국용)"
```

---

## Task 3: 브리핑 템플릿 3종에 형식 분기 조건문 추가

**Files:**
- Modify: `scripts/templates/briefings/kospi.html`
- Modify: `scripts/templates/briefings/us.html`
- Modify: `scripts/templates/briefings/close.html`

- [ ] **Step 1: kospi.html 수정**

`{% include "sections/reasons.html" %}` 한 줄을 아래로 교체:

```jinja2
{% if analysis_format == 'scenario' %}
  {% include "sections/scenario_split.html" %}
{% elif analysis_format == 'why_what_so' %}
  {% include "sections/why_what_so.html" %}
{% else %}
  {% include "sections/reasons.html" %}
{% endif %}
```

- [ ] **Step 2: us.html 수정**

동일하게 `{% include "sections/reasons.html" %}` 교체 (kospi.html과 동일 블록).

- [ ] **Step 3: close.html 수정**

`{% if reason_title %}{% include "sections/close_reason.html" %}{% endif %}` 를 아래로 교체:

```jinja2
{% if reason_title %}
  {% if analysis_format == 'scenario' %}
    {% include "sections/scenario_split.html" %}
  {% elif analysis_format == 'bullet' %}
    {% include "sections/reasons.html" %}
  {% else %}
    {% include "sections/close_reason.html" %}
  {% endif %}
{% endif %}
```

- [ ] **Step 4: 커밋**

```bash
git add scripts/templates/briefings/kospi.html scripts/templates/briefings/us.html scripts/templates/briefings/close.html
git commit -m "feat: 브리핑 템플릿 3종 형식 분기 조건문 추가"
```

---

## Task 4: generate_html.py — 형식 컨텍스트 빌더 추가

**Files:**
- Modify: `scripts/generate_html.py`

- [ ] **Step 1: `build_scenario_context()` 함수 추가**

`build_reasons()` 함수 바로 뒤에 추가 (약 153번줄 이후):

```python
def build_scenario_context(analysis: dict) -> dict:
    """시나리오 분기 형식용 컨텍스트. analysis_format == 'scenario' 일 때 사용."""
    return {
        "sc_summary": analysis.get("sc_summary", ""),
        "sc_left_label": analysis.get("sc_left_label", "하락 근거"),
        "sc_right_label": analysis.get("sc_right_label", "반등 가능성"),
        "sc_left_items": analysis.get("sc_left_items", [])[:3],
        "sc_right_items": analysis.get("sc_right_items", [])[:3],
        "sc_footer": analysis.get("sc_footer", ""),
    }
```

- [ ] **Step 2: `build_why_what_so_context()` 함수 추가**

`build_scenario_context()` 바로 뒤에 추가:

```python
def build_why_what_so_context(analysis: dict) -> dict:
    """WHY/WHAT/SO WHAT 형식용 컨텍스트. analysis_format == 'why_what_so' 일 때 사용."""
    b_rows = []
    for label, key, sw in [("WHY", "why", False), ("WHAT", "what", False), ("SO?", "so_what", True)]:
        if analysis.get(key):
            b_rows.append({"label": label, "text": analysis[key], "so_what": sw})
    return {
        "reason_lead": analysis.get("reason_lead", ""),
        "b_rows": b_rows,
    }
```

- [ ] **Step 3: `build_reasons()` 확장 — `analysis_format` 포함**

기존 `build_reasons()` 함수를 아래로 교체:

```python
def build_reasons(analysis: dict) -> dict:
    direction = analysis.get("prediction", {}).get("direction", "")
    fallback = {
        "상승 우위": "왜 오를까? — 오늘의 상승 시그널",
        "하락 우위": "왜 내릴까? — 오늘의 하락 시그널",
    }.get(direction, "오를까 내릴까? — 오늘의 핵심 변수")
    fmt = analysis.get("analysis_format", "bullet")
    ctx = {
        "analysis_format": fmt,
        "reason_title": analysis.get("reason_title") or fallback,
        "reasons": analysis.get("reasons", [])[:4],
    }
    if fmt == "scenario":
        ctx.update(build_scenario_context(analysis))
    elif fmt == "why_what_so":
        ctx.update(build_why_what_so_context(analysis))
    return ctx
```

- [ ] **Step 4: close 섹션에 형식 분기 추가**

`render_briefing()` 내 close 분기에서 현재 `b_rows` 빌딩 블록을 아래로 교체 (약 317번줄):

```python
    # close_reason 섹션
    if analysis.get("market_title") or analysis.get("reason_title"):
        fmt = analysis.get("analysis_format", "why_what_so")
        ctx["analysis_format"] = fmt
        ctx["reason_title"] = analysis.get("market_title") or analysis.get("reason_title", "")
        if fmt == "scenario":
            ctx.update(build_scenario_context(analysis))
        elif fmt == "bullet":
            ctx["reasons"] = analysis.get("reasons", [])[:4]
        else:  # why_what_so (default for close)
            ctx["reason_lead"] = analysis.get("market_summary", "")
            b_rows = []
            for label, key, sw in [("WHY", "why", False), ("WHAT", "what", False), ("SO?", "so_what", True)]:
                if analysis.get(key):
                    b_rows.append({"label": label, "text": analysis[key], "so_what": sw})
            ctx["b_rows"] = b_rows
```

기존 코드:
```python
    if analysis.get("market_title"):
        b_rows = []
        for label, key, sw in [("WHY", "why", False), ("WHAT", "what", False), ("SO?", "so_what", True)]:
            if analysis.get(key):
                b_rows.append({"label": label, "text": analysis[key], "so_what": sw})
        ctx.update({
            "reason_title": analysis["market_title"],
            "reason_lead": analysis.get("market_summary", ""),
            "b_rows": b_rows,
        })
```

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_html.py
git commit -m "feat: generate_html.py 형식 컨텍스트 빌더 추가 및 분기 처리"
```

---

## Task 5: call_claude.py — 형식 랜덤 선택 + 시스템 프롬프트 업데이트

**Files:**
- Modify: `scripts/call_claude.py`

- [ ] **Step 1: 랜덤 형식 선택 주입 코드 추가**

`call_claude()` 함수의 `user_content` 빌딩이 끝나는 지점 (avoidance hint 주입 직후, `print(f"[call_claude] Calling Claude API")` 직전)에 추가:

```python
    # 브리핑 형식 랜덤 선택 (Python이 제어, Claude는 지시받은 형식만 사용)
    _formats = ["bullet", "scenario", "why_what_so"]
    chosen_format = random.choice(_formats)
    user_content += f"\n\n## 오늘 브리핑 근거 섹션 형식\n반드시 `{chosen_format}` 형식으로 출력하고, JSON에 `\"analysis_format\": \"{chosen_format}\"`을 포함한다.\n"
    print(f"[call_claude] Selected format: {chosen_format}")
```

파일 상단 import 목록에 `import random`이 없으면 추가.

- [ ] **Step 2: KOSPI_SYSTEM_PROMPT 출력 형식 섹션에 3가지 형식 명세 추가**

기존 `## 출력 형식` 섹션 끝부분(JSON 예시 직전)에 아래 내용 추가:

```
**[형식 지시] 매 실행 시 유저 메시지 하단에 오늘 사용할 형식이 지정된다. 지정된 형식에 따라 아래 중 하나의 필드 세트만 출력한다.**

### 형식 A: bullet
`reason_title`(훅 타이틀) + `reasons`(4개 불릿 배열) 출력.
기존 방식 그대로.

### 형식 B: scenario
`reason_title` + 아래 6개 필드 출력:
- `sc_summary`: 오늘 시장 한 줄 요약 (예측 방향 + 핵심 팩터)
- `sc_left_label`: 왼쪽 컬럼 레이블 (상승우위="상승 근거", 하락우위="하락 근거")
- `sc_right_label`: 오른쪽 컬럼 레이블 (상승우위="리스크", 하락우위="반등 가능성")
- `sc_left_items`: 왼쪽 항목 정확히 3개 (각 60자 이내, <b> 수치 강조 포함)
- `sc_right_items`: 오른쪽 항목 정확히 3개 (각 60자 이내)
- `sc_footer`: 다음 세션 핵심 변수 1문장 (해요체)
`reasons` 필드는 출력하지 않는다.

### 형식 C: why_what_so
`reason_title` + 아래 4개 필드 출력:
- `reason_lead`: 오늘 시장 전반 2문장 요약 (지수 등락폭·방향과 핵심 이유)
- `why`: 시장을 움직인 근본 원인 1~2문장
- `what`: 강한/약한 섹터·종목 구체 수치 1~2문장
- `so_what`: 다음 세션 시사점 정확히 1문장 (해요체)
`reasons` 필드는 출력하지 않는다.
```

- [ ] **Step 3: US_SYSTEM_PROMPT에 동일한 형식 명세 추가**

KOSPI와 동일하게 `## 출력 형식` 섹션 끝에 같은 내용 추가. 단 레이블은 미국 문맥에 맞게:
- `sc_left_label` 예시: "강세 근거"/"약세 근거"
- `sc_right_label` 예시: "리스크"/"반등 가능성"

- [ ] **Step 4: KOSPI_CLOSE_SYSTEM_PROMPT에 형식 명세 추가**

마감 브리핑용 `## 출력 형식` 섹션에 아래 추가:

```
**[형식 지시] 유저 메시지 하단에 오늘 사용할 형식이 지정된다.**

### 형식 A: bullet
기존 방식 대신 `reason_title` + `reasons` 4개 불릿 배열 출력.
`market_title`, `why`, `what`, `so_what`은 출력하지 않는다.

### 형식 B: scenario  
`reason_title` + `sc_summary`, `sc_left_label`("버틴 요인"), `sc_right_label`("내린 요인"), `sc_left_items`(3개), `sc_right_items`(3개), `sc_footer` 출력.
`market_title`, `why`, `what`, `so_what`은 출력하지 않는다.

### 형식 C: why_what_so (기본값)
기존 방식 그대로 `market_title`, `market_summary`, `why`, `what`, `so_what` 출력.
```

마감의 `call_claude_closing()` 함수에도 동일하게 형식 랜덤 선택 주입 코드 추가:
```python
    _formats = ["bullet", "scenario", "why_what_so"]
    chosen_format = random.choice(_formats)
    user_content += f"\n\n## 오늘 브리핑 근거 섹션 형식\n반드시 `{chosen_format}` 형식으로 출력하고, JSON에 `\"analysis_format\": \"{chosen_format}\"`을 포함한다.\n"
    print(f"[call_claude] Selected format: {chosen_format}")
```

- [ ] **Step 5: 커밋**

```bash
git add scripts/call_claude.py
git commit -m "feat: call_claude.py 형식 랜덤 선택 주입 + 시스템 프롬프트 3종 형식 명세 추가"
```

---

## Task 6: 로컬 검증

**Files:** 없음 (기존 스냅샷으로 렌더링 테스트)

- [ ] **Step 1: bullet 형식 렌더링 테스트**

`data/analysis_kospi.json`에 `"analysis_format": "bullet"` 필드 추가 후:
```bash
python3 scripts/generate_html.py --type kospi --date 2026-06-11 --data-file data/latest_kospi.json
```
`web/briefings/2026-06-11/kospi/index.html`에서 `<ul>` 불릿 섹션 확인.

- [ ] **Step 2: scenario 형식 렌더링 테스트**

`data/analysis_kospi.json`에 아래 필드 세팅:
```json
{
  "analysis_format": "scenario",
  "reason_title": "테스트 시나리오",
  "sc_summary": "테스트 요약이에요.",
  "sc_left_label": "하락 근거",
  "sc_right_label": "반등 가능성",
  "sc_left_items": ["항목1", "항목2", "항목3"],
  "sc_right_items": ["항목A", "항목B", "항목C"],
  "sc_footer": "다음 변수: 테스트예요."
}
```
재렌더 후 `sc-card` 섹션 확인.

- [ ] **Step 3: why_what_so 형식 렌더링 테스트**

`data/analysis_kospi.json`에:
```json
{
  "analysis_format": "why_what_so",
  "reason_title": "테스트 WHY/WHAT/SO",
  "reason_lead": "오늘 테스트 요약이에요.",
  "why": "WHY 내용이에요.",
  "what": "WHAT 내용이에요.",
  "so_what": "SO WHAT 내용이에요."
}
```
재렌더 후 `b-format` 섹션 확인.

- [ ] **Step 4: 최종 커밋 후 main 푸시**

```bash
git push origin feature/stock-page-engine
# CSS는 이미 main에 올라있으므로 나머지 변경도 main에 머지 또는 cherry-pick
git checkout main && git pull
git cherry-pick <Task1~5 커밋 해시들>
git push origin main
```
