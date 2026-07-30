# Double-Shot 운영 규칙

## AI 파이프라인

### 뉴스 수집 — `fetch_news.py`

- `google_search` tool로 그 시점 최신 뉴스를 직접 검색·요약 (1회 호출). RSS 파싱 제거됨.
- 브리핑 타입별 검색 프롬프트 (KOSPI / KOSPI_CLOSE / US) 로 검색 키워드 지시.
- 결과: `data/news_summary_{type}.json`

### 분석·예측 — `call_claude.py`

- **Prompt Caching** 적용 (시스템 프롬프트 캐시, ~5분 TTL, 재실행 시 90% 비용 절감)
- 출력: JSON only (`analysis_{type}.json`) → HTML 생성은 `generate_html.py`가 담당
- 생성 항목: `prediction` (direction / up_pct / confidence), `reasons`, `reason_title`, `stock_picks`

### 데이터 검증 게이트 — `validate_analysis.py`

- `call_claude --no-html` → **validate_analysis** → `call_claude --render` → telegram 순으로 동작.
- 픽 종목 실측 주입 + 본문 금지패턴·환율·지수%·수급 스케일 교정.
- 치명적 오류 시 발행 중단 + 관리자 텔레그램 알림.

### 월가 애널리스트 발언 수집 — `fetch_analyst_quotes.py`

- Gemini 2.5 Flash Lite + `google_search` tool로 12명 애널리스트의 48시간 이내 실발언 수집.
- 발언이 없으면 `[]` 저장 후 exit 0 — 파이프라인 보호. 섹션만 생략됨.
- 출력: `data/analyst_quotes.json` (최대 4건, 최신순 정렬)
- 감성 분류: `bull` / `bear` / `neu` (Gemini가 검색·추출 동시에 자동 분류)
- us-briefing job에서 `fetch_news.py` 직후, `call_claude.py` 직전에 실행. `continue-on-error: true`.
- 대상 애널리스트 (12명): Tom Lee, Ed Yardeni, Dan Ives, Mike Wilson, Savita Subramanian, Bill Ackman, Stan Druckenmiller, Mohamed El-Erian, Jeff Gundlach, Ray Dalio, Cathie Wood, Michael Burry

### 외국계 IB 코멘트 수집 — `fetch_ib_korea_views.py`

- Google News 한국어 RSS로 화이트리스트 IB(골드만·모건스탠리·JP모건·UBS·씨티·노무라·맥쿼리·HSBC·CLSA·번스타인·BofA·바클레이스) × 코스피/대형주 쿼리로 **최근 24시간** 국내 2차 보도를 실수집.
- 제목/요약에 화이트리스트 IB명이 실제로 있어야 채택(귀속 불가 시 제외). IB당 1건, 최대 3건.
- 원문 링크: Google News 링크를 batchexecute로 발행사 원문 URL로 리졸브, 실패 시 Google News 링크 폴백(둘 다 실기사 연결).
- Gemini는 **요약·분류만** — 날짜·URL·출처는 RSS 실데이터라 생성 불가. 목표가·지수 숫자는 제목·요약에 있으면 허용, 없으면 생성 금지. 해요체 고정.
- **다이제스트 방식**: 원문 발언 전문을 갖고 있지 않으므로 큰따옴표 버바텀 인용을 하지 않고 스탠스 요약 + 원문 링크로 제시.
- 출력: `data/ib_korea_views.json`. 대상 없으면 `views: []` → 섹션 생략(파이프라인 보호).
- 표시: 코스피 오전 브리핑 "🏦 외국계 시각" 섹션(reasons 뒤·stock_picks 앞). `generate_html.build_ib_korea_views()`가 url 없는 항목 제외.
- kospi-briefing job에서 `fetch_news.py` 직후, `call_claude.py` 직전 실행. `continue-on-error: true`.

**⚠️ Google News RSS의 `pubDate`는 신뢰하지 않는다 — 실제 발행일시로 재검증한다 (2026-07-13·2026-07-14 두 차례 실사고로 확정된 방지 룰):**

Google이 오래된 기사(특히 MSN 등 리스티클성 기사)를 몇 주 뒤에 재크롤링하면서 RSS `pubDate`를 현재 시각 근처로 다시 찍어주는 경우가 있다. 24시간 필터는 이 조작된 `pubDate`를 통과시킨다. 2026-07-13에는 "골드만삭스 코스피 1만2000" 옛 기사가, 2026-07-14에는 그 재발 형태인 "JP모건 코스피 15,000"(실제 발행일 2026-06-25 — 약 19일 전)가 같은 방식으로 통과했다. 첫 사고 때 지수 레벨 정규식(`_is_stale_index_level`)으로 막았지만, 두 번째 사고는 그 정규식이 커버하지 못하는 표기("15,000 간다" — 콤마 표기·만/선/포인트 접미사 없음)라서 뚫렸다.

- **1차 방어(저비용 사전 필터)**: `_extract_index_levels()`가 제목·요약에서 지수 레벨(만/선/포인트 접미사 + 콤마·접미사 없는 예측 동사 패턴 "간다"·"가능"·"돌파"·"도달")을 추출하고, `_is_stale_index_level()`이 실제 코스피(yfinance) 대비 ±30%를 벗어나면 네트워크 호출 전에 후보를 버린다. 이 정규식은 앞으로도 새 표기 변형에 뚫릴 수 있으므로 **최종 방어선이 아니다**.
- **2차 방어(최종 판정, 반드시 통과해야 채택)**: `_select_verified_candidates()`가 각 후보의 Google News 링크를 원문 URL로 리졸브한 뒤, 원문 페이지의 **실제 발행일시**(JSON-LD `datePublished`, `article:published_time`/`og:published_time` meta, 또는 MSN은 `assets.msn.com/content/view/v2/Detail/{market}/{id}` 콘텐츠 API의 `publishedDateTime`)를 다시 조회해 그 값이 24시간 이내인지로 **최종 판정**한다. RSS `pubDate`는 하우스별 후보를 최신순으로 시도하는 순서 결정에만 쓰고, 채택 여부 판정에는 쓰지 않는다.
- **실제 발행일 추출 실패 시 후보를 버린다** (표시하지 않는다). 완전성보다 정합성을 우선한다 — 검증 불가한 기사를 "일단 보여주고" 나중에 걸러내지 않는다.
- **원문 URL 리졸브 버그(2026-07-14 동시 발견·수정)**: `_resolve_gnews_url()`이 Google `batchexecute` 응답을 파싱할 때, 쿼리스트링에 `=`·`&`가 있으면 응답이 `=`·`&`로 이중 이스케이프되는데 기존 정규식이 첫 역슬래시에서 멈춰 URL이 잘렸다(`?no=104294` → `?no`). `_extract_resolved_url()`이 `\uXXXX`를 실제 문자로 복원한 뒤 반환하도록 수정됨 — 이 함수를 건드릴 때는 쿼리스트링 있는 URL로 반드시 재검증할 것.
- **재발 시 진단 순서**: ① 의심 항목의 `url`을 직접 열어 실제 발행일 확인(불가하면 사이트 자체가 정적 메타데이터 없는 SPA — MSN처럼 사이트별 API가 필요한지 검토). ② `_parse_real_published_at()`이 해당 사이트의 날짜 마크업을 못 찾는지 확인(신규 언론사 도메인마다 마크업이 다를 수 있음). ③ 두 방어선 모두 통과했는데도 옛 기사라면, `_is_stale_index_level`의 접미사 패턴이 아니라 **실제 발행일 검증 로직 자체의 버그**(파싱 실패를 조용히 통과시키는 등)를 의심할 것 — 정규식 표기 변형 추가만으로는 재발을 막지 못한다는 게 이번 두 번의 사고로 확인된 교훈이다.

### 오늘 증권가 시황 수집 — `fetch_research_reports.py`

- 네이버 금융 리서치 시황정보 게시판(`market_info_list.naver`)에서 **당일(KST) 발행 국내 시황 리포트**만 수집.
- **발행 시점 기준 최근 24시간 필터**: 네이버 게시판은 발행 "날짜"만 제공하고 "시각"은 노출하지 않음(원본 HTML에 시:분 정보 없음) — 시각 단위 필터는 소스상 불가능. 대신 **당일 날짜만 채택**하는 방식으로 근사한다. 잡이 16:25(KST) 실행되므로 당일자 리포트는 구조적으로 발행 후 0~16시간 이내이며 최근 24시간 이내임이 보장됨. 어제 날짜 리포트는 채택하지 않음(발행 시각을 알 수 없어 24시간 이내인지 판별 불가하므로 안전하게 제외).
- 제목에 박힌 날짜 표기(`YY.MM.DD`, `M/D`)가 당일과 다르면 전일자 내용 재게시로 간주해 제외 (예: 7/2에 올라온 "7/1 KB 리서치 장마감코멘트" — 게시일은 오늘이지만 내용은 어제자).
- 해외/글로벌/원자재 리포트 제외(코스피/국내/증시/시장/마켓/전략 키워드만), 증권사당 1건, 최대 3건.
- Gemini 요약(1~2문장, **해요체 고정**) — 프롬프트로 지수·등락률·목표가 등 숫자 언급을 금지하고, 생성 후 정규식으로 숫자 잔존 여부 재검증. 잔존 시 해당 리포트 폐기(섹션에서 빠짐) — 마감 브리핑 히어로 수치(실측)와 리포트 본문 수치(장중/구버전일 수 있음)가 충돌하는 것을 방지.
- 대상 리포트가 없으면 `reports: []` 저장 — 섹션 자체 생략, 파이프라인 보호.
- 출력: `data/research_reports.json`
- kospi-close-briefing job에서 `fetch_movers_why.py` 직후, `call_claude.py` 직전에 실행. `continue-on-error: true`.

### 마감 데이터 수집 — `fetch_closing_kospi.py`

- 장중 흐름 (intraday), 수급 (investor_trading), 시장 폭 (market_breadth), 섹터 (sectors)
- 거래대금 급증 × 수급 동반 종목 (dpick): 외국인·기관 동시 순매수 + 거래대금 1.5배↑
- 출력 필드: `market_breadth.up/down/unchanged/upper_limit/lower_limit`

## API 키 / 환경변수

| 변수                   | 용도 |
| -------------------- | ---- |
| `ANTHROPIC_API_KEY`  | Claude Sonnet 5 |
| `GEMINI_API_KEY`     | Gemini 2.5 Flash |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 |
| `TELEGRAM_CHAT_ID`   | 텔레그램 채널 |
| `RESEND_API_KEY`     | 이메일 발송 (Resend) |
| `GH_PAT`             | Vercel → GitHub Actions dispatch |
| `TOSS_CLIENT_ID`     | 토스증권 Open API |
| `TOSS_CLIENT_SECRET` | 토스증권 Open API 시크릿 |

GitHub Actions Secrets에 모두 등록되어 있음.

### 토스증권 Open API (`scripts/toss_client.py`)

- **인증**: OAuth2 `client_credentials` 방식. `_get_token()`이 토큰을 캐싱(메모리, ~24h TTL).
- **엔드포인트**: `https://openapi.tossinvest.com`
  - `GET /api/v1/candles` — 일봉/1분봉 (1회 최대 200개, `nextBefore`로 페이지네이션)
  - `GET /api/v1/prices` — 현재가 일괄 (최대 200개)
  - `GET /api/v1/exchange-rate` — 환율 (`midRate`)
- **심볼 형식**: 한국 종목 6자리 코드 그대로, 미국 종목 티커 그대로 (`.KS`/`.KQ` 접미사 불필요)

### 실측 조회 우선순위 (`validate_analysis.py`)

| 종목    | 1순위           | 2순위 (폴백) |
| ----- | ------------- | ------------ |
| 한국 종목 | 토스증권 Open API | 네이버 일봉 (`api.stock.naver.com`) |
| 미국 종목 | 토스증권 Open API | yfinance |
| 환율    | 토스증권 Open API | (없음 — 실패 시 `None` 반환) |

## Vercel 라우팅

```
/                              → landing.html
/briefings/                    → briefings/index.html
/briefings/{date}/kospi/       → briefings/{date}/kospi/index.html
/briefings/{date}/close/       → briefings/{date}/close/index.html
/briefings/{date}/us/          → briefings/{date}/us/index.html
/briefings/ko/{date}/          → 레거시 호환
/briefings/us/{date}/          → 레거시 호환
/briefings/ko-close/{date}/    → 레거시 호환
```

## GitHub Actions Workflow (`daily_report.yml`)

4개 job, 모두 `workflow_dispatch` 트리거 (Vercel Cron이 `/api/trigger`로 dispatch):

| job                    | 트리거 type      | 주요 스텝 |
| ---------------------- | ------------- | --------- |
| `kospi-briefing`       | `kospi`       | fetch_data → fetch_news → call_claude → update_latest → telegram → email → generate_html → commit → pages |
| `us-briefing`          | `us`          | fetch_data → fetch_news → **fetch_analyst_quotes** → call_claude → update_latest → telegram → email → generate_html → commit → pages |
| `kospi-close-briefing` | `kospi-close` | fetch_closing_kospi → fetch_news → call_claude → telegram → generate_html → commit → pages |
| `kospi-accuracy`       | `accuracy`    | check_accuracy → commit |

---

## 운영 규칙

### 0. 데이터 정합성 — 자동 검증 파이프라인 (핵심)

> # 이 서비스의 제1원칙 — 다른 모든 규칙에 우선한다
>
> **① 브리핑은 발행 시점에 새로 수집한 데이터로 만든다.**
> **② 데이터가 없으면 그 섹션은 비운다. 절대 지어내지 않는다.**
>
> 이 둘을 어기면 브리핑을 정해진 시각에 내보내는 의미 자체가 사라진다.
> 할루시네이션 브리핑은 **서비스를 접어야 하는 수준의 사고**다 — 늦거나, 짧거나,
> 섹션이 비는 것은 모두 감수할 수 있지만 **틀린 것은 감수할 수 없다.**
>
> **① 발행 시점 데이터**
> - 주가·등락률·수급·종목 픽 등 모든 수치는 생성 당시 fetch_data / fetch_closing_kospi /
>   toss_client 등이 **그 시점에** 수집한 실측값만 허용한다.
> - **"지금"의 기준은 브리핑이 나가는 시각의 시장 상태다.** 미국 브리핑(21:15 KST)은
>   미국 프리마켓 한복판에 나가므로 **프리마켓 실체결가**가 "지금"이다. 직전 정규장 종가를
>   싣고 본문만 "프리마켓"이라 쓰면 위반이다(2026-07-27 실사고 → §26).
> - 벤더의 편의 필드를 그대로 믿지 않는다 — `fast_info.last_price`는 연장시간대를 반영하지 않고,
>   `fast_info.previous_close`는 직전이 아닌 과거 세션을 준다(§24·§26). 실제 시계열로 교차 검증한다.
>
> **② 없으면 비운다**
> - 수집에 실패했거나 검색되지 않은 데이터는 표시하지 않는다. 빈 값으로 두거나 섹션을 생략한다.
> - 어떤 이유로도 데이터를 억지로 생성(추론·추정·보간·하드코딩)하지 않는다. LLM이 만든 숫자,
>   캐시된 이전 세션 데이터, 출처 불명의 값은 사용 금지.
> - **실명 없는 사건은 발행하지 않는다** — "B사가…"처럼 익명화된 서술은 검증 자체가 불가능하다(§25).
> - **뉴스 수집이 빈손이면 이슈 섹션을 비운 채로 발행한다.** 빈 섹션을 채우려고 분석 단계에서
>   소재를 만들어내는 것이 이 서비스에서 가장 위험한 실패 모드다.
>
> **화면에 표시되는 모든 수치는 실측이어야 한다. LLM이 생성한 숫자는 신뢰하지 않고, 발행 전 실제 시장 데이터로 덮어쓴다.**
>
> **완전성보다 정합성이 우선이다.** 이 문장이 §0부터 §26까지 모든 규칙의 요약이다.

**파이프라인 순서 (절대 바꾸지 말 것):**

```
call_claude --no-html   분석 JSON만 (HTML·텔레그램 생성 안 함)
      → validate_analysis   픽 실측 주입 + 본문 교정
      → call_claude --render   교정된 데이터로 웹 페이지·텔레그램 메시지 생성
      → send_telegram   웹 페이지 생성 후 발송
```

LLM 출력(HTML·텔레그램)이 검증 이전에 만들어지면 교정이 반영되지 않는다. 새 출력물을 추가할 때도 반드시 `--render`(검증 이후) 단계에서 생성한다.

**종목 픽 실측 주입 (`enrich_picks_with_realdata`):**

- 미국 종목 → 토스증권 Open API 우선, 실패 시 yfinance 폴백.
- 한국 종목 → 토스증권 Open API 우선 (6자리 코드 그대로), 실패 시 네이버 일봉 폴백. **6자리 코드만 사용, `.KS`/`.KQ` 접미사 금지.**
  - ⚠️ yfinance에 `.KS`를 붙이면 KOSDAQ 종목이 유령 데이터(하루 stale·틀린 가격)를 반환한다.
- **기준은 브리핑 발행 시각의 시장 상태에 따라 다르다** (`_fetch_pick_realdata`):
  - **미국 브리핑(21:15 KST = 미국 프리마켓)** → `live=True`. 현재가 = **프리마켓 실체결가**,
    기준가 = 직전 정규장 종가. 발행 시점 데이터 원칙(§0 ①) 그대로다.
  - **코스피 아침(07:25 = 한국·미국 모두 휴장)** → 직전 완료 세션 종가 대비(`close[-1] vs close[-2]`).
    이 시각엔 그게 곧 "가장 최신 실측"이라 §0과 충돌하지 않는다.
  - ⚠️ 2026-07-27까지 이 자리에 "실시간 장중가 아님"이 무조건 규칙으로 적혀 있었고,
    그게 §0 ①을 정면으로 부정해 미국 브리핑의 구조적 위반을 제도화했다(§26). 다시 되돌리지 말 것.

**실측 소스가 없는 영역은 수치를 표시하지 않는다:**
- 미국 프리장 신고가(`premarket_highs`) → 정성 정보만, 숫자 제거.

**검증 범위 (현재):** 픽·사이드바·마감 카드는 실측. 본문 산문은 금지단위·환율·지수%·수급 100배 스케일만 검증 — 산문 내 개별 종목 수치는 구조적 미검증이므로 수동 점검 시 주의.

### 1. 브리핑 데이터 수동 검증

> **자동 게이트가 있어도, 수동 패치·재생성 시에는 LLM이 생성한 가격·수치를 실제 시장 데이터로 검증하고 반영한다.**

