# 체크리스트 — 홈 실적 캘린더 + 밸류에이션 상세 이전

배경·근거는 [context-notes.md](context-notes.md) 참조.

## 사전 조사 (완료)

- [x] 밸류에이션 블록 제거 (커밋 966257cd — HTML·JS·CSS 69줄)
- [x] `valuation.json` 소비처가 홈 위젯 한 곳뿐임을 확인
- [x] yfinance 실적일 시간대 오차 확인 → 기각
- [x] 네이버 `irScheduleInfo` 채택 결정
- [x] 커버리지 실측 — 실적 24/46, 밸류에이션 27/46

## 1. 실적 발표 캘린더 — 수집

- [ ] `scripts/fetch_earnings_calendar.py` 작성
  - [ ] `stock_universe.json` 46종목 순회, `irScheduleInfo` 추출
  - [ ] 오늘(KST) 이후 일정만 채택, 날짜순 정렬
  - [ ] `irScheduleDday`는 저장하지 않음 (§20 — 상대 라벨 금지)
  - [ ] 개별 종목 실패는 건너뛰고 계속 (전체 실패 아님)
  - [ ] `web/data/earnings-calendar.json` 원자적 쓰기
  - → 검증: 실행 후 24건 내외, 전부 오늘 이후 날짜
- [ ] `scripts/test_fetch_earnings_calendar.py` — 과거 일정 배제·정렬·결손 처리
  - → 검증: `python3 scripts/test_fetch_earnings_calendar.py` 통과

## 2. 실적 발표 캘린더 — 화면

- [ ] `web/stocks/index.html`에 블록 마크업 추가 (밸류에이션이 있던 자리)
- [ ] `web/assets/stocks-home.js`에 로더·렌더러 추가
  - [ ] D-day를 렌더 시점에 계산 (오늘/내일/N일 후)
  - [ ] 날짜별 그룹핑
  - [ ] 클릭 시 `goStock(code)`
  - [ ] 일정 0건이면 블록 숨김
  - [ ] `updated_at` 신선도 가드
- [ ] `web/assets/stocks-home.css`에 스타일 추가
  - → 검증: 브라우저에서 24건 렌더·콘솔 오류 0·블록 숨김 동작

## 3. 밸류에이션 상세 이전

- [ ] `generate_html.py`에 `_valuation_for_code(code)` + 신선도 가드
- [ ] `scripts/templates/stocks/detail.html`에 섹션 추가
- [ ] 데이터 없는 19종목은 섹션 생략 확인
  - → 검증: `generate_html.py --stocks`로 3종목 생성 후 HTML 확인

## 4. 파이프라인

- [ ] `.github/workflows/daily_report.yml`에 캘린더 수집 스텝 추가
  - [ ] `timeout-minutes: 5` + `continue-on-error: true` (§21)
  - [ ] `git add`에 `web/data/earnings-calendar.json` 포함
  - → 검증: YAML 파싱 통과

## 5. 마무리

- [ ] 전체 테스트 실행
- [ ] 로컬 프리뷰에서 홈·상세 최종 확인
- [ ] 커밋 (수집 / 화면 / 상세 이전 / 워크플로우 단위로 분리)
