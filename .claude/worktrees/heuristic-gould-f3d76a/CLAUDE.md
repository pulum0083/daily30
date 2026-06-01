# Double-Shot — AI 투자 브리핑 서비스

## 프로젝트 개요

매일 아침 코스피·저녁 미국 시장 AI 예측 브리핑을 자동 생성해 텔레그램·이메일로 발송하는 서비스.
Gemini(뉴스 요약) + Claude(분석·예측) 하이브리드 파이프라인으로 구동된다.

## 서비스 URL

| 구분 | URL |
|------|-----|
| 랜딩페이지 | **https://doubleshot.space** |
| 브리핑 목록 | **https://doubleshot.space/briefings** |
| 최신 브리핑 | **https://doubleshot.space/briefings/{YYYY-MM-DD}/** |

호스팅: Vercel (정적 서빙 + Cron 트리거) + GitHub Pages (`gh-pages` 브랜치, Vercel 배포 시 병행)

## 브리핑 스케줄

| 브리핑 | 실행 시각 (KST) | 요일 |
|--------|----------------|------|
| 코스피 시초가 | 08:30 | 평일 (월~금) |
| 미국 시장 | 21:20 | 평일 (월~금) |
| 공포탐욕 패치 | 09:05 | 평일 (화~토) |
| 예측 정확도 체크 | 09:10 | 평일 (화~토) |

## 실행 흐름

```
Vercel Cron → /api/trigger?type=kospi
  → GitHub Actions workflow_dispatch
    → 휴장일 확인 (holiday_check.py)
    → 시장 데이터 수집 (fetch_data.py)
    → 뉴스 요약 (fetch_news.py — Gemini 2.5 Flash Lite)
    → AI 분석·예측 (call_claude.py — Claude Sonnet 4.6, Prompt Caching)
    → latest.json 갱신 (update_latest.py)
    → 텔레그램 전송 (send_telegram.py)
    → 이메일 전송 (send_email.py → Resend API)
    → HTML 생성 & main 커밋·푸시 (generate_html.py)
    → GitHub Pages 배포 (gh-pages 브랜치)
```

## 디렉토리 구조

```
daily30/
├── CLAUDE.md
├── vercel.json                   # Vercel 라우팅 + Cron 스케줄 설정
├── api/
│   ├── trigger.mjs               # Vercel Cron → GitHub Actions dispatch
│   └── subscribe.mjs             # 이메일 구독 신청 API (최신 브리핑 즉시 발송)
├── scripts/
│   ├── call_claude.py            # Claude Sonnet 4.6 + Prompt Caching 분석 생성
│   ├── fetch_data.py             # yfinance 기반 시장 데이터 수집
│   ├── fetch_news.py             # Gemini 2.5 Flash Lite 뉴스 요약
│   ├── generate_html.py          # templates/ 기반 HTML 브리핑 생성
│   ├── send_telegram.py          # 텔레그램 전송
│   ├── send_email.py             # Resend API 이메일 전송 (pulum0083@gmail.com)
│   ├── update_latest.py          # web/data/latest.json 갱신 (구독 API용)
│   ├── holiday_check.py          # 한국/미국 공휴일 확인
│   ├── patch_fg.py               # Fear & Greed 지수 HTML 패치 (09:05 KST)
│   ├── check_accuracy.py         # 전일 예측 정확도 체크
│   └── templates/
│       ├── briefing.html         # 브리핑 페이지 템플릿
│       └── index.html            # 날짜별 index 템플릿
├── web/
│   ├── landing.html              # 랜딩페이지 (/ 라우팅)
│   ├── favicon.svg               # GNB 로고 마크 기반 SVG 파비콘
│   ├── briefings/
│   │   ├── index.html            # 브리핑 목록 (/briefings)
│   │   ├── YYYY-MM-DD-kospi.html # 코스피 브리핑 flat 파일
│   │   ├── YYYY-MM-DD-us.html    # 미국 브리핑 flat 파일
│   │   └── YYYY-MM-DD/           # URL용 디렉토리 (/briefings/YYYY-MM-DD/)
│   │       └── index.html
│   ├── data/
│   │   └── latest.json           # 최신 브리핑 요약 (구독 API가 읽음)
│   └── assets/
│       ├── style.css
│       ├── main.js
│       ├── briefing-list.js
│       └── og-image.svg          # OG 썸네일 (브리핑 대시보드 스타일)
├── data/
│   ├── briefings.json            # 예측·정확도 누적 데이터
│   ├── latest_kospi.json         # 최신 코스피 시장 데이터 (gitignore)
│   ├── latest_us.json            # 최신 미국 시장 데이터 (gitignore)
│   ├── analysis_kospi.json       # Claude 분석 결과 (gitignore)
│   ├── analysis_us.json          # Claude 분석 결과 (gitignore)
│   ├── news_summary_kospi.json   # Gemini 뉴스 요약 (커밋됨)
│   └── news_summary_us.json      # Gemini 뉴스 요약 (커밋됨)
├── .github/workflows/
│   └── daily_report.yml          # kospi / us / fg-patch / accuracy 4개 job
└── config.json                   # API 키 (gitignore — config.example.json 참조)
```