```python
# 가장 안전한 방법: validate_analysis의 함수 직접 재사용 (토스→폴백 자동 처리)
from scripts.validate_analysis import _fetch_kospi_realdata, _fetch_us_realdata
result = _fetch_kospi_realdata("005930")  # 한국: 6자리 코드
result = _fetch_us_realdata("BAC")        # 미국: 티커

# 토스 API 직접 사용
import scripts.toss_client as tc
candles = tc.get_candles("005930", interval="1d", count=300)
closes = [float(c["closePrice"]) for c in candles if c.get("closePrice")]

# 네이버 일봉 폴백 (토스 실패 시)
import urllib.request, json
from datetime import datetime, timedelta
code = "005930"
end = datetime.now().strftime("%Y%m%d") + "0000"
start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d") + "0000"
url = f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime={start}&endDateTime={end}"
rows = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})).read())
closes = [r["closePrice"] for r in rows if r.get("closePrice")]

# yfinance 폴백 (미국, 토스 실패 시)
import yfinance as yf
hist = yf.Ticker("BAC").history(period="5d").dropna(subset=["Close"])
```

> ⚠️ 국내 종목에 `yf.Ticker("{code}.KS")`를 쓰지 말 것.

- 가격이 실제와 차이나면 → 가격·등락률·MA200·진입/목표/손절·sparkline 모두 일괄 수정.
- **sparkline 빈 배열** `drawMiniChart('mc-N', [], [], [])` → yfinance 20일 종가로 채운다.
- **MA200 계산**: `period="300d"` 필요. 최근 20개 slice 사용.

#### 코스피 마감 브리핑 3대 필수 확인 항목

마감 브리핑 생성·수정 시 `data/latest_kospi_close.json`에서 반드시 확인한다.

**① 시장 폭 (`market_breadth`)** — `up`·`down` 모두 0이면 데이터 미수집.

**② 수급 현황 (`investor_trading`)** — `net`이 null이거나 3개 모두 0이면 오류. 단위: 백만원 (억원 = net / 100).

**③ dpick** — 빈 배열은 네이버 업데이트 전일 수 있는 정상 동작. 16:30 이후 `fetch_closing_kospi.py` 재실행.

#### 데이터 확인 순서 (마감 브리핑 수동 패치 시)

```
1. data/latest_kospi_close.json 열어서 위 3개 필드 확인
2. 0 또는 누락 → python3 scripts/fetch_closing_kospi.py 재실행 (16:30 이후)
3. dpick 빈 배열 → 16:30 이후 재실행
4. 여전히 누락 → 네이버 금융 / KRX 웹에서 수동 확인
5. HTML 직접 수정 → 커밋
6. python3 scripts/generate_html.py --write-list-only 실행
```

### 2. generate_html.py — 분석 데이터 오염 방지 메커니즘

#### analysis_snapshot.json (핵심 보호 장치)

`generate_html.py`는 HTML 생성 시 `web/briefings/{date}/{type}/analysis_snapshot.json`을 함께 커밋한다.
이 스냅샷이 존재하면 이후 재생성 시 `data/analysis_{type}.json` 대신 스냅샷을 우선 사용한다.

```
1순위: web/briefings/{date}/{type}/analysis_snapshot.json  (git-committed, 날짜 고정)
2순위: data/analysis_{type}.json                           (gitignored, 다음 워크플로우가 덮어씀)
```

**날짜 검증 게이트**: 스냅샷 없이 `data/analysis_{type}.json`을 사용할 때,
`generated_at` 날짜가 `--date`와 다르면 즉시 RuntimeError로 발행 중단.
다른 워크플로우 실행으로 오염된 파일이 예측을 덮어쓰는 것을 차단한다.

**재생성 시 안전 순서:**
```bash
# 스냅샷이 있으면 자동으로 올바른 분석 데이터 사용
python3 scripts/generate_html.py --type kospi --date 2026-06-08 --data-file data/latest_kospi.json
```

**⚠️ 같은 날짜 재실행 시 스냅샷이 새 분석을 무음으로 덮는 함정 (2026-07-09 실제 사고, 수정 완료):**

스냅샷 우선 규칙은 "다른 날짜 워크플로우의 오염 방지"가 목적이지만, **같은 날짜에 정정 재실행**을 할 때도 그대로 적용돼 방금 새로 만든 분석이 항상 무시되고 옛 스냅샷이 계속 쓰이는 사고가 있었다(정정 재실행을 해도 데이터만 바뀌고 예측 문구는 옛날 그대로 남음). 원인은 `render_briefing()`이 스냅샷 존재 여부만 보고 무조건 우선했기 때문 — 재실행 의도(정정 vs 단순 재빌드)를 구분하지 못했다.

수정: 스냅샷을 무시하고 최신 `data/analysis_{type}.json`으로 강제 재생성하는 `--force` 플래그 추가. 스냅샷을 실제로 사용할 때는 이제 **경고 로그**를 출력한다(기존엔 완전 무음).

```
generate_html.py --force              스냅샷 무시, 최신 analysis_{type}.json 강제 사용
call_claude.py --render --force-refresh   위 --force를 generate_html.py 서브프로세스에 전달
GitHub Actions workflow_dispatch의 force_refresh=true   kospi/us/kospi-close 3개 잡의 --render 스텝에 --force-refresh 전달
```

**브리핑을 같은 날짜에 정정 재실행할 때는 반드시 `--force-refresh`(또는 GHA의 `force_refresh=true`)를 함께 써야 한다.** 안 쓰면 정정이 조용히 무시된다. 스냅샷 사용 로그(`⚠️ 기존 snapshot 사용`)가 뜨는데 정정을 의도한 상황이라면 플래그 누락을 의심할 것.

**스냅샷 수동 생성 (원복 후 등 스냅샷 없을 때):**
```python
import json
from pathlib import Path
analysis = json.load(open("data/analysis_kospi.json"))
analysis["prediction"] = {"direction": "하락 우위", "up_pct": 20, "confidence": 80}
analysis["generated_at"] = "2026-06-08T07:39:00+09:00"
snap = Path("web/briefings/2026-06-08/kospi/analysis_snapshot.json")
snap.write_text(json.dumps(analysis, ensure_ascii=False, indent=2))
```

#### HTML 재생성 시 덮어쓰기 주의

`generate_html.py --type kospi ...`를 실행하면 해당 날짜 브리핑 HTML이 완전히 재생성된다.
수동으로 가격·sparkline을 수정한 HTML이 있다면 반드시 확인 후 실행할 것.

브리핑 목록 JSON만 갱신할 때:
```bash
python3 scripts/generate_html.py --write-list-only
```

### 3. 에셋 경로 — /v2/ 경로는 완전 삭제됨

모든 CSS·JS·favicon은 `/assets/` 경로를 사용한다. `/v2/assets/`는 삭제됨.
생성된 HTML에서 `/v2/` 경로가 발견되면 즉시 수정한다.

### 4. 브리핑 목록 동적 재구성

`web/assets/main.js`의 `patchBriefingList()`가 페이지 로드 시 `/data/briefings-list.json`을 fetch해 목록 전체를 재구성한다.
- **현재 KST 날짜**를 오늘 카드로 잡는다 (DOM에 박힌 날짜를 쓰지 않는다).
- 오늘 카드 + 과거 행(최근 10일, ready 1개 이상) 전체를 JSON에서 재구성.
- 현재 보고 있는 브리핑만 `is-current`로 강조.
- 주말(토·일): 모든 슬롯 `state: 'empty'`(`—`). "생성 예정" 문구 절대 표시 금지.

`/briefings` 진입 시: `briefings-list.json`에서 가장 최근 `ready` 슬롯 URL로 `location.replace()`. 날짜 내 우선순위: `us > close > kospi`. `vercel.json`에 날짜를 하드코딩하지 않는다.

### 5. 랜딩 페이지 CSS 변수 의존성

`landing.html`의 `:root`에 반드시 아래 매핑이 있어야 한다:

```css
:root {
  --gnb-height: var(--gnb-h, 52px);
}
```

이 변수가 없으면 `.stage-canvas` 높이가 0이 되어 랜딩 페이지 전체가 빈 화면이 된다.

### 6. 예측 섹션 — 항상 열린 상태 유지

`applyTimeCollapse()` 함수의 KST 9시 이후 자동 접힘 로직은 제거됨.
예측 섹션은 항상 열린 상태를 유지해야 한다. 다시 자동 접힘 로직을 추가하지 말 것.

### 7. AI 반도체 위젯 (칩보드)

`web/assets/main.js`의 `loadChipWidget()`이 `/chips/api/prices`를 fetch한다.
이 함수는 `window.addEventListener('load', ...)` 안에서 반드시 호출되어야 한다.

### 8. 텔레그램 발송 금지 조건

작업 완료 알림, 수동 테스트, 개발 중 임시 실행 시 텔레그램을 발송하지 않는다.
구독자 채널이므로 스케줄된 브리핑 외 ad-hoc 발송은 노이즈가 된다.

### 9. 예측 결과 위젯 — 대표/서브 타이틀 구조

`web/assets/main.js`의 장 마감 후 예측 결과 표시 규칙 (`isAfterMarket()` 블록):

- **대표 타이틀** (`lsb-head-em`): "오늘 장이 종료됐어요." 고정 문구 사용 금지.
- **서브 타이틀** (`lsb-sub`): `nn% 하락 마감이에요.` 형식.
- **hit.dn (하락 예측 적중)**: 아쉬움 표현 반드시 붙임. 예: "하락 예측이 맞았어요. 아쉬운 하루였어요."
- **hit.up (상승 예측 적중)**: "상승 예측이 맞았어요."로만.
- CLOSE_MSGS 구조: 각 케이스마다 `title` 배열과 `sub` 배열 분리 관리.

### 10. 브리핑 라이브 패널 — 구조와 운영 규칙

> **라이브 스코어보드는 2026-07-26에 코드째 제거됐다.** `initLiveScoreboard()`(413줄)와
> `sections/_live_scoreboard.html`이 있었지만, 그 섹션은 `scripts/config/*.json`의 섹션 목록에
> **한 번도 들어간 적이 없어**(`git log -S`로 확인) 발행 페이지에 `#live-scoreboard`가 생성되지
> 않았다. 즉 함수는 매 로드마다 조기 return만 하는 죽은 코드였고, 그 안에는 정의조차 없는
> `fetchNews()` 호출이 남아 있었다(되살렸다면 즉시 ReferenceError). 이 문서가 동작 명세를
> 상세히 적고 있어 살아 있는 기능처럼 보였던 것이 발견을 늦췄다 — **문서가 코드보다 오래
> 사는 상황을 경계할 것.** 복구가 필요하면 git 이력에서 꺼낸다.
>
> 현재 브리핑에서 실제로 동작하는 라이브 패널은 아래 셋이다.
> `initLiveMarketPanel()`(시장 지표), `initNowBand()`(지금 코스피 밴드), `initSidebarSignals()`(특이 신호).

#### 시장 지표 패널 (`initLiveMarketPanel()`)

| 영역                  | 데이터 소스 | 갱신 주기 |
| ------------------- | ----------- | ------- |
| 코스피 지수 · 등락률        | `/api/kospi-live` | 10초 |
| 코스피200 · 코스닥 · 원/달러 | `/api/market` | 60초 |
| 수급 (외국인·기관·개인)      | `/api/market` | 60초 |
| 장중 뉴스 이슈            | `/data/kospi-news-live.json` | 5분 |
| 스파크라인 그래프           | 인메모리 누적 + sessionStorage 복원 | 폴링 시 자동 |

**수급 표시 순서: 개인 → 기관 → 외국인 (변경 금지. 한국 투자자 관점 기준)**

#### 스파크라인 규칙

- 색상: 상승=빨강(`#E03131`), 하락=파랑(`#2775ED`) — 첫 값 대비 현재값으로 자동 결정
- 시작가 기준 점선을 그려 흐름 맥락 제공
- `sessionStorage('mkt-spark-v1')`에 저장 — 새로고침 후에도 즉시 복원
- 슬라이딩 윈도우 최대 30개 누적

#### 이슈 브리핑 수집 스케줄 (평일 기준, KST)

| 구간 | 주기 | 슬롯 |
| --- | --- | --- |
| 09:10 ~ 15:00 | 30분 | `MARKET` |
| 16:35 ~ 21:00 | 1시간 | `POST_MARKET` |
| 21:30 ~ 01:00 | 1시간 | `US_MARKET` |

총 22회/일. Vercel cron 사용 금지 (Hobby 플랜 cron 2개 제한).
트리거는 **cron-job.org → GitHub API dispatch**(`workflow_dispatch`). 2026-06-08에 GHA native schedule에서 전환됨([kospi-news-live.yml](../.github/workflows/kospi-news-live.yml) 헤더 주석이 정본).

#### 종목 뉴스(`fetch_stock_news.py`) 수집 스케줄 — 평일/주말 이원화

주도주 위젯 "관련 뉴스"(`web/data/stock-news.json`)는 **이슈 브리핑과 다른 스케줄**로 돈다. 평일은 이슈 브리핑 워크플로우에 얹혀 있고, 주말은 전용 워크플로우가 담당한다.

| 요일 | 구간 (KST) | 주기 | 담당 워크플로우 | 트리거 |
| --- | --- | --- | --- | --- |
| 평일 | 09:00 ~ 15:30 | 30분 | `kospi-news-live.yml` | cron-job.org |
| 평일 | 16:35 ~ 23:30 | 1시간 | `kospi-news-live.yml` | cron-job.org |
| **주말(토·일)** | **09:00 ~ 21:00** | **3시간** (09·12·15·18·21시, 5회/일) | **`stock-news-weekend.yml`** | **GHA native cron** |
| 주말 | 21:00 ~ 익일 09:00 | 수집 없음 | — | — |
| 공휴일(평일) | 종일 | 수집 없음 | — | — |

**주말 워크플로우가 `fetch_stock_news.py`만 실행하는 이유 (다른 스크립트를 추가하지 말 것):**

- `fetch_news_live.py` — `get_slot()`이 **시각만** 보고 요일을 안 본다. 토요일 12시에 `MARKET`을 반환해 **휴장일인데 "장중 이슈"를 발행**한다.
- `fetch_movers_why.py` — 요일 게이팅이 없어 주말에 movers 데이터를 덮어쓴다. 이 파일들의 소유자는 `kospi-news-live.yml`이다(§18 파일 소유권 충돌).

주말 워크플로우는 `git add web/data/stock-news.json` **한 파일만** 커밋한다. 넓은 경로를 통째로 add 하면 §18 사고가 재발한다.

**GHA cron 지연 발화 방어**: GHA native cron은 지연 발화가 잦아 평일 새벽으로 밀릴 수 있다. 워크플로우 첫 스텝에서 `TZ=Asia/Seoul date +%u`로 실제 실행 시점의 요일을 재확인하고, 주말이 아니면 이후 스텝을 전부 건너뛴다. **cron 표현식만 믿지 않는다.**

**화면 표기와 스케줄의 1:1 대응 (필수)**: `web/stocks/index.html`의 `setNight()`이 `#lw-upd`에 갱신 주기를 표기한다. 위 표가 정본이며, **스케줄을 바꾸면 이 표기도 같이 바꾼다.** 수집이 없는 구간(주말 심야·공휴일)에는 주기를 적지 않고 "최신순"만 표기한다 — 실제로 돌지 않는 주기를 광고하지 않는다(운영 규칙 0). 2026-07-18 실사고: 주말에 수집이 0건인데 "1시간 주기"가 그대로 떠 있었다.

**`get_slot()` 시간대 경계값:**
```
09:00~15:29 KST → MARKET
16:35~21:29 KST → POST_MARKET
21:30~01:00 KST → US_MARKET
```

#### 이슈 브리핑 섹션 — 브리핑 페이지에서는 제거됨 (수집은 계속한다)

> **브리핑 페이지의 이슈 브리핑 섹션은 2026-07-26에 코드째 제거됐다.** `initIssueBriefing()`(160줄)과
> `sections/_issue_briefing.html`이 있었지만, 마감 브리핑에서 include를 뺀 2026-07-10 이후
> **어느 템플릿에서도 include되지 않아** `#issue-briefing-wrap`이 생성되지 않았다(라이브 코스피
> 브리핑 HTML에서 0건 확인). 스코어보드와 같은 죽은 코드 상태였다.
>
> **⚠️ 수집 파이프라인(`fetch_news_live.py`, 하루 22회)은 계속 필요하다 — 끄지 말 것.**
> 산출물 `kospi-news-{date}.json`·`kospi-news-live.json`을 아래가 실제로 소비한다.
> - `main.js` `initNowBand()` — 브리핑 상단 "지금 코스피" 밴드의 장중 뉴스 이슈
> - `stocks-home.js` / `web/stocks/index.html` — 종목 홈 브리핑 스트립(§13 `issue` 슬롯)
>
> `fetch_news_live.py`는 `slot == "POST_MARKET"`이면 RSS 수집·Gemini 호출 없이 즉시 종료한다
> (2026-07-10, API 비용 차단). 같은 job의 `fetch_movers_why.py`(사이드바 "코스피 주도주" 위젯
> 데이터)는 계속 정상 실행 — 스케줄 자체(cron-job.org "장 후" 트리거)를 끄면 그 데이터도 같이
> 끊기므로 유지한다.

**수집 구조 — RSS 기반 2단계 파이프라인 (2026-06-16 적용):**

1단계: Google News RSS로 오늘 날짜 기사 실수집 (날짜·제목 실데이터).
2단계: Gemini(`google_search` 미사용)가 목록에서 선별 + 요약만 담당.

- 날짜 세탁 원천 차단: pub_date 는 RSS 가 보장 → Gemini 가 날짜를 만들 수 없음.
- 슬롯별 RSS 소스: `_GN_KR` (한국어 Google News RSS), `_GN_EN` (영어 Google News RSS).
- 오늘 날짜 기사가 2건 미만이면 발행 생략 (exit 0).

**이슈 중복 방지**: 오늘 기발행 타이틀 목록을 Gemini 프롬프트에 주입해 동일 주제를 피하도록 유도.

**[상시 룰] 새 이슈가 없으면 콘텐츠는 그대로, 최신 항목의 시각만 현재화한다 (2026-07-23 도입):**

기존엔 신규 기사가 없으면(①RSS 자체가 2건 미만 ②기존 발행분과 55% 이상 유사해 중복 제거 후 2건 미만 ③Gemini 4회 재시도까지 전부 중복) `sys.exit(0)`으로 조용히 발행을 생략했다. 이 자체는 §0(없는 이슈를 지어내지 않는다) 원칙상 맞는 동작이지만, 부작용으로 "오늘 장중 이슈" 목록이 마지막 발행 시각에 몇 시간씩 멈춰 있어 사용자에게는 파이프라인이 죽은 것처럼 보였다(2026-07-23 실사고 조사 — 12:30 이후 15:00까지 세 차례 정상 실행됐으나 전부 스킵, 국내 언론이 같은 "외국인 순매수·7000선 회복" 서사를 반복 재보도했을 뿐 실제 신규 소재가 없었음이 확인됨).

