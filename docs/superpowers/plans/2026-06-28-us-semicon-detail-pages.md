# 미국 반도체 종목 경량 상세 페이지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 🌙 밤사이 미국 반도체 시황 7개 심볼(AVGO·NVDA·AMD·MU·ASML·SOXX·SMH)의 경량 상세 페이지를 `/stocks/us/{ticker}/`에 생성하고, 허브 🌙 행 클릭으로 진입하게 한다.

**Architecture:** 한국 `detail.html`·`build_stock_page`는 건드리지 않고, 미국 전용 데이터 모듈(`us_detail_data.py`)·템플릿(`us_detail.html`)·빌더(`generate_html.py`에 추가)를 신설한다. 데이터는 전부 yfinance 실측이며, 순수 계산함수는 `build_stocks_snapshot.py`의 기존 함수(`change_pct`·`wk52_high_low`·`sparkline`·`ma200`)를 재사용한다(DRY). 정적 as-of-종가 페이지로, 라이브 가격은 허브 타일이 담당한다.

**Tech Stack:** Python 3.9, yfinance, Jinja2, 기존 `build_stocks_snapshot` 순수함수, `web/assets/stocks.js`(공유 스파크라인 렌더), `web/assets/stocks.css`(공유 스타일).

---

## File Structure

- **Create** `scripts/config/us_stocks.json` — 7개 심볼 선언(ticker, name, kind, peers).
- **Create** `scripts/us_detail_data.py` — 순수 헬퍼(`fmt_usd`·`_yf_q_label`·`parse_us_financials`) + 네트워크 fetch(`fetch_us_realdata`·`fetch_us_financials`).
- **Create** `scripts/test_us_detail_data.py` — 순수 헬퍼 단위 테스트(네트워크 없음).
- **Create** `scripts/templates/stocks/us_detail.html` — 경량 Jinja2 템플릿.
- **Modify** `scripts/generate_html.py` — `build_us_stock_page`·`build_all_us_stocks`·`--us-stocks` 플래그·사이트맵 7개 URL.
- **Modify** `web/stocks/index.html` — 🌙 `ue-row`를 클릭 가능한 링크로(DRAM 제외).

---

## Task 1: 미국 종목 config 생성

**Files:**
- Create: `scripts/config/us_stocks.json`

- [ ] **Step 1: config 파일 작성**

```json
[
  { "ticker": "AVGO", "name": "브로드컴", "kind": "stock", "peers": ["NVDA", "AMD"] },
  { "ticker": "NVDA", "name": "엔비디아", "kind": "stock", "peers": ["AMD", "AVGO"] },
  { "ticker": "AMD",  "name": "AMD",     "kind": "stock", "peers": ["NVDA", "AVGO"] },
  { "ticker": "MU",   "name": "마이크론", "kind": "stock", "peers": ["NVDA", "ASML"] },
  { "ticker": "ASML", "name": "ASML",    "kind": "stock", "peers": ["MU", "NVDA"] },
  { "ticker": "SOXX", "name": "반도체 ETF", "kind": "etf", "peers": ["SMH", "NVDA"] },
  { "ticker": "SMH",  "name": "반도체 ETF", "kind": "etf", "peers": ["SOXX", "NVDA"] }
]
```

- [ ] **Step 2: JSON 유효성 확인**

Run: `python3 -c "import json; print(len(json.load(open('scripts/config/us_stocks.json'))))"`
Expected: `7`

- [ ] **Step 3: Commit**

```bash
git add scripts/config/us_stocks.json
git commit -m "feat(종목): 미국 반도체 상세 페이지 대상 종목 config 추가"
```

---

## Task 2: `fmt_usd` 순수함수 (TDD)

**Files:**
- Create: `scripts/us_detail_data.py`
- Test: `scripts/test_us_detail_data.py`

- [ ] **Step 1: 실패 테스트 작성**

`scripts/test_us_detail_data.py`:

```python
# us_detail_data 순수 계산함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 scripts/test_us_detail_data.py"""
import us_detail_data as u


def test_fmt_usd():
    assert u.fmt_usd(81_615_000_000.0) == "$81.6B"
    assert u.fmt_usd(1_230_000_000.0) == "$1.23B"
    assert u.fmt_usd(543_000_000.0) == "$543M"
    assert u.fmt_usd(-1_200_000_000.0) == "−$1.2B"
    assert u.fmt_usd(None) == ""
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd scripts && python3 -m pytest test_us_detail_data.py::test_fmt_usd -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'us_detail_data'`)

