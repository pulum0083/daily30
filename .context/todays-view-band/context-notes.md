# 지금 코스피 밴드 — 컨텍스트 노트

## 조사 결과 (2026-07-11)
- _live_scoreboard.html은 main 포함 어디에도 include 안 됨 → initLiveScoreboard/
  initLiveMarketPanel은 현재 죽은 코드(사이드바 market_data.html은 서버 스냅샷만, 폴링 X).
- 따라서 밴드는 기존 활성 컴포넌트 대체가 아니라 본문 최상단 신규 라이브 컴포넌트.
- initLiveMarketPanel(main.js ~1589)은 사이드바 #market-data-panel DOM에 강결합
  (.panel-header/.mkt-list). 밴드는 .nowband 별도 마크업 → 폴링/fetch/스파크 로직만 재사용.

## 결정된 접근
- 앞선 슬라이스(2~5)와 달리 라이브 JS·main.js 수정. 머지 시 라이브 동작 변경.
- 유저 합의: "저위험 먼저, 밴드는 마지막"(AskUserQuestion). 저위험 슬라이스 2~5 완료.

## 슬라이스 진행 상황 (worktree-todays-view-frontend, 미푸시)
- 슬라이스1 fe1bf71c: todays_view 프론트 렌더
- 슬라이스2 3ebbac68: 예측 게이지 → 참고 지표 스트립 강등(코스피 한정)
- 슬라이스3 d7f53478: 사이드바 텔레그램 subcard + 월배당 계산기 링크
- 슬라이스4 f9b0085c: 종목 픽 이름 → 영구 상세 페이지 링크(존재 게이트)
- 슬라이스5 27e4c38e: 텔레그램 알림 제목 가변화(어제 결과 + 오늘 한 줄)
- 슬라이스6(밴드): 이 계획 — 미착수

## 기술 해소 (2026-07-11, 구현 착수 전 조사 완료)
- /api/kospi-live → {price, changePct} (코스피 지수, 10초). initLiveScoreboard fetchKospi 참고.
- /api/market → {kosdaq:{price,changePct}, kospi200:{price,changePct}, forex:{price,changePct},
  investor:{foreign,institution,individual}} (60초, 수급 억 단위). initLiveMarketPanel applyData 참고.
- 장중 이슈 → /data/kospi-news-{date}.json (fallback kospi-news-live.json), history를 MARKET 슬롯 필터.
- 스파크라인: 기존 drawSparkline(id, data, hoverIdx)는 canvas 기반. 밴드도 <canvas>+drawSparkline
  재사용 권장(프로토타입 SVG 대신). 누적: sessionStorage('mkt-spark-v1') 패턴 재사용. 코스피 지수 누적.
- @keyframes pulse는 style.css에 없음 → .nb-dot용으로 추가 필요.
- CSS 변수 매핑: 프로토타입 --dim → style.css엔 없음 → --muted로 (슬라이스1~5와 동일 규칙).
- 상태 판정 함수는 initLiveScoreboard/initLiveMarketPanel의 kstNow/isPreOpen/isMarketHours/
  isAfterMarket/mktIsPast(URL 날짜 비교) 로직 그대로 재사용.

## 결정 반영해 해야 할 구조 변경
- build_market_items(generate_html.py:354) kospi spec에서 ("원/달러","usdkrw") 제거(밴드로 이관).
- kospi.html: {% include "sections/_issue_briefing.html" %} 제거(밴드가 이슈 흡수).
- kospi.html: 밴드 include를 accordion-body__inner 최상단(todays_view 위)에 추가.
- base.html: initNowBand() 호출 추가(기존 initLiveScoreboard/initLiveMarketPanel 호출은
  죽은 상태 유지 or 제거 검토).

## 검증 한계 (정직하게)
- 라이브 폴링은 실제 /api 엔드포인트(Vercel serverless) 필요 → 로컬 정적 렌더로 검증 불가.
- 방법: window.fetch를 mock해 /api/kospi-live·/api/market 샘플 JSON 주입, 밴드 DOM 채워지는지
  + 상태별(pre/live/after/past) 렌더 확인. 슬라이스2~5의 정적 렌더 검증보다 무겁다.
