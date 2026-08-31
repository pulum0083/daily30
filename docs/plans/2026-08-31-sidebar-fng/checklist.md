# 브리핑 사이드바 '시장 지표' — VIX + 공포·탐욕 지수 2개로 축소

## 목표
- 코스피·미국 브리핑 사이드바 `시장 지표` 패널에 **VIX**와 **공포·탐욕 지수** 두 항목만 남긴다.
- 나스닥 / 필라델피아 반도체 / 나스닥100 선물 행은 화면에서 제거(데이터 수집은 유지 — 분석·다른 위젯이 소비).
- 공포·탐욕 지수는 CNN Fear & Greed Index(0~100 시장 심리 지표) 실측을 수집한다.

## 체크리스트
- [x] CNN F&G 엔드포인트가 실제로 응답하는지 로컬 검증
- [x] `fetch_data.get_fear_greed()` 신설 (CNN dataviz) → `market_data_js["fng"]` (kospi·us)
- [x] `generate_html.build_market_items()` — VIX + F&G만, 신선도 게이트 포함
- [x] `market_data.html` 뱃지 키를 범용(`badge`/`badge_cls`)으로 변경
- [x] `_modals.html` 공포·탐욕 지수 설명 모달 추가
- [x] `call_claude.py` [필수 규칙 5-1] 근거 문구 현행화 (모델에는 여전히 미제공 → 언급 금지 유지)
- [x] 단위 테스트 `scripts/test_market_items.py`
- [x] 로컬 전체 테스트 통과
- [x] **GitHub Actions 러너(미국 IP)에서 CNN 수집 가능한지 실측 확인**
