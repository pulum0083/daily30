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

> **브리핑에 사용되는 모든 데이터는 해당 브리핑 생성 시점에 실제로 수집한 데이터만 사용한다.**
>
> - 주가·등락률·수급·종목 픽 등 모든 수치는 생성 당시 fetch_data / fetch_closing_kospi / toss_client 등이 수집한 실측값만 허용한다.
> - 수집에 실패했거나 검색되지 않은 데이터는 표시하지 않는다. 빈 값으로 두거나 섹션을 생략한다.
> - 어떤 이유로도 데이터를 억지로 생성(추론·추정·보간·하드코딩)하지 않는다. LLM이 만든 숫자, 캐시된 이전 세션 데이터, 출처 불명의 값은 사용 금지.
>
> **화면에 표시되는 모든 수치는 실측이어야 한다. LLM이 생성한 숫자는 신뢰하지 않고, 발행 전 실제 시장 데이터로 덮어쓴다.**

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
- 기준: 직전 완료 세션 종가 대비 등락률(`close[-1] vs close[-2]`), 실시간 장중가 아님.

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

### 10. 라이브 스코어보드 — 구조와 운영 규칙

`web/assets/main.js`의 `initLiveScoreboard()` 함수가 담당. 당일·과거 브리핑 모두 표시.

#### 상태별 동작

| 상태         | 조건             | 동작 |
| ---------- | -------------- | ---- |
| 장 전 (준비 중) | 당일 08:50~08:59 | 카운트다운 표시 |
| 장 중 (LIVE) | 당일 09:00~15:30 | `/api/kospi-live` 10초 폴링 |
| 장 후 (당일)   | 당일 15:30 이후    | 최종 종가 fetch 후 예측 결과 표시 |
| 과거 브리핑     | URL 날짜 < 오늘    | 정적 결과 표시 (폴링 없음) |
| 숨김         | 장 시작 전(~08:49) | `display:none` |

- **결과 미집계**: `data-actual-pct`가 비어 있으면 "결과 집계 중…". 다음 날 09:10 `check_accuracy.py` 실행 후 자동 주입.
- 스코어보드 HTML은 `buildPanel()`이 동적 생성 — 인라인 HTML에서 ID를 찾으려 하면 찾을 수 없다.
- `isPast` 플래그는 `initLiveScoreboard()` 내부 클로저 변수. `initLiveMarketPanel()`은 별도로 `mktIsPast`를 계산한다.

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

총 22회/일. Vercel cron 사용 금지 (Hobby 플랜 cron 2개 제한) — GHA native schedule 사용.

**`get_slot()` 시간대 경계값:**
```
09:00~15:29 KST → MARKET
16:35~21:29 KST → POST_MARKET
21:30~01:00 KST → US_MARKET
```

#### 이슈 브리핑 섹션 위치·표시 규칙

표시 조건: `issue_news.history` 1개 이상일 때만 섹션 표시.

| 브리핑 | 위치 | 표시 슬롯 |
| --- | --- | --- |
| 코스피 예측 브리핑 | 스코어보드 아래, 예측 카드 위 | `MARKET` |
| 코스피 마감 브리핑 | 마감 시황 아래, 수급 위 | `POST_MARKET` |
| 미국 시장 브리핑 | 본문 최상단 | `US_MARKET` |

**`initIssueBriefing()` 동작 (`web/assets/main.js`):**
- `#issue-briefing-wrap`의 `data-date`, `data-slot` 읽기
- `/data/kospi-news-{date}.json` fetch (없으면 `kospi-news-live.json` fallback)
- `data-slot` 범위로 history 필터링 후 1개 이상이면 표시, 0개면 `display:none`

**수집 구조 — RSS 기반 2단계 파이프라인 (2026-06-16 적용):**

1단계: Google News RSS로 오늘 날짜 기사 실수집 (날짜·제목 실데이터).
2단계: Gemini(`google_search` 미사용)가 목록에서 선별 + 요약만 담당.

- 날짜 세탁 원천 차단: pub_date 는 RSS 가 보장 → Gemini 가 날짜를 만들 수 없음.
- 슬롯별 RSS 소스: `_GN_KR` (한국어 Google News RSS), `_GN_EN` (영어 Google News RSS).
- 오늘 날짜 기사가 2건 미만이면 발행 생략 (exit 0).

**이슈 중복 방지**: 오늘 기발행 타이틀 목록을 Gemini 프롬프트에 주입해 동일 주제를 피하도록 유도.

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
- **출처 링크 우선순위**: `url` 필드(grounding 메타데이터)가 있으면 원본 링크, 없으면 `이름 + source + time_label` 구글 검색 폴백. `generate_html.py`의 `build_analyst_quotes()`가 처리.
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
- **휴일 처리**: 클라이언트 휴일 목록 없이도, 휴일엔 당일 브리핑이 ready가 아니므로 자동으로 숨겨진다.
- **issue 슬롯**: 이슈 미수집(예: 09:00~첫 수집 전)이면 오늘 kospi 예측으로 폴백, 그것도 없으면 숨김. 클릭 시 `/briefings/{date}/kospi/`로 이동.
- `getKSTSlot` 경계값을 임의로 바꾸지 말 것. 위 표가 정본이다.
