# 체크리스트 — 09:00 장중 이슈 어제 기사 사고

- [x] 원인 확정 — 09:00 발행분이 어제 발행분과 동일 서사임을 데이터로 대조 → 검증: `kospi-news-2026-07-29.json` history와 제목 비교
- [x] A. MARKET 슬롯 장 개시 시각 게이트 추가 (`pub_time >= 09:00`) → 검증: 단위 테스트
- [x] B. 어제 발행분 타이틀을 dedup 목록에 합침 → 검증: 단위 테스트 + 저장 `seen_titles`에 어제분이 섞이지 않음
- [x] 테스트 작성·통과 (`scripts/test_market_session_gate.py`) → 검증: `pytest` 전건 통과
- [x] 기존 회귀 테스트 통과 → 검증: `pytest scripts/test_bump_latest_time.py scripts/test_fetch_news_dedup.py`
- [x] 오늘자 잘못된 09:00 항목 제거 → 검증: `kospi-news-2026-07-30.json`·`kospi-news-live.json`에서 해당 history 항목 부재
- [x] 현재 시각으로 재수집해 실제 장중 이슈로 교체 → 검증: 새 항목의 `pub_time`이 09:00 이후, 어제 서사와 무관
- [x] 커밋 → 검증: 수정 커밋 / 데이터 커밋 분리
- [x] 프로덕션 반영 확인 → 검증: `doubleshot.space/data/kospi-news-live.json`의 `updated_at`·타이틀 대조
