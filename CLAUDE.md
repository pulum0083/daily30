# Double-Shot — AI 투자 브리핑 서비스

## 프로젝트 개요

매일 아침 코스피·저녁 미국 시장 AI 예측 브리핑을 자동 생성해 텔레그램·이메일로 발송하는 서비스.
Gemini(뉴스 요약) + Claude(분석·예측) 하이브리드 파이프라인으로 구동된다.

## 서비스 URL

| 구분 | URL |
|------|-----|
| 랜딩페이지 | **https://doubleshot.space** |
| 브리핑 목록 | **https://doubleshot.space/briefings** |
| 코스피 브리핑 | **https://doubleshot.space/briefings/{YYYY-MM-DD}/kospi/** |
| 마감 브리핑 | **https://doubleshot.space/briefings/{YYYY-MM-DD}/close/** |
| 미국 브리핑 | **https://doubleshot.space/briefings/{YYYY-MM-DD}/us/** |

호스팅: Vercel (정적 서빙 + Cron 트리거) + GitHub Pages (`gh-pages` 브랜치, Vercel 배포 시 병행)

## 브리핑 스케줄

| 브리핑 | 실행 시각 (KST) | 요일 |
|--------|----------------|------|
| 코스피 시초가 | 07:30 | 평일 (월~금) |
| 코스피 마감 | 16:30 | 평일 (월~금) |
| 미국 시장 | 21:20 | 평일 (월~금) |
| 예측 정확도 체크 | 09:10 | 평일 (화~토) |

## 실행 흐름

```
cron-job.org → /api/trigger?type=kospi
  → GitHub Actions workflow_dispatch
    → 휴장일 확인 (holiday_check.py)
    → 시장 데이터 수집 (fetch_data.py / fetch_closing_kospi.py)
    → 뉴스 요약 (fetch_news.py — Gemini 2.5 Flash Lite)
    → AI 분석·예측 (call_claude.py — Claude Sonnet 4.6, Prompt Caching)
    → latest.json 갱신 (update_latest.py)
    → 텔레그램 전송 (send_telegram.py)
    → 이메일 전송 (send_email.py → Resend API)
    → HTML 생성 & main 커밋·푸시 (generate_html.py)
      → web/data/briefings-list.json 자동 갱신 (write_briefings_list_json)
    → GitHub Pages 배포 (gh-pages 브랜치)
```

## 디렉토리 구조

