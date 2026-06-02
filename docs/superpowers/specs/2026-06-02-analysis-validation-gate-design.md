# 분석 자동 검증 게이트 — 설계 문서

작성일: 2026-06-02
대상: `scripts/validate_analysis.py` (신규)

## 문제

Claude가 생성한 `analysis_{type}.json`의 수치·본문이 검증 없이 `generate_html.py`로
들어가 발행된다. 과거 "코스피 시총 6경", 환율 오류, 종목 가격 할루시네이션이
이 경로로 그대로 나갔다. `generate_html.py`에 수치 검증 코드는 0줄.

## 목표

`call_claude` → `generate_html` 사이에 자동 검증 게이트를 두어,
교정 가능한 오류는 자동 교정하고 치명적·교정 불가 오류는 발행을 차단한다.

## 흐름 (아키텍처 A — 독립 스크립트)

```
call_claude → analysis_{type}.json
   ↓
validate_analysis.py --type {type}
   ├─ 교정: analysis_{type}.json 제자리 덮어쓰기 (exit 0)
   ├─ 통과/경고: 그대로 (exit 0)
   └─ 치명적: exit 1 + 관리자 텔레그램 알림 → 잡 실패(발행 중단)
   ↓
generate_html (교정본 렌더)
```

워크플로 3개 잡(kospi/us/kospi-close) 모두 `call_claude` 다음, `generate_html`(=커밋 스텝) 앞에 스텝 추가.

## 입력

- `data/analysis_{type}.json` — 검증·교정 대상 (Claude 생성)
- `data/latest_{type}.json` — 실측 ground truth (지수·종목 후보·market_data)

`type` ∈ {kospi, us, kospi-close}. latest 파일명: kospi→latest_kospi, us→latest_us, kospi-close→latest_kospi_close.

## 2계층 검증

### 계층 1 — 실측 교차검증 (구조화 수치, 자동 교정)

`stock_picks[]`의 표시 가격·등락률을 `latest_*.json`의 종목 후보
(`kospi_candidates`/`us_candidates`/`sector_stocks`)와 **name/ticker로 매칭**.

- pick `price`(문자열 "53,600원"/"$53.60") → 숫자 파싱.
- 매칭 후보의 숫자 `price`와 비교, **±5% 초과 이탈 시 교정**:
  - `price`, `change`(="±X.XX%"), `change_cls` 를 실측값으로 덮어쓴다.
  - 같은 비율로 `entry`/`target`/`stop`의 "N원"/"$N" 숫자도 비례 스케일(파싱 가능할 때만).
- 매칭 후보가 없으면 교차검증 생략(WARN 로그).

### 계층 2 — 본문 패턴 스캔

검사 대상 문자열(타입별):
- kospi/us: `reasons[]`, `watch_items[].text`, `stock_picks[].scenario`, `stock_picks[].action_guide`
- kospi-close: `market_summary`, `why`, `what`, `so_what`, `sector_focus.paragraphs[]`
- **제외**: `reason_title`, `market_title` (헤드라인 — 별도 규칙)

금지 패턴:
1. **금지 단위 '경'**: `[\d][\d,]*\s*경(?![가-힣])` — 숫자+경 (뒤에 한글 음절 없을 때).
   "경기/경제/경우" 오탐 방지. 한국 시장에 '경 원' 단위 통계는 없음 → 100% 할루시네이션.
2. **환율 범위**: "환율"·"원/달러"·"원달러" 인근 `[\d,]+\s*원` 숫자가 1,000~2,000 밖.
3. **지수 등락률**: "코스피"·"코스닥" 인근 `[+-][\d.]+%` 절대값 30% 초과.

### 교정/차단 전략 (컨테이너별)

| 위치 | 위반 시 동작 |
|------|------------|
| `stock_picks[]` 가격 불일치 | in-place 교정 |
| `stock_picks[]` 본문 금지패턴 | 해당 pick 제거 |
| `reasons[]` / `paragraphs[]` / `watch_items[]` 원소 금지패턴 | 해당 원소 제거 |
| **스칼라 본문** (`market_summary`/`why`/`what`/`so_what`) 금지패턴 | **차단** (안전한 부분 제거 불가) |
| 구조 필드 불능 (`prediction.up_pct` 0~100 밖, `direction` 누락) | **차단** |
| 교정 후 브리핑 빈약 (`reasons`<2, picks 전부 제거, paragraphs 전부 제거) | **차단** |

## 심각도 → exit code

- CORRECTABLE / WARN / 통과 → exit 0 (교정본 저장 후 발행 진행)
- CRITICAL → exit 1 (발행 중단) + 관리자 알림

## 관리자 알림

차단(CRITICAL) 시에만 `TELEGRAM_ADMIN_CHAT_ID`(신규 GH Secret)로
"🚫 {type} 브리핑 차단 — {사유 요약}" 발송. 교정/경고는 GH 로그에만.
키 미설정 시 알림은 건너뛰되 **차단은 그대로 유지**(키 없다고 나쁜 데이터가 나가면 안 됨).
구독자 채널(`TELEGRAM_CHAT_ID`)과 분리.

## 테스트

`scripts/test_validate_analysis.py` — 픽스처 입력으로 케이스별 검증:
- 가격 ±5% 이탈 교정 (in-place)
- "6경" 본문 → reasons 원소 제거 / close 스칼라 → 차단
- "경기/경제" 오탐 없음
- 환율 범위·지수 등락률 위반
- `up_pct` 범위 차단
- reasons 과다삭제 차단
- 정상 입력은 무변경·exit 0

## 범위 밖 (v1 제외)

- 마감 브리핑 `market_breadth`/`investor`/`dpick` 검증 (이미 fetch 단계 검증 규칙 존재).
- 본문 스칼라 필드의 문장 단위 수술적 교정 (문법 깨짐 위험 → 차단으로 처리).
