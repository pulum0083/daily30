# 미국 브리핑 코스피 구조 정렬 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미국 시장 예측 브리핑을 코스피 예측 브리핑과 동일한 주요 구성(오늘의 관점·예측 스트립·이렇게 보는 이유·월가 코멘트[외국계 시각 스타일]·우리 성적표·텔레그램/월배당 사이드바)으로 맞춘다.

**Architecture:** Jinja 템플릿(`scripts/templates/`) + config-driven `generate_html.py` 조립기 + `call_claude.py`(Claude Sonnet 5) AI 프롬프트로 구성된 정적 브리핑 파이프라인. 이번 변경은 (1) US AI 프롬프트에 `todays_view` 생성 규칙 추가, (2) `generate_html.py`에서 `todays_view`·`scorecard` 게이트를 US로 확장, (3) US 템플릿 재구성 + 월가 코멘트 섹션 재스타일 + 사이드바 공용화로 이뤄진다.

**Tech Stack:** Python 3, Jinja2, Anthropic SDK(claude-sonnet-5). HTML 템플릿 변경은 단위 테스트가 아니라 `generate_html.py`로 임시 날짜 렌더 후 grep·브라우저 프리뷰로 검증한다(프로젝트 관례).

**검증 원칙 (모든 태스크 공통):**
- 라이브 산출물(`web/briefings/{실제날짜}/…`, `gh-pages`)은 절대 건드리지 않는다.
- 렌더 검증은 **가짜 날짜 `2099-01-01`** 로만 생성하고, 검증 후 `web/briefings/2099-01-01/` 디렉터리를 삭제한다.
- `data/analysis_us.json`·`data/latest_us.json`·`data/analyst_quotes.json`(모두 gitignored)을 렌더 입력으로 쓴다. 임시로 수정했다면 원복한다.
- 텔레그램 발송·`git push`는 이 플랜 범위 밖(사용자 지시 시에만).

---

## File Structure

- `scripts/call_claude.py` — `US_SYSTEM_PROMPT`에 todays_view 규칙·필드·JSON 예시 추가 (Task 5).
- `scripts/generate_html.py` — todays_view·scorecard 게이트 확장 (Task 1).
- `scripts/templates/sections/_sidebar_kospi.html` → `_sidebar_cta.html` 리네임 (Task 2).
- `scripts/templates/briefings/kospi.html` — 사이드바 include 경로 갱신 (Task 2).
- `scripts/templates/sections/analyst_quotes.html` — ib-row 스타일로 재작성 (Task 3).
- `scripts/templates/briefings/us.html` — 본문·사이드바 재구성 (Task 4).

각 파일은 단일 책임을 유지한다. 템플릿은 표현, `generate_html.py`는 컨텍스트 조립, `call_claude.py`는 AI 출력 계약을 담당한다.

---

## Task 1: generate_html.py — todays_view·scorecard 게이트를 US로 확장

**Files:**
- Modify: `scripts/generate_html.py:913-915` (scorecard 게이트)
- Modify: `scripts/generate_html.py:928` (todays_view 게이트)

- [ ] **Step 1: scorecard 게이트를 US 포함으로 수정**

`scripts/generate_html.py`의 다음 블록(line 913 부근):

```python
    # 코스피 성적표 카드 — 사이드바 accuracy.html 대체(kospi 전용). 데이터 부족 시 빈 dict → 카드 생략.
    if internal_type == "kospi":
        ctx.update(build_scorecard(internal_type))
        ctx["scorecard"] = bool(ctx.get("sc_monthly"))
```

를 아래로 바꾼다(주석도 갱신):

```python
    # 예측 성적표 카드 — 사이드바 accuracy.html 대체(kospi·us 공용). 데이터 부족 시 빈 dict → 카드 생략.
    if internal_type in ("kospi", "us"):
        ctx.update(build_scorecard(internal_type))
        ctx["scorecard"] = bool(ctx.get("sc_monthly"))
```

- [ ] **Step 2: todays_view 게이트를 US 포함으로 수정**

`scripts/generate_html.py`의 line 928 부근:

```python
        # 오늘의 관점(todays_view) — 코스피 오전 브리핑 전용. 없으면 None → 템플릿에서 섹션 생략.
        ctx["todays_view"] = analysis.get("todays_view") if internal_type == "kospi" else None
```