```
daily30/
├── CLAUDE.md
├── vercel.json                      # Vercel 라우팅 + Cron 스케줄 설정
├── api/
│   ├── trigger.mjs                  # Vercel Cron → GitHub Actions dispatch
│   └── subscribe.mjs                # 이메일 구독 신청 API (최신 브리핑 즉시 발송)
├── scripts/
│   ├── call_claude.py               # Claude Sonnet 4.6 + Prompt Caching 분석 생성
│   ├── fetch_data.py                # yfinance 기반 코스피·미국 시장 데이터 수집
│   ├── fetch_closing_kospi.py       # 코스피 마감 데이터 수집 (수급·장중·시장폭·dpick)
│   ├── fetch_news.py                # Gemini 2.5 Flash Lite 뉴스 요약
│   ├── generate_html.py             # config-driven HTML 브리핑 조립기
│   │                                #   --type {kospi|us|kospi-close} --date YYYY-MM-DD --data-file <path>
│   │                                #   --write-list-only  → HTML 재생성 없이 briefings-list.json만 갱신
│   ├── send_telegram.py             # 텔레그램 전송
│   ├── send_email.py                # Resend API 이메일 전송
│   ├── update_latest.py             # web/data/latest.json 갱신 (구독 API용)
│   ├── holiday_check.py             # 한국/미국 공휴일 확인
│   ├── patch_fg.py                  # Fear & Greed 지수 HTML 패치 (09:05 KST)
│   ├── check_accuracy.py            # 전일 예측 정확도 체크
│   ├── config/
│   │   ├── kospi.json               # 코스피 브리핑 섹션 선언
│   │   ├── close.json               # 마감 브리핑 섹션 선언
│   │   └── us.json                  # 미국 브리핑 섹션 선언
│   └── templates/
│       ├── base.html                # 공통 레이아웃 (GNB, CSS/JS 경로)
│       ├── briefings/
│       │   ├── kospi.html           # 코스피 예측 브리핑 템플릿
│       │   ├── close.html           # 코스피 마감 브리핑 템플릿
│       │   └── us.html              # 미국 시장 브리핑 템플릿
│       ├── pages/
│       │   └── briefings_index.html # 브리핑 목록 페이지 템플릿
│       └── sections/                # 공통 섹션 partial 템플릿
├── web/
│   ├── landing.html                 # 랜딩페이지 (/ 라우팅)
│   ├── favicon.svg
│   ├── briefings/
│   │   ├── index.html               # 브리핑 목록 (/briefings) — 항상 최신 브리핑 본문 포함
│   │   └── YYYY-MM-DD/
│   │       ├── kospi/index.html     # 코스피 예측 브리핑
│   │       ├── close/index.html     # 코스피 마감 브리핑
│   │       └── us/index.html        # 미국 시장 브리핑
│   ├── data/
│   │   ├── latest.json              # 최신 브리핑 요약 (구독 API가 읽음)
│   │   └── briefings-list.json      # 날짜별 슬롯 상태 (브리핑 목록 동적 패치용)
│   └── assets/
│       ├── style.css
│       ├── main.js
│       ├── briefing-list.js
│       └── og-image.svg
├── data/
│   ├── briefings.json               # 예측·정확도 누적 데이터 (커밋됨)
│   ├── supply_history.json          # 외국인·기관·개인 7일 수급 히스토리 (커밋됨)
│   ├── latest_kospi.json            # 최신 코스피 시장 데이터 (gitignore)
│   ├── latest_us.json               # 최신 미국 시장 데이터 (gitignore)
│   ├── latest_kospi_close.json      # 최신 마감 데이터 (gitignore)
│   ├── analysis_kospi.json          # Claude 분석 결과 (gitignore)
│   ├── analysis_us.json             # Claude 분석 결과 (gitignore)
│   ├── analysis_kospi-close.json    # Claude 마감 분석 결과 (gitignore)
│   ├── news_summary_kospi.json      # Gemini 뉴스 요약 (커밋됨)
│   └── news_summary_us.json         # Gemini 뉴스 요약 (커밋됨)
├── .github/workflows/
│   └── daily_report.yml             # kospi / us / kospi-close / accuracy 4개 job
└── config.json                      # API 키 (gitignore — config.example.json 참조)
```

## AI 파이프라인

### 뉴스 수집 — Gemini 2.5 Flash Lite (`fetch_news.py`)
- 구글 검색 기반 뉴스 크롤링 후 요약
- `data/news_summary_{type}.json` 저장

### 뉴스 수집 — Gemini 2.5 Flash + Google Search grounding (`fetch_news.py`)
- `google_search` tool로 그 시점 최신 뉴스를 **직접 검색·요약**(1회 호출). RSS 파싱 제거됨.
- 브리핑 타입별 검색 프롬프트(KOSPI/KOSPI_CLOSE/US)로 검색 키워드 지시.

### 분석·예측 — Claude Sonnet 4.6 (`call_claude.py`)
- **Prompt Caching** 적용 (시스템 프롬프트 캐시, ~5분 TTL, 재실행 시 90% 비용 절감)
- 출력: JSON only (`analysis_{type}.json`) → HTML 생성은 `generate_html.py`가 담당
- 생성 항목: `prediction` (direction / up_pct / confidence), `reasons`, `reason_title`, `stock_picks`

### 데이터 검증 게이트 — `validate_analysis.py`
- call_claude(`--no-html`) → **validate_analysis** → call_claude(`--render`) → telegram 순으로 동작.
- 픽 종목 실측 주입(미국 yfinance·한국 네이버 일봉) + 본문 금지패턴·환율·지수%·수급 스케일 교정.
- 치명적 오류 시 발행 중단 + 관리자 텔레그램 알림.

