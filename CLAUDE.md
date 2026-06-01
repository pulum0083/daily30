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
| 코스피 마감 | 16:00 | 평일 (월~금) |
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

### 분석·예측 — Claude Sonnet 4.6 (`call_claude.py`)
- **Prompt Caching** 적용 (시스템 프롬프트 캐시, ~5분 TTL, 재실행 시 90% 비용 절감)
- 출력: JSON only (`analysis_{type}.json`) → HTML 생성은 `generate_html.py`가 담당
- 생성 항목: `prediction` (direction / up_pct / confidence), `reasons`, `reason_title`, `stock_picks`

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

GitHub Actions Secrets에 모두 등록되어 있음.

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

### 1. 브리핑 데이터 검증 — 의심 없이 확인, 틀리면 수정 후 커밋

> **LLM이 생성한 가격·수치는 틀릴 수 있다. 브리핑에 나오는 모든 수치는 실제 시장 데이터로 검증하고 반영한다.**

#### 종목 가격·등락률 (코스피·미국 예측 브리핑)

`analysis_*.json`의 종목 가격·등락률은 **LLM 할루시네이션** 가능성이 있다.
HTML 반영 전 반드시 yfinance 또는 네이버 금융으로 실제 값을 확인하고 덮어쓴다.

```python
import yfinance as yf

# 국내 종목: "{종목코드}.KS" 형식, 5d로 최근 종가 확인
hist = yf.Ticker("005380.KS").history(period="5d").dropna(subset=["Close"])
last_close = int(hist["Close"].iloc[-1])

# 미국 종목: 티커 직접 사용
hist = yf.Ticker("BAC").history(period="5d").dropna(subset=["Close"])
```

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

#### 데이터 확인 순서 (마감 브리핑 수동 패치 시)

```
1. data/latest_kospi_close.json 열어서 위 3개 필드 확인
2. 0 또는 누락 → python3 scripts/fetch_closing_kospi.py 재실행 (장 종료 후)
3. 여전히 누락 → 네이버 금융 / KRX 웹에서 수동 확인
4. HTML 직접 수정 → 커밋
5. python3 scripts/generate_html.py --write-list-only 실행
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

### 10. 커밋 단위

- 한 논리적 변경 = 한 커밋. 여러 파일을 고쳤더라도 같은 목적이면 하나로 묶는다.
- HTML 수동 패치(가격 보정, sparkline 추가 등)는 커밋 메시지에 종목명·수정 내용을 명시한다.
- 브리핑 자동 생성 커밋(`📊 코스피 브리핑: ...`)과 수동 수정 커밋은 구분한다.
