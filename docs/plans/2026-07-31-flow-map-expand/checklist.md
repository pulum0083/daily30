# 체크리스트 — 자금 지도 확장 패널 (C-2)

## 1. 데이터 (`scripts/build_etf_flows.py`)

- [x] `daily_by_theme()` 신설 — 윈도우 내 연속 쌍 차분, **최종 NAV** 기준, 중간 결측은 carry-forward
- [x] `aggregate_by_theme()`에 `gross`(|flow| 총합) 추가
- [x] `main()`에서 `daily`를 테마에 병합해 출력
- [x] 검증: 일별 합 == 누적 (실히스토리로 확인)

## 2. 테스트 (`scripts/test_build_etf_flows.py`)

- [x] 일별 합 == 누적 (telescoping)
- [x] 중간 스냅샷 결측 시 carry-forward 동작
- [x] `gross >= |net|`, 집중도 ≤ 100%
- [x] 히스토리 부족(기준일 없음) → `daily: []`
- [x] 기존 6개 테스트 통과 유지

## 3. 화면 (`web/assets/stocks-home.js` · `stocks-home.css`)

- [x] 일별 0축 막대 (유입 위 / 유출 아래)
- [x] 집중도 한 줄 + 게이지 + 내부이동 배수
- [x] 유입/유출 세로 그룹 + 그룹 소계, 브랜드 접두어 유지
- [x] `daily`/`gross` 없으면 해당 블록 생략 (하위호환)
- [x] 확장 애니메이션(height 트랜지션)이 늘어난 높이에서도 정상 동작

## 4. 검증

- [x] `python3 scripts/test_build_etf_flows.py`
- [x] `node --test web/assets/*.test.mjs` (40건 유지)
- [x] `npx eslint@9 web/assets/ api/` — 0 errors
- [x] 브라우저: 혼재 테마(반도체) 종목명 안 잘림
- [x] 브라우저: 구버전 JSON(daily 없음)으로 degrade 확인
- [x] 커밋
