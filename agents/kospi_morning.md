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

⚠️ **가격 데이터 필수 규칙:**
- 모든 종목의 현재가/종가는 반드시 **웹 검색으로 당일 최신 가격을 확인**한다. 학습 데이터의 과거 가격을 절대 사용하지 않는다.
- 네이버 금융(finance.naver.com), Google Finance, Yahoo Finance 등에서 실시간 시세를 검색한다.
- 검색 예: "SK하이닉스 주가", "삼성전자 현재가"
- MA20, MA200도 웹 검색 또는 yfinance 데이터 기반으로 산출한다.
- 가격을 확인할 수 없는 종목은 추천 목록에서 제외한다.

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
      "name": "종목명 (예시)",
      "price": "웹 검색으로 확인한 실제 현재가",
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

### HTML 레이아웃 필수 구조

생성할 HTML은 반드시 **2컬럼 레이아웃**을 사용한다:
- 왼쪽: 브리핑 본문 (`layout-grid__main`)
- 오른쪽: 시장 지표 사이드바 (`layout-grid__right`)

```html
<div class="layout-grid">
  <div class="layout-grid__main">
    <!-- 브리핑 본문 (market-summary-bar, 예측카드, 종목추천 등) -->
  </div>
  <aside class="layout-grid__right">
    <div class="right-panel">
      <div class="panel-header">
        <span class="section-title">시장 지표</span>
        <span class="live-dot">LIVE</span>
      </div>
      <div class="mkt-list">
        <div class="mkt-group" id="mkt-g1">
          <div class="mkt-group-header" onclick="toggleMktGroup('mkt-g1')">
            <span class="mkt-group-title">국내 · 미국 · 환율</span>
            <svg class="mkt-group-chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"/></svg>
          </div>
          <div class="mkt-group-body"><div class="mkt-group-body-inner">
            <!-- 각 지표 row -->
            <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">코스피</span><div class="mkt-vals"><div class="mkt-val" id="kospi-val">-</div><div class="mkt-chg" id="kospi-badge">-</div></div></div><div class="mkt-spark"><canvas id="c-kospi"></canvas></div></div>
            <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">코스닥</span><div class="mkt-vals"><div class="mkt-val" id="kosdaq-val">-</div><div class="mkt-chg" id="kosdaq-badge">-</div></div></div><div class="mkt-spark"><canvas id="c-kosdaq"></canvas></div></div>
            <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">나스닥</span><div class="mkt-vals"><div class="mkt-val" id="nasdaq-val">-</div><div class="mkt-chg" id="nasdaq-badge">-</div></div></div><div class="mkt-spark"><canvas id="c-nasdaq"></canvas></div></div>
            <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">나스닥100 선물</span><div class="mkt-vals"><div class="mkt-val" id="nq-val">-</div><div class="mkt-chg" id="nq-badge">-</div></div></div><div class="mkt-spark"><canvas id="c-nq"></canvas></div></div>
            <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">다우존스</span><div class="mkt-vals"><div class="mkt-val" id="dji-val">-</div><div class="mkt-chg" id="dji-badge">-</div></div></div><div class="mkt-spark"><canvas id="c-dji"></canvas></div></div>
            <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">필라델피아 반도체</span><div class="mkt-vals"><div class="mkt-val" id="sox-val">-</div><div class="mkt-chg" id="sox-badge">-</div></div></div><div class="mkt-spark"><canvas id="c-sox"></canvas></div></div>
            <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">달러환율 USD/KRW</span><div class="mkt-vals"><div class="mkt-val" id="usd-val">-</div><div class="mkt-chg" id="usd-badge">-</div></div></div><div class="mkt-spark"><canvas id="c-usd"></canvas></div></div>
            <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">달러 인덱스 DXY</span><div class="mkt-vals"><div class="mkt-val" id="dxy-val">-</div><div class="mkt-chg" id="dxy-badge">-</div></div></div><div class="mkt-spark"><canvas id="c-dxy"></canvas></div></div>
          </div></div>
        </div>
        <div class="mkt-group" id="mkt-g2">
          <div class="mkt-group-header" onclick="toggleMktGroup('mkt-g2')">
            <span class="mkt-group-title">변동성</span>
            <svg class="mkt-group-chevron" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"/></svg>
          </div>
          <div class="mkt-group-body"><div class="mkt-group-body-inner">
            <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">WTI 국제유가</span><div class="mkt-vals"><div class="mkt-val" id="oil-val">-</div><div class="mkt-chg" id="oil-badge">-</div></div></div><div class="mkt-spark"><canvas id="c-oil"></canvas></div></div>
            <div class="fg-block">
              <div class="fg-block-header"><span class="mkt-name">공포탐욕지수</span><span class="fg-badge" id="fg-badge">-</span></div>
              <div class="fg-body">
                <div class="fg-gauge-mini"><canvas id="fg-gauge-canvas" style="width:118px;height:64px;display:block;"></canvas></div>
                <div class="fg-info">
                  <div class="fg-now"><span class="fg-now-val" id="fg-value">-</span><span class="fg-now-lbl" id="fg-label">-</span></div>
                  <div class="fg-hist-grid">
                    <div class="fg-hist-item"><span class="lbl">전일</span><span class="val" id="fg-hist-prev">-</span></div>
                    <div class="fg-hist-item"><span class="lbl">1주</span><span class="val" id="fg-hist-1w">-</span></div>
                    <div class="fg-hist-item"><span class="lbl">1달</span><span class="val" id="fg-hist-1m">-</span></div>
                    <div class="fg-hist-item"><span class="lbl">1년</span><span class="val" id="fg-hist-1y">-</span></div>
                  </div>
                </div>
              </div>
            </div>
          </div></div>
        </div>
      </div>
    </div>
  </aside>
</div>
```

