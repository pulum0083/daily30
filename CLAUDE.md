# DailyB — 개인 투자 비서

## 프로젝트 개요

자동화된 일일/주간 투자 브리핑 생성 시스템. 코스피 및 미국 시장 방향 예측, 주간 이슈 점검, 텔레그램 알림, 구글 시트 데이터 적재를 담당한다.

## 실행 흐름

```
스케줄 트리거 → 시장 데이터 수집 → 휴장 확인 → 분석/예측 생성 → HTML 저장 → 텔레그램 전송 → 구글 시트 업데이트
```

## 디렉토리 구조

```
DailyB/
├── CLAUDE.md
├── agents/
│   ├── kospi_morning.md      # 월~금 08:30 KST 코스피 브리핑
│   ├── us_evening.md         # 월~금 22:30 KST 미국 시장 브리핑
│   └── weekly_report.md      # 일요일 21:00 KST 주간 리포트
├── scripts/
│   ├── fetch_data.py         # yfinance 기반 시장 데이터 수집
│   ├── generate_html.py      # HTML 브리핑 생성
│   ├── send_telegram.py      # 텔레그램 전송
│   ├── update_sheets.py      # 구글 시트 업데이트
│   └── holiday_check.py      # 휴장일 확인
├── web/
│   ├── index.html            # 최신 브리핑 (항상 최신으로 덮어씀)
│   ├── briefings/            # 날짜별 아카이브 (YYYY-MM-DD-{type}.html)
│   └── assets/               # CSS/JS 정적 파일
├── data/
│   └── briefings.json        # 누적 구조화 데이터
├── config.json               # API 키 및 설정 (git 미포함)
└── config.example.json       # 설정 템플릿
```

## 설정 파일 (config.json)

처음 사용 전 `config.example.json`을 복사하여 `config.json`으로 저장하고 값을 채운다.

```json
{
  "telegram": {
    "bot_token": "...",
    "chat_id": "..."
  },
  "google_sheets": {
    "credentials_file": "gcp_credentials.json",
    "spreadsheet_id": "..."
  },
  "web": {
    "base_url": "https://your-hosting-url.com"
  }
}
```

## 에이전트별 실행 방법

### 코스피 브리핑 (월~금 08:30 KST)
```bash
claude --print agents/kospi_morning.md
```

### 미국 시장 브리핑 (월~금 22:30 KST)
```bash
claude --print agents/us_evening.md
```

### 주간 리포트 (일요일 21:00 KST)
```bash
claude --print agents/weekly_report.md
```

## 주요 규칙

1. **휴장일 스킵**: 한국 공휴일(코스피), 미국 공휴일(US 브리핑) 확인 후 해당일엔 실행 중단
2. **데이터 최신성**: 항상 당일 최신 데이터 기준으로 생성. yfinance 실패 시 웹 검색으로 대체
3. **HTML 저장 경로**: `web/briefings/YYYY-MM-DD-kospi.html`, `web/briefings/YYYY-MM-DD-us.html`
4. **index.html 갱신**: 최신 브리핑 생성 후 `web/index.html`도 최신 내용으로 덮어씀
5. **텔레그램 메시지**: 핵심 요약 300자 이내 + 웹 서비스 링크
6. **구글 시트**: 날짜, 브리핑 유형, 예측 방향, 신뢰도, 핵심 지표값만 저장 (짧은 구조화 데이터)
7. **오류 처리**: 개별 스텝 실패 시 로그 남기고 다음 스텝 계속 진행
