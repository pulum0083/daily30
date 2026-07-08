# 외국계 IB 코멘트 섹션 (코스피 오전 브리핑) — 설계

작성일: 2026-07-08

## 배경 · 목적

미국 브리핑의 "💬 월가 코멘트"(`analyst_quotes`) 형식을 코스피 오전 브리핑에 이식한다.
단, 대상을 **해외 인플루언서 개인의 한국 종목 발언**이 아니라 **외국계 증권사·글로벌 IB의
한국 시장·대형주 코멘트**로 잡는다. 이유는 다음과 같다.

- 인플루언서(Dan Ives, Cathie Wood 등)가 한국 개별주를 짚는 일은 구조적으로 희소해, 무할루시네이션
  조건을 지키면 대부분의 날 섹션이 빈다.
- 반면 외국계 IB의 한국 시장·대형주 콜(예: 모건스탠리의 삼성·SK하이닉스 비중축소, JP모건의 코스피
  목표 상향)은 국내 매체가 당일 2차 보도로 활발히 다뤄, 실날짜·실URL·실출처가 확보된다.

### 실증 (2026-07-08 확인)

- Google News 한국어 RSS `"모건스탠리 SK하이닉스"` 쿼리 → 당일(07-08) 기사 4건(한국경제·연합인포맥스·
  서울신문·솔루션뉴스) 반환. `"JP모건 한국 증시"` → 코스피 목표 상향 기사 다수.
- Google News RSS 링크(`news.google.com/rss/articles/CBMi...`)는 batchexecute 엔드포인트로 발행사
  원문 URL 리졸브 성공 (예: `https://www.hankyung.com/article/202607071371i`). **새 API 키 불필요.**

## 핵심 원칙 — 무할루시네이션 보장 구조

| 요구조건 | 보장 방식 |
| --- | --- |
| 할루시네이션 없음 | 제목·날짜·링크·출처가 전부 RSS 실데이터. Gemini는 **요약·분류만** 수행하며 날짜·URL·출처를 생성할 수 없다. |
| 원본 링크 이동 | batchexecute로 발행사 원문 URL 리졸브 → 실패 시 Google News 링크 폴백(둘 다 실기사 연결). |
| 실날짜(최근 24시간) | RSS `pubDate`. |
| IB 귀속 정확성 | 제목/요약에 화이트리스트 IB명이 실제로 박혀 있어야만 채택. 귀속 불가하면 버린다. |

### 정직성 프레이밍 — "발언 인용"이 아니라 "코멘트 다이제스트"

소스는 국내 매체의 2차 보도 **헤드라인 + RSS 요약(약 180자)**뿐이라, IB 원문 발언 전문을 갖고 있지
않다. 따라서 **큰따옴표 버바텀 인용을 하지 않고**, "무엇을 어떤 톤으로 말했다더라 + 원문 보기"의
**다이제스트 카드**로 제시한다. 원문 전문이 필요하면 카드 링크로 이동한다.

## 데이터 플로우

신규 스크립트 `scripts/fetch_ib_korea_views.py` → `data/ib_korea_views.json`

```
1. Google News RSS(한국어) — 화이트리스트 IB × 코스피/대형주 쿼리 세트로 수집
2. pubDate 최근 24시간(now-24h ~ now, KST) 기사만 채택
3. 제목/요약에 화이트리스트 IB명이 실제로 박혀 있어야 채택 (없으면 버림)
4. IB당 1건, 최대 3건 (같은 콜 중복 제거 — 동일 IB는 가장 최근 1건만)
5. batchexecute로 원문 링크 리졸브 → 실패 시 Google News 링크 폴백
6. Gemini(google_search 미사용): 제목+요약 기반 1~2문장 스탠스 요약(해요체) + bull/bear/neu 분류
   - 제목/요약에 없는 내용 생성 금지
   - 목표가·지수 숫자는 원문 헤드라인/요약에 실제로 있으면 허용(스탠스의 핵심이므로),
     없으면 만들지 않는다
7. 대상 없으면 빈 배열 저장 → 섹션 자체 생략 (파이프라인 보호, exit 0)
```

### 화이트리스트 IB (한글 표기 기준 매칭)

골드만삭스 · 모건스탠리 · JP모건 · UBS · 씨티(그룹) · 노무라 · 맥쿼리 · HSBC · CLSA · 번스타인 ·
BofA(뱅크오브아메리카) · 바클레이스.

- IB명 표기 변형 매핑 필요 (예: "JP모건"/"JP모간"/"제이피모건", "골드만삭스"/"골드만", "씨티"/"씨티그룹").
- 각 IB에 이니셜 부여 (GS / MS / JPM / UBS / Citi / NOM / MQ / HSBC / CLSA / BST / BofA / BARC).

### 출력 JSON 스키마 (`data/ib_korea_views.json`)

