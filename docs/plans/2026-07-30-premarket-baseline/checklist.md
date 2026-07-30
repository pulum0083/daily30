# 프리장·애프터장 등락률 기준가 통합 — 체크리스트

## 배경 (한 줄)

`/api/intraday`가 프리장·애프터장에 **한 세션 과거** 종가를 기준가로 써서 미국 상세 페이지 등락률이 전부 틀렸다. `/api/stocks-live`는 정상이라 같은 종목이 홈과 상세에서 다른 값을 보였다.

## 작업

- [x] 실사고 픽스처 확보 (2026-07-30 프리장 DRAM meta) → verify: `regularMarketPrice=44.85`, `chartPreviousClose=47.77` 확인
- [x] `api/_us-session.test.mjs` 작성 — 4개 세션(pre·open·post·closed) × 기준가 선택 + 실사고 리플레이 → verify: 모듈 미구현이라 실패하는 것 확인
- [x] `api/_us-session.mjs` 신설 — `usSessionState()` / `usBaseClose()` (stocks-live의 검증된 로직을 그대로 추출) → verify: 위 테스트 통과
- [x] `api/stocks-live.mjs` — 인라인 판정을 공용 모듈 호출로 교체 → verify: 기존 동작 불변(프리장 DRAM -1.2%대 유지)
- [x] `api/intraday.mjs` — 응답에 `baseClose`·`session` 추가 (`prevClose`는 하위호환 유지) → verify: 프리장에 `baseClose=44.85`
- [x] `web/assets/stocks.js` — 헤더 등락률 기준가를 `d.baseClose` 우선으로 교체 → verify: 상세 헤더가 홈과 같은 값
- [x] 전체 테스트 실행 → verify: `node --test api/*.test.mjs web/assets/*.test.mjs` 통과, `python3 -m pytest scripts/ -q` 회귀 없음
- [x] SERVICE_RULES.md §30 방지 룰 추가 → verify: 재발 시 진단 순서까지 기재
- [x] 커밋 · 배포 · 라이브 검증 → verify: 상세 페이지와 홈의 등락률이 일치

## 성공 기준

프리장 중 같은 종목을 홈과 상세에서 각각 열었을 때 **등락률이 일치**하고, 그 값이 `(프리장 실체결가 − 직전 정규장 종가) / 직전 정규장 종가`와 같다.