### 마감 데이터 수집 — `fetch_closing_kospi.py`
- 장중 흐름 (intraday), 수급 (investor_trading), 시장 폭 (market_breadth), 섹터 (sectors)
- 거래대금 급증 × 수급 동반 종목 (dpick): 외국인·기관 동시 순매수 + 거래대금 1.5배↑
- 코스피200 TOP10 (kospi200_top10), AI 반도체 종목 (ai_semicon_stocks)
- 출력 필드: `market_breadth.up/down/unchanged/upper_limit/lower_limit`

## API 키 / 환경변수

| 변수 | 용도 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude Sonnet 4.6 |
| `GEMINI_API_KEY` | Gemini 2.5 Flash Lite |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 |
| `TELEGRAM_CHAT_ID` | 텔레그램 채널 |
| `RESEND_API_KEY` | 이메일 발송 (Resend) |
| `GH_PAT` | Vercel → GitHub Actions dispatch |
| `TOSS_CLIENT_ID` | 토스증권 Open API — 종목 캔들·현재가·환율 조회 |
| `TOSS_CLIENT_SECRET` | 토스증권 Open API 시크릿 |

GitHub Actions Secrets에 모두 등록되어 있음.

### 토스증권 Open API (`scripts/toss_client.py`)

- **용도**: 종목 캔들(일봉), 현재가 일괄 조회, USD/KRW 환율 조회.
- **인증**: OAuth2 `client_credentials` 방식. `_get_token()`이 토큰을 캐싱(메모리, ~24h TTL).
- **키 우선순위**: 환경변수 `TOSS_CLIENT_ID` / `TOSS_CLIENT_SECRET` → `config.json` `toss.client_id` / `toss.client_secret`.
- **엔드포인트**: `https://openapi.tossinvest.com`
  - `GET /api/v1/candles` — 일봉/1분봉 (1회 최대 200개, `nextBefore`로 페이지네이션)
  - `GET /api/v1/prices` — 현재가 일괄 (최대 200개)
  - `GET /api/v1/exchange-rate` — 환율 (`midRate`)
- **심볼 형식**: 한국 종목 6자리 코드 그대로, 미국 종목 티커 그대로 사용 (`.KS`/`.KQ` 접미사 불필요).

#### 실측 조회 우선순위 (`validate_analysis.py`)

| 종목 | 1순위 | 2순위 (폴백) |
|------|-------|-------------|
| 한국 종목 | 토스증권 Open API | 네이버 일봉 (`api.stock.naver.com`) |
| 미국 종목 | 토스증권 Open API | yfinance |
| 환율 | 토스증권 Open API | (없음 — 실패 시 `None` 반환) |

토스 API가 미설정이거나 응답 실패 시 자동으로 폴백 소스를 사용한다.

## 이메일 발송

- **브리핑 자동 발송**: `send_email.py` → `pulum0083@gmail.com` (매 브리핑 후 자동)
- **구독 웰컴 발송**: `api/subscribe.mjs` → 구독 신청 시 최신 브리핑 즉시 발송
- 발신 주소: `noreply@doubleshot.space` (Resend 도메인 인증 완료)

## Vercel 라우팅

```
/                              → landing.html
/briefings/                    → briefings/index.html
/briefings/{date}/kospi/       → briefings/{date}/kospi/index.html
/briefings/{date}/close/       → briefings/{date}/close/index.html
/briefings/{date}/us/          → briefings/{date}/us/index.html
/briefings/ko/{date}/          → briefings/{date}-kospi.html  (레거시 호환)
/briefings/us/{date}/          → briefings/{date}-us.html     (레거시 호환)
/briefings/ko-close/{date}/    → briefings/ko-close/{date}/index.html (레거시 호환)
```

## GitHub Actions Workflow (`daily_report.yml`)

4개 job, 모두 `workflow_dispatch` 트리거 (Vercel Cron이 `/api/trigger`로 dispatch):

