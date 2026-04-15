# Daily30 시스템 리포트

## 서비스 개요

개인 투자 브리핑 자동화 시스템. 매일 코스피 시초가·미국 증시 방향을 AI로 예측하여 웹 페이지와 Telegram으로 발행한다.

---

## 아키텍처 개요

```
GitHub Actions 스케줄
        │
        ├─► [holiday_check.py] 휴장일이면 중단
        │
        ├─► [fetch_data.py] yfinance + CNN FG Index로 시장 데이터 수집
        │                   → data/latest_{type}.json
        │
        ├─► [fetch_news.py] Google News RSS → Gemini 2.5 Flash Lite 요약
        │                   → data/news_summary_{type}.json
        │
        ├─► [call_claude.py] Claude Sonnet 4.6 (Prompt Caching)
        │     + [generate_html.py] 분석 JSON → HTML 자동 생성
        │                   → data/analysis_{type}.json
        │                   → web/briefings/YYYY-MM-DD-{type}.html
        │                   → web/index.html (최신으로 덮어씀)
        │
        ├─► [send_telegram.py] 요약 메시지 전송
        │
        └─► git commit & push → Netlify 자동 배포
```

---

## 실행 스케줄

| 브리핑 | 크론 (UTC) | 발행 시각 (KST) |
|---|---|---|
| 코스피 시초가 | `5 23 * * 0-4` (일~목) | 매일 **08:05** |
| 미국 시장 | `15 12 * * 1-5` (월~금) | 매일 **21:15** |
| 주간 리포트 | — | 미구현 |

---

## 스크립트별 역할

| 스크립트 | 입력 | 출력 | 비고 |
|---|---|---|---|
| `holiday_check.py` | `--market kospi\|us` | exit code 0/1 | 공휴일·주말 판단 |
| `fetch_data.py` | `--type kospi\|us` | `latest_{type}.json` | yfinance, sparkline, MA20/200 |
| `fetch_news.py` | `--type kospi\|us` | `news_summary_{type}.json` | Gemini Flash Lite, max 512 tokens |
| `call_claude.py` | `--type`, JSON 파일들 | `analysis_{type}.json` + HTML | Prompt Caching, JSON only 출력 |
| `generate_html.py` | analysis + market JSON | `.html` 파일 2개 | Canvas 차트 데이터 embedding |
| `send_telegram.py` | `--type` | Telegram 메시지 | 실패해도 파이프라인 계속 |
| `update_sheets.py` | — | Google Sheets 행 추가 | 미구현 (설정만 완료) |

---

## 사용 외부 서비스

| 서비스 | 용도 | 비용 |
|---|---|---|
| **Claude Sonnet 4.6** | 시장 분석 생성 | ~$0.07/회 |
| **Gemini 2.5 Flash Lite** | 뉴스 요약 | ~$0.0004/회 (무시할 수준) |
| **yfinance** | 주가·지수 데이터 | 무료 |
| **CNN Fear & Greed** | 공포탐욕지수 | 무료 |
| **Google News RSS** | 뉴스 헤드라인 | 무료 |
| **Telegram Bot API** | 브리핑 알림 | 무료 |
| **Netlify** | 정적 웹 호스팅 | 무료 |
| **Google Sheets** | 데이터 아카이브 | 미구현 |

**월 API 비용: 약 $3.13 (44회 실행 기준)**

---

## 웹 서비스 구성

```
web/
├── index.html                       ← 항상 최신 브리핑 (매 실행마다 덮어씀)
├── briefings/
│   └── YYYY-MM-DD-{type}.html       ← 날짜별 아카이브
└── assets/
    ├── style.css                    ← 라이트/다크 모드, 컴포넌트 스타일
    └── main.js                      ← Canvas 차트, 게이지, 모달, 테마 토글
```

**주요 UI 컴포넌트:**
- 예측 카드 (상승/하락 확률 바, 신뢰도)
- 예측 근거 bullet (이모지 + `<b>수치</b>` 강조)
- 잭 켈로그 MA20 종목 카드 (mini chart: 주가·MA20·MA200)
- 사이드바 시장 지표 (sparkline + 등락률)
- 공포탐욕지수 게이지
- 설명 모달 3종 (예측 방법론, 켈로그 전략, 공포탐욕지수)

---

## 비용 최적화 내역 (커밋 7e46693)

| 최적화 항목 | 절감 효과 |
|---|---|
| Claude → JSON only 출력 (HTML은 Python 생성) | 출력 토큰 -4,000/회 |
| Gemini Flash로 뉴스 사전 압축 | Claude 입력 토큰 절감 |
| Prompt Caching (시스템 프롬프트 2,055 tokens) | 재시도 시 90% 할인 |
| yfinance 사전 수집 (웹 검색 제거) | 입력 토큰 -3,400/회 |
| **합계** | **이전 대비 49% 절감** ($6.14 → $3.13/월) |

---

## 구현 현황

| 기능 | 상태 |
|---|---|
| 코스피·미국 일일 자동 브리핑 | ✅ 완료 |
| Claude Prompt Caching | ✅ 완료 |
| Gemini 뉴스 요약 | ✅ 완료 |
| HTML 동적 생성 + 아카이브 | ✅ 완료 |
| Telegram 알림 | ✅ 완료 |
| Dark/Light 모드 | ✅ 완료 |
| Sparkline & 미니 차트 | ✅ 완료 |
| Google Sheets 적재 | ⬜ 미구현 |
| 주간 리포트 | ⬜ 미구현 |
| 종목 캘린더 (실적발표 등) | ⬜ 미구현 |
