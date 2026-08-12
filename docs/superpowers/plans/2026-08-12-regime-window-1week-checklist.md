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

## 후속 판단이 필요한 항목 (사용자에게 보고함)

- [ ] "정점 +0.0% → 지금 −3.8%" 문구 — 1주일 창에서는 `peak`이 0.0인 경우가 흔하다
      (창 시작 대비 누적이라 주 내내 못 오르면 러닝 정점이 0). 수치는 정확하지만 읽히지 않는다.
      문구 조정은 사용자 결정 대기.
- [ ] 스파크라인 점이 26개 → 6개로 줄어 점 사이 간격이 시각적으로 넓어졌다. 원래 지적이
      곡선 쪽이었다면 역효과 — 사용자 확인 대기.

## 환경 메모

`node --test web/assets/` (디렉터리 모드)는 이 환경(Node v24.14.0)에서 `MODULE_NOT_FOUND`로
실패한다. 이번 변경과 무관한 기존 현상이며, 파일별로 돌리면 전부 통과한다.
