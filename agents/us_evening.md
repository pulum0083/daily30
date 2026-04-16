# 미국 시장 브리핑 에이전트

오늘 날짜(KST 기준)의 미국 시장 방향 예측 브리핑을 생성한다. 현재 시각은 KST 22:30경이며, 미국 시장은 약 1시간 후 개장한다 (EST 13:30, 서머타임 적용 시 12:30).
(휴장일 확인은 workflow가 이미 수행했으므로 여기서는 건너뛴다.)

## Step 1: 시장 데이터 수집

`data/latest_us.json` 파일을 읽어라. **이 파일 하나에 모든 시장 데이터가 사전 수집되어 있다.**

- `market_data_js` → `window.MARKET_DATA` 스크립트에 그대로 사용 (sidebar 지표 + sparkline 포함)
- `fearGreed` → 공포탐욕지수 (이미 `market_data_js.fearGreed`에 포함)
- `sp500`, `vix`, `bigtech`, `gold`, `rates`, `oil`, `futures`, `asia`, `europe` → 예측 분석에 활용
- `us_candidates` → 잭 켈로그 전략 종목 후보 (가격, MA20, MA200, signal 포함, signal 우선순위 순 정렬)

**웹 검색 최소화**: 모든 시장 데이터는 JSON 파일에 있다. 오늘의 경제지표 발표 일정 및 연준 이벤트 확인을 위해 1~2회 웹 검색 허용. 종목 가격 웹 검색 금지.

## Step 2: 미국 시장 방향 예측

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

✅ **종목 가격 데이터 규칙:**
- `us_candidates` 배열에서 `ma20_signal`이 `crossing_up` 또는 `above`인 종목을 우선 선택한다.
- `price`, `change_pct`, `ma20`, `ma20_dist_pct`, `ma200`, `ma200_dist_pct`는 JSON에서 읽어 그대로 사용한다.
- `sparkline`, `ma20_sparkline`, `ma200_sparkline` 배열을 `stockCharts` 항목의 `prices`, `ma20`, `ma200`에 매핑한다.
- JSON에 없는 종목을 추천하려면 1회만 웹 검색하여 가격을 확인한 후 사용한다.

## Step 3: 분석 결과 저장

분석 결과를 `data/analysis_us.json`에 저장한다 (kospi와 동일 JSON 구조).
**HTML은 별도 스크립트(`scripts/generate_html.py`)가 생성하므로 여기서 HTML을 출력하지 않는다.**

```json
{
  "prediction": {
    "direction": "상승 우위",
    "up_pct": 60,
    "down_pct": 40,
    "confidence": 72
  },
  "reasons": [
    "🌏 아시아 증시 … <b>수치</b> …",
    "📈 S&P500 선물 … <b>수치</b> …",
    "📉 VIX … <b>수치</b> …",
    "🏦 국채금리 … <b>수치</b> …",
    "💹 빅테크 프리마켓 … <b>수치</b> …"
  ],
  "stock_picks": [
    {
      "name": "NVDA (엔비디아)",
      "price": "$XXX.XX",
      "change": "+X.XX%",
      "change_cls": "up",
      "signal": "MA20 상향 돌파",
      "golden": false,
      "ma20_dist_pct": 3.2,
      "ma200_dist_pct": 22.1,
      "scenario_tag": "모멘텀 가속",
      "scenario": "시나리오 설명.",
      "action_guide": "시가 $XXX 이내 진입. 목표: $YYY / 손절: $ZZZ 이탈 시."
    }
  ]
}
```

**`scenario` 문체 규칙:**
- 종결 어미는 반드시 `~함`, `~있음`, `~충족`, `~예상` 등 **명사형/단언형**으로 끊는다. `~입니다`, `~합니다` 사용 금지.
- MA20·MA200 실제 수치(달러)를 문장 안에 직접 언급한다 (예: "MA20($168.76)을 상향 돌파하며").
- 2~3문장으로 작성하되, 가격·수급 시그널 → 추가 상승 여지 순서로 전개한다.

예시:
```
MS는 MA20($168.76)과 MA200($161.76)을 모두 크게 상회하며 골든 조건을 충족. 빅테크 섹터 전반에 수급이 집중되는 국면에서 클라우드·AI 성장 기대감이 추가 모멘텀으로 작용할 가능성이 높음.
```

저장 완료 후 별도 조치 없음 — HTML 생성은 workflow가 `generate_html.py`를 통해 처리한다.

## Step 4: 텔레그램 메시지 파일 저장

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

🔗 상세 분석 → https://pulum0083.github.io/daily30/briefings/YYYY-MM-DD-us.html
```

## 오류 처리

각 Step이 실패해도 다음 Step을 계속 진행한다.
