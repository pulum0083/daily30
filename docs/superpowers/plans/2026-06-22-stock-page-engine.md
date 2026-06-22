# 종목 상세 페이지 엔진 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 손으로 작성한 `/stocks/{code}/` 프로토 HTML을, 종목 메타 + 빌드 타임 실측 데이터로 자동 생성하는 config-driven 엔진으로 전환한다.

**Architecture:** 기존 `scripts/generate_html.py`(Jinja2 config-driven 브리핑 생성기)에 종목 상세 생성 경로를 추가한다. 종목 메타는 `scripts/config/stocks.json`에 선언하고, 시세·sparkline·52주는 `validate_analysis._fetch_kospi_realdata()`(토스→네이버 폴백)로 빌드 타임에 주입한다. 목표가·분기실적 등 실측 소스가 없는 영역은 기존 프로토처럼 일러스트레이션 배너로 정직하게 표기한다. 생성물은 클린 URL `/stocks/{code}/index.html`로 떨어진다.

**Tech Stack:** Python 3, Jinja2 3.1, pytest 8.4, 기존 `toss_client.py` / `validate_analysis.py` 재사용.

**확정된 결정 (2026-06-22):**
- 생성 방식: `generate_html.py` 확장 (별도 스크립트 아님)
- 데이터 깊이: 빌드 타임 실측 주입만 (런타임 LIVE 폴링은 후속 단계)
- 초기 범위: 005930(삼성전자)·000660(SK하이닉스)·005380(현대차) 3종

---

## File Structure

**신규 생성:**
- `scripts/config/stocks.json` — 종목 메타 목록(code/name/sector/market/peers). 커밋됨.
- `scripts/config/stock.json` — 종목 페이지 섹션·템플릿 선언 (kospi.json과 동형).
- `scripts/templates/stocks/detail.html` — 종목 상세 Jinja2 템플릿 (005930 프로토에서 추출).
- `web/assets/stocks.css` — 종목 페이지 공유 스타일 (인라인 추출).
- `web/assets/stocks.js` — sparkline 렌더·기간탭 토글 (인라인 추출).
- `scripts/test_build_stock_pages.py` — 생성기 단위·통합 테스트.

**수정:**
- `scripts/generate_html.py` — 종목 생성 함수 + `--stocks` CLI 경로 + 사이트맵에 종목 URL 추가.

**폐기 (Task 6):**
- `web/stocks/stock.html` — 쿼리파라미터 단일 템플릿. 클린 URL 디렉토리 방식으로 일원화.

**소스 오브 트루스:** `web/stocks/005930/index.html`(현 프로토)를 디자인 기준으로 삼아 템플릿을 추출한다. 추출 후 이 파일은 생성기가 덮어쓴다.

---

## 실측 데이터 계약

`validate_analysis._fetch_kospi_realdata(code)` 반환 dict (검증 완료):

```python
{
  "price": 354000.0,
  "change_pct": -2.34,          # close[-1] vs close[-2], 실시간 장중가 아님
  "sparkline": [..20개 종가..],
  "ma20_dist_pct": 1.2, "ma20_sparkline": [..20..],   # len>=20
  "ma200_dist_pct": 5.1, "ma200_sparkline": [..20..], # len>=200
  # "error": "..."  ← 실패 시
}
```

이 dict에 **없는 것**(52주 hi/lo, 목표가, 분기실적, 수급 7일)은 Task 2에서 토스 캔들 원본으로 52주만 추가 산출하고, 나머지(목표가·분기실적)는 일러스트레이션으로 표기한다. 수급 7일은 `data/supply_history.json`에 해당 종목 데이터가 있을 때만 주입, 없으면 일러스트.

---

### Task 1: 종목 메타 + 섹션 config 선언

**Files:**
- Create: `scripts/config/stocks.json`
- Create: `scripts/config/stock.json`
- Test: `scripts/test_build_stock_pages.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_build_stock_pages.py`:

```python
# 종목 상세 페이지 생성기 테스트
import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "config"


def test_stocks_config_schema():
    stocks = json.loads((CONFIG / "stocks.json").read_text(encoding="utf-8"))
    assert isinstance(stocks, list) and len(stocks) >= 3
    codes = {s["code"] for s in stocks}
    assert {"005930", "000660", "005380"} <= codes
    for s in stocks:
        assert len(s["code"]) == 6
        for key in ("name", "sector", "market", "peers"):
            assert key in s, f"{s['code']} missing {key}"
        assert isinstance(s["peers"], list)
        for p in s["peers"]:
            assert len(p["code"]) == 6 and p["name"], f"{s['code']} bad peer {p}"


def test_stock_section_config():
    cfg = json.loads((CONFIG / "stock.json").read_text(encoding="utf-8"))
    assert cfg["template"] == "stocks/detail.html"
    assert "sections" in cfg and "price_chart" in cfg["sections"]
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_build_stock_pages.py -v`
Expected: FAIL — `FileNotFoundError: .../config/stocks.json`

