# 체크리스트 — 미국 이슈 결과 스코어보드

설계 `plan.md`. **구현 완료(2026-09-06)** — 배포 전 확인만 남았다.

## 1. 채점 스크립트

- [x] `scripts/score_us_issues.py` 신규 — 파일 첫 줄 한국어 역할 주석
- [x] 대상 세션 = `session_label.prev_us_session(브리핑날짜)`
- [x] `web/briefings/{세션날짜}/us/analysis_snapshot.json` 의 `issues` 로드
- [x] **날짜 고정 조회** — 해당 ET 세션 봉 선택, 직전 봉과 비교. 없으면 티커 버림(최신 봉 폴백 금지)
- [x] 프록시 화이트리스트("지수 전반" 계열 → S&P500). 롱테일 라벨은 매핑하지 않음
- [x] 판정 배지·결과 한 줄 조립(전부 결정론)
- [x] 중복 제거 — 같은 프록시·같은 방향 두 번째부터 결과줄 생략
- [x] 측정 불가 카드 생략, 남는 카드 0이면 빈 결과
- [x] `data/us_issue_results.json` 저장(`us_session_date`·`scored_at`·`cards`)
- [x] `.gitignore` 에 추가(스냅샷에 흡수되는 실행 중간물)

## 2. 렌더

- [x] `generate_html.build_us_issue_results(analysis, target_date)`
- [x] 우선순위 — 스냅샷 `analysis["us_issue_results"]` → 없으면 데이터 파일 → `analysis` 에 주입
- [x] 날짜 게이트 — `us_session_date != prev_us_session(대상일)` 이면 버림
- [x] `scripts/templates/sections/us_issue_results.html` 신규(항목 0이면 섹션 없음)
- [x] `kospi.html` 에 include, 위치는 근거 아래·예측 위
- [x] `web/assets/style.css` 에 `.res-tk` `.verdict` `.reshead` `.proxy-note` `.sec-foot` 추가
- [x] 라이트·다크 양쪽 확인

## 3. us_issues 제거

- [x] `call_claude.py` 412 필수 필드 목록에서 제거
- [x] `call_claude.py` 443 출력 예시에서 제거
- [x] `call_claude.py` 493 필드 설명 제거
- [x] `call_claude.py` 498 §23 빅테크 룰 → `key_drivers`·`todays_view` 를 가리키도록 수정(룰 유지)
- [x] `generate_html.py` 226 `_us_issues_label` → `_prev_us_session_label`로 개명·재사용 (제거하지 않음)
- [x] `generate_html.py` 238~254 `build_us_issues` 제거
- [x] `generate_html.py` 596 `ctx.update` 제거
- [x] `templates/sections/_us_issues.html` 삭제
- [x] `templates/briefings/kospi.html` 38행 include 제거
- [x] `validate_analysis.py` 954 `_SUPERLATIVE_LIST_FIELDS` 에서 `"us_issues"` 제거
- [x] `scripts/test_build_us_issues.py` 삭제
- [x] `test_index_superlatives.py` `test_event_tense.py` fixture를 살아 있는 필드로 교체
- [x] `grep -rn us_issues scripts/ web/assets/` 로 잔존 참조 0 확인(발행본 제외)

## 4. 워크플로우

- [x] `daily_report.yml` `kospi-briefing` 잡, `fetch_data.py` 직후 스텝 추가
- [x] `continue-on-error: true` + `timeout-minutes: 5`
- [x] 커밋 스텝이 `data/us_issue_results.json` 을 끌고 들어가지 않는지 확인(§18)

## 5. 테스트

- [x] `scripts/test_us_issue_scoring.py` — 판정·결과줄·중복 제거·카드 생략·날짜 게이트·폴백 금지
- [x] 9/3·9/4 실측 리플레이 케이스
- [x] `python3 -m pytest scripts/ -q` 전체 통과
- [x] `node --test` 전체 통과(회귀 없음 확인)

## 6. 문서

- [x] `docs/SERVICE_RULES.md` 에 새 섹션 규칙 추가(§ 신규) — 채점 규칙·프록시·실패 모드
- [x] `us_issues` 제거를 §23 항목에 반영(빅테크 룰의 무대 이동)
- [x] `context-notes.md` 에 구현 중 결정 계속 기록

## 7. 배포 후 확인 (아직 못 함)

- [ ] 07:25 실행에서 대상 세션 일봉이 실제로 확정돼 있는지 (며칠 로그 관찰)
- [ ] 섹션이 매일 정상 노출되는지 — 매일 빠지면 분봉 기반 후속 필요
- [ ] 커밋 스텝이 채점 결과 파일을 끌고 가지 않는지 실제 잡에서 재확인
