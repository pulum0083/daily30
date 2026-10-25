# 체크리스트 — 월봉 5개월선 안착 종목 코너

설계 `plan.md`.

## 1. 스크리닝
- [x] `scripts/monthly_ma5.py` — 순수 함수(월말 시리즈·5개월선·연속 개수·판정) + CLI
- [x] 공식 종가 교정 경로(`official_day_rows`) 사용, pin 지원
- [x] 월초(이번 달 행 없음) 처리
- [x] `data/monthly_ma5.json` 저장 + `.gitignore`
- [x] 46종목 중 조회 실패 종목 수를 기록하고 전부 실패면 파일을 쓰지 않음

## 2. 백테스트 수치
- [x] `scripts/backtest_monthly_ma5.py` 작성
- [x] `scripts/config/monthly_ma5_backtest.json` 생성·커밋

## 3. 렌더
- [x] `generate_html.build_monthly_ma5()` — 스냅샷 1순위, 날짜 대조
- [x] `sections/monthly_ma5.html`(A안), `style.css`, `_modals.html`의 `ma5m-modal`
- [x] `kospi.html` include 교체, `config/kospi.json`
- [x] 종목 0개면 섹션 생략

## 4. 상승 모멘텀 제거(코스피)
- [x] `fetch_data.py` 후보 스크리닝 제거
- [x] `call_claude.py` 코스피 프롬프트 정리 + 응답의 `stock_picks` 버림
- [x] `generate_html.py` 코스피 분기 `stock_picks` 제거
- [x] 텔레그램 링크 문구

## 5. 워크플로·문서
- [ ] `daily_report.yml` kospi 잡에 스크리닝 스텝
- [ ] `SERVICE_RULES.md` 새 절, `CLAUDE.md` 흐름 갱신

## 6. 검증
- [ ] 단위 테스트(`test_monthly_ma5.py`) + 제거 회귀 테스트
- [ ] 전체 `pytest scripts/` + `node --test`(api) 통과
- [ ] 실데이터로 스크리닝 실행 → 프로토타입 결과와 일치 확인
- [ ] 10/23 스냅샷으로 렌더해 브라우저 확인(커밋 안 하는 경로)
