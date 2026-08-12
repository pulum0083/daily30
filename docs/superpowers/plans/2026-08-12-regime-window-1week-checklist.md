# 체크리스트 — 국면 판정 창 1주일 전환

- [x] `market_regime_core.py` 상수 교체 (WINDOW_DAYS 5 / COOL -2.5 / HIGH -0.5)
      → 검증: `pytest scripts/test_market_regime_backtest.py -q` **4개 통과 (가드 수정 없이)**
- [x] `build_market_regime.py` 스파크 샘플 간격을 WINDOW_DAYS에서 유도
      → 검증: `SPARK_STRIDE=1`, 재빌드 후 `spark` 6점·일별 확인. 126일이면 stride 5·26점(기존 유지)
- [x] `test_market_regime_core.py` 임계값 하드코딩 제거(상수 참조)
      → 검증: `pytest scripts/test_market_regime_core.py -q` 37개 통과
- [x] `stocks-home.js` "6개월" 3곳 → `window_days` 유도 라벨(`winLabel()`)
      → 검증: `node --test web/assets/market-regime.test.mjs` 14개 통과(라벨 테스트 3개 신규)
- [x] `index.html` 주석 갱신 · 워크플로우 스텝명 · 에셋 캐시 버전 bump(js v12)
      → 검증: `grep "6개월"` — 소스에 0건(테스트 픽스처 제외)
- [x] 실데이터 재빌드 (`python3 scripts/build_market_regime.py`)
      → 검증: `window_days: 5`, 22/22 티커 수집, headline 정상 생성
- [x] 브라우저 확인 (로컬 `:8792/stocks/`)
      → 검증: "최근 1주일 · 08/11 기준" · "최근 1주일 누적 기준" · "1주일 최고" · 스파크 6점
- [x] 전체 테스트 스위트
      → 검증: `pytest scripts/ -q` **718개 통과** · JS 파일별 **148개 통과**

## 후속 조정 (사용자 요청으로 반영 완료)

- [x] "정점 +0.0% → 지금 −3.8%" → **"1주일 고점 대비 −3.8%"**. 누적이 창 시작 기준이라 창이
      짧으면 러닝 정점이 0.0인 경우가 흔하다(7개 중 3개). gap 한 값은 어떤 창 길이에서도
      같은 의미로 읽힌다. '뜨는 중'은 기존 '누적 +X%' 유지 — 두 컬럼이 각각 낙폭·성과를 말한다.
      → 검증: JS 테스트 `'식는 중' 카드는 고점 대비 낙폭 한 값으로 말한다`
- [x] 스파크라인을 2패스 렌더로 교체. `preserveAspectRatio="none"` + 고정 viewBox 200×34가
      **가로 1.46배·세로 0.82배 비균등 확대**를 만들고 있었다(stroke 2px → 가로 2.9px·세로 1.6px).
      DOM 삽입 후 실제 픽셀 폭을 재서 viewBox를 맞추고, 관측점이 10개 이하일 때 점을 찍어
      '성긴 선'이 아니라 '일별 관측치'로 읽히게 했다.
      → 검증: 1280px에서 viewBox 292×28 배율 1.000/1.000, 480px에서 400×28 배율 1.000/1.000,
        점 7개(관측 6 + 끝점 링). 리사이즈 재렌더 확인.
      → 주의: `paintSparks()`는 반드시 `box.style.display=''` **뒤에** 호출해야 한다
        (display:none이면 clientWidth가 0이라 폴백 폭으로 그려진다). 구현 중 실제로 밟은 버그다.

## 환경 메모

`node --test web/assets/` (디렉터리 모드)는 이 환경(Node v24.14.0)에서 `MODULE_NOT_FOUND`로
실패한다. 이번 변경과 무관한 기존 현상이며, 파일별로 돌리면 전부 통과한다.
