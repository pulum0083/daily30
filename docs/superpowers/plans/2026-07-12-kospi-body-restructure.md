# 코스피 아침 브리핑 본문 재구조 Implementation Plan

> 스펙: docs/superpowers/specs/2026-07-12-kospi-body-restructure-design.md
> 구현: 이 세션에서 인라인 실행(프롬프트+템플릿 작업 — 실데이터 생성으로 반복 검증). venv312 사용.

**Goal:** 오늘의 관점 안에 6+split 포맷 로테이션을 넣고, 예측 아래에 항상 표시되는 넘버링 "이렇게 보는 이유"(reasons)를 부활시킨다. 코스피 아침 전용.

**핵심 원칙:** todays_view(view_title+recap+outlook)는 계속 항상 생성(스키마 안정). recap/outlook은 analysis_format=='split'일 때만 관점 본문으로 표시(비-split 날은 포맷 본문). reasons는 항상 출력.

---

## Task 1: LLM 프롬프트·스키마 (call_claude.py, 코스피 SYSTEM_PROMPT + 빌드부)

**Files:** `scripts/call_claude.py`

- [ ] 1a. 코스피 전용 포맷 풀 추가 (모듈 상단, FORMAT_POOL 근처 line 34):
```python
FORMAT_POOL_KOSPI = ["split", "scenario", "why_what_so", "qa", "signal", "flow", "keynum"]
FORMAT_WEIGHTS_KOSPI = [3, 2, 2, 2, 2, 2, 2]   # split(복기/관전) 약간 높게
```
- [ ] 1b. 포맷 선택부(line 1332)를 브리핑 타입 분기:
```python
if briefing_type == "kospi":
    chosen_format = random.choices(FORMAT_POOL_KOSPI, weights=FORMAT_WEIGHTS_KOSPI, k=1)[0]
else:
    chosen_format = random.choices(FORMAT_POOL, weights=FORMAT_WEIGHTS, k=1)[0]
```
- [ ] 1c. 코스피 SYSTEM_PROMPT의 각 형식(B~G, line 449~502)에서 `reasons 필드는 출력하지 않는다.` 줄을 전부 삭제.
- [ ] 1d. 형식 지시 블록 맨 위(line 447 아래)에 형식 A: split + 전역 reasons 규칙 추가:
```
### 형식 A: split (복기·프레임)
`reason_title` 불필요. 아래 두 필드로 '오늘의 관점' 본문을 채운다:
- todays_view.recap / todays_view.outlook (아래 오늘의 관점 규칙대로). split일 때만 관점 본문에 표시된다.
다른 형식 필드(sc_*, qa_items 등)는 출력하지 않는다.

**[reasons — 형식과 무관하게 항상 출력]**
- `reasons`: 정확히 3개. 각 `{"text": "<b>핵심</b> 압축 설명…", "codes": ["6자리"]}`.
- 예측 방향의 **핵심 동인 3개만** 압축(예: 금리·반도체·수급). 관점 섹션(위 형식 본문)과 문장을 반복하지 말고 다른 각도로 요약한다.
- 개별 종목 언급 시 codes에 6자리 코드(미기재 시 검증 단계에서 제거). <b> 강조 허용, 해요체.
```
- [ ] 1e. todays_view 규칙(line 284~)에 dek 추가:
```
- dek: view_title 아래 1~2문장 부제(해요체). 오늘 관점의 맥락을 풀어 설명. 없으면 생략 가능.
```
- [ ] 1f. 필수 필드 목록(line 378)과 JSON 예시(line 390~)에 `reasons`(3개)·`todays_view.dek` 추가. 예시 reasons:
```json
"reasons": [
  { "text": "🚀 <b>미 반도체 강세</b>가 하루 더 이어질 자리예요. 간밤 SOX가 올라 국내 반도체 갭업 출발 가능성.", "codes": ["000660","005930"] },
  { "text": "📅 <b>삼성 실적 발표 전 관망</b>이 상단을 눌러요. 대형주 적극 베팅은 부담.", "codes": [] },
  { "text": "🌏 <b>외국인 수급은 아직 확신 부족</b>. 이틀째 순매수 이어져야 방향 신뢰.", "codes": [] }
]
```

