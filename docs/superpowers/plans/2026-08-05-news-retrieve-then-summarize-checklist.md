# 체크리스트 — 뉴스 retrieve-then-summarize 전환

## 0단계 — 완료 (2026-08-04)
- [x] §31 근본 원인 규명 (방관자 티커로 stale 실적 통과)
- [x] `_earnings_subject_tickers` — 주어 기준 어닝 검증
- [x] `_drop_prev_run_echoes` — 직전 실행 목록 되뱉기 차단
- [x] `_item_text` 키 비의존화 + `_normalize_news_items` 정규화 경계
- [x] 그라운딩 신호를 게이트 이전 원본에서 측정
- [x] `_count_grounding_chunks` + 출처 0건 하드 폐기
- [x] 2026-08-04 미국 브리핑 정정·배포, 공지 게시
- [x] SERVICE_RULES §31 기록

## 1단계 — 공용 모듈 추출 (동작 변화 없음)
- [ ] `scripts/news_sources.py` 신설 (헤더 주석 한국어 1줄)
- [ ] `_fetch_rss` / `_GN_KR` / `_GN_EN` 이동 → verify: `test_fetch_news_dedup.py` 통과
- [ ] `_resolve_gnews_url` / `_extract_resolved_url` 이동 → verify: 쿼리스트링 있는 URL로 재검증(§Google News 이중 이스케이프 버그)
- [ ] `_parse_real_published_at` 이동 → verify: MSN 콘텐츠 API 경로 포함 기존 테스트 통과
- [ ] `_is_dup_title` 이동 → verify: `test_market_session_gate.py` 통과
- [ ] `fetch_news_live.py` · `fetch_ib_korea_views.py` 호출부 교체 → verify: 전체 596건 통과
- [ ] 커밋: "refactor(뉴스): RSS 수집 공용 모듈 추출"

## 2단계 — 미국 브리핑 수집기 전환
- [ ] 실패 테스트 먼저 — 목록에 없는 사건을 LLM이 반환하면 폐기되는지
- [ ] US 검색 쿼리 세트 정의 (§19 기준: 실적·프리마켓 반응·매크로)
- [ ] `fetch_news.py` RSS 경로 구현 (미국 타입 한정)
- [ ] 인덱스 참조 프롬프트 + 범위 검증 게이트
- [ ] 목록 밖 고유명사 검출 게이트 → verify: §31 사고 데이터로 리플레이
- [ ] 라이브 1회 실행 → verify: catalyst마다 실제 원문 URL이 붙는지 직접 열어 확인
- [ ] 커밋

## 3단계 — 출처 표시
- [ ] catalyst에 `url` 보존 (`fetch_news.py` → `call_claude.py` → `generate_html.py`)
- [ ] 이슈 카드에 출처 링크 렌더 → verify: 브라우저에서 링크 클릭해 실기사 도달
- [ ] 커밋

## 4단계 — 확대
- [ ] US 1주 운영 관찰 (수집 실패율·이슈 품질·오제거 여부)
- [ ] `kospi` 전환 → verify
- [ ] `kospi-close` 전환 → verify
- [ ] SERVICE_RULES 갱신 (§10 RSS 구조 설명을 fetch_news까지 확대)
