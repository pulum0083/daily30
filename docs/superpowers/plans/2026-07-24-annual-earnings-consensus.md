# 연간 실적 컨센서스 섹션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 상세 페이지(삼성·SK하이닉스·현대차 3종목)에 네이버 `finance/annual` 기반 연도별 실적(확정 3개년 + 컨센서스 1개년) 막대 차트 섹션을 추가한다.

**Architecture:** 기존 분기 재무 수집(`_naver_financials`/`parse_financials`)을 연도용으로 미러링한다. 순수 파서 `parse_financials_annual`가 `isConsensus` 플래그를 `est`로 매핑하고 구조적 sanity 게이트(영업이익>매출·매출≤0 폐기)를 적용, `_naver_financials_annual`가 3종목만(`ANNUAL_FIN_CODES`) 수집해 스냅샷에 `financials_annual`로 싣는다. 상세 템플릿은 분기 차트 컴포넌트(`fin-chart`, 기존 CSS)를 연도용으로 미러링해 분기 섹션 바로 위에 렌더한다.

**Tech Stack:** Python 3.12(표준 라이브러리), 순수함수 단위 테스트(pytest 없이 `python3 scripts/test_build_stocks_snapshot.py`), Jinja2 템플릿, 기존 fin-* CSS 재사용.

---

## File Structure

- Modify `scripts/build_stocks_snapshot.py` — `parse_financials_annual`(순수 파서) + `_naver_financials_annual`(수집) + `ANNUAL_FIN_CODES` 상수 + `_build_one` 배선.
- Modify `scripts/test_build_stocks_snapshot.py` — 파서 단위 테스트 2건 추가.
- Modify `scripts/generate_html.py` — `build_stock_page` 컨텍스트에 `financials_annual` 전달.
- Modify `scripts/templates/stocks/detail.html` — "연간 실적" 섹션(분기 섹션 위).
- 생성물: `web/data/stocks-snapshot.json`(스크립트가 씀), `web/stocks/{005930,000660,005380}/index.html`.

데이터 규약: 값은 억원(정수). 연도 항목 `{year:"2026", rev:억원, op:억원, est:bool}`. `est=true`가 컨센서스(예상).

---

## Task 1: 순수 파서 `parse_financials_annual` + sanity 게이트 + 테스트

**Files:**
- Modify: `scripts/build_stocks_snapshot.py` (기존 `parse_financials` 함수 바로 아래에 추가)
- Test: `scripts/test_build_stocks_snapshot.py` (기존 `test_parse_financials` 아래, `run()` 위에 추가)

- [ ] **Step 1: 테스트 추가** — `scripts/test_build_stocks_snapshot.py`의 `def run():` 바로 위에 삽입

```python
def test_parse_financials_annual():
    info = {
        "trTitleList": [
            {"key": "202312", "isConsensus": "N"},
            {"key": "202412", "isConsensus": "N"},
            {"key": "202512", "isConsensus": "N"},
            {"key": "202612", "isConsensus": "Y"},
        ],
        "rowList": [
            {"title": "매출액", "columns": {"202312": {"value": "2,589,355"},
             "202412": {"value": "3,008,709"}, "202512": {"value": "3,336,059"},
             "202612": {"value": "7,324,732"}}},
            {"title": "영업이익", "columns": {"202312": {"value": "65,670"},
             "202412": {"value": "327,260"}, "202512": {"value": "436,011"},
             "202612": {"value": "3,832,404"}}},
        ],
    }
    out = m.parse_financials_annual(info)
    assert [r["year"] for r in out] == ["2023", "2024", "2025", "2026"]
    assert out[0] == {"year": "2023", "rev": 2589355, "op": 65670, "est": False}
    # 2026 컨센서스 — 영업(383조)<매출(732조)이라 게이트 통과, 크기는 손대지 않음
    assert out[-1]["est"] is True and out[-1]["rev"] == 7324732
    assert m.parse_financials_annual(None) == []


def test_parse_financials_annual_sanity_gate():
    # 구조적으로 불가능한 값만 폐기: 영업이익>매출, 매출≤0
    info = {
        "trTitleList": [
            {"key": "202512", "isConsensus": "N"},   # 정상 → 유지
            {"key": "202612", "isConsensus": "Y"},   # 영업>매출 → 폐기
            {"key": "202712", "isConsensus": "Y"},   # 매출 0 → 폐기
        ],
        "rowList": [
            {"title": "매출액", "columns": {"202512": {"value": "1,000"},
             "202612": {"value": "500"}, "202712": {"value": "0"}}},
            {"title": "영업이익", "columns": {"202512": {"value": "100"},
             "202612": {"value": "900"}, "202712": {"value": "50"}}},
        ],
    }
    out = m.parse_financials_annual(info)
    assert [r["year"] for r in out] == ["2025"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd scripts && python3 test_build_stocks_snapshot.py`
