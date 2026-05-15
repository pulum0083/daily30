**최초 작성:** 2026년 4월 13일
**최종 업데이트:** 2026년 5월 15일

**프로젝트명:** Double-Shot — AI 기반 투자 브리핑 자동화 서비스

**서비스 URL:** https://doubleshot.space

**문서 목적:** 전체 시스템 설계·구현 과정 및 현황 정리

---

## 1. 프로젝트 개요

### 해결하려는 문제

매일 아침 시장이 열리기 전, 투자자는 전일 미국 시장 흐름·지표·뉴스를 종합해 오늘 코스피 방향을 스스로 판단해야 한다. 이 작업은 반복적이고 시간이 걸리며, 감정적 판단이 개입되기 쉽다.

### 솔루션 한 줄 정의

> **"매일 아침·저녁, AI가 시장 데이터를 수집·분석해 코스피·미국 시장 방향 예측과 추천 종목을 텔레그램·이메일로 전송하고, 웹에 아카이빙한다."**

---

## 2. 서비스 구조 한눈에 보기

```
[스케줄 트리거]
    cron-job.org → Vercel /api/trigger
         → GitHub Actions workflow_dispatch
              │
              ▼
[데이터 수집]
    yfinance (S&P500, NASDAQ, SOX, EWY, VIX, DXY, 환율, 유가, DRAM ETF 등)
    + 네이버 증권 (투자자 순매수, 코스피 마감 시세, 급등주, 섹터)
    + ForexFactory (경제 지표 캘린더)
         │
         ▼
[뉴스 요약]
    Gemini 2.5 Flash Lite (구글 검색 기반 크롤링 → 요약)
         │
         ▼
[AI 분석 엔진]
    Claude Sonnet 4.6 (Prompt Caching)
    → 방향 예측 (상승/하락/중립, 확률, 신뢰도)
    → 예측 근거 bullet (5개+)
    → 잭 켈로그 20일선 전략 종목 (3~5개)
    → JSON 출력 only
         │
    ┌────┴────────────────┐
    ▼                     ▼
[HTML 생성]          [알림 전송]
 generate_html.py     ├ 텔레그램 (send_telegram.py)
    │                 └ 이메일 (send_email.py → Resend API)
    ▼
[배포]
 GitHub Push → GitHub Pages (gh-pages 브랜치)
             + Vercel (정적 서빙 + API 라우팅)
```

---

## 3. 자동화 스케줄

| **브리핑** | **실행 시각 (KST)** | **실행 조건** | **주요 내용** |
|---|---|---|---|
| **코스피 시초가** | 월~금 08:30 | 한국 시장 개장일 | 전일 미국 마감 기반 코스피 시초가 방향 예측 |
| **코스피 마감** | 월~금 15:40 | 한국 시장 개장일 | 장중 흐름·섹터 성과·급등주 분석 |
| **미국 시장** | 월~금 21:20 | 미국 시장 개장일 | 프리마켓 기반 당일 미국 시장 방향 예측 |
| **공포탐욕 패치** | 화~토 09:05 | 평일 | Fear & Greed 지수 HTML 패치 |
| **예측 정확도** | 화~토 09:10 | 평일 | 전일 예측 vs 실제 결과 자동 기록 |

> **트리거 경로:** cron-job.org → Vercel `/api/trigger?type={type}` → GitHub Actions `workflow_dispatch`
>
> **휴장일 처리:** `holiday_check.py --market kospi|us`로 자동 감지. 감지 실패 시 하드코딩된 2025~2026년 공휴일 목록으로 폴백.

---

## 4. 기술 스택 및 선택 이유

### 4-1. 실행 환경: GitHub Actions + cron-job.org

| **항목** | **내용** |
|---|---|
| **선택 이유** | 별도 서버 없이 무료로 크론 스케줄 실행 가능 |
| **트리거** | cron-job.org → Vercel API → GitHub Actions dispatch (Vercel Cron 대비 정확도 향상) |
| **한계** | 무료 플랜 2,000분/월 (브리핑 1회 약 2분 → 월 80회, 충분) |

