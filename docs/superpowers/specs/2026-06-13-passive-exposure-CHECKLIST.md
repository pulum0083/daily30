# 패시브 노출도 — 체크리스트

## 스파이크 (완료)
- [x] 데이터 소스 4종 무인증 접근 검증 (etfItemList / etfAnalysis / integration / day candle)
- [x] `build_etf_exposure.py` 스파이크 작성 + 실행
- [x] day-1 분포 확보 → 임계치 앵커 확정 (高: dov≥8 AND conc≥10%)
- [x] AND 결합 타당성 실증 (주성엔지니어링·KB금융 오탐 배제 확인)

## v1 파이프라인 (완료)
- [x] 역인덱스에서 ETF 코드 제외 (etfItemList 코드 셋으로 필터)
- [x] 뱃지 분류 함수 — 절대 AND 임계 채택(percentile 대신, 해석 가능·앵커됨)
- [x] `top_etfs` 기여 ETF 리스트를 contrib_krw 순으로 정렬·상위 5 저장
- [x] 산출 스키마대로 `data/etf_exposure.json` 출력 (coverage·thresholds·ranking·stocks)
- [x] 민감도 점수(0~100) + destination ranking 배열 (기본 정렬 = 거래일수)
- [x] ADV20 보강 K=80
- [x] 핵심 계산 단위 테스트 (parse_kor_won, classify_badge, composite_score) — 3 passed
- [x] 실패 내성: etfAnalysis 실패 ETF 스킵, 종목 보강 실패 시 지표 null
- [x] **리츠·인프라 제외** (RE_EXCLUDE) — 유동성 부재로 거래일수 폭발, 내러티브 왜곡
- [x] **cp949 인코딩 픽스** — etfItemList 레거시 엔드포인트 ETF명 깨짐 해결

## UI 연동 (다음 — stock-page-engine 본체 구현 시)
- [ ] **히어로**: "패시브 민감주" destination — 홈 프리뷰 블록(상승/하락 톱 다음, etf-divider 직전) + 전용 페이지. 기본 정렬 거래일수, 토글 3종, 섹터 쏠림 배너
- [ ] **서포트**: detail 사이드바 "이 종목을 담은 ETF" 패널 실데이터 바인딩 (PHASE 2 제거)
- [ ] 패시브 노출 뱃지 + 한 줄 요약 (인과 금지 카피)
- [ ] 면책 문구 ("주요 ETF TOP10 기준, 소수 비중 누락 가능")

## 운영 통합
- [ ] kospi-close job에 build_etf_exposure 스텝 추가 (마감 후)
- [ ] generate_html 스냅샷 커밋 패턴에 etf_exposure 포함 (오염방지)
- [ ] SERVICE_RULES에 패이프라인 1줄 등재

## v2 (후속)
- [ ] 지수 정기변경 편입/편출 캘린더 (KRX 소스 조사부터)