- [ ] **Step 3: 최소 구현**

`scripts/us_detail_data.py`:

```python
# 미국 종목 상세 페이지용 yfinance 실측 + 순수 포맷 헬퍼
"""미국 반도체 종목(AVGO·NVDA·AMD·MU·ASML·SOXX·SMH) 상세 페이지 데이터.

순수함수(fmt_usd·_yf_q_label·parse_us_financials)는 네트워크 없이 테스트 가능.
시세·52주·MA 계산은 build_stocks_snapshot 의 검증된 순수함수를 재사용한다.
"""
import sys

import build_stocks_snapshot as m


def fmt_usd(v):
    """USD 실수 → '$81.6B'/'$1.23B'/'$543M'/'−$1.2B'. None→''."""
    if v is None:
        return ""
    sign = "−" if v < 0 else ""
    a = abs(v)
    if a >= 1e9:
        return f"{sign}${a/1e9:.1f}B" if a / 1e9 >= 10 else f"{sign}${a/1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a/1e6:.0f}M"
    return f"{sign}${a:,.0f}"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd scripts && python3 -m pytest test_us_detail_data.py::test_fmt_usd -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/us_detail_data.py scripts/test_us_detail_data.py
git commit -m "feat(종목): 미국 상세 USD 포맷 헬퍼 fmt_usd"
```

---

## Task 3: `_yf_q_label` 순수함수 (TDD)

**Files:**
- Modify: `scripts/us_detail_data.py`
- Test: `scripts/test_us_detail_data.py`

- [ ] **Step 1: 실패 테스트 추가**

`scripts/test_us_detail_data.py`에 추가:

```python
def test_yf_q_label():
    assert u._yf_q_label("2026-04-30") == "26Q2"
    assert u._yf_q_label("2025-10-31") == "25Q4"
    assert u._yf_q_label("2026-01-31") == "26Q1"
    assert u._yf_q_label("bad") == "bad"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd scripts && python3 -m pytest test_us_detail_data.py::test_yf_q_label -v`
Expected: FAIL (`AttributeError: module 'us_detail_data' has no attribute '_yf_q_label'`)

- [ ] **Step 3: 최소 구현**

`scripts/us_detail_data.py`의 `fmt_usd` 아래에 추가:

```python
def _yf_q_label(date_str):
    """'2026-04-30' → '26Q2'. 월 기준 분기 라벨. 파싱 실패 시 입력 그대로."""
    try:
        yy = date_str[2:4]
        mm = int(date_str[5:7])
        q = (mm - 1) // 3 + 1
        return f"{yy}Q{q}"
    except (ValueError, IndexError, TypeError):
        return date_str
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd scripts && python3 -m pytest test_us_detail_data.py::test_yf_q_label -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/us_detail_data.py scripts/test_us_detail_data.py
git commit -m "feat(종목): 분기 라벨 헬퍼 _yf_q_label"
```

---

## Task 4: `parse_us_financials` 순수함수 (TDD)

**Files:**
- Modify: `scripts/us_detail_data.py`
- Test: `scripts/test_us_detail_data.py`

- [ ] **Step 1: 실패 테스트 추가**

`scripts/test_us_detail_data.py`에 추가:

```python
def test_parse_us_financials():
    # columns: 최신순 (date_str, {rev, op})
    cols = [
        ("2026-04-30", {"rev": 81_600_000_000.0, "op": 53_500_000_000.0}),
        ("2026-01-31", {"rev": 39_300_000_000.0, "op": 24_000_000_000.0}),
        ("2025-10-31", {"rev": None, "op": None}),   # 둘 다 None → 제외
    ]
    out = u.parse_us_financials(cols)
    # 오래된→최신 정렬, None 행 제외
    assert [r["q"] for r in out] == ["26Q1", "26Q2"]
    assert out[-1]["rev"] == 81_600_000_000.0
    assert out[-1]["op"] == 53_500_000_000.0
    assert out[0]["est"] is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd scripts && python3 -m pytest test_us_detail_data.py::test_parse_us_financials -v`
Expected: FAIL (`AttributeError: ... 'parse_us_financials'`)

- [ ] **Step 3: 최소 구현**

`scripts/us_detail_data.py`의 `_yf_q_label` 아래에 추가:

```python
def parse_us_financials(columns, n=5):
    """yfinance 분기실적 컬럼 → 템플릿용 리스트.

    columns: [(date_str, {'rev':float|None, 'op':float|None}), ...] 최신순.
    반환: 최근 n분기를 오래된→최신으로 [{q, rev, op, est:False}]. 둘 다 None이면 제외.
    """
    out = []
    for date_str, vals in columns[:n]:
        rev, op = vals.get("rev"), vals.get("op")
        if rev is None and op is None:
            continue
        out.append({"q": _yf_q_label(date_str), "rev": rev, "op": op, "est": False})
    out.reverse()
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd scripts && python3 -m pytest test_us_detail_data.py -v`
Expected: 3 passed (fmt_usd, yf_q_label, parse_us_financials)

- [ ] **Step 5: Commit**

```bash
git add scripts/us_detail_data.py scripts/test_us_detail_data.py
git commit -m "feat(종목): yfinance 분기실적 파서 parse_us_financials"
```

---

## Task 5: yfinance 네트워크 fetch 함수

**Files:**
- Modify: `scripts/us_detail_data.py`

네트워크 의존이라 단위 테스트 대신 수동 실행으로 검증한다.

- [ ] **Step 1: `fetch_us_realdata` 구현**

`scripts/us_detail_data.py` 끝에 추가:

```python
def fetch_us_realdata(ticker):
    """yfinance 일봉 → 시세·등락률·20일 스파크라인·52주·MA20/200. 실패 시 {'error':..,'price':None}.

    등락률은 직전 완료 세션 종가 기준(close[-1] vs close[-2]) — 한국 페이지와 동일 원칙.
    """
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="300d").dropna(subset=["Close"])
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "price": None}
    closes = [float(x) for x in hist["Close"].tolist()]
    if len(closes) < 2:
        return {"error": "데이터 부족", "price": None}
    price = closes[-1]
    hi, lo = m.wk52_high_low(closes)
    ma20 = round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None
    ma200v = m.ma200(closes)
    idx = hist.index
    return {
        "error": None,
        "price": round(price, 2),
        "change_pct": m.change_pct(closes),
        "sparkline": [round(c, 2) for c in m.sparkline(closes, 20)],
        "sparkline_dates": [d.strftime("%-m/%-d") for d in idx[-20:]],
        "week52_low": round(lo, 2),
        "week52_high": round(hi, 2),
        "week52_pos_pct": round((price - lo) / (hi - lo) * 100, 1) if hi > lo else 0,
        "ma20_dist_pct": round((price / ma20 - 1) * 100, 1) if ma20 else None,
        "ma200_dist_pct": round((price / ma200v - 1) * 100, 1) if ma200v else None,
        "asof": idx[-1].strftime("%Y-%m-%d"),
    }


def fetch_us_financials(ticker):
    """yfinance quarterly_financials → parse_us_financials 입력으로 변환 후 파싱. 실패 시 []."""
    try:
        import yfinance as yf
        qf = yf.Ticker(ticker).quarterly_financials
    except Exception as e:  # noqa: BLE001
        print(f"[us_detail] {ticker} 분기실적 실패: {e}", file=sys.stderr)
        return []
    if qf is None or qf.empty:
        return []

    def _cell(field, col):
        try:
            v = qf.loc[field, col]
        except KeyError:
            return None
        return None if v != v else float(v)  # NaN → None

    columns = []
    for col in qf.columns:
        rev = _cell("Total Revenue", col)
        op = _cell("Operating Income", col)
        if op is None:
            op = _cell("Total Operating Income As Reported", col)
        columns.append((col.strftime("%Y-%m-%d"), {"rev": rev, "op": op}))
    return parse_us_financials(columns)
```

- [ ] **Step 2: 수동 실행 검증**

Run:
```bash
cd scripts && python3 -c "
import us_detail_data as u
rd = u.fetch_us_realdata('NVDA')
print('price', rd['price'], 'chg', rd['change_pct'], 'asof', rd['asof'])
print('spark', len(rd['sparkline']), 'ma200', rd['ma200_dist_pct'])
fin = u.fetch_us_financials('NVDA')
print('fin quarters', [q['q'] for q in fin])
print('last rev', fin[-1]['rev'] if fin else None)
"
```
Expected: price/change_pct 숫자, asof 날짜(YYYY-MM-DD), spark 20개, fin quarters 4~5개, last rev 수십억대 정수.

- [ ] **Step 3: 회귀 — 순수 테스트 재확인**

