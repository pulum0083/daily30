# 컨텍스트 노트 — 섹터/미국연계 랜덤 + 메가캡 가중

## 배경 (조사 결과)
- 섹터 리뷰(`sector_focus`)는 커밋 `d7c3757`에서 템플릿 삭제, `5e81ea7`에서 call_claude 생성 로직 삭제 → us_linked_story로 교체됨.
- 06-25부터 us_linked_story 렌더 시작. 06-10~24는 sector_focus 생성됐으나 템플릿 없어 공백.
- 잔재: `validate_analysis.py:913-935`(sector_focus/sector_semicon 검증)·`fetch_data.py`(SECTOR_FOCUS_STOCKS, sector_stocks 데이터)는 그대로 살아있음 → 복원이 쉬움.
- CSS `semicon-section-title`(style.css:165), 회피 이력 `data/sector_history_kospi.json` 모두 보존됨.
- `close_sector.html`(마감 사이드바 섹터 로테이션)은 별개 기능 — 건드리지 않음.

## 결정
- **노출 방식**: 날짜 시드 랜덤 + 폴백. `random.Random(f"section-{date}")`로 sector/us 택1(재실행 재현성). us 선택 시 마땅한 미국 이벤트 없으면 sector_focus로 자동 폴백.
- **선택 위치**: call_claude.py user_content에 지시문 주입 (시스템 프롬프트는 캐시되므로 양쪽 규칙 다 넣고, 택1은 user 메시지가 지정).
- **메가캡 가중**: 프롬프트에 규칙 추가. 단 [필수 규칙 7](픽 외 개별종목 등락 서술 금지) 때문에 reasons 본문은 섹터/SOX 레벨로만 표현하고, 개별 등락률(삼전 +X%) 직접 기재는 금지 유지.

## 주의 — 사용자 "60%" 수치
- 사용자는 삼전+하이닉스+SK스퀘어가 코스피 시총 60%+라 했으나, 실제 시총 비중은 약 1/3 수준(삼전 ~21%, 하이닉스 ~10%, SK스퀘어 ~0.5%). 60%는 **지수 등락 기여도(특히 반도체 급등락일)** 관점에선 성립할 수 있음.
- 따라서 프롬프트에 "60%"를 사실로 하드코딩하지 않음 (SERVICE_RULES 데이터 정합성). "시총 약 1/3, 등락 기여도로는 절반 이상인 날이 많다"로 정성 표현.