| job | 트리거 type | 주요 스텝 |
|-----|------------|-----------|
| `kospi-briefing` | `kospi` | fetch_data → fetch_news → call_claude → **update_latest** → telegram → email → generate_html → commit → pages |
| `us-briefing` | `us` | 동일 구조 |
| `kospi-close-briefing` | `kospi-close` | fetch_closing_kospi → fetch_news → call_claude → telegram → generate_html → commit → pages |
| `kospi-accuracy` | `accuracy` | check_accuracy → commit |

---

## 운영 규칙

### 0. 데이터 정합성 — 자동 검증 파이프라인 (핵심)

> **화면에 표시되는 모든 수치는 실측이어야 한다. LLM이 생성한 숫자는 신뢰하지 않고, 발행 전 실제 시장 데이터로 덮어쓴다.**

**파이프라인 순서 (절대 바꾸지 말 것):**

```
call_claude --no-html   분석 JSON만 (HTML·텔레그램 생성 안 함)
      → validate_analysis   픽 실측 주입 + 본문 교정
      → call_claude --render   교정된 데이터로 웹 페이지·텔레그램 메시지 생성
      → send_telegram   웹 페이지 생성 후 발송
```

LLM 출력(HTML·텔레그램)이 검증 *이전*에 만들어지면 교정이 반영되지 않는다. 새 출력물을 추가할 때도 반드시 `--render`(검증 이후) 단계에서 생성한다.

**종목 픽 실측 주입 (`enrich_picks_with_realdata`):**
- 미국 종목 → **토스증권 Open API** 우선, 실패 시 **yfinance** 폴백.
- 한국 종목 → **토스증권 Open API** 우선 (6자리 코드 그대로), 실패 시 **네이버 일봉** 폴백 (`api.stock.naver.com/chart/domestic/item/{code}/day`). **6자리 코드만 사용, `.KS`/`.KQ` 접미사 금지.**
  - ⚠️ yfinance에 `.KS`를 붙이면 KOSDAQ 종목이 유령 데이터(하루 stale·틀린 가격)를 반환한다. 토스·네이버는 코드만으로 시장을 정확히 식별한다.
- 기준: 직전 완료 세션 종가 대비 등락률(`close[-1] vs close[-2]`), 실시간 장중가 아님.

**실측 소스가 없는 영역은 수치를 표시하지 않는다:**
- 미국 프리장 신고가(`premarket_highs`), 낙수 섹터 등락률(`spill` tag) → 정성 정보만, 숫자 제거.

**검증 범위 (현재):** 픽·사이드바·마감 카드는 실측. 본문 산문(reasons·scenario·마감 WHY/WHAT/SO)은 금지단위·환율·지수%·수급 100배 스케일만 검증 — 산문 내 개별 종목 수치는 구조적 미검증이므로 수동 점검 시 주의.

### 1. 브리핑 데이터 수동 검증 — 의심 없이 확인, 틀리면 수정 후 커밋

> **자동 게이트가 있어도, 수동 패치·재생성 시에는 LLM이 생성한 가격·수치를 실제 시장 데이터로 검증하고 반영한다.**

#### 종목 가격·등락률 (코스피·미국 예측 브리핑)

`analysis_*.json`의 종목 가격·등락률은 **LLM 할루시네이션** 가능성이 있다.
HTML 반영 전 반드시 yfinance 또는 네이버 금융으로 실제 값을 확인하고 덮어쓴다.