- 해결: `_bump_latest_time()` — 위 세 스킵 지점 모두에서 새 history 항목을 추가하지 않고, **`history[0]`(최신 항목)의 `time`과 최상위 `updated_at`만 현재 시각으로 덮어쓴다.** `market`/`stock`의 제목·본문 등 콘텐츠는 절대 건드리지 않는다 — "이 시각까지 확인했지만 여전히 같은 이슈가 최신"이라는 사실만 반영한다.
- `kospi-news-live.json`뿐 아니라 소비처(`initNowBand()`·종목 홈 브리핑 스트립)가 우선 읽는 날짜별 아카이브 `kospi-news-{date}.json`도 함께 갱신한다 — live만 갱신하면 화면엔 여전히 옛 시각으로 남는다.
- 오늘자 데이터 자체가 없으면(당일 첫 발행 전) 아무것도 하지 않는다 — 갱신할 대상이 없다.
- 워크플로우(`kospi-news-live.yml`)의 커밋 스텝은 이미 두 파일을 전부 `git add` 대상에 포함하고 `git diff --cached`가 비어있지 않으면 커밋하므로, 이 변경만으로 스킵 시에도 "시각 갱신" 커밋이 자동으로 만들어진다(워크플로우 수정 불필요).
- 테스트: `scripts/test_bump_latest_time.py` — 오늘자 없음(False)·오늘자 있음(시각만 갱신, 콘텐츠·seen_titles 불변, history 개수 불변)·아카이브 동시 갱신·날짜 다름(안 건드림)·history 없음(False) 5케이스.

**코스피 지수 레벨 자동 검증 (MARKET 슬롯)**: 기사 수집 후 yfinance `^KS11`으로 코스피 직전 종가를 조회해, 기사 제목에 언급된 지수 레벨이 실제 수준의 ±30% 이탈하면 재시도한다.
- 구현: `_get_kospi_ref()` + `_is_wrong_index_level()`.
- 패턴: `(\d{3,4})[선포]` (예: "2600선", "8700포인트") 추출 후 비교.

**잘못된 이슈 수동 삭제**: `kospi-news-{date}.json` 및 `kospi-news-live.json`의 `history` 배열에서 오래된 날짜·잘못된 수치를 담은 항목은 즉시 삭제 후 커밋한다.
- 삭제 기준: 날짜가 틀렸거나, 지수·가격이 당일 실제 수준과 현저히 다른 항목.
- `history` 항목 삭제 후 JSON 문법(trailing comma) 반드시 확인.

**데이터 아카이브 파이프라인:**
```
fetch_news_live.py → web/data/kospi-news-live.json (당일 갱신)
                   → web/data/kospi-news-{date}.json (날짜별 아카이브)

check_accuracy.py → data/briefings.json (actual_change_pct 기록)
                  → web/briefings/{date}/kospi/index.html (data-actual-pct 주입)
                  → web/data/market-{date}.json (코스피·코스닥·코스피200·수급)
```

### 11. 월가 코멘트 섹션 (`analyst_quotes`) — 운영 규칙

미국 시장 브리핑 전용 섹션. 발언이 없으면 섹션 전체 생략 (빈 상태 표시 금지).

- **발언 생성·추론 금지.** `fetch_analyst_quotes.py`가 google_search에서 실제로 찾은 발언만 표시한다.
- **URL hallucination 금지.** Gemini에게 URL을 직접 생성하도록 시키지 않는다. URL은 반드시 Gemini `grounding_metadata.grounding_chunks`에서 추출한다. 프롬프트에 URL 필드를 요청하면 존재하지 않는 URL이 생성된다.
- **grounding URL은 반드시 즉시 리졸브한다.** `grounding_chunks[].web.uri`는 `vertexaisearch.cloud.google.com/grounding-api-redirect/...` 형태의 **임시 리다이렉트 토큰**이라 시간이 지나면(정적 페이지를 나중에 열람할 때) 만료되어 존재하지 않는 페이지로 뜬다. `fetch_analyst_quotes.py`의 `_resolve_redirect()`가 수집 시점에 즉시 한 번 따라가 실제 최종 기사 URL(예: `yna.co.kr/view/...`)로 치환해 저장한다 — 링크가 영구적이고 브라우저에 목적지 도메인이 명확히 보인다. 리졸브 실패(타임아웃·차단 등) 시 해당 URL은 버리고(빈 문자열) 폴백으로 넘어간다 — 깨진 링크를 저장하지 않는다.
- **출처 링크 우선순위**: `url` 필드(리졸브된 원본 링크)가 있으면 그 링크, 없으면 `이름 + source + time_label` 구글 검색 폴백. `generate_html.py`의 `build_analyst_quotes()`가 처리.
- **수동 재수집**: `python3 scripts/fetch_analyst_quotes.py` 실행 후 `generate_html.py`로 재생성.
- **발언이 없는 날**: `data/analyst_quotes.json`이 `[]`이면 섹션이 자동으로 생략된다. 정상 동작.
- **감성 뱃지**: `bull`(강세) / `bear`(약세) / `neu`(중립) 세 가지만 허용. 다른 값은 스크립트가 자동으로 `neu`로 정규화한다.
- **섹션 순서**: 미국 브리핑 기준 reasons → 구분선 → `analyst_quotes` → `watchpoints` → `stock_picks`.

### 12. 커밋 단위

- 한 논리적 변경 = 한 커밋. 여러 파일을 고쳤더라도 같은 목적이면 하나로 묶는다.
- HTML 수동 패치(가격 보정, sparkline 추가 등)는 커밋 메시지에 종목명·수정 내용을 명시한다.
- 브리핑 자동 생성 커밋(`📊 코스피 브리핑: ...`)과 수동 수정 커밋은 구분한다.

### 13. 종목 대시보드 브리핑 스트립 — 타임테이블 (룰 고정)

`web/stocks/index.html`의 `#brief-strip`(더블샷 브리핑 연결 영역)은 현재 KST 시각에 따라 노출 내용을 바꾼다. `getKSTSlot()` + `renderBriefStrip()`이 담당하며 **5분마다 재평가**한다.

| 시간대 (KST, 평일) | 슬롯 | 노출 내용 |
| --- | --- | --- |
| 07:30 ~ 09:00 | `kospi` | 코스피 예측 브리핑 타이틀 |
| 09:00 ~ 16:30 | `issue` | 장중 이슈 브리핑 (`kospi-news-{date}.json`의 `latest`, 30분 갱신마다 타이틀 변경) |
| 16:30 ~ 21:20 | `close` | 코스피 마감 브리핑 타이틀 |
| 21:20 ~ 23:00 | `us` | 미국 시장 예측 브리핑 타이틀 |
| 23:00 ~ 익일 07:30 | `none` | **영역 제거** (`is-hidden`) |
| 주말·휴일 | `none` | **영역 제거** |

- **stale 날짜 폴백 금지.** 각 슬롯은 "오늘(`kstDateStr()`) 해당 타입이 `briefings-list.json`에서 `state==='ready'`"일 때만 표시한다. 과거 날짜 브리핑으로 폴백하지 않는다 (생성 시점에 박힌 정적 HTML 값도 신뢰 금지 — 초기 `is-hidden`으로 두고 JS가 채운다).
- **휴일 처리**: 한국 공휴일엔 코스피 슬롯(`kospi`·`issue`·`close`)은 `krIsKospiHoliday()`로 자동 숨김. **단 미국 예측(`us`) 슬롯은 한국 공휴일 여부와 무관하게 KST 평일이면 노출한다** — 미국장은 제헌절 등 한국 공휴일에도 열려 미국 브리핑이 발행되기 때문(2026-07-17 제헌절 실사고로 확정). `slotNow()`에서 `us`만 `isWeekday()`(한국 거래일) 게이트에서 분리하고, 실제 노출 여부는 `render()`의 `state==='ready'`가 최종 판정(미국 휴장일엔 당일 us가 ready가 아니라 자동 숨김).
- **issue 슬롯**: 이슈 미수집(예: 09:00~첫 수집 전)이면 오늘 kospi 예측으로 폴백, 그것도 없으면 숨김. 클릭 시 `/briefings/{date}/kospi/`로 이동.
- `getKSTSlot` 경계값을 임의로 바꾸지 말 것. 위 표가 정본이다.

### 14. 코스피 마감 브리핑 — 증권가 시황 섹션

`close.html` 템플릿의 "오늘 증권가 시황"(`close_research.html`) 섹션.

- `research_reports.json` 기반. 발행 시점 필터·숫자 가드는 위 `fetch_research_reports.py` 규칙 참조. **해요체 고정**.
- `generate_html.py`에서 날짜 불일치 시(`date != target_date`) 표시하지 않는다 — 이전 실행의 잔존 파일이 다른 날짜 브리핑을 오염시키는 것을 방지.
- `kospi-close-briefing` job 순서: `fetch_closing_kospi.py` → `fetch_news.py` → `fetch_movers_why.py` → `fetch_research_reports.py` → `call_claude.py`. `fetch_research_reports.py`는 `continue-on-error: true` — 실패해도 마감 브리핑 발행 자체는 막지 않는다.

> "오늘의 화제 종목"(`close_movers.html`, `movers-why-{date}.json` 기반) 섹션은 2026-07-03 제거됨 — 모든 브리핑 사이드바의 "코스피 주도주" 위젯(main.js `loadLeadersWidget()`)이 같은 데이터로 실시간 곡선·뉴스 핀을 이미 보여주고 있어 본문 중복이었다. `fetch_movers_why.py`와 그 데이터 파일은 그대로 유지 — 사이드바 위젯이 계속 소비한다.

### 15. 배포 사고 대응 — Vercel 자동배포 조용한 취소 (2026-07-03)

**증상**: `git push`는 성공하고 `data/*.json`·커밋 내역도 정상인데, `doubleshot.space`에는 반영이 안 됨. `vercel ls`로 보면 최근 프로덕션 배포들이 빌드 없이(`Build [0ms]`) 곧바로 `Canceled` 상태로 끝나 있음 — 에러도 아니고 조용히 실패해서 알아차리기 어렵다.

**발견한 원인 한 가지**: `.github/workflows/deploy.yml`의 주석("`web/data/` 변경은 제외 — kospi-news-live.yml이 직접 배포")과 실제 `paths` 목록이 어긋나 있었다 — `web/data/**`가 여전히 트리거 경로에 남아 있어서, `kospi-news-live.yml`이 데이터 커밋을 푸시할 때마다 **같은 push에 대해 배포 이벤트가 중복 발생**했다. 이 커밋(2026-07-03)에서 `paths`에서 `web/data/**`를 제거해 주석과 일치시켰다. 다만 이게 Vercel 취소의 유일한 원인인지는 대시보드 접근 없이 100% 확정하지 못했다 — 재발 가능성 있음.

**재발 감지 — 자동화됨**: `kospi-news-live.yml`에 "🔍 프로덕션 배포 반영 확인" 스텝 추가. 푸시 후 30초 대기, `doubleshot.space/data/kospi-news-live.json`의 `updated_at`을 방금 커밋한 로컬 값과 대조. 불일치 시 `VERCEL_TOKEN` 시크릿이 있으면 `vercel deploy --prod`로 자동 복구 시도, 그리고 `TELEGRAM_ADMIN_CHAT_ID`로 관리자 알림 발송. `VERCEL_TOKEN`을 GitHub Secrets에 추가하면 자동 복구까지 되고, 없으면 알림만 온다(Vercel 계정 설정 → Tokens에서 발급).

**두 번째 근본 원인 확정 (2026-07-06)**: 위 자동 복구가 매번 실패해 텔레그램 알림이 계속 반복 발송되는 사고 발생. 원인은 **자동 복구가 엉뚱한 Vercel 프로젝트에 배포하고 있었기 때문**이다. 이 GitHub 저장소의 실제 이름은 `pulum0083/daily30`인데(로컬 디렉터리명 `double-shot`과 다름), `kospi-news-live.yml`의 복구 스텝은 매번 새 체크아웃에서 `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` 없이 `vercel deploy --prod`를 돌렸다. 프로젝트 링크가 없는 상태에서 Vercel CLI는 저장소/디렉터리 이름으로 프로젝트를 자동 매칭하는데, 이때 `daily30`이라는 이름의 (실제로는 `doubleshot.space`와 무관한) 별개 프로젝트로 연결돼버렸다. 즉 복구 배포가 `daily30-seven.vercel.app`에는 매번 성공하면서 정작 `doubleshot.space`(별도 프로젝트 `double-shot`, ID `prj_XRVsCkXlroRpbd9WVPgtH3OiE6Fo`, org `team_iPwo9taZIskxdoXOJu9assy2` 소속)는 전혀 갱신되지 않아, 미반영이 영구화되고 알림이 매 실행마다 반복됐다. 해결: 복구 스텝 env에 `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID`를 `double-shot` 프로젝트로 명시 고정 + 복구 시도 후 재확인해서 실제 반영됐으면 알림을 생략하도록 수정. **Vercel 프로젝트/도메인 관련 자동화를 새로 추가할 때는 항상 프로젝트를 명시적으로 고정할 것 — 저장소 이름과 도메인이 연결된 프로젝트명이 다르면 CLI의 자동 매칭을 신뢰하지 말 것.**

**수동 복구 (알림 받았을 때)**:
```bash
vercel ls                 # 최근 배포가 Canceled인지 확인
vercel --prod --yes       # CLI로 강제 배포 — git 웹훅 우회, 즉시 반영됨
curl -s https://doubleshot.space/data/kospi-news-live.json | python3 -m json.tool  # 반영 확인
```

**점검 순서**: ① `git log origin/main` — 커밋이 실제로 푸시됐는지. ② `vercel ls` — 최근 배포 상태(Canceled/Ready/Error). ③ Canceled면 위 수동 복구. ④ 반복되면 `.github/workflows/*.yml`에서 같은 push 경로에 걸리는 다른 워크플로우가 늘었는지(중복 트리거) 확인.

**세 번째·최종 근본 원인 확정 (2026-07-07) — git-트리거 자동배포는 항상 BLOCKED된다**: "가끔 취소된다"가 아니라, **git 커밋으로 트리거되는 Vercel 자동배포는 예외 없이 매번 막힌다**는 사실을 Vercel API로 직접 확인했다(`vercel inspect <url> --json`의 `readyState`가 `BLOCKED`, GitHub 체크에는 "Vercel - No GitHub account was found matching the commit author email address"). 최근 배포 40개를 `GET /v6/deployments`로 조회한 결과 27개가 `BLOCKED`, 나머지 13개는 전부 사람이 CLI로 수동 `vercel --prod`를 돌린 것이었다 — 즉 지금까지 사이트가 갱신된 적은 전부 수동 복구 덕분이었고, 자동배포는 단 한 번도 성공한 적이 없었다.

원인: 이 저장소의 모든 자동 커밋이 봇 이메일(`dailyb-bot@users.noreply.github.com`)로 이뤄지는데, 이 이메일이 어떤 Vercel 계정과도 연결돼 있지 않다. Vercel은 git 커밋 작성자를 계정과 매칭하지 못하면 배포를 자동으로 `BLOCKED` 처리한다(빌드 성공 여부와 무관 — 애초에 빌드가 시작되지도 않는 경우가 대부분). 반면 `vercel deploy --token=...`(CLI/API 토큰 기반 배포)는 이 커밋-작성자 검증을 받지 않으므로 항상 정상 배포된다.

**조치 (2026-07-07)**:
- `.github/workflows/vercel-deploy.yml` 신설 — `main`에 대한 **모든 push**(경로 제한 없음, 어떤 워크플로우/수동 push든 상관없이)에서 무조건 `vercel deploy --prod --yes --token "$VERCEL_TOKEN"` 실행. `VERCEL_ORG_ID`/`VERCEL_PROJECT_ID`를 `double-shot` 프로젝트로 명시 고정(위 문단과 동일 이유). 실패 시에만 관리자 텔레그램 알림.
- `kospi-news-live.yml`의 자체 "확인 후 복구" 스텝은 제거 — 위 워크플로우가 모든 push를 공용으로 처리하므로 중복 배포를 막기 위함.
- `scripts/vercel-ignore-build.sh`를 항상 `exit 0`(배포 스킵)으로 변경 — git-트리거 배포는 이제 시도해봐야 항상 BLOCKED로 낭비될 뿐이라(무료 플랜 "일 100회 배포" 한도 소모), 아예 시도하지 않도록 껐다. 프로덕션 배포는 100% `vercel-deploy.yml`이 담당한다.
- **향후 이 저장소에 새 자동 커밋 워크플로우를 추가할 때, 별도로 Vercel 배포 스텝을 넣을 필요 없다** — `main` push만 되면 `vercel-deploy.yml`이 알아서 배포한다.

### 16. 텔레그램 "지난 예측" 배지 — 미채점 예측을 옛 결과로 대체하지 않는다 (2026-07-14 실사고)

**증상**: 2026-07-14 07:28 KST 코스피 예측 브리핑 텔레그램에 "지난 예측 ✓ 적중" 배지가 떴지만, 실제 어제(2026-07-13) 예측은 "상승 우위"(신뢰도 66%)였고 코스피는 "검은 월요일" **-8.95% 급락**(6806.93, 서킷브레이커 7회)으로 마감해 명백히 빗나갔다. 배지는 거짓이 아니라 **오래된(2026-07-10) 채점 결과를 조용히 대신 보여준 것**이었다.

**근본 원인**: `check_accuracy.py --backfill`은 매일 09:10 KST(화~토)에 실행되는데, 코스피 아침 브리핑·텔레그램 발송은 07:25~07:30 KST — **항상 그보다 먼저** 나간다. 즉 텔레그램이 만들어지는 시점엔 어제 예측이 구조적으로 항상 미채점(`is_correct: None`) 상태다. `scripts/call_claude.py`의 `_last_scored_result()`는 원래 "가장 최근 **채점된**" 항목을 찾도록 짜여 있어서, 어제 항목이 미채점이면 그보다 더 과거의 채점된 항목으로 조용히 건너뛰고, 그 결과를 날짜 구분 없이 그냥 "지난 예측"이라는 이름으로 표시했다.

**수정**: `_last_scored_result()`가 "가장 최근 **항목**"(채점 여부 무관)만 보도록 바꿨다. 그 항목이 아직 미채점이면 `None`을 반환하고, `save_telegram_message()`는 `None`일 때 배지 자체를 생략한다 — 옛 결과로 대체하지 않는다. 테스트: `scripts/test_last_scored_result.py`.