**검증:** venv312로 `call_claude.py --type kospi --no-html` 여러 번 실행 → analysis_kospi.json에 `reasons`(3개)·`todays_view.dek` 존재, analysis_format이 split 포함 7종 중 하나. split 뽑히면 recap/outlook 존재.

---

## Task 2: 검증 게이트 (validate_analysis.py)

**Files:** `scripts/validate_analysis.py`

- [ ] 2a. todays_view.recap codes 검증 로직을 찾아(기존) reasons[].codes에도 동일 적용. 실측 안 되는 codes는 경고/제거(recap과 동일 방식). reasons가 없거나 3개 미만이어도 발행은 막지 않음(경고).

**검증:** venv312 validate_analysis.py --type kospi 실행 → reasons codes 검증 로그 확인, 치명오류 없이 통과.

---

## Task 3: 렌더 컨텍스트 (generate_html.py)

**Files:** `scripts/generate_html.py`

- [ ] 3a. `build_reasons`(line 251)에 reasons 넘버링 컨텍스트 추가: `ctx["reasons"] = analysis.get("reasons", [])`. split 포맷이면 포맷 컨텍스트 빌더 호출 대신 통과(recap/outlook은 todays_view에서 옴).
- [ ] 3b. `analysis_format == 'split'` 케이스 처리: build_reasons의 if/elif 체인에 split 추가(별도 컨텍스트 불필요 → pass). 
- [ ] 3c. todays_view 컨텍스트에 dek 전달 확인(analysis.todays_view.dek 그대로 넘어가면 OK — todays_view dict 통째 전달이면 자동).

**검증:** 렌더 후 컨텍스트에 reasons·dek 존재.

---

## Task 4: 템플릿 재배치

**Files:** `scripts/templates/briefings/kospi.html`, `sections/todays_view.html`, 신규 `sections/reasons.html`

- [ ] 4a. `todays_view.html`: view_title + dek(있으면) + 본문. 본문은 analysis_format=='split'이면 recap/outlook(현재 마크업), 아니면 아무것도 안 함(포맷은 kospi.html이 관점 셸 안에서 include). 
  - 실제로는 관점 셸을 kospi.html에서 열고, split이면 todays_view의 recap/outlook 파셜을, 아니면 포맷 include를 관점 안에 넣는 구조가 깔끔. → todays_view.html을 "셸(제목+dek) + split 본문"으로, 포맷 include는 kospi.html에서 관점 divider 전에 배치.
- [ ] 4b. `kospi.html` 재배치:
```jinja
{% include "sections/_now_band.html" %}
{% if todays_view %}
  {# 오늘의 관점: 제목+dek+본문(split이면 recap/outlook, 아니면 포맷) #}
  <div class="open-section tv-lead">
    <div class="tv-kicker">🧭 오늘의 관점</div>
    <h2 class="tv-title">{{ todays_view.view_title }}</h2>
    {% if todays_view.dek %}<p class="tv-dek">{{ todays_view.dek | safe }}</p>{% endif %}
    {% if analysis_format == 'split' %}
      {% include "sections/_tv_split.html" %}   {# recap/outlook 2단 #}
    {% elif analysis_format == 'scenario' %}{% include "sections/scenario_split.html" %}
    {% elif analysis_format == 'qa' %}{% include "sections/qa.html" %}
    {% elif analysis_format == 'signal' %}{% include "sections/signal_board.html" %}
    {% elif analysis_format == 'flow' %}{% include "sections/flow_chain.html" %}
    {% elif analysis_format == 'keynum' %}{% include "sections/key_numbers.html" %}
    {% else %}{% include "sections/why_what_so.html" %}{% endif %}
  </div>
{% endif %}
{% if todays_view %}{% include "sections/prediction_strip.html" %}{% else %}{% include "sections/prediction.html" %}{% endif %}
{% if reasons %}{% include "sections/reasons.html" %}{% endif %}
{% if comfort_line %}{% include "sections/_comfort_line.html" %}{% endif %}
<div class="divider"></div>
{% if ib_korea_views %}{% include "sections/ib_korea_views.html" %}<div class="divider"></div>{% endif %}
{% if stock_picks %}{% include "sections/stock_picks.html" %}{% endif %}
```
  - 주의: 포맷 템플릿들(qa.html 등)은 자체 `open-section` 래퍼가 있음 → 관점 셸 안에 중첩되면 스타일 충돌 가능. 관점 셸을 열지 말고, 제목/dek만 별도 블록 + 포맷은 기존대로 두되 reason_title을 관점 제목과 겹치지 않게 처리하는 방식도 검토(구현 중 렌더 확인).
