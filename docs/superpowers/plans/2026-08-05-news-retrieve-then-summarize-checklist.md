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

## 1단계 — 공용 모듈 추출 (동작 변화 없음) ✅ 2026-08-04
- [x] `scripts/news_sources.py` 신설
- [x] `fetch_rss` / `GN_KR` / `GN_EN` / `parse_rss_datetime` / `clean_title` 이동
- [x] `resolve_gnews_url` / `extract_resolved_url` 이동
- [x] `parse_real_published_at` / `fetch_msn_published_at` / `verify_real_published_at` 이동
- [x] `is_dup_title` / `title_kw` / `title_bigrams` 이동
- [x] 두 소비처를 별칭으로 교체 (기존 private 이름 유지 → 호출부·monkeypatch 테스트 무변경)
- [x] 내 변경이 만든 고아 import 제거 (`ET`, `parsedate_to_datetime`)
- [x] verify: 전체 596건 통과 + 실 네트워크 스모크(30건 수집 → yna.co.kr 리졸브 → 발행일 05:10 검증)
- [x] 커밋

**남긴 것(의도적)**: `fetch_stock_news.py`의 `_resolve_gnews_url`은 반환 타입이 다르고
(`(url, page)` 튜플), `fetch_domestic_issues.py`의 `_parse_rss_datetime`도 별도다.
지금 통합하면 스테이지 2와 무관한 회귀 위험만 커진다 — 4단계 이후 별건으로 정리한다.
`_clean_title`은 두 소비처의 동작이 실제로 달라(괄호 태그 제거 여부) 파라미터로 보존했다.

## 2단계 — 미국 브리핑 수집기 전환 ✅ 2026-08-04
- [x] 실패 테스트 먼저 — `test_rss_news_selection.py` 15건, 구현 전 전부 실패 확인
- [x] US RSS 쿼리 세트 정의 (§19 기준: 실적·프리마켓 반응·반도체·매크로, 한/영 6개)
- [x] `fetch_news.py --source rss` 경로 구현 (`fetch_and_summarize_rss`, us 한정)
- [x] 인덱스 참조 프롬프트(`_articles_prompt_block`) + 범위 검증 게이트(`_resolve_selection`)
- [x] 목록 밖 숫자·기업 검출 게이트(`_unsourced_claim`) → verify: §31 마이크론 리플레이로 구조적 배제 확인
- [x] 원문 URL 리졸브 + 실제 발행일시 검증(`_attach_verified_sources`) — 검증 실패 항목은 버림
- [x] 라이브 1회 실행 → verify: 4개 선택 중 1건(맥도날드, 발행일 검증 실패)은 정상 제외,
      3건은 실제 원문 URL + 발행일시 확인(Fortune 08-03 16:03 UTC, 블루밍비트·매일일보 08-04)
- [x] 전체 611건 통과. 커밋·푸시

**RSS 경로가 만드는 것**: `catalysts`(문자열, 기존 계약 유지) + `catalyst_sources`
(url·source·published_at — 3단계가 소비할 원자재). `key_indicators`·`headlines`는 비운다 —
이 경로는 "사건 → 영향" 서사만 담당하고, 지표류는 fetch_data.py 실측이 이미 맡는다.

**아직 파이프라인에 배선 안 됨**: `daily_report.yml`의 us-briefing job은 여전히
`fetch_news.py --type us`(기존 gemini 경로)를 호출한다. `--source rss`로 바꾸는 건
런타임 코드 변경 없는 원라이너지만, 정규 발행에 앞서 수동 실행으로 하루 더 관찰한다.

## 3단계 — 출처 표시
- [ ] catalyst에 `url` 보존 (`fetch_news.py` → `call_claude.py` → `generate_html.py`)
- [ ] 이슈 카드에 출처 링크 렌더 → verify: 브라우저에서 링크 클릭해 실기사 도달
- [ ] 커밋

## 4단계 — 확대
- [ ] US 1주 운영 관찰 (수집 실패율·이슈 품질·오제거 여부)
- [ ] `kospi` 전환 → verify
- [ ] `kospi-close` 전환 → verify
- [ ] SERVICE_RULES 갱신 (§10 RSS 구조 설명을 fetch_news까지 확대)