Expected: FAIL — `AttributeError: module 'build_stocks_snapshot' has no attribute 'parse_financials_annual'`

- [ ] **Step 3: 파서 구현** — `scripts/build_stocks_snapshot.py`의 `parse_financials` 함수 바로 아래에 삽입

```python
def parse_financials_annual(finance_info):
    """네이버 finance/annual 응답에서 연도별 매출·영업이익(억원)을 순서대로.
    각 항목: {year:'2026', rev:매출, op:영업이익, est:컨센서스추정여부}.
    구조적 sanity 게이트(운영규칙 0): 매출 결측/≤0 또는 영업이익>매출(불가능)인 연도는 폐기.
    컨센서스 값의 크기 자체는 손대지 않는다(벤더 실측)."""
    if not finance_info:
        return []
    titles = finance_info.get("trTitleList", [])
    rows = {r.get("title"): r.get("columns", {}) for r in finance_info.get("rowList", [])}
    rev_col = rows.get("매출액", {})
    op_col = rows.get("영업이익", {})
    out = []
    for t in titles:
        key = t.get("key") or ""
        rev = _to_int((rev_col.get(key) or {}).get("value"))
        op = _to_int((op_col.get(key) or {}).get("value"))
        if rev is None or rev <= 0:
            continue
        if op is not None and op > rev:
            continue
        out.append({"year": key[:4], "rev": rev, "op": op,
                    "est": t.get("isConsensus") == "Y"})
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd scripts && python3 test_build_stocks_snapshot.py`
Expected: PASS — 기존 테스트 + 2건 모두 통과(마지막 줄 `N passed`, N은 기존+2).

- [ ] **Step 5: 커밋**

```bash
git add scripts/build_stocks_snapshot.py scripts/test_build_stocks_snapshot.py
git commit -m "feat(stocks): 연간 실적 파서 parse_financials_annual + sanity 게이트 + 테스트"
```

---

## Task 2: 수집 `_naver_financials_annual` + 3종목 게이팅 배선

**Files:**
- Modify: `scripts/build_stocks_snapshot.py` (상수 추가 + `_naver_financials` 아래 함수 추가 + `_build_one` 배선)

- [ ] **Step 1: 상수 추가** — `_naver_financials` 함수 정의부 위(모듈 상단 상수 근처, 예: `_VOL_SENTINEL` 등 상수가 모인 곳)에 삽입. 적절한 위치가 없으면 `parse_financials_annual` 정의 바로 위에 삽입.

```python
# 연간 실적 컨센서스 수집 대상 — 리포트가 지목한 3종목만(스코프 좁혀 QA 단순화, §후속 확대)
ANNUAL_FIN_CODES = {"005930", "000660", "005380"}
```

- [ ] **Step 2: 수집 함수 추가** — `_naver_financials(code)` 함수 바로 아래에 삽입

```python
def _naver_financials_annual(code):
    """종목별 연간 매출·영업이익(억원, 컨센서스 플래그 포함). 실패 시 []."""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/finance/annual"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return parse_financials_annual(data.get("financeInfo"))
    except Exception as e:
        print(f"[snapshot] naver finance/annual {code} 실패: {e}", file=sys.stderr)
        return []
```

- [ ] **Step 3: `_build_one` 배선 — 초기화** — `_build_one` 함수 안의 `supply5 = financials = None` 줄을 아래로 교체

```python
    supply5 = financials = financials_annual = None
```

- [ ] **Step 4: `_build_one` 배선 — 수집 호출** — `financials = _naver_financials(symbol)  # 분기 매출·영업이익` 줄 바로 아래에 삽입

```python
        if symbol in ANNUAL_FIN_CODES:
            financials_annual = _naver_financials_annual(symbol)  # 연간 매출·영업이익(3종목)
```

- [ ] **Step 5: `_build_one` 배선 — 레코드 부착** — `if financials:` 블록(`rec["financials"] = financials`) 바로 아래에 삽입

```python
    if financials_annual:
        rec["financials_annual"] = financials_annual
```

- [ ] **Step 6: 기존 테스트 여전히 통과 + 임포트 무결성 확인**