를 아래로 바꾼다:

```python
        # 오늘의 관점(todays_view) — 코스피·미국 브리핑. 없으면 None → 템플릿에서 섹션 생략.
        ctx["todays_view"] = analysis.get("todays_view") if internal_type in ("kospi", "us") else None
```

- [ ] **Step 3: format_in_view는 US에서 False로 유지되는지 확인 (수정 없음)**

line 930이 아래 그대로인지 확인만 한다(변경하지 않는다). US는 `format_in_view=False`라 이렇게 보는 이유가 기존 형식 본문+reason_title로 남는다.

```python
        ctx["format_in_view"] = (internal_type == "kospi")
```

Run:
```bash
cd "/Users/luke/Service App/double-shot" && grep -n 'format_in_view' scripts/generate_html.py
```
Expected: `ctx["format_in_view"] = (internal_type == "kospi")` 한 줄만 출력.

- [ ] **Step 4: build_scorecard가 US 데이터로 동작하는지 검증**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 -c "import sys; sys.path.insert(0,'scripts'); import generate_html as g; sc=g.build_scorecard('us'); print('sc_monthly:', bool(sc.get('sc_monthly')), '| cum:', sc.get('sc_cum_pct'), '| recent15:', sc.get('sc_recent15_pct'))"
```
Expected: `sc_monthly: True | cum: <숫자> | recent15: <숫자>` (빈 dict가 아니어야 함 — US 채점 57건 존재).

- [ ] **Step 5: Commit**

```bash
cd "/Users/luke/Service App/double-shot" && git add scripts/generate_html.py && git commit -m "feat(us): todays_view·scorecard 게이트를 미국 브리핑으로 확장"
```

---

## Task 2: 사이드바 파일 공용화 (_sidebar_kospi → _sidebar_cta)

**Files:**
- Rename: `scripts/templates/sections/_sidebar_kospi.html` → `scripts/templates/sections/_sidebar_cta.html`
- Modify: `scripts/templates/briefings/kospi.html:59`

- [ ] **Step 1: git mv로 리네임**

```bash
cd "/Users/luke/Service App/double-shot" && git mv scripts/templates/sections/_sidebar_kospi.html scripts/templates/sections/_sidebar_cta.html
```

- [ ] **Step 2: 리네임된 파일의 상단 주석 수정**

`scripts/templates/sections/_sidebar_cta.html`의 1번째 줄:

```jinja
{# 코스피 사이드바 CTA — 텔레그램 구독 카드(재디자인) + 월배당 계산기 링크 + 공통 푸터. 코스피 전용(_chip_cta 대체). #}
```

를 아래로 바꾼다:

```jinja
{# 사이드바 CTA — 텔레그램 구독 카드 + 월배당 계산기 링크 + 공통 푸터. 코스피·미국 브리핑 공용(_chip_cta 대체). #}
```

- [ ] **Step 3: kospi.html include 경로 갱신**

`scripts/templates/briefings/kospi.html:59`:

```jinja
      {% include "sections/_sidebar_kospi.html" %}
```

를 아래로 바꾼다:

```jinja
      {% include "sections/_sidebar_cta.html" %}
```

- [ ] **Step 4: 남은 참조가 없는지 확인**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && grep -rn "_sidebar_kospi" scripts/
```
Expected: 출력 없음(0건).

- [ ] **Step 5: 코스피 렌더가 여전히 동작하는지 확인**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 scripts/generate_html.py --type kospi --date 2099-01-01 --data-file data/latest_kospi.json --force 2>&1 | tail -3 && grep -c "월배당 계산기" web/briefings/2099-01-01/kospi/index.html
```
Expected: `wrote …/kospi/index.html` 로그 + `1` (월배당 배너 존재).

- [ ] **Step 6: 임시 산출물 정리**

```bash
cd "/Users/luke/Service App/double-shot" && rm -rf web/briefings/2099-01-01
```

- [ ] **Step 7: Commit**

```bash
cd "/Users/luke/Service App/double-shot" && git add -A scripts/templates && git commit -m "refactor: _sidebar_kospi → _sidebar_cta 리네임(코스피·미국 공용)"
```

---

## Task 3: 월가 코멘트 섹션을 외국계 시각(ib-row) 스타일로 재작성

**Files:**
- Modify: `scripts/templates/sections/analyst_quotes.html` (전체 재작성)

- [ ] **Step 1: analyst_quotes.html을 ib-list/ib-row 마크업으로 교체**

`scripts/templates/sections/analyst_quotes.html` 전체를 아래로 바꾼다. 섹션 제목("💬 월가 코멘트")·메타("48h 이내 실발언")는 유지하고, 카드 내부만 `ib_korea_views.html`과 동일한 `.ib-*` 클래스를 쓴다. 애널리스트 소속(affiliation)은 이름 옆에 `·`로 붙여 정보 손실 없이 기존 CSS만으로 표현한다.

```jinja
{# 월가 애널리스트 발언 — 외국계 시각(ib_korea_views)과 동일한 .ib-row 스타일. 리스트 비면 전체 생략. #}
{% if analyst_quotes %}
<div class="open-section">
  <div class="open-section__title" style="display:flex;align-items:center;gap:6px;">
    <span>💬 월가 코멘트</span>
    <span style="font-size:11px;font-weight:400;color:var(--muted);margin-left:auto;text-transform:none;letter-spacing:0;">48h 이내 실발언</span>
  </div>
  <div class="ib-list">
    {% for q in analyst_quotes %}
    <div class="ib-row">
      <div class="ib-logo">{{ q.initials }}</div>
      <div class="ib-body">
        <div class="ib-name">{{ q.name }}{% if q.affiliation %} · {{ q.affiliation }}{% endif %} <span class="ib-badge {{ q.sentiment }}">{% if q.sentiment == 'bull' %}강세{% elif q.sentiment == 'bear' %}약세{% else %}중립{% endif %}</span></div>
        <div class="ib-text">{{ q.quote }}</div>
        <div class="ib-foot">
          <a class="ib-src" href="{{ q.search_url }}" target="_blank" rel="noopener noreferrer">{{ q.source }} <span class="ib-src-arrow">→</span></a>
          <span class="ib-time">{{ q.time_label }}</span>
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 2: 렌더 검증 — 월가 코멘트가 ib-row로 나오는지 확인**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 scripts/generate_html.py --type us --date 2099-01-01 --data-file data/latest_us.json --force 2>&1 | tail -2 && echo "--- ib-row 개수 / analyst-card 잔존 ---" && grep -c "ib-row" web/briefings/2099-01-01/us/index.html && grep -c "analyst-card" web/briefings/2099-01-01/us/index.html
```
Expected: `ib-row` ≥1, `analyst-card` = 0. (`data/analyst_quotes.json`이 비어 있으면 둘 다 0 — 이 경우 Step 3으로 임시 데이터 주입 후 재확인.)

- [ ] **Step 3: (analyst_quotes.json이 비어 있을 때만) 임시 데이터로 재검증**

`data/analyst_quotes.json`이 `[]`라 Step 2에서 ib-row가 0이면, 임시 파일로 렌더만 확인한다:

```bash
cd "/Users/luke/Service App/double-shot" && cp data/analyst_quotes.json /tmp/aq_backup.json && cat > data/analyst_quotes.json <<'EOF'
[{"initials":"TL","name":"Tom Lee","affiliation":"Fundstrat","sentiment":"bull","quote":"연말 랠리 가능성이 높아요.","search_url":"https://www.google.com/search?q=Tom+Lee","source":"CNBC","time_label":"12시간 전"}]
EOF
python3 scripts/generate_html.py --type us --date 2099-01-01 --data-file data/latest_us.json --force 2>&1 | tail -1 && grep -c "ib-row" web/briefings/2099-01-01/us/index.html && cp /tmp/aq_backup.json data/analyst_quotes.json
```
Expected: `ib-row` ≥1. 마지막 명령이 원본 `analyst_quotes.json`을 복원한다.

- [ ] **Step 4: 임시 산출물 정리**

```bash
cd "/Users/luke/Service App/double-shot" && rm -rf web/briefings/2099-01-01
```

- [ ] **Step 5: Commit**

```bash
cd "/Users/luke/Service App/double-shot" && git add scripts/templates/sections/analyst_quotes.html && git commit -m "style(us): 월가 코멘트를 외국계 시각 ib-row 스타일로 통일"
```

---

## Task 4: us.html 본문·사이드바 재구성

**Files:**
- Modify: `scripts/templates/briefings/us.html:18-47`

- [ ] **Step 1: 본문 블록 재구성**

`scripts/templates/briefings/us.html`의 `<div class="accordion-body__inner">` 내부(line 19~38)를 아래로 바꾼다. 순서: 오늘의 관점 → 예측 스트립 → 이렇게 보는 이유(기존 형식 본문) → comfort_line → divider → 월가 코멘트 → stock_picks.

```jinja
          <div class="accordion-body__inner">
            {# 오늘의 관점 — todays_view 있을 때만(없으면 아래 예측은 대형 카드로 폴백) #}
            {% if todays_view %}{% include "sections/todays_view.html" %}{% endif %}
            {# 당일 방향 예측 — 오늘의 관점이 있으면 참고 지표 스트립으로 격하 #}
            {% if todays_view %}{% include "sections/prediction_strip.html" %}{% else %}{% include "sections/prediction.html" %}{% endif %}
            {# 이렇게 보는 이유 — US 기존 형식 본문(reason_title이 섹션 제목) #}
            {% if analysis_format == 'scenario' %}
              {% include "sections/scenario_split.html" %}
            {% elif analysis_format == 'qa' %}
              {% include "sections/qa.html" %}
            {% elif analysis_format == 'signal' %}
              {% include "sections/signal_board.html" %}
            {% elif analysis_format == 'flow' %}
              {% include "sections/flow_chain.html" %}
            {% elif analysis_format == 'keynum' %}
              {% include "sections/key_numbers.html" %}
            {% else %}
              {% include "sections/why_what_so.html" %}
            {% endif %}
            {% if comfort_line %}{% include "sections/_comfort_line.html" %}{% endif %}
            <div class="divider"></div>
            {% if analyst_quotes %}{% include "sections/analyst_quotes.html" %}{% endif %}
            {% if stock_picks %}{% include "sections/stock_picks.html" %}{% endif %}
          </div>
```

- [ ] **Step 2: 사이드바 블록 재구성**

같은 파일의 `<aside class="layout-grid__right">` 블록(line 43~47)을 아래로 바꾼다. 성적표(있으면)→시장지표→텔레그램/월배당 사이드바.

```jinja
    <aside class="layout-grid__right">
      {% if scorecard %}{% include "sections/_scorecard.html" %}{% elif accuracy %}{% include "sections/accuracy.html" %}{% endif %}
      {% if market_items %}{% include "sections/market_data.html" %}{% endif %}
      {% include "sections/_sidebar_cta.html" %}
    </aside>
```

- [ ] **Step 3: 렌더 검증 — 구조·순서·섹션 존재 확인**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 scripts/generate_html.py --type us --date 2099-01-01 --data-file data/latest_us.json --force 2>&1 | tail -2 && python3 - <<'PY'
html = open("web/briefings/2099-01-01/us/index.html", encoding="utf-8").read()
checks = {
  "예측 스트립(participi)": 'predc' in html,           # prediction_strip 또는 prediction
  "우리 성적표": '우리 성적표' in html or 'sc-card' in html,
  "월배당 배너": '월배당 계산기' in html,
  "텔레그램 구독 카드": 'subcard__btn' in html,
  "구형 chip_cta 미포함": 'sidebar-cta__tg' not in html,
}
for k,v in checks.items():
    print(("OK " if v else "FAIL "), k)
PY
```
Expected: 모든 항목 `OK`. (오늘의 관점은 `data/analysis_us.json`에 아직 todays_view가 없어 이번엔 폴백으로 대형 예측 카드가 나올 수 있음 — Task 6에서 todays_view 포함 재검증.)

- [ ] **Step 4: 임시 산출물 정리**

```bash
cd "/Users/luke/Service App/double-shot" && rm -rf web/briefings/2099-01-01
```

- [ ] **Step 5: Commit**

```bash
cd "/Users/luke/Service App/double-shot" && git add scripts/templates/briefings/us.html && git commit -m "feat(us): 브리핑 본문·사이드바를 코스피 구조로 재구성"
```

---

## Task 5: US AI 프롬프트에 todays_view 생성 규칙 추가

**Files:**
- Modify: `scripts/call_claude.py` (`US_SYSTEM_PROMPT`, line 526~861 범위)

- [ ] **Step 1: todays_view 작성 규칙 블록 추가**

`scripts/call_claude.py`의 US 프롬프트에서 `### 예측 근거 섹션 타이틀(reason_title) 작성 규칙`(line 709) **바로 앞**에 아래 블록을 삽입한다.

```python
### 오늘의 관점(todays_view) 작성 규칙 (미국 브리핑)
- **⚠️ 형식(scenario/qa/signal 등)과 무관하게 항상 완전히 출력한다. view_title·dek 두 필드를 모두 채운다.**
- 구조적·대형 테마 우선: news_summary에 실적 시즌·연준 정책 전환·대형 M&A처럼 하루로 끝나지 않고
  여러 세션에 걸쳐 시장을 지배하는 테마가 있으면, 단발 등락보다 우선해 view_title에 반영한다.
  단 news_summary에 실제로 존재하는 테마만 반영하고, 없으면 지어내지 않는다(데이터 정합성).
- view_title: 오늘밤 미국장을 한 줄로 규정하는 에디토리얼 제목. 예측 방향 단정 금지, 관점 제시.
- dek: view_title 아래 붙는 1~2문장 부제(해요체). 오늘 관점의 맥락을 풀어 설명한다. `<b>` 강조 허용. **항상 채운다.**
- recap·outlook은 미국 브리핑에서 표시하지 않으므로 출력하지 않는다.

```

- [ ] **Step 2: 필수 필드 목록에 todays_view 추가**

`scripts/call_claude.py:750`:

```python
**[필수] JSON에 반드시 포함해야 하는 필드: prediction, reason_title, reasons, stock_picks, comfort_line**
```

를 아래로 바꾼다:

```python
**[필수] JSON에 반드시 포함해야 하는 필드: prediction, reason_title, todays_view(view_title·dek), reasons, stock_picks, comfort_line**
```

- [ ] **Step 3: JSON 예시에 todays_view 블록 추가**

`scripts/call_claude.py`의 US JSON 예시에서 `"reason_title": "왜 오를까? — 선물 강세·빅테크 반등 동시 호재",`(line 760) 다음 줄, `"comfort_line": …`(line 761) **앞**에 아래를 삽입한다.

```python
  "todays_view": {
    "view_title": "실적 시즌 한복판, 오늘밤 진짜 변수는 금리",
    "dek": "빅테크 실적이 지수를 밀어올렸지만, 오늘은 방향보다 <b>10년물 금리</b>가 어디까지 가느냐가 관건이에요."
  },
```

- [ ] **Step 4: 프롬프트가 문법적으로 온전한지(파이썬 import) 확인**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 -c "import sys; sys.path.insert(0,'scripts'); import call_claude; assert 'todays_view' in call_claude.US_SYSTEM_PROMPT; assert 'view_title·dek' in call_claude.US_SYSTEM_PROMPT; print('US_SYSTEM_PROMPT ok, len=', len(call_claude.US_SYSTEM_PROMPT))"
```
Expected: `US_SYSTEM_PROMPT ok, len= <숫자>` (import 에러 없음, todays_view 규칙·필드 포함).

- [ ] **Step 5: Commit**

```bash
cd "/Users/luke/Service App/double-shot" && git add scripts/call_claude.py && git commit -m "feat(us): AI 프롬프트에 오늘의 관점(todays_view) 생성 규칙 추가"
```

---

## Task 6: 오늘의 관점 포함 엔드투엔드 렌더 + 브라우저 프리뷰 검증

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: data/analysis_us.json에 임시 todays_view 주입 후 렌더**

실제 Claude 호출 없이, 현재 `data/analysis_us.json`에 todays_view를 임시로 넣어 오늘의 관점이 렌더되는 전체 흐름을 확인한다.

```bash
cd "/Users/luke/Service App/double-shot" && cp data/analysis_us.json /tmp/analysis_us_backup.json && python3 - <<'PY'
import json
p = "data/analysis_us.json"
a = json.load(open(p, encoding="utf-8"))
a["todays_view"] = {
  "view_title": "실적 시즌 한복판, 오늘밤 진짜 변수는 금리",
  "dek": "빅테크 실적이 지수를 밀어올렸지만, 오늘은 방향보다 <b>10년물 금리</b>가 관건이에요."
}
json.dump(a, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("injected todays_view")
PY
python3 scripts/generate_html.py --type us --date 2099-01-01 --data-file data/latest_us.json --force 2>&1 | tail -2
```
Expected: `injected todays_view` + `wrote …/us/index.html`.

- [ ] **Step 2: 순서·섹션 자동 검증**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 - <<'PY'
html = open("web/briefings/2099-01-01/us/index.html", encoding="utf-8").read()
def idx(s): 
    i = html.find(s); 
    return i if i>=0 else 10**9
order = [("오늘의 관점", 'tv-kicker'), ("예측 스트립", 'predc__lbl'),
         ("이렇게 보는 이유(형식 본문)", 'reason'), ("월가 코멘트", '월가 코멘트'),
         ("종목 픽", 'stock_picks' )]
positions = [(name, idx(sel)) for name, sel in order]
print("탐지된 위치:", [(n, p if p<10**9 else 'MISSING') for n,p in positions])
seq = [p for _,p in positions if p<10**9]
print("오늘의 관점 존재:", 'tv-kicker' in html)
print("순서 단조 증가:", seq == sorted(seq))
PY
```
Expected: `오늘의 관점 존재: True`, `순서 단조 증가: True`.

- [ ] **Step 3: 브라우저 프리뷰로 시각 확인**

`mcp__Claude_Browser__preview_start`로 로컬 파일을 연다(정적 HTML이므로 `url`에 file 경로 대신, 간단 서버가 없으면 아래처럼 python http.server 사용):

```bash
cd "/Users/luke/Service App/double-shot/web" && python3 -m http.server 8799 >/dev/null 2>&1 &
```

그다음 `preview_start {url: "http://localhost:8799/briefings/2099-01-01/us/index.html"}` → `read_page`로 본문 순서(오늘의 관점 → 예측 스트립 → 이유 → 월가 코멘트 → 픽)와 사이드바(성적표·월배당 배너)를 확인하고, `computer {action:"screenshot"}`으로 근거를 남긴다. CSS 경로가 절대경로(`/assets/…`)라 http.server 루트(`web/`)에서 정상 로드된다.

Expected: 월가 코멘트가 외국계 시각과 동일한 카드 모양, 예측이 "참고 지표" 스트립, 사이드바에 "우리 성적표" 카드 + "월배당 계산기" 배너가 보인다.

- [ ] **Step 4: 임시 상태 원복 및 정리**

```bash
cd "/Users/luke/Service App/double-shot" && cp /tmp/analysis_us_backup.json data/analysis_us.json && rm -rf web/briefings/2099-01-01 && pkill -f "http.server 8799" 2>/dev/null; git status --short
```
Expected: `data/analysis_us.json` 복원, 임시 브리핑 삭제. `git status --short`에 `web/briefings/2099-01-01`·`data/analysis_us.json` 변경이 남아 있지 않아야 한다(라이브 오염 방지).

- [ ] **Step 5: 최종 상태 확인 (커밋할 것이 없음)**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && git log --oneline -5 && git status --short
```
Expected: Task 1~5 커밋 5개가 보이고, 검증 잔여물(임시 날짜 디렉터리·gitignored 데이터 변경)이 워킹트리에 없다.

---

## Self-Review (작성자 확인 완료)

- **Spec 커버리지:** 오늘의 관점(Task 5+1+4), 당일 방향 예측 스트립(Task 4), 이렇게 보는 이유 기존 형식(Task 4, format_in_view 유지 Task 1 Step 3), 월가 코멘트 ib 스타일(Task 3), 우리 성적표(Task 1+4), 텔레그램/월배당 사이드바(Task 2+4) — 모두 태스크 존재.
- **Placeholder:** 없음. 모든 코드 스텝에 실제 코드·명령·기대 출력 포함.
- **타입 일관성:** 게이트 조건 `internal_type in ("kospi","us")` 통일, 사이드바 include 경로 `sections/_sidebar_cta.html` 통일, 월가 코멘트 필드(`q.initials/name/affiliation/sentiment/quote/search_url/source/time_label`)는 기존 `analyst_quotes.html`과 동일.
- **주의:** 라이브 산출물 미변경 원칙을 모든 렌더 검증에 명시(가짜 날짜 + 정리 스텝).