Run: `cd scripts && python3 -m pytest test_us_detail_data.py -v`
Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
git add scripts/us_detail_data.py
git commit -m "feat(종목): 미국 종목 yfinance 시세·분기실적 fetch"
```

---

## Task 6: 경량 상세 템플릿 `us_detail.html`

**Files:**
- Create: `scripts/templates/stocks/us_detail.html`

- [ ] **Step 1: 템플릿 작성**

`scripts/templates/stocks/us_detail.html` 전체:

```html
<!-- 미국 반도체 종목 경량 상세 페이지 Jinja2 템플릿 (US lite) -->
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-PW9RHHFPM4"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-PW9RHHFPM4');</script>
<title>{{ stock.name }}({{ stock.ticker }}) · 미국 반도체 — 더블샷</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@latest/dist/web/static/pretendard.min.css">
<link rel="stylesheet" href="/assets/stocks.css?v=2">
<script defer src="/assets/stocks.js"></script>
</head>
<body>
<nav class="gnb">
  <div class="gnb__in">
    <a class="gnb__logo" href="/stocks/">종목</a>
    <div class="gnb__subs">
      <a class="gnb__sub" href="https://doubleshot.space/">Double-Shot</a>
      <div class="gnb__divider"></div>
      <a class="gnb__sub" href="/stocks/income-designer/">월배당 설계기</a>
    </div>
  </div>
</nav>

