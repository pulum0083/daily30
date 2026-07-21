# 특이 신호 수정 체크리스트 (2026-07-21)

문제: `/api/signals`가 3건만 반환하고 그 3건은 전부 `turnover`(기계적 상위 3) — 실제 신호 0건.
게다가 그 상위 3종목이 거래대금 단위 버그로 **틀린 종목**이었다.

## ① 거래대금 단위 버그 (실데이터 오류 — 최우선)

- [x] `api/signals.mjs` 종목 `amount`를 `pollOne`의 `price * vol`로 계산
- [x] 종목용 `amountOne()` 호출 제거 (ETF는 유지 — 전 16종목 백만원 단위 일관 확인됨)
- [x] 회귀 테스트: 코스닥 종목이 1000배 뻥튀기돼도 상위 3에 오르지 않음
- [x] 실측 검증: 상위 3 = SK하이닉스·삼성전자·현대차

## ② 상승장 카테고리 신설

- [x] `counter_down`(역행 하락) — 시장 상승 중 지수 대비 3%p 이상 언더퍼폼 + 실제 하락(하한선)
- [x] `surge_up`(거래량 급증 + 급등) — `mult >= 1.5 && pct >= +3.0`
- [x] `SIGNAL_META` · `SIGNAL_SCORE` · `whyText()` 3곳 동시 갱신
- [x] `vol_surge` 라벨을 `거래량 급증 · 급락`으로 명확화 (기존 `거래량 급증`은 급락 조건을 숨김)
- [x] 테스트: 상승장 발화 / 하락장 미발화 / 하한선 미달 미발화

## ③ 장중 거래량 배수 정규화

- [x] `_market-calendar.mjs`에 `sessionProgressAt(min)`(순수) + `krSessionProgress()` 추가
- [x] `classifyStock`이 `opts.progress`로 분모 보정 (`vol_avg20 * progress`), 기본값 1
- [x] `VOL_PROGRESS_FLOOR = 0.2` — 개장 직후 폭발적 배수 방지 (보수적으로 동작)
- [x] 테스트: 09:00 0 / 12:15 0.5 / 15:30 이후 1 / 휴장 1

## ④ 장중 수급 신호 (전일 기준)

- [x] `trendOne` fetch를 `phase === 'closed'` 게이트 밖으로
- [x] `classifySupply(trend, { suffix })` — 장중이면 배지에 ` (전일 기준)` 부착
- [x] ⚠️ 네이버 trend API는 장중에 당일 행을 주지 않음(최신=전일). "잠정"이 아니라 "전일 기준"이 정확
- [x] 테스트: suffix 부착/미부착

## ⑤ 화면·문서

- [x] `web/stocks/index.html` 도움말 툴팁 2곳(홈·전체 화면) 신규 카테고리 반영
- [x] 장중 거래량 배수가 "페이스 기준"임을 툴팁에 명시
- [x] `docs/STOCKS_SERVICE_RULES.md`에 단위 버그 재발 방지 규칙 기록

## 검증

- [x] `node --test api/*.test.mjs` 전체 통과
- [x] 로컬에서 수정된 코어로 오늘 실데이터 재계산 → 신호 건수·종목 확인
- [x] 커밋 (푸시는 사용자가 일괄)