### 4-2. AI 엔진: Gemini + Claude 하이브리드 파이프라인

| **단계** | **모델** | **역할** |
|---|---|---|
| 뉴스 수집·요약 | Gemini 2.5 Flash Lite | 구글 검색 기반 크롤링 → 요약 (저비용) |
| 분석·예측 | Claude Sonnet 4.6 | 시장 데이터 + 뉴스 종합 분석, JSON 출력 |

- **Prompt Caching** 적용 (시스템 프롬프트 캐시, ~5분 TTL, 재실행 시 90% 비용 절감)
- Claude는 JSON only 출력 → HTML 생성은 `generate_html.py`(Jinja2 템플릿)가 담당

### 4-3. 웹 서비스: Vercel + GitHub Pages 이중 배포

| **서비스** | **역할** |
|---|---|
| Vercel | 도메인 라우팅, 서버리스 API (`/api/trigger`, `/api/subscribe`) |
| GitHub Pages | `gh-pages` 브랜치에서 정적 HTML 서빙 |

### 4-4. 알림: 텔레그램 + 이메일

| **채널** | **구현** | **특징** |
|---|---|---|
| 텔레그램 | `send_telegram.py` → Bot API 직접 호출 | 핵심 시그널 150자 이내 해요체 + 브리핑 URL |
| 이메일 | `send_email.py` → Resend API | 브리핑 자동 발송 + 구독 웰컴 발송 |

발신 주소: `noreply@doubleshot.space` (Resend 도메인 인증 완료)

---

## 5. 에이전트 설계 철학

### "Gemini가 기자, Claude가 애널리스트"

```
1. Gemini (기자)      → 구글 검색으로 뉴스 크롤링 + 요약
2. yfinance + 네이버  → 정량 시장 데이터 수집
3. Claude (애널리스트) → 데이터 + 뉴스 종합 분석, 방향 예측, 종목 선별
4. generate_html.py   → Jinja2 템플릿으로 HTML 렌더링
```

### 핵심 설계 원칙

| **원칙** | **구현 방식** |
|---|---|
| **실시간 데이터** | 학습 데이터 사용 금지, 반드시 API/크롤링으로 현재가 확인 |
| **장애 격리** | 텔레그램·이메일 스텝은 `continue-on-error: true` |
| **중복 방지** | `telegram_sent_log.json`으로 발송 이력 관리 |
| **글쓰기 규칙** | 의견 먼저·해요체, reason_title은 해요체 제외 |
| **push 충돌 방지** | `git pull --rebase && git push` 패턴 |

---

## 6. 웹 서비스 UI 설계

### 레이아웃 구조

```
┌─────────── GNB (네비게이션 바) ───────────┐
│  Double-Shot   날짜·시각  [코스피] [🌙]   │
└───────────────────────────────────────────┘
┌──────────────────────┬────────────────────┐
│                      │   시장 지표  - LIVE │
│  예측 카드           │                    │
│  ├ 방향 예측         │  [미국 시장]    ▼  │
│  ├ 상승/하락 확률    │  나스닥  17,697    │
│  └ 신뢰도            │  SOX     4,833 ⬆   │
│                      │  ···               │
│  예측 근거           │  [한국 시장]    ▼  │
│  ├ bullet ×5+        │  코스피  2,583     │
│  └ 리스크 요인       │  ···               │
│                      │  [변동성]       ▼  │
│  잭 켈로그 종목      │  WTI    $61.60     │
│  ├ 종목 1~5          │  공포탐욕: 35 공포 │
│  └ 실행 가이드       │  [반원 게이지]     │
│                      │                    │
│  과거 브리핑 아카이브│                    │
└──────────────────────┴────────────────────┘
```

### 코스피 마감 브리핑 레이아웃

```
┌──────────────────────┬────────────────────┐
│  마감 시황 요약      │   섹터 성과 (5개)  │
│  ├ 장중 흐름         │  ├ 상승 섹터       │
│  ├ 스파크라인 차트   │  └ 하락 섹터       │
│  └ 급등주 + 사유     │                    │
└──────────────────────┴────────────────────┘
```

