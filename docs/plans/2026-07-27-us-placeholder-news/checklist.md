# 체크리스트 — 2026-07-27 미국 브리핑 익명 플레이스홀더 날조

## 1. 조사
- [x] 발행 스냅샷에서 날조 이슈 식별 (B사·C은행·D사)
- [x] 원천 `data/news_summary_us.json` 대조 → Gemini 수집 단계 날조로 확정
- [x] 종목 픽 4건 실측 대조 (AAPL·GS·JPM·NVDA) → 전부 일치
- [x] 이슈 1·4·5의 사실 근거 실측 대조 (MU·AMAT·KLAC·LRCX / WTI·브렌트 / AAPL / 선물)
- [x] 기존 게이트가 못 잡은 이유 규명

## 2. 게이트 신설
- [x] `scripts/test_placeholder_entities.py` — 실사고 데이터 포함 테스트 먼저 작성
- [x] `fetch_news._drop_placeholder_entities()` 구현
- [x] `fetch_and_summarize`의 전 필드(catalysts·headlines·key_indicators)에 배선
- [x] `US_PROMPT` 실명 필수 지시 보강
- [x] 테스트 통과 확인 (`test_placeholder_entities.py`)
- [x] 기존 게이트 테스트 회귀 확인 (`test_search_failure_notes.py`, `test_earnings_gate.py`)
- [x] 실사고 원본 `news_summary_us.json`으로 엔드투엔드 리플레이 → 날조 4건 제거 확인

## 3. 오늘자 브리핑 정정 (surgical)
- [x] `analysis_snapshot.json` — 이슈 2·3 제거, 이슈 5 탈오염
- [x] `analysis_snapshot.json` — GS·JPM 픽 시나리오에서 "C은행" 제거
- [x] `index.html` — 동일 편집 (이슈 카드 2장 삭제, 제목·본문·시나리오 정정)
- [x] `index.html`에 `[A-Z]사|[A-Z]은행` 잔존 0건 확인
- [x] 사이드바·픽 수치는 건드리지 않음(실측 정상) 확인

## 4. 룰 반영
- [x] `docs/SERVICE_RULES.md` §25 작성
- [x] 계획·컨텍스트 노트 정리

## 5. 마무리
- [x] 커밋 (게이트 / 정정 / 룰)
- [ ] 푸시·배포 — **사용자 지시 대기**
