# 체크리스트 — 행동 이벤트 수집

- [x] `stocks-home.js`에 `dsTrackEvent()` 헬퍼 추가 (`dsTrackPageview()` 옆)
- [x] `goStock()` — 차단 분기에 `stock_detail_blocked`, 진입 분기에 `stock_detail_open`
- [x] `renderSearch()` 입력 — 800ms 디바운스 후 `search`(search_term·result_count)
- [x] `main.js` — `a[href*="t.me/"]` 위임 리스너로 `telegram_click`
- [x] `stocks.js` — 종목 상세용 동일 리스너 (main.js 미로드 페이지)
- [x] 회귀 확인: `main.test.mjs` 20/20 · `api/*.test.mjs` 88/88 통과
- [x] 커밋 (푸시는 지시 대기)

## 라이브 검증 결과 (localhost:8792, 실측)

| 경로 | 결과 |
| --- | --- |
| `goStock('032830')` 차단 | `stock_detail_blocked{stock_code:032830}` **1건** · 이동 없음 · 토스트 유지 · dataLayer +1 |
| `goStock('005930')` 진입 | `stock_detail_open{stock_code:005930}` **1건**, 이동 전 동기 발생 |
| 검색 4글자 연속 입력 | `search{search_term:'삼성생명',result_count:1}` **1건** (키 입력마다가 아님 — 디바운스 정상) |
| 텔레그램 CTA (홈) | `telegram_click{link_url,page_path:'/stocks/'}` **1건** |
| 텔레그램 CTA (종목 상세) | `telegram_click{page_path:'/stocks/005930/'}` **1건** · main.js 미로드 확인 · 중복 없음 |

에셋 캐시는 `no-cache, must-revalidate`라 배포 즉시 반영된다(버전 쿼리 불필요).

## 남은 것 — 사용자 몫

`/api/visitors` 503은 이번 범위 밖이다. 시크릿이라 코드로 다루지 않는다.
살리려면 Vercel 환경변수 4개(`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/
`GOOGLE_REFRESH_TOKEN`/`GA_PROPERTY_ID`)를 직접 등록해야 한다.
다만 이건 사이드바 방문자수 위젯용이라 진단 가치는 낮다 —
"정체인가·유입이 어디로·이탈이 어디서"는 GA4 콘솔이 이미 12주치를 갖고 있다.