- **방지 룰**: "지난 예측" 류의 배지·요약 문구를 만들 때는 반드시 "그 라벨이 가리키는 대상이 실제로 최근 항목인지"를 확인하고, 최근 항목이 없거나 조건(채점 완료 등)을 못 채우면 **더 오래된 데이터로 대체 표시하지 말고 생략**한다. 스케줄 순서상 특정 데이터가 항상 늦게 채워지는 구조(이 경우 accuracy 체크가 항상 아침 브리핑보다 늦음)라면, 그 사실을 코드 주석에 명시하고 "아직 없음"과 "오래된 값으로 대체"를 절대 혼동하지 않는다.
- **재발 시 진단 순서**: ① 텔레그램에 나온 배지·수치가 정말 "가장 최근" 데이터를 가리키는지 `data/briefings.json`(또는 해당 데이터 소스)에서 날짜를 직접 대조. ② 가장 최근 항목이 미채점/미생성 상태인데 배지가 떴다면, 그 배지를 만드는 함수가 조건 미충족 시 조용히 더 과거 데이터로 폴백하는지 확인. ③ 폴백 로직이 있다면 제거하고 "생략"으로 바꾼다 — 완전성보다 정합성이 우선이다(운영 규칙 0).
- **범위**: 이미 발송된 2026-07-14 07:28 텔레그램 메시지 자체는 되돌릴 수 없다(텔레그램은 정해진 스케줄에만 발송 — ad-hoc 정정 메시지를 임의로 보내지 않는다). 다음 발송부터 정상화된다.

### 17. 코스피 마감 브리핑 발행 파이프라인 완전 정지 (2026-07-14 실사고, 수정 완료)

**증상**: 16:25 KST에 시작한 `kospi-close-briefing` 잡이 데이터 수집·분석·검증·HTML 생성까지 전부 정상 완료했는데도, "🔎 상세 페이지 라이브 확인" 스텝에서 20분 이상 멈춰 텔레그램·이메일이 발송되지 않았다. 이 스텝은 재시도 상한이 없어 방치하면 GitHub Actions 기본 잡 타임아웃(6시간)까지 계속 돌 수 있었다.

**근본 원인 두 가지가 겹침:**

1. **커밋 push 실패가 조용히 무시됨**: "💾 HTML & 데이터 커밋 → main 푸시" 스텝의 5회 재시도 루프(`for i in 1 2 3 4 5`)가 실패 후 `exit 1` 없이 끝나는 구조라, 5번 다 실패해도 스텝이 성공 처리됐다. 오늘 실제로 같은 워크플로우 실행 안에서 동시에 돌던 "코스피 장중 뉴스 갱신" 잡의 16:36 push와 경합해 5회 모두 실패했다. 결과: 마감 브리핑 커밋이 `origin/main`에 올라가지 못했다.
2. **존재하지 않는 SHA로 Vercel 배포 시도**: 다음 스텝이 `git rev-parse HEAD`(원격에 없는 로컬 전용 커밋)로 `vercel-deploy.yml`을 dispatch했고, 체크아웃이 `fatal: remote error: upload-pack: not our ref ...`로 실패했다 — `doubleshot.space`는 갱신되지 않음.
3. **GitHub Pages 자체가 이 저장소에서 비활성화 상태**(`gh api repos/pulum0083/daily30 -q .has_pages` → `false`)인데, `check_page_live.py`는 `pulum0083.github.io/daily30` URL이 "CDN 반영 지연"인 줄 알고 무제한(10초 간격) 재시도했다. `gh-pages` 브랜치(peaceiris 배포는 git push 성공 여부와 무관하게 직접 파일시스템에서 푸시됨)에는 오늘자 콘텐츠가 정상적으로 있었지만, Pages 사이트 자체가 꺼져 있어 그 URL은 영원히 404였다.

**복구**: `gh-pages` 브랜치에서 오늘자 `web/briefings/2026-07-14/close/`(index.html + analysis_snapshot.json)와 관련 데이터 파일을 로컬로 가져와 `main`에 커밋·푸시 → `vercel deploy --prod`로 수동 배포 → 텔레그램은 로컬 네트워크(사내 프록시)가 Telegram API TLS를 막고 있어 1회성 GitHub Actions 워크플로우로 발송(사용 후 삭제).

**수정** (재발 방지):
- `daily_report.yml`의 커밋-push 재시도 루프 5곳(코스피/미국/마감 브리핑, 정확도 백필, 장중 뉴스 갱신) 모두 5회 실패 시 `exit 1`로 명시적으로 중단하도록 수정 — 무음 실패로 다음 스텝(존재하지 않는 SHA로 배포 트리거)이 이어지는 것을 차단.
- `check_page_live.py`: 확인 대상을 죽은 GitHub Pages URL 대신 실제 서비스 URL(`doubleshot.space`)로 변경, 재시도 상한을 최대 10분(60회)으로 둠. 상한 초과 시 `exit 1`로 명시 실패(무음 스킵 아님).

- **방지 룰**: 커밋 push를 재시도 루프로 감쌀 때는 반드시 루프 종료 후 성공 여부를 확인하고 실패 시 잡을 중단한다(다음 스텝이 그 커밋의 SHA를 전제로 동작하는 한 특히). "무제한 재시도로 조기 포기를 막는다"는 설계(2026-07-06 사고 방지용)를 적용할 때는, 그 대상이 애초에 살아날 수 있는 것인지(예: Pages가 활성화돼 있는지) 먼저 확인 — 상한 없는 재시도는 "느린 성공"과 "영원한 실패"를 구분하지 못한다.
- **재발 시 진단 순서**: ① `gh run view <run-id>`로 어느 스텝에서 멈췄는지 확인. ② 그 스텝이 재시도 루프면 대상 URL/리소스가 원리적으로 존재하는지 직접 확인(`curl`, `gh api repos/.../has_pages` 등). ③ 커밋 push 스텝이 ✓(성공)인데 이후 스텝이 이상하면 `git log origin/main`으로 실제로 반영됐는지 직접 대조 — 스텝의 성공 표시를 신뢰하지 않는다.

### 18. 마감 브리핑 커밋이 movers-why 파일 경합으로 재차 발행 중단 (2026-07-15 실사고, 수정 완료)

**증상**: 16:25 KST `kospi-close-briefing` 잡이 데이터 수집·분석·검증·HTML 생성까지 전부 정상 완료했는데, "💾 HTML & 데이터 커밋 → main 푸시" 스텝이 5회 rebase 재시도 모두 동일하게 실패 → §17에서 추가한 `exit 1` 가드가 정상 작동해 잡이 깨끗하게 중단됐지만, 그 결과로 **그날 마감 브리핑(HTML·텔레그램·이메일)이 통째로 발행되지 못하고 유실**됐다(`doubleshot.space/briefings/2026-07-15/close/` → 404로 확인).

**근본 원인**: `kospi-close-briefing` 잡의 "🗞️ 코스피 주도주 뉴스 근거(종가 기준)" 스텝이 `fetch_movers_why.py`로 `web/data/movers-why-{date}.json`·`movers-why-live.json`을 직접 재생성하고, 이후 "💾 HTML & 데이터 커밋" 스텝이 `git add web/ data/`로 이 파일들을 같이 커밋했다. 그런데 같은 시각(16:35~) cron-job.org가 트리거하는 별도 워크플로우 [kospi-news-live.yml](../.github/workflows/kospi-news-live.yml)("이슈 브리핑 수집")도 **같은 파일들**을 독립적으로 `fetch_movers_why.py`로 재수집·커밋한다(POST_MARKET 슬롯, §10 참조). 두 워크플로우가 매번 같은 JSON 파일을 통째로 다른 값으로 재작성하므로 git이 자동 병합을 못 하고, rebase를 몇 번을 재시도해도 **매번 동일한 충돌**이 재현됐다(일시적 경합이 아니라 구조적으로 항상 재현되는 충돌).

`movers-why-*.json`은 `generate_html.py`·`call_claude.py` 어디서도 읽지 않는다 — 사이드바 "코스피 주도주" 위젯이 클라이언트에서 직접 fetch하는 독립 데이터이며, §10 기준 원 소유자는 `kospi-news-live.yml`이다. 즉 `kospi-close-briefing` 잡이 이 파일을 커밋할 이유가 애초에 없었다.

**1차 수정 시도(버그)**: `git add web/ data/ ':(exclude,glob)web/data/movers-why-*.json'`로 스테이징에서만 제외했더니, 워킹트리에는 여전히 unstaged 변경이 남아 `git rebase`가 겹치는 파일이 없어도 `cannot rebase: you have unstaged changes`로 즉시 거부됨 — 같은 스텝이 다른 원인으로 다시 5회 실패했다.

