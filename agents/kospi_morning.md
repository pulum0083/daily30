# 코스피 시초가 브리핑 에이전트

오늘 날짜(KST 기준)의 코스피 시초가 방향 예측 브리핑을 생성한다.
(휴장일 확인은 workflow가 이미 수행했으므로 여기서는 건너뛴다.)

## Step 1: 시장 데이터 수집

`data/latest_kospi.json`이 이미 존재하면 이를 활용한다. 없거나 불충분하면 웹 검색으로 아래 데이터를 직접 수집한다:

### 수집 대상 데이터 (전일 종가 / 최신 기준)
| 지표 | 설명 |
|------|------|
| S&P 500 | 전일 종가, 등락률 |
| NASDAQ | 전일 종가, 등락률 |
| 다우존스 | 전일 종가, 등락률 |
| 필라델피아 반도체지수 (SOX) | 전일 종가, 등락률 |
| EWY ETF | 전일 종가, 등락률 |
| VIX | 현재 수준 |
| 공포탐욕지수 | CNN Fear & Greed Index |
| 달러 인덱스 (DXY) | 전일 종가, 등락률 |
| 원/달러 환율 | 최신 |
| WTI 유가 | 전일 종가, 등락률 |
| 브렌트유 | 전일 종가, 등락률 |
| 미국 10년물 국채 금리 | 현재 |
| 코스피200 선물 프리장 수급 | 외국인 순매수/순매도 계약수 (가용 시) |
| 미국 빅테크 전일 성과 | NVDA, AAPL, MSFT, AMZN, META, GOOGL |
| 아시아 선물 | 코스피/닛케이 야간선물 (가용 시) |
| 금 | 전일 종가, 등락률 |

## Step 2: 코스피 방향 예측

수집한 데이터를 기반으로 오늘 코스피 시초가 방향을 분석한다.

**예측 출력 형식:**
- 방향: 상승 우위 / 하락 우위 / 중립
- 상승 확률: X%, 하락 확률: Y%
- 신뢰도: XX% (데이터 가용성과 신호 일관성 기준)

**예측 근거 (최소 5개 bullet point):**
- 각 핵심 지표가 상승/하락 시그널로 작용하는 이유를 명시
- 수치 포함 (예: S&P500 +1.82%, SOX +2.41%)
- 리스크 요인도 반드시 포함

**잭 켈로그 20일선 전략 종목 (3~5개):**
- MA20 상향 돌파 또는 MA20 지지 반등 + 거래량 급증 조건
- 각 종목마다: 종목명, 현재가, 등락률, MA20/MA200 대비 위치, 시나리오, 실행 가이드

## Step 3: HTML 브리핑 생성

분석 결과를 `data/analysis_kospi.json`에 아래 형식으로 저장한다:

```json
{
  "prediction": {
    "direction": "상승 우위",
    "up_pct": 68,
    "down_pct": 32,
    "confidence": 84
  },
  "reasons": [
    "🇺🇸 S&P500 <b>+1.82%</b> ...",
    "💡 SOX <b>+2.41%</b> ..."
  ],
  "stock_picks": [
    {
      "name": "SK하이닉스",
      "price": "185,200원",
      "change": "+3.47%",
      "change_cls": "up",
      "signal": "MA200 탈환 + MA20 돌파",
      "golden": true,
      "ma20_dist_pct": 2.1,
      "ma200_dist_pct": 2.9,
      "scenario_tag": "구조적 변화",
      "scenario": "...",
      "action_guide": "시가 +2% 이내 출발 시 진입 유리."
    }
  ]
}
```

```bash
python3 scripts/generate_html.py --type kospi --data-file data/latest_kospi.json
```

저장 경로:
- `web/briefings/YYYY-MM-DD-kospi.html`
- `web/index.html` (덮어쓰기)

## Step 4: 텔레그램 메시지 파일 저장

텔레그램 메시지를 `data/telegram_message_kospi.txt`에 아래 형식으로 저장한다.
(실제 전송은 GitHub Actions workflow가 담당하므로 send_telegram.py를 직접 실행하지 않는다)

```
🇰🇷 코스피 시초가 브리핑 | YYYY.MM.DD

📊 예측: [상승/하락] 우위 ([X]%)
신뢰도: [XX]%

핵심 시그널:
• [bullet 1 — 가장 중요한 근거]
• [bullet 2]
• [bullet 3]

⚠️ 주요 리스크: [한 줄]

🔗 상세 분석 → https://bejewelled-toffee-87de55.netlify.app/briefings/YYYY-MM-DD-kospi.html
```

## 오류 처리

각 Step이 실패해도 다음 Step을 계속 진행한다. 실패 항목만 로그에 기록한다.