### 반응형 대응

- **데스크톱(900px+):** 2컬럼 — 브리핑 본문 + 우측 패널 sticky
- **모바일(900px-):** 1컬럼 — 브리핑 본문 → 패널 (하단)

### 주요 UI 요소

| **요소** | **구현** |
|---|---|
| Sparkline 차트 | Canvas API, 최근 10개 데이터 포인트 면적 그래프 |
| 공포탐욕 게이지 | 반원 Canvas 게이지 + 전일/1주/1달/1년 이력 |
| 라이트/다크 모드 | GNB 토글, `localStorage` 지속 |
| OG 썸네일 | 동적 생성 SVG 기반 |
| 파비콘 | GNB 로고 마크 기반 SVG |
| Google Analytics | G-PW9RHHFPM4 |

---

## 7. 데이터 흐름 상세

```
GitHub Actions
    │
    ├─ python3 scripts/fetch_data.py --type kospi
    │      └─ yfinance + 네이버 증권 데이터 수집
    │         → data/latest_kospi.json
    │
    ├─ python3 scripts/fetch_news.py --type kospi
    │      └─ Gemini 2.5 Flash Lite 뉴스 요약
    │         → data/news_summary_kospi.json
    │
    ├─ python3 scripts/call_claude.py --type kospi
    │      └─ Claude Sonnet 4.6 (Prompt Caching)
    │         → data/analysis_kospi.json (JSON only)
    │
    ├─ python3 scripts/update_latest.py --type kospi
    │      └─ web/data/latest.json 갱신
    │
    ├─ python3 scripts/send_telegram.py --type kospi
    │      └─ Telegram Bot API 호출
    │
    ├─ python3 scripts/send_email.py --type kospi
    │      └─ Resend API 호출
    │
    ├─ python3 scripts/generate_html.py --type kospi
    │      └─ Jinja2 템플릿 렌더링
    │         → web/briefings/YYYY-MM-DD-kospi.html
    │         → web/briefings/YYYY-MM-DD/index.html
    │         → web/briefings/index.html (목록 갱신)
    │
    └─ git add → commit → pull --rebase → push
           └─ GitHub Pages 자동 배포 (gh-pages 브랜치)
```

---

## 8. 보안 설계

| **항목** | **처리 방식** |
|---|---|
| Anthropic API Key | GitHub Secrets → 환경변수 주입 |
| Gemini API Key | GitHub Secrets → 환경변수 주입 |
| Telegram Bot Token | GitHub Secrets → 환경변수 주입 |
| Telegram Chat ID | GitHub Secrets → 환경변수 주입 |
| Resend API Key | GitHub Secrets + Vercel 환경변수 |
| GH_PAT | Vercel → GitHub Actions dispatch용 |
| config.json (로컬 테스트용) | `.gitignore`로 버전관리 제외 |

---

## 9. URL 구조

| **경로** | **대상** |
|---|---|
| `/` | `landing.html` (랜딩페이지) |
| `/briefings/` | `briefings/index.html` (브리핑 목록) |
| `/briefings/{YYYY-MM-DD}/` | 날짜별 통합 index |
| `/briefings/ko/{date}/` | 코스피 브리핑 (레거시 호환) |
| `/briefings/us/{date}/` | 미국 브리핑 (레거시 호환) |
| `/briefings/ko-close/{date}/` | 코스피 마감 시황 |

---

## 10. 현재 시스템 상태

### 완료된 것 (4/13 이후 주요 변경 포함)

