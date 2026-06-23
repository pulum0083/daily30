# 종목 대시보드 3종 실측화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 대시보드의 시세·차트·52주 / 실시간 가격 / 섹터 리스트 3개 항목을 일러스트에서 실측 데이터로 전환한다.

**Architecture:** 단일 config(`stock_universe.json`, 8섹터 ~48종목)를 출처로 삼아 — (1) 매일 1회 토스 캔들 스냅샷 빌드(`build_stocks_snapshot.py` → `stocks-snapshot.json`), (2) 서버리스 폴링 엔드포인트(`api/stocks-live.mjs`, 커밋 안 함), (3) 섹터별 정적 페이지(`/stocks/sector/{key}/`)를 만든다. 화면 수치는 전부 실측, 라이브 데이터는 git에 내보내지 않는다.

**Tech Stack:** Python 3 (토스 Open API, yfinance/네이버 폴백), Node 서버리스(Vercel, `api/*.mjs`), 정적 HTML 생성(`generate_html.py`), 순수함수 단위 테스트(`python3 scripts/test_*.py`).

**참고 스펙:** `docs/superpowers/specs/2026-06-24-stocks-dashboard-realdata-design.md`

**전제/주의:**
- SERVICE_RULES 0번: 화면 수치는 전부 실측. 라이브 데이터 git 커밋 금지.
- 한국 종목은 6자리 코드만 (`.KS`/`.KQ` 접미사 금지 — yfinance KOSDAQ 유령데이터 방지).
- 대시보드 페이지 본체(`web/stocks/index.html`)는 현재 `/tmp/stock-preview/web/stocks/index.html` 프로토타입으로만 존재. **Phase 5 착수 전, 사용자가 다듬은 최신 프로토를 `web/stocks/index.html`로 승격(repo 반영)했는지 확인**한다. 미승격 시 Phase 1~4(백엔드)만 먼저 진행 가능.
- 테스트 컨벤션: 순수함수만 `test_*` 함수로 작성, 파일 하단 `run()` + `if __name__=="__main__"`, 네트워크 없음. 실행 `python3 scripts/test_xxx.py`.

---

## File Structure

**생성:**
- `scripts/config/stock_universe.json` — 8섹터 종목 + 섹터별 벨웨더 단일 매핑
- `scripts/build_stocks_snapshot.py` — 캔들→스냅샷 빌드 (순수 계산함수 + 오케스트레이터)
- `scripts/test_build_stocks_snapshot.py` — 순수 계산함수 단위 테스트
- `api/stocks-live.mjs` — 시간대 분기 실시간 현재가 서버리스 (커밋 안 함)
- `scripts/templates/pages/stock_sector.html` — 섹터 페이지 템플릿
- (생성물) `web/data/stocks-snapshot.json` — 매일 커밋
- (생성물) `web/stocks/sector/{key}/index.html` × 8 — 매일 재생성·커밋

**수정:**
- `scripts/generate_html.py` — 섹터 8페이지 생성 + 홈에 스냅샷 주입
- `web/stocks/index.html` — 스냅샷 baseline + `/api/stocks-live` 폴링 배선, 섹터 칩 링크
- `.github/workflows/daily_report.yml` — `kospi-close-briefing` 잡에 스냅샷 빌드·섹터 생성 스텝 추가

---

## Phase 1 — 종목 유니버스 config

### Task 1: stock_universe.json 생성

**Files:**
- Create: `scripts/config/stock_universe.json`

- [ ] **Step 1: JSON 파일 작성**

기존 `SECTOR_FOCUS_STOCKS`(섹터당 3종목)를 6자리 코드로 변환하고 섹터당 5~6종목으로 확장. 벨웨더는 미국 짝 종목/ETF.