```python
# 가장 안전한 방법: validate_analysis의 함수 직접 재사용 (토스→폴백 자동 처리)
from scripts.validate_analysis import _fetch_kospi_realdata, _fetch_us_realdata
result = _fetch_kospi_realdata("005930")  # 한국: 6자리 코드
result = _fetch_us_realdata("BAC")        # 미국: 티커

# 토스 API 직접 사용 (toss_client.py)
import scripts.toss_client as tc
candles = tc.get_candles("005930", interval="1d", count=300)  # 한국
candles = tc.get_candles("BAC",    interval="1d", count=300)  # 미국
closes = [float(c["closePrice"]) for c in candles if c.get("closePrice")]

# 네이버 일봉 폴백 (토스 실패 시)
import urllib.request, json
from datetime import datetime, timedelta
code = "005930"
end = datetime.now().strftime("%Y%m%d") + "0000"
start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d") + "0000"
url = f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime={start}&endDateTime={end}"
rows = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})).read())
closes = [r["closePrice"] for r in rows if r.get("closePrice")]  # 오래된→최신

# yfinance 폴백 (미국, 토스 실패 시)
import yfinance as yf
hist = yf.Ticker("BAC").history(period="5d").dropna(subset=["Close"])
```

> ⚠️ 국내 종목에 `yf.Ticker("{code}.KS")`를 쓰지 말 것. KOSDAQ 종목이 유령 데이터(하루 stale·틀린 가격)를 반환한다.

- 가격이 실제와 차이나면 → 가격·등락률·MA200·진입/목표/손절·sparkline 모두 일괄 수정.
- **sparkline 빈 배열** `drawMiniChart('mc-N', [], [], [])` → 캔버스 빈칸. yfinance 20일 종가로 채운다.
- **MA200 계산**: `period="300d"` 필요. 최근 20개 slice 사용.

#### 코스피 마감 브리핑 3대 필수 확인 항목

마감 브리핑 생성·수정 시 아래 세 항목을 `data/latest_kospi_close.json`(또는 `data/v2/latest_kospi_close.json`)에서 반드시 확인한다. 값이 0이거나 비어 있으면 수정한다.

**① 시장 폭 (`market_breadth`)**

```json
{
  "market_breadth": {
    "up": 179,        ← 0이면 오류
    "down": 732,      ← 0이면 오류
    "unchanged": 12,
    "upper_limit": 4,
    "lower_limit": 0,
    "new_high": 0,
    "new_low": 0
  }
}
```

상승·하락이 모두 0이면 데이터 미수집. 네이버 금융 → KRX 시장 정보로 당일 값을 확인하고 HTML 수정.

**② 수급 현황 (`investor_trading`)**

```json
{
  "investor_trading": {
    "foreign": { "net": -2914300 },    ← 단위: 백만원 (억원 = net / 100)
    "institution": { "net": 2535000 },
    "individual": { "net": 377400 }
  }
}
```

`net`이 null이거나 3개 모두 0이면 오류. `supply_cells`에 반영된 억원 단위 값과 교차 검증.

**③ 거래대금 급증 + 수급 동반 종목 (`dpick`)**

```json
[{
  "name": "포스코DX", "code": "022100",
  "change_pct": 19.26,
  "trade_value_eok": 3191,   ← 억원
  "trade_mult": 8.6,          ← 20일 평균 대비 배수
  "frgn_eok": 204,
  "inst_eok": 93
}]
```

`dpick` 키 자체가 없거나 빈 배열이면 `fetch_closing_kospi.py`의 `fetch_dpick()`로 재수집하거나, 네이버 금융 거래량 상위에서 수동 확인 후 HTML에 직접 추가.

**dpick 빈 배열 = 정상 동작일 수 있다.** `fetch_dpick()`는 네이버 `item/frgn` 페이지의 최신 행 날짜가 오늘 KST가 아니면 해당 종목을 자동 스킵한다. 16:30 실행 기준에도 네이버 업데이트가 늦으면 `dpick`이 비어 있고, HTML에서 섹션이 사라진다. 이는 어제 데이터를 표시하지 않기 위한 의도적 동작이다.

#### 데이터 확인 순서 (마감 브리핑 수동 패치 시)

```
1. data/latest_kospi_close.json 열어서 위 3개 필드 확인
2. 0 또는 누락 → python3 scripts/fetch_closing_kospi.py 재실행 (16:30 이후)
3. dpick 빈 배열 → 네이버 업데이트 전(16:20 이전)일 수 있음. 16:30 이후 재실행.
4. 여전히 누락 → 네이버 금융 / KRX 웹에서 수동 확인
5. HTML 직접 수정 → 커밋
6. python3 scripts/generate_html.py --write-list-only 실행
```

