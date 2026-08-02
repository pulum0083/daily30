# StockRipple 벤치마크 4개 기능 — 진행 컨텍스트

이 파일은 세션이 끊긴 뒤에도 이어받을 수 있도록 결정 사항과 근거를 남긴다. 새 세션은 이 문서만 읽고 바로 이어갈 수 있어야 한다.

## 배경

`docs/analysis/2026-08-02-stockripple-benchmark.html`에서 StockRipple을 분석해 도입 4개 기능을 정했다.

1. 실적발표 캘린더
2. 테마 타임라인
3. 밤사이 브리지 · 국장 선반영 %p
4. 검증 근거 노출

**다음 실제 구현은 테마 타임라인부터 시작한다.** (2026-08-02 사용자 지시로 순서 변경 — 원래 캘린더를 먼저 다루고 있었으나, 캘린더는 프로토타입까지 마치고 일시정지했다.)

## 완료된 것

### 1. 서브탭 IA — 설계 완료, 구현 계획(writing-plans) 미착수

- 스펙: [`docs/superpowers/specs/2026-08-02-stocks-subnav-ia-design.md`](../../superpowers/specs/2026-08-02-stocks-subnav-ia-design.md) (커밋 `dab819c6`, ncai 규격 반영 `adb680a9`)
- 확정 구조: GNB는 `브리핑 | 월배당` 유지. 시그널 서브탭 6개 — **전체 · 특이신호 · 테마 · 섹터 · ETF · 일정**. 이번 구현 범위는 **기존 4개(전체·특이신호·섹터·ETF)만 점등**, 테마·일정은 각 기능이 완성될 때 점등.
- 배치: 페이지 머리말 끝(검색창·시장패널 아래), 언더라인 탭, 공용 스크립트 1벌(`ds-subnav.js`)로 세 페이지(`/stocks/`·`/themes/`·`/calendar/`) 공유 — §30 이중 구현 재발 방지.
- **사용자가 스펙 승인·writing-plans 전환을 명시적으로 확인하지 않았다** — 캘린더 프로토타입으로 바로 넘어갔다. 다음 세션에서 이 스펙을 다시 보여주고 승인받거나, 테마 작업과 함께 구현할지 판단 필요.

### 2. 실적 캘린더 — 프로토타입 완료, 설계 문서(design spec) 미작성, 일시정지

- 최종 프로토타입: [`docs/prototypes/2026-08-02-earnings-calendar.html`](../../prototypes/2026-08-02-earnings-calendar.html) (커밋 `8bee4db5`)
- **아직 정식 스펙 문서(`docs/superpowers/specs/...-earnings-calendar-design.md`)를 안 썼다.** 브레인스토밍 프로세스가 "설계 제시 → 스펙 작성" 단계 전에 멈췄다. 재개 시 이 프로토타입 내용을 스펙으로 옮겨 쓰는 작업이 남아 있다.

**데이터 소스 확정 사항 (스파이크로 검증 완료):**

- `https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD` — 하루 132~570건, BMO(`time-pre-market`)/AMC(`time-after-hours`)/미정(`time-not-supplied`) 구분, 컨센서스 EPS, 추정 기관 수, 시총, 작년 동기 실적.
- **치명적 제약: `time` 필드는 발표 후 이틀이면 지워진다.** 실측 — 미래 10영업일은 미정 비율 5~11%, 과거 -2·-3일은 94~100% 미정. **BMO/AMC는 이벤트가 미래일 때 매일 스냅샷으로 수집해 누적 저장해야 한다.** 발행 시점에 그때그때 조회하면 값이 없다 — 이게 §19·§23·§29 시제 사고를 구조적으로 막는 핵심 설계 포인트이므로 반드시 이 방식으로 구현할 것.
- yfinance `get_earnings_dates()`의 시각은 전부 `16:00 ET` 기본값이라 **못 쓴다.** 대신 `Reported EPS`·`Surprise(%)`(실제 결과)는 이걸 써야 한다.
- **Nasdaq 컨센서스와 yfinance 컨센서스가 다르다** (실측: LIN 4.49 vs 4.12, 9% 차이). 발표 완료(사이드바) 행은 **yfinance의 컨센·실제·서프라이즈 세 값만** 써서 섞지 않는다 — 부호 모순 0건으로 검증 완료.
- `ff_calendar_thisweek.json`(기존 경제지표 소스)의 `actual` 필드는 94건 중 0건 — §29 "죽은 판별자" 재확인, 이 필드로 발표여부 판정하지 말 것.
- 코스피 read-through 관심 종목(MU·TSM·ASML·AMAT·LRCX·KLAC·WDC·SNDK·NVDA·AMD·AVGO·INTC·MSFT·GOOGL·AMZN·META·AAPL·TSLA·ORCL·SMCI·DELL·ANET·MRVL·QCOM·TXN) 화이트리스트로 "코스피 연관" 뱃지 판정.

