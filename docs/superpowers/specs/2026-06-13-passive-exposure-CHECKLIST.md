# 패시브 노출도 — 체크리스트

## 스파이크 (완료)
- [x] 데이터 소스 4종 무인증 접근 검증 (etfItemList / etfAnalysis / integration / day candle)
- [x] `build_etf_exposure.py` 스파이크 작성 + 실행
- [x] day-1 분포 확보 → 임계치 앵커 확정 (高: dov≥8 AND conc≥10%)
- [x] AND 결합 타당성 실증 (주성엔지니어링·KB금융 오탐 배제 확인)

## v1 파이프라인
- [ ] 역인덱스에서 ETF 코드 제외 (etfItemList 코드 셋으로 필터)
- [ ] 백분위 기반 뱃지 분류 함수 (절대값 → percentile 컷)
- [ ] `top_etfs` 기여 ETF 리스트를 contrib_krw 순으로 정렬·상위 5 저장
- [ ] 산출 스키마대로 `data/etf_exposure.json` 출력 (coverage·thresholds 포함)
- [ ] ADV20 보강 K=80으로 확대
- [ ] 핵심 계산 단위 테스트 (parse_kor_won, passive_value 집계, 백분위 컷)
- [ ] 실패 내성: etfAnalysis 실패 ETF 스킵, 종목 보강 실패 시 해당 지표 null

## UI 연동
- [ ] detail 사이드바 "이 종목을 담은 ETF" 패널 실데이터 바인딩 (PHASE 2 제거)
- [ ] 패시브 노출 뱃지 + 한 줄 요약 (인과 금지 카피)
- [ ] 면책 문구 ("주요 ETF TOP10 기준, 소수 비중 누락 가능")

## 운영 통합
- [ ] kospi-close job에 build_etf_exposure 스텝 추가 (마감 후)
- [ ] generate_html 스냅샷 커밋 패턴에 etf_exposure 포함 (오염방지)
- [ ] SERVICE_RULES에 패이프라인 1줄 등재

## v2 (후속)
- [ ] 지수 정기변경 편입/편출 캘린더 (KRX 소스 조사부터)
