# 코스피 아침 브리핑 — 섹터 로테이션 설계

**작성일:** 2026-06-02
**대상 레포:** pulum0083/daily30 (`/Users/ncsoft/m-project/double-shot`)
**관련 문서:** `docs/PRD.md`, `agents/kospi_morning.md`, `scripts/call_claude.py`

---

## 1. 배경과 문제

코스피 아침 브리핑(07:30, 장 시작 전)에는 본문 하단에 **반도체 섹터 심층 분석** 한 칸이 들어간다. 현재 이 섹션은 `sector_semicon` 필드로 **매일 무조건 반도체 고정**이다. 로테이션 개념이 없다.

목표는 이 한 칸을 **매일 다른 섹터로 돌리는 것**이다. 하루 1개 섹터를, 그날 가장 의미 있는 섹터로 자동 선정해 심층 브리핑한다.

### 핵심 제약 (설계를 좌우함)

- 아침 브리핑은 **장 시작 전**이라 한국 섹터의 "오늘 등락" 정량 데이터가 없다.
- 현재 반도체 섹터 심층도 간밤 **미국 SOX·DRAM ETF + 뉴스 + 구조적 관점**으로 작성된다.
- 따라서 비반도체 섹터는 정량 프록시가 약하고, **뉴스(`news_summary_kospi`)와 구조적 관점**이 주 재료가 된다.

---

## 2. 섹터 풀 (8개 — 확정)

성장·경기·방어 균형을 고려한 8개로 고정한다.

| key | 섹터명 | 이모지 | 대표 종목 |
|---|---|---|---|
| `semicon` | 반도체 | 🏭 | 삼성전자, SK하이닉스, 한미반도체 |
| `power` | AI전력기기 | ⚡ | HD현대일렉트릭, LS일렉트릭, 효성중공업 |
| `defense` | 방산 | 🛡️ | 한화에어로스페이스, LIG넥스원, 현대로템 |
| `ship` | 조선 | 🚢 | HD현대중공업, 한화오션, 삼성중공업 |
| `battery` | 2차전지 | 🔋 | LG에너지솔루션, 에코프로비엠, 삼성SDI |
| `auto` | 자동차 | 🚗 | 현대차, 기아, 현대모비스 |
| `bio` | 바이오 | 💊 | 삼성바이오로직스, 셀트리온, 유한양행 |
| `finance` | 금융 | 🏦 | KB금융, 신한지주, 메리츠금융 |

---

## 3. 데이터 모델 변경

`sector_semicon` (반도체 고정) → `sector_focus` (오늘의 섹터) 로 일반화.

```json
"sector_focus": {
  "sector_key": "defense",
  "sector_name": "방산",
  "emoji": "🛡️",
  "signal": "한 줄 펀치라인 (30자 이내, 마침표 종결)",
  "paragraphs": [
    "1문단: 오늘 이 섹터의 핵심 모멘텀 또는 이슈",
    "2문단: 종목 구도 (승자 vs 패자, 왜 갈렸나)",
    "3문단: 리스크 · 포지션 관점"
  ]
}
```

기존 반도체 3문단 구조(모멘텀 → 종목구도 → 리스크)를 그대로 계승한다. `signal`/`paragraphs` 형태는 동일하고, 섹터 식별 메타(`sector_key`, `sector_name`, `emoji`)만 추가된다.

---

## 4. 하이브리드 선정 로직

> 사용자 결정: **하이브리드** (그날 가장 뜨거운 섹터 자동 선정 + 최근 다룬 섹터 가산점 제외).

1. **이력 파일**: `data/sector_history_kospi.json` 에 선정 이력을 기록한다.
   ```json
   [{"date": "2026-06-02", "sector_key": "semicon"}, ...]
   ```
2. **프롬프트 입력**: `call_claude.py`가 Claude에게 ① 8개 섹터 풀 ② **최근 5회(영업일 기준, 이력 5건) 선정 섹터 목록**을 전달한다.
3. **Claude 선정**: 뉴스 + 시장데이터를 보고 **최근 5회(영업일 기준, 이력 5건) 안 나온 섹터 중 오늘 가장 임팩트 큰 1개**를 선택한다. 단, 특정 섹터에 압도적 빅뉴스가 있으면 중복도 허용한다.
4. **이력 append**: `generate_html.py`(또는 분석 직후 단계)가 선택된 `sector_key`를 `sector_history_kospi.json`에 append 한다. 코드 레벨에서 로테이션 다양성을 보장한다.

