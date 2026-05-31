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

### 2026-05-31 (일) 저녁 — 카나리 사전 수정분 일괄 push 완료
오늘 발견·수정 4건(네비 href·모멘텀 scenario 2문장·MA20→20일선·마감 세로 레이아웃+목록10일) 모두 **push 완료** (main 5f39122, branch rebuild-config-driven 71f1bfe). 위 개별 항목의 "⚠️ push 보류" 문구는 이 시점 이후 해소됨. 월 07:30 GA 첫 브리핑부터 scripts/v2 최신 반영. 라이브 /v2/ 에셋(style.css 등)도 즉시 반영.

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

## 마감 미구현 섹션 실데이터화 (사용자: ①부터 하나씩)

### ⚠️ 데이터 소스 조사 결론 (2026-05-31)
투자자 수급 데이터 소스 상태: **pykrx 투자자 엔드포인트 = KRX "LOGOUT" 안티스크래핑으로 빈 결과**(OHLCV만 정상, 샌드박스·과거날짜 무관). 네이버 모바일 API(`api.stock.naver.com/.../investorTrend`) = 404(경로 변경, 기존 fetch_data도 깨졌을 가능성). **유일하게 작동: 단일일 시장합계 스크래핑(`sise_index.naver`)** — 현재 수급현황 당일 수치 출처. → ②(종목별 외인·기관) ③ 일부도 같은 투자자 데이터 의존이라 동일 제약.

### ① 수급 7일 흐름 — ✅ 구현 완료 (단일일 누적 방식, 사용자 선택)
벌크 7일 API가 막혀, 매일 작동하는 단일일 수급을 `data/supply_history.json`(v2는 data/v2)에 **날짜별 멱등 upsert** 후 각 투자자 최근 7거래일 시계열을 flow-chart로 렌더. generate_html에 `update_supply_history`·`supply_flow` 추가, `build_close_sections(…, target_date)`. **기관 세부(inst_list)는 보류**(KRX 유일 소스라 막힘 → inst_list 없으면 섹션 자동 생략). worktree 44065ea → sync → main. 로컬 검증: 합성 시드 6일+당일자동추가=7일, 3개 차트×7막대·콘솔에러0. ⚠️ 라이브는 첫 7거래일 동안 점진적으로 채워짐(처음엔 막대 1~6개). 합성 시드(data/v2/supply_history.json)는 로컬 테스트용 — 미커밋.
### ② 거래대금 급증 + 수급 동반 종목(dpick) — ✅ 구현 완료
소스 재조사 결과: **pykrx 시장전체 OHLCV·투자자 전부 막힘(단일종목 OHLCV만 됨), 네이버 모바일 API 404.** 단 **네이버 종목별 `item/frgn`(외국인·기관 일별 순매매 수량)은 작동**하고 2026-05-29 실데이터 확인. → fetch_closing_kospi에 `fetch_dpick`(+`_fetch_frgn_daily`,`_dpick_num`) 추가: ⓐuniverse=네이버 거래량상위(`sise_quant`)에서 ETF 제외 상위 20, ⓑ종목별 frgn로 당일 거래대금(=거래량×종가)·20일평균 대비 배수·외인/기관 순매수액(**수량×종가 근사**, KRX 금액소스 막힘) 산출, ⓒ거래대금배수≥1.5 & 외인·기관 동시 순매수 필터 → 거래대금순 top3. generate_html `build_close_sections`에 dpick_rows 빌더(seg 막대 width=금액/최대×65%, vol 조/억 포맷, take 문구). worktree 11c535d·(mult중복·조사 fix) → sync → main. 실데이터 검증: NAVER(거래대금 1.76조 ×6.1, 외인+378·기관+2,053억)·삼성전자우·LG씨엔에스, 콘솔에러0. ⚠️ **순매수 금액은 근사치**(주식수×종가) — 전문투자자 대상이라 차후 정확 금액 소스(KRX OTP 정상화 등) 확보 시 교체 권장. fetch_dpick은 종목별 ~20 HTTP 팬아웃(마감잡 ~10s 추가).
- **남은 작업: ③ 아침 픽 결과.** 아침 픽 영속화(briefings.json엔 stock_picks 없음)+OHLC 조회+결과분류, 파이프라인 2잡 연계. 가장 큼.

## 발견 이슈 (카나리 중)

- **2026-05-31: reasons 1문장 압축 문제 (기존 서비스는 블릿당 2문장).** 원인 = 프롬프트 규칙 A가 "2문장"을 강제하지 않고 few-shot 예시에도 1문장이 섞임. 수정(worktree cda8f30 → sync → main cf226cc): ① 규칙 A를 "각 reason 정확히 2문장(의견+데이터)"으로 명문화(코스피·미국), ② reasons 글자수 규칙에 "1문장 압축 금지" 추가, ③ few-shot 예시 JSON을 2문장 모범으로 교체, ④ 5/29 테스트 데이터(data/v2 analysis_kospi·us)의 reasons도 실수치 기반 2문장으로 교체. → 내일 라이브 브리핑부터 자동 적용.

