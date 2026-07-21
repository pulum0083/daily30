# 체크리스트 — 홈 실적 캘린더 + 밸류에이션 상세 이전

배경·근거는 [context-notes.md](context-notes.md) 참조.

## 사전 조사 (완료)

- [x] 밸류에이션 블록 제거 (커밋 966257cd — HTML·JS·CSS 69줄)
- [x] `valuation.json` 소비처가 홈 위젯 한 곳뿐임을 확인
- [x] yfinance 실적일 시간대 오차 확인 → 기각
- [x] 네이버 `irScheduleInfo` 채택 결정
- [x] 커버리지 실측 — 실적 24/46, 밸류에이션 27/46

## 1~2. 실적 발표 캘린더 — 철회 (2026-07-21)

구현·검증까지 완료했으나(58502ac7·3e386cc7) 사용자가 화면을 보고 기각. 코드·데이터·워크플로우 항목 전부 제거함. 근거는 [context-notes.md](context-notes.md) "안 1 철회" 참조.

- [x] ~~`scripts/fetch_earnings_calendar.py` 작성~~ → 제거
- [x] ~~`scripts/test_fetch_earnings_calendar.py`~~ → 제거
- [x] ~~홈 블록 마크업·JS·CSS~~ → 제거
- [x] 제거 후 브라우저 재검증 — 콘솔 오류 0, 블록 완전히 사라짐 확인

## 3. 밸류에이션 상세 이전

- [ ] `generate_html.py`에 `_valuation_for_code(code)` + 신선도 가드
- [ ] `scripts/templates/stocks/detail.html`에 섹션 추가
- [ ] 데이터 없는 19종목은 섹션 생략 확인
  - → 검증: `generate_html.py --stocks`로 3종목 생성 후 HTML 확인

## 4. 마무리

- [ ] 전체 테스트 실행
- [ ] 로컬 프리뷰에서 상세 페이지 최종 확인
- [ ] 커밋 (밸류에이션 이전 / 캘린더 제거 단위로 분리)
