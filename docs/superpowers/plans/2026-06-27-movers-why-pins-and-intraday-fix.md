# 왜움직였나 — 장중곡선 오염 픽스 + 핀 최대 2개(빨강 우선)

작성: 2026-06-27. 대상: 종목 대시보드(`/stocks/`).

## 배경

사용자 요청 2건.
1. 배포하면 장중 그래프가 "날아가는" 원인 규명·수정.
2. 곡선 위 뉴스 핀을 최소 2개로(빨강 'why' 우선, 없으면 회색 'related' 폴백).

## Plan

### A. 장중 곡선 오염 (버그)

- 원인: `whyMovedPush`가 라이브 폴러에서 가격을 `buf[code]`(곡선 버퍼)에 계속 추가한다.
  - 로컬은 `/api/*` 404라 안 불려서 깨끗 → 배포에서만 재현.
  - 마감 후 `pollNight`이 HL 24h 환산가를 `nowHHMM()`(예 22:00)와 함께 push.
    - `timeToX`가 930분 초과를 우측 끝(x=626)으로 clamp → 끝에 수직 스파이크.
    - HL 환산가가 종목별로 코스피 장중과 자릿수 불일치(예: 하이닉스 ~10배) → min/max 폭발 → 곡선이 차트 밖으로 날아감.
  - SERVICE_RULES §0 정합성 위반(실측 1분봉에 마감 후 perp 환산가 혼입).
- 수정: `whyMovedPush`에 KST 시각 게이트. 540~930분(09:00~15:30)일 때만 buf에 반영.
  - 장중 `pollDay`의 네이버 실측 KRW는 스케일·시간축 정상이라 그대로 통과.
  - 마감 후 HL 가격은 타일 숫자만 갱신, 곡선엔 미반영.

### B. 핀/뉴스 최대 2개, 빨강 우선

- 정합성 제약: 그날 실제 기사만. "최소 2"는 "최대 2"로 해석(기사 0~1건이면 그만큼만).
- `fetch_movers_why.py`:
  - `pick_event` → `_gemini_pick(name, articles)`로 분리(이중 RSS fetch 제거).
  - 새 `pick_events(name, today, change_pct, max_n=2)`: Gemini 1순위 + 남은 기사 폴백, tier 'why' 우선 정렬 후 상위 2.
  - `build_payload`가 `pick_events` 사용, events 리스트 그대로 주입.
- 렌더(`index.html`): 핀 2개 근접 시 번호 뱃지 겹침 방지(수평 최소 간격 보정). 리스트(`wm-tl`)는 events 순서 그대로 → 핀 번호와 일치 유지.

## Checklist

- [ ] A. `whyMovedPush` 시각 게이트 추가
- [ ] B1. `pick_event` → `_gemini_pick` 분리
- [ ] B2. `pick_events` 신설(빨강 우선, 최대 2)
- [ ] B3. `build_payload`에서 `pick_events` 사용
- [ ] B4. 핀 근접 시 수평 de-overlap 보정
- [ ] 단위 테스트(`pick_events` 빨강 우선·상한) 추가 후 `pytest scripts/` 통과
- [ ] 로컬 미리보기로 곡선·핀 확인

## Context Notes

- `buf`에 쓰는 곳은 `backfill`(초기 1회, /api/intraday)과 `whyMovedPush`(라이브) 둘뿐. 게이트는 후자만.
- 마감 후에도 `/api/intraday`는 당일 1분봉 풀데이터를 주므로 게이트 후에도 곡선은 "당일 전체"로 정상.
- 핀과 리스트는 같은 `events` 배열 1:1. JSON에서 빨강 우선 정렬하면 핀·리스트 모두 빨강이 1번.
- 테스트(`test_movers_why.py`)는 `classify_tier`/`_fallback_event`/`select_movers`만 검증 → 리팩터 안전.
- 푸시는 사용자 지시 시에만(deploy.yml 자동배포). 이번엔 커밋까지만.
