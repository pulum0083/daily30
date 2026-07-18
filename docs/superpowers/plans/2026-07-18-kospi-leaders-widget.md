# 코스피 주도주 위젯 재구성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `web/stocks/index.html`의 코스피 주도주 위젯을 재구성해, 탭(종목) 선택 시 **곡선+장중지표 / 관련뉴스5+증권사 목표주가**를 보여주고 하단에 코스피 외국계 시각을 붙인다.

**Architecture:** 수집은 Python 스크립트 2개가 담당해 정적 JSON을 `web/data/`에 쓰고, 렌더링은 `web/stocks/index.html`의 인라인 JS가 그 JSON을 fetch해서 그린다. 기존 실시간 가격 폴링(`/api/stocks-live`)과 HL 24h 전환 로직은 **건드리지 않는다**. GHA 분 예산(private repo, 2,000분/월) 때문에 새 잡을 만들지 않고 기존 잡에 스텝을 얹는다.

**Tech Stack:** Python 3 (urllib, re — 신규 의존성 없음), Gemini 2.5 Flash Lite (뉴스 요약), pytest, 바닐라 JS/CSS.

**확정 프로토타입:** `docs/prototypes/2026-07-18-kospi-leaders-layout-v6.html` — UI 마크업·CSS는 이 파일에서 그대로 가져온다.

---

## 검증된 데이터 소스 (2026-07-18 실측 확인)

이 계획은 추측이 아니라 실제 HTTP 응답으로 확인한 사실 위에 세워졌다. **아래 내용을 신뢰하고 구현하되, 셀렉터가 깨지면 사이트 마크업이 바뀐 것이다.**

| 항목 | 소스 | 확인 결과 |
| --- | --- | --- |
| 종목별 리포트 목록 | `finance.naver.com/research/company_list.naver?searchType=itemCode&itemCode={code}&page={n}` (EUC-KR) | ✅ 2페이지로 60건 / 13~15개 증권사 / 약 4개월치 |
| 개별 목표가·투자의견 | `finance.naver.com/research/company_read.naver?nid={nid}&page=1` (EUC-KR) | ✅ 상세 페이지에만 존재. 목록에는 **없음** |
| 컨센서스 목표주가 | ❌ 네이버 API 없음 | `api.stock.naver.com/.../integration` → **HTTP 409**. `m.stock.naver.com/.../integration`의 `consensus` → **null**. → **직접 평균 계산한다** |
| 뉴스 | Google News RSS 종목명 쿼리 | ✅ 기존 `fetch_news_live.py`와 동일 패턴 |
| 썸네일 | 원문 `og:image` | ⚠️ 추출은 되지만 **상당수가 언론사 로고 폴백**이다. 기사 고유 이미지가 아닐 수 있음 |

**리포트 상세 페이지 실제 마크업 (정규식 근거):**

```html
<div class="view_info_1">
    목표가 <em class="money"><strong>480,000</strong></em>
    <span class="division">|</span>
    투자의견 <em class="coment">Buy</em>
```

**뉴스 발행량 실측 (3종목 합산, 최근 7일):**

| 구간 (KST) | 시간당 기사 | 채택 주기 |
| --- | --- | --- |
| 09:00~15:30 | 3.00건 | 30분 (기존 잡 편승) |
| 15:30~21:00 | 2.06건 | 1시간 (기존 잡 편승) |
| 21:00~24:00 | 0.62건 | 2시간 (기존 잡 편승) |
| 00:00~06:00 | 0.48건 | **생략** — 06:00 폴링이 밤새 기사를 어차피 다 가져온다 |
| 06:00~09:00 | 2.29건 | **1시간 (신규 크론)** — 장중 다음으로 밀도가 높다 |
| 주말 | 측정 불가(RSS 104건 절단 + pubDate 재스탬핑) | **3시간, 08:00~20:00 (신규 크론)** — 2주 후 로그로 재조정 |

---

## File Structure

**신규 생성**

- `scripts/fetch_stock_targets.py` — 증권사 리포트 수집 → 목표가/투자의견 파싱 → 컨센서스 계산 → 히스토리 누적
- `scripts/test_fetch_stock_targets.py` — 위 파싱·계산 로직 테스트
- `scripts/fetch_stock_news.py` — 종목별 뉴스 RSS 수집 → dedupe → Gemini 요약 → og:image
- `scripts/test_fetch_stock_news.py` — dedupe·og:image 파싱 테스트
- `web/data/stock-targets.json` — 위젯이 fetch (스크립트가 생성)
- `web/data/stock-news.json` — 위젯이 fetch (스크립트가 생성)
- `data/consensus_history.json` — 컨센서스 일별 누적 (커밋됨)

**수정**

- `web/stocks/index.html` — 위젯 마크업·CSS·JS 재구성
- `.github/workflows/daily_report.yml` — 목표주가 수집 스텝 2곳 추가
- `.github/workflows/kospi-news-live.yml` — 종목 뉴스 스텝 + 신규 스케줄 창

**건드리지 않는다**

- `krOpen()` / `setNight()` — 실시간 ↔ HL 24h 전환 로직
- `/api/stocks-live` 폴링
- `fetch_ib_korea_views.py` — 이미 있는 것을 그대로 재사용

---

### Task 1: 리포트 목록·상세 파서

**Files:**
- Create: `scripts/fetch_stock_targets.py`
- Test: `scripts/test_fetch_stock_targets.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_fetch_stock_targets.py`:

```python
# 네이버 증권사 리포트 목록·상세 파싱과 컨센서스 계산을 검증하는 테스트
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_stock_targets as fst

LIST_HTML = """
<table><tbody>
<tr><td><a href="/item/main.naver?code=005930">삼성전자</a></td>
<td><a href="company_read.naver?nid=93991&page=1">메모리 이익 체력 확인</a></td>
<td>하나증권</td><td>26.07.08</td><td>5527</td></tr>
<tr><td><a href="/item/main.naver?code=005930">삼성전자</a></td>
<td><a href="company_read.naver?nid=93978&page=1">체급의 위력</a></td>
<td>대신증권</td><td>26.07.07</td><td>5081</td></tr>
<tr><td colspan="5">광고행</td></tr>
</tbody></table>
"""

DETAIL_HTML = """
<div class="view_info">
    <div class="view_info_1">
        목표가 <em class="money"><strong>480,000</strong></em>
    <span class="division">|</span>
    투자의견 <em class="coment">Buy</em>
    </div></div>
"""

DETAIL_NO_TARGET = """
<div class="view_info_1">투자의견 <em class="coment">Buy</em></div>
"""


def test_parse_report_list_extracts_rows():
    rows = fst.parse_report_list(LIST_HTML)
    assert len(rows) == 2
    assert rows[0] == {"firm": "하나증권", "date": "26.07.08", "nid": "93991"}
    assert rows[1]["firm"] == "대신증권"


def test_parse_report_detail_extracts_target_and_opinion():
    assert fst.parse_report_detail(DETAIL_HTML) == {
        "target_price": 480000, "opinion": "Buy"
    }


def test_parse_report_detail_returns_none_target_when_absent():
    # 목표가 없는 리포트가 실제로 존재한다 — 조용히 0으로 만들지 말고 None을 반환해야 한다
    assert fst.parse_report_detail(DETAIL_NO_TARGET)["target_price"] is None
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python3 -m pytest scripts/test_fetch_stock_targets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_stock_targets'`