### 시장 지표 데이터 주입 (필수)

HTML `</body>` 직전에 아래 `<script>` 블록을 삽입하여 수집한 시장 데이터를 주입한다.
`data` 배열은 최근 10개 데이터 포인트 (sparkline용). yfinance `history(period="5d", interval="1h")`로 수집하거나, 웹 검색으로 최근 종가 추이를 넣는다.

```html
<script>
window.MARKET_DATA = {
  kospi:  { base: 2584.93, chg: 1.00, data: [2556,2562,2570,2575,2578,2580,2582,2583,2584,2585] },
  kosdaq: { base: 740.11,  chg: 0.79, data: [730,733,735,736,737,738,739,739,740,740] },
  nasdaq: { base: 17728.39,chg: 2.39, data: [17300,17400,17480,17520,17560,17600,17650,17680,17710,17728] },
  nq:     { base: 19897.19,chg: 0.18, data: [19800,19820,19840,19850,19860,19870,19880,19885,19890,19897] },
  dji:    { base: 40887.75,chg: 1.49, data: [40200,40350,40450,40520,40580,40650,40720,40780,40840,40888] },
  sox:    { base: 4825.53, chg: 2.36, data: [4700,4720,4740,4755,4770,4785,4800,4810,4820,4826] },
  oil:    { base: 61.70,   chg:-4.04, data: [64.5,64.0,63.5,63.1,62.8,62.5,62.2,61.9,61.8,61.7] },
  usd:    { base: 1376.77, chg:-0.29, data: [1382,1381,1380,1380,1379,1378,1378,1377,1377,1377] },
  dxy:    { base: 102.57,  chg:-0.17, data: [103.0,102.9,102.9,102.8,102.8,102.7,102.7,102.6,102.6,102.6] },
  fearGreed: { value: 27, prev: 6, "1w": 12, "1m": 64, "1y": 75 }
};
</script>
```

위 값들은 **반드시 Step 1에서 수집한 실제 데이터로 채운다**. 예시 숫자를 그대로 사용하지 않는다.

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