### 2. generate_html.py 사용 시 기존 수정 덮어쓰기 주의

`generate_html.py --type kospi ...` 를 실행하면 해당 날짜 브리핑 HTML이 **완전히 재생성**된다.
수동으로 가격·sparkline을 수정한 HTML이 있다면 반드시 확인 후 실행할 것.

**브리핑 목록 JSON만 갱신할 때**는 `--write-list-only` 플래그를 사용한다:
```bash
python3 scripts/generate_html.py --write-list-only
```

### 3. 에셋 경로 — /v2/ 경로는 완전 삭제됨

모든 CSS·JS·favicon은 `/assets/` 경로를 사용한다. `/v2/assets/`는 삭제됨.

| 올바른 경로 | 잘못된 경로 (사용 금지) |
|------------|------------------------|
| `/assets/style.css` | `/v2/assets/style.css` |
| `/assets/main.js` | `/v2/assets/main.js` |
| `/favicon.svg` | `/v2/favicon.svg` |
| `/briefings/` | `/v2/briefings/` |

생성된 HTML에서 `/v2/` 경로가 발견되면 즉시 수정한다.

### 4. 브리핑 목록 동적 재구성 메커니즘

브리핑 목록(`.bottom-list`)은 HTML 생성 시점에 "오늘" 날짜가 정적으로 박힌다.
페이지마다 생성 시점이 다르면 목록이 불일치하므로, **JS가 목록 전체를 다시 그린다.**

`web/assets/main.js`의 `patchBriefingList()`가 페이지 로드 시 동작한다:
- `/data/briefings-list.json`(단일 진실원)을 fetch.
- **현재 KST 날짜**를 오늘 카드로 잡는다 (DOM에 박힌 날짜를 쓰지 않는다 — 이게 불일치의 원인이었다).
- 오늘 카드 + 과거 행(최근 10일, ready 1개 이상) 전체를 JSON에서 재구성한다.
- 현재 보고 있는 브리핑(`location.pathname` 파싱)만 `is-current`로 강조하고, 나머지는 링크.
- 결과: **어느 브리핑을 선택하든 목록은 동일·최신 상태**를 유지한다.

`generate_html.py` 실행 시 `write_briefings_list_json()`이 자동으로 JSON을 갱신한다.
- **수동으로 JSON만 갱신**할 때: `python3 scripts/generate_html.py --write-list-only`
- 정적 템플릿(`briefing_list.html`)은 JS 비활성 시 폴백으로만 쓰인다.

#### 주말(토·일) 슬롯 처리

`_blIsWeekend(dateStr)` 헬퍼로 요일을 판단한다. 토·일은 코스피·미국 휴장이므로 오늘 카드의 모든 슬롯을 `state: 'empty'`(`—`)로 표시한다. "생성 예정" 문구를 절대 표시하지 않는다.

#### `/briefings` 진입 시 최신 브리핑 자동 이동

`web/briefings/index.html`이 `briefings-list.json`을 fetch해 가장 최근 `ready` 슬롯 URL로 `location.replace()` 한다. 날짜 내 우선순위: `us > close > kospi`. **`vercel.json`에 날짜를 하드코딩하지 않는다** — 브리핑이 생성될 때마다 자동으로 최신을 가리킨다.

### 5. 마감 브리핑 시장 폭 데이터 필드

`latest_kospi_close.json`의 `market_breadth` 필드에서 읽는다:

```json
{
  "market_breadth": {
    "up": 179,        → 상승 종목 수
    "down": 732,      → 하락 종목 수
    "unchanged": 12,  → 보합 종목 수
    "upper_limit": 4, → 상한가
    "lower_limit": 0, → 하한가
    "new_high": 0,    → 52주 신고가
    "new_low": 0      → 52주 신저가
  }
}
```

### 6. 랜딩 페이지 CSS 변수 의존성