<div class="page-wrap">
<div class="screen on" id="detail">
  <div class="crumb">
    <a href="/stocks/">홈</a> › <a href="/stocks/">종목</a> › <span style="color:var(--muted)">미국 반도체</span> › <span style="color:var(--ink)">{{ stock.name }}</span>
  </div>
  <div class="grid">
    <!-- ===== 좌측 메인 ===== -->
    <div class="dbox">

      <!-- 헤더 카드: 종목명 + USD 시세 + 20일 스파크라인 -->
      <div class="hero2" id="hero-stock" style="position:relative;">
        <div class="top">
          <div>
            <div class="hn">{{ stock.name }} <span class="chip">🇺🇸 {{ stock.ticker }}</span></div>
            <div class="meta">미국 반도체 · {{ generated_label }}</div>
          </div>
          <div style="text-align:right">
            <div class="px num">${{ "%.2f"|format(rd.price) }}</div>
            {% if rd.change_pct > 0 %}
            <div class="cg num" style="color:var(--up)">▲ +{{ "%.2f"|format(rd.change_pct) }}%</div>
            {% elif rd.change_pct < 0 %}
            <div class="cg num" style="color:var(--dn)">▼ {{ "%.2f"|format(rd.change_pct) }}%</div>
            {% else %}
            <div class="cg num" style="color:var(--muted)">— 0.00%</div>
            {% endif %}
          </div>
        </div>
        <div class="ctabs">
          <a class="on" id="ctab-spark">20일 종가</a>
        </div>
        <div class="cpane" id="pane-spark">
          <div class="spark-header" id="spark-main"
               data-spark="{{ rd.sparkline | join(',') }}"
               data-dates="{{ rd.sparkline_dates | join(',') }}"
               style="cursor:crosshair;position:relative;"></div>
        </div>
        <div id="spark-tip" style="display:none;position:absolute;pointer-events:none;font-size:11px;font-weight:700;background:var(--ink);color:#fff;padding:4px 8px;border-radius:5px;white-space:nowrap;z-index:5;transform:translateX(-50%);"></div>
      </div>

      <!-- 실측 핵심 지표 -->
      <div class="np">
        <div class="np__h">
          <span class="np__t">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M5 21V8l5-4 5 4v13M9 9h2m-2 4h2m4-4h2m-2 4h2"/></svg>
            실측 핵심 지표
          </span>
          <span class="np__s">{{ generated_label }} 기준</span>
        </div>

        {% if rd.week52_low %}
        <div class="mx">
          <div class="mx-h"><span>52주 범위</span><span>현재가 <b style="color:var(--up)">{{ rd.week52_pos_pct }}%</b> 지점</span></div>
          <div class="w52"><div class="fill" style="width:{{ rd.week52_pos_pct }}%"></div><div class="now" style="left:{{ rd.week52_pos_pct }}%"></div></div>
          <div class="w52-lb"><span>최저 ${{ "%.2f"|format(rd.week52_low) }}</span><span>최고 ${{ "%.2f"|format(rd.week52_high) }}</span></div>
        </div>
        {% endif %}

        {% if rd.ma20_dist_pct is not none or rd.ma200_dist_pct is not none %}
        <div class="duo">
          {% if rd.ma20_dist_pct is not none %}
          <div class="cell">
            <div class="l">20일선 대비</div>
            <div class="v" style="color:{{ 'var(--up)' if rd.ma20_dist_pct >= 0 else 'var(--dn)' }}">{{ '+' if rd.ma20_dist_pct >= 0 else '' }}{{ "%.1f"|format(rd.ma20_dist_pct) }}%</div>
            <div class="sub">{{ '단기 추세 위' if rd.ma20_dist_pct >= 0 else '단기 추세 아래' }}</div>
          </div>
          {% endif %}
          {% if rd.ma200_dist_pct is not none %}
          <div class="cell">
            <div class="l">200일선 대비</div>
            <div class="v" style="color:{{ 'var(--up)' if rd.ma200_dist_pct >= 0 else 'var(--dn)' }}">{{ '+' if rd.ma200_dist_pct >= 0 else '' }}{{ "%.1f"|format(rd.ma200_dist_pct) }}%</div>
            <div class="sub">{{ '장기 추세 위' if rd.ma200_dist_pct >= 0 else '장기 추세 아래' }}</div>
          </div>
          {% endif %}
        </div>
        {% endif %}
      </div>

      <!-- 분기 실적 (매출·영업이익, USD) -->
      {% if financials %}
      {% set rev_max = (financials | map(attribute='rev') | reject('none') | list | max) or 1 %}
      <div class="np">
        <div class="np__h">
          <span class="np__t">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M5 21V8l5-4 5 4v13M9 9h2m-2 4h2m4-4h2m-2 4h2"/></svg>
            분기 실적
          </span>
          <span class="np__s">매출액 · 분기 기준 · USD</span>
        </div>
        <div style="padding:16px 16px 12px;">
          <div class="fin-chart">
            {% for q in financials %}
            <div class="fin-col">
              <span class="fin-cap">{{ q.rev | usd }}</span>
              <div class="fin-bar actual" style="height:{{ ((q.rev or 0) / rev_max * 150) | round | int }}px"></div>
            </div>
            {% endfor %}
          </div>
          <div class="fin-xrow">
            {% for q in financials %}
            <span class="fin-x">{{ q.q }}<br><span style="color:{{ 'var(--up)' if (q.op or 0) >= 0 else 'var(--dn)' }}">영업 {% if q.op is not none %}{{ q.op | usd }}{% else %}—{% endif %}</span></span>
            {% endfor %}
          </div>
        </div>
      </div>
      {% endif %}

    </div>

    <!-- ===== 우측 사이드바 ===== -->
    <div>
      <!-- 같은 섹터 (미국 반도체) -->
      <div class="panel"><div class="panel__h">같은 섹터 · 미국 반도체</div>
        {% for p in peers %}
        <a class="srow" href="/stocks/us/{{ p.ticker | lower }}/">
          <span class="n2">{{ p.name }} <small class="num">{{ p.ticker }}</small></span>
          {% if p.change_pct is not none %}
            {% if p.change_pct > 0 %}<span class="c up num">+{{ "%.2f"|format(p.change_pct) }}%</span>
            {% elif p.change_pct < 0 %}<span class="c dn num">{{ "%.2f"|format(p.change_pct) }}%</span>
            {% else %}<span class="c num" style="color:var(--muted)">0.00%</span>{% endif %}
          {% else %}<span class="c num" style="color:var(--muted)">—</span>{% endif %}
        </a>
        {% endfor %}
      </div>

      <!-- 더블샷 브리핑 적중률 -->
      <div class="np">
        <div class="np__h">
          <span class="np__t">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/></svg>
            더블샷 브리핑 적중률
          </span>
        </div>
        <div class="acc-grid">
          <div class="acc-cell"><div class="l">코스피 방향</div><div class="v">{{ acc.kospi }}%</div></div>
          <div class="acc-cell"><div class="l">미국 방향</div><div class="v">{{ acc.us }}%</div></div>
        </div>
        <a class="acc-cta" href="https://doubleshot.space/briefings">매일 아침·저녁 AI 브리핑 받아보기 →</a>
      </div>
    </div>
  </div>

  <div class="disc" style="line-height:1.7;">
    <p style="margin:0 0 6px;"><b>📅 업데이트 기준</b></p>
    <p style="margin:0 0 4px;">· <b>시세·이동평균·52주</b> — 미국 장 마감 후 갱신. 직전 거래일({{ generated_label }}) 종가 기준 yfinance 실측이에요.</p>
    <p style="margin:0 0 4px;">· <b>분기 실적</b> — yfinance 분기 재무 기준이며 단위는 USD예요.</p>
    <p style="margin:6px 0 0;">모든 수치는 실측이며 투자 판단 참고용이에요. 실시간 시세는 <a href="/stocks/">종목 홈</a>의 밤사이 미국 반도체 시황에서 확인하세요.</p>
  </div>
