# 체크리스트

## 섹터 거래대금 가중
- [x] `_signals-core.mjs sectorAverages()` — `wavg` 추가, amount 없으면 avg 폴백
- [x] 테스트 3건 추가 (실사고 리플레이·부분 amount·0/음수 amount)
- [x] `stocks-home.js secBuildSectorData()` — 행별 dvol + wavg
- [x] `sbxSectorStat()` 폴백 경로도 가중 계산 + `sbxAvgOf()` 헬퍼로 표시부 통일
- [x] 섹터 상세 KPI(`sec-avg`)도 같은 기준 사용 — 칩과 어긋나지 않게
- [x] 라벨 "섹터 평균" → "거래대금 가중" (2곳)

## 홈 정리
- [x] `#income` HTML 블록 제거 (5,333 bytes)
- [x] 인컴 전용 JS 제거 (17,216 bytes, 287줄) — 하드코딩 `INCOME_UNIVERSE` 포함
- [x] 고아 참조 0건 확인 (`goBack`은 공용이라 유지)
- [x] in-flight fetch dedupe shim (`main.js` 최상단)

## 검증 (localhost 실측)
- [x] 섹터 칩: 반도체 **+2.92%** (이전 -2.78%) · 금융 +6.06% — 주도주·코스피와 부호 일치
- [x] 배너 문구가 "금융·반도체가 방어선"으로 정정됨 (이전엔 반도체를 부진으로 분류)
- [x] `#income` 제거 확인 · 라벨 2곳 반영 확인
- [x] dedupe: 같은 URL 3회 → 네트워크 1회, 소비처 4곳 본문 정상, POST 통과
- [x] 테스트: api 91/91 · main.js 20/20 · python 705 pass

## 알려진 기존 실패 (이번 작업 무관)
`scripts/test_send_telegram_retry.py::test_admin_alert_sent_when_send_fails` —
변경 전 HEAD에서도 동일 실패. 텔레그램 발송 실패 시 관리자 알림이 호출되지 않는다(§32의
안전망이 죽어 있음). 이번 변경은 파이썬 파일을 건드리지 않았고, 별도 작업으로 다뤄야 한다.

## 보고서 수치 정정
진단 보고서의 "#income 17,217 bytes = 홈 HTML의 29%"는 **HTML 블록이 아니라
`#income` 마커 이후 파일 끝까지의 바이트**를 잰 값이었다. 실제로는
HTML 5,333 bytes + JS 17,216 bytes = 22,549 bytes였다(총량은 오히려 더 컸다).
"/api/intraday 7종목 × 2회"도 2회 로드 누적이었다 — 1회 로드 기준 낭비는 8건.
