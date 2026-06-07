# Double-Shot — AI 투자 브리핑 서비스

매일 아침 코스피·저녁 미국 시장 AI 예측 브리핑을 자동 생성해 텔레그램·이메일로 발송하는 서비스.
Gemini(뉴스 요약) + Claude(분석·예측) 하이브리드 파이프라인으로 구동된다.

호스팅: Vercel (정적 서빙 + Cron 트리거) + GitHub Pages (`gh-pages` 브랜치)

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
| 코스피 시초가   | 07:30       | 평일 (월~금) |
| 코스피 마감    | 16:30       | 평일 (월~금) |
| 미국 시장     | 21:20       | 평일 (월~금) |
| 예측 정확도 체크 | 09:10       | 평일 (화~토) |

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
double-shot/
├── CLAUDE.md
├── SERVICE_RULES.md             # 운영 규칙 (AI 파이프라인, 데이터 검증, UI 규칙 등)
├── vercel.json                  # Vercel 라우팅 + Cron 스케줄 설정
├── api/
│   ├── trigger.mjs              # Vercel Cron → GitHub Actions dispatch
│   └── subscribe.mjs            # 이메일 구독 신청 API (최신 브리핑 즉시 발송)
├── scripts/
│   ├── call_claude.py           # Claude Sonnet 4.6 + Prompt Caching 분석 생성
│   ├── fetch_data.py            # yfinance 기반 코스피·미국 시장 데이터 수집
│   ├── fetch_closing_kospi.py   # 코스피 마감 데이터 수집 (수급·장중·시장폭·dpick)
│   ├── fetch_news.py            # Gemini 2.5 Flash Lite 뉴스 요약
│   ├── fetch_news_live.py       # 이슈 브리핑 수집 (시간대별 슬롯 분기, 22회/일)
│   ├── generate_html.py         # config-driven HTML 브리핑 조립기
│   ├── send_telegram.py         # 텔레그램 전송
│   ├── send_email.py            # Resend API 이메일 전송
│   ├── update_latest.py         # web/data/latest.json 갱신 (구독 API용)
│   ├── holiday_check.py         # 한국/미국 공휴일 확인
│   ├── patch_fg.py              # Fear & Greed 지수 HTML 패치 (09:05 KST)
│   ├── check_accuracy.py        # 전일 예측 정확도 체크
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
│   │   ├── latest.json          # 최신 브리핑 요약 (구독 API용)
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
