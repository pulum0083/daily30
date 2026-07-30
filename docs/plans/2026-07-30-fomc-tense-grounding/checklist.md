# 체크리스트 — 2026-07-30 FOMC 시제 사고

## 조사
- [x] 오염 페이지 특정 (`web/briefings/2026-07-30/{kospi,us}/`)
- [x] 실제 FOMC 사실 교차 확인 (동결 9-3 / 의장 워시 / 점도표 인상 우세)
- [x] RC-1 확인 — `fetch_data.py:162` 날짜 단위 분류
- [x] RC-2 확인 — 소스 피드 92건 전부 `actual=''`
- [x] RC-3 확인 — `C 은행`(공백) 정규식 통과 실증
- [x] RC-4 확인 — catalysts 문자열화 + "오늘 지표 없음"(FOMC 날)
- [x] RC-5 확인 — validate_analysis에 시제 게이트 없음

## 작업 1 — 라이브 정정
- [x] 코스피 스냅샷 6곳 정정
- [x] 코스피 index.html 대응 정정
- [x] 미국 스냅샷 FOMC 카드·todays_view 정정
- [x] 미국 스냅샷 씨티그룹 이슈 제거
- [x] 미국 스냅샷 유가 "급락" 완화
- [x] 미국 index.html 대응 정정
- [x] 정정 후 잔존 검사 (파월·예고형·씨티 0건)

## 작업 2 — 재발 방지
- [x] Fix A — 캘린더 `status: released/upcoming` (시각 비교)
- [x] Fix B — 프롬프트 `actual` 판정 제거 → `status` 기반
- [x] Fix C — 익명 게이트 공백 허용
- [x] Fix D — 수집 신뢰도 게이트 (`_grounding_failure_signals`)
- [x] Fix E — 이벤트 시제 게이트 (`validate_event_tense`)
- [x] 테스트 작성 (A/C/D/E)
- [x] 전체 테스트 스위트 통과 확인

## 마무리
- [x] context-notes.md 갱신
- [x] SERVICE_RULES.md §29 추가
- [x] 커밋
- [ ] 푸시·배포 (사용자 지시 대기)
