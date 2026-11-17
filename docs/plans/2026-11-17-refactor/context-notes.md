# 결정 노트

- 2026-11-17 17:30 — 작업 트리에 13:18~13:22 수정된 미커밋 리팩토링 발견(출처 미상, 이 세션이 만든 것 아님). 테스트 JS 427·파이썬 1,152 전부 통과, eslint 오류 0(경고 6). 사용자가 '이어받아 마무리'를 골랐다.
- 테스트가 모듈 전역을 바꿔치는 곳이 많다(generate_html.BRIEFINGS_DIR 24곳, DATA_DIR 17곳, call_claude.DATA_DIR 23곳 등). 함수를 새 모듈로 옮기면 그 함수는 새 모듈의 전역을 보므로, 테스트의 바꿔치기 대상도 함께 옮겨야 한다 — 안 그러면 테스트가 진짜 data/ 를 읽거나 쓴다.
- 골든 대조는 리팩토링 전 커밋(741734c80)을 기준으로 고정했다. 같은 기준 코드를 두 번 돌려 차이 0줄(재현 가능)임을 먼저 확인했다. 로컬에 sp500_ma200.json·midterm_2018.json이 없어 그 두 상세 페이지는 양쪽 모두 '데이터 없음'으로 건너뛴다 — 그 두 작성기는 단위 테스트로만 덮인다.
- 1단계(남은 리팩토링) 골든 차이 0줄. 성격별로 세 커밋으로 나눴다(API 파서 / 파이썬 데이터 읽기·그래프 / npm 스크립트·CI).
- 2단계 generate_html 분할은 손으로 자르지 않고 split_module.py(ast로 이름별 의존을 계산해 import 생성, 순환이면 멈춤)로 했다. 첫 배치가 순환이라(briefing_meta↔sections_kospi↔…↔site_index) build_prediction을 sections_shared로, 사이드바 목록(existing_dates·find_adjacent·build_list_context)을 site_index로 옮겨 끊었다.
- 옮긴 이름은 전부 generate_html에서 다시 import해 call_claude·weekly_report·테스트가 gh.X로 그대로 읽는다. 처음엔 안 쓰는 import를 정리하다 gate_write까지 지워 weekly_report가 깨질 뻔했다(테스트는 통과) — gh.X 참조를 전수 대조해 찾았다.
- 테스트의 monkeypatch.setattr(gh, "DATA_DIR", …)는 이제 옮겨 간 함수에 닿지 않는다. scripts/gen_testkit.py의 gen_patch가 그 이름을 가진 생성기 모듈 전부를 함께 바꾼다. 테스트 뒤 git status로 진짜 data/·web/ 가 바뀌지 않았음을 확인했다.
- 남겨 둔 것: test_stock_seo_meta.py가 2026-10-26에 지운 g._stock_seo를 부르는 죽은 테스트(섹터 페이지가 없으면 skip). 이번 범위 밖이라 그대로 뒀다.
- 3단계 검증용으로 golden_validate.py를 만들었다 — 발행 게이트 validate()를 스냅샷 232편에 네트워크를 막고 다시 돌려 교정·경고·차단·교정본을 남긴다. 기준 코드로 두 번 돌려 같음을 확인(교정 306·경고 362·차단 16). 분할 뒤 차이 0줄.
- validate_analysis는 scripts. 경로(`from scripts.validate_analysis import …`, 운영 규칙 §1 수동 검증 예시)로도 import되므로 모듈 맨 위에 sys.path.insert를 넣었다 — 그 경로로 import될 때 gate_* 를 못 찾는다.
- 테스트의 바꿔치기는 gen_testkit.gate_patch(validate_analysis와 gate_* 전부)로 바꿨다. setattr이 여러 줄에 걸친 테스트(tests/test_prose_validation.py)를 처음에 놓쳐 진짜 시세를 조회하다 실패했다 — 정규식을 줄바꿈까지 받게 고쳤다.
- 4단계 검증용 golden_cc.py — Claude API를 부르지 않는 결정론 부분(시스템 프롬프트 3종·지시문 7종·기록 힌트·텔레그램 메시지 232편)을 다시 만든다. 분할 전후 차이 0줄.
- ⚠️ 4단계 중 사고: 테스트 바꿔치기를 새 모듈로 옮기기 전에 한 번 테스트를 돌려, 옮겨 간 save_prediction_to_briefings·save_telegram_message가 진짜 data/briefings.json과 data/telegram_message_{kospi,us,kospi_close}.txt를 썼다. briefings.json은 git checkout으로 바로 되돌렸다(작업 전 수정 없음 확인). 텔레그램 메시지 셋은 gitignore된 로컬 산출물이라 원래 내용을 되살릴 수 없다 — 발행 잡이 매번 새로 만들므로 서비스엔 영향이 없다.
- 그 뒤로 '테스트가 진짜 파일·네트워크를 건드리는지'를 전후로 비교하는 장치를 만들었다(스크래치패드 open_audit.py — 테스트마다 data/·web/ 파일 열기를 감사 훅으로 기록, nonet_pytest.py — 네트워크를 막고 실패 목록). 분할 직전 커밋(7859954ed)과 지금이 같다(읽기 68건·쓰기 0건, 네트워크 의존 실패 0건).
- 이 감사로 3단계에서 놓친 것도 찾았다 — test_index_superlatives가 va._index_extremes = … 로 직접 대입해, 옮겨 간 게이트가 그 값을 못 보고 진짜 지수 시세를 조회하면서도 통과하고 있었다. gate_superlative를 직접 바꾸게 고쳤다. 같은 패턴(test_calibration_hint·test_signal_snapshot의 cc.BASE_DIR/DATA_DIR 직접 대입)도 analysis_history로 옮겼다.
- 소스 문자열을 읽는 테스트(test_kospi_picks_removed·test_prediction_accuracy_upgrade)는 call_claude 묶음 전체(gen_testkit.CC_MODULES)를 읽게 바꿨다.
