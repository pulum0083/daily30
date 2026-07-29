# 체크리스트 — 실시간 장중 곡선 표기 통일

## 1. 상세 페이지 (`web/assets/stocks.js`)

- [x] 미국 세션 구간 경계 헬퍼 추가 (`usSegBounds`·`usSegWindow`·`etMinOfTs`·`kstHM`)
- [x] 미국 `px2()`를 데이터 범위 정규화 → 세션 고정 프레임으로 교체 (0~1 클램프)
- [x] 미국 x축 라벨을 데이터 시작/중간/끝 → 세션 시작/중간/끝(KST)으로 교체
- [x] 장중일 때 곡선 끝 → 오른쪽 끝 점선 트레일 (국내·미국 공통)
- [x] 장중일 때 끝점 맥동 도트 (SVG SMIL — CSS 파일 변경 없이 즉시 반영)
- [x] 마감 후에는 트레일·맥동 없이 기존 정적 끝점 유지

## 2. 섹터 페이지 (`scripts/templates/pages/stock_sector.html`)

- [x] `drawSpark(card, vals, label, isLive)` — 09:00~15:30 경과 비율만큼만 채우기
- [x] 점선 트레일 + `.spark-livedot` 맥동 도트
- [x] `.sector-card__spark`에 `position:relative`, `.spark-livedot` CSS 추가
- [x] 호출부 2곳(정적 20일 / 장중)에 `isLive` 인자 전달

## 3. 검증

- [x] ~~`scripts/test_live_curve_frame.py`~~ → **실제 페이지 수치 검증으로 대체**.
      로직이 브라우저 JS(IIFE 내부)라 파이썬 유닛테스트로 감쌀 수 없고,
      로직 복사본을 테스트하는 건 의미가 없어 실제 렌더 결과를 측정했다.
- [x] 미국 상세(정규장 진행 중): 마지막 점이 프레임의 24.3%, 실제 경과 24.1% — 일치
- [x] 섹터 카드(10:30 KST 스텁): 곡선 23.1% 채움 + 도트 위치·애니메이션·정원 확인
- [x] 국내 상세(장 마감): 프레임 꽉 참 + 맥동·트레일 없음
- [x] `generate_html.py --sectors` 정상 실행 (템플릿 회귀 없음)

## 4. 마무리

- [x] `generate_html.py --sectors`로 섹터 페이지 8종 재생성
- [x] 커밋 (푸시는 사용자 지시 시에만)
- [ ] **남은 확인** — 미국 프리장·애프터장 구간은 지금이 정규장이라 실측 확인 불가.
      코드상 `usSegBounds`가 구간별 경계를 반환하므로 동작하나, 17:00\~22:30 KST(프리장) /
      05:00\~09:00 KST(애프터장)에 한 번 눈으로 확인하면 좋다.
