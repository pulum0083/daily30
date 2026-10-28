# 체크리스트

- [x] 시안 — 후보 전부(`2026-10-28-vs-intraday-readability.html`), 고른 안만(`2026-10-28-vs-intraday-final.html`)
- [x] 곡선: 세 칸 · 0% 기준 면 · 오늘 선 부호 색 · 회색 차이 막대 · 어제 끝 값 회색 · 차이 괄호 제거 · 말풍선 차이 줄 색 제거
- [x] 강도 카드 → 숫자 두 개 + 판정 뱃지(`heatWord`)
- [x] 주도권 카드 → 시장 기준선(순위 칸·이동 화살표·코스피/코스닥 점선·센/약한 섹터 한 줄)
- [x] 수급 카드 → 판 쪽 vs 산 쪽 + 기관 순매수 구성
- [x] 근거 4줄은 마감 후에만, 스켈레톤을 장중 카드 모양·실측 높이로
- [x] 설명 모달 문구(색 규칙·아래 카드) 갱신
- [x] 안 쓰게 된 함수(stat·miniBars·marketRow·sectorRow·turnPill·flowMainStat·flowInstPairs·pill)·CSS 정리
- [x] 테스트 갱신 — `node --test api/*.test.mjs web/assets/*.test.mjs` 206 + 179 통과, eslint 경고 없음(vs 파일)
- [x] 실데이터(10/28 13:06)·하락일 가상 데이터로 브라우저 렌더 확인(모바일 375px, PC 1100px)
- [x] 자산 버전 올림(js v=22, css v=15)
- [x] SERVICE_RULES §49·§54 기록
- [ ] 다음 장중(09:00~15:30)에 실제 /stocks/에서 확인
