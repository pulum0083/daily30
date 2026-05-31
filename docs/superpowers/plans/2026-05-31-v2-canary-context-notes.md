# v2 카나리 병행 배포 — Context Notes

작업 중 내려진 결정과 그 근거를 계속 append 한다.

## 결정 로그

### 2026-05-31 (일) — 계획 수립
- **전략 확정: 임시 v2 하니스(additive) 방식.** 일반 머지는 구 서비스를 깨뜨리므로(`/assets/style.css` 공유 의존), 신 파이프라인을 `scripts/v2/`·`web/v2/`로 격리 복사해 main 위에 얹는다. 컷오버 때 하니스는 폐기하고 `rebuild-config-driven` 브랜치 본체를 루트로 머지.
- **발송 정책: 기존만 발송, v2 무음** (사용자 선택). v2 단계에 telegram/email 미추가.
- **병행 실행: 격리 병합** (사용자 선택). 같은 GA job 내 삽입으로 기존 cron 트리거 재사용.
- **v2 전용 call_claude 실행 이유**: 신규 필드(watch_items/spill/entry·target·stop/close_supply)는 브랜치 call_claude에만 존재. v2에서 신규 섹션까지 검증하려면 브랜치 call_claude를 따로 돌려야 함. Claude 호출 하루 ~4건×2일 추가(비용 무시 가능).
- **데이터 격리: `data/v2/`**. 워크플로가 구 파이프라인이 `data/`에 만든 입력(latest/news/briefings)을 `data/v2/`로 복사해 공급. v2 call_claude·generate_html은 `data/v2`에서만 입출력.
- **삭제 일정 연기**: 메모 #3의 "월요일 후 기존 데이터 삭제" → **수요일(6/3) 컷오버 시점으로 연기** (사용자 결정).
- **하드코딩 경로 집계 완료**: generate_html.py 374·375·395(네비)·464·531(에셋), base.html 14(favicon)·18(gnb). 이게 v2 prefix 패치 대상 전부.

## ⚠️ 브랜치 반영 필요 목록 (컷오버 전 rebuild-config-driven에 포팅할 것)
> 월·화 v2 하니스(`scripts/v2/`)에서만 고친 수정은 수요일 머지 때 증발한다. 여기 누적.

- (아직 없음)

## 🔧 v2 작업 워크플로 (2026-05-31 확정 — 증발 위험 제거)

**원본은 항상 `rebuild-config-driven` 브랜치다. `scripts/v2`·`web/v2`는 손대지 말 것(파생물).**

1. v2 디자인·로직 수정은 worktree에서 한다: `../double-shot-v2src` (= rebuild-config-driven 브랜치)
2. worktree에서 수정 후 **커밋**한다: `git -C ../double-shot-v2src add -A && git -C ../double-shot-v2src commit -m ...`
3. 메인 리포에서 동기화: `python3 scripts/sync_v2.py` → scripts/v2·web/v2 가 브랜치 최신 + /v2/ 패치로 재생성
4. 메인에서 평소처럼: `git add scripts/v2 web/v2 && git commit && git push` → 라이브 /v2/ 반영

- `sync_v2.py`는 **멱등**(재실행해도 동일). 패치 앵커가 안 맞으면(브랜치 구조 변경 시) 즉시 에러로 중단 → 조용한 손상 방지.
- worktree에 미커밋 변경이 있으면 sync가 경고. **수요일 컷오버는 커밋된 브랜치만 머지**하므로 worktree 커밋 필수.
- 이 방식이면 v2 수정이 자동으로 브랜치에 쌓이고, 컷오버(rebuild-config-driven 머지) 시 100% 반영된다.

## 발견 이슈 (카나리 중)

- **2026-05-31: reasons 1문장 압축 문제 (기존 서비스는 블릿당 2문장).** 원인 = 프롬프트 규칙 A가 "2문장"을 강제하지 않고 few-shot 예시에도 1문장이 섞임. 수정(worktree cda8f30 → sync → main cf226cc): ① 규칙 A를 "각 reason 정확히 2문장(의견+데이터)"으로 명문화(코스피·미국), ② reasons 글자수 규칙에 "1문장 압축 금지" 추가, ③ few-shot 예시 JSON을 2문장 모범으로 교체, ④ 5/29 테스트 데이터(data/v2 analysis_kospi·us)의 reasons도 실수치 기반 2문장으로 교체. → 내일 라이브 브리핑부터 자동 적용.

- **2026-05-31: 네비 href "None" 렌더 버그.** 인접 브리핑이 없을 때(첫·끝 날짜) 헤더 ‹›버튼이 `href="None"`으로 렌더됨. 원인 = 조립 템플릿 3종이 `{{ prev_url | default('#') }}`를 썼는데 Jinja `default`는 **undefined일 때만** 적용되고 명시적 `None`엔 안 먹음. 수정(worktree 66e224d → sync → main 7885445): `default('#', true)`로 boolean 인자 추가해 falsy(None)에도 적용. `disabled` 클래스 조건(`{% if not prev_url %}`)은 None이 falsy라 원래 정상. 로컬 4페이지 재렌더로 `href="#"`+disabled 검증 완료. ⚠️ **push 보류 상태(사용자 결정) — 월 07:30 전 push 안 하면 첫 라이브 브리핑엔 버그 잔존.**

- **2026-05-31: PREP 커밋(aaef1db)의 base.html 패치 누락.** sync_v2.py 도입 시 발견 — base.html이 비-v2 경로(`/favicon.svg`·`/briefings`)인 채로 커밋돼 있었음. sync 결과로 `/v2/` 패치 적용해 후속 커밋에서 수정. (원인: PREP 당시 Edit 유령 출력으로 실제 미반영)