```json
{
  "sectors": {
    "semicon": {
      "label": "반도체",
      "stocks": [
        { "code": "005930", "name": "삼성전자" },
        { "code": "000660", "name": "SK하이닉스" },
        { "code": "042700", "name": "한미반도체" },
        { "code": "058470", "name": "리노공업" },
        { "code": "000990", "name": "DB하이텍" },
        { "code": "039030", "name": "이오테크닉스" }
      ],
      "bellwethers": [
        { "t": "NVDA", "name": "엔비디아", "kind": "US" },
        { "t": "MU", "name": "마이크론", "kind": "US" },
        { "t": "SOXX", "name": "반도체 ETF", "kind": "US" }
      ]
    },
    "power": {
      "label": "전력기기",
      "stocks": [
        { "code": "267260", "name": "HD현대일렉트릭" },
        { "code": "010120", "name": "LS일렉트릭" },
        { "code": "298040", "name": "효성중공업" },
        { "code": "034020", "name": "두산에너빌리티" },
        { "code": "033100", "name": "제룡전기" }
      ],
      "bellwethers": [
        { "t": "GEV", "name": "GE Vernova", "kind": "US" },
        { "t": "VRT", "name": "Vertiv", "kind": "US" }
      ]
    },
    "defense": {
      "label": "방산",
      "stocks": [
        { "code": "012450", "name": "한화에어로스페이스" },
        { "code": "079550", "name": "LIG넥스원" },
        { "code": "064350", "name": "현대로템" },
        { "code": "047810", "name": "한국항공우주" },
        { "code": "272210", "name": "한화시스템" }
      ],
      "bellwethers": [
        { "t": "ITA", "name": "방산 ETF", "kind": "US" },
        { "t": "LMT", "name": "록히드마틴", "kind": "US" }
      ]
    },
    "ship": {
      "label": "조선",
      "stocks": [
        { "code": "329180", "name": "HD현대중공업" },
        { "code": "042660", "name": "한화오션" },
        { "code": "010140", "name": "삼성중공업" },
        { "code": "009540", "name": "HD한국조선해양" },
        { "code": "010620", "name": "HD현대미포" }
      ],
      "bellwethers": []
    },
    "battery": {
      "label": "2차전지",
      "stocks": [
        { "code": "373220", "name": "LG에너지솔루션" },
        { "code": "247540", "name": "에코프로비엠" },
        { "code": "006400", "name": "삼성SDI" },
        { "code": "003670", "name": "포스코퓨처엠" },
        { "code": "066970", "name": "엘앤에프" }
      ],
      "bellwethers": [
        { "t": "ALB", "name": "Albemarle", "kind": "US" },
        { "t": "LIT", "name": "리튬 ETF", "kind": "US" }
      ]
    },
    "auto": {
      "label": "자동차",
      "stocks": [
        { "code": "005380", "name": "현대차" },
        { "code": "000270", "name": "기아" },
        { "code": "012330", "name": "현대모비스" },
        { "code": "204320", "name": "HL만도" },
        { "code": "011210", "name": "현대위아" }
      ],
      "bellwethers": [
        { "t": "TSLA", "name": "테슬라", "kind": "US" },
        { "t": "F", "name": "포드", "kind": "US" }
      ]
    },
    "bio": {
      "label": "바이오",
      "stocks": [
        { "code": "207940", "name": "삼성바이오로직스" },
        { "code": "068270", "name": "셀트리온" },
        { "code": "000100", "name": "유한양행" },
        { "code": "326030", "name": "SK바이오팜" },
        { "code": "196170", "name": "알테오젠" }
      ],
      "bellwethers": [
        { "t": "XBI", "name": "바이오 ETF", "kind": "US" },
        { "t": "LLY", "name": "일라이릴리", "kind": "US" }
      ]
    },
    "finance": {
      "label": "금융",
      "stocks": [
        { "code": "105560", "name": "KB금융" },
        { "code": "055550", "name": "신한지주" },
        { "code": "138040", "name": "메리츠금융지주" },
        { "code": "086790", "name": "하나금융지주" },
        { "code": "316140", "name": "우리금융지주" }
      ],
      "bellwethers": [
        { "t": "JPM", "name": "JP모건", "kind": "US" },
        { "t": "KBE", "name": "은행 ETF", "kind": "US" }
      ]
    }
  }
}
```