`landing.html`은 `--gnb-height` 변수를 사용한다.
`assets/style.css`에서는 `--gnb-h`(52px)로 정의되어 있으므로 landing.html `:root`에 반드시 매핑이 있어야 한다:

```css
:root {
  --gnb-height: var(--gnb-h, 52px);
}
```

이 변수가 없으면 `.stage-canvas` 높이가 0이 되어 랜딩 페이지 전체가 빈 화면이 된다.

### 7. 예측 섹션 — 항상 열린 상태 유지

`applyTimeCollapse()` 함수에서 KST 9시 이후 자동으로 예측 섹션을 접는 로직을 제거했다.
예측 섹션은 **항상 열린 상태**를 유지해야 한다. 다시 자동 접힘 로직을 추가하지 말 것.

### 8. AI 반도체 위젯 (칩보드)

`web/assets/main.js`의 `loadChipWidget()`이 `/chips/api/prices`를 fetch한다.
API 응답이 없으면 폴백(삼성전자·SK하이닉스·Micron·AMD·Intel)을 표시한다.
이 함수는 `window.addEventListener('load', ...)` 안에서 반드시 호출되어야 한다.

### 9. 텔레그램 발송 금지 조건

작업 완료 알림, 수동 테스트, 개발 중 임시 실행 시 텔레그램을 발송하지 않는다.
구독자 채널이므로 스케줄된 브리핑 외 ad-hoc 발송은 노이즈가 된다.

### 10. 예측 결과 위젯 — 대표/서브 타이틀 구조

`web/assets/main.js`의 장 마감 후 예측 결과 표시 규칙 (`isAfterMarket()` 블록 내):

- **대표 타이틀** (`lsb-head-em`): 예측 결과 요약문. "오늘 장이 종료됐어요." 고정 문구 사용 금지.
- **서브 타이틀** (`lsb-sub`): 등락률 한 줄. `nn% 하락 마감이에요.` 형식.
- **hit.dn (하락 예측 적중)**: 대표 타이틀 뒤에 아쉬움 표현을 반드시 붙인다. 예: "하락 예측이 맞았어요. 아쉬운 하루였어요."
- **hit.up (상승 예측 적중)**: 아쉬움 표현 없이 "상승 예측이 맞았어요."로만.
- CLOSE_MSGS 구조는 각 케이스마다 `title` 배열과 `sub` 배열을 분리 관리한다.

### 11. 라이브 스코어보드 — 구조와 운영 규칙

라이브 스코어보드는 `web/assets/main.js`의 `initLiveScoreboard()` 함수가 담당한다.
**당일 브리핑과 과거 브리핑 모두** 스코어보드를 표시한다. 상태에 따라 렌더링이 달라진다.

#### 상태별 동작

| 상태 | 조건 | 동작 |
|------|------|------|
| 장 전 (준비 중) | 당일 08:50~08:59 | 카운트다운 표시 |
| 장 중 (LIVE) | 당일 09:00~15:30 | `/api/kospi-live` 10초 폴링 |
| 장 후 (당일) | 당일 15:30 이후 | 최종 종가 fetch 후 예측 결과 표시 |
| **과거 브리핑** | URL 날짜 < 오늘 | **정적 결과 표시 (폴링 없음)** |
| 숨김 | 장 시작 전(~08:49) | `display:none` |

#### 과거 브리핑 스코어보드 규칙

과거 코스피 브리핑 페이지에서 스코어보드가 **항상 표시**된다. 예측 적중 여부, 그날 이슈, 시장 지표를 확인하는 용도다.

- **결과 표시**: `data-actual-pct` 속성이 있으면 예측 적중/빗나감 메시지 + 등락률 + 게이지 바늘 렌더링.
- **결과 미집계**: `data-actual-pct`가 비어 있으면 "결과 집계 중…" 표시. 다음 날 09:10 `check_accuracy.py` 실행 후 자동 주입.
- **뉴스 이슈**: `fetchNews()`가 `/data/kospi-news-{date}.json` (날짜별 아카이브)를 fetch. 아카이브가 없으면 빈 상태.
- **시장 지표 패널**: `initLiveMarketPanel()`이 `/data/market-{date}.json`을 fetch해 정적 표시. 스파크라인 없이 종가·수급만 표시.