```json
{
  "generated_at": "2026-07-08T07:20:00+09:00",
  "date": "2026-07-08",
  "views": [
    {
      "house": "모건스탠리",
      "initials": "MS",
      "summary": "삼성전자·SK하이닉스 메모리 사이클이 정점을 지났다며 비중 축소를 권고했어요...",
      "source": "한국경제",
      "url": "https://www.hankyung.com/article/202607071371i",
      "published_at": "2026-07-08T09:51:00+09:00",
      "time_label": "오늘 09:51",
      "sentiment": "bear"
    }
  ]
}
```

- `sentiment` ∈ {bull, bear, neu} (그 외 값은 neu로 정규화, analyst_quotes와 동일).
- `time_label`: 발언이 오늘(KST)이면 "오늘 HH:MM", 어제면 "어제 HH:MM".

## 표시

- 섹션 타이틀: **🏦 외국계 시각** (US "💬 월가 코멘트"와 구분), 우측 라벨 "최근 24시간".
- 카드 구조는 `analyst_quotes` 카드 스타일 재사용:
  `이니셜(GS/MS/JPM) · IB명(한글) · "글로벌 IB" · 스탠스 요약문 · 매체명 · time_label · bull/bear/neu 뱃지 · 원문 링크(→)`.
- bull=빨강 / bear=파랑 / neu=회색 (기존 색 그대로, 한국 투자자 관습).
- **빈 날은 섹션 자체 생략** (`views`가 비면 렌더 안 함).

## 배선

- 신규 스크립트: `scripts/fetch_ib_korea_views.py` → `data/ib_korea_views.json`
  - `fetch_news_live.py`의 RSS 유틸(`_fetch_rss`류)·`get_gemini_api_key` 재사용.
  - batchexecute 리졸버는 이 스크립트 내부 함수로 구현(재사용 대상 없음). 리졸브 실패 시 폴백.
- `generate_html.py`:
  - `build_ib_korea_views(data)` 빌더 추가 — `data/ib_korea_views.json`을 읽어 `{"ib_korea_views": [...]}` 반환.
    `url`이 없는 항목은 제외(analyst_quotes 규칙과 동일). 컨텍스트 병합은 kospi 렌더 경로에서만.
  - 섹션 템플릿 `scripts/templates/sections/ib_korea_views.html` — `analyst_quotes.html` 클론,
    필드명·타이틀 교체, 리스트 비면 전체 생략.
- **실제 렌더 배선은 `kospi.html`의 명시적 `{% include %}`가 담당한다.** (`sections_main` config 키는
  코드가 읽지 않는 문서용 목록이므로, 렌더에 영향을 주지 않는다.)
  - `scripts/templates/briefings/kospi.html`: reasons 블록 뒤 `<div class="divider"></div>`(현재 34행) 다음,
    watchpoints(현재 38행) 앞에 `{% if ib_korea_views %}{% include "sections/ib_korea_views.html" %}<div class="divider"></div>{% endif %}` 삽입. (US 레이아웃 reasons → analyst_quotes → picks와 동일 위치)
  - `scripts/config/kospi.json`: `sections_main` 목록에도 `"ib_korea_views"`를 `reasons` 뒤에 추가 —
    **문서 일관성 목적**(코드가 읽지는 않음), 실제 배선 아님.
- `.github/workflows/daily_report.yml`의 `kospi-briefing` job: `fetch_news.py` 뒤, `call_claude.py` 앞에
  `fetch_ib_korea_views.py` 스텝 추가, `continue-on-error: true`.
  - 이 데이터는 `call_claude` 분석 입력이 아니라 `generate_html`이 직접 소비하므로 검증
    파이프라인(validate_analysis) 순서에 영향 없음. `generate_html --render` 시점에 파일만 있으면 된다.

## 범위 밖 (YAGNI)

- 코스피 마감 브리핑·미국 브리핑에는 넣지 않는다 (요청은 오전 브리핑 한정).
- 인플루언서 개인 발언은 제외 (기존 US 월가 코멘트가 담당).
- 기사 본문 전문 크롤링은 하지 않는다 (제목+RSS 요약만으로 다이제스트 — 오히려 할루시네이션 여지가 적다).
- 라이브(main.js) 동적 갱신 없음. 생성 시점 정적 카드.

## 검증 기준 (구현 완료 판정)

1. `python3 scripts/fetch_ib_korea_views.py` 실행 → `data/ib_korea_views.json` 생성, 각 항목의 `url`이
   실제 발행사 원문(또는 동작하는 Google News 링크)으로 열림, `published_at`이 최근 24시간 이내.
2. 대상 없을 때 빈 배열 저장 + exit 0 (파이프라인 무중단).
3. `generate_html.py --type kospi`로 오전 브리핑 생성 시, 데이터 있으면 "🏦 외국계 시각" 섹션이
   reasons 뒤·stock_picks 앞에 렌더, 비면 섹션 생략.
4. 라이트/다크 모두 카드가 기존 analyst_quotes와 동일 스타일로 표시.
5. 화이트리스트 밖 매체·IB명 미포함 기사가 채택되지 않음 (귀속 정확성).