</div>
</div>

<script>
// 스파크라인 마우스오버 → 날짜·종가 툴팁 (USD)
(function(){
  var wrap=document.getElementById('spark-main');
  var tip=document.getElementById('spark-tip');
  var hero=document.getElementById('hero-stock');
  if(!wrap||!tip||!hero) return;
  var vals=(wrap.getAttribute('data-spark')||'').split(',').map(Number).filter(Boolean);
  var dates=(wrap.getAttribute('data-dates')||'').split(',');
  var n=vals.length; if(!n) return;
  wrap.addEventListener('mousemove',function(e){
    var rect=wrap.getBoundingClientRect();
    var heroRect=hero.getBoundingClientRect();
    var i=Math.round((e.clientX-rect.left)/rect.width*(n-1));
    i=Math.max(0,Math.min(n-1,i));
    tip.textContent=(dates[i]||'')+' · $'+vals[i].toLocaleString();
    tip.style.display='block';
    tip.style.left=(e.clientX-heroRect.left)+'px';
    tip.style.top=(e.clientY-heroRect.top-32)+'px';
  });
  wrap.addEventListener('mouseleave',function(){tip.style.display='none';});
})();
</script>
</body>
</html>
```

- [ ] **Step 2: 템플릿 문법 검증**

Run:
```bash
cd scripts && python3 -c "
from jinja2 import Environment, FileSystemLoader
env=Environment(loader=FileSystemLoader('templates'))
env.get_template('stocks/us_detail.html')
print('template OK')
"
```
Expected: `template OK` (문법 에러 없음). `lower` 필터는 Jinja 내장이라 통과.

- [ ] **Step 3: Commit**

```bash
git add scripts/templates/stocks/us_detail.html
git commit -m "feat(종목): 미국 반도체 경량 상세 템플릿 us_detail.html"
```

---

## Task 7: 빌더 + `--us-stocks` 플래그

**Files:**
- Modify: `scripts/generate_html.py`

- [ ] **Step 1: import + 상수 추가**

`scripts/generate_html.py` 상단의 import 영역(`import build_stocks_snapshot`가 있으면 그 근처, 없으면 다른 로컬 모듈 import 아래)에 추가:

```python
import us_detail_data as ud
```

그리고 `CONFIG_DIR` 정의(38번 줄 근처) 아래에 추가:

```python
US_STOCKS_PATH = CONFIG_DIR / "us_stocks.json"
```

- [ ] **Step 2: 빌더 함수 추가**

`build_all_stocks` 함수 정의(1185번 줄) **바로 앞**에 추가:

```python
def build_us_stock_page(stock, peers, env):
    """미국 종목 1개의 경량 상세 페이지를 생성·기록하고 출력 경로를 반환한다."""
    rd = ud.fetch_us_realdata(stock["ticker"])
    if rd.get("error") or rd.get("price") is None:
        raise RuntimeError(f"{stock['ticker']} 실측 실패: {rd.get('error')}")
    financials = ud.fetch_us_financials(stock["ticker"]) if stock.get("kind") == "stock" else []
    env.filters["usd"] = ud.fmt_usd
    tmpl = env.get_template("stocks/us_detail.html")
    asof = rd.get("asof") or datetime.now(KST).strftime("%Y-%m-%d")
    generated_label = f"{asof[5:7]}-{asof[8:10]} 종가"
    html = tmpl.render(
        stock=stock,
        rd=rd,
        financials=financials,
        peers=peers,
        generated_label=generated_label,
        acc=_briefing_accuracy(),
    )
    tk = stock["ticker"].lower()
    out_dir = WEB_DIR / "stocks" / "us" / tk
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    return f"stocks/us/{tk}/index.html"


def build_all_us_stocks():
    """us_stocks.json 전체를 순회 생성. peer 등락률은 실측에서 채운다(캐시 재사용, fail-fast)."""
    stocks = load_json(US_STOCKS_PATH)
    name_map = {s["ticker"]: s["name"] for s in stocks}
    rd_cache = {}

    def _peer_change(tk):
        if tk not in rd_cache:
            rd_cache[tk] = ud.fetch_us_realdata(tk)
        return rd_cache[tk].get("change_pct")

    results = []
    for s in stocks:
        peers = [
            {"ticker": pt, "name": name_map.get(pt, pt), "change_pct": _peer_change(pt)}
            for pt in s.get("peers", [])
        ]
        results.append(build_us_stock_page(s, peers, make_env()))
    return results