- [ ] **Step 3: config 파일 작성**

`scripts/config/stocks.json` — **peer는 `{code, name}` 객체**로 자기 이름을 들고 다닌다. peer는 표시용 참조일 뿐 top-level 등록 대상이 아니다(생성 범위 3종 유지, peer 이름은 레지스트리 조회 없이 해결).

```json
[
  { "code": "005930", "name": "삼성전자",   "sector": "반도체", "market": "KOSPI",
    "peers": [{ "code": "000660", "name": "SK하이닉스" }, { "code": "042700", "name": "한미반도체" }] },
  { "code": "000660", "name": "SK하이닉스", "sector": "반도체", "market": "KOSPI",
    "peers": [{ "code": "005930", "name": "삼성전자" }, { "code": "042700", "name": "한미반도체" }] },
  { "code": "005380", "name": "현대차",     "sector": "자동차", "market": "KOSPI",
    "peers": [{ "code": "000270", "name": "기아" }, { "code": "012330", "name": "현대모비스" }] }
]
```

`scripts/config/stock.json`:

```json
{
  "type": "stock",
  "template": "stocks/detail.html",
  "url_prefix": "stocks",
  "sections": [
    "price_chart",
    "why_moved",
    "supply_flow",
    "reference_metrics",
    "peers"
  ],
  "illustration_sections": ["target_price", "quarterly_earnings"]
}
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_build_stock_pages.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/config/stocks.json scripts/config/stock.json scripts/test_build_stock_pages.py
git commit -m "feat(종목 엔진): 종목 메타·섹션 config 선언"
```

---

### Task 2: 실측 데이터 래퍼 (52주 범위 산출 추가)

기존 `_fetch_kospi_realdata()`는 52주 hi/lo를 주지 않는다. 토스 캔들(300개 ≈ 1년 영업일)에서 52주 범위를 산출하는 얇은 래퍼를 생성기 쪽에 추가한다. `validate_analysis.py`는 수정하지 않는다(검증 파이프라인 보호).

**Files:**
- Modify: `scripts/generate_html.py` (함수 추가, import)
- Test: `scripts/test_build_stock_pages.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_build_stock_pages.py`에 추가:

```python
import scripts.generate_html as gh


def test_stock_realdata_adds_52w(monkeypatch):
    fake_closes = [100.0 + i for i in range(300)]  # 오래된→최신

    def fake_kospi(code):
        from scripts.validate_analysis import _closes_to_realdata
        return _closes_to_realdata(fake_closes, ndigits=2)

    monkeypatch.setattr(gh, "_fetch_kospi_realdata", fake_kospi)
    # 52주 범위는 캔들 원본에서 산출되므로 캔들 fetch도 모킹
    monkeypatch.setattr(gh, "_fetch_stock_closes", lambda code: fake_closes)

    rd = gh.stock_realdata("005930")
    assert rd["price"] == 399.0
    assert rd["week52_low"] == 100.0
    assert rd["week52_high"] == 399.0
    assert 0 <= rd["week52_pos_pct"] <= 100
    assert rd["error"] is None
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_build_stock_pages.py::test_stock_realdata_adds_52w -v`
Expected: FAIL — `AttributeError: module 'scripts.generate_html' has no attribute 'stock_realdata'`

- [ ] **Step 3: 생성기에 래퍼 추가**

`scripts/generate_html.py` 상단 import 부근에 추가:

```python
from validate_analysis import _fetch_kospi_realdata
import toss_client as tc
```

(기존 import 스타일에 맞춰 `from scripts.validate_analysis import ...` 폴백이 필요하면 try/except로 감싼다. 기존 파일의 import 관례를 따를 것.)

같은 파일에 함수 추가:

```python
def _fetch_stock_closes(code):
    """토스 일봉 종가 리스트(오래된→최신). 52주 범위 산출용."""
    candles = tc.get_candles(code, interval="1d", count=300)
    return [float(c["closePrice"]) for c in candles if c.get("closePrice")]


def stock_realdata(code):
    """종목 상세용 실측 dict. 시세·sparkline·MA + 52주 범위."""
    rd = _fetch_kospi_realdata(code)
    if rd.get("error"):
        return {"error": rd["error"], "price": None}
    rd["error"] = None
    try:
        closes = _fetch_stock_closes(code)
        if closes:
            lo, hi = min(closes), max(closes)
            rd["week52_low"] = round(lo, 2)
            rd["week52_high"] = round(hi, 2)
            rd["week52_pos_pct"] = round((rd["price"] - lo) / (hi - lo) * 100, 1) if hi > lo else 0
    except Exception:
        rd["week52_low"] = rd["week52_high"] = rd["week52_pos_pct"] = None
    return rd
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_build_stock_pages.py::test_stock_realdata_adds_52w -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_html.py scripts/test_build_stock_pages.py
git commit -m "feat(종목 엔진): 실측 래퍼 + 52주 범위 산출"
```

---

### Task 3: detail 템플릿 + 공유 에셋 추출

005930 프로토(`web/stocks/005930/index.html`)에서 인라인 CSS/JS를 외부 파일로 빼고, 리터럴 값을 Jinja2 변수로 치환한 템플릿을 만든다.

**Files:**
- Create: `web/assets/stocks.css`
- Create: `web/assets/stocks.js`
- Create: `scripts/templates/stocks/detail.html`

- [ ] **Step 1: 인라인 CSS 추출**

`web/stocks/005930/index.html`의 `<style>...</style>` 블록 전체를 잘라 `web/assets/stocks.css`로 옮긴다(첫 줄에 한국어 헤더 주석 금지 — CSS는 `/* ... */` 사용). 내용 변경 없이 그대로 이동.

- [ ] **Step 2: 인라인 JS 추출**

`web/stocks/005930/index.html`의 `<script>` 블록(`drawMiniChart` 등 6개 함수 포함)을 `web/assets/stocks.js`로 옮긴다. 첫 줄에 한국어 헤더:

```javascript
// 종목 상세 페이지의 sparkline 렌더와 기간탭 토글을 담당하는 스크립트
```

- [ ] **Step 3: detail.html 템플릿 작성**

`scripts/templates/stocks/detail.html` 첫 줄에 한국어 헤더 주석. 005930 프로토의 마크업을 베이스로, 인라인 `<style>`/`<script>`를 외부 참조로 교체하고 리터럴을 변수로 치환한다.

변수 치환 매핑 (프로토 리터럴 → Jinja2):

| 프로토 리터럴 | 변수 |
| --- | --- |
| `삼성전자` | `{{ stock.name }}` |
| `005930` | `{{ stock.code }}` |
| `반도체` | `{{ stock.sector }}` |
| `KOSPI` | `{{ stock.market }}` |
| `354,000` | `{{ "{:,}".format(rd.price | int) }}` |
| `-2.34%` / `▼` | `{{ rd.change_pct }}` + 부호 분기 |
| 5일 sparkline 배열 | `data-spark="{{ rd.sparkline | join(',') }}"` (stocks.js가 읽어 렌더) |
| `최저 53,700` / `최고 374,500` | `{{ rd.week52_low }}` / `{{ rd.week52_high }}` |
| `현재가 94% 지점` | `{{ rd.week52_pos_pct }}` |
| 같은 섹터 peer 행 | `{% for p in peers %}` 루프 (Task 4에서 peers context 주입) |
| 헤더 `06-19 종가` | `{{ generated_label }}` |

`<head>`의 에셋 참조:

```html
<link rel="stylesheet" href="/assets/stocks.css">
<script defer src="/assets/stocks.js"></script>
```

일러스트 배너 문구는 프로토 그대로 유지하되, 실측 주입 항목을 정확히 반영:

```html
<div class="proto-banner">프로토타입 · 시세·sparkline·52주는 실측, 목표가·분기실적은 일러스트레이션</div>
```

navbar는 기존 프로토와 동일 마크업 사용(향후 base 템플릿 공유는 별도 과제).

- [ ] **Step 4: 템플릿 문법 검증**

Run:
```bash
python3 -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('scripts/templates')).get_template('stocks/detail.html'); print('template OK')"
```
Expected: `template OK` (문법 에러 없음)

- [ ] **Step 5: 커밋**

```bash
git add web/assets/stocks.css web/assets/stocks.js scripts/templates/stocks/detail.html
git commit -m "feat(종목 엔진): detail 템플릿 + 공유 에셋 추출"
```

---

### Task 4: 종목 페이지 생성 함수 + CLI

**Files:**
- Modify: `scripts/generate_html.py`
- Test: `scripts/test_build_stock_pages.py`

- [ ] **Step 1: 실패하는 통합 테스트 작성**

`scripts/test_build_stock_pages.py`에 추가:

```python
def test_build_stock_page_writes_real_price(tmp_path, monkeypatch):
    fake = {"price": 354000.0, "change_pct": -2.34,
            "sparkline": [350000.0, 354000.0], "error": None,
            "week52_low": 53700.0, "week52_high": 374500.0, "week52_pos_pct": 94.0}
    monkeypatch.setattr(gh, "stock_realdata", lambda code: fake)
    monkeypatch.setattr(gh, "WEB_DIR", tmp_path)  # 출력 루트 격리

    stock = {"code": "005930", "name": "삼성전자", "sector": "반도체",
             "market": "KOSPI", "peers": ["000660"]}
    out = gh.build_stock_page(stock, [{"code": "000660", "name": "SK하이닉스", "change_pct": 3.42}])

    html = (tmp_path / "stocks" / "005930" / "index.html").read_text(encoding="utf-8")
    assert "354,000" in html
    assert "53,700" in html and "374,500" in html
    assert "SK하이닉스" in html       # peer 링크
    assert "/assets/stocks.css" in html
    assert "06-1" not in html or "{{" not in html  # 미치환 변수·하드코딩 날짜 없음
    assert out.endswith("stocks/005930/index.html")
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_build_stock_pages.py::test_build_stock_page_writes_real_price -v`
Expected: FAIL — `AttributeError: ... has no attribute 'build_stock_page'`

- [ ] **Step 3: 생성 함수 + CLI 구현**

`scripts/generate_html.py`에 추가 (기존 `WEB_DIR`/출력 경로 상수가 있으면 재사용, 없으면 정의):

```python
def build_stock_page(stock, peers):
    """종목 1개의 상세 페이지를 생성·기록하고 출력 경로를 반환한다."""
    from datetime import datetime
    rd = stock_realdata(stock["code"])
    if rd.get("error") or rd.get("price") is None:
        raise RuntimeError(f"{stock['code']} 실측 실패: {rd.get('error')}")
    env = make_env()
    tmpl = env.get_template("stocks/detail.html")
    ctx = {
        "stock": stock,
        "rd": rd,
        "peers": peers,
        "generated_label": datetime.now().strftime("%m-%d") + " 종가",
    }
    html = tmpl.render(**ctx)
    out_dir = WEB_DIR / "stocks" / stock["code"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return f"stocks/{stock['code']}/index.html"


def build_all_stocks():
    """stocks.json 전체를 순회 생성. peer는 {code,name} 객체, 등락률은 실측에서 채운다."""
    stocks = load_json(CONFIG_DIR / "stocks.json")
    results = []
    for s in stocks:
        peers = []
        for p in s.get("peers", []):
            prd = stock_realdata(p["code"])
            peers.append({
                "code": p["code"],
                "name": p["name"],
                "change_pct": None if prd.get("error") else prd.get("change_pct"),
            })
        results.append(build_stock_page(s, peers))
    return results
```

`main()`의 argparse에 플래그 추가:

```python
parser.add_argument("--stocks", action="store_true",
                    help="stocks.json 종목 상세 페이지 일괄 생성")
```

`main()` 본문 분기 추가 (기존 `--write-list-only` 분기 부근):

```python
if args.stocks:
    for path in build_all_stocks():
        print(f"생성: {path}")
    return
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_build_stock_pages.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_html.py scripts/test_build_stock_pages.py
git commit -m "feat(종목 엔진): build_stock_page 생성 함수 + --stocks CLI"
```

---

### Task 5: 3종목 실생성 + 사이트맵 + 정합성 검증

**Files:**
- Modify: `scripts/generate_html.py` (`write_sitemap_xml`에 종목 URL 추가)
- Generated: `web/stocks/{005930,000660,005380}/index.html`

- [ ] **Step 1: 사이트맵 테스트 작성**

`scripts/test_build_stock_pages.py`에 추가:

```python
def test_sitemap_includes_stock_urls():
    import inspect
    src = inspect.getsource(gh.write_sitemap_xml)
    assert "stocks" in src, "사이트맵 생성에 종목 URL 추가 필요"
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_build_stock_pages.py::test_sitemap_includes_stock_urls -v`
Expected: FAIL (현재 `write_sitemap_xml`에 stocks 없음)

- [ ] **Step 3: 사이트맵에 종목 URL 추가**

`scripts/generate_html.py`의 `write_sitemap_xml()` 안, URL 수집 루프에 추가:

```python
# 종목 상세 페이지
for s in load_json(CONFIG_DIR / "stocks.json"):
    urls.append(f"{BASE_URL}/stocks/{s['code']}/")
```