- [ ] **Step 2: JSON 유효성·종목 수 확인**

Run:
```bash
python3 -c "import json; d=json.load(open('scripts/config/stock_universe.json')); n=sum(len(s['stocks']) for s in d['sectors'].values()); print('sectors',len(d['sectors']),'stocks',n); assert len(d['sectors'])==8; assert 40<=n<=55; print('OK')"
```
Expected: `sectors 8 stocks 41 ... OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/config/stock_universe.json
git commit -m "feat(종목 유니버스): stock_universe.json 8섹터 종목 매핑 추가"
```

> **유니버스 단일 출처:** 스냅샷 빌더(Phase 2)·섹터 페이지(Phase 4)·서버리스(Phase 3)는 모두 이 JSON을 직접 읽는다. 기존 `fetch_data.py`의 `SECTOR_FOCUS_STOCKS`(브리핑 파이프라인용)는 **건드리지 않는다** — `.KS` 접미사 기반 yfinance 흐름이라 전환 시 회귀 위험이 있고, 이번 3종 실측화에 필요하지 않다(YAGNI). 신규 기능과 브리핑은 유니버스 출처가 분리된 채 공존한다.

---

## Phase 2 — 스냅샷 빌더 (① 시세·차트·52주)

### Task 2: 순수 계산함수 (TDD)

종가 시계열에서 등락률·52주 고저·스파크라인·MA200을 계산하는 순수함수. 네트워크 없음.

**Files:**
- Create: `scripts/build_stocks_snapshot.py`
- Create: `scripts/test_build_stocks_snapshot.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# build_stocks_snapshot 순수 계산함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 scripts/test_build_stocks_snapshot.py"""
import build_stocks_snapshot as m


def test_change_pct():
    assert m.change_pct([100.0, 110.0]) == 10.0
    assert m.change_pct([200.0, 190.0]) == -5.0
    assert m.change_pct([100.0]) is None     # 직전 종가 없음
    assert m.change_pct([]) is None


def test_wk52():
    closes = [float(x) for x in range(1, 301)]   # 1..300
    hi, lo = m.wk52_high_low(closes)
    assert hi == 300.0
    # 최근 252거래일 = closes[-252:] → 49..300, 최저 49
    assert lo == 49.0


def test_spark():
    closes = [float(x) for x in range(1, 31)]    # 1..30
    assert m.sparkline(closes, 5) == [26.0, 27.0, 28.0, 29.0, 30.0]
    assert m.sparkline([1.0, 2.0], 5) == [1.0, 2.0]   # 데이터 부족 시 있는 만큼


def test_ma200():
    closes = [float(x) for x in range(1, 301)]   # 1..300
    # 최근 200개 = 101..300, 평균 = (101+300)/2 = 200.5
    assert m.ma200(closes) == 200.5
    assert m.ma200([1.0, 2.0]) is None           # 200개 미만


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: 실패 확인**

Run: `cd scripts && python3 test_build_stocks_snapshot.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_stocks_snapshot'`

- [ ] **Step 3: 순수함수 구현**

```python
# 종목 유니버스 일봉 → 시세·52주·스파크라인·MA200 스냅샷 빌드
#!/usr/bin/env python3
"""실행: python3 scripts/build_stocks_snapshot.py
   stock_universe.json의 ~48 한국 종목 + 섹터 벨웨더를 토스 캔들로 수집해
   web/data/stocks-snapshot.json 으로 저장한다. SERVICE_RULES 0번 준수."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))


def change_pct(closes):
    """직전 완료 세션 대비 등락률(%). 데이터 부족 시 None."""
    if len(closes) < 2:
        return None
    return round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)


def wk52_high_low(closes):
    """최근 252거래일 고가/저가. (hi, lo). 데이터 부족 시 있는 만큼."""
    if not closes:
        return None, None
    window = closes[-252:]
    return max(window), min(window)


def sparkline(closes, n):
    """최근 n개 종가. 부족하면 있는 만큼."""
    return closes[-n:]


def ma200(closes):
    """최근 200거래일 단순이동평균. 200개 미만이면 None."""
    if len(closes) < 200:
        return None
    window = closes[-200:]
    return round(sum(window) / len(window), 2)
```