## AI 파이프라인

### 뉴스 수집 — Gemini 2.5 Flash Lite (`fetch_news.py`)
- 구글 검색 기반 뉴스 크롤링 후 요약
- `data/news_summary_{type}.json` 저장

### 분석·예측 — Claude Sonnet 4.6 (`call_claude.py`)
- **Prompt Caching** 적용 (시스템 프롬프트 캐시, ~5분 TTL, 재실행 시 90% 비용 절감)
- 출력: JSON only (`analysis_{type}.json`) → HTML 생성은 `generate_html.py`가 담당
- 생성 항목: `prediction` (direction / up_pct / confidence), `reasons`, `reason_title`, `stock_picks`

## API 키 / 환경변수

| 변수 | 용도 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude Sonnet 4.6 |
| `GEMINI_API_KEY` | Gemini 2.5 Flash Lite |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 |
| `TELEGRAM_CHAT_ID` | 텔레그램 채널 |
| `RESEND_API_KEY` | 이메일 발송 (Resend) |
| `GH_PAT` | Vercel → GitHub Actions dispatch |

GitHub Actions Secrets에 모두 등록되어 있음. Vercel 환경변수에도 `RESEND_API_KEY`, `GH_PAT` 등록 필요.

## 이메일 발송

- **브리핑 자동 발송**: `send_email.py` → `pulum0083@gmail.com` (매 브리핑 후 자동)
- **구독 웰컴 발송**: `api/subscribe.mjs` → 구독 신청 시 최신 브리핑 즉시 발송
- 발신 주소: `noreply@doubleshot.space` (Resend 도메인 인증 완료)
- 관리자 알림: 새 구독자 발생 시 `pulum0083@gmail.com`으로 알림

## 주요 규칙

1. **휴장일 스킵**: `holiday_check.py --market kospi|us` 확인 후 해당일엔 전체 파이프라인 중단
2. **데이터 최신성**: 항상 당일 KST 기준. yfinance 실패 시 웹 검색으로 대체
3. **URL 구조**: 브리핑 URL = `/briefings/{YYYY-MM-DD}/` (type prefix 없음)
4. **latest.json**: 브리핑 생성 직후 `update_latest.py`로 반드시 갱신 (구독 API가 이 파일 기준으로 발송)
5. **텔레그램**: 핵심 시그널 150자 이내 해요 체, 브리핑 URL 포함
6. **오류 처리**: 텔레그램·이메일 스텝은 `continue-on-error: true` (실패해도 HTML 커밋은 진행)
7. **push 충돌 방지**: 커밋 후 `git pull --rebase && git push` 패턴 사용
8. **브랜치 전략**: 소규모 수정(스크립트 1~2개, 버그 픽스)은 main 직접 push. 대규모 변경(템플릿 전면 교체, 파이프라인 구조 변경 등)은 feature 브랜치 → PR → merge

## Vercel 라우팅

```
/                        → landing.html
/briefings/              → briefings/index.html
/briefings/{date}/       → briefings/{date}/index.html  (filesystem)
/briefings/ko/{date}/    → briefings/{date}-kospi.html  (레거시 호환)
/briefings/us/{date}/    → briefings/{date}-us.html     (레거시 호환)
```

## GitHub Actions Workflow (`daily_report.yml`)

4개 job, 모두 `workflow_dispatch` 트리거 (Vercel Cron이 `/api/trigger`로 dispatch):

| job | 트리거 type | 주요 스텝 |
|-----|------------|-----------|
| `kospi-briefing` | `kospi` | fetch_data → fetch_news → call_claude → **update_latest** → telegram → email → commit → pages |
| `us-briefing` | `us` | 동일 구조 |
| `fg-patch` | `fg-patch` | patch_fg → commit (pull --rebase) → pages |
| `kospi-accuracy` | `accuracy` | check_accuracy → commit |
