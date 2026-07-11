# 지금 코스피 밴드 — Stage B 슬라이스6 체크리스트

프로토타입: docs/prototypes/2026-07-11-kospi-briefing-redesign.html (① 지금 코스피 밴드)
성격: 라이브 JS 컴포넌트. 코스피 본문 최상단. 장전(정적 스냅샷)/장중(폴링) 2상태.
접근: 죽어있는 initLiveMarketPanel/initLiveScoreboard의 폴링·fetch 로직 재사용 + 밴드 DOM 신규.

## 데이터 소스 (전부 클라이언트 API — 실측)
- 코스피 지수·등락률 → /api/kospi-live (10초)
- 코스피200·코스닥·원/달러·수급(개인·기관·외국인) → /api/market (60초)
- 장중 이슈 → /data/kospi-news-{date}.json (없으면 kospi-news-live.json), MARKET 슬롯
- 스파크라인 → 인메모리 누적 + sessionStorage('mkt-spark-v1') 복원 (기존 규칙 재사용)

## 상태 규칙 (SERVICE_RULES §10 준수)
- [ ] 장전(08:50~08:59): 준비중/카운트다운. 장 전 스냅샷(지난 종가·지난 수급·밤사이 이슈) 정적 표시
- [ ] 장중(09:00~15:29): LIVE 폴링, 스파크라인 누적
- [ ] 장후(15:30~): 최종 종가 고정 표시(폴링 중단)
- [ ] 과거 브리핑(URL<오늘): 정적, 폴링 없음
- [ ] 숨김(~08:49 당일): display:none
- [ ] 주말·휴일: 자동 숨김(당일 데이터 미존재)

## 데이터 정합성 (철칙)
- [ ] 폴링 실패/미수집 영역은 수치 미표시(빈칸/섹션 생략). 이전 세션·하드코딩 값 금지
- [ ] 밤사이 이슈(SOX 등)는 서버 렌더 데이터 유무 확인 후에만 표시 — 없으면 정성 문구/생략
- [ ] 수급 표시 순서: 개인 → 기관 → 외국인 (변경 금지)
- [ ] 스파크라인 색: 상승=빨강(#E03131)/하락=파랑(#2775ED), 시초가 점선

## 구현 단계
- [x] 1. 밴드 마크업 템플릿 sections/_now_band.html (코스피 본문 최상단, todays_view 위)
- [x] 2. .nowband CSS를 style.css에 이식(테마 변수·html.dark)
- [x] 3. main.js: initNowBand() — initLiveMarketPanel의 fetch/poll/스파크 헬퍼 재사용, 밴드 DOM 갱신
- [x] 4. (호출부는 main.js IIFE 내부 load 핸들러에 등록 — base.html 아님) initNowBand에서 initNowBand() 호출 배선
- [x] 5. kospi.html에 _now_band include (issue_briefing 위 or 대체 검토)
- [x] 6. 사이드바 원달러 제거+이슈섹션 제거 완료. 죽은 initLiveScoreboard/Panel은 그대로 둠(무해). 기존 죽은 initLiveScoreboard/initLiveMarketPanel·market_data.html 사이드바 처리 결정
       (밴드가 지수·수급을 흡수하면 사이드바 시장지표 중복 → 유지/축소/제거 결정 필요)
- [x] 7. 검증(mock 하니스 장중 재현 + 다크). 잔여: 실제 배포 후 라이브 API 확인. 검증: 장중/장후/과거/주말 상태별 렌더, 폴링 실패 시 빈칸, 다크

## 결정됨 (2026-07-11 유저 확인)
- [x] 원/달러: 밴드에 포함, 사이드바 시장지표에서 제거 → build_market_items kospi spec에서 usdkrw 제외
- [x] 장중 이슈: 밴드에 통합, kospi.html에서 _issue_briefing include 제거

## (구버전) 미결 결정 — 위에서 해소
- [ ] 사이드바 market_data(나스닥·SOX·원달러·VIX)와 밴드(코스피·코스닥·수급)의 관계 —
      밴드가 코스피/코스닥/수급을, 사이드바가 해외지표를 담당하는 분업이 맞나?
- [ ] 밴드 장중 이슈 vs 기존 issue_briefing 섹션(_issue_briefing.html) 중복 —
      밴드에 이슈를 넣으면 아래 issue_briefing과 겹침. 하나로 통합할지?