(기존 함수의 `urls` 리스트·`BASE_URL` 변수명에 맞춰 조정. 변수명이 다르면 기존 것을 따른다.)

- [ ] **Step 4: 테스트 + 실제 생성**

Run:
```bash
python3 -m pytest scripts/test_build_stock_pages.py -v
python3 scripts/generate_html.py --stocks
```
Expected: pytest 전체 PASS. 생성 로그 3줄(`생성: stocks/005930/index.html` 등).

- [ ] **Step 5: 실측 정합성 수동 확인**

생성된 005930 페이지 가격을 실측과 대조 (SERVICE_RULES 0번 원칙):

```bash
python3 -c "from scripts.generate_html import stock_realdata; print(stock_realdata('005930')['price'])"
grep -o '[0-9,]\{6,\}' web/stocks/005930/index.html | head -3
```
Expected: 출력 가격과 HTML 내 대표 가격이 일치. 불일치 시 Task 2/3 매핑 재확인.

미치환 변수·`/v2/` 경로 점검:

```bash
grep -rn '{{ \|/v2/' web/stocks/005930/index.html web/stocks/000660/index.html web/stocks/005380/index.html || echo "clean"
```
Expected: `clean`

- [ ] **Step 6: 커밋**

```bash
git add scripts/generate_html.py web/stocks/005930/ web/stocks/000660/ web/stocks/005380/ scripts/test_build_stock_pages.py
git commit -m "feat(종목 엔진): 3종목 실생성 + 사이트맵 종목 URL"
```

---

### Task 6 (선택): 인덱스 허브 링크 정리 + stock.html 폐기

`/stocks/` 인덱스가 클린 URL과 `stock.html?code=`를 혼용 중이다. 클린 URL로 일원화한다. 인덱스 전면 템플릿화는 별도 과제이며, 여기서는 링크 정합성만 잡는다.

**Files:**
- Modify: `web/stocks/index.html`
- Delete: `web/stocks/stock.html`

- [ ] **Step 1: 잔존 링크 확인**

Run: `grep -rn 'stock.html' web/`
Expected: index.html / 000660 / 005930 등에 참조 존재 (현황 파악).

- [ ] **Step 2: 링크 치환**

`web/stocks/index.html`의 `href="/stocks/stock.html?code=005380"` → `href="/stocks/005380/"`. 그 외 `stock.html?code=XXXXXX` 형태 모두 `/stocks/XXXXXX/`로 치환.

- [ ] **Step 3: stock.html 삭제 + 참조 0 확인**

```bash
git rm web/stocks/stock.html
grep -rn 'stock.html' web/ || echo "no refs"
```
Expected: `no refs`

- [ ] **Step 4: 프리뷰 검증**

dev server(`localhost:3000`)에서 `/stocks/` 진입 → 현대차 카드 클릭 → `/stocks/005380/`로 이동, 404 아님 확인. (preview_screenshot로 증빙)

- [ ] **Step 5: 커밋**

```bash
git add web/stocks/index.html
git commit -m "refactor(종목): 인덱스 링크 클린 URL 일원화 + stock.html 폐기"
```

---

## Self-Review (작성자 점검 완료)

- **스펙 커버리지:** 생성 방식(generate_html.py 확장)=Task 4, 빌드 타임 실측=Task 2·4, 3종목=Task 5, 공유 에셋 추출=Task 3, 클린 URL 일원화=Task 6. 모두 태스크 존재.
- **플레이스홀더:** 코드 스텝마다 실제 코드 포함. 템플릿(Task 3)은 792줄 프로토가 소스이므로 전체 재현 대신 변수 매핑표로 지시 — 의도된 derivation 방식.
- **타입 일관성:** `stock_realdata()`(Task 2) 반환 키(`price`/`change_pct`/`sparkline`/`week52_*`/`error`)를 Task 4 `build_stock_page`와 테스트가 동일하게 참조. `build_stock_page(stock, peers)` 시그니처 Task 4·테스트 일치.

## 주의 / 가드레일

- **데이터 정합성(SERVICE_RULES 0번):** 화면 수치는 실측만. 목표가·분기실적은 실측 소스 미확보 → 일러스트 배너로 명시, 실측처럼 보이게 하지 말 것.
- **텔레그램 금지:** 이 작업 중 어떤 단계에서도 텔레그램 발송 없음.
- **라이브 서비스 경계:** 생성 대상은 `web/stocks/`(신규 영역). 기존 `web/briefings/`·gh-pages 브리핑은 건드리지 않는다.
- **validate_analysis.py 불변:** 검증 파이프라인 보호를 위해 실측 함수는 import만, 수정 금지.
