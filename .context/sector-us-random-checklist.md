# 아침 브리핑 2건 조정 — 체크리스트

## 1. 섹터 리뷰 ↔ 미국 연계 종목 랜덤 노출 (날짜 시드 + 폴백)
- [x] `scripts/templates/sections/sector_focus.html` 복원
- [x] `call_claude.py`: `SECTOR_POOL`·`SECTOR_BY_KEY` 상수 복원
- [x] `call_claude.py`: `load_sector_history`/`save_sector_to_history`/`build_sector_avoidance_hint`/`pick_sector` 복원
- [x] `call_claude.py`: 시스템 프롬프트에 sector_focus 작성 규칙 복원 (택1 안내 포함)
- [x] `call_claude.py`: JSON 스키마 예시에 sector_focus 병존 표기
- [x] `call_claude.py`: 날짜 시드 랜덤 선택자 + 지시문 주입 (sector/us 택1, us는 폴백→sector)
- [x] `call_claude.py`: 섹터 로테이션 회피 힌트 주입 복원
- [x] `call_claude.py`: 호출 후 sector_focus 있으면 `pick_sector` + 이력 저장
- [x] `generate_html.py`: sector_focus ctx 매핑 복원 (us_linked와 병존)
- [x] `kospi.html`: us_linked 있으면 us_linked, 아니면 sector_focus 렌더

## 2. 반도체 메가캡 가중 규칙
- [x] `call_claude.py` kospi 방향 예측 우선순위에 삼전·하이닉스·SK스퀘어 집중도 규칙 추가

## 검증
- [x] 구문 체크 OK
- [x] generate_html 양쪽 분기 렌더 확인 (06-24 sector / 06-25 us, 텔레그램 발송 X)
- [x] 날짜 시드 재현성 + ~50/50 분포 + pick_sector 폴백 확인
- [x] US 브리핑 회귀 없음