| **항목** | **상태** | **변경 시점** |
|---|---|---|
| GitHub Actions 5종 스케줄 (코스피/미국/마감/FG패치/정확도) | 정상 동작 | — |
| Gemini + Claude 하이브리드 AI 파이프라인 | 정상 동작 | 4월 중순 |
| Netlify → Vercel + GitHub Pages 이전 | 완료 | 4/15 |
| 도메인 doubleshot.space 적용 | 완료 | 4월 중순 |
| 이메일 발송 (Resend API) | 정상 동작 | 4월 중순 |
| Vercel Cron → cron-job.org 이전 | 완료 | 5/14 |
| 코스피 마감 브리핑 파이프라인 | 정상 동작 | 5월 초 |
| 마감 브리핑: 섹터 성과 패널 + 급등주 사유 | 구현 완료 | 5/13~14 |
| 예측 정확도 자동 트래킹 (`check_accuracy.py`) | 정상 동작 | 4/15 |
| Fear & Greed 지수 HTML 패치 | 정상 동작 | — |
| 텔레그램 중복 발송 방지 (`telegram_sent_log.json`) | 구현 완료 | 5/14 |
| Jinja2 기반 HTML 템플릿 분리 | 완료 | 4/17 |
| OG 썸네일·파비콘·Google Analytics | 완료 | 4~5월 |
| 의견 먼저·해요체 글쓰기 규칙 | 적용 완료 | 4~5월 |
| DRAM ETF 데이터 추가 | 완료 | 5월 초 |
| 네이버 증권 데이터 소스 전환 (투자자 순매수, 마감 시세) | 완료 | 5월 |
| dry_run 옵션 (테스트용 발송 건너뛰기) | 구현 완료 | 5월 |

### 알려진 제약

| **항목** | **내용** |
|---|---|
| 시장 지표 "실시간" | 브리핑 생성 시점 데이터 고정. 페이지 로드 후 업데이트 없음 |
| 종목 가격 정확도 | 네이버 + yfinance 기반 — 실시간 HTS 연동 아님 |
| GitHub Actions 딜레이 | 크론 실행 시각 ±수 분 지연 가능 (cron-job.org로 완화) |
| Anthropic 크레딧 | 소진 시 자동 실행 중단 (모니터링 필요) |
| 이메일 구독 | 공사 중 (임시 중단 상태) |

---

## 11. 향후 발전 방향 (제안)

| **우선순위** | **아이템** | **설명** | **상태** |
|---|---|---|---|
| ~~High~~ | ~~예측 정확도 트래킹~~ | ~~전날 예측 vs 실제 결과 자동 기록~~ | ✅ 완료 |
| High | **크레딧 자동 모니터링** | 잔액 임계값 이하 시 텔레그램 경고 알림 | 미착수 |
| High | **이메일 구독 정상화** | 공사 중 상태 해제 + 구독 플로우 완성 | 미착수 |
| Mid | **종목 가격 API 연동** | 한국투자증권 or KIS API로 실시간 종가 수집 | 미착수 |
| Mid | **주간 리포트 자동화** | 주간 요약 + 다음주 이벤트 캘린더 (프롬프트만 존재) | 미착수 |
| Low | **공포탐욕지수 API 직접 연동** | CNN Fear & Greed Index API 실시간 갱신 | 미착수 |
| Low | **다중 사용자 지원** | 텔레그램 그룹 구독 관리 | 미착수 |

---

## 12. 파일 구조 요약