- [ ] **Step 3: 최소 구현 작성**

`scripts/fetch_stock_targets.py`:

```python
# 네이버 증권사 리포트에서 종목별 목표주가·투자의견을 수집해 컨센서스를 계산하는 스크립트
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
LIST_URL = ("https://finance.naver.com/research/company_list.naver"
            "?searchType=itemCode&itemCode={code}&page={page}")
DETAIL_URL = "https://finance.naver.com/research/company_read.naver?nid={nid}&page=1"

_STRIP = re.compile(r"<[^>]+>")


def _text(html):
    return _STRIP.sub("", html).strip()


def fetch_euckr(url):
    """네이버 금융 리서치 게시판은 EUC-KR로 서빙된다."""
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=20).read().decode("euc-kr", "ignore")


def parse_report_list(html):
    """목록 HTML에서 (증권사, 날짜, nid)를 뽑는다. 목표가는 목록에 없다."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        nid = re.search(r"nid=(\d+)", row)
        cols = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        cols = [c for c in cols if c]
        if not nid or len(cols) < 4:
            continue
        if not re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", cols[3]):
            continue
        out.append({"firm": cols[2], "date": cols[3], "nid": nid.group(1)})
    return out


def parse_report_detail(html):
    """상세 HTML에서 목표가·투자의견을 뽑는다. 목표가가 없는 리포트는 None."""
    tp = re.search(r"목표가[\s\S]{0,40}?([\d][\d,]{2,})", html)
    op = re.search(r"투자의견\s*<em[^>]*>([^<]+)</em>", html)
    return {
        "target_price": int(tp.group(1).replace(",", "")) if tp else None,
        "opinion": op.group(1).strip() if op else None,
    }
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `python3 -m pytest scripts/test_fetch_stock_targets.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/fetch_stock_targets.py scripts/test_fetch_stock_targets.py
git commit -m "feat(targets): 네이버 증권사 리포트 목록·상세 파서 추가"
```

---

### Task 2: 컨센서스 계산

증권사별로 리포트가 여러 건 있으므로, **증권사당 최신 1건만** 써야 한다. 안 그러면 리포트를 많이 낸 증권사가 평균에 과대 반영된다.

**Files:**
- Modify: `scripts/fetch_stock_targets.py`
- Test: `scripts/test_fetch_stock_targets.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`scripts/test_fetch_stock_targets.py` 끝에 추가:

```python
def test_compute_consensus_uses_latest_per_firm():
    # 같은 증권사가 2건을 냈으면 최신 1건만 평균에 들어가야 한다
    reports = [
        {"firm": "하나증권", "date": "26.07.08", "target_price": 100000},
        {"firm": "하나증권", "date": "26.05.02", "target_price": 60000},
        {"firm": "대신증권", "date": "26.07.07", "target_price": 120000},
    ]
    r = fst.compute_consensus(reports, today="26.07.18")
    assert r["firm_count"] == 2
    assert r["consensus"] == 110000  # (100000 + 120000) / 2


def test_compute_consensus_drops_reports_older_than_3_months():
    reports = [
        {"firm": "A증권", "date": "26.07.08", "target_price": 100000},
        {"firm": "B증권", "date": "26.01.05", "target_price": 999999},
    ]
    r = fst.compute_consensus(reports, today="26.07.18")
    assert r["firm_count"] == 1
    assert r["consensus"] == 100000


def test_compute_consensus_returns_none_when_no_valid_reports():
    # 목표가가 전부 없으면 억지로 0을 만들지 않고 None (운영규칙 0)
    reports = [{"firm": "A증권", "date": "26.07.08", "target_price": None}]
    assert fst.compute_consensus(reports, today="26.07.18")["consensus"] is None
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python3 -m pytest scripts/test_fetch_stock_targets.py -k consensus -v`
Expected: FAIL — `AttributeError: module 'fetch_stock_targets' has no attribute 'compute_consensus'`

- [ ] **Step 3: 구현 추가**

`scripts/fetch_stock_targets.py` 끝에 추가:

```python
from datetime import datetime, timedelta


def _to_date(yymmdd):
    """'26.07.08' → date. 네이버는 2자리 연도를 쓴다."""
    return datetime.strptime(yymmdd, "%y.%m.%d").date()


def compute_consensus(reports, today, months=3):
    """증권사당 최신 1건만 골라 최근 N개월 목표주가 평균을 낸다.

    유효한 목표가가 하나도 없으면 consensus=None을 반환한다 —
    억지로 0이나 추정치를 만들지 않는다(운영규칙 0).
    """
    cutoff = _to_date(today) - timedelta(days=months * 31)
    latest = {}
    for r in reports:
        if r.get("target_price") is None:
            continue
        d = _to_date(r["date"])
        if d < cutoff:
            continue
        prev = latest.get(r["firm"])
        if prev is None or d > _to_date(prev["date"]):
            latest[r["firm"]] = r
    picked = list(latest.values())
    if not picked:
        return {"consensus": None, "firm_count": 0, "reports": []}
    avg = round(sum(p["target_price"] for p in picked) / len(picked))
    picked.sort(key=lambda p: _to_date(p["date"]), reverse=True)
    return {"consensus": avg, "firm_count": len(picked), "reports": picked}
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `python3 -m pytest scripts/test_fetch_stock_targets.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/fetch_stock_targets.py scripts/test_fetch_stock_targets.py
git commit -m "feat(targets): 증권사당 최신 1건 기준 컨센서스 계산 추가"
```

---

### Task 3: 수집 엔트리포인트 + JSON 출력 + 히스토리 누적

**Files:**
- Modify: `scripts/fetch_stock_targets.py`
- Test: `scripts/test_fetch_stock_targets.py`

- [ ] **Step 1: 실패하는 테스트 추가**

```python
import json


def test_append_history_writes_one_point_per_day(tmp_path):
    p = tmp_path / "consensus_history.json"
    fst.append_history(p, "005930", 100000, "2026-07-18")
    fst.append_history(p, "005930", 105000, "2026-07-18")  # 같은 날 두 번째 호출
    data = json.loads(p.read_text(encoding="utf-8"))
    # 하루 1점만 — 두 번째 호출이 덮어쓰되 점 개수는 늘지 않는다
    assert len(data["005930"]) == 1
    assert data["005930"][0] == {"date": "2026-07-18", "value": 105000}


def test_append_history_keeps_separate_days(tmp_path):
    p = tmp_path / "consensus_history.json"
    fst.append_history(p, "005930", 100000, "2026-07-17")
    fst.append_history(p, "005930", 105000, "2026-07-18")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert [d["date"] for d in data["005930"]] == ["2026-07-17", "2026-07-18"]


