# 애프터장 가격 잔존 경로 감사 — 체크리스트 (2026-09-15)

## 계획

§48 이후에도 15:30 뒤 애프터장(16:00~20:00) 가격·등락률·거래량을 정규장 값처럼 쓰는 경로를 찾아,
사용자 화면·브리핑에 들어가는 것만 기존 단일 소스(`kr_official_closes.py` / `_kr-regular-session.mjs`)로 고친다.
판정 근거는 9/14 과거 데이터(1분봉·일봉 대조)와 9/15 16:04·16:15·16:40·17:37 실측이다.

## 고친 것

- [x] 일봉 거래량 → `kr_official_closes`가 정규장 1분봉 합으로 교정 + 저장소 `volumes`
- [x] `build_stocks_snapshot` — 오늘 거래량이 없으면 전날 거래량으로 미끄러지지 않게
- [x] `generate_html._naver_dated_rows` — 픽 채점·스파크라인 날짜를 공식 일봉으로
- [x] dpick — §51의 자체 거래량 합산을 `official_session()`으로 합침
- [x] `fetch_movers_why` — 15:30 뒤 `official_today()`
- [x] `api/signals.mjs` closed — `fetchLastRegularSession()`, asOf는 세션 날짜
- [x] `fetch_valuation` — 정규장 밖에선 PER = 공식 종가 ÷ EPS
- [x] 마감 잡 `kospi200_top10`·`ai_semicon_stocks` 국내 2종목 — 정규장 밖에선 `official_today()`
- [x] 각 항목 9/14·9/15 값 회귀 테스트

## 이미 처리됐거나 해당 없음

- [x] `api/vol-top.mjs`·`build_etf_exposure.py` — §52에서 삭제
- [x] 업종·급등주·dpick 수급·마감 수급 — §51
- [x] 코스피 지수·시장 폭 — 영향 없음(실측)

## 마무리

- [x] pytest 847 · api 159 · web 115 통과, eslint 오류 0
- [x] SERVICE_RULES §48 기록
- [x] 커밋(논리 단위) 6개, 17:4x 푸시
