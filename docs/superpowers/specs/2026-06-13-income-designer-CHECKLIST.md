# 배당 인컴 설계기 — 체크리스트

## 데이터 타당성 (완료 — 2026-06-13)
- [x] 네이버 etfAnalysis에 분배 데이터 존재 확인 (`dividend` 필드)
- [x] 분배율 TTM·주당분배금·분배 월·연 횟수 가용 확인
- [x] 총수익(returnPerformanceList) vs NAV성과(navPerformanceList) 분리 확인
- [x] **가격침식 프록시 = 총수익 − 분배율 산출 가능 확인** (정직 레이어 해자)
- [x] 실증: TIGER 미국30년국채커버드콜 분배율 13% vs 총수익 1.85% → 침식 −11%
- [x] taxationTypeCode 매핑 확인 (1=국내주식형 / 2=배당과세형 / 4=해외주식형)
- [x] AUM(marketValue) 1조+ 필터용 확인
- [x] **한계 확인**: ROC 명시 분해 ✗(프록시 대체), 분배금 시계열 ✗(네이버 404, v2)

## v1 파이프라인 (완료 — 2026-06-13, build_income_etfs.py)
- [x] 유니버스 수집 — 이름 패턴 + dividendYieldTtm>0 + AUM 임계 필터
- [x] 유니버스 분포 확인 — 1조+ 8개뿐 → **7천억+ 20개로 확정**(사용자 결정)
- [x] 건전성 뱃지 분류 함수 (건전/주의/원금성) + 단위 테스트 (test_build_income_etfs.py, 5 passed)
- [x] 가격침식 프록시 = Y1총수익 − 분배율. **필드 검증**: returnPerformanceList.Y1 ≈ navPerformanceList.Y1 일치 → NAV 기준 총수익 확정 (themeReturns.returnRate1y는 별개라 미사용)
- [x] 상장 1년 미만 → low_confidence 플래그 (is_new_fund)
- [x] 산출 data/income_etfs.json 출력 (20종, health: ok 14·warn 2·bad 2·None 2)
- [~] 인컴 목표 → 필요 원금 역산: 프로토 시뮬레이터에 구현. 분배 월 평탄화는 v1 데이터(dividend_months) 보유, UI 미반영
- [x] 종합과세 2천만원 임계 경고 (프로토 simOut)
- [ ] **한계 — 강세장 침식 프록시 둔감**: 최근 1년 강세로 주식형 커버드콜 총수익이 +89~177%로 찍혀 대부분 ok 판정. 진짜 원금성은 국채 커버드콜 2종만 bad. 임계 보정 또는 분배율-vs-가격만 별도 지표 검토 (CONTEXT-NOTES 발견 4)
- [ ] **데이터 의심값**: 주식형 커버드콜 Y1 +177%/+174% 등 비현실적. navPerf와 일치하나 신생·저가상장 왜곡 가능. v2에서 가격 시계열 교차검증

## UI 프로토타입 (완료 — 2026-06-13, flow-clickable.html)
- [x] **피벗 결정**: 보유-입력 트래커 접고 랭킹(히어로)+단발 시뮬레이터(서포트). CONTEXT-NOTES 결정 4.
- [x] 홈 HOT 카드 → 배당 인컴 설계기 destination (#income)
- [x] 히어로 랭킹: ETF 카드 + 건전성 뱃지(건전/주의/원금성) + 침식 프록시 + 정렬 토글
- [x] 서포트 단발 시뮬레이터: 보유(KR+해외) 입력 → 인컴·원금성 경고·종합과세·갭 메우기
- [x] 정직 배너 + 면책 문구 (예상치·투자권유 아님)

## UI 본체 연동 (stock-page-engine 본체 구현 시)
- [ ] 프로토타입을 실제 종목 페이지 엔진 템플릿에 이식
- [ ] income_etfs.json 실데이터 바인딩 (현재 프로토는 하드코딩 샘플)

## 운영 통합
- [ ] kospi-close job에 스텝 추가 (또는 주1회 — 분배는 자주 안 바뀜)
- [ ] SERVICE_RULES 1줄 등재

## v2 (후속)
- [ ] 분배금 per-payment 시계열 (세이브로/운용사) → 정확한 월별 인컴 캘린더