#### 데이터 아카이브 파이프라인

```
fetch_news_live.py (30분마다 실행)
  → web/data/kospi-news-live.json  (당일 갱신)
  → web/data/kospi-news-{date}.json  (날짜별 아카이브 ← 과거 브리핑용)

check_accuracy.py (다음 날 09:10 실행)
  → data/briefings.json 에 actual_change_pct 기록
  → web/briefings/{date}/kospi/index.html 의 data-actual-pct 속성 주입
  → web/data/market-{date}.json 생성 (코스피·코스닥·코스피200·수급)
```

#### 구성 요소 (당일 장 중)

시장 지표 패널은 `initLiveMarketPanel()`이 담당하며, 스코어보드와 독립적으로 동작한다.

| 영역 | 데이터 소스 | 갱신 주기 |
|------|------------|----------|
| 코스피 지수 · 등락률 | `/api/kospi-live` | 10초 |
| 코스피200 · 코스닥 · 원/달러 | `/api/market` | 60초 |
| 수급 (외국인·기관·개인) | `/api/market` | 60초 |
| 장중 뉴스 이슈 | `/data/kospi-news-live.json` | 5분 |
| 스파크라인 그래프 | 인메모리 누적 + sessionStorage 복원 | 폴링 시 자동 |

`/api/market`은 코스피200·코스닥·원달러·수급을 한 번에 반환하는 Vercel API 엔드포인트다. 60초마다 자동 갱신되며, 장 중 실시간 데이터를 표시한다.

#### 뉴스 워크플로우

- **스케줄**: 평일 09:10~15:00 KST, 30분 간격 (총 13회)
- **워크플로우**: `.github/workflows/kospi-news-live.yml` (GHA native schedule)
- **Vercel cron 사용 금지**: Hobby 플랜은 cron 2개 제한이므로 `vercel.json` `crons` 배열은 비워 둔다.
- JSON 구조: `{ date, updated_at, latest: { market, stock }, history: [...] }`
- `history`는 최대 6개 보관 (같은 날짜인 경우에만 이어받음)

#### 스파크라인 규칙

- 색상: 상승=빨강(`#E03131`), 하락=파랑(`#2775ED`) — 첫 값 대비 현재값으로 자동 결정
- 시작가 기준 점선을 그려 흐름 맥락을 제공한다
- 데이터는 `sessionStorage('mkt-spark-v1')`에 저장 — 새로고침 후에도 즉시 복원
- 폴링 데이터를 슬라이딩 윈도우(최대 30개)로 누적

#### 수급 표시 순서

개인 → 기관 → 외국인 (변경 금지. 한국 투자자 관점 기준)

#### 수정 시 주의사항

- `isDuringMarket()` / `isPreOpen()` / `isAfterMarket()` 판단 함수가 겹쳐 있다. 상태 로직 변경 시 세 함수 모두 확인.
- `isPast` 플래그는 `initLiveScoreboard()` 내부 클로저 변수다. `initLiveMarketPanel()`은 별도로 `mktIsPast`를 계산한다.
- 스코어보드 HTML은 `buildPanel()`이 동적으로 생성한다. 인라인 HTML에서 ID를 찾으려 하면 찾을 수 없다.
- `applyTimeCollapse()` 자동 접힘 로직은 제거됨 — 다시 추가하지 말 것.

### 12. 커밋 단위

- 한 논리적 변경 = 한 커밋. 여러 파일을 고쳤더라도 같은 목적이면 하나로 묶는다.
- HTML 수동 패치(가격 보정, sparkline 추가 등)는 커밋 메시지에 종목명·수정 내용을 명시한다.
- 브리핑 자동 생성 커밋(`📊 코스피 브리핑: ...`)과 수동 수정 커밋은 구분한다.