def test_append_history_ignores_none(tmp_path):
    p = tmp_path / "consensus_history.json"
    fst.append_history(p, "005930", None, "2026-07-18")
    assert json.loads(p.read_text(encoding="utf-8")) == {}
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python3 -m pytest scripts/test_fetch_stock_targets.py -k history -v`
Expected: FAIL — `AttributeError: ... has no attribute 'append_history'`

- [ ] **Step 3: 구현 추가**

`scripts/fetch_stock_targets.py` 끝에 추가:

```python
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "web" / "data" / "stock-targets.json"
HISTORY_JSON = ROOT / "data" / "consensus_history.json"
STOCKS = {"005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차"}
MIN_HISTORY_POINTS = 20   # 이 개수 미만이면 프런트에서 추이 그래프를 숨긴다
MAX_HISTORY_POINTS = 120  # 약 6개월치 거래일


def append_history(path, code, value, date_str):
    """컨센서스를 하루 1점만 누적한다. 같은 날 재실행은 덮어쓴다."""
    if value is None:
        path.write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")
        return
    data = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    series = [d for d in data.get(code, []) if d["date"] != date_str]
    series.append({"date": date_str, "value": value})
    series.sort(key=lambda d: d["date"])
    data[code] = series[-MAX_HISTORY_POINTS:]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_close_price(code):
    """상승여력 계산의 기준가. 정규장 종가 고정 — HL 24h 환산가에 연동하지 않는다.

    환산가는 실제 체결가가 아니라(운영규칙 0), 밤새 상승여력이 흔들리면 안 된다.
    프로젝트 표준 조회 경로(토스 → 네이버 폴백)를 그대로 재사용한다.
    """
    반환 dict의 종가 키는 ``price``다 (``close``가 아니다 — 2026-07-18 실측 확인).
    데이터가 부족하면 ``{"error": ...}``를 돌려주므로 그 경우도 None으로 처리한다.
    """
    try:
        from validate_analysis import _fetch_kospi_realdata
        r = _fetch_kospi_realdata(code)
        if not r or r.get("error") or r.get("price") is None:
            return None
        return int(r["price"])
    except Exception as e:
        print(f"  ! 종가 조회 실패 {code}: {e}", file=sys.stderr)
        return None


def collect(code, pages=2):
    """종목 하나의 리포트를 수집해 목표가·투자의견까지 채운다."""
    rows = []
    for page in range(1, pages + 1):
        try:
            rows += parse_report_list(fetch_euckr(LIST_URL.format(code=code, page=page)))
        except Exception as e:
            print(f"  ! 목록 실패 {code} p{page}: {e}", file=sys.stderr)
    for r in rows:
        try:
            r.update(parse_report_detail(fetch_euckr(DETAIL_URL.format(nid=r["nid"]))))
        except Exception as e:
            print(f"  ! 상세 실패 nid={r['nid']}: {e}", file=sys.stderr)
            r["target_price"], r["opinion"] = None, None
    return rows


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    today_short = datetime.now().strftime("%y.%m.%d")
    history = {}
    if HISTORY_JSON.exists():
        history = json.loads(HISTORY_JSON.read_text(encoding="utf-8") or "{}")

    out = {"updated_at": today, "stocks": {}}
    for code, name in STOCKS.items():
        reports = collect(code)
        c = compute_consensus(reports, today=today_short)
        append_history(HISTORY_JSON, code, c["consensus"], today)
        hist = json.loads(HISTORY_JSON.read_text(encoding="utf-8") or "{}").get(code, [])
        out["stocks"][code] = {
            "name": name,
            "consensus": c["consensus"],
            "firm_count": c["firm_count"],
            "close_price": fetch_close_price(code),
            # 화면에는 최대 10건만 쓴다
            "reports": [
                {"firm": r["firm"], "opinion": r["opinion"],
                 "target_price": r["target_price"], "date": r["date"]}
                for r in c["reports"][:10]
            ],
            # 점이 부족하면 추이 그래프를 아예 내보내지 않는다 (프런트 숨김 게이트)
            "history": hist if len(hist) >= MIN_HISTORY_POINTS else [],
        }
        print(f"  {name}: 컨센 {c['consensus']} / {c['firm_count']}개사 / 히스토리 {len(hist)}점")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {OUT_JSON}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 + 실제 수집 검증**

Run: `python3 -m pytest scripts/test_fetch_stock_targets.py -v`
Expected: PASS (9 passed)

Run: `python3 scripts/fetch_stock_targets.py`
Expected: 3종목 각각 `컨센 <숫자> / 1x개사 / 히스토리 1점` 출력 후 `✅ .../stock-targets.json`

Run: `python3 -c "import json;d=json.load(open('web/data/stock-targets.json'));s=d['stocks']['005930'];print(s['consensus'], s['firm_count'], len(s['reports']), s['history'])"`
Expected: 컨센 숫자 + 10 이하 리포트 수 + `[]` (첫 실행이라 히스토리 1점 < 20 → 빈 배열)

- [ ] **Step 5: 커밋**

```bash
git add scripts/fetch_stock_targets.py scripts/test_fetch_stock_targets.py web/data/stock-targets.json data/consensus_history.json
git commit -m "feat(targets): 목표주가 수집 엔트리포인트 + 컨센서스 히스토리 누적"
```

---

### Task 4: 종목 뉴스 수집 + 중복 제거

**Files:**
- Create: `scripts/fetch_stock_news.py`
- Test: `scripts/test_fetch_stock_news.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_fetch_stock_news.py`:

```python
# 종목별 뉴스 수집의 중복 제거와 og:image 추출을 검증하는 테스트
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_stock_news as fsn

RSS = """<rss><channel>
<item><title>삼성전자 HBM4 공급 임박</title><link>https://a.com/1</link>
<pubDate>Fri, 18 Jul 2026 09:40:00 GMT</pubDate><source>이데일리</source></item>
<item><title>메모리 사이클 반등</title><link>https://a.com/2</link>
<pubDate>Fri, 18 Jul 2026 08:55:00 GMT</pubDate><source>한국경제</source></item>
</channel></rss>"""


def test_parse_rss_extracts_items():
    items = fsn.parse_rss(RSS)
    assert len(items) == 2
    assert items[0]["title"] == "삼성전자 HBM4 공급 임박"
    assert items[0]["url"] == "https://a.com/1"
    assert items[0]["source"] == "이데일리"


def test_merge_keeps_existing_summaries():
    # 이미 요약된 기사는 재요약하지 않는다 — Gemini 호출 비용이 여기서 결정된다
    old = [{"url": "https://a.com/1", "title": "옛 제목", "summary": "이미 요약됨",
            "thumb": "t.jpg", "time": "09:40", "source": "이데일리"}]
    new = [{"url": "https://a.com/1", "title": "삼성전자 HBM4 공급 임박",
            "time": "09:40", "source": "이데일리"},
           {"url": "https://a.com/2", "title": "메모리 사이클 반등",
            "time": "08:55", "source": "한국경제"}]
    merged, todo = fsn.merge(old, new)
    assert [m["url"] for m in merged] == ["https://a.com/1", "https://a.com/2"]
    assert merged[0]["summary"] == "이미 요약됨"
    assert merged[0]["thumb"] == "t.jpg"
    assert [t["url"] for t in todo] == ["https://a.com/2"]


def test_merge_caps_at_five():
    new = [{"url": f"https://a.com/{i}", "title": f"t{i}", "time": "09:00",
            "source": "s"} for i in range(8)]
    merged, _ = fsn.merge([], new)
    assert len(merged) == 5


def test_extract_og_image():
    html = '<meta property="og:image" content="https://img.com/a.jpg">'
    assert fsn.extract_og_image(html) == "https://img.com/a.jpg"


def test_extract_og_image_returns_none_when_absent():
    # 썸네일 없는 기사가 반드시 생긴다 — 폴백이 동작해야 한다
    assert fsn.extract_og_image("<html><body>no meta</body></html>") is None
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python3 -m pytest scripts/test_fetch_stock_news.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_stock_news'`

- [ ] **Step 3: 구현 작성**

`scripts/fetch_stock_news.py`:

```python
# 종목별 관련 뉴스를 RSS로 수집해 요약·썸네일을 붙여 위젯용 JSON을 만드는 스크립트
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "web" / "data" / "stock-news.json"
STOCKS = {"005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차"}
MAX_ITEMS = 5
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
RSS_URL = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"

_TAG = re.compile(r"<[^>]+>")


def _fetch(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")


def parse_rss(xml):
    """RSS에서 제목·링크·발행시각·언론사를 뽑는다. 날짜는 RSS가 보장한다."""
    out = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        b = m.group(1)
        t = re.search(r"<title>(.*?)</title>", b, re.S)
        l = re.search(r"<link>(.*?)</link>", b, re.S)
        p = re.search(r"<pubDate>(.*?)</pubDate>", b, re.S)
        s = re.search(r"<source[^>]*>(.*?)</source>", b, re.S)
        if not (t and l):
            continue
        when = ""
        if p:
            try:
                d = parsedate_to_datetime(p.group(1)).astimezone(KST)
                today = datetime.now(KST).date()
                when = d.strftime("%H:%M") if d.date() == today else "어제"
            except Exception:
                when = ""
        out.append({
            "title": _TAG.sub("", t.group(1)).strip(),
            "url": l.group(1).strip(),
            "time": when,
            "source": _TAG.sub("", s.group(1)).strip() if s else "",
        })
    return out


def merge(old, new):
    """기존 항목의 요약·썸네일을 보존하고, 신규 항목만 todo로 돌려준다."""
    by_url = {o["url"]: o for o in old}
    merged, todo = [], []
    for item in new[:MAX_ITEMS]:
        prev = by_url.get(item["url"])
        if prev and prev.get("summary"):
            merged.append({**item, "summary": prev["summary"],
                           "thumb": prev.get("thumb")})
        else:
            merged.append({**item, "summary": "", "thumb": None})
            todo.append(item)
    return merged, todo


def extract_og_image(html):
    """원문 og:image. 없으면 None — 프런트가 폴백 자리를 그린다."""
    m = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html)
         or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html))
    return m.group(1) if m else None
```

- [ ] **Step 4: 테스트 실행해 통과 확인**

Run: `python3 -m pytest scripts/test_fetch_stock_news.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/fetch_stock_news.py scripts/test_fetch_stock_news.py
git commit -m "feat(stock-news): 종목 뉴스 RSS 파싱·중복 제거·og:image 추출 추가"
```

---

### Task 5: 뉴스 요약(Gemini) + 엔트리포인트

기존 `fetch_news_live.py`의 Gemini 호출 방식을 그대로 따른다. **신규 기사만** 요약해 호출량을 억제한다.

**Files:**
- Modify: `scripts/fetch_stock_news.py`
- Test: `scripts/test_fetch_stock_news.py`

- [ ] **Step 1: 실패하는 테스트 추가**

```python
def test_build_prompt_lists_all_titles():
    items = [{"title": "제목A", "source": "S1"}, {"title": "제목B", "source": "S2"}]
    p = fsn.build_prompt("삼성전자", items)
    assert "제목A" in p and "제목B" in p
    assert "삼성전자" in p
    assert "해요체" in p          # 기존 운영 규칙과 동일한 어조 고정
    assert "JSON" in p


def test_apply_summaries_matches_by_index():
    merged = [{"url": "u1", "summary": ""}, {"url": "u2", "summary": "기존"}]
    todo = [{"url": "u1"}]
    fsn.apply_summaries(merged, todo, ["새 요약이에요."])
    assert merged[0]["summary"] == "새 요약이에요."
    assert merged[1]["summary"] == "기존"


def test_apply_summaries_tolerates_short_response():
    # Gemini가 요청보다 적게 돌려줘도 죽지 않아야 한다
    merged = [{"url": "u1", "summary": ""}, {"url": "u2", "summary": ""}]
    todo = [{"url": "u1"}, {"url": "u2"}]
    fsn.apply_summaries(merged, todo, ["하나만 왔어요."])
    assert merged[0]["summary"] == "하나만 왔어요."
    assert merged[1]["summary"] == ""
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `python3 -m pytest scripts/test_fetch_stock_news.py -k "prompt or summaries" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'build_prompt'`

- [ ] **Step 3: 구현 추가**

`scripts/fetch_stock_news.py` 끝에 추가:

```python
import os
import sys

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "gemini-2.5-flash-lite:generateContent")


def build_prompt(name, items):
    lines = "\n".join(f"{i+1}. {it['title']} ({it['source']})"
                      for i, it in enumerate(items))
    return (
        f"다음은 {name} 관련 뉴스 제목 목록이에요.\n{lines}\n\n"
        f"각 제목마다 한 문장 요약을 만들어 주세요.\n"
        f"규칙:\n"
        f"- 반드시 해요체로 끝맺어요.\n"
        f"- 제목에 없는 수치·날짜·목표주가를 새로 만들지 않아요.\n"
        f"- 각 요약은 60자 이내로 해요.\n"
        f"- 출력은 JSON 배열 문자열만 내보내요. 예: [\"...\", \"...\"]\n"
    )


def summarize(name, items):
    """신규 기사만 요약한다. 실패하면 빈 리스트 — 섹션은 제목만으로도 동작한다."""
    if not items or not GEMINI_KEY:
        return []
    body = json.dumps({"contents": [{"parts": [{"text": build_prompt(name, items)}]}]})
    req = urllib.request.Request(
        f"{GEMINI_URL}?key={GEMINI_KEY}", data=body.encode(),
        headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
        txt = r["candidates"][0]["content"]["parts"][0]["text"]
        m = re.search(r"\[[\s\S]*\]", txt)
        return json.loads(m.group(0)) if m else []
    except Exception as e:
        print(f"  ! 요약 실패 {name}: {e}", file=sys.stderr)
        return []


def apply_summaries(merged, todo, summaries):
    """todo 순서대로 요약을 채운다. 응답이 짧으면 남은 건 빈 문자열로 둔다."""
    by_url = {m["url"]: m for m in merged}
    for i, item in enumerate(todo):
        if i < len(summaries) and item["url"] in by_url:
            by_url[item["url"]]["summary"] = str(summaries[i]).strip()


def main():
    old_all = {}
    if OUT_JSON.exists():
        old_all = json.loads(OUT_JSON.read_text(encoding="utf-8") or "{}").get("stocks", {})

    out = {"updated_at": datetime.now(KST).isoformat(), "stocks": {}}
    for code, name in STOCKS.items():
        try:
            items = parse_rss(_fetch(RSS_URL.format(q=urllib.parse.quote(name))))
        except Exception as e:
            print(f"  ! RSS 실패 {name}: {e}", file=sys.stderr)
            out["stocks"][code] = old_all.get(code, [])   # 기존 데이터 보존
            continue
        merged, todo = merge(old_all.get(code, []), items)
        apply_summaries(merged, todo, summarize(name, todo))
        for it in todo:
            target = next((m for m in merged if m["url"] == it["url"]), None)
            if target is None:
                continue
            try:
                target["thumb"] = extract_og_image(_fetch(it["url"], timeout=10))
            except Exception:
                target["thumb"] = None
        out["stocks"][code] = merged
        print(f"  {name}: {len(merged)}건 (신규 {len(todo)}건 요약)")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {OUT_JSON}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 + 실제 수집 검증**

Run: `python3 -m pytest scripts/test_fetch_stock_news.py -v`
Expected: PASS (8 passed)

Run: `python3 scripts/fetch_stock_news.py`
Expected: 3종목 각각 `5건 (신규 5건 요약)` 출력 후 `✅ .../stock-news.json`

Run: `python3 scripts/fetch_stock_news.py`
Expected: 두 번째 실행은 `신규 0건 요약` — dedupe가 작동해 Gemini를 다시 부르지 않는다

- [ ] **Step 5: 커밋**

```bash
git add scripts/fetch_stock_news.py scripts/test_fetch_stock_news.py web/data/stock-news.json
git commit -m "feat(stock-news): Gemini 요약·썸네일 수집 엔트리포인트 추가"
```

---

### Task 6: 위젯 마크업·CSS 교체

프로토타입 `docs/prototypes/2026-07-18-kospi-leaders-layout-v6.html`의 마크업·CSS를 실제 위젯에 이식한다. **기존 타일 3개와 `usw-pill`·`usw-sub` 클래스명은 유지**해야 `setNight()`가 계속 동작한다.

**Files:**
- Modify: `web/stocks/index.html` (위젯 인라인 블록 — `#us-linked-widget` 정의부, 약 813행)

- [ ] **Step 1: 현재 위젯 구조 확인**

Run: `grep -n "why-moved\|usw-tiles\|usw-pill\|usw-sub\|wm-grid" web/stocks/index.html | head -20`
Expected: `#why-moved`·`.wm-grid` 등 기존 곡선/지표 블록 위치가 출력된다. 이 영역이 교체 대상이다.

- [ ] **Step 2: `#why-moved` 내부를 2×2 구조로 교체**

`#why-moved` 안의 `.wm-grid` 블록을 아래로 교체한다. **`.usw-pill`·`.usw-sub`가 들어있는 상단 타일 영역은 손대지 않는다.**

```html
<div class="lw-row">
  <div class="lw-l lw-chart">
    <div class="lw-h">📈 <span id="wm-name">삼성전자</span>
      <span class="ds-date"></span> 장중
      <span class="lw-live">● 실측 1분봉</span></div>
    <svg id="wm-svg" viewBox="0 0 640 200" role="img" aria-label="장중 1분봉 곡선"></svg>
    <div class="lw-hint" id="lw-hint"></div>
  </div>
  <div class="lw-r">
    <div class="lw-h">📊 장중 지표<span class="lw-note">당일</span></div>
    <div id="wm-metrics"></div>
    <div class="lw-moved">평균체결가(VWAP)·외국인 보유율은
      <a id="lw-detail-link" href="#">종목 상세</a>에서 볼 수 있어요.</div>
  </div>
</div>

<div class="lw-row">
  <div class="lw-l">
    <div class="lw-h">📰 관련 뉴스<span class="lw-note" id="lw-upd">최신순 · 30분 주기</span></div>
    <div class="lw-news" id="lw-news"></div>
  </div>
  <div class="lw-r">
    <div class="lw-h">🎯 증권사 목표주가<span class="lw-note" id="lw-tp-cnt"></span></div>
    <div class="lw-tp-hero">
      <span class="lbl">컨센서스</span><span class="val" id="lw-tp-val">—</span>
      <span class="lw-tp-up" id="lw-tp-up"></span>
    </div>
    <div class="lw-tp-meta" id="lw-tp-meta"></div>
    <div class="lw-gauge"><div class="cur" id="lw-tp-cur" style="width:0%"></div></div>
    <div id="lw-brk"></div>
    <div class="lw-tr" id="lw-tr" style="display:none">
      <div class="lw-tr-h">컨센서스 추이<span class="d" id="lw-tr-d"></span></div>
      <svg id="lw-tr-svg" viewBox="0 0 240 60"></svg>
    </div>
  </div>
</div>

<div class="lw-ib" id="lw-ib" style="display:none">
  <div class="lw-ib-h"><span class="bar"></span><span class="t">🏦 외국계 시각</span>
    <span class="n">코스피 · 최근 24시간</span></div>
  <div class="lw-ib-note">개별 종목이 아닌 <b>코스피 지수 전반</b>에 대한 외국계 IB 코멘트예요.</div>
  <div id="lw-ib-list"></div>
</div>
```

- [ ] **Step 3: CSS 추가**

`#us-linked-widget` 스타일 블록 끝에 아래를 추가한다. 프로토타입 v6의 클래스명을 `lw-` 접두사로 옮긴 것이다.

```css
#why-moved .lw-row{display:flex;flex-wrap:wrap;gap:18px;align-items:flex-start}
#why-moved .lw-row + .lw-row{margin-top:16px;padding-top:16px;border-top:1px solid #F1F5F9}
#why-moved .lw-l{flex:1.55 1 330px;min-width:0}
#why-moved .lw-r{flex:1 1 240px;min-width:0;border-left:1px solid #F1F5F9;padding-left:18px}
@media(max-width:700px){#why-moved .lw-r{flex:0 0 100%;border-left:none;padding-left:0;
  border-top:1px solid #F1F5F9;padding-top:14px}}
#why-moved .lw-h{font-size:12px;font-weight:800;display:flex;align-items:center;gap:6px;margin-bottom:10px;color:#0F172A}
#why-moved .lw-note{margin-left:auto;font-size:10.5px;font-weight:700;color:#94A3B8}
#why-moved .lw-live{font-size:10px;font-weight:800;color:#E03131;background:#FEF2F2;border-radius:999px;padding:2px 7px}
#why-moved .lw-chart svg{width:100%;height:auto;display:block;overflow:visible}
#why-moved .lw-hint{font-size:10.5px;color:#94A3B8;margin-top:4px}
#why-moved .lw-moved{font-size:10.5px;color:#94A3B8;margin-top:9px;line-height:1.5}
#why-moved .lw-moved a{color:#2775ED;font-weight:700;text-decoration:none}
#why-moved .lw-tp-hero{display:flex;align-items:baseline;gap:7px}
#why-moved .lw-tp-hero .lbl{font-size:11px;font-weight:700;color:#94A3B8}
#why-moved .lw-tp-hero .val{font-size:16px;font-weight:800;color:#334155;font-variant-numeric:tabular-nums}
#why-moved .lw-tp-up{font-size:11.5px;font-weight:800;color:#E03131}
#why-moved .lw-tp-meta{font-size:10.5px;color:#94A3B8;margin-top:3px}
#why-moved .lw-gauge{position:relative;height:5px;border-radius:4px;background:#F1F5F9;margin:10px 0 12px;overflow:hidden}
#why-moved .lw-gauge .cur{position:absolute;left:0;top:0;height:100%;border-radius:4px;background:#94A3B8}
#why-moved .lw-brk{display:flex;align-items:center;gap:8px;padding:6.5px 0;border-top:1px solid #F1F5F9}
#why-moved .lw-brk:first-of-type{border-top:none}
#why-moved .lw-brk .f{font-size:12px;font-weight:700;min-width:62px;color:#334155}
#why-moved .lw-brk .o{font-size:9.5px;font-weight:800;color:#16A34A;background:#ECFDF3;border-radius:5px;padding:1px 6px}
#why-moved .lw-brk .o.neu{color:#94A3B8;background:#F1F5F9}
#why-moved .lw-brk .t{margin-left:auto;font-size:12.5px;font-weight:800;font-variant-numeric:tabular-nums}
#why-moved .lw-brk .d{font-size:10px;color:#94A3B8;min-width:34px;text-align:right}
#why-moved .lw-tr{background:#F7F9FC;border:1px solid #E5E7EB;border-radius:11px;padding:10px 12px 8px;margin-top:13px}
#why-moved .lw-tr-h{display:flex;align-items:baseline;font-size:10.5px;font-weight:800;color:#334155}
#why-moved .lw-tr-h .d{margin-left:auto;font-size:11px;font-weight:800}
#why-moved .lw-tr svg{width:100%;height:auto;display:block;margin-top:5px}
#why-moved .lw-news a{display:flex;gap:11px;text-decoration:none;color:inherit;padding:10px 0;border-top:1px solid #F1F5F9}
#why-moved .lw-news a:first-child{border-top:none}
#why-moved .lw-news .nt{font-size:10.5px;font-weight:700;color:#94A3B8}
#why-moved .lw-news .nh{font-size:12.5px;font-weight:800;line-height:1.4;margin:3px 0 4px;color:#0F172A}
#why-moved .lw-news a:hover .nh{color:#2775ED}
#why-moved .lw-news .ns{font-size:11.5px;color:#334155;line-height:1.5;margin-bottom:4px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
#why-moved .lw-news .nsrc{font-size:10.5px;color:#94A3B8}
#why-moved .lw-news .nimg{flex:0 0 74px;width:74px;height:56px;border-radius:8px;object-fit:cover;
  background:#F1F5F9;border:1px solid #E5E7EB;margin-top:14px}
#why-moved .lw-ib{margin-top:16px;padding-top:15px;border-top:2px solid #F1F5F9}
#why-moved .lw-ib-h{display:flex;align-items:center;gap:7px;margin-bottom:4px}
#why-moved .lw-ib-h .bar{width:3px;height:14px;border-radius:2px;background:#2775ED}
#why-moved .lw-ib-h .t{font-size:13px;font-weight:800;color:#0F172A}
#why-moved .lw-ib-h .n{margin-left:auto;font-size:10.5px;font-weight:700;color:#94A3B8}
#why-moved .lw-ib-note{font-size:10.5px;color:#94A3B8;margin-bottom:9px}
#why-moved .lw-ib-row{display:flex;gap:11px;align-items:flex-start;padding:11px 0;border-top:1px solid #F1F5F9}
#why-moved .lw-ib-row .lg{flex:0 0 40px;height:40px;border-radius:9px;background:#F1F5F9;
  display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;color:#334155}
#why-moved .lw-ib-row .bd{flex:1 1 auto;min-width:0}
#why-moved .lw-ib-row .nm{font-size:12.5px;font-weight:800;color:#0F172A}
#why-moved .lw-ib-row .tg{font-size:9.5px;font-weight:800;border-radius:5px;padding:1px 7px;margin-left:6px}
#why-moved .lw-ib-row .tg.bull{color:#E03131;background:#FEF2F2}
#why-moved .lw-ib-row .tg.bear{color:#2775ED;background:#EFF4FE}
#why-moved .lw-ib-row .tg.neu{color:#94A3B8;background:#F1F5F9}
#why-moved .lw-ib-row .tx{font-size:11.5px;color:#334155;line-height:1.55;margin:4px 0 5px}
#why-moved .lw-ib-row .sr{font-size:10.5px;color:#2775ED;font-weight:700;text-decoration:none}
#why-moved .lw-ib-row .tm{flex:0 0 auto;font-size:10.5px;color:#94A3B8;text-align:right}
```

- [ ] **Step 3b: 죽은 CSS 정리**

교체로 더 이상 쓰이지 않게 된 `.wm-grid`·`.wm-left`·`.wm-right`·`.wm-bell-tk`·`.wm-card-h` 규칙을 삭제한다. **`#wm-svg`·`#wm-name`·`.wm-h`·`.wm-toggle`은 남긴다** (곡선·접기 토글이 계속 쓴다).

Run: `grep -n "wm-grid\|wm-left\|wm-right\|wm-bell\|wm-card" web/stocks/index.html`
Expected: 삭제 후 0건

- [ ] **Step 4: 렌더 확인**

브라우저에서 `web/stocks/index.html`을 열고 위젯 영역을 확인한다. 이 시점에는 JS 배선 전이라 **빈 골격만 보이는 게 정상**이다. 콘솔 에러가 없어야 한다.

Expected: 타일 3개는 기존대로 가격 표시, 하단은 헤더만 있고 내용은 비어 있음, 콘솔 에러 없음

- [ ] **Step 5: 커밋**

```bash
git add web/stocks/index.html
git commit -m "refactor(stocks): 주도주 위젯을 2×2 구조로 마크업·CSS 교체"
```

---

### Task 7: 위젯 JS 배선

**Files:**
- Modify: `web/stocks/index.html` (위젯 인라인 `<script>` — `usSel()` 근처, 약 815행 및 2880~2950행)

- [ ] **Step 1: 데이터 로더 + 렌더러 추가**

위젯 `<script>` 블록에 아래를 추가한다.

```javascript
/* 주도주 위젯 — 목표주가·뉴스·외국계 시각 렌더러 */
var LW = { targets:null, news:null, ib:null };

function lwNum(n){ return (n==null) ? '—' : Number(n).toLocaleString('ko-KR'); }

function lwRenderTargets(code){
  var box = LW.targets && LW.targets.stocks && LW.targets.stocks[code];
  var cntEl=document.getElementById('lw-tp-cnt');
  if(!box){ if(cntEl) cntEl.textContent='수집 중'; return; }
  var close = box.close_price || null;
  var hist = box.history || [];
  // 추이 그래프가 뜨면 리포트 8건, 숨겨지면 10건으로 늘려 우측 여백을 메운다
  var reports = box.reports.slice(0, hist.length >= 20 ? 8 : 10);
  cntEl.textContent = '리포트 ' + reports.length + '건';
  document.getElementById('lw-tp-val').textContent = lwNum(box.consensus);
  var upEl=document.getElementById('lw-tp-up');
  if(box.consensus && close){
    var pct=((box.consensus-close)/close*100);
    upEl.textContent=(pct>=0?'+':'')+pct.toFixed(1)+'%';
    document.getElementById('lw-tp-cur').style.width=Math.max(0,Math.min(100,close/box.consensus*100))+'%';
  } else { upEl.textContent=''; document.getElementById('lw-tp-cur').style.width='0%'; }
  document.getElementById('lw-tp-meta').textContent =
    (close? '종가 '+lwNum(close)+' 기준 · ':'') + '3개월 '+box.firm_count+'개사 평균';
  document.getElementById('lw-brk').innerHTML = reports.map(function(r){
    var neu = (r.opinion && /중립|Hold|Neutral/i.test(r.opinion)) ? ' neu' : '';
    return '<div class="lw-brk"><span class="f">'+r.firm+'</span>'+
      (r.opinion?'<span class="o'+neu+'">'+r.opinion+'</span>':'')+
      '<span class="t">'+lwNum(r.target_price)+'</span>'+
      '<span class="d">'+r.date.slice(3).replace('.','/')+'</span></div>';
  }).join('');
  lwDrawTrend(hist);
}

function lwDrawTrend(hist){
  var wrap=document.getElementById('lw-tr');
  if(!hist || hist.length < 20){ wrap.style.display='none'; return; }  // 숨김 게이트
  wrap.style.display='';
  var p=hist.map(function(h){return h.value;});
  var W=240,H=60,PT=8,PB=14,PL=4,PR=4;
  var mn=Math.min.apply(null,p), mx=Math.max.apply(null,p), span=(mx-mn)||1;
  var X=function(i){return PL+(W-PL-PR)*(i/(p.length-1));};
  var Y=function(v){return PT+(H-PT-PB)*(1-(v-mn)/span);};
  var line=p.map(function(v,i){return X(i).toFixed(1)+','+Y(v).toFixed(1);}).join(' ');
  var rising=p[p.length-1]>=p[0];
  var col=rising?'#E03131':'#2775ED', fill=rising?'rgba(224,49,49,.12)':'rgba(39,117,237,.12)';
  var base=H-PB;
  document.getElementById('lw-tr-svg').innerHTML=
    '<polygon points="'+X(0)+','+base+' '+line+' '+X(p.length-1)+','+base+'" fill="'+fill+'"/>'+
    '<polyline points="'+line+'" fill="none" stroke="'+col+'" stroke-width="1.8" stroke-linejoin="round"/>'+
    '<circle cx="'+X(p.length-1)+'" cy="'+Y(p[p.length-1])+'" r="2.8" fill="'+col+'"/>'+
    '<text x="'+PL+'" y="'+(H-3)+'" font-size="9" fill="#94A3B8" font-weight="600">'+lwNum(p[0])+'</text>'+
    '<text x="'+(W-PR)+'" y="'+(H-3)+'" font-size="9" fill="#94A3B8" font-weight="600" text-anchor="end">'+lwNum(p[p.length-1])+'</text>';
  var pct=((p[p.length-1]-p[0])/p[0]*100);
  var d=document.getElementById('lw-tr-d');
  d.textContent=(pct>=0?'+':'')+pct.toFixed(1)+'%';
  d.style.color=col;
  wrap.querySelector('.lw-tr-h').firstChild.textContent='컨센서스 추이 · '+p.length+'거래일';
}

function lwRenderNews(code){
  var list = LW.news && LW.news.stocks && LW.news.stocks[code];
  var el=document.getElementById('lw-news');
  if(!list || !list.length){ el.innerHTML='<div style="font-size:11.5px;color:#94A3B8;padding:8px 0">수집된 뉴스가 없어요.</div>'; return; }
  el.innerHTML=list.map(function(n){
    var img = n.thumb ? '<img class="nimg" src="'+n.thumb+'" alt="" loading="lazy" '+
              'onerror="this.style.visibility=\'hidden\'">' : '';
    return '<a href="'+n.url+'" target="_blank" rel="noopener">'+
      '<div style="flex:1 1 auto;min-width:0"><div class="nt">'+(n.time||'')+'</div>'+
      '<div class="nh">'+n.title+'</div>'+
      (n.summary?'<div class="ns">'+n.summary+'</div>':'')+
      '<div class="nsrc">'+(n.source||'')+'</div></div>'+img+'</a>';
  }).join('');
}

function lwRenderIB(){
  var views = LW.ib && LW.ib.views;
  var wrap=document.getElementById('lw-ib');
  if(!views || !views.length){ wrap.style.display='none'; return; }  // 없으면 섹션 생략
  wrap.style.display='';
  document.getElementById('lw-ib-list').innerHTML=views.map(function(v){
    var tag = (v.stance==='bull'?'bull':v.stance==='bear'?'bear':'neu');
    var label = (tag==='bull'?'강세':tag==='bear'?'약세':'중립');
    return '<div class="lw-ib-row"><div class="lg">'+(v.house||'').slice(0,4)+'</div>'+
      '<div class="bd"><div><span class="nm">'+(v.house||'')+'</span>'+
      '<span class="tg '+tag+'">'+label+'</span></div>'+
      '<div class="tx">'+(v.summary||'')+'</div>'+
      (v.url?'<a class="sr" href="'+v.url+'" target="_blank" rel="noopener">'+(v.source||'원문')+' →</a>':'')+
      '</div><div class="tm">'+(v.time_label||'')+'</div></div>';
  }).join('');
}

function lwRenderAll(code){ lwRenderTargets(code); lwRenderNews(code); }

function lwLoad(){
  var j=function(u){ return fetch(u,{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;}); };
  Promise.all([j('/data/stock-targets.json'), j('/data/stock-news.json'), j('/data/ib_korea_views.json')])
    .then(function(res){
      LW.targets=res[0]; LW.news=res[1]; LW.ib=res[2];
      lwRenderAll(window.__uswCode || '005930');
      lwRenderIB();
    });
}
window.addEventListener('load', lwLoad);
```

- [ ] **Step 2: 탭 전환에 렌더러 연결**

기존 `usSel(code)` 함수 본문 끝에 아래 두 줄을 추가한다.

```javascript
  window.__uswCode = code;
  if (typeof lwRenderAll === 'function') lwRenderAll(code);
```

- [ ] **Step 3: 마감 후 안내 문구 연결**

기존 `setNight(on)` 함수 본문 끝에 아래를 추가한다. **곡선 타이틀·시간축은 바꾸지 않는다** — 곡선은 항상 직전 정규장 1분봉이다.

```javascript
  var hint=document.getElementById('lw-hint');
  if(hint) hint.textContent = on
    ? '※ 곡선은 한국거래소 1분봉이라 24h가 없어요. 마감 후에도 직전 정규장 흐름을 보여줘요.'
    : '';
  var upd=document.getElementById('lw-upd');
  if(upd) upd.textContent = on ? '최신순 · 1시간 주기' : '최신순 · 30분 주기';
```

- [ ] **Step 4: 브라우저 검증**

`web/stocks/index.html`을 열고 확인한다.

Expected:
- 탭 3개를 각각 눌렀을 때 목표주가·리포트 리스트·뉴스가 종목별로 바뀐다
- 컨센서스 추이 박스는 **숨겨져 있다** (히스토리 20점 미만이므로 정상)
- 외국계 시각 섹션이 `ib_korea_views.json` 내용으로 채워진다 (없으면 섹션 자체가 사라진다)
- 타일 가격·`●실시간`/`🌙 HL 24h` 뱃지는 기존과 동일하게 동작한다
- 콘솔 에러 없음

- [ ] **Step 5: 커밋**

```bash
git add web/stocks/index.html
git commit -m "feat(stocks): 주도주 위젯에 목표주가·뉴스·외국계 시각 배선"
```

---

### Task 8: 워크플로우 스케줄 배선

**GHA 분 예산 제약이 이 태스크의 설계를 결정한다.** private repo라 무료 2,000분/월이므로 **새 잡을 만들지 않는다.** 기존 잡에 스텝을 얹고, 기존 스케줄이 안 덮는 창(평일 06~09, 주말)만 크론을 추가한다.

**Files:**
- Modify: `.github/workflows/daily_report.yml`
- Modify: `.github/workflows/kospi-news-live.yml`

- [ ] **Step 1: 목표주가 수집을 기존 잡 2곳에 추가**

`daily_report.yml`의 `kospi-briefing` 잡에서 `fetch_news.py` 다음, `call_claude.py` 앞에 추가:

```yaml
      - name: 🎯 증권사 목표주가 수집 (개장 전)
        continue-on-error: true
        run: python3 scripts/fetch_stock_targets.py
```

같은 파일의 `kospi-close-briefing` 잡에서 `fetch_research_reports.py` 다음에 동일 스텝을 추가하되 이름만 바꾼다:

```yaml
      - name: 🎯 증권사 목표주가 수집 (마감 후)
        continue-on-error: true
        run: python3 scripts/fetch_stock_targets.py
```

> `continue-on-error: true` — 목표주가 수집이 실패해도 브리핑 발행 자체는 막지 않는다(기존 `fetch_research_reports.py`와 동일 정책).

- [ ] **Step 2: 커밋 대상에 산출물 포함 확인**

두 잡의 커밋 스텝이 `git add web/ data/`로 넓게 잡고 있으므로 `web/data/stock-targets.json`·`data/consensus_history.json`이 자동 포함된다.

Run: `grep -n "git add web/ data/" .github/workflows/daily_report.yml`
Expected: 최소 2건 (kospi-briefing, kospi-close-briefing)

> ⚠️ `SERVICE_RULES.md` §18 참조 — 다른 워크플로우가 소유한 파일을 함께 커밋하면 rebase 충돌이 난다. `stock-targets.json`·`consensus_history.json`은 **이 두 잡만** 쓰므로 안전하다. `stock-news.json`은 `kospi-news-live.yml`이 소유하므로 **daily_report.yml에서 커밋하면 안 된다** — 아래 Step 4에서 제외 처리한다.

- [ ] **Step 3: 종목 뉴스를 기존 뉴스 잡에 추가**

`kospi-news-live.yml`에서 `fetch_news_live.py` 실행 스텝 다음에 추가:

```yaml
      - name: 📰 종목별 관련 뉴스 수집
        continue-on-error: true
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python3 scripts/fetch_stock_news.py
```

- [ ] **Step 4: daily_report.yml에서 stock-news.json 충돌 차단**

`daily_report.yml`의 세 브리핑 잡 커밋 스텝에서, 기존 `git checkout -- web/data/movers-why-*.json` 줄 바로 뒤에 추가한다:

```bash
          git checkout -- web/data/stock-news.json 2>/dev/null || true
```

> 이유는 `SERVICE_RULES.md` §18과 동일하다. `stock-news.json`의 소유자는 `kospi-news-live.yml`이고, 두 워크플로우가 같은 파일을 각자 재생성하면 rebase가 매번 충돌한다. pathspec 제외만으로는 부족하고 **워킹트리를 되돌려야** rebase가 동작한다.

- [ ] **Step 5: 신규 스케줄 창 추가**

`kospi-news-live.yml`의 `on.schedule`에 아래 두 크론을 추가한다. GHA 크론은 **UTC** 기준이다.

```yaml
    # 평일 06:00~09:00 KST (= 21:00~24:00 UTC 전일) — 조간·개장 전, 실측상 장중 다음으로 밀도 높음
    - cron: '0 21,22,23 * * 0-4'
    # 주말 08:00~20:00 KST 3시간 간격 (= 23:00 UTC 금 ~ 11:00 UTC 토/일)
    - cron: '0 23 * * 5,6'
    - cron: '0 2,5,8,11 * * 6,0'
```

- [ ] **Step 6: 워크플로우 문법 검증**

Run: `python3 -c "import yaml;[yaml.safe_load(open(f)) for f in ['.github/workflows/daily_report.yml','.github/workflows/kospi-news-live.yml']];print('YAML OK')"`
Expected: `YAML OK`

Run: `grep -c "cron:" .github/workflows/kospi-news-live.yml`
Expected: 기존 개수 + 3

- [ ] **Step 7: 커밋**

```bash
git add .github/workflows/daily_report.yml .github/workflows/kospi-news-live.yml
git commit -m "ci: 목표주가·종목뉴스 수집 스텝과 개장전·주말 스케줄 추가"
```

---

## 배포 후 확인 사항

- [ ] 첫 실행 후 `web/data/stock-targets.json`의 `history`가 `[]`인지 확인 (20점 미만이라 정상). 약 1개월 뒤 추이 그래프가 자동으로 나타난다.
- [ ] 2주 뒤 `kospi-news-live` 잡 로그에서 **주말 실행의 `신규 N건 요약`** 값을 확인해 주말 주기(3시간)를 재조정한다. 계속 0건이면 1일 2회로 줄인다.
- [ ] GHA 사용량을 월말에 확인한다. 2,000분에 근접하면 주말 크론부터 줄인다.
- [ ] 썸네일이 언론사 로고로만 채워지는 비율이 높으면, 로고 URL 패턴(`logo`, `sns`, `default` 등 포함)을 걸러 `thumb=None` 처리하는 필터를 추가한다.

---

## 이 계획이 하지 않는 것 (의도적 제외)

- **핫링킹 캐싱** — 프로토타입 검토 때 언급한 `web/data/thumbs/` 캐싱은 이번 범위에서 뺐다. 먼저 `og:image` 직접 링크로 배포해 실제 차단률을 측정하고, 문제가 확인되면 그때 캐싱을 추가하는 게 맞다. 지금 넣으면 저장소 용량과 커밋 부피만 늘린다.
- **코스피 목표지수** — 정형 소스가 없어 제외했다. 외국계 시각 섹션이 그 역할을 대신한다.
- **VWAP·외국인 보유율** — 위젯에서 빼고 종목 상세로 안내 링크만 남긴다. 상세 페이지에는 이미 구현돼 있다.
