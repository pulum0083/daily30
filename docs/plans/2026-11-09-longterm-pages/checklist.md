# 장기 지표 영구 페이지 2개 + 주간 장기 리포트 — 체크리스트

계획: 이미 매일 계산하는 장기 지표(코스피 체크·S&P 500 200일선)를 오래 쌓아 보여주는 영구 페이지 2개와,
토요일마다 한 번 만들고 고치지 않는 주간 장기 리포트를 만든다. 새 데이터 원천은 없다.
시안: docs/prototypes/2026-11-09-longterm-pages.html (A안·B안 반영본)

## 데이터
- [x] kospi_check: 월별 history(종가·5년 평균·거리·1년 뒤 등락·1년 안 최대 하락) 추가 — home-summary엔 넣지 않음, data/kospi_check.json에 저장
- [x] sp500_ma200: 섹터별·분포·중앙값·과열/20%↓ 수 추가, data/sp500_breadth_history.json 누적(upsert) + --backfill
- [x] 2020-08 이후 breadth history 백필해서 커밋

## 페이지
- [x] /stocks/kospi-check/ — 히어로·25년 그래프 2개·지금과 비슷했던 때(B안)·계산 방법
- [x] /stocks/sp500-200/ — 히어로·흐름 그래프·섹터·분포(지금 vs 보통)·눈여겨볼 종목(과열→위로→아래로)
- [x] /weekly/{금요일}/ + /weekly/ 목록 — 이번 주 시장(요일 계단 A안)·장기 지표 한 주 사이·월봉 5개월선·섹터
- [x] sitemap·발행 게이트 등재

## 파이프라인
- [x] kospi-close 잡: 코스피 체크 페이지 생성
- [x] us 잡: S&P 페이지 생성(브리핑 렌더 때 같이)
- [x] weekly-report.yml: 토요일 08·11·14시 KST(이미 있으면 건너뜀), 커밋 → vercel 배포 dispatch

## 검증·문서
- [x] 테스트(파이썬) + 전체 테스트
- [x] 실데이터로 세 페이지 로컬 렌더·브라우저 확인
- [x] SERVICE_RULES §82
- [ ] 홈 연결 시안(docs/prototypes)
