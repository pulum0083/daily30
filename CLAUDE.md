# Double-Shot — AI 투자 브리핑 서비스

매일 아침 코스피·저녁 미국 시장 AI 예측 브리핑을 자동 생성해 텔레그램으로 발송하는 서비스.
Gemini(뉴스 요약) + Claude(분석·예측) 하이브리드 파이프라인으로 구동된다.

호스팅: Vercel (정적 서빙 + API) + GitHub Pages (`gh-pages` 브랜치), 스케줄링: Cloudflare (Cron Triggers)

## 서비스 URL

| 구분      | URL |
| ------- | --- |
| 랜딩페이지   | https://doubleshot.space |
| 브리핑 목록  | https://doubleshot.space/briefings |
| 코스피 브리핑 | https://doubleshot.space/briefings/{YYYY-MM-DD}/kospi/ |
| 마감 브리핑  | https://doubleshot.space/briefings/{YYYY-MM-DD}/close/ |
| 미국 브리핑  | https://doubleshot.space/briefings/{YYYY-MM-DD}/us/ |

## 브리핑 스케줄

| 브리핑       | 실행 시각 (KST) | 요일       |
| --------- | ----------- | -------- |
| 코스피 시초가   | 07:25       | 평일 (월~금) |
| 코스피 마감    | 16:25       | 평일 (월~금) |
| 미국 시장     | 21:15       | 평일 (월~금) |
| 예측 정확도 체크 | 09:10       | 평일 (화~토) |

## 실행 흐름

```
Cloudflare (Cron Triggers) → /api/trigger?type=kospi
  → GitHub Actions workflow_dispatch
    → 휴장일 확인 (holiday_check.py)
    → 시장 데이터 수집 (fetch_data.py / fetch_closing_kospi.py)
    → 월봉 5개월선 안착 종목 스크리닝 (monthly_ma5.py — 코스피 아침만)
    → 뉴스 요약 (fetch_news.py — Gemini 2.5 Flash Lite)
    → AI 분석·예측 (call_claude.py — Claude Sonnet 5, Prompt Caching)
    → 텔레그램 전송 (send_telegram.py)
    → HTML 생성 & main 커밋·푸시 (generate_html.py)
      → web/data/briefings-list.json 자동 갱신 (write_briefings_list_json)
    → GitHub Pages 배포 (gh-pages 브랜치)
```

## 디렉토리 구조

```
double-shot/
├── CLAUDE.md
├── SERVICE_RULES.md             # 운영 규칙 (AI 파이프라인, 데이터 검증, UI 규칙 등)
├── vercel.json                  # Vercel 라우팅 + Cron 스케줄 설정
├── api/
│   └── trigger.mjs              # Vercel Cron → GitHub Actions dispatch
├── scripts/
│   ├── call_claude.py           # Claude Sonnet 5 + Prompt Caching 분석 생성
│   ├── fetch_data.py            # yfinance 기반 코스피·미국 시장 데이터 수집
│   ├── fetch_closing_kospi.py   # 코스피 마감 데이터 수집 (수급·장중·시장폭·dpick)
│   ├── fetch_news.py            # Gemini 2.5 Flash Lite 뉴스 요약
│   ├── fetch_news_live.py       # 이슈 브리핑 수집 (시간대별 슬롯 분기, 22회/일)
│   ├── generate_html.py         # config-driven HTML 브리핑 조립기
│   ├── send_telegram.py         # 텔레그램 전송
│   ├── holiday_check.py         # 한국/미국 공휴일 확인
│   ├── patch_fg.py              # Fear & Greed 지수 HTML 패치 (09:05 KST)
│   ├── check_accuracy.py        # 전일 예측 정확도 체크
│   ├── monthly_ma5.py           # 월봉 5개월선 안착 종목 스크리닝 (코스피 아침 코너)
│   ├── backtest_monthly_ma5.py  # 위 조건 백테스트 → config/monthly_ma5_backtest.json
│   ├── validate_analysis.py     # 분석 결과 검증 게이트 (픽 실측 주입 + 교정)
│   ├── toss_client.py           # 토스증권 Open API 클라이언트
│   ├── config/
│   │   ├── kospi.json           # 코스피 브리핑 섹션 선언
│   │   ├── close.json           # 마감 브리핑 섹션 선언
│   │   └── us.json              # 미국 브리핑 섹션 선언
│   └── templates/
│       ├── base.html            # 공통 레이아웃 (GNB, CSS/JS 경로)
│       ├── briefings/
│       │   ├── kospi.html       # 코스피 예측 브리핑 템플릿
│       │   ├── close.html       # 코스피 마감 브리핑 템플릿
│       │   └── us.html          # 미국 시장 브리핑 템플릿
│       ├── pages/
│       │   └── briefings_index.html
│       └── sections/
│           └── _issue_briefing.html
├── web/
│   ├── landing.html             # 랜딩페이지
│   ├── briefings/
│   │   ├── index.html           # 브리핑 목록 (/briefings)
│   │   └── YYYY-MM-DD/{kospi,close,us}/index.html
│   ├── data/
│   │   └── briefings-list.json  # 날짜별 슬롯 상태 (브리핑 목록 동적 패치용)
│   └── assets/
│       ├── style.css
│       ├── main.js
│       └── briefing-list.js
├── data/
│   ├── briefings.json           # 예측·정확도 누적 데이터 (커밋됨)
│   └── supply_history.json      # 외국인·기관·개인 7일 수급 히스토리 (커밋됨)
├── .github/workflows/
│   └── daily_report.yml         # kospi / us / kospi-close / accuracy 4개 job
└── config.json                  # API 키 (gitignore)
```

@docs/SERVICE_RULES.md