- **2026-05-31: 마감 WHY/WHAT/SO 세로 레이아웃 + 하단 목록 10일 축소.** ① `.b-row`(close_reason의 WHY/WHAT/SO?)를 가로 flex→`flex-direction:column;gap:6px`로 변경, 아이콘 배지 아래 줄에 설명. b-label의 `margin-top:2px` 제거(세로라 불필요). ② `generate_html.build_list_context` past_dates `[:30]`→`[:10]`. 공유 섹션이라 코스피·마감·미국·index 모두 동일 적용. 정확도 30일 윈도(typed[-30:])는 별개라 유지. prune_briefings.py(HTML 15일 보존)는 미변경. worktree 71f1bfe → sync → main c34da41.

- **2026-05-31: 브리핑 표시 문구 MA20/MA200 → 20일선/200일선.** 사용자 요청(영어 약어 대신 한글). 변경(worktree b8295d9 → sync → main 641fc26): ① `_modals.html` 도움말 모달(MA20을→20일선을, MA20 위에서→20일선 위에서, "(MA20)"→"(20일선)"), ② call_claude few-shot `signal` "MA20 상향 돌파"→"20일선 상향 돌파"(badge 표시), ③ scenario 규칙·few-shot "20일 이동평균선(MA20)"·"20일선(MA20)"→"20일선". 범례·200일선 게이지 라벨은 이미 한글이라 무변경. **데이터 필드명(ma20_signal·ma200_dist_pct 등)과 내부 선택규칙 텍스트(116·123·124·319·327 "잭 켈로그 MA20 전략"·"MA200 구조적 강세")는 출력 아님→유지.** 테스트데이터(data/v2)도 동기화. 렌더 grep로 출력 MA20/MA200 0건 확인. ⚠️ push 보류 누적.

- **2026-05-31: 상승 모멘텀 scenario 형식 = 기존 서비스 2문장으로 정렬.** 기존 라이브 모멘텀 카드는 "전일 <b>+X%</b> 급등하며 MA20을 막 돌파한 종목이에요. {촉매}로 투자 심리 개선, {시장 맥락} 속 추가 상승 여력이 있어요." 2문장. v2는 ① scenario가 촉매 1문장만, ② 템플릿(stock_picks.html L17)이 scenario+action_guide를 합쳐 노트에 "진입/목표/손절"이 그리드와 중복 표시되는 문제. 수정(worktree a27f27c → sync → main b55c1b0): ① call_claude 코스피·미국에 "시나리오(scenario) 작성 규칙"(정확히 2문장, 1문장=전일등락+MA20 돌파/지지, 2문장=촉매+여력, **진입가 텍스트 금지**) 명문화 + few-shot scenario 교체, ② 템플릿에서 action_guide 노트 중복 제거(진입/목표/손절 그리드는 유지 — 프로토타입 의도). ③ 5/29 테스트데이터(data/v2 analysis_kospi·us) scenario도 실수치 2문장으로 교체해 로컬 검증. 라이브 자동 적용은 내일 브리핑부터. ⚠️ push 보류 상태(아래 네비 건과 함께).

- **2026-05-31: 네비 href "None" 렌더 버그.** 인접 브리핑이 없을 때(첫·끝 날짜) 헤더 ‹›버튼이 `href="None"`으로 렌더됨. 원인 = 조립 템플릿 3종이 `{{ prev_url | default('#') }}`를 썼는데 Jinja `default`는 **undefined일 때만** 적용되고 명시적 `None`엔 안 먹음. 수정(worktree 66e224d → sync → main 7885445): `default('#', true)`로 boolean 인자 추가해 falsy(None)에도 적용. `disabled` 클래스 조건(`{% if not prev_url %}`)은 None이 falsy라 원래 정상. 로컬 4페이지 재렌더로 `href="#"`+disabled 검증 완료. ⚠️ **push 보류 상태(사용자 결정) — 월 07:30 전 push 안 하면 첫 라이브 브리핑엔 버그 잔존.**

- **2026-05-31: PREP 커밋(aaef1db)의 base.html 패치 누락.** sync_v2.py 도입 시 발견 — base.html이 비-v2 경로(`/favicon.svg`·`/briefings`)인 채로 커밋돼 있었음. sync 결과로 `/v2/` 패치 적용해 후속 커밋에서 수정. (원인: PREP 당시 Edit 유령 출력으로 실제 미반영)