Run: `cd scripts && python3 test_build_stocks_snapshot.py`
Expected: PASS — 전체 통과(파싱 함수 추가가 기존 동작을 안 깸).

- [ ] **Step 7: 커밋**

```bash
git add scripts/build_stocks_snapshot.py
git commit -m "feat(stocks): 연간 실적 수집 _naver_financials_annual — 3종목(ANNUAL_FIN_CODES) 배선"
```

---

## Task 3: generate_html 컨텍스트 전달

**Files:**
- Modify: `scripts/generate_html.py` (`build_stock_page`의 컨텍스트 dict)

- [ ] **Step 1: 컨텍스트에 추가** — `"financials": snap_stock.get("financials"),` 줄 바로 아래에 삽입

```python
        "financials_annual": snap_stock.get("financials_annual"),
```

- [ ] **Step 2: 파이썬 문법 확인**

Run: `python3 -c "import ast; ast.parse(open('scripts/generate_html.py').read())" && echo OK`
Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add scripts/generate_html.py
git commit -m "feat(stocks): build_stock_page 컨텍스트에 financials_annual 전달"
```

---

## Task 4: 상세 템플릿 "연간 실적" 섹션

**Files:**
- Modify: `scripts/templates/stocks/detail.html` (분기 실적 섹션 `<!-- 분기 실적 (매출·영업이익) -->` 바로 위에 삽입)

`fmt_eok` 매크로는 같은 파일 앞부분(현재 233행 근처)에 이미 정의돼 있고, 삽입 위치는 그 뒤이므로 사용 가능하다.

- [ ] **Step 1: 섹션 삽입** — `<!-- 분기 실적 (매출·영업이익) -->` 주석 줄 바로 위에 삽입(분기 섹션과 동일 구조를 연도용으로 미러링)

```html
      <!-- 연간 실적 (매출·영업이익 · 확정 + 컨센서스) -->
      {% if financials_annual %}
      {% set arev_max = (financials_annual | map(attribute='rev') | reject('none') | list | max) or 1 %}
      <div class="np">
        <div class="np__h">
          <span class="np__t">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M5 21V8l5-4 5 4v13M9 9h2m-2 4h2m4-4h2m-2 4h2"/></svg>
            연간 실적
          </span>
          <span class="np__s">매출액 · 연간</span>
        </div>
        <div style="padding:16px 16px 12px;">
          <div class="fin-chart">
            {% for y in financials_annual %}
            <div class="fin-col">
              <span class="fin-cap{{ ' est' if y.est }}">{% if y.rev is not none %}{{ fmt_eok(y.rev) }}{% endif %}{{ '(E)' if y.est }}</span>
              <div class="fin-bar {{ 'est' if y.est else 'actual' }}" style="height:{{ ((y.rev or 0) / arev_max * 150) | round | int }}px"></div>
            </div>
            {% endfor %}
          </div>
          <div class="fin-xrow">
            {% for y in financials_annual %}
            <span class="fin-x{{ ' est' if y.est }}">{{ y.year }}<br><span style="color:{{ 'var(--up)' if (y.op or 0) >= 0 else 'var(--dn)' }}">영업 {% if y.op is not none %}{{ fmt_eok(y.op) }}{% else %}—{% endif %}</span></span>
            {% endfor %}
          </div>
          <div class="fin-foot"><div class="fin-legend">
            <span><i style="background:var(--up)"></i>확정 실적</span>
            <span><i class="est"></i>컨센서스 추정</span>
          </div></div>
        </div>
      </div>
      {% endif %}