- [ ] 4c. 신규 `sections/_tv_split.html`: 현재 todays_view.html의 recap/outlook 2단(tv-cols) 마크업 이관.
- [ ] 4d. 신규 `sections/reasons.html`: 프로토 `.rlist/.ritem/.rnum/.rtext` 넘버링:
```html
{# 이렇게 보는 이유 — 예측 근거 3줄 넘버링. reasons 있을 때만. #}
<div class="open-section">
  <div class="rz-title">이렇게 보는 이유</div>
  <div class="rz-list">
    {% for r in reasons %}
    <div class="rz-item"><div class="rz-num">{{ loop.index }}</div><div class="rz-text">{{ r.text | safe }}</div></div>
    {% endfor %}
  </div>
</div>
```

**검증:** 각 포맷별로 렌더 확인(아래 Task 6).

---

## Task 5: CSS (style.css)

**Files:** `web/assets/style.css`

- [ ] 5a. `.tv-dek` 추가(프로토 `.lead__dek` 이식): `font-size:13.5px;color:var(--muted);margin-top:8px;line-height:1.6;`
- [ ] 5b. `.rz-title/.rz-list/.rz-item/.rz-num/.rz-text` 추가(프로토 `.reason__t/.rlist/.ritem/.rnum/.rtext` 이식, 네임스페이스 rz-). `.rz-title::before{content:'💬'}`.

---

## Task 6: 실데이터 전수 검증 (venv312)

- [ ] 6a. `analysis_format`을 강제로 바꿔가며 7개 포맷 전부 렌더 확인. 방법: analysis_kospi.json 생성 후 `analysis_format`을 split/scenario/qa/signal/flow/keynum/why_what_so로 바꿔 `generate_html.py --force`로 재생성, 각각 로컬 브라우저에서 렌더 확인(관점 안 본문 + 예측 + 이렇게 보는 이유 넘버링 + 다크).
- [ ] 6b. reasons 넘버링 1·2·3 표시, dek 표시, split일 때 recap/outlook 표시 확인.
- [ ] 6c. 미국 브리핑 회귀: `call_claude.py --type us --no-html`가 split을 안 뽑고 정상 동작(FORMAT_POOL 유지) 확인.

---

## Task 7: 커밋

- [ ] 논리 단위로 분리: (1) call_claude 프롬프트·스키마, (2) validate reasons, (3) generate_html 컨텍스트, (4) 템플릿 재배치, (5) CSS. 생성된 web/ 데이터 파일은 커밋 제외.

## 리스크·롤백
- 스키마 변경으로 월요일 자동 브리핑 영향 → Task 6에서 7포맷 전수 통과가 게이트. 실패 시 커밋 안 함.
- 포맷 템플릿의 open-section 중첩 스타일 충돌 가능 → 4b에서 렌더로 확인 후 셸 구조 확정.