- [ ] **Step 4: 통과 확인**

Run: `cd scripts && python3 test_build_stocks_snapshot.py`
Expected: `4 passed` → PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/build_stocks_snapshot.py scripts/test_build_stocks_snapshot.py
git commit -m "feat(스냅샷): 시세·52주·스파크라인·MA200 순수 계산함수 + 테스트"
```

### Task 3: 종가 시계열 수집 (토스 → 폴백)

**Files:**
- Modify: `scripts/build_stocks_snapshot.py`

- [ ] **Step 1: 시계열 수집 함수 추가**

`build_stocks_snapshot.py`에 추가:

```python
import urllib.request

sys.path.insert(0, str(Path(__file__).parent))
import toss_client as tc


def _toss_closes(symbol):
    """토스 일봉 종가 시계열(오래된→최신). 실패 시 []."""
    try:
        candles = tc.get_candles(symbol, interval="1d", count=300)
        return [float(c["closePrice"]) for c in candles if c.get("closePrice")]
    except Exception as e:
        print(f"[snapshot] toss {symbol} 실패: {e}", file=sys.stderr)
        return []


def _naver_closes(code):
    """네이버 일봉 폴백(한국). 실패 시 []."""
    try:
        end = datetime.now().strftime("%Y%m%d") + "0000"
        start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d") + "0000"
        url = (f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
               f"?startDateTime={start}&endDateTime={end}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        rows = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return [float(r["closePrice"]) for r in rows if r.get("closePrice")]
    except Exception as e:
        print(f"[snapshot] naver {code} 실패: {e}", file=sys.stderr)
        return []


def _yf_closes(ticker):
    """yfinance 폴백(미국). 실패 시 []."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="400d").dropna(subset=["Close"])
        return [float(x) for x in hist["Close"].tolist()]
    except Exception as e:
        print(f"[snapshot] yfinance {ticker} 실패: {e}", file=sys.stderr)
        return []


def fetch_closes(symbol, market):
    """market='kr'|'us'. 토스 우선, 폴백 분기. 한국은 6자리 코드만."""
    closes = _toss_closes(symbol)
    if closes:
        return closes
    return _naver_closes(symbol) if market == "kr" else _yf_closes(symbol)
```

- [ ] **Step 2: 한 종목 실제 수집 점검 (네트워크)**

Run: `cd scripts && python3 -c "import build_stocks_snapshot as m; c=m.fetch_closes('005930','kr'); print('len',len(c),'last',c[-1] if c else None)"`
Expected: `len 250+ last <삼성전자 최근 종가>` (네트워크 필요. 0이면 토스 인증/폴백 점검)

- [ ] **Step 3: Commit**

```bash
git add scripts/build_stocks_snapshot.py
git commit -m "feat(스냅샷): 종가 시계열 수집 (토스→네이버/yfinance 폴백)"
```

### Task 4: 스냅샷 오케스트레이터 + 저장

**Files:**
- Modify: `scripts/build_stocks_snapshot.py`

- [ ] **Step 1: build_snapshot + main 추가**

```python
UNIVERSE_PATH = Path(__file__).parent / "config" / "stock_universe.json"
OUT_PATH = Path(__file__).parent.parent / "web" / "data" / "stocks-snapshot.json"


def load_universe():
    return json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))


def _build_one(symbol, name, sector, market):
    closes = fetch_closes(symbol, market)
    if len(closes) < 2:
        print(f"[snapshot] {symbol}({name}) 데이터 부족 → 생략", file=sys.stderr)
        return None
    hi, lo = wk52_high_low(closes)
    return {
        "name": name, "sector": sector,
        "close": closes[-1],
        "change_pct": change_pct(closes),
        "wk52_high": hi, "wk52_low": lo,
        "spark5": sparkline(closes, 5),
        "spark20": sparkline(closes, 20),
        "ma200": ma200(closes),
    }


def build_snapshot():
    uni = load_universe()
    stocks, bellwethers = {}, {}
    for key, sec in uni["sectors"].items():
        for s in sec["stocks"]:
            rec = _build_one(s["code"], s["name"], key, "kr")
            if rec:
                stocks[s["code"]] = rec
        for b in sec.get("bellwethers", []):
            if b["t"] in bellwethers:
                continue
            rec = _build_one(b["t"], b["name"], key, "us")
            if rec:
                bellwethers[b["t"]] = {"name": b["name"], "close": rec["close"],
                                       "change_pct": rec["change_pct"]}
    return {
        "generated_at": datetime.now(KST).isoformat(),
        "stocks": stocks,
        "bellwethers": bellwethers,
    }


def main():
    snap = build_snapshot()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[snapshot] {len(snap['stocks'])}종목 + {len(snap['bellwethers'])}벨웨더 → {OUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 전체 빌드 실행 (네트워크)**

Run: `cd scripts && python3 build_stocks_snapshot.py`
Expected: `[snapshot] 40+종목 + N벨웨더 → .../web/data/stocks-snapshot.json`

- [ ] **Step 3: 산출물 검증**

Run:
```bash
python3 -c "import json; d=json.load(open('web/data/stocks-snapshot.json')); s=d['stocks']['005930']; print(s['name'],s['close'],s['change_pct'],'52w',s['wk52_high'],s['wk52_low'],'ma200',s['ma200'],'spark5',len(s['spark5']))"
```
Expected: `삼성전자 <종가> <등락%> 52w <고> <저> ma200 <값> spark5 5`

- [ ] **Step 4: Commit**

```bash
git add scripts/build_stocks_snapshot.py web/data/stocks-snapshot.json
git commit -m "feat(스냅샷): 유니버스 순회 빌드·저장 + 첫 스냅샷"
```

---

## Phase 3 — 실시간 서버리스 (② 실시간 가격, B안)

### Task 5: api/stocks-live.mjs

`market.mjs`의 토스 토큰 패턴을 재사용. KST 시간대 분기로 한국/미국 현재가 반환. 라이브 데이터는 커밋 안 함(런타임 응답).

**Files:**
- Create: `api/stocks-live.mjs`
- 참조(복사 대상): `api/market.mjs` 5–23행 (토스 토큰), `scripts/config/stock_universe.json`

- [ ] **Step 1: 엔드포인트 작성**

```javascript
// 종목 유니버스 실시간 현재가 — KST 시간대 분기 (KR 장중 / 마감 후 US 벨웨더)
// 라이브 데이터는 git 커밋하지 않는다 (SERVICE_RULES: 라이브 내보내기 금지)
import universe from '../scripts/config/stock_universe.json' assert { type: 'json' };

let _tossToken = null;
let _tossExpires = 0;

async function getTossToken() {
  if (_tossToken && Date.now() < _tossExpires - 60000) return _tossToken;
  const r = await fetch('https://openapi.tossinvest.com/oauth2/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: process.env.TOSS_CLIENT_ID,
      client_secret: process.env.TOSS_CLIENT_SECRET,
    }),
  });
  const d = await r.json();
  _tossToken = d.access_token;
  _tossExpires = Date.now() + (d.expires_in || 86400) * 1000;
  return _tossToken;
}

function krNow() {
  // UTC → KST 분 단위
  const utcMin = new Date().getUTCHours() * 60 + new Date().getUTCMinutes();
  return (utcMin + 9 * 60) % (24 * 60);
}

function phase() {
  const m = krNow();
  if (m >= 9 * 60 && m <= 15 * 60 + 30) return 'kr';        // 09:00–15:30
  // 한국 마감 후 ~ 익일 06:00 (미 장 마감 ~ KST 06:00 무렵) → US 벨웨더 라이브
  if (m > 15 * 60 + 30 || m < 6 * 60) return 'us';
  return 'none';
}

function krCodes() {
  return Object.values(universe.sectors).flatMap(s => s.stocks.map(x => x.code));
}
function usTickers() {
  const set = new Set();
  Object.values(universe.sectors).forEach(s => (s.bellwethers || []).forEach(b => set.add(b.t)));
  return [...set];
}

async function tossPrices(symbols) {
  const token = await getTossToken();
  const r = await fetch(
    'https://openapi.tossinvest.com/api/v1/prices?symbols=' + encodeURIComponent(symbols.join(',')),
    { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error(`toss prices ${r.status}`);
  const d = await r.json();
  return Array.isArray(d.result) ? d.result : (d.result?.prices || d.prices || []);
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  try {
    const ph = phase();
    if (ph === 'none') return res.status(200).json({ phase: 'none', prices: [] });
    const symbols = ph === 'kr' ? krCodes() : usTickers();
    const prices = await tossPrices(symbols);
    return res.status(200).json({ phase: ph, prices });
  } catch (e) {
    return res.status(502).json({ error: String(e), prices: [] });
  }
}
```

> **확인사항(구현 중 검증):** 토스 `/api/v1/prices` 응답 객체의 실제 키(현재가·등락률 필드명). `scripts/toss_client.py:get_prices` 응답을 한번 찍어 필드명을 맞춘다:
> `cd scripts && python3 -c "import toss_client as tc, json; print(json.dumps(tc.get_prices(['005930'])[:1], ensure_ascii=False, indent=2))"`
> 프론트(Task 8)가 읽는 필드명을 이 응답에 맞춘다.

- [ ] **Step 2: 로컬 검증 (vercel dev)**

Run: `vercel dev --listen 3000 --yes` 백그라운드 후
```bash
curl -s localhost:3000/api/stocks-live | python3 -c "import sys,json; d=json.load(sys.stdin); print('phase',d['phase'],'n',len(d['prices']))"
```
Expected: `phase kr|us|none n <개수>` (장중이면 50, 마감후면 벨웨더 수)

- [ ] **Step 3: Commit**

```bash
git add api/stocks-live.mjs
git commit -m "feat(실시간): stocks-live 서버리스 — KST 시간대 분기 토스 현재가"
```

---

## Phase 4 — 섹터 페이지 (③ 섹터 리스트, A안)

### Task 6: 섹터 페이지 템플릿

**Files:**
- Create: `scripts/templates/pages/stock_sector.html`
- 참조: `scripts/templates/base.html`, 기존 `scripts/templates/pages/briefings_index.html` (레이아웃 패턴)

- [ ] **Step 1: 템플릿 작성**

`generate_html.py`가 쓰는 템플릿 엔진(기존 페이지와 동일 방식 — Jinja2 또는 문자열 치환)을 먼저 확인:
`grep -nE "jinja|render_template|Template|format_map|\.replace\(" scripts/generate_html.py | head`

확인된 방식에 맞춰, `{{ sector_label }}`·`{{ stock_rows }}`(또는 동일 패턴) 슬롯을 가진 섹터 페이지 템플릿을 작성한다. 본문 구성: 섹터명 헤더 + 종목 카드 리스트(종목명·코드·종가·등락%·52주 고저·5일 스파크라인). 카드에 `data-code` 부여(장중 라이브 패치용). `base.html`을 확장해 GNB·에셋 경로 상속.

> 첫 줄 한국어 헤더 주석: `<!-- 섹터별 종목 리스트 정적 페이지 (검색 유입 영구 자산) -->`

- [ ] **Step 2: Commit**

```bash
git add scripts/templates/pages/stock_sector.html
git commit -m "feat(섹터): 섹터 페이지 템플릿 추가"
```

### Task 7: generate_html에 섹터 페이지 생성 추가

**Files:**
- Modify: `scripts/generate_html.py`

- [ ] **Step 1: 섹터 페이지 빌더 함수 추가**

`generate_html.py`에 추가 (기존 페이지 생성 함수들과 동일 패턴):

```python
def build_sector_pages():
    """stock_universe.json + stocks-snapshot.json으로 섹터 8페이지를 정적 생성한다."""
    import json
    from pathlib import Path
    root = Path(__file__).parent.parent
    uni = json.loads((Path(__file__).parent / "config" / "stock_universe.json").read_text(encoding="utf-8"))
    snap_path = root / "web" / "data" / "stocks-snapshot.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8")) if snap_path.exists() else {"stocks": {}}
    for key, sec in uni["sectors"].items():
        rows = []
        for s in sec["stocks"]:
            d = snap["stocks"].get(s["code"])
            if not d:
                continue   # 실측 없으면 표시 안 함 (SERVICE_RULES 0번)
            rows.append(_render_sector_stock_row(s, d))   # 템플릿 슬롯에 맞춰 구현
        html = _render_sector_page(sec["label"], key, "".join(rows))
        out = root / "web" / "stocks" / "sector" / key / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"[generate_html] 섹터 페이지 {key} → {out}")
```

`_render_sector_stock_row`·`_render_sector_page`는 Task 6 템플릿 슬롯 이름에 맞춰 구현(기존 generate_html 렌더 헬퍼와 동일 방식). main 흐름 또는 CLI 플래그(`--sectors`)에서 `build_sector_pages()` 호출.

- [ ] **Step 2: 생성 실행**

Run: `cd scripts && python3 generate_html.py --sectors` (또는 정해진 진입점)
Expected: `섹터 페이지 semicon → .../web/stocks/sector/semicon/index.html` × 8

- [ ] **Step 3: 정적 미리보기 확인**

`.claude/launch.json`에 섹터 페이지가 web 루트 하위이므로 기존 `daily30-web`(port 8788, `--directory web`) 서버로 접근:
`/stocks/sector/semicon/` 가 종목 종가·등락·52주로 렌더되는지 preview 스크린샷.

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_html.py web/stocks/sector/
git commit -m "feat(섹터): 8개 섹터 정적 페이지 생성"
```

---

## Phase 5 — 홈 대시보드 배선

> **선행 확인:** `web/stocks/index.html`이 repo에 승격되어 있어야 한다(상단 전제 참고). 없으면 사용자에게 프로토 승격 요청 후 진행.

### Task 8: 스냅샷 baseline + 라이브 폴링 배선

**Files:**
- Modify: `web/stocks/index.html` (대시보드 인라인 스크립트 또는 분리 JS)

- [ ] **Step 1: 스냅샷 fetch → 시세 렌더**

페이지 로드 시 `/data/stocks-snapshot.json`을 fetch해 거래량 영역·대표주 카드의 종가·등락·52주·스파크라인을 실측값으로 채운다(기존 일러스트 하드코딩 제거). 각 종목 DOM에 `data-code` 부여.

- [ ] **Step 2: 라이브 폴링 패치**

`/api/stocks-live` 폴링(KR 10초 / US 30초)으로 `data-code` 매칭 종목의 가격·등락을 패치. `phase==='none'`이면 폴링 스킵(스냅샷 종가 유지). 기존 `initLiveMarketPanel`의 sessionStorage 복원 패턴 재사용.

> 폴링이 읽는 가격 필드명은 Task 5 Step 1의 토스 응답 확인 결과에 맞춘다.

- [ ] **Step 3: 검증 (preview)**

`daily30-web`(8788) 또는 stocks 프리뷰에서 `/stocks/index.html` 로드 → 콘솔 에러 없는지(`preview_console_logs`), 종목 시세가 스냅샷 값으로 렌더되는지 스크린샷.

- [ ] **Step 4: Commit**

```bash
git add web/stocks/index.html
git commit -m "feat(대시보드): 스냅샷 실측 시세 + stocks-live 폴링 배선"
```

### Task 9: 섹터 칩 → 섹터 페이지 링크

**Files:**
- Modify: `web/stocks/index.html` (섹터별 보기 칩)

- [ ] **Step 1: 칩에 링크 부여**

8개 섹터 칩을 `/stocks/sector/{key}/`로 링크. key 매핑은 `stock_universe.json` 섹터 키와 일치(반도체→semicon 등).

- [ ] **Step 2: 검증**

preview에서 칩 클릭 → 해당 섹터 페이지로 이동 확인(`preview_click` 후 `preview_snapshot`).

- [ ] **Step 3: Commit**

```bash
git add web/stocks/index.html
git commit -m "feat(대시보드): 섹터 칩 → 섹터 페이지 링크"
```

---

## Phase 6 — CI 배선

### Task 10: daily_report.yml에 스냅샷·섹터 생성 스텝 추가

**Files:**
- Modify: `.github/workflows/daily_report.yml` (`kospi-close-briefing` 잡)

- [ ] **Step 1: 스텝 추가**

`kospi-close-briefing` 잡의 `generate_html` 직전(또는 직후)에 추가. 마감 후 종가 확정 시점이라 적합. 토스 시크릿은 기존 잡과 동일하게 env 주입.

```yaml
      - name: Build stocks snapshot (시세·52주)
        env:
          TOSS_CLIENT_ID: ${{ secrets.TOSS_CLIENT_ID }}
          TOSS_CLIENT_SECRET: ${{ secrets.TOSS_CLIENT_SECRET }}
        run: python3 scripts/build_stocks_snapshot.py

      - name: Generate sector pages (섹터 리스트)
        run: python3 scripts/generate_html.py --sectors
```

커밋·푸시 스텝의 `git add` 범위에 `web/data/stocks-snapshot.json`·`web/stocks/sector/`가 포함되는지 확인(기존 add 패턴이 `web/` 전체면 자동 포함).

- [ ] **Step 2: yml 문법 검증**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/daily_report.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily_report.yml
git commit -m "ci(종목 대시보드): kospi-close 잡에 스냅샷 빌드·섹터 생성 스텝 추가"
```

---

## 최종 검증 체크리스트

- [ ] `python3 scripts/test_build_stocks_snapshot.py` → 4 passed
- [ ] `python3 scripts/build_stocks_snapshot.py` → `web/data/stocks-snapshot.json` 40+종목, 삼성전자 값 실측 확인
- [ ] `/stocks/sector/semicon/` 등 8페이지 종가·52주 실측 렌더
- [ ] `/stocks/index.html` 시세 스냅샷 렌더 + 장중 폴링 패치, 콘솔 에러 없음
- [ ] 섹터 칩 클릭 → 섹터 페이지 이동
- [ ] 라이브 데이터(`/api/stocks-live` 응답)가 git에 커밋되지 않음
- [ ] 기존 브리핑 파이프라인(`fetch_data.SECTOR_FOCUS_STOCKS`) 회귀 없음

## 미해결 / 실행 중 결정

- 토스 `/api/v1/prices` 가격·등락 필드명 → Task 5에서 실응답 확인 후 프론트 필드 일치
- `generate_html.py` 템플릿 엔진 방식(Jinja2 vs 문자열 치환) → Task 6에서 확인 후 템플릿 작성
- SOXX 등 ETF 벨웨더가 토스에서 조회되는지 → 미조회 시 해당 벨웨더 생략(빈 값 표시 금지)
- 미국 장중 DST 경계로 `phase()`의 'us' 종료 시각 미세 변동 — 현재 KST 06:00 컷오프로 단순화, 필요 시 조정
