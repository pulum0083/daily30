# 월가 코멘트 섹션 설계 (Analyst Quotes)

**날짜:** 2026-06-07  
**대상 브리핑:** 미국 시장 브리핑 (`us`)  
**상태:** 승인됨

---

## 개요

유명 월가 애널리스트·투자자 12명의 최근 48시간 이내 실발언을 google_search로 수집해 미국 시장 브리핑에 섹션으로 표시한다. AI가 발언을 생성하거나 추론하는 것은 절대 금지 — 검색 결과에서 실제로 발견된 발언만 사용한다.

---

## 결정 사항

| 항목 | 결정 |
|---|---|
| 대상 발언 기간 | 48시간 이내 |
| 최대 표시 인원 | 4명 (최신순 정렬) |
| 섹션 위치 | 본문(긴급 점검) 아래, 관전 포인트 위 |
| 카드 스타일 | 아바타(이니셜) + 강세/약세/중립 뱃지 |
| 발언 없을 때 | 섹션 전체 숨김 (빈 상태 표시 없음) |
| 감성 분류 | Gemini가 검색·추출과 동시에 자동 분류 |
| 구현 방식 | 독립 스크립트 `fetch_analyst_quotes.py` |

---

## 애널리스트 목록 (12명)

| 이름 | 소속 | 이니셜 | 성향 |
|---|---|---|---|
| Tom Lee | Fundstrat | TL | 강세 |
| Ed Yardeni | Yardeni Research | EY | 강세 |
| Dan Ives | Wedbush | DI | 빅테크 강세 |
| Mike Wilson | Morgan Stanley | MW | 약세 |
| Savita Subramanian | Bank of America | SS | 중립~강세 |
| Bill Ackman | Pershing Square | BA | 이벤트 중심 |
| Stan Druckenmiller | Duquesne Family Office | SD | 매크로 |
| Mohamed El-Erian | Allianz | ME | 거시 |
| Jeff Gundlach | DoubleLine Capital | JG | 채권·금리 |
| Ray Dalio | Bridgewater Associates | RD | 거시·리스크 |
| Cathie Wood | ARK Invest | CW | 혁신·AI |
| Michael Burry | Scion Asset Management | MB | 약세 |

---

## 데이터 파이프라인

```
GHA us-briefing job
  → fetch_analyst_quotes.py          (NEW — continue-on-error: true)
      Gemini Flash + google_search
      → data/analyst_quotes.json
  → call_claude.py                   (변경 없음)
  → generate_html.py                 (analyst_quotes.json 읽어서 컨텍스트 주입)
      → web/briefings/{date}/us/index.html
```

---

## `fetch_analyst_quotes.py` 상세

### 동작

1. 애널리스트 12명을 소그룹으로 묶어 Gemini에게 검색 지시
2. Gemini가 `google_search` tool로 각 인물의 최근 발언 검색
3. 발견된 발언만 추출. 없으면 생략.
4. 각 발언에 대해 `bull` / `bear` / `neu` 감성 분류
5. 최신순 정렬 후 최대 4개만 보존
6. `data/analyst_quotes.json` 저장

### 검색 프롬프트 전략

```
각 인물별로: "{이름}" "{소속}" market outlook statement 2026
날짜 필터: 최근 48시간 이내 발언만 포함
할루시네이션 방지 지시: 검색 결과에 실제로 나타난 발언만 인용. 없으면 해당 인물 결과에서 제외.
```

### 출력 JSON 구조

```json
[
  {
    "name": "Tom Lee",
    "affiliation": "Fundstrat",
    "initials": "TL",
    "quote": "S&P500이 6,000 돌파를 향한 랠리를 재개할 준비가 됐습니다...",
    "source": "CNBC Fast Money",
    "published_at": "2026-06-06T23:14:00+09:00",
    "time_label": "어제 23:14",
    "sentiment": "bull"
  }
]
```

`published_at`: ISO 8601 (KST). 스크립트에서 최신순 정렬 후 4명 보존에 사용. `time_label`은 현재 KST 기준 "오늘/어제" 표시용.

발언이 없는 날: `[]` (빈 배열)

---

## 템플릿 (`sections/analyst_quotes.html`)

- `{% if analyst_quotes %}` 조건부 렌더 — 빈 배열이면 섹션 전체 생략
- 각 카드: 아바타(이니셜) + 이름 + 소속 + 감성 뱃지 + 발언 + 출처 + 시간
- CSS 클래스: `.analyst-card`, `.analyst-avatar`, `.analyst-badge.bull/bear/neu` 등 (style.css에 이미 추가됨)

---

## `us.json` 변경

```json
{
  "sections_main": [
    "prediction",
    "reasons",
    "nh_stock",
    "analyst_quotes",   ← NEW (nh_stock 뒤, watchpoints 앞)
    "watchpoints",
    "stock_picks"
  ]
}
```

---

## `generate_html.py` 변경

`build_analyst_quotes(data)` 빌더 추가:
- `data/analyst_quotes.json` 로드 (없으면 빈 배열)
- 템플릿 컨텍스트에 `analyst_quotes` 키로 주입

---

## GitHub Actions 변경 (`daily_report.yml`)

us-briefing job에 step 추가:

```yaml
- name: Fetch analyst quotes
  run: python3 scripts/fetch_analyst_quotes.py
  continue-on-error: true
  env:
    GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

`continue-on-error: true` — 수집 실패 시 기존 파이프라인 보호. 섹션만 생략됨.

---

## 에러 처리

| 상황 | 동작 |
|---|---|
| 검색 결과 없음 | `[]` 저장, 섹션 생략 |
| Gemini API 실패 | 스크립트 종료(exit 0), `[]` 저장 |
| JSON 파싱 실패 | 에러 로그 출력 후 `[]` 폴백 |
| 4명 초과 발견 | 최신순 4명만 보존 |

---

## 파일 변경 목록

| 파일 | 변경 |
|---|---|
| `scripts/fetch_analyst_quotes.py` | 신규 생성 |
| `scripts/templates/sections/analyst_quotes.html` | 신규 생성 |
| `scripts/config/us.json` | `sections_main`에 `analyst_quotes` 추가 |
| `scripts/generate_html.py` | `build_analyst_quotes()` 빌더 추가 |
| `.github/workflows/daily_report.yml` | us-briefing job에 step 추가 |
| `web/assets/style.css` | analyst 카드 CSS 이미 추가됨 ✅ |