**최종 수정**: [daily_report.yml](../.github/workflows/daily_report.yml) `git add` 직전에 `git checkout -- web/data/movers-why-*.json 2>/dev/null || true`를 추가해 이 잡이 로컬에서 만든 movers-why 변경분을 커밋 전에 완전히 폐기 — 워킹트리를 깨끗한 상태로 만들어 rebase도 정상 동작하고 애초에 충돌 소지 자체가 사라진다. 재실행([run 29399172821](https://github.com/pulum0083/daily30/actions/runs/29399172821))으로 정상 발행 확인.

- **방지 룰**: 한 워크플로우가 `git add web/ data/`처럼 넓은 경로를 통째로 커밋할 때, 그 안에 **다른 워크플로우가 독립 스케줄로 소유·커밋하는 파일**이 섞여 있으면 안 된다. 잡 안에서 그 파일을 스크립트가 재생성했더라도(다른 목적의 부수 효과라도) 커밋 직전에 `git checkout --`으로 폐기해 워킹트리를 깨끗하게 유지할 것. **`git add`에서 pathspec으로 제외하는 것만으로는 부족하다** — `git rebase`는 대상 파일이 겹치지 않아도 unstaged 변경이 하나라도 있으면 무조건 거부한다.
- **재발 시 진단 순서**: ① 실패 로그에서 `CONFLICT`(내용 충돌)인지 `cannot rebase: you have unstaged changes`(워킹트리 오염)인지 구분 — 원인이 다르다. ② `CONFLICT`면 `git log origin/main`으로 같은 시각에 같은 파일을 커밋한 다른 워크플로우가 있는지 확인(`.github/workflows/*.yml`에서 같은 파일 경로를 `git add`하는 곳 grep). ③ 그 파일이 이 잡의 HTML/텔레그램 생성에 실제로 쓰이는지(`grep`으로 generate_html.py·call_claude.py 등에서 참조 여부) 확인 — 안 쓰이면 커밋 대상에서 완전히 빼는 게 정답, 쓰이면 소유권을 한쪽 워크플로우로 통합하는 게 정답.

### 19. 미국 브리핑 이슈 — 주요 기업 실적 발표를 핵심 촉매로 잡는다

미국 시장 브리핑의 오늘의 이슈(`issues`)는 지수·거시 지표(CPI 등) 개괄만 다루면 안 되고, **오늘/어제 발표된 주요 기업 실적(어닝)과 경영진 코멘트를 최우선 촉매로 포착**해야 한다. 어닝시즌에는 개별 기업 실적이 지수·섹터를 가장 크게 움직이는 요인이며, 한 기업의 실적·발언이 **다른 종목·섹터로 파급(read-through)**되는 경우가 특히 중요하다(예: 2026-07-14 IBM 실적 콜의 AI 인프라 언급이 메모리 기업 상승으로 이어짐).

- **검색 대상은 빅테크에 한정하지 않는다.** `fetch_news.py`의 `US_PROMPT`가 매그니피센트7·반도체·장비(ASML·LRCX·AMAT·KLAC 등)뿐 아니라 **금융주(모건스탠리·골드만삭스·JP모건·뱅크오브아메리카·블랙록·씨티 등 대형 은행·자산운용), 헬스케어·소비재 등 전 섹터 대형주의 실적·가이던스·컨퍼런스콜 발언**을 검색하도록 지시한다. 어닝시즌 초입엔 대형 은행 실적이 먼저 나오므로 금융주를 빠뜨리지 말 것.
- **프리마켓(개장 전) 반응을 1급 선행 신호로 잡는다.** 미국 브리핑은 21:15 KST(= 미국 프리마켓 한복판)에 나가므로, 개장 전에 실적을 낸 기업(ASML 등 유럽 상장사·대형 은행처럼 미국 개장 전 발표)의 실적으로 **프리마켓에서 이미 움직인 섹터**가 오늘 세션을 예고하는 핵심 촉매다(예: ASML 실적 서프라이즈 → 프리마켓 반도체 장비주 강세). "무슨 실적 → 프리마켓에서 어느 섹터가 왜 강세/약세" 형태로 검색·이슈화한다. 프리마켓 반응은 뉴스 요약에 실제로 등장한 것만 쓰고(운영 규칙 0), 개별 종목 % 수치는 이슈 카드 본문에 넣지 않는다(§ 이슈 카드 숫자 금지).
- **read-through를 인과로 정리한다.** "어느 기업의 무슨 실적/발언 → 어느 종목·섹터를 왜 움직였는지"를 한 문장 촉매(`catalysts`)로 담고, `call_claude.py`의 이슈 카드에서 `down`/`up` 양면으로 표현한다(자금 이동형은 둘 다, 한 방향이면 한쪽만).
- **이슈 선택 우선순위 1순위 = 주요 기업 실적·경영진 코멘트** (`call_claude.py` US 프롬프트). 실적 촉매가 뉴스 요약에 등장하면 매크로·수치 이슈보다 앞세운다.
- **생성·추론 금지(운영 규칙 0 유지).** 실적 수치·주가 반응은 뉴스 요약(`catalysts`·`headlines`·`key_indicators`)에 **실제로 검색된 것만** 쓴다. 검색되지 않은 실적을 지어내지 않으며, 실적이 없는 날은 억지로 실적 이슈를 만들지 않는다.
- 관련 구현: `scripts/fetch_news.py` `US_PROMPT`(검색·`catalysts` 규칙), `scripts/call_claude.py` 미국 브리핑 "이슈 선택 우선순위". 두 곳을 함께 유지·수정한다 — 검색 프롬프트만 고치고 분석 프롬프트를 안 고치면 실적을 수집해도 이슈로 안 올라온다(그 반대도 마찬가지).

### 20. 종목 상세 페이지 목표주가 — 하드코딩 mock 데이터가 3주 넘게 라이브 노출 (2026-07-19 실사고, 수정 완료)

**증상**: 사용자가 삼성전자 상세 페이지(`/stocks/005930/`)의 "증권사 목표주가" 표에서 대신증권 리포트가 "1일 전"으로 뜨는데 실제로는 훨씬 전에 나온 것 같다고 지적. 확인해보니 네이버 원문상 해당 리포트의 실제 발행일은 7/08이었고(당시 기준 11일 전), SK하이닉스·현대차 상세 페이지도 동일한 문제였다.

**근본 원인**: `scripts/generate_html.py`에 `BROKER_TARGETS`라는 정적 딕셔너리가 있었다(주석: "2026-06-25 기준 수집"). 증권사명·목표가·투자의견·"N일 전" 라벨까지 **코드에 리터럴로 박아둔 값**으로, 실제 수집 로직이 전혀 없었다. 그런데 `kospi-close-briefing` job이 **평일 16:25마다 `generate_html.py --stocks`로 상세 페이지 3종목을 계속 재생성**하면서도(§2 참조) 이 딕셔너리는 건드리지 않아, "1일 전"이라는 상대 시간 라벨이 실제로는 3주 넘게 고정된 채 매일 다시 구워져 나갔다. 실제 증권사명(KB증권·삼성증권 등)을 달고 나가는 숫자였고, 그중 일부는 최근 그 증권사가 낸 적도 없는 목표가였다 — 운영 규칙 0("화면에 표시되는 모든 수치는 실측이어야 한다") 정면 위반.

같은 종목의 허브 페이지(`web/stocks/index.html`의 `#why-moved` 위젯)는 처음부터 `fetch_stock_targets.py`가 네이버에서 실측 수집한 `web/data/stock-targets.json`을 쓰고 있어 문제가 없었다 — **같은 데이터를 표시하는 두 화면이 서로 다른 소스(하나는 실측, 하나는 mock)를 쓰고 있다는 걸 아무도 알아채지 못한 채 굳어 있었다.**

**수정**:
- `BROKER_TARGETS` 딕셔너리와 이를 가공하던 `_enrich_broker_targets()`를 완전히 제거.
- `_broker_targets_for_code(code, current_price)`를 신설해 이미 실측이 검증된 `web/data/stock-targets.json`을 읽도록 교체. 종목별 `reports`에서 min/avg/max·상승여력을 계산하고, 데이터가 없으면 섹션 자체를 생략한다(억지로 채우지 않음).
- `_rel_when(yymmdd)`: "N일/주/개월 전" 라벨을 **저장된 문자열이 아니라 페이지 생성 시점마다 새로 계산**해서 뒀다 — 매일 재생성되는 페이지이므로 이 방식이면 값이 자연히 갱신된다.
- `_opinion_ko(op)`: 네이버 리포트가 영·국문을 혼용하는 투자의견(`Buy`/`StrongBuy`/`매수`/`적극매수` 등)을 표시용 한국어로 통일 — 허브 위젯의 `opinionKo()`(JS)와 동일 규칙을 Python으로 맞췄다.
- **재발 방지 가드**: `_targets_data_is_stale()` — `stock-targets.json`의 `updated_at`이 5일(평일 하루 2회 갱신 기준, 3일 연휴+주말 버퍼)보다 오래됐거나 필드 자체가 없으면, 목표주가 섹션을 **표시하지 않고** GHA 로그에 경고를 남긴다. 이번 사고의 근본 원인(수집이 죽었는데도 화면엔 계속 "그럴듯한 값"이 남아 있어 아무도 눈치 못 챔)이 실측 소스로 바꾼 뒤에도 그대로 재발할 수 있다는 판단에서 추가함 — `fetch_stock_targets.py`가 향후 조용히 실패해도 "낡은 값이 계속 진짜처럼 보이는" 상태로 되돌아가지 않도록 막는다.

**즉시 반영**: 정규 스케줄(평일 16:25)을 기다리지 않고 `generate_html.py --stocks`를 수동 실행해 3종목만 반영·배포. 이때 나머지 42종목도 함께 재생성됐지만(전체 종목을 도는 커맨드라 회피 불가) 이번 수정과 무관하고 비거래일(일요일)에 만들어진 값이라 커밋하지 않고 되돌림 — 그 종목들은 다음 평일 정규 job이 정상적으로 반영한다.

- **방지 룰**: **정적 데이터(가격·리포트·날짜 등 "실측처럼 보이는" 값)를 코드에 리터럴로 넣지 않는다.** 프로토타입·임시 표시가 필요하면 반드시 (a) 파일명이나 변수명에 `MOCK`/`PLACEHOLDER`를 명시하고, (b) 생성 스크립트가 그 함수를 호출할 때마다 경고를 찍게 하거나, (c) 애초에 진짜 fetch 스크립트부터 먼저 만든다. "나중에 실데이터로 교체" 계획은 매일 자동 재생성되는 파이프라인 안에서는 특히 위험하다 — 재생성이 "성공"으로 보이기 때문에 아무도 돌아와서 안 고친다.
- **동일 데이터의 이중 소스 경계**: 같은 종목·같은 항목을 두 화면(허브 위젯 vs 상세 페이지처럼)에서 표시할 땐 반드시 같은 데이터 소스를 공유하게 만든다. 소스가 갈라져 있으면 한쪽만 고쳐지고 다른 쪽은 몇 주씩 방치돼도 겉보기엔 둘 다 "정상 작동 중"으로 보인다.
- **상대 시간 라벨("N일 전" 등)은 저장하지 말고 렌더 시점에 계산한다.** 저장된 라벨은 저장 시점에만 맞고, 그 이후엔 페이지가 재생성되든 안 되든 계속 그 시점 기준으로 남는다(§ 외국계 시각 `time_label` 사고와 동일 패턴 — 이번이 벌써 두 번째 재발).
- **실측 데이터 소스에도 신선도 가드를 둔다.** "이제 진짜 데이터를 쓴다"로 끝내지 말고, 그 데이터를 만드는 수집 잡이 죽었을 때 무슨 일이 벌어지는지까지 설계한다 — 조용히 낡은 값을 계속 보여주는 것과, 섹션을 생략하고 로그에 경고를 남기는 것 중 항상 후자를 택한다(운영 규칙 0).
- **재발 시 진단 순서**: ① 화면에 뜬 날짜·상대 라벨을 실제 소스(네이버 원문 등)와 직접 대조 — 표시된 "N일 전"을 신뢰하지 않는다. ② `grep`으로 해당 값이 코드에 리터럴로 박혀 있는지(`scripts/*.py`에서 종목명·가격이 하드코딩된 딕셔너리 형태로 있는지) 확인. ③ 같은 데이터가 다른 화면에도 표시된다면 그 화면의 소스와 대조해 두 소스가 갈라져 있는지 확인.

### 21. 마감 브리핑 텔레그램이 종목 서비스 재빌드에 막혀 지연 — 타임아웃 상한 부재 (2026-07-20 실사고, 수정 완료)

**증상**: 16:25 KST `kospi-close-briefing` 잡이 시작 후 15분 44초가 지나서야 텔레그램이 나갔다(사용자 체감 "13분째 미발행"). 멈춘 게(hang) 아니라 **느렸던** 것 — 잡은 스스로 완료됐다.

**근본 원인**: 마감 브리핑 HTML·텔레그램 메시지 자체는 `🖥️ 웹 페이지·텔레그램 메시지 생성` 스텝에서 **1초 만에 이미 생성 완료**됐는데, 그 뒤로 **종목 서비스(대시보드) 페이지 재빌드** 스텝 4개가 커밋·배포·텔레그램 **앞에** 놓여 있었다. 이들은 미국 GitHub 러너가 네이버/토스를 순차로 대량 호출해서 느리다 — 그날 목표주가 176초·종목 스냅샷 빌드 157초·국내 상세 재생성 237초·밸류에이션 168초로 **합계 ~12분**. 그래서 브리핑이 준비된 뒤에도 구독자 텔레그램이 약 10분 늦게 나갔다.

결정적으로 **워크플로우 전체에 `timeout-minutes`가 0건**이었다(grep 확인). 상한이 없으면 느린 네트워크 스텝이 방치돼도 기본 GHA 6시간 잡 타임아웃까지 버틴다 — 2026-07-10엔 실제로 마감잡이 85분까지 늘어졌다. 게다가 `📈 종목 스냅샷 빌드`만 유일하게 `continue-on-error`가 없어서, 이 스텝이 멈추면 뒤의 텔레그램이 **영영 안 나가는** 구조였다.

**설계 확인(중요)**: 텔레그램은 원래대로 웹 페이지 생성 → 커밋 → 배포 → `🔎 상세 페이지 라이브 확인`을 **전부 통과한 뒤 맨 마지막**에 나가야 한다("웹 페이지가 다 만들어진 후 텔레그램"). 이 순서는 유지한다 — 문제는 순서가 아니라 상한 없는 지연이었다. 텔레그램을 앞으로 당기는 식의 재배치는 하지 않는다.

**수정** ([daily_report.yml](../.github/workflows/daily_report.yml)):
- 3개 브리핑 잡(kospi/us/kospi-close)에 **job-level `timeout-minutes: 35`** 백스톱 — 상한 없는 스텝이 잡 전체를 6시간까지 끄는 것을 차단.
- 네트워크 무거운 5개 스텝(아침 목표주가 + 마감의 목표주가·스냅샷·국내상세·밸류에이션)에 **`timeout-minutes: 5`**.
- `📈 종목 스냅샷 빌드`에 **`continue-on-error: true` 추가**. 타임아웃·실패 시 스냅샷은 직전 값을 유지하고 마감 브리핑 발행은 계속된다. 이 스텝들은 전부 종목 서비스용이라, 그날 갱신을 건너뛰어도(구식이지만 실측) 다음 거래일에 정상화된다(운영 규칙 0 — 구식이지만 실측 > 발행 지연).

- **방지 룰**: 사용자에게 나가는 산출물(텔레그램·이메일)이 파이프라인 **마지막**에 있고 그 앞에 네트워크 수집 스텝들이 있다면, **그 수집 스텝마다 `timeout-minutes`를 반드시 건다.** "느린 성공"과 "영원한 지연"을 상한 없이 구분할 수 없다. 특히 산출물 발행에 필수가 아닌 부수 작업(종목 서비스 재빌드 등)은 `continue-on-error: true` + 짧은 `timeout-minutes`로 감싸, 실패해도 마케 산출물 발행은 절대 막지 않게 한다. 잡 전체에도 넉넉한 `timeout-minutes` 백스톱을 둔다(기본 6시간은 사실상 무한).
- **재발 시 진단 순서**: ① `gh api .../actions/jobs/<id> --jq '.steps[]|...'`로 **스텝별 소요시간**을 뽑아 진짜 병목을 특정한다(체감상 "멈춘" 스텝이 실제 원인이 아닐 수 있다 — 이번에도 밸류에이션인 줄 알았으나 실제론 상세 재생성이 최장). ② 병목 스텝이 산출물 발행에 필수인지 확인 — 아니면 `continue-on-error`+`timeout-minutes`로 감싼다. ③ `grep -c timeout-minutes`로 워크플로우에 상한이 하나라도 있는지 확인 — 0이면 그 자체가 사고 대기 상태다.

### 22. 코스피 예측 브리핑 "이렇게 보는 이유"에 stale·날조 US 서사 노출 (2026-07-22 실사고, 수정 완료)

**증상**: 07:26 KST 코스피 예측 브리핑 `key_drivers`(이렇게 보는 이유) 3줄이 전부 미국 야간장 서사인데 실측과 어긋났다. "SOX +5.21%"·"EWY +6.18%"는 **직전 세션(화 07-21)이 아니라 그 전 세션(월 07-20)의 값**이었고(실측 EWY는 +1.72%), "엔비디아 실적 발표 후 차익 실현"은 **7월 하순에 엔비디아 실적 자체가 없는 날조**(NVDA 실제 -0.48%)였다. 같은 밤 "SOX +5.21% 급등"과 "나스닥은 엔비디아 차익실현으로 하락"이 **내부 모순**이기도 했다. 국내 recap(삼성 +6.15%·하이닉스 +4.08% = 07-20→21 실측)은 정상 — **미국 서사만 오염**.

**근본 원인**: 발행 게이트 `validate_key_drivers()`는 항목 `codes`에 **한국 종목코드가 있을 때만** 실측 대조했다. US 항목은 `codes: []`라 안쪽 루프가 돌지 않고 **무조건 통과**했다. SOX·EWY를 실측 방향까지 잡던 `validate_prose_nonpick_stocks`는 구 `reasons` 필드만 스캔하는데 신규 `qa` 포맷은 `key_drivers`를 써서 그마저 안 걸렸다. 운영 규칙 0이 경고한 "산문 내 수치 구조적 미검증" 구멍이 신규 포맷의 US 지수·이벤트로 확대된 것.

**수정** ([validate_analysis.py](../scripts/validate_analysis.py)):
- `validate_key_drivers`가 `codes` 없이도 본문에서 US 티커(SOX·EWY·NVDA 등)를 추출해 실측 재조회(토스→yfinance) 후, 방향 모순 또는 정량 stale이면 항목 제거.
- `_us_figure_stale(text, real, tol=2.0)` 신설. `is_contradicted`(5%p·5배·부호반전)는 **인접 세션 stale**(EWY +6.18 vs 실측 +1.72, diff 4.46%p)을 못 잡는다 — SOX·EWY change_pct는 fetch_data와 게이트가 같은 일봉 소스라 같은 세션이면 소수점까지 일치하므로, 정밀 데이터 인용에 한해 타이트 임계치(2%p)를 별도 적용.
- 실측 실패 시 fail-open(정상 항목 오제거 방지). 테스트 5개(`test_validate_analysis.py`), 엔드투엔드로 EWY stale 항목 실제 제거 확인.

- **"엔비디아 실적 발표" 날조의 진짜 출처 규명·수정 완료 (같은 사고 후속 조사)**: 이 이벤트 서술은 Claude의 key_drivers 환각이 아니라 **Gemini 뉴스 요약(`fetch_news.py`)에서 왔다** — 당일 `news_summary_kospi.json`의 `catalysts`·`key_indicators`에 이미 "엔비디아 실적 발표 이후 차익 실현"이 들어 있었고 Claude는 충실히 전파했을 뿐이다(NVIDIA는 7월 하순 실적 없음). `fetch_news`엔 이미 어닝 캘린더 게이트(`_drop_stale_earnings` + yfinance `_days_since_last_earnings`)가 있었는데, catalyst의 `ticker` **필드**만 봐서 Gemini 문자열 catalyst(필드 없음)의 한글명 "엔비디아"를 NVDA로 못 풀어 검증을 건너뛰었다. 수정([fetch_news.py](../scripts/fetch_news.py)): `_NAME_TO_TICKER` + `_resolve_company_tickers`로 **텍스트의 미국 대형주 사명(한/영)을 티커로 resolve**하고, `_drop_stale_earnings`가 필드+텍스트 티커 모두로 어닝 캘린더 검증. catalysts뿐 아니라 **headlines·key_indicators에도 적용**(같은 날조가 다른 필드로 새어나가는 것 차단). 국내주는 `.KS` 어닝 조회가 불안정해 맵 미등록=fail-open. 테스트 4개(`test_earnings_gate.py`), 엔드투엔드로 실제 사고 데이터에서 날조 3건 제거 확인.
- **방지 룰(추가)**: 산문/뉴스에 사명이 **텍스트로만**(티커 필드 없이) 등장하는 이벤트 주장을 검증할 땐, 사명→티커 resolve를 반드시 거쳐야 한다. "ticker 필드가 있을 때만 검증"하는 게이트는 필드 없는 LLM 문자열 출력에 그대로 뚫린다. 또 한 소스(catalysts)만 거르면 같은 날조가 다른 필드(headlines·key_indicators)로 우회하므로, LLM이 소비하는 **모든 뉴스 필드**에 동일 게이트를 적용한다.
- **잔여 갭(남음)**: (a) 국내주 실적 날조는 yfinance `.KS` 어닝이 불안정해 아직 미검증(맵 미등록 fail-open). (b) key_indicators처럼 실측 매크로 + 날조 인과가 한 문장에 섞이면 항목을 통째로 드롭한다(실측 지수는 fetch_data가 별도 소스라 §0상 안전하나, 문장 단위 스크러빙은 아님). (c) 임박(예정) 실적 프리뷰는 과거 발표일 기준이라 오검출 여지 — 실제 사고 유형("발표 이후")과 구분 필요.
- **방지 룰**: 산문 검증기를 만들 때, 검증 대상 필드가 **포맷 버전에 따라 바뀌는지**(`reasons` vs `key_drivers`) 반드시 확인한다 — 새 포맷 필드가 옛 검증기를 우회한다. 그리고 "실제로 존재하는 옆 세션 값"(stale)은 hallucination용 느슨한 임계치를 통과하므로, 정밀 데이터 인용에는 타이트 임계치를 따로 둔다.
- **재발 시 진단 순서**: ① 의심 수치를 토스 API 일봉으로 세션별 대조 — "값 자체가 틀렸나" vs "옆 세션 값을 인용했나" 구분. ② `analysis_format`을 확인해 해당 산문 필드가 실제로 게이트를 타는지(`grep`으로 validate_* 함수가 그 필드명을 스캔하는지) 확인. ③ 이벤트 인과("~실적 발표", "~어닝")는 수치 게이트로 안 잡히니 뉴스 요약과 직접 대조.

### 23. 코스피 아침 브리핑이 '이미 발표된' 간밤 빅테크 실적을 '발표 예정'으로 오표기 (2026-07-23 실사고, 수정 완료)

> **[상시 원칙] 간밤 미국 빅테크 실적은 코스피 아침 브리핑에서 항상 최우선으로 다룬다.** 빅테크(구글·MS·아마존·메타·엔비디아 등)의 **AI 설비투자(capex) 성장률**이 메모리·HBM 수요의 선행지표이고, 그 수요가 코스피 대장주 삼성전자·SK하이닉스 주가와 직결되기 때문이다 — **빅테크 AI 투자 성장률이 오르면 메모리 수요 기대↑ → 대장주·코스피 상방, 성장률이 꺾이면 메모리 수요 둔화 우려 → 대장주·코스피 하방.** 그래서 빅테크 실적일엔 실적·클라우드 성장률·**capex 규모와 증감 방향**을 핵심 촉매로 최우선 수집·서술하고 삼성전자·SK하이닉스 read-through를 반드시 함께 담는다. (사용자 지시 2026-07-23. 구현: `fetch_news.py` KOSPI_PROMPT 최우선 룰, `call_claude.py` us_issues 최우선 지시. 실측·검색된 실적만 사용 — 운영 규칙 0.)

**증상**: 2026-07-23 07:30 KST 코스피 예측 브리핑이 구글(알파벳) 2분기 실적을 **"오늘 밤 발표 예정"·"실적 대기, 관망 우위"**로 전면 서술했다. 그러나 구글은 **직전날(7/22) 미 증시 마감 후 ET**에 이미 실적을 발표한 상태였고(= KST 7/23 새벽, 브리핑 생성 ~2시간 전), 결과는 클라우드 매출 **+82%(248억 달러)**·총매출 +24%·분기 capex 449억 달러·연 1,900억 달러 투자 계획으로 **AI 인프라 투자 성장을 재확인한 강한 호실적**이었다. 브리핑 전체(reason_title·todays_view·key_drivers·us_issues·num_cards·watch_items)가 미래형 프레이밍으로 채워져 HBM 대장주(삼성전자·SK하이닉스) read-through라는 핵심 촉매를 결과로 담지 못했다.

**근본 원인**: 미국 대형주 실적은 미 증시 마감 후(코스피 아침 브리핑 직전 KST 새벽)에 나오므로, 07:25 뉴스 수집 시점엔 **이미 결과가 공개돼 있는 게 정상**이다. 그런데 (1) `fetch_news.py`의 구글 실적 검색 힌트(commit 7c174f75)가 "실적 발표"만 지시하고 "발표 예정 프리뷰 기사에 속지 말고 결과를 담으라"는 구분을 넣지 않았고, (2) Gemini `google_search`가 결과 기사(발표 ~2시간 후라 아직 덜 확산)보다 **프리뷰("~발표 예정")·어닝 콜 일정("call tomorrow") 기사**를 더 많이 물어와, (3) `call_claude.py` us_issues 지시도 "결과 vs 예정" 구분이 없어 Gemini가 준 미래형 프레이밍을 그대로 전파했다. 어닝 게이트(§22)는 stale/날조를 막을 뿐, "실제로 발표됐는데 예정으로 잘못 쓴 것"은 검출 대상이 아니다.

**수정**:
- [fetch_news.py](../scripts/fetch_news.py) `KOSPI_PROMPT`: 간밤 빅테크 실적을 **상시 룰**로 승격 — "이미 발표됐으면 '예정'이 아니라 '결과'를 담는다. 프리뷰 프레이밍 기사에 속지 말고 실제 결과 기사를 찾아 매출 증감률·클라우드 성장률·capex 규모·발표 후 주가 반응까지 수치로 담고 HBM read-through를 정리한다. 진짜 발표 전이면 그때만 '예정' 표기하고 결과를 지어내지 않는다(운영 규칙 0)."
- [call_claude.py](../scripts/call_claude.py) `us_issues` 지시: "이미 발표된 실적이면 결과로 쓴다 — reason_title·todays_view·key_drivers 모두 결과 기준 서술" 문장 추가.

- **방지 룰**: 미국 실적은 통상 **코스피 아침 브리핑 직전(KST 새벽)에 발표**된다 — 즉 아침 브리핑 시점엔 "예정"이 아니라 "결과"가 정상이다. 빅테크 실적일에 브리핑이 "오늘 밤 발표 예정"으로 나오면 **프리뷰 기사에 속은 것**을 의심할 것. 뉴스 요약에 결과 수치(매출·클라우드·capex·주가 반응)가 있으면 반드시 결과로 서술하고, 특히 **클라우드/AI capex 성장률**을 HBM(삼성전자·SK하이닉스) 수요 read-through의 1급 촉매로 최우선 노출한다.
- **재발 시 진단 순서**: ① 실적일 브리핑이 "발표 예정"으로 나왔으면 그 종목의 실제 발표 시각(미 증시 마감 후 ET = KST 새벽)을 확인 — 브리핑 생성 시점보다 앞서면 이미 결과가 나온 것. ② 당일 `news_summary_kospi.json`의 catalysts·key_indicators에 프리뷰 기사만 담겼는지(결과 수치 누락) 확인. ③ 결과가 늦게 확산돼 수집 시점에 프리뷰만 잡혔다면, 프롬프트 지시로 결과 기사를 우선 검색하도록 강화됐는지 확인(이 수정으로 반영). ④ 수동 정정 시엔 스냅샷(source of truth)과 렌더된 index.html을 함께 고치되, 로컬 market_data가 stale이면 `generate_html` 재생성 대신 두 파일의 실적 서사만 surgical 편집한다(측정 데이터 오염 방지).

### 24. 월요일 브리핑의 '간밤' 오표기 + S&P500 부호 반전 + 전일 종가 기준가 오류 (2026-07-27 실사고, 수정 완료)

**증상**: 2026-07-27(월) 07:29 KST 코스피 예측 브리핑에서 세 가지가 동시에 나왔다.
① 지난 금요일(7/24) 미국장을 **"간밤"**으로 서술 — 월요일이라 간밤 미국장은 존재하지 않는다.
② **S&P500 "-0.05%로 조정 마감"·"나스닥·S&P500 나란히 하락"** — 실제로는 **+0.05%**(7408.30→7411.98) 강보합.
③ **EWY -5.78%·DRAM ETF -8.62%** — 실측은 **-6.27%·-8.75%**.

**근본 원인 (셋이 서로 다름)**:

1. **'간밤'**: 코드·프롬프트·템플릿(`_us_issues.html` 섹션 제목 "간밤 미국 시장 이슈")에 이 단어가 **상수로 박혀** 있었다. 코스피 아침 브리핑은 "어제 미국장 = 간밤"을 암묵 전제로 설계됐는데, **월요일과 휴일 다음날에는 그 전제가 깨진다**(직전 미국장이 금요일 이전).
2. **S&P500 부호 반전**: 수집 데이터는 정상이었다(`fast_info` +0.05%). LLM이 서술하며 부호를 뒤집었고, 게이트가 못 잡았다 — `validate_key_drivers`의 US 실측 대조는 `_US_TICKER_RE`(`[A-Z]{2,5}`)로 **ASCII 티커만** 추출해서 "나스닥"·"S&P500" 같은 **한글·기호 지수명은 아예 검증 대상에 오르지 못했다**(§22에서 남겨둔 잔여 갭이 지수명으로 재현).
3. **EWY·DRAM 기준가**: `fetch_data._get_realtime_price()`가 yfinance `fast_info.previous_close`를 전일 종가로 신뢰하는데, **이 값이 직전 세션이 아닌 더 과거 세션의 종가를 반환한다**(사고 당시 EWY `previous_close`=172.964 = 7/21 종가, 실제 직전 종가는 173.86 = 7/23). `last_price`는 정확했으므로 **분자는 맞고 분모만 틀린** 형태라 값이 그럴듯해 보였고, 오차가 0.5%p 수준이라 기존 정량 게이트(±2%p)도 통과했다.

**추가로 드러난 서사 오류(이중 계상)**: EWY -6.27%는 같은 날 **코스피 -5.72% 급락을 반영한 수치**인데 "오늘 새로 들어온 악재"로 서술됐다. 정작 코스피 마감 이후 움직여 실제로 신규 정보인 SOX -4.25%·DRAM ETF -8.75%는 뒤에 밀렸고, 금요일 대장주 급락(삼성전자 -7.59%·SK하이닉스 -8.34%)은 recap에서 누락됐다.

**수정**:
- [session_label.py](../scripts/session_label.py) 신설 — `us_session_label(date)`가 `holiday_check`로 직전 미국장을 실제 계산해 "간밤"/"지난 금요일"/"직전 미국장(7/17)"을 돌려준다. `fix_overnight_wording()`은 본문의 간밤·어젯밤·지난밤·밤사이를 그 라벨로 치환.
- [validate_analysis.py](../scripts/validate_analysis.py) `fix_overnight_labels()` — 발행 직전 analysis JSON 전체 문자열을 재귀 순회해 결정론적으로 치환. **프롬프트 지시만으로는 새기 때문에 게이트가 최종 방어선이다**(§22 교훈).
- [call_claude.py](../scripts/call_claude.py) `_session_label_directive()` — 간밤이 아닌 날에만 프롬프트에 "직전 미국장은 X (지난 금요일)이다, '간밤'이라 쓰지 말 것" 지시를 주입(1차 방어).
- [generate_html.py](../scripts/generate_html.py) `_us_issues_label()` + `_us_issues.html` — 섹션 제목을 `{{ us_issues_label }} 미국 시장 이슈`로 동적화.
- [validate_analysis.py](../scripts/validate_analysis.py) `_index_figures()`/`_index_figure_wrong()` — 한글·기호 지수명(나스닥·S&P500·다우·필라델피아 반도체)을 심볼로 resolve해 실측 대조. **지수명 바로 뒤 12자 이내의 등락률만** 그 지수의 주장으로 본다 — 문자열 전체를 훑으면 "나스닥 -0.64%, S&P500 +0.05%"처럼 여러 지수가 한 문장에 있을 때 서로의 수치와 교차 비교돼 정상 항목을 오제거한다. **부호 반전 또는 2%p 초과**면 해당 key_drivers 항목 제거. "나스닥100 선물"은 일봉 실측과 기준이 달라 마스킹해 제외.
- [fetch_data.py](../scripts/fetch_data.py) `_prev_close_from_daily()` — `fast_info.previous_close`를 일봉으로 교차 검증해 교정. 장 마감 상태(현재가 == 마지막 일봉 종가)면 그 직전 종가, 세션 진행 중이면 거래소 현지 날짜로 마지막 바가 오늘 바인지 판별. 교정 시 stderr에 로그. `get_ticker_full`·`build_sidebar_market_data` 두 호출부 모두 적용.
- 테스트: `test_prev_close_from_daily.py`(5), `test_index_figures.py`(7). 사고 당시 데이터로 리플레이해 두 게이트가 실제로 발화하고 정정본은 통과하는 것까지 확인.

- **방지 룰(시각 표현)**: **'간밤'·'전일'처럼 시점을 가리키는 상대 표현을 코드·프롬프트·템플릿에 상수로 박지 않는다.** 반드시 직전 거래일을 실제 계산해서 라벨을 만든다. 월요일과 휴일 다음날은 이 전제가 항상 깨지는데, 주 5회 중 4회는 맞아떨어져서 오류가 눈에 안 띈다. (§20의 "상대 시간 라벨은 렌더 시점에 계산한다"와 같은 계열 — 이번이 세 번째 재발이다.)
- **방지 룰(지수명 검증)**: 산문 실측 대조 게이트를 만들 때 **ASCII 티커 정규식만으로는 부족하다** — 한국어 브리핑은 지수를 "나스닥"·"S&P500"·"코스피"처럼 쓴다. 사명→티커 resolve가 필요했던 §22와 동일한 구조의 갭이므로, 새 게이트를 추가할 땐 항상 "이 대상이 본문에 한글로 등장하면 어떻게 되나"를 먼저 확인한다.
- **방지 룰(기준가)**: **등락률은 분자(현재가)뿐 아니라 분모(전일 종가)도 실측 검증한다.** 벤더가 주는 `previous_close`류 편의 필드를 그대로 믿지 않는다 — 분모만 틀리면 값이 그럴듯한 범위로 나와 정량 게이트를 통과한다. 일봉 시계열이 있으면 그쪽이 정본이다.
- **방지 룰(이중 계상)**: 한국 마감 **이후** 움직인 지표(SOX·나스닥·DRAM ETF 등)만 오늘의 신규 변수다. **EWY처럼 한국 시장을 추종하는 상품의 등락률은 같은 날 코스피 등락을 그대로 반영한 값**이라, 이를 "간밤 새로 들어온 악재"로 쓰면 이미 실현된 하락을 두 번 세는 것이다. EWY를 근거로 쓸 땐 당일 코스피 등락률과 함께 제시해 중복분을 드러낸다.
- **재발 시 진단 순서**: ① 브리핑에 '간밤'이 있으면 그날 요일과 `prev_us_session()`을 먼저 대조. ② 지수 등락률은 **부호까지** yfinance 일봉으로 직접 확인 — 절댓값이 맞아도 부호가 뒤집혀 있을 수 있다. ③ 값이 실측과 0.1~1%p 어긋나면 분자가 아니라 **분모(전일 종가)를 의심**하고 `fast_info.previous_close`와 일봉 `closes.iloc[-2]`를 비교한다.

### 25. 미국 브리핑 이슈 3건이 익명 플레이스홀더("B사"·"C은행")로 날조 (2026-07-27 실사고, 수정 완료)

**증상**: 2026-07-27 21:17 KST 미국 브리핑의 "오늘 점검할 이슈" 5건 중 3건이 **실존하지 않는 익명 기업**을 주어로 삼았다. "**B사** 서비스 출시 지연 발표 → 시간 외 급락", "**C은행** 대손충당금 서프라이즈 → 금융 섹터 심리 위축", "**D사** AI 파트너십 발표". 종목 픽 시나리오 2건(GS·JPM)까지 "C은행발 금융 섹터 경계감"으로 오염됐다. 사용자에게는 실제 기업을 익명 처리한 것처럼 보이지만, 그런 사건 자체가 없었다.

**근본 원인**: Claude 환각이 아니라 **Gemini 뉴스 수집 단계의 날조**다 — 당일 `data/news_summary_us.json`에 이미 `A사`·`B사`·`C은행`·`D사`가 들어 있었고 `call_claude.py`는 충실히 전파했다. `US_PROMPT`의 catalysts 예시가 `"[기업]의 [제품·전략 발표] → …"` 형태의 **대괄호 슬롯**인데, google_search로 실제 소재를 찾지 못하자 Gemini가 그 슬롯 구조만 남기고 주어를 알파벳 익명으로 채워 형식상 그럴듯한 답을 만들어냈다. 스키마 위반도 동반됐다 — catalysts는 `{date, text, ticker}` 객체여야 하는데 **순수 문자열 배열**로 돌아왔다(수집이 정상 경로를 타지 않았다는 신호).

**기존 게이트 3개가 전부 통과시킨 이유** (구조가 서로 다른 갭이다):
- `_drop_search_failure_notes`(§같은 날 오전 추가) — "확인되지 않았습니다" 류 **자백형** 실패만 잡는다. 이번은 자백 없이 그럴듯하게 지어낸 형태라 무관.
- `_drop_stale_earnings`(§22) — 사명→티커 resolve 기반인데 "B사"는 어떤 티커로도 풀리지 않아 **fail-open**으로 통과.
- `validate_analysis`(§0·§22·§24) — 수치 게이트다. 실제로 종목 픽 4건(AAPL·GS·JPM·NVDA)의 가격·등락률·MA 이격은 전부 실측과 일치했다. **구멍은 "숫자"가 아니라 "사건의 주어"였다** — 주어가 가짜인 것은 어떤 수치 게이트로도 검출되지 않는다.

**수정**:
- [fetch_news.py](../scripts/fetch_news.py) `_drop_placeholder_entities()` 신설 — 익명 플레이스홀더 주어(`A사`·`C은행`·`D증권`·`[기업]` 대괄호 슬롯·`○○사`·`모 기업`·`익명의`)를 담은 항목을 `catalysts`·`headlines`·`key_indicators` 전 필드에서 제거. 실명 없는 사건은 검증 자체가 불가능하므로 항목째 버린다.
- `US_PROMPT`에 "모든 항목의 주어는 실제 실명이어야 하고, 특정 못 하면 익명화하지 말고 항목을 통째로 버린다. 남는 게 없으면 빈 배열" 명시(1차 방어). **프롬프트만으로는 새기 때문에 게이트가 최종 방어선**(§22·§24와 동일 교훈).
- 테스트 `scripts/test_placeholder_entities.py`(7케이스) — 실사고 원본 데이터 리플레이 포함. 실명 항목(마이크론·애플·JP모건·SK하이닉스·S&P500)이 오제거되지 않는 것까지 검증.
- 오늘자 페이지 정정: 로컬 `latest_us.json`이 7/17자 stale이라 `generate_html` 재생성은 사이드바를 오염시킨다(§23 선례) → `analysis_snapshot.json` + `index.html`을 **surgical 편집**. 날조 이슈 2건 삭제, "D사" 이슈는 검증된 애플·엔비디아 부분만 남김, 픽 시나리오 2건 탈오염. 사이드바·픽 수치는 실측이라 건드리지 않음.

- **방지 룰(익명 주어)**: **실명이 없는 사건 서술은 검증이 불가능하므로 발행하지 않는다.** LLM이 소재를 못 찾았을 때의 실패 모드는 두 가지다 — ① 자백("확인되지 않았습니다") ② **익명화한 그럴듯한 날조("B사가…")**. ②가 훨씬 위험하다. 자백은 눈에 띄지만 날조는 형식이 완전해서 그대로 발행된다. 수집 결과에 실명이 없으면 빈 배열로 두는 게 정답이다(운영 규칙 0).
- **방지 룰(프롬프트 예시)**: 프롬프트에 `[기업]`·`○○사` 같은 **슬롯형 예시**를 넣으면 LLM은 소재를 못 찾았을 때 그 슬롯을 익명 주어로 메워 반환한다. 슬롯 예시를 쓸 거면 반드시 "슬롯을 그대로 남기거나 익명으로 채우지 말고 항목을 버려라"를 **같은 자리에** 붙이고, 그 지시가 지켜졌는지 결정론 게이트로 다시 확인한다.
- **방지 룰(게이트 범위)**: 검증 게이트를 "수치가 맞는가"로만 설계하면 **주어·사건이 통째로 가짜인 경우를 놓친다.** 새 게이트를 추가할 때는 "이 항목의 수치가 전부 맞더라도 사건 자체가 없었다면 무엇이 잡아내는가"를 함께 답할 것. 스키마 위반(객체여야 할 catalysts가 문자열로 옴)은 수집이 정상 경로를 안 탔다는 **선행 신호**이므로 함께 감시한다.
- **재발 시 진단 순서**: ① 브리핑 본문에서 `[A-Z]사`·`[A-Z]은행` 정규식을 먼저 grep — 걸리면 즉시 날조 확정. ② 원천 `data/news_summary_{type}.json`을 열어 날조가 수집 단계인지 분석 단계인지 구분(수집 단계면 `fetch_news`, 분석 단계면 `call_claude`가 범인). ③ catalysts가 객체가 아니라 문자열 배열로 와 있으면 google_search 그라운딩 실패를 의심. ④ 정정은 `generate_html` 재생성 전에 로컬 `latest_{type}.json`의 날짜를 먼저 확인 — stale이면 재생성하지 말고 스냅샷·HTML을 surgical 편집한다(§23).

### 26. 미국 브리핑이 프리마켓에 발행되면서 직전 정규장 종가를 실었다 (2026-07-27 실사고, 수정 완료)

**증상**: 2026-07-27 미국 브리핑의 1번 이슈가 "메모리·반도체 장비주가 **프리마켓에서 크게 밀렸어요**"였고 MU·AMAT·KLAC·LRCX 급락을 근거로 들었다. 그러나 그 수치(-6.99·-4.72·-3.75·-4.56%)는 **금요일(7/24) 정규장** 등락이었고, 정작 그 시각 실제 프리마켓은 **반등 중**이었다(MU +1.9%, AMAT +2.9%, KLAC +2.4%, LRCX +2.2%). 브리핑의 핵심 서사가 현실과 **정반대**였다. 종목 픽 가격·등락률도 전부 금요일 종가 기준이었다.

**근본 원인**: `fetch_data._get_realtime_price()`가 1순위로 쓰는 **yfinance `fast_info.last_price`가 연장시간대(프리·애프터) 체결을 반영하지 않는다.** 프리마켓 한복판에도 직전 정규장 종가를 그대로 준다(실측: 프리마켓에서 MU가 938에 거래되는데 fast_info는 920.95 반환). 이게 1순위라 **항상 성공**하므로, `prepost=True`를 쓰도록 제대로 짜여 있던 2순위 폴백은 **한 번도 실행된 적 없는 죽은 코드**였다. 미국 브리핑은 21:15 KST = 프리마켓 한복판에 나가므로, 이 서비스는 **출시 이래 단 한 번도 프리마켓 데이터로 미국 브리핑을 만든 적이 없다.**

**왜 오래 안 들켰나 — 룰 문서가 위반을 제도화하고 있었다**: §0 헤드라인은 "생성 시점에 실제로 수집한 데이터만 사용한다"인데, 같은 §0 안의 픽 주입 항목에 **"기준: 직전 완료 세션 종가 대비 등락률, 실시간 장중가 아님"**이 무조건 규칙으로 적혀 있었다. 코스피 아침(07:25, 양 시장 휴장)에는 맞는 말이지만 미국 브리핑엔 틀린 말이고, 이 한 줄이 §0 원칙을 정면으로 부정해 코드의 구조적 위반을 "명세대로 동작 중"으로 보이게 만들었다. **문서의 하위 조항이 최상위 원칙을 무력화한 사례** — 룰을 추가할 때 상위 원칙과 충돌하는지 반드시 확인할 것.

**수정**:
- `fetch_data._extended_hours_price()` 신설 — `prepost=True` intraday의 마지막 바가 신선하면(기본 12시간 이내) 그 값을 현재가로 채택. **판정은 값이 아니라 타임스탬프로** 한다(fast_info 값을 5분봉에서 되찾는 값 매칭 방식은 공식 종가와 봉 종가가 미세하게 달라 실측 10종목 중 4종목에서 빗나갔다). 주말·휴장으로 마지막 체결이 오래됐으면 fast_info 유지(fail-open).
- `validate_analysis._closes_to_realdata(live_price=)` — 현재가 = 발행 시점 실체결가, **기준가 = 직전 정규장 종가**. 스파크라인 마지막 점도 실체결가로 교체. MA 이격도 그 가격 기준 재계산.
- `_fetch_pick_realdata(ticker, is_us)` — **미국 픽만 `live=True`**. 코스피 아침은 07:25에 양 시장이 닫혀 있어 직전 완료 세션이 곧 최신 실측이므로 기존 동작 유지.
- **롤오버 가드 범위 버그 동시 발견·수정**: `get_ticker_full`의 선물 롤오버 가드(1시간봉과 3% 이상 벌어지면 되돌림)에 **티커 제한이 없었다.** 1시간봉은 prepost를 포함하지 않아, 프리마켓에서 3% 이상 움직인 **개별주**를 "롤오버 갭"으로 오인해 정규장 종가로 되돌린다(XOM 프리마켓 -3.19% → +4.15%로 **부호까지 반전**). `_is_futures_like()`로 선물·지수·환율(`=F`·`^`·`=X`)에만 적용하도록 제한. 이 버그는 원래도 있었지만 `price`가 항상 정규장 종가라 gap이 0이어서 잠복해 있었다 — **한 곳을 실측화하면 그 값을 전제로 짜인 다른 가드가 오작동할 수 있다.**
- 테스트: `test_extended_hours_price.py`(8), `test_live_pick_realdata.py`(6).

- **방지 룰(발행 시각 = 데이터 기준)**: **브리핑이 나가는 시각의 시장 상태가 곧 "지금"이다.** 브리핑 타입마다 발행 시각의 시장 국면(프리마켓/장중/마감후/휴장)을 먼저 적고, 데이터 수집 기준을 거기에 맞춘다. 모든 브리핑에 하나의 기준("직전 완료 세션")을 일괄 적용하지 않는다.
- **방지 룰(벤더 편의 필드)**: `fast_info.last_price`(연장시간대 미반영)·`fast_info.previous_close`(과거 세션 반환, §24)처럼 **벤더가 주는 요약 필드는 시장 국면에 따라 조용히 틀린다.** 실제 시계열(일봉·분봉)로 교차 검증하고, 교정이 일어나면 로그를 남긴다.
- **방지 룰(폴백이 죽었는지 확인)**: "1순위 실패 시 2순위" 구조에서 **1순위가 항상 성공하면 2순위는 영원히 죽은 코드**다. 폴백에 더 정확한 로직을 넣어두고 안심하지 말 것 — 로그나 테스트로 그 경로가 실제로 실행되는지 확인한다.
- **재발 시 진단 순서**: ① 브리핑 본문에 "프리마켓"·"장중"·"현재" 같은 시제 표현이 있으면, 그 수치를 `yf.download(prepost=True, interval='1m')` 마지막 바와 직접 대조. ② 값이 직전 정규장 종가와 정확히 일치하면 연장시간대 미반영을 확정. ③ 실측화한 뒤에는 그 값을 전제로 동작하는 다른 가드(롤오버·이상치 필터)가 오작동하지 않는지 부호까지 재확인.

### 27. 뉴스 수집이 실측과 반대인 서사를 냈다 — 수집 단계 실측 대조 게이트 (2026-07-27, 신설)

**증상**: §26 정정 과정에서 미국 뉴스를 재수집했더니 2회 연속 사용 불가한 결과가 나왔다.
1차는 익명 날조("B사 신규 서비스 출시 지연" — §25 게이트가 즉시 차단),
2차는 실명이 붙었지만 **실측과 방향이 정반대**였다.

| 수집된 주장 | 실측 |
| --- | --- |
| "국제유가 배럴당 80달러 **돌파** → 에너지 관련주 **상승세**" | WTI 83.91, **-6.05%**. CVX -2.9%, XOM -3.3% |
| "중동 긴장 완화 속 국제유가 **상승세 지속**" | 자체 모순 + 실측 반대 |
| "애플 신형 아이폰 생산 차질 루머 → 부품주 약세" | AAPL **+0.4%** 프리마켓 상승 |

**왜 기존 게이트가 다 통과시켰나**: §25(익명)는 실명이 있어 통과, §22(어닝)는 실적 서사가 아니라 통과, `validate_analysis`는 **`call_claude` 이후**라 이미 그 서사로 브리핑이 만들어진 뒤다. 즉 "수치가 틀렸다"도 "주어가 가짜다"도 아닌 **"방향이 반대다"** 라는 제3의 실패 유형이었다.

**수정**:
- `fetch_news._drop_reality_contradictions()` — 뉴스 항목이 주장하는 방향을 실측과 대조해 반대면 항목째 제거. `_fetch_reality_snapshot()`이 유가(CL=F) 실측을 조회하고, 조회 실패 시 판단하지 않는다(fail-open). `call_claude` **이전** 단계라 잘못된 서사가 애초에 분석에 들어가지 않는다.
- 방향어 매칭은 **대상 키워드 앞뒤 25자 창 안에서만** 한다 — 문장 전체를 훑으면 "유가 하락으로 항공주 상승"처럼 서로 다른 대상의 방향어가 교차 매칭된다.
- `validate_analysis.find_session_mislabels()` — **프리장에 거래되지 않는 지수**(SOX·나스닥·S&P500·다우·코스피)를 "프리마켓에서"로 서술하면 경고. 재생성 중 실제로 재발했다(모델이 SOX 금요일 종가 -4.25%를 "프리마켓에서 눌린다"로 서술 — 실제 프리마켓 반도체는 반등 중이라 서사가 정반대). **문장 단위로 판정**하고 제목·본문을 따로 본다 — 이어붙이면 "SOX는 금요일 밀렸어요. 다만 프리마켓에선 AMD가 올랐어요"처럼 세션을 올바로 구분한 서술까지 걸린다. 지수 뒤에 "선물"이 붙으면 제외(지수 선물은 연장시간대에도 거래된다).
- 테스트: `test_news_reality_gate.py`(9), `test_session_mislabel.py`(7).

**그날 처리**: 두 번 다 폐기하고 **뉴스 없이 발행**했다. 이슈는 실측 시장데이터(선물·VIX·금리·유가·경제 캘린더)에서만 구성했고, 폐기한 원본은 `docs/plans/2026-07-27-us-placeholder-news/rejected-news-sample.json`에 증거로 남겼다.

- **방지 룰(제3의 실패 유형)**: LLM 수집 실패는 세 가지 모습으로 온다 — ① 자백("확인되지 않았습니다") ② 익명 날조("B사가…") ③ **실명 + 방향 반대**. ③이 가장 위험하다. 실명이 있어 그럴듯하고, 수치 게이트는 "그 수치가 어디서 왔나"만 보지 "방향이 맞나"는 안 본다. **검증 가능한 실측이 있는 대상(유가·지수·환율·개별주)은 수집 단계에서 방향을 대조한다.**
- **방지 룰(게이트 위치)**: 서사를 만들어내는 단계(`call_claude`) **이전**에 잘라야 한다. 그 뒤에 두면 이미 브리핑 전체가 잘못된 전제 위에 쓰인 뒤라, 항목 하나를 지워도 관점·예측·픽 시나리오에 스며든 서사는 남는다.
- **방지 룰(뉴스 없이 발행해도 된다)**: 수집이 두 번 실패하면 **세 번째를 시도하지 말고 비운 채로 발행한다.** 이슈 섹션이 없는 브리핑은 짧을 뿐이지만, 방향이 반대인 브리핑은 사용자의 판단을 적극적으로 망친다. 실측 시장데이터(선물·VIX·금리·유가·경제 캘린더)만으로도 이슈 섹션은 구성할 수 있다 — 그쪽이 항상 안전한 대안이다.
- **재발 시 진단 순서**: ① 이슈에 방향 서술("상승세"·"급락")이 있으면 그 대상의 실측을 직접 조회해 부호부터 확인. ② 실측과 반대면 `data/news_summary_{type}.json`을 열어 수집 단계에서 온 것인지 확인. ③ "프리마켓에서"라는 표현이 붙은 대상이 실제로 프리장에 거래되는지 확인(지수는 아니다 — §26).

### 28. 코스피 아침 브리핑이 "나스닥 사상 최고치 경신"을 발행 — 뉴스 수집 그라운딩 실패 (2026-07-29 실사고, 수정 완료)

**증상**: 2026-07-29 07:26 KST 코스피 예측 브리핑이 "간밤 미국 증시는 **나스닥이 사상 최고치를 경신**하는 등 기술주 강세"로 시작했다. 실측은 정반대였다 — 나스닥은 **-0.22% 하락 마감**(24,876.91)이었고 최근 고점 대비로도 한참 아래였다. 결정적으로 **같은 페이지 사이드바에 그 -0.22%가 실측으로 찍혀 있었다**(fetch_data 수집분). 본문과 사이드바가 한 화면에서 서로를 부정한 것이다. 같은 뿌리에서 나온 오류가 4개 더 있었다 — "엔비디아 시간외 **+2% 이상** 상승"(실측 +0.25%), "SK하이닉스 ADR 상장", "한은 기준금리 3.50% 동결"(모두 미검증), 그리고 원천 뉴스 요약의 "**S&P500 5,500선 돌파**"(실측 ~7,412).

**근본 원인**: Claude 환각이 아니라 **Gemini 뉴스 수집(`fetch_news.py`)의 그라운딩 실패**다. 당일 `data/news_summary_kospi.json`에 이미 위 내용이 다 들어 있었고 `call_claude`는 충실히 전파했을 뿐이다. 저장된 파일에 **그라운딩 실패의 물증이 셋** 남아 있었는데 어느 것도 감지되지 않았다.

1. **수치가 전부 학습 시점 레벨**: S&P500 5,500(실측 7,412, -26%)·WTI 78달러(실측 ~84)·원/달러 1,350원대(실측 1,457)·한은 기준금리 3.50%. 검색이 아니라 기억에서 쓴 값들이다.
2. **catalysts가 객체가 아니라 문자열 배열**: 프롬프트는 `{date, text}` 객체를 요구하는데 순수 문자열로 왔다. §25가 "수집이 정상 경로를 안 탔다는 선행 신호"라고 적어뒀지만 **감지하는 코드가 없었다**.
3. **프롬프트 출력 예시의 슬롯 라벨을 그대로 echo**: key_indicators 항목이 `"국내 트랙 이슈 1 — 한국 증권거래소는…"`으로 시작했다. 출력 형식 예시에 적어둔 설명 문구를 라벨째 되돌려준 것 — 검색이 아니라 템플릿을 메웠다는 뜻이고, 실제로 그 두 항목이 ADR·금통위 날조의 출처였다.

**기존 게이트 전부가 통과시킨 이유 (서로 다른 구조의 갭이다)**:
- §22 `_us_figure_stale`·§24 `_index_figure_wrong` — **지수명 인접에 등락률 숫자가 있어야** 발화한다. "사상 최고치를 경신"에는 숫자가 하나도 없어 구조적으로 눈이 멀었다.
- §27 `_drop_reality_contradictions` — 실측 대조 기계는 이미 있었지만 `_REALITY_SUBJECTS`에 **유가만** 연결돼 있었다. 지수는 대조 대상이 아니었다.
- 방향 게이트가 지수를 봤더라도 "S&P500 0.3% 상승"은 실측(+0.24%)과 **방향·수치 모두 맞다** — 틀린 건 레벨(5,500)뿐이라 방향 대조로는 못 잡는다.
- §25 익명 게이트 — 주어가 전부 실명(나스닥·엔비디아·한국은행)이라 통과.

**수정**:
- `fetch_news._REALITY_SUBJECTS`에 지수(나스닥·S&P500·다우·필라델피아 반도체) 추가. `_fetch_reality_snapshot()`이 `{change_pct, level, high_52w, low_52w}` 스냅샷을 조회한다(기존 float 형태도 하위호환 수용).
- `fetch_news._superlative_claim_wrong()` — **숫자 없는 정성 최상급 주장**("사상 최고/최저·신고가·신저가")을 실측 등락 방향과 52주 고·저로 판정. 오늘 사고를 직접 막는다.
- `fetch_news._level_claim_wrong()` — 지수명 근처의 레벨 표기("5,500선"·"7,400 돌파")가 실측과 ±15% 넘게 벌어지면 제거. **방향은 맞고 레벨만 틀린** 형태 전용.
- `fetch_news._drop_prompt_slot_echoes()` — 출력 예시 슬롯 라벨을 되뱉은 항목 제거. 함께 **프롬프트의 슬롯 라벨 자체를 제거**(1차 방어) — `"국내 트랙 이슈 1 — …"` → `"(3) …"` + "번호·설명을 출력에 남기지 말 것" 명시.
- catalysts가 전부 문자열이면 **경고 로그**를 남긴다(항목을 버리지는 않는다 — 날짜 미상 거시 촉매를 보호해야 한다).
- `KOSPI_PROMPT`에서 **17일 지난 `[임시 2026-07-12 추가] SK하이닉스 ADR` 줄 제거**. "테마 소멸 시 제거"라고 적어놓고 방치돼, 모델이 프롬프트에 박힌 테마를 **오늘 검색된 뉴스처럼 되돌려주는** 통로가 됐다.
- `validate_analysis.validate_index_superlatives()` — 발행 직전 최종 방어선. 분석 JSON 전체를 재귀 순회해 지수 최상급 주장을 실측 대조하고, **리스트 항목(us_issues·key_drivers·telegram_signals 등)은 제거, 스칼라 산문(why·what·so_what 등)에 남으면 발행 차단**한다. 산문은 자동 교정이 불가능하고, 틀린 전제 위에 쓰인 글은 문장 하나를 지워도 나머지 서사가 그대로 남기 때문이다. 최상급 표현이 없으면 네트워크 조회조차 하지 않고, 실측 조회 실패 시엔 판단하지 않는다(fail-open).
- 테스트: `test_news_index_gate.py`(11), `test_index_superlatives.py`(8). 둘 다 실사고 원문을 리플레이하고, **실제 신고가는 통과**하는 것까지 검증한다.

**그날 처리**: 로컬 `latest_kospi.json`이 2026-04-15자로 stale이라 `generate_html` 재생성은 사이드바 실측을 오염시킨다(§23·§25 선례) → `analysis_snapshot.json` + `index.html`을 **surgical 편집**했다. 날조 서사를 같은 페이지 사이드바의 실측(나스닥 -0.22%·SOX -4.49%·NQ선물 -0.78%)으로 대체하고, 검증 불가 항목(ADR·금통위·엔비디아 +2%)은 대체하지 않고 **제거**했다. 07:30에 이미 발송된 텔레그램은 되돌릴 수 없다(§16 — ad-hoc 정정 발송을 하지 않는다).

**의도적으로 남긴 갭 (다음에 건드릴 때 이 판단을 먼저 읽을 것)**:
- **개별 종목 수치는 수집 단계에서 대조하지 않는다.** 이번 사고의 "엔비디아 시간외 +2% 이상"(실측 종가 +0.25%)은 게이트를 통과한다. 일봉 종가는 **연장시간대를 반영하지 않으므로**(§26), 종가 기준으로 시간외 주장을 반박하면 **정상적인 시간외 보도를 오제거**하게 된다. 종목 수치를 대조하려면 먼저 프리·애프터 실체결가 소스를 붙여야 한다 — 그 전에는 붙이지 않는 것이 맞다.
- **레벨 허용 오차는 ±15%로 느슨하게 뒀다.** 실사고의 "WTI 78달러"(실측 83.91, -7%)는 의도적으로 통과한다. 벤치마크 차이(WTI/브렌트)·인용 시점 차이로 한 자릿수 % 오차는 정상 기사에도 흔해서, 조이면 오제거가 난다. 이 게이트의 목적은 **학습 시점 값을 통째로 가져온 날조**(S&P 5,500 vs 7,412 = -26%)를 잡는 것이다.

- **방지 룰(제4의 실패 유형 — 숫자 없는 주장)**: §27이 정리한 세 유형(자백 / 익명 날조 / 실명+방향 반대)에 하나를 더한다 — ④ **검증 가능한 숫자가 아예 없는 정성 최상급 주장**. "사상 최고치 경신"·"역대급 급등"처럼 숫자가 없으면 모든 수치 게이트가 발화하지 않는다. **정성 표현도 실측으로 판정할 수 있다** — 최고 주장은 "그날 올랐는가 + 52주 고점 근처인가"로 환원된다. 새 게이트를 만들 때는 "이 주장에 숫자가 하나도 없으면 무엇이 잡아내는가"를 반드시 답할 것.
- **방지 룰(레벨도 대조한다)**: 등락률만 맞추면 통과하는 게이트는 **레벨 날조를 놓친다.** LLM이 그라운딩에 실패하면 등락률은 그럴듯하게 지어내면서 지수 레벨은 학습 시점 값을 그대로 쓰는 경향이 있다(S&P 5,500·환율 1,350·기준금리 3.50%처럼 **몇 년 전 값이 세트로 등장**한다). 수치를 검증할 땐 변화량과 절대 수준을 **둘 다** 본다.
- **방지 룰(선행 신호를 코드로 감시한다)**: "스키마 위반은 그라운딩 실패의 신호"라고 **문서에만** 적어두면 아무도 못 본다(§25에 적어뒀지만 이번에 그대로 재현됐다). 신호를 발견했으면 그 자리에서 **감지 코드와 로그**를 만든다 — 문서는 사람이 읽어야 작동하지만 게이트는 매일 자동으로 작동한다.
- **방지 룰(프롬프트의 임시 항목에 만료를 건다)**: `[임시 YYYY-MM-DD 추가, 테마 소멸 시 제거]`로 넣은 검색 힌트는 **아무도 돌아와서 지우지 않는다.** 방치된 힌트는 모델에게 "이건 오늘의 뉴스다"라는 잘못된 사전 정보가 되고, 그라운딩이 실패하면 그대로 되돌아 나온다. 임시 힌트는 날짜 조건으로 게이트하거나(예: `today == "YYYY-MM-DD"`), 넣을 때 제거 기한을 함께 정한다.
- **재발 시 진단 순서**: ① 본문 수치를 **같은 페이지 사이드바**(fetch_data 실측)와 먼저 대조한다 — 한 화면 안에서 모순되면 본문이 틀린 것이다. ② `data/news_summary_{type}.json`을 열어 수집 단계인지 분석 단계인지 가른다. ③ 수집 단계면 **지수 레벨·환율·기준금리를 실측과 비교** — 여러 값이 동시에 몇 년 전 수준이면 그라운딩 실패 확정이다. ④ catalysts가 객체인지, key_indicators가 프롬프트 슬롯 라벨로 시작하는지 확인(둘 다 실패의 물증). ⑤ 정정은 로컬 `latest_{type}.json`의 날짜를 먼저 확인하고, stale이면 재생성하지 말고 스냅샷·HTML을 surgical 편집한다.

### 29. 09:00 장중 이슈가 어제 장 요약 기사를 발행 (2026-07-30 실사고, 수정 완료)

**증상**: `/stocks` 브리핑 스트립의 "장중 이슈" 09:00 항목이 어제(7/29) 내용이었다 — "코스피·코스닥 또 동반 급락…사상 첫 이틀 연속 서킷브레이커 발동", 노무라 급락 배경 코멘트. 둘 다 어제 14:01·15:01에 이미 발행한 이슈를 제목만 바꿔 다시 낸 것이다. `market` 항목 원문 URL은 `viva100.com/article/20260729501199`(기사 ID가 7/29), `stock` 항목(조선일보) 실제 `datePublished`는 오늘 07:48 KST — 날짜만 오늘이고 내용은 어제 장 리캡.

**근본 원인 (두 겹)**:
1. **`_fetch_rss`의 날짜 필터가 "오늘 날짜"만 본다.** 09:00 슬롯이 도는 시점엔 장이 방금 열려 장중 뉴스가 존재하지 않으므로, RSS가 주는 "오늘 날짜" 기사는 전부 **새벽에 발행된 어제 장 리캡**이다. 기존 3시간 컷오프는 09:00 실행 시 06:00이 되어 새벽 리캡을 그대로 통과시켰다.
2. **중복 제거가 오늘 발행분만 대상으로 했다.** `all_today_titles`는 `date == today`일 때만 채워져, 그날 첫 실행(09:00)엔 비교 대상이 하나도 없었다 — 어제 낸 이슈의 재발행을 막을 근거가 코드에 없었다.

**수정** ([fetch_news_live.py](../scripts/fetch_news_live.py)):
- `filter_after_market_open()` — MARKET 슬롯은 `pub_time >= 09:00`(장 개시) 발행분만 채택. `pub_time`을 못 읽은 기사도 제외(발행 시각 검증 불가 → 채택 안 함). 09:00 정각 실행은 이 게이트로 거의 항상 빈손이 되는데 **그게 정상이다** — 개장 직후엔 장중 이슈가 없다. 빈손이면 발행을 생략하고 화면은 오늘 코스피 예측으로 폴백한다(§13).
- `load_prev_day_titles()` — 어제 아카이브의 `seen_titles` + history 타이틀을 dedup **입력**에 합침. 저장되는 `seen_titles`에는 넣지 않는다.
- `_is_dup_title()` — 어절 겹침 **또는 문자 2-gram 겹침**(임계 0.40)으로 판정. 어제 dedup만으로는 이번 사고를 못 막는다는 것을 측정으로 확인했다: 두 쌍의 어절 겹침이 **0.33·0.29**로 임계 0.55에 한참 미달했다("매도" vs "매도와", "배경" vs "배경은", "외인" vs "외국인" — 조사·어미가 다르면 전부 다른 토큰). 같은 쌍의 2-gram 겹침은 0.48·0.68이고 서로 다른 이슈는 0.00~0.27로 사이가 비어 있다. 기존 오늘 dedup에도 함께 적용된다.
- 테스트 `scripts/test_market_session_gate.py`(11) — 실사고 리플레이 + 서로 다른 이슈 오제거 방지 검증.
- 재수집(09:38) 결과: 개장 전 발행 12건 제외 → 09:02~09:25 발행 4건 → dedup 후 2건에서 선별. 채택 기사 원문 URL 200 확인, einfomax `datePublished` = `2026-07-30T09:02:10+09:00`.

- **방지 룰(장중 이슈는 장이 열린 뒤 발행분만)**: "오늘 날짜 기사"는 "오늘 장중 뉴스"가 아니다. 새벽 발행분은 오늘 날짜를 달고 어제 장을 요약한다. 시간대 슬롯이 있는 수집 파이프라인에선 **날짜가 아니라 발행 시각으로** 그 슬롯의 유효 구간을 게이트한다. 슬롯의 첫 실행이 구조적으로 빈손이 되는 것은 결함이 아니다 — 그 시각에 소재가 없다는 사실의 정확한 반영이다.
- **방지 룰(한국어 중복 판정은 어절만으로 부족하다)**: 어절 단위 유사도는 조사·어미 변형에 뚫린다. 같은 사건을 다른 언론사가 다시 쓴 제목은 어절이 절반도 안 겹치는 일이 흔하다. 한국어 제목 중복 판정에는 **문자 n-gram**을 함께 쓰고, 임계는 실제 중복 쌍과 비중복 쌍을 측정해 사이가 비는 값으로 정한다 — 감으로 정하지 않는다.
- **방지 룰(dedup 창을 하루로 끊지 않는다)**: "오늘 발행분과 비교"는 그날 첫 실행에서 항상 무효다. 일자 경계로 리셋되는 상태를 중복 판정 근거로 쓸 때는 **직전 일자까지 포함**해야 첫 실행이 보호된다.
- **재발 시 진단 순서**: ① 의심 항목의 `url`을 직접 열어 실제 발행일시를 확인(경로의 기사 ID·`datePublished`). ② 어제 아카이브(`kospi-news-{어제}.json`) history와 제목을 대조 — 같은 서사면 재발행 확정. ③ 재발행인데 게이트를 통과했다면 `_is_dup_title`의 두 신호를 실제 제목 쌍에 직접 돌려 수치를 확인한다(임계 미달인지, 아예 비교 대상에 없었는지 구분).

### 30. 프리장 등락률이 홈과 상세에서 갈렸다 — 기준가 이중 구현 (2026-07-30 실사고, 수정 완료)

**증상**: 홈 `/stocks` "밤사이 미국 반도체 시황"의 DRAM은 **-1.25%**인데, 클릭해 들어간 `/stocks/us/dram/` 헤더는 **-7.35%**였다. 더 헷갈렸던 건 같은 상세 페이지의 프리장 곡선이 저점 43.30 → 고점 44.26으로 **반등 중**이었다는 점이다 — 한 화면 안에서 헤더와 곡선이 서로 다른 이야기를 했다. 실제로 틀린 것은 **헤더 등락률 하나**였고 곡선·가격은 모두 실측이었다.

가격은 두 화면이 사실상 같았고(44.29 vs 44.26 — 폴링 시차) **분모만** 갈렸다.

| 화면 | API | 기준가 | 등락률 |
| --- | --- | --- | --- |
| 홈 | `/api/stocks-live` | 44.85 = 07-29 정규장 종가 | -1.23% ✅ |
| 상세 | `/api/intraday` | 47.77 = 07-**28** 종가 | -7.35% ❌ |

DRAM 실제 일봉은 07-28 **47.77** → 07-29 **44.85**다. 07-29에 이미 -6.1% 빠진 것을 상세 페이지가 **오늘 프리장 낙폭으로 이중 계상**했다. `(44.26 − 47.77) / 47.77 = −7.35%`로 화면 값과 정확히 일치해 산식까지 확인됐다.

**근본 원인 — Yahoo `previousClose`의 정의**: `api/intraday.mjs`가 `meta.chartPreviousClose ?? meta.previousClose`를 기준가로 썼는데, 이 필드는 **`regularMarketTime`(직전 정규장 마감) 기준 하루 전**이다.

- 정규장 중 → `regularMarketTime`이 오늘이라 `previousClose` = 어제 종가 = **맞다**
- 프리장·애프터장 → `regularMarketTime`이 직전 마감이라 `previousClose` = 그 **하루 전** = **틀리다**

즉 버그는 프리장·애프터장에만 나타난다 — 한국 사용자가 미국 종목을 보는 저녁·밤이 정확히 그 구간이다. DRAM·NVDA·AVGO·MU·SOXX 5종목 전부 동일하게 재현돼 **DRAM 고유 문제가 아니라 미국 상세 페이지 전체**의 구조적 오류였다.

**왜 오래 안 들켰나 — §20 이중 소스가 그대로 재현됐다**: `api/stocks-live.mjs`는 프리·애프터장에서 `regularMarketPrice`를 기준가로 써서 **처음부터 정확했다**. 정답 구현이 같은 저장소에 이미 있었는데 두 API가 각자 판정해 한쪽만 맞았다. 홈이 정상이라 "프리장 등락률은 잘 나온다"는 인상이 생겨 상세 쪽 오류가 가려졌다.

**수정**:
- [_us-session.mjs](../api/_us-session.mjs) 신설 — `usSessionState(meta, nowSec)` / `usBaseClose(meta, state)`. `stocks-live`의 검증된 로직을 그대로 추출해 **두 API가 공유**한다. 파일명이 `_`로 시작하는 건 Vercel이 `api/` 안의 `_` 접두 파일을 라우트로 만들지 않기 때문이다.
- 세션별 기준가 매핑 — `pre` → `regularMarketPrice`(어제 정규장 종가), `post` → `regularMarketPrice`(당일 정규장 종가), `open`·`closed` → `chartPreviousClose`(전일 종가). 네 경우 모두 클라이언트가 그리는 곡선 구간과 일치한다.
- [intraday.mjs](../api/intraday.mjs) — 응답에 `baseClose`·`session` 추가. `prevClose`는 하위호환으로 유지(국내 `?code=` 소비처가 여럿이라 스키마를 좁히지 않는다).
- [stocks.js](../web/assets/stocks.js) — 헤더 기준가를 `baseClose` 우선, 없으면 `prevClose` 폴백.
- [stocks-live.mjs](../api/stocks-live.mjs) — 인라인 판정을 공용 모듈 호출로 교체. 같이 발견한 잠복 버그도 수정 — `isFinite(null)`이 `true`라 `price`가 null일 때 통과해 **-100%**가 만들어질 수 있었다(`typeof price !== 'number'`를 추가).
- 테스트 `api/_us-session.test.mjs`(9) — 네 세션 × 기준가 + 실사고 리플레이(44.26이 -1.3%대여야 하고 -7.35%가 아님) + 공휴일·meta 불완전 방어.

- **방지 룰(기준가는 세션마다 다르다)**: 등락률의 **분모는 발행·조회 시점의 세션에 따라 달라진다.** 하나의 "전일 종가" 개념을 모든 세션에 일괄 적용하면 프리장·애프터장에서 반드시 틀린다. 벤더의 `previousClose`류 필드가 **무엇 기준의 하루 전인지**를 확인하고(여기선 `regularMarketTime` 기준), 세션별 매핑을 명시적으로 코드에 적는다. §24가 "분모도 실측 검증한다"였고 §26이 "발행 시각이 곧 지금이다"였다면, 이번은 그 둘의 교집합이다 — **분모의 기준 시점도 세션에 따라 움직인다.**
- **방지 룰(판정 로직을 두 번 쓰지 않는다)**: 같은 판정(기준가 선택·세션 구분)을 두 API가 각자 구현하면 한쪽만 맞고, **맞는 쪽이 있기 때문에** 틀린 쪽이 더 오래 방치된다. §20이 "같은 데이터의 이중 소스"를 금지한 이유가 이것이고, 이번엔 데이터 소스가 아니라 **계산 로직**이 갈라져 같은 사고가 났다. 공용 모듈로 추출하고 테스트가 두 소비처를 모두 커버하게 한다.
- **방지 룰(한 화면 안의 모순을 신호로 읽는다)**: 이번 사고는 곡선(정상)과 헤더(오류)가 같은 카드 안에서 어긋나 발견됐다. §28의 "본문 수치를 같은 페이지 사이드바와 대조한다"와 같은 원리다 — **한 화면에서 두 요소가 서로를 부정하면 둘 중 하나는 확실히 틀렸다.** 사용자 신고가 "이상하다"로 올 때 먼저 같은 화면 안의 다른 요소와 교차 대조한다.
- **재발 시 진단 순서**: ① 홈과 상세의 **가격**을 먼저 비교 — 같으면 분자는 정상이므로 분모를 의심한다. ② 표시된 등락률로 기준가를 역산하고(`price / (1 + pct/100)`) 그 값이 일봉 어느 날짜의 종가인지 대조 — 한 세션 밀렸는지 바로 드러난다. ③ `range=1d&includePrePost=true` meta에서 `regularMarketPrice`와 `chartPreviousClose`를 직접 찍어 두 값이 다른지 확인(프리·애프터장엔 반드시 다르다). ④ 같은 값을 계산하는 다른 API가 있으면 그 구현과 대조 — 한쪽이 맞으면 로직이 갈라진 것이다.

### 29. 이미 끝난 FOMC를 두 브리핑이 '예정'으로 발행 — 캘린더 시제 + 수집 그라운딩 실패 (2026-07-30 실사고, 수정 완료)

**증상**: FOMC는 2026-07-29 14:00 ET(= **07-30 03:00 KST**)에 끝났는데, 같은 날 07:25 코스피 브리핑과 21:17 미국 브리핑이 **모두** 이를 "아직 발표되지 않은 예정 이벤트"로 서술했다("동결이 **유력하지만**", "결과 발표를 **앞두고**", "**예정돼 있어요**"). 부수적으로 연준 의장을 **파월**로 썼는데 실제 의장은 **케빈 워시**였고, 실제 결과는 매파적(9-3 동결, 점도표 18명 중 9명이 연내 인상 지지, 워시가 포워드 가이던스 미제공 명시)인데 브리핑은 **"인하 시점 힌트"**를 전제로 서술했다. 같은 미국 브리핑에 익명 플레이스홀더 `C 은행`이 **실명 씨티그룹으로 승격**된 날조 이슈도 함께 실렸다(씨티는 당일 +2.49%인데 ▼ 하락 요인 표기).

**결정적 정황**: 같은 코스피 페이지의 국내 이슈 섹션에는 실수집 뉴스로 **"연준, 기준금리 3.50∼3.75% 동결"·"5회 연속 동결…'매파 경고음'"**이 이미 실려 있었다. **한 화면 안에서 AI 서술이 실수집 데이터와 정면으로 모순**했다(§28의 "본문을 같은 페이지 실측과 먼저 대조하라"가 그대로 적용되는 사례).

**근본 원인 (5개, 층위가 서로 다름)**

1. **캘린더가 날짜 단위로만 '오늘'을 판정** — `fetch_data.fetch_economic_calendar()`가 `date_kst_date == today_kst`로만 분류해 **시각을 무시**했다. `date_kst`에 `03:00 KST`가 들어 있는데도, 21:15에 나가는 미국 브리핑에서 그날 새벽 이벤트가 그대로 `today`에 남았다.
2. **유일한 발표여부 판별자가 죽어 있었다** — 프롬프트는 "actual이 빈 문자열이면 아직 미발표"라고 지시했지만, 소스 `ff_calendar_thisweek.json`을 직접 조회해보니 **7/27~7/31 전체 92건 중 `actual`이 채워진 건 0건**이었다(85분 전 발표된 Core PCE·GDP조차 빈 문자열). 이 피드는 결과가 없는 **순수 일정 피드**다. 즉 이 판별자는 항상 "미발표"만 반환하는 §26형 **죽은 폴백**이었고, 1번과 결합해 오류가 **결정적으로** 발생했다.
3. **§25 익명 게이트가 공백 하나로 뚫렸다** — 정규식이 `[A-Z](?:은행|증권|…)`이라 `C은행`은 막지만 `C 은행`(공백)은 통과했다. 그다음 분석 단계가 이 익명 주어를 **실명 씨티그룹(티커 C)** 으로 승격시켜, §25보다 악화된 형태(실명이 붙어 더 그럴듯한 날조)가 됐다.
4. **수집 그라운딩 실패 신호가 데이터에 남았는데 아무도 판정하지 않았다** — 그날 `news_summary_us.json`에 물증이 셋 있었다. ① catalysts가 객체가 아닌 **문자열 배열**(스키마 위반) ② FOMC·GDP·Core PCE가 전부 잡혀 있는 날에 **"오늘 발표될 주요 경제 지표는 예정되어 있지 않으나"** ③ 익명 플레이스홀더. §25·§28이 "스키마 위반은 선행 신호"라고 **문서에만** 적어뒀고 감지 코드가 없었다.
5. **US 프롬프트엔 economic_calendar 설명이 아예 없었다** — 상세 설명은 KOSPI 프롬프트에만 있었고, 미국 브리핑은 캘린더 JSON을 아무 시제 지침 없이 받았다.

**수정**

- `fetch_data._bucket_calendar_events()` 신설 — **시각까지 비교**해 이벤트마다 `status: "released"|"upcoming"`을 붙인다. 순수 함수로 분리해 네트워크 없이 테스트한다.
- `call_claude._calendar_tense_directive()` — 끝난 이벤트가 있을 때만 user_content에 시제 지시를 주입한다(§24 `_session_label_directive` 패턴). **세 브리핑을 한 번에 덮으므로** 프롬프트 상수 3곳에 복붙하지 않는다. 프롬프트의 죽은 `actual` 규칙은 `status` 기반으로 교체하고, 관전 포인트는 `status="upcoming"`만 넣도록 했다.
- `fetch_news._PLACEHOLDER_ENTITY_RE`에 `\s*` 추가 — 공백 변형 차단.
- `fetch_news._grounding_failure_signals()` / `_is_grounding_failure()` **신설(근본 처방)** — 개별 문장을 반박하는 대신 **수집 결과 전체의 신뢰도**를 판정한다. 신호 2개 이상이면 뉴스 요약을 통째로 버리고 **뉴스 없이 발행**한다(§27). 익명 플레이스홀더 신호는 항목이 제거되기 전에 봐야 하므로 **개별 항목 게이트보다 먼저** 돌린다.
- `validate_analysis.validate_event_tense()` — 발행 직전 최종 방어선. 끝난 이벤트를 예고형으로 쓴 **리스트 항목은 제거, 스칼라 산문은 발행 차단**(§28 선례). 끝난 이벤트가 없으면 즉시 반환하고 네트워크 조회도 없다.
- 테스트 33건 추가(전체 450건 통과). 실사고 리플레이로 정정 전 스냅샷에서 **코스피 항목제거 3 + 발행차단 1**, 미국 항목제거 1, 수집 게이트 **폐기 판정**을 확인했고, 정정본은 0건으로 통과하는 것까지 검증했다.

**방지 룰**

- **시제 판정은 날짜가 아니라 시각으로 한다.** 발행 시각이 그날 안에 있는 브리핑(코스피 07:25 / 마감 16:25 / 미국 21:15)은 "오늘 = 아직 안 옴"이 성립하지 않는다. 같은 날 새벽 이벤트는 **세 브리핑 모두에서 이미 과거**다. (§24 "'간밤'을 상수로 박지 말 것"과 같은 계열 — 이번이 네 번째 재발이다.)
- **벤더 필드가 실제로 채워지는지 직접 확인하고 쓴다.** "actual이 있으면 발표됨" 같은 판정을 넣기 전에 소스를 며칠치 조회해 그 필드가 실제로 채워지는지 본다. **항상 같은 값만 반환하는 판별자는 판별자가 아니라 죽은 코드**이고, 있으면 오히려 "판정하고 있다"는 착각을 준다(§26).
- **정규식 게이트를 하나 더 추가하려 할 때 먼저 물을 것 — "이건 입력 단계에서 걸러졌어야 하는 것 아닌가?"** §22→§24, §25→§29, §27→§28 모두 앞선 정규식이 다음 변형(한글·공백·다른 대상)에 뚫린 사례다. 표현 공간은 무한하고 정규식은 유한하므로 이 경주는 계속 진다. **수집 결과의 신뢰도를 통째로 판정하는 쪽**이 비용 대비 효과가 훨씬 크다.
- **"선행 신호"를 발견하면 문서가 아니라 코드에 남긴다.** 문서는 사람이 읽어야 작동하고 게이트는 매일 자동으로 작동한다. §25·§28이 스키마 위반을 신호로 지목해뒀지만 감지 코드가 없어 이번에 그대로 재현됐다.
- **프롬프트 설명이 브리핑 타입별로 갈라져 있는지 확인한다.** 이번엔 캘린더 설명이 KOSPI에만 있었다. 공통 규칙은 프롬프트 상수 복붙 대신 **데이터 기반 지시 주입**으로 한 곳에서 관리한다.

**재발 시 진단 순서**: ① 브리핑 본문의 이벤트 시제를 **같은 페이지의 국내 이슈·사이드바(실수집·실측)** 와 먼저 대조 — 한 화면 안에서 모순되면 AI 서술이 틀린 것이다. ② `data/latest_{type}.json`의 `economic_calendar.today`에서 해당 이벤트의 `date_kst`와 **발행 시각**을 직접 비교. ③ `status`가 없거나 전부 upcoming이면 `_bucket_calendar_events`가 안 타는 경로(캐시된 옛 파일 등)를 의심. ④ `data/news_summary_{type}.json`에서 catalysts가 객체인지, 캘린더에 일정이 있는데 "지표 없음"이라 적혔는지 확인 — 둘 다 그라운딩 실패의 물증이다. ⑤ 정정은 로컬 `latest_{type}.json`의 날짜를 먼저 확인하고, stale이면 재생성하지 말고 스냅샷·HTML을 surgical 편집한다(§23·§28).