```

- [ ] **Step 2: 삽입 위치 확인**

Run: `grep -n "연간 실적\|분기 실적 (매출" scripts/templates/stocks/detail.html`
Expected: `연간 실적` 주석이 `분기 실적 (매출` 주석보다 먼저 나온다.

- [ ] **Step 3: 커밋**

```bash
git add scripts/templates/stocks/detail.html
git commit -m "feat(stocks): 상세 페이지 '연간 실적' 섹션 — 분기 차트 미러링(분기 위)"
```

---

## Task 5: 통합 — 3종목 재생성·렌더 검증

**Files:** (검증만, 코드 변경 없음)

- [ ] **Step 1: 3종목 수집 결과 격리 확인**

전체 스냅샷을 네트워크로 재수집하지 않고, 수집 함수만 격리 실행해 결과를 눈으로 확인한다.

Run:
```bash
cd scripts && python3 -c "
import build_stocks_snapshot as m
for code,nm in [('005930','삼성전자'),('000660','SK하이닉스'),('005380','현대차')]:
    fa=m._naver_financials_annual(code)
    print(nm, code, '→', [(r['year'], r['rev'], r['op'], 'E' if r['est'] else '') for r in fa])
"
```
Expected: 3종목 모두 4개년(2023·24·25 확정 + 2026 E) 출력, 값이 억원 정수, 2026만 `E`.

- [ ] **Step 2: 기존 스냅샷에 3종목만 주입 후 상세 재생성**

전체 재수집(46종목 네트워크)은 무거우므로, 기존 `web/data/stocks-snapshot.json`의 3종목 레코드에 `financials_annual`만 주입한 뒤 상세를 생성한다(가볍고 결정적). 이 변경은 Step 5에서 되돌린다.

Run:
```bash
python3 -c "
import json
import scripts.build_stocks_snapshot as m
p='web/data/stocks-snapshot.json'
d=json.load(open(p))
for code in ('005930','000660','005380'):
    fa=m._naver_financials_annual(code)
    if fa and code in d.get('stocks',{}):
        d['stocks'][code]['financials_annual']=fa
json.dump(d, open(p,'w'), ensure_ascii=False, indent=1)
print('injected')
"
python3 scripts/generate_html.py --stocks  # 상세 페이지 재생성
grep -c "연간 실적" web/stocks/005930/index.html web/stocks/000660/index.html web/stocks/005380/index.html
grep -L "연간 실적" web/stocks/005930/index.html web/stocks/068270/index.html
```
Expected: 3종목 각 파일에서 `연간 실적` 1건씩. 게이팅 확인 — `068270`(셀트리온 등 비대상)은 `grep -L`에 잡혀야(섹션 없음). 참고: 스냅샷 dict 경로가 `stocks[code]`가 아니면(구조 상이) 주입 코드의 키를 실제 구조에 맞춘다.

- [ ] **Step 3: 브라우저 렌더 확인**

- `preview_start`로 `daily30-web`(포트 8788) 기동 → `http://localhost:8788/stocks/005930/`
- `read_page`/스크린샷으로 "연간 실적" 섹션이 분기 실적 위에 렌더되는지, 확정 3개년(빨강 실선)·컨센서스 2026(빗금·(E)·파란 라벨)·범례가 맞는지 확인.
- `005380`(현대차)도 확인 — 완만한 성장 형태.

Expected: 세 종목 모두 연간 섹션 정상, 확정/컨센서스 시각 구분, "(E)" 마커.

- [ ] **Step 4: 단위 테스트 최종 재확인**

Run: `cd scripts && python3 test_build_stocks_snapshot.py`
Expected: 전체 통과.

- [ ] **Step 5: 재생성된 43종목 처리**

`generate_html.py --stocks`는 전 종목을 재생성한다. 3종목 외 43개는 이번 변경(연간 섹션 게이팅)과 무관하게 다른 실측 데이터(시세 등)가 갱신됐을 수 있다. `git status`로 확인 후, **연간 섹션과 무관한 43종목 변경은 커밋하지 않는다**(SERVICE_RULES §20 사례 — 비거래일/무관 재생성분 되돌림). 3종목 상세 + 스냅샷만 커밋 대상. 단, 스냅샷은 정규 잡이 곧 덮어쓰므로 실데이터 커밋은 배포 시점 정규 파이프라인에 맡기고, 여기선 **커밋하지 않고** 로컬 검증만 한 뒤 되돌린다.

Run:
```bash
git checkout -- web/stocks/ web/data/stocks-snapshot.json 2>/dev/null || true
git status --short web/
```
Expected: 검증용 재생성분이 정리돼 워킹트리가 깨끗(코드·템플릿 변경은 Task 1~4에서 이미 커밋됨).

- [ ] **Step 6: 커밋 없음** — 검증 전용 태스크.

---

## 배포 메모 (구현 후)

- 코드·템플릿 변경만 커밋된 상태. 실제 3종목 상세 HTML은 정규 `kospi-close-briefing` 잡의 `generate_html.py --stocks` 스텝(평일 16:25)이 다음 실행 때 `financials_annual` 포함 스냅샷으로 재생성·배포한다.
- 즉시 반영을 원하면 사용자 지시하에 `build_stocks_snapshot.py` → `generate_html.py --stocks`로 3종목을 생성·커밋·푸시(라이브 서비스 경계 — 지시 시에만).
- 후속: 검증 후 `ANNUAL_FIN_CODES`를 주요 종목으로 확대.
