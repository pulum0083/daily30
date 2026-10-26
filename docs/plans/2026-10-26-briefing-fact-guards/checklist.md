# 브리핑 사실 가드 — 체크리스트 (2026-10-26)

- [x] 현직 인물 표(`scripts/config/officeholders.json`) — 연준 의장 케빈 워시(2026-05-22 취임) 확인
- [x] 프롬프트에 현직 인물 지시(`_officeholder_directive`, 전 타입)
- [x] 발행 전 교정 `validate_analysis.fix_officeholder_names` — 역할 표현이 붙은 전임자 이름만 교체, 나머지는 경고
- [x] 최근 미국 세션 일지 수집(`fetch_data._recent_sessions` → `us_recent_sessions`) + 프롬프트 지시(`_us_session_log_directive`, 코스피)
- [x] 테스트 `scripts/test_fact_guards.py`(6), 전체 pytest 통과
- [x] 10/26 근거로 다시 써보기(발송 없음) — 의장 이름·날짜 확인
- [x] SERVICE_RULES §64
