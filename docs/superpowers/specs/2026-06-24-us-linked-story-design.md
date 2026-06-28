# 코스피 브리핑: 섹터 브리핑 → 미국 연계 종목 소식 교체

## 목적

코스피 예측 브리핑의 섹터 로테이션 브리핑(sector_focus)을 삭제하고, 당일 한국 시장에 가장 임팩트가 큰 미국 이벤트 1건을 다루는 `us_linked_story` 섹션으로 교체한다.

## 삭제 범위

### call_claude.py
- `SECTOR_POOL` 상수 (8개 섹터 정의)
- `SECTOR_BY_KEY` 딕셔너리
- `KOSPI_SYSTEM_PROMPT` 내 "오늘의 섹터 브리핑(sector_focus) 작성 규칙" 블록 전체 (line 257~293)
- `KOSPI_SYSTEM_PROMPT` 내 JSON 예시의 `sector_focus` 필드 (line 342~352)
- `KOSPI_SYSTEM_PROMPT` 필수 필드 목록에서 `sector_focus` 제거 (line 299)
- `US_SYSTEM_PROMPT` 내 "반도체 섹터 브리핑(sector_semicon) 작성 규칙" 블록 (line 595~605)
- `US_SYSTEM_PROMPT` 내 JSON 예시의 `sector_semicon` 필드 (line 654~661)
- `load_sector_history()` 함수
- `save_sector_to_history()` 함수
- `build_sector_avoidance_hint()` 함수
- `pick_sector()` 함수
- main 함수 내 sector 관련 호출부

### generate_html.py
- line 719~724: `sector_focus` / `sector_semicon` 컨텍스트 빌드 블록

### 템플릿
- `scripts/templates/sections/sector_focus.html` 파일 삭제

### kospi.html 템플릿
- line 36: `{% if sector_signal %}{% include "sections/sector_focus.html" %}...{% endif %}` 교체

### 데이터 파일
- `data/sector_history_*.json` — 더 이상 생성/참조하지 않음 (기존 파일은 수동 삭제)

## 추가: us_linked_story 섹션

### JSON 출력 스키마

```json
{
  "us_linked_story": {
    "title": "마이크론 실적 발표 — 내일 새벽, HBM 가이던스가 핵심",
    "paragraphs": [
      "마이크론이 한국시간 내일(6/26) 새벽 실적을 발표해요. ...",
      "월가 컨센서스는 매출 <b>$8.8B</b>(YoY +50%), ...",
      "반대로 DRAM 재고 증가나 가격 하락 시그널이 나오면 ..."
    ],
    "related_stocks": [
      {"name": "SK하이닉스", "code": "000660"},
      {"name": "삼성전자", "code": "005930"},
      {"name": "MU", "code": "MU"}
    ]
  }
}
```

### call_claude.py 프롬프트 규칙

`KOSPI_SYSTEM_PROMPT`에 추가할 규칙.

```
### 미국 연계 종목 소식(us_linked_story) 작성 규칙
코스피 아침 브리핑 하단에 붙는, 오늘 한국 시장에 가장 임팩트가 큰 미국 이벤트 1건 심층 분석.

- **주제 선택**: 뉴스 요약·시장 데이터에서 한국 종목에 직접 영향을 주는 미국 이벤트를 1건 고른다.
  - 실적 발표 (마이크론→SK하이닉스, 애플→LG이노텍 등)
  - 정책·규제 (미국 반도체 수출규제→반도체주, FOMC→금융주 등)
  - 미국 종목 급등락 (테슬라→2차전지, 엔비디아→반도체 등)
  - 해당 이벤트가 한국 시장에 왜 중요한지가 핵심.
- **title**: 이벤트 핵심을 한 줄로. 30~50자. 마침표 종결 아닌 헤드라인 스타일.
- **paragraphs**: 3개 문단, 각 문단 해요체 1~2문장.
  - 1문단: 이벤트 핵심 — 무엇이, 언제 일어나는지
  - 2문단: 한국 연관 종목에 미치는 영향 — 수치 근거(<b> 강조)
  - 3문단: 리스크 시나리오 또는 반대 방향 가능성
- **related_stocks**: 이 이벤트와 직접 연관된 한국 종목 2~4개. 미국 티커도 포함 가능.
  - name: 종목명 (한국은 한글, 미국은 티커)
  - code: 종목 코드 (한국 6자리, 미국 티커)
- 뉴스 요약에 마땅한 미국 이벤트가 없으면 `us_linked_story`를 null로 출력한다. 억지로 만들지 않는다.
```

필수 필드 목록 변경: `sector_focus` → `us_linked_story` (null 허용).

### 템플릿: us_linked_story.html

`scripts/templates/sections/us_linked_story.html` 신규 생성.

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

### CSS 추가 (style.css)

```css
/* 미국 연계 종목 소식 */
.us-linked-title{font-size:14px!important;font-weight:700!important;color:var(--ink)!important;text-transform:none!important;letter-spacing:-0.2px;}
.us-linked-title::before{display:none!important;}
.us-badge{display:inline-flex;align-items:center;gap:4px;background:var(--primary-bg);color:var(--primary);font-size:11px;font-weight:700;padding:3px 8px;border-radius:4px;margin-right:6px;}
.us-linked-chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;}
.us-linked-chip{font-size:11px;color:var(--muted);background:var(--surface-soft);border:1px solid var(--hairline);padding:3px 8px;border-radius:12px;}
```

### generate_html.py 변경

line 719~724의 sector_focus 블록을 us_linked_story 블록으로 교체.

```python
if internal_type == "kospi":
    uls = analysis.get("us_linked_story") or {}
    if uls.get("title"):
        ctx["us_linked_title"] = uls["title"]
        ctx["us_linked_paragraphs"] = uls.get("paragraphs", [])
        ctx["us_linked_stocks"] = uls.get("related_stocks", [])
```

### kospi.html 템플릿 변경

line 36 교체.

```
{% if us_linked_title %}{% include "sections/us_linked_story.html" %}<div class="divider"></div>{% endif %}
```

### 위치

기존과 동일: reasons(분석) 뒤 → **us_linked_story** → watchpoints 앞.

### US 브리핑 (sector_semicon)

US 브리핑의 `sector_semicon`도 함께 삭제한다. US 브리핑에는 대체 섹션을 추가하지 않는다 (이미 미국 시장 자체를 다루므로 불필요).

## 영향 범위

- 코스피 브리핑만 변경. 마감 브리핑·미국 브리핑은 영향 없음 (sector_semicon 삭제 제외).
- validate_analysis.py: sector 관련 검증 없으므로 변경 불필요.
- 텔레그램 메시지: sector 내용을 포함하지 않으므로 변경 불필요.