### 후처리 검증 (코드)

- Claude가 반환한 `sector_key`가 8개 풀에 없으면 → 가장 오래 안 나온 섹터로 폴백.
- 최근 5회(영업일 기준, 이력 5건)과 중복이면 로그 경고만 남기고 통과(빅뉴스 예외 허용). 강제 교체는 하지 않는다.

---

## 5. 데이터 소스 범위

> 사용자 결정: **MVP 먼저.** 새 데이터 소스를 추가하지 않는다.

- 반도체: 기존대로 SOX·DRAM ETF 정량 활용.
- 그 외 섹터: 뉴스(`news_summary_kospi`) + 구조적 관점으로 작성.
- (후속 과제로 분리) `fetch_data.py`에 섹터별 미국 프록시 ETF(방산 XAR, 원자력 URA, 2차전지 LIT, 바이오 IBB 등) + 전일 KRX 섹터지수 추가 → 모든 섹터 정량 훅. **이번 범위 아님.**

---

## 6. 템플릿 변경

`scripts/templates/sections/sector_semicon.html` → `sector_focus.html` 로 일반화.

```html
{# 오늘의 섹터 심층 브리핑 — 관전 포인트 위, 블릿 형태 #}
<div class="open-section">
  <div class="open-section__title sector-section-title">{{ sector_emoji }} {{ sector_name }} 섹터 — {{ sector_signal }}</div>
  <div class="reason-block">
    <ul>
      {% for para in sector_paragraphs %}
      <li>{{ para | safe }}</li>
      {% endfor %}
    </ul>
  </div>
</div>
```

`generate_html.py`의 컨텍스트 매핑을 `sector_focus` 기준으로 변경:
- `sector_emoji` ← `sector_focus.emoji`
- `sector_name` ← `sector_focus.sector_name`
- `sector_signal` ← `sector_focus.signal`
- `sector_paragraphs` ← `sector_focus.paragraphs`

---

## 7. 재미 레이어

- **섹터별 고정 이모지** + 그날의 펀치라인 `signal` (기존 계승).
- **종목 구도**를 2문단에 명시 — 같은 섹터 안 승자/패자 대비로 드라마 부여 (예: "한화에어로 +X% vs LIG넥스원 보합, 왜 갈렸나").
- **연속성(선택)**: 이력에 직전 같은 섹터를 다룬 날짜가 있으면 "지난 X일 만에 다시 보는 섹터" 멘트를 1문단 도입에 자연스럽게 녹인다.

---

## 8. 변경 범위 요약 (touch points)

| 파일 | 변경 |
|---|---|
| `scripts/call_claude.py` | 섹터 브리핑 프롬프트를 반도체 고정 → 8개 풀 + 최근 이력 입력 기반 동적 선정으로. 출력 필드 `sector_semicon` → `sector_focus`(+메타) |
| `scripts/generate_html.py` | `sector_semicon` 매핑 → `sector_focus` 매핑. 이력 파일 append 로직 추가 |
| `scripts/templates/sections/sector_semicon.html` | → `sector_focus.html` 로 rename + 제목 동적화 |
| `scripts/templates/briefings/kospi.html` (include 지점) | include 파일명 갱신 |
| `agents/kospi_morning.md` | 섹터 섹션 규칙 문서 갱신 (반도체 고정 → 로테이션) |
| `data/sector_history_kospi.json` | 신규 이력 파일 |
| `docs/PRD.md` | 섹터 로테이션 반영 |

---

## 9. 비범위 (Non-goals)

- 섹터별 정량 데이터 소스 추가 (후속 과제).
- 코스피 **마감** 브리핑의 섹터 성과 패널 변경 (별개 기능, 손대지 않음).
- 미국 브리핑 변경.
- 8개 외 섹터 확장 (인터넷·엔터·로봇·게임 등은 추후).

---

## 10. 성공 기준

- 아침 브리핑이 매일 8개 풀 중 1개 섹터를 자동 선정해 심층 섹션을 출력한다.
- 같은 섹터가 5일 내 반복되지 않는다(빅뉴스 예외 제외).
- 기존 반도체 브리핑과 동일한 시각적 형태(제목+블릿)로, 섹터명·이모지만 동적으로 바뀐다.
- `generate_html.py` 실행 시 이력 파일이 정상 append 된다.
