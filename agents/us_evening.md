# 미국 시장 브리핑 에이전트

오늘 날짜(KST 기준)의 미국 시장 방향 예측 브리핑을 생성한다. 현재 시각은 KST 22:30경이며, 미국 시장은 약 1시간 후 개장한다 (EST 13:30, 서머타임 적용 시 12:30).

## Step 1: 미국 휴장일 확인

웹 검색으로 오늘이 미국 주식시장(NYSE/NASDAQ) 공휴일인지 확인한다. 공휴일이면:
- "오늘은 미국 주식시장 휴장일입니다. 브리핑을 생성하지 않습니다."를 출력하고 종료.

## Step 2: 시장 데이터 수집

```bash
python3 scripts/fetch_data.py --type us
```

fetch_data.py 실패 시 웹 검색으로 아래 데이터를 직접 수집한다:

### 수집 대상 데이터 (당일 최신 기준 — 미국 프리마켓 포함)
| 지표 | 설명 |
|------|------|
| S&P500 선물 | 프리마켓 등락률 |
| 나스닥100 선물 | 프리마켓 등락률 |
| 다우존스 선물 | 프리마켓 등락률 |
| NVDA | 프리마켓 가격, 등락률 |
| AAPL | 프리마켓 가격, 등락률 |
| MSFT | 프리마켓 가격, 등락률 |
| AMZN | 프리마켓 가격, 등락률 |
| META | 프리마켓 가격, 등락률 |
| GOOGL | 프리마켓 가격, 등락률 |
| TSLA | 프리마켓 가격, 등락률 |
| VIX | 현재 |
| 미국 10년물 국채 금리 | 현재, 전일 대비 |
| 달러 인덱스 (DXY) | 현재, 등락률 |
| WTI 유가 | 현재, 등락률 |
| 공포탐욕지수 | CNN Fear & Greed Index |
| 아시아 증시 마감 | 코스피, 닛케이, 항셍 등락률 |
| 유럽 증시 | DAX, FTSE100, CAC40 등락률 |
| 오늘의 경제지표 발표 | 발표 예정 지표 및 영향도 |
| 연준 위원 발언 일정 | 오늘 예정 여부 |

## Step 3: 미국 시장 방향 예측

**예측 출력 형식:**
- 방향: 상승 / 하락 / 보합
- S&P500 예상 범위: +X.X% ~ +Y.Y% (또는 -X.X% ~ -Y.Y%)
- 상승 확률: X%, 하락 확률: Y%
- 핵심 섹터: 오늘 주목할 섹터 (반도체/에너지/금융/빅테크 등)

**예측 근거 (최소 5개 bullet point):**
- 아시아·유럽 증시 흐름
- 선물 프리마켓 방향
- VIX 및 공포탐욕지수
- 국채 금리 및 달러 움직임
- 주요 경제지표 및 연준 이벤트
- 빅테크 프리마켓 수급

**잭 켈로그 20일선 전략 — 미국 종목 (3~5개):**
- MA20 상향 돌파 또는 MA20 지지 반등 + 거래량 급증 조건
- 각 종목마다: 티커, 현재가, 등락률, MA20/MA200 대비, 시나리오, 실행 가이드

## Step 4: HTML 브리핑 생성

분석 결과를 `data/analysis_us.json`에 저장한다 (kospi와 동일 JSON 구조).

```bash
python3 scripts/generate_html.py --type us --data-file data/latest_us.json
```

저장 경로:
- `web/briefings/YYYY-MM-DD-us.html`
- `web/index.html` (덮어쓰기)

## Step 5: 텔레그램 메시지 파일 저장

텔레그램 메시지를 `data/telegram_message_us.txt`에 저장한다.
(실제 전송은 GitHub Actions workflow가 담당하므로 send_telegram.py를 직접 실행하지 않는다)

```
🇺🇸 미국 시장 브리핑 | YYYY.MM.DD

📊 S&P500 예측: [상승/하락] ([+X.X% ~ +Y.Y%])
상승확률: [X]%

핵심 시그널:
• [bullet 1]
• [bullet 2]
• [bullet 3]

📅 오늘의 이벤트: [주요 경제지표 or 연준 발언]

🔗 상세 분석 → https://bejewelled-toffee-87de55.netlify.app/briefings/YYYY-MM-DD-us.html
```

## 오류 처리

각 Step이 실패해도 다음 Step을 계속 진행한다.
