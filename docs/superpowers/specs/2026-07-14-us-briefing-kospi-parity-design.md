# 미국 시장 브리핑 — 코스피 예측 브리핑 구조 정렬 설계

작성일: 2026-07-14

## 목표

미국 시장 예측 브리핑(`/briefings/{date}/us/`)의 주요 구성을 코스피 예측 브리핑
(`/briefings/{date}/kospi/`)과 동일하게 맞춘다. 대상 주요 내용:

1. 오늘의 관점
2. 당일 방향 예측
3. 이렇게 보는 이유
4. 월가 코멘트 (코스피의 "외국계 시각"과 **동일한 시각 스타일**로)
5. 우리 성적표
6. 텔레그램 구독 카드
7. 월배당 계산기 배너

## 결정된 범위 (사용자 확정)

- **오늘의 관점**: US AI 프롬프트를 수정해 신규 추가한다.
- **이렇게 보는 이유**: US **기존 형식 본문 유지**(key_drivers 도입 안 함).
- **당일 방향 예측**: 코스피와 동일하게 **참고 지표 스트립(`prediction_strip`)으로 격하**한다.

## 현재 구조 대비 (as-is → to-be)

| 주요 내용 | 코스피 | 미국 (현재) | 미국 (변경 후) |
|---|---|---|---|
| 오늘의 관점 | `todays_view` (view_title·dek·recap·outlook) | 없음 | `todays_view` (view_title·dek) 신규 |
| 당일 방향 예측 | `prediction_strip` | `prediction`(대형 카드) | `prediction_strip` |
| 이렇게 보는 이유 | `key_drivers` 넘버링 | 형식 본문(why_what_so 등) | 형식 본문 **유지** |
| 월가 코멘트 | (해당 없음 — 외국계 시각 `ib_korea_views`) | `analyst_quotes` 카드 스타일 | `analyst_quotes` **ib-row 스타일** |
| 우리 성적표 | `_scorecard` 카드 | 간단 `accuracy`만 | `_scorecard` 카드 |
| 텔레그램/월배당 | `_sidebar_kospi` | `_chip_cta`(텔레그램만) | `_sidebar_cta`(공용) |

US 형식 풀(`FORMAT_POOL`)에는 `split`이 없으므로 `todays_view.html`의 recap/outlook
2단은 렌더되지 않는다. 따라서 US는 `view_title` + `dek`만 생성하면 충분하다
(토큰·환각 표면 최소화).

## 변경 상세

### 변경 1 — `scripts/call_claude.py` (`US_SYSTEM_PROMPT`)

- `### 오늘의 관점(todays_view) 작성 규칙 (미국 브리핑)` 블록 추가.
  - `view_title`: 오늘밤 미국장을 한 줄로 규정하는 에디토리얼 제목. 방향 단정 금지.
  - `dek`: 1~2문장 부제(해요체). `<b>` 강조 허용. 항상 채운다.
  - recap/outlook은 US에서 렌더되지 않으므로 요구하지 않는다.
- 필수 필드 목록(line ~750)에 `todays_view(view_title·dek)` 추가.
- JSON 예시(line ~753~)에 `todays_view` 블록 추가.
- 데이터 정합성: news_summary에 실제 존재하는 테마만 반영, 없으면 지어내지 않는다.

### 변경 2 — `scripts/generate_html.py`

- line 928 `todays_view` 게이트: `internal_type == "kospi"` → `internal_type in ("kospi", "us")`.
- line 913~915 `build_scorecard`/`scorecard` 게이트: `if internal_type == "kospi"`
  → `if internal_type in ("kospi", "us")`. `build_scorecard`가 type 인자로
  `briefings.json`을 필터링하므로 US 채점 데이터로 카드가 만들어진다.
- `format_in_view`(line 930)는 US에서 **False 유지** — 이렇게 보는 이유가 기존 형식
  본문으로 남고 `reason_title`이 그 제목으로 표시된다.

### 변경 3 — `scripts/templates/briefings/us.html`

본문 순서(사용자 지정):

```
todays_view (있으면)                      # 오늘의 관점
prediction_strip (todays_view 있으면) / prediction   # 당일 방향 예측
형식 본문 (scenario/qa/signal/flow/keynum/why_what_so)  # 이렇게 보는 이유(기존 형식)
comfort_line
divider
analyst_quotes (있으면)                    # 월가 코멘트
stock_picks
```

사이드바:

```
scorecard (있으면) / accuracy
market_data (있으면)
_sidebar_cta                               # 텔레그램 구독 카드 + 월배당 배너
```

kospi.html처럼 `{% if todays_view %}prediction_strip{% else %}prediction{% endif %}`
패턴을 쓴다(todays_view 미생성 시 안전 폴백).

### 변경 4 — `scripts/templates/sections/analyst_quotes.html`

`ib_korea_views.html`의 `.ib-list` / `.ib-row` / `.ib-logo` / `.ib-body` /
`.ib-name` / `.ib-badge` / `.ib-text` / `.ib-foot` / `.ib-src` / `.ib-time` 마크업으로
재작성한다. 섹션 제목("💬 월가 코멘트")과 메타("48h 이내 실발언")는 유지.

필드 매핑:

| ib_korea_views | analyst_quotes |
|---|---|
| `v.initials` | `q.initials` |
| `v.house` | `q.name` (+ affiliation) |
| `v.sentiment` | `q.sentiment` (bull/bear/neu) |
| `v.summary` | `q.quote` |
| `v.url` | `q.search_url` |
| `v.source` | `q.source` |
| `v.time_label` | `q.time_label` |

affiliation은 이름 옆 또는 아래 보조 텍스트로 유지한다.

### 변경 5 — 사이드바 파일 정리

`sections/_sidebar_kospi.html` → `sections/_sidebar_cta.html`로 리네임하고
kospi.html·us.html 두 곳에서 공용으로 include한다. 파일 상단 주석의 "코스피 전용"
문구를 "코스피·미국 브리핑 공용"으로 수정한다. close.html은 `_chip_cta` 유지(범위 밖).

## 검증

- 임시 날짜로 US 브리핑을 재생성(`generate_html.py --type us --date <임시> --force`)해
  라이브 스냅샷을 건드리지 않고 결과 HTML을 만든다.
- 브라우저 프리뷰로 본문 순서(오늘의 관점 → 예측 스트립 → 이유 → 월가 코멘트 → 픽),
  월가 코멘트가 외국계 시각과 동일한 카드 모양인지, 사이드바 성적표·월배당 배너를 확인.
- `analyst_quotes.json`이 비어 있으면 섹션이 자동 생략되는지(운영 규칙 11) 재확인.
- 라이브 커밋/텔레그램 발송은 사용자 지시 시에만.

## 리스크 / 주의

- US AI 프롬프트 변경은 매일 21:20(KST) 실행되는 라이브 파이프라인의 출력 계약을
  바꾼다. `todays_view` 미생성 시에도 `{% if todays_view %}` 폴백으로 페이지가 깨지지
  않아야 한다(변경 3에서 보장).
- 스냅샷 우선 규칙(운영 규칙 2)에 따라, 이미 생성된 과거 US 브리핑은 스냅샷을 쓰므로
  이번 변경의 영향을 받지 않는다. 신규 생성분부터 적용된다.
- 성적표(`build_scorecard`)가 US 채점 데이터로 정상 동작하는지 구현 시 실측 확인.