```
daily30/
├── CLAUDE.md                          ← 프로젝트 컨텍스트 (AI 에이전트용)
├── vercel.json                        ← Vercel 라우팅 + 정적 서빙 설정
├── api/
│   ├── trigger.mjs                    ← cron-job.org → GitHub Actions dispatch
│   └── subscribe.mjs                  ← 이메일 구독 신청 API
├── scripts/
│   ├── call_claude.py                 ← Claude Sonnet 4.6 + Prompt Caching 분석
│   ├── fetch_data.py                  ← yfinance + 네이버 시장 데이터 수집
│   ├── fetch_news.py                  ← Gemini 2.5 Flash Lite 뉴스 요약
│   ├── fetch_closing_kospi.py         ← 코스피 마감 데이터 수집 (네이버)
│   ├── generate_html.py              ← Jinja2 템플릿 기반 HTML 렌더링
│   ├── send_telegram.py              ← 텔레그램 봇 전송
│   ├── send_email.py                 ← Resend API 이메일 전송
│   ├── update_latest.py              ← web/data/latest.json 갱신
│   ├── holiday_check.py              ← 한국/미국 공휴일 확인
│   ├── patch_fg.py                   ← Fear & Greed 지수 HTML 패치
│   ├── check_accuracy.py             ← 전일 예측 정확도 체크
│   ├── translate_to_en.py            ← 영문 번역 (현재 비활성)
│   ├── update_sheets.py              ← Google Sheets 연동
│   ├── patch_reason_block.py         ← 예측 근거 블록 패치
│   └── templates/
│       ├── briefing.html              ← 브리핑 페이지 Jinja2 템플릿
│       ├── briefing_closing.html      ← 마감 시황 Jinja2 템플릿
│       ├── index.html                 ← 날짜별 index 템플릿
│       ├── kospi_morning.md           ← Claude 에이전트 프롬프트 (코스피)
│       └── us_evening.md              ← Claude 에이전트 프롬프트 (미국)
├── web/
│   ├── landing.html                   ← 랜딩페이지 (doubleshot.space/)
│   ├── index.html                     ← 최신 브리핑 리다이렉트
│   ├── favicon.svg                    ← GNB 로고 기반 SVG 파비콘
│   ├── briefings/
│   │   ├── index.html                 ← 브리핑 목록 (/briefings)
│   │   ├── YYYY-MM-DD-kospi.html      ← 코스피 브리핑
│   │   ├── YYYY-MM-DD-us.html         ← 미국 브리핑
│   │   ├── ko-close/YYYY-MM-DD/       ← 코스피 마감 시황
│   │   └── YYYY-MM-DD/index.html      ← 날짜별 통합 index
│   ├── data/
│   │   └── latest.json                ← 최신 브리핑 요약 (구독 API용)
│   └── assets/
│       ├── style.css
│       ├── main.js
│       ├── briefing-list.js
│       └── og-image.svg
├── data/
│   ├── briefings.json                 ← 예측·정확도 누적 데이터
│   ├── telegram_sent_log.json         ← 텔레그램 발송 이력
│   ├── latest_kospi.json              ← 최신 코스피 데이터 (gitignore)
│   ├── latest_us.json                 ← 최신 미국 데이터 (gitignore)
│   ├── analysis_kospi.json            ← Claude 분석 결과 (gitignore)
│   ├── analysis_us.json               ← Claude 분석 결과 (gitignore)
│   ├── news_summary_kospi.json        ← Gemini 뉴스 요약
│   └── news_summary_us.json           ← Gemini 뉴스 요약
├── docs/
│   ├── PRD.md                         ← 본 문서
│   └── SYSTEM_REPORT.md               ← 시스템 리포트
└── .github/workflows/
    └── daily_report.yml               ← 5개 job (kospi/us/kospi-close/fg-patch/accuracy)
```

---

## 13. 변경 이력

| **날짜** | **주요 변경** |
|---|---|
| 2026-04-13 | PRD 최초 작성 (DailyB 명칭, Netlify 배포, Claude CLI 기반) |
| 2026-04-14 | 하이브리드 AI 파이프라인 도입 (Gemini + Claude Prompt Caching) |
| 2026-04-15 | Netlify → GitHub Pages 이전, 예측 정확도 트래킹 추가, 도메인 doubleshot.space 적용 |
| 2026-04-17 | Jinja2 템플릿 분리 (generate_html.py 리팩토링) |
| 2026-04월 중~하순 | 이메일 발송(Resend), OG 이미지, 파비콘, GA, 랜딩페이지 한/영 전환 |
| 2026-05-01~07 | Vercel Cron 도입, DRAM ETF 추가, 네이버 투자자 순매수 전환 |
| 2026-05-09~13 | 코스피 마감 브리핑 파이프라인 추가 (섹터 성과, 급등주, 스파크라인) |
| 2026-05-14 | Vercel Cron → cron-job.org 이전, 텔레그램 중복 발송 방지 개선 |
| 2026-05-15 | PRD 전면 업데이트 (현행 시스템 상태 반영) |

---

*본 문서는 Double-Shot 시스템의 설계·구현 전 과정을 기록한 것으로, 시스템 유지보수 및 기능 확장 시 참고 자료로 활용할 수 있습니다.*