```

- [ ] **Step 3: CLI 플래그 추가**

`parser.add_argument("--stocks", ...)`(1455번 줄 근처) 바로 아래에 추가:

```python
    parser.add_argument("--us-stocks", dest="us_stocks", action="store_true",
                        help="미국 반도체 종목 경량 상세 페이지 생성")
```

그리고 `if args.stocks:` 블록(1463~1467번 줄) **바로 아래**에 추가:

```python
    if args.us_stocks:
        for path in build_all_us_stocks():
            print(f"생성: {path}")
        write_sitemap_xml()
        return
```

- [ ] **Step 4: 빌드 실행 검증**

Run: `cd scripts && python3 generate_html.py --us-stocks`
Expected: `생성: stocks/us/avgo/index.html` … 7줄 출력, 에러 없음.

- [ ] **Step 5: 생성 결과 확인**

Run: `ls web/stocks/us/*/index.html | wc -l`
Expected: `7`

Run: `grep -c "분기 실적" web/stocks/us/nvda/index.html web/stocks/us/soxx/index.html`
Expected: `web/stocks/us/nvda/index.html:1` (단일종목 있음), `web/stocks/us/soxx/index.html:0` (ETF 없음)

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_html.py web/stocks/us
git commit -m "feat(종목): 미국 반도체 상세 빌더 + --us-stocks 플래그"
```

---

## Task 8: 사이트맵에 미국 페이지 추가

**Files:**
- Modify: `scripts/generate_html.py:1241-1247` (한국 종목 사이트맵 루프 직후)

- [ ] **Step 1: 사이트맵 루프 추가**

`write_sitemap_xml`의 한국 종목 루프(`for s in load_json(CONFIG_DIR / "stocks.json"):` … `})` 블록, 1241~1247번 줄) **바로 아래**에 추가:

```python
    # 생성된 미국 반도체 상세 페이지만 포함
    for s in load_json(US_STOCKS_PATH):
        tk = s["ticker"].lower()
        if (WEB_DIR / "stocks" / "us" / tk / "index.html").exists():
            urls.append({
                "loc": f"{BASE}/stocks/us/{tk}/",
                "changefreq": "weekly",
                "priority": "0.6",
            })
```

- [ ] **Step 2: 사이트맵 재생성·검증**

Run: `cd scripts && python3 generate_html.py --us-stocks && grep -c "stocks/us/" ../web/sitemap.xml`
Expected: `7`

- [ ] **Step 3: Commit**

```bash
git add scripts/generate_html.py web/sitemap.xml
git commit -m "feat(종목): 사이트맵에 미국 반도체 상세 7개 URL 추가"
```

---

## Task 9: 허브 🌙 행 클릭 → 상세 진입

**Files:**
- Modify: `web/stocks/index.html:1077-1081` (`render()` 함수의 `ue-row` 생성)

- [ ] **Step 1: 행을 링크로 변경**

`web/stocks/index.html`의 `render()` 함수에서 아래 블록을(1077~1081번 줄):

```javascript
    gridEl.innerHTML=TICKERS.map(function(t){
      var d=dataBySym[t.sym]||{};
      return '<div class="ue-row"><span class="nm">'+t.nm+' <span class="tk">'+t.tk+'</span>'+(t.lead?' <span class="lead">선행</span>':'')+'</span>'
        +'<span class="px" data-usd="'+(d.price!=null?d.price:'')+'">'+fmtPx(d.price)+'</span>'+cgHtml(d.changePct)+'</div>';
    }).join('');
```

다음으로 교체한다(DRAM 선행행은 비링크, 나머지는 `/stocks/us/{ticker}/` 링크):

```javascript
    gridEl.innerHTML=TICKERS.map(function(t){
      var d=dataBySym[t.sym]||{};
      var inner='<span class="nm">'+t.nm+' <span class="tk">'+t.tk+'</span>'+(t.lead?' <span class="lead">선행</span>':'')+'</span>'
        +'<span class="px" data-usd="'+(d.price!=null?d.price:'')+'">'+fmtPx(d.price)+'</span>'+cgHtml(d.changePct);
      if(t.lead) return '<div class="ue-row">'+inner+'</div>';
      return '<a class="ue-row ue-row--link" href="/stocks/us/'+t.tk.toLowerCase()+'/">'+inner+'<svg class="ue-go" width="14" height="14" viewBox="0 0 20 20" fill="none"><path d="M8 5l5 5-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></a>';
    }).join('');
```

- [ ] **Step 2: 링크 행 스타일 추가**

`web/stocks/index.html`의 `#us-evening .ue-row` 정의(1022번 줄 근처) **바로 아래**에 추가:

```css
#us-evening a.ue-row--link{text-decoration:none;cursor:pointer;color:inherit;}
#us-evening a.ue-row--link:hover{background:#F8FAFF;}
#us-evening .ue-go{color:#94A3B8;flex:none;margin-left:6px;opacity:0;transition:opacity .15s;}
#us-evening a.ue-row--link:hover .ue-go{opacity:1;}
```

- [ ] **Step 3: 미리보기 검증 (진입 동선)**

미리보기 서버에서 `/stocks/`를 열고:
- 🌙 섹션 NVDA 행에 호버 시 화살표가 나타나고 배경이 바뀐다.
- NVDA 행 클릭 → `/stocks/us/nvda/`로 이동, 페이지가 렌더된다.
- DRAM(메모리·HBM 선행) 행은 클릭해도 이동하지 않는다(`<div>`라 링크 아님).

- [ ] **Step 4: Commit**

```bash
git add web/stocks/index.html
git commit -m "feat(종목): 🌙 미국 반도체 행 클릭 → 상세 페이지 진입"
```

---

## Task 10: 엔드투엔드 검증

**Files:** (없음 — 통합 확인)

- [ ] **Step 1: 전체 순수 테스트**

Run: `cd scripts && python3 -m pytest test_us_detail_data.py -v`
Expected: 3 passed

- [ ] **Step 2: 빌드 재실행**

Run: `cd scripts && python3 generate_html.py --us-stocks`
Expected: 7줄 `생성:` 출력, 에러 없음

- [ ] **Step 3: 미리보기로 7개 페이지 렌더 확인**

미리보기에서 다음 URL을 순회하며 확인:
- `/stocks/us/nvda/` — 헤더에 `$` 가격, 20일 종가 스파크라인, 52주 범위, 분기 실적(막대) 표시
- `/stocks/us/soxx/` — 분기 실적 섹션 **없음**, 시세·52주·peers는 표시
- 사이드바 peers 클릭 → 다른 미국 페이지로 이동

콘솔 에러 없음 확인(preview_console_logs).

- [ ] **Step 4: 생략 섹션 부재 확인**

Run:
```bash
grep -l "수급 동향\|외국인 보유율\|증권사 목표주가\|트랙레코드\|오늘의 시그널" web/stocks/us/*/index.html || echo "생략 섹션 없음 OK"
```
Expected: `생략 섹션 없음 OK`

- [ ] **Step 5: 최종 커밋(생성물 갱신분이 있으면)**

```bash
git add web/stocks/us web/sitemap.xml
git commit -m "chore(종목): 미국 반도체 상세 페이지 생성물 갱신" || echo "변경 없음"
```

---

## Self-Review 체크

- **Spec coverage:** 범위(7심볼·Task1) · URL(/stocks/us/{ticker}/·Task7) · yfinance 데이터(Task5) · 5개 섹션 + 생략(Task6) · 분기실적 USD(Task4·6) · 진입동선(Task9) · 라우팅(filesystem, Task10 미리보기 검증) · 사이트맵(Task8) — 전부 태스크에 매핑됨.
- **라우팅 주의:** 기존 `/stocks/{code}/`가 `{ "handle": "filesystem" }`로 해소되므로 `/stocks/us/{tk}/`도 자동 해소될 것으로 본다. Task10 Step3 미리보기에서 실패하면 `vercel.json` routes에 `{ "src": "^/stocks/us/([a-z]+)/?$", "dest": "/stocks/us/$1/index.html" }`를 `{ "handle": "filesystem" }` 앞에 추가하는 보정 태스크를 수행한다.
- **타입 일관성:** `fetch_us_realdata`가 반환하는 키(price·change_pct·sparkline·sparkline_dates·week52_low/high/pos_pct·ma20_dist_pct·ma200_dist_pct·asof)를 템플릿이 동일 이름으로 참조. peers는 `{ticker,name,change_pct}`로 생성·소비 일치. financials 항목은 `{q,rev,op,est}`로 파서·템플릿 일치.
- **DRY:** 시세·52주·MA·스파크라인 계산은 `build_stocks_snapshot`의 `change_pct`·`wk52_high_low`·`sparkline`·`ma200` 재사용.
- **푸시 정책:** 커밋만, 푸시·배포는 사용자 지시 시에만(메모리 규칙).