**확정된 화면 설계:**

- 2단 레이아웃 — `#signals-all`의 `.home-cols`(2fr 1fr, 900px 이하 1단 — 캘린더는 820px 채택) 규격 그대로.
- 좌측(본문): **A안 — 날짜별로 경제지표·실적을 함께**, 하루 상위 **6건 + "더보기"**, 시총 $10B+ 필터.
- 우측(사이드): 발표 완료 목록 — yfinance 실제 결과(컨센→실제→서프라이즈%), 상단에 완료/상회/하회 집계 3칸.
- "코스피 연관" **텍스트 전용 뱃지** (태극기 이모지 제거 — 13px에서 잘 안 읽힘).
- 하단 면책 문구: BMO=22:30 KST, AMC=다음날 05:00 KST는 **개장·마감 시각 기준 관례값**이지 실제 공시 시각이 아니라고 명시.
- 홈 "이번 주 일정" 요약 블록은 시그널 홈 **맨 아래**(사용자 지시) — 코스피 연관 우선 + 나머지 시총순 4건 + 다음 경제지표 1건.

**디자인 시스템 — ncai-design-system 준거 (중요, 재확인 필요 없음):**

- 저장소: `GronkOut/ncai-design-system` (React + Base UI 전제, `resources/design-system.md` 2,160줄이 정본). Double-Shot은 빌드 없는 정적 HTML이라 **컴포넌트는 못 가져오고 토큰·규칙만 따른다.**
- **Double-Shot은 이미 이 시스템 토큰을 쓰고 있었다** — `--canvas`/`--surface-soft`/`--hairline`/`--ink`/`--primary` 등 변수명만 줄었을 뿐 값(라이트·다크 모두)이 일치.
- **좌측 컬러 액센트 바(border-left accent) 전면 금지** — 문서 4곳(1459·1480·1514·1848)에서 명시. 특히 1572 "Status as a Whisper"가 우리 케이스: 상태는 8px 점 하나 또는 뱃지로, 좌측 컬러 레일·지그재그 배경 금지.
- 채택한 강조 방식(E1): 강조 = `surface-soft` **톤**(컬러 아님), 종류 = **pill 뱃지**(h24·패딩8·gap4·`.caption-13r`/weight 500). 카드 = `card-standard`(canvas+1px hairline+radius16). 리스트 행 = hairline `border-bottom` + `:last-child` 제거(List Separator Rule).
- 탭(서브탭 IA에도 적용) = underline 변형. 높이 40px·패딩16·`.label-14m`. **활성 = 텍스트·언더라인 모두 primary, weight는 500 고정(굵게 금지 — 레이아웃 점프 유발이 금지 사유).**
- **도메인 예외 1건**: 서프라이즈 상회·하회 색은 ncai `semantic-error/success`(빨강=오류, 초록=성공) 대신 **사이트 고유 `--up`(#E03131 빨강=상승)/`--dn`(#2775ED 파랑=하락)** 사용 — 한국 시장 관례가 시스템 semantic과 반대라 별도 `--ds-up`/`--ds-dn` 토큰으로 분리. 이후 다른 기능에서도 상승·하락 색은 이 규칙을 따를 것(ncai semantic 팔레트 쓰지 말 것).
- 밀도 주의: ncai 최소 텍스트가 `.caption-13r`(13px)라 기존에 쓰던 9.5~10.5px 소형 텍스트는 못 쓴다 — 같은 공간에 들어가는 정보량이 줄어드는 걸 전제하고 레이아웃을 짤 것.

### 3. 밤사이 브리지 — 브레인스토밍·스펙 완료, 구현 미착수

- 스펙: [`docs/superpowers/specs/2026-08-02-overnight-bridge-design.md`](../../superpowers/specs/2026-08-02-overnight-bridge-design.md)
- 비주얼 컴패니언으로 배치 3안(본문/사이드바/스트립) 검토 → **A(본문, 「간밤 미국 시장 이슈」 뒤·예측 앞)** 확정.
- 범위는 코스피 아침(07:25)만 — 개장 전 선행형(간밤 미국 정규장 vs 한국 직전 마감). 집계는 섹터 대표 종목 대칭(`stock_universe.json` 단일 소스, `fetch_data.py`의 죽은 `SECTOR_FOCUS_STOCKS` 재사용 금지 — 섹터 구성이 다름).
- LLM 미개입 — 순수 결정론적 계산이라 §22~§29 계열 사고가 구조적으로 불가능한 섹션.
- **자기검토로 실제 버그 하나 잡음**: 스냅샷 스테일 기준을 처음 2일로 썼다가, 금요일 16:33 스냅샷을 월요일 07:25에 읽으면 이미 ~2.6일 지나 매주 월요일 정상 데이터가 스테일로 오판될 뻔했다 → §20 선례대로 4일로 수정. 새 신선도 게이트를 쓸 때마다 "가장 긴 정상 간격(주말·연휴)"을 먼저 계산해볼 것.
- 남은 것: `writing-plans`로 구현 계획 전환.

### 4. 코스피 브리핑 위로 카드 재구성 — 브레인스토밍·스펙 완료, 구현 미착수 (StockRipple 스코프 밖 애드혹 지시)

- 스펙: [`docs/superpowers/specs/2026-08-02-kospi-comfort-card-design.md`](../../superpowers/specs/2026-08-02-kospi-comfort-card-design.md)
- 사용자가 브리지 브레인스토밍 도중 화면 스크린샷을 붙여 추가 지시: "이렇게 보는 이유" 섹션 제거 + "위로 한 줄" 카드에 텔레그램 구루 명언(`data/guru_quotes.json`, 272개) 추가.
- 비주얼 컴패니언 2라운드(배치 A/B/C → C 재설계 3변형) 끝에 **C2(따옴표 글리프, 명언이 주인공, 저자는 무채색 텍스트)** 확정.
- **명언 동기화가 핵심 설계 포인트**: 지금 `pick_quote()`(`send_telegram.py`)는 발송 직전 랜덤 선택인데, 웹은 그보다 앞선 `call_claude --render`에서 완성되므로 그대로 두면 같은 날 웹·텔레그램이 다른 명언을 보여준다. `render_outputs()`가 `generate_html.py` 서브프로세스 호출 **전**에 `data/quote_today.json`을 써서 텔레그램이 그걸 읽도록 방향을 뒤집었다(코스피 타입만, us·kospi-close는 미적용). 폴백은 기존 랜덤 유지.
- `key_drivers` 필드·검증 게이트(§22·§24·§28·§29)는 안 건드림 — 화면 렌더링 한 줄만 제거, 데이터 생성·검증 파이프라인은 그대로.
- **두 스펙이 같은 템플릿(`kospi.html`)을 건드린다** — 확정된 최종 섹션 순서는 이 스펙의 "미결 사항"에 명시: `_now_band → todays_view/형식별 → _us_issues → _overnight_bridge(신규) → prediction/strip → (reasons 제거) → _comfort_line(C2) → divider → domestic_issues → ...`
- 남은 것: `writing-plans`로 구현 계획 전환. 두 스펙을 같은 계획에서 함께 구현할지, 순서대로 나눠 구현할지는 계획 단계에서 결정.

## 다음 세션에서 할 일 — 테마 타임라인 브레인스토밍

`superpowers:brainstorming` 스킬로 처음부터 시작한다(비주얼 컴패니언 사용 — 이전 세션에서 사용자 동의 받음, 새 세션에서는 다시 물어볼 것).

**먼저 할 데이터 스파이크** (캘린더와 같은 순서 — 가능한 범위를 먼저 확인 후 프로토타입):

- 소스: `web/data/kospi-news-{date}.json` 아카이브, 2026-06-05부터 60일치 이미 존재(재수집 불필요).
- 확인할 것: 실제로 테마별로 묶이는지(예: "미·이란 전쟁", "반도체 수출"), 테마당 항목 수가 타임라인이라 부를 만큼 나오는지, 날짜·출처가 실측인지(§25·§28 기준 — 실명·실측만).
- StockRipple의 "말말말" 포맷 참고: 테마 제목 + 진행 중 요약 + 연관 지수·종목 실시간 시세 + 헤드라인 타임라인(출처·시각·한 줄 요약).
- IA 연결: `/themes/` 신규 실 페이지, 서브탭 "테마" 점등, 홈에 "진행 중 테마" 요약 블록(§ 서브탭 스펙의 "홈과 탭의 관계" 규칙에 따라 필수).
- 디자인은 위 ncai 규칙(뱃지·hairline 리스트·2단 레이아웃)을 그대로 재사용 — 매번 새로 확인할 필요 없음.

## 열린 질문 (다음 세션 시작 시 사용자에게 확인)

1. 서브탭 IA 스펙(`2026-08-02-stocks-subnav-ia-design.md`)을 지금 구현할지, 테마 페이지와 함께 구현할지.
2. 캘린더는 스펙 문서 작성부터 재개할지, 테마를 먼저 끝내고 나중에 재개할지.
3. 비주얼 컴패니언 서버(전 세션 `localhost:58611`)는 세션 종료 후 유효하지 않다 — 새로 `start-server.sh --project-dir` 실행 필요.

## 참고 파일 위치

- 벤치마크 분석: `docs/analysis/2026-08-02-stockripple-benchmark.html`
- 서브탭 IA 스펙: `docs/superpowers/specs/2026-08-02-stocks-subnav-ia-design.md`
- 캘린더 프로토타입: `docs/prototypes/2026-08-02-earnings-calendar.html`
- 관련 커밋: `dab819c6`(벤치마크+IA 스펙) → `7d1a1e53`(캘린더 1차 프로토) → `adb680a9`(ncai 규격 교정) → `8bee4db5`(캘린더 최종)
