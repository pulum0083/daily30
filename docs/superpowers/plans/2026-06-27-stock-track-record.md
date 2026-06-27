# 종목 트랙레코드(A) + 적중률(B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 상세 페이지에 "더블샷 AI 픽 트랙레코드"(이 종목 픽 이력 + 픽 이후 실측 채점)와 "브리핑 적중률" 섹션을 추가한다. 둘 다 인하우스 데이터, 칩보드 무관.

**Architecture:** 순수 함수 모듈(`scripts/stock_track_record.py`)이 (1) 브리핑 스냅샷에서 종목 픽을 채굴하고, (2) 네이버 일봉(날짜+종가)으로 목표 도달/손절/진행 중을 채점하고, (3) briefings.json에서 코스피·미국 적중률을 집계한다. 네트워크 호출은 의존성 주입(`fetch_closes` 콜백)으로 분리해 단위 테스트한다. `generate_html.py`의 `build_stock_page`가 이 결과를 ctx에 주입하고, `detail.html` 템플릿이 두 섹션을 렌더한다(데이터 없으면 자동 숨김).

**Tech Stack:** Python 3, pytest 8.4.2, Jinja2, 네이버 일봉 API(`api.stock.naver.com`), 기존 `generate_html.py --stocks` 파이프라인

설계 문서: `docs/superpowers/specs/2026-06-27-stock-detail-redesign-design.md`
검증 프로토: `web/stocks/005930-proto/index.html`

---

## 파일 변경 목록

| 파일 | 역할 | 변경 |
| --- | --- | --- |
| `scripts/stock_track_record.py` | 픽 채굴·채점·적중률 순수 모듈 | **신규** |
| `scripts/test_stock_track_record.py` | 단위 테스트 | **신규** |
| `scripts/generate_html.py` (`build_stock_page` ~950) | ctx에 track_record·accuracy 주입 | 수정 |
| `scripts/templates/stocks/detail.html` | A·B 섹션 추가(프로토 마크업) | 수정 |
| `web/assets/stocks.css` | A·B 섹션 스타일(프로토 인라인 이관) | 수정 |

> 범위: 트랙레코드(A) + 적중률(B)만. 시그널(C)·실측지표 재설계·네이버 목표가/영업이익·칩보드 청소는 후속 계획.
> 데이터 흐름 검증된 사실: 픽 `entry/target/stop` 포맷 `"340,000원"`·`"$1,077"`(범위형 `"320,000~325,000원"` 존재). 네이버 일봉 `{"localDate":"20260625","closePrice":358500.0}`. KR 상세 페이지는 6자리 코드라 KR 픽만 매칭(US 티커는 매칭 안 됨).

---

## Task 1: 가격 문자열 파서

**Files:**
- Create: `scripts/stock_track_record.py`
- Test: `scripts/test_stock_track_record.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_stock_track_record.py`:

```python
# 종목 트랙레코드 모듈 테스트
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stock_track_record import parse_price


def test_parse_price_won():
    assert parse_price("340,000원") == 340000.0


def test_parse_price_dollar():
    assert parse_price("$1,077") == 1077.0


def test_parse_price_range_midpoint():
    assert parse_price("320,000~325,000원") == 322500.0


def test_parse_price_none():
    assert parse_price("") is None
    assert parse_price(None) is None
    assert parse_price("미정") is None
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q`
Expected: FAIL — `ModuleNotFoundError` 또는 `ImportError: cannot import name 'parse_price'`

- [ ] **Step 3: 최소 구현**

`scripts/stock_track_record.py` (파일 첫 줄은 한국어 헤더 주석):

```python
# 종목 픽 트랙레코드 채굴·채점 + 브리핑 적중률 집계 (전부 인하우스 실측)
import re
import json
import glob
import os


def parse_price(s):
    """'340,000원'→340000.0, '$1,077'→1077.0, '320,000~325,000원'→범위 중앙값. 못 읽으면 None."""
    if not s:
        return None
    nums = re.findall(r"[\d,]+(?:\.\d+)?", str(s))
    vals = []
    for n in nums:
        n = n.replace(",", "")
        if n:
            try:
                vals.append(float(n))
            except ValueError:
                pass
    if not vals:
        return None
    if len(vals) >= 2:
        return (vals[0] + vals[1]) / 2  # 범위형 → 중앙값
    return vals[0]
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/stock_track_record.py scripts/test_stock_track_record.py
git commit -m "feat(종목): 트랙레코드 가격 파서 parse_price"
```

---

## Task 2: 픽 채굴 (mine_picks)

**Files:**
- Modify: `scripts/stock_track_record.py`
- Test: `scripts/test_stock_track_record.py`

- [ ] **Step 1: 실패하는 테스트 작성** (테스트 파일에 픽스처 + 테스트 추가)

```python
import os
import json
from stock_track_record import mine_picks


def _write_snapshot(tmp_path, date, btype, picks):
    d = tmp_path / "web" / "briefings" / date / btype
    d.mkdir(parents=True, exist_ok=True)
    (d / "analysis_snapshot.json").write_text(
        json.dumps({"stock_picks": picks}, ensure_ascii=False), encoding="utf-8"
    )


def test_mine_picks_matches_code_sorted_by_date(tmp_path):
    _write_snapshot(tmp_path, "2026-06-16", "kospi", [
        {"ticker": "005930", "name": "삼성전자", "signal": "20일선 위 강세",
         "scenario_tag": "반도체 랠리", "entry": "337,000원", "target": "357,000원", "stop": "323,000원"},
        {"ticker": "000660", "name": "SK하이닉스", "entry": "1원", "target": "2원", "stop": "0원"},
    ])
    _write_snapshot(tmp_path, "2026-06-15", "kospi", [
        {"ticker": "005930", "name": "삼성전자", "signal": "20일선 상향 돌파",
         "scenario_tag": "AI칩 반사이익", "entry": "322,500원", "target": "360,000원", "stop": "305,000원"},
    ])
    picks = mine_picks("005930", snapshots_dir=str(tmp_path / "web" / "briefings"))
    assert len(picks) == 2
    assert picks[0]["date"] == "2026-06-15"   # 날짜 오름차순
    assert picks[1]["date"] == "2026-06-16"
    assert picks[0]["btype"] == "kospi"
    assert picks[0]["target"] == "360,000원"


def test_mine_picks_no_match_returns_empty(tmp_path):
    _write_snapshot(tmp_path, "2026-06-15", "kospi", [
        {"ticker": "000660", "name": "SK하이닉스", "entry": "1원", "target": "2원", "stop": "0원"},
    ])
    assert mine_picks("005930", snapshots_dir=str(tmp_path / "web" / "briefings")) == []
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q -k mine_picks`
Expected: FAIL — `ImportError: cannot import name 'mine_picks'`

- [ ] **Step 3: 최소 구현** (`stock_track_record.py`에 추가)

```python
def mine_picks(code, snapshots_dir="web/briefings"):
    """snapshots_dir/*/*/analysis_snapshot.json을 스캔해 ticker==code인 픽을 날짜 오름차순으로 반환."""
    out = []
    pattern = os.path.join(snapshots_dir, "*", "*", "analysis_snapshot.json")
    for f in glob.glob(pattern):
        parts = f.replace("\\", "/").split("/")
        date, btype = parts[-3], parts[-2]
        try:
            data = json.load(open(f, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for p in (data.get("stock_picks") or []):
            if str(p.get("ticker")) == str(code):
                out.append({
                    "date": date,
                    "btype": btype,
                    "name": p.get("name"),
                    "signal": p.get("signal"),
                    "scenario_tag": p.get("scenario_tag"),
                    "entry": p.get("entry"),
                    "target": p.get("target"),
                    "stop": p.get("stop"),
                })
    out.sort(key=lambda x: x["date"])
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/stock_track_record.py scripts/test_stock_track_record.py
git commit -m "feat(종목): 브리핑 스냅샷에서 종목 픽 채굴 mine_picks"
```

---

## Task 3: 픽 채점 (score_pick)

**Files:**
- Modify: `scripts/stock_track_record.py`
- Test: `scripts/test_stock_track_record.py`

채점 규칙(설계 확정): 평가 구간 = 픽 다음 거래일부터 픽 후 15거래일. 일봉 종가 순회, 손절가 이하 먼저 닿으면 `stop`, 손절 전 목표가 이상 닿으면 `hit`(도달일수 기록), 둘 다 미터치면 `running`. 표시 수치 = 진입가 대비 구간 내 최대 종가 수익률 + 현재가 수익률.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from stock_track_record import score_pick


def _pick(entry, target, stop, date="2026-06-15"):
    return {"date": date, "entry": entry, "target": target, "stop": stop}


def test_score_hit_when_close_reaches_target():
    # 진입 322,500 / 목표 360,000 / 손절 305,000
    closes = [
        ("20260615", 322500.0), ("20260616", 337000.0), ("20260617", 350000.0),
        ("20260618", 362500.0),  # 목표 도달
        ("20260619", 354000.0),
    ]
    r = score_pick(_pick("322,500원", "360,000원", "305,000원"), closes)
    assert r["result"] == "hit"
    assert r["days_to_target"] == 3        # 6/16,6/17,6/18 → 3거래일째
    assert round(r["max_ret_pct"], 1) == round((362500 - 322500) / 322500 * 100, 1)


def test_score_stop_when_close_breaks_stop_first():
    closes = [
        ("20260615", 322500.0), ("20260616", 300000.0),  # 손절(305,000) 이하 먼저
        ("20260617", 365000.0),
    ]
    r = score_pick(_pick("322,500원", "360,000원", "305,000원"), closes)
    assert r["result"] == "stop"


def test_score_running_when_neither_hit():
    closes = [
        ("20260615", 322500.0), ("20260616", 330000.0), ("20260617", 340000.0),
    ]
    r = score_pick(_pick("322,500원", "360,000원", "305,000원"), closes)
    assert r["result"] == "running"
    # 현재가 수익률 = 마지막 종가 기준
    assert round(r["cur_ret_pct"], 1) == round((340000 - 322500) / 322500 * 100, 1)


def test_score_horizon_caps_window():
    # 픽 후 16거래일째에 목표 도달 → 15거래일 구간 밖이라 running
    closes = [("20260615", 322500.0)] + [
        (f"202607{str(i).zfill(2)}", 330000.0) for i in range(1, 16)
    ] + [("20260720", 365000.0)]
    r = score_pick(_pick("322,500원", "360,000원", "305,000원"), closes, horizon_bd=15)
    assert r["result"] == "running"
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q -k score`
Expected: FAIL — `ImportError: cannot import name 'score_pick'`

- [ ] **Step 3: 최소 구현**

```python
def score_pick(pick, dated_closes, horizon_bd=15):
    """dated_closes: [(YYYYMMDD, close)] 오름차순. 픽 날짜 이후 구간을 채점."""
    entry = parse_price(pick.get("entry"))
    target = parse_price(pick.get("target"))
    stop = parse_price(pick.get("stop"))
    pick_date = pick["date"].replace("-", "")  # 'YYYY-MM-DD' → 'YYYYMMDD'

    after = [(d, c) for (d, c) in dated_closes if d > pick_date]
    after.sort(key=lambda x: x[0])
    window = after[:horizon_bd]

    result = "running"
    days_to_target = None
    for i, (d, c) in enumerate(window):
        if stop is not None and c <= stop:
            result = "stop"
            days_to_target = i + 1
            break
        if target is not None and c >= target:
            result = "hit"
            days_to_target = i + 1
            break

    win_closes = [c for (_, c) in window]
    max_close = max(win_closes) if win_closes else (entry or 0)
    last_close = dated_closes[-1][1] if dated_closes else (entry or 0)
    max_ret_pct = ((max_close - entry) / entry * 100) if entry else 0.0
    cur_ret_pct = ((last_close - entry) / entry * 100) if entry else 0.0

    return {
        "result": result,
        "days_to_target": days_to_target,
        "max_ret_pct": max_ret_pct,
        "cur_ret_pct": cur_ret_pct,
    }
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/stock_track_record.py scripts/test_stock_track_record.py
git commit -m "feat(종목): 픽 실측 채점 score_pick (목표도달/손절/진행중)"
```

---

## Task 4: 트랙레코드 조립 (build_track_record)

**Files:**
- Modify: `scripts/stock_track_record.py`
- Test: `scripts/test_stock_track_record.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from stock_track_record import build_track_record


def test_build_track_record_summary(tmp_path):
    _write_snapshot(tmp_path, "2026-06-15", "kospi", [
        {"ticker": "005930", "name": "삼성전자", "entry": "322,500원", "target": "360,000원", "stop": "305,000원"},
    ])
    _write_snapshot(tmp_path, "2026-06-25", "kospi", [
        {"ticker": "005930", "name": "삼성전자", "entry": "340,000원", "target": "360,000원", "stop": "328,000원"},
    ])
    closes = [("20260615", 322500.0), ("20260618", 362500.0), ("20260626", 339500.0)]
    tr = build_track_record("005930", lambda code: closes,
                            snapshots_dir=str(tmp_path / "web" / "briefings"))
    assert tr["count"] == 2
    assert tr["hit"] == 1          # 6/15 픽 목표 도달
    assert tr["running"] == 1      # 6/25 픽 진행 중
    assert tr["stop"] == 0
    assert tr["picks"][0]["result"] == "hit"


def test_build_track_record_none_when_no_picks(tmp_path):
    (tmp_path / "web" / "briefings").mkdir(parents=True, exist_ok=True)
    assert build_track_record("005930", lambda code: [],
                              snapshots_dir=str(tmp_path / "web" / "briefings")) is None
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q -k build_track_record`
Expected: FAIL — `ImportError: cannot import name 'build_track_record'`

- [ ] **Step 3: 최소 구현**

```python
def build_track_record(code, fetch_closes, snapshots_dir="web/briefings"):
    """픽 채굴 + 채점 조립. 픽 없으면 None.
    fetch_closes: callable(code) -> [(YYYYMMDD, close)] (의존성 주입)."""
    picks = mine_picks(code, snapshots_dir=snapshots_dir)
    if not picks:
        return None
    closes = fetch_closes(code) or []
    scored = []
    hit = stop = running = 0
    for p in picks:
        s = score_pick(p, closes)
        if s["result"] == "hit":
            hit += 1
        elif s["result"] == "stop":
            stop += 1
        else:
            running += 1
        scored.append({**p, **s})
    return {"count": len(picks), "hit": hit, "stop": stop, "running": running, "picks": scored}
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/stock_track_record.py scripts/test_stock_track_record.py
git commit -m "feat(종목): 트랙레코드 조립 build_track_record"
```

---

## Task 5: 브리핑 적중률 집계 (briefing_accuracy)

**Files:**
- Modify: `scripts/stock_track_record.py`
- Test: `scripts/test_stock_track_record.py`

`data/briefings.json` 구조(확인됨): `{"briefings": [{"type": "us"|"kospi"|..., "is_correct": true/false/null, ...}]}`. 코스피 = type이 'us'가 아닌 것, 미국 = type=='us'. `is_correct`가 null인 항목은 미채점이라 제외.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from stock_track_record import briefing_accuracy


def test_briefing_accuracy_groups_kospi_and_us():
    briefings = [
        {"type": "kospi", "is_correct": True},
        {"type": "kospi", "is_correct": False},
        {"type": "kospi-close", "is_correct": True},
        {"type": "us", "is_correct": True},
        {"type": "us", "is_correct": True},
        {"type": "us", "is_correct": None},   # 미채점 → 제외
    ]
    acc = briefing_accuracy(briefings)
    assert acc["kospi_n"] == 3
    assert acc["kospi_pct"] == 67          # 2/3 → 67
    assert acc["us_n"] == 2
    assert acc["us_pct"] == 100


def test_briefing_accuracy_empty():
    acc = briefing_accuracy([])
    assert acc["kospi_n"] == 0 and acc["kospi_pct"] is None
    assert acc["us_n"] == 0 and acc["us_pct"] is None
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q -k accuracy`
Expected: FAIL — `ImportError: cannot import name 'briefing_accuracy'`

- [ ] **Step 3: 최소 구현**

```python
def briefing_accuracy(briefings):
    """briefings.json의 briefings 리스트에서 코스피·미국 방향 적중률 집계.
    is_correct가 None인 항목(미채점)은 제외."""
    def _agg(items):
        scored = [b for b in items if b.get("is_correct") is not None]
        n = len(scored)
        if n == 0:
            return (None, 0)
        correct = sum(1 for b in scored if b.get("is_correct"))
        return (round(correct / n * 100), n)

    us = [b for b in briefings if b.get("type") == "us"]
    kospi = [b for b in briefings if b.get("type") != "us"]
    kp, kn = _agg(kospi)
    up, un = _agg(us)
    return {"kospi_pct": kp, "kospi_n": kn, "us_pct": up, "us_n": un}
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q`
Expected: PASS (14 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/stock_track_record.py scripts/test_stock_track_record.py
git commit -m "feat(종목): 브리핑 적중률 집계 briefing_accuracy"
```

---

## Task 6: generate_html 배선 — ctx 주입

**Files:**
- Modify: `scripts/generate_html.py` (`build_stock_page`, ~950)

- [ ] **Step 1: 네이버 날짜+종가 fetch 헬퍼 추가**

`generate_html.py`의 기존 이중 import 블록(`try: from scripts.validate_analysis ... except ImportError: from validate_analysis ...`, ~26–30행)에 같은 패턴으로 추가:

```python
try:
    from scripts.validate_analysis import _fetch_kospi_realdata
    import scripts.toss_client as tc
    from scripts.stock_track_record import build_track_record, briefing_accuracy
except ImportError:
    from validate_analysis import _fetch_kospi_realdata
    import toss_client as tc
    from stock_track_record import build_track_record, briefing_accuracy
```

(기존 두 줄은 그대로 두고 `stock_track_record` 줄만 각 분기에 추가.)

`build_stock_page` 함수 위에 fetch 헬퍼 추가:

```python
def _fetch_dated_closes(code):
    """네이버 일봉에서 (YYYYMMDD, close) 리스트(오름차순)를 반환. 실패 시 빈 리스트."""
    import urllib.request
    from datetime import datetime, timedelta
    end = datetime.now().strftime("%Y%m%d") + "0000"
    start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d") + "0000"
    url = (f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
           f"?startDateTime={start}&endDateTime={end}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        rows = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return [(r["localDate"], float(r["closePrice"])) for r in rows
                if r.get("localDate") and r.get("closePrice")]
    except Exception:
        return []
```

- [ ] **Step 2: ctx에 track_record·accuracy 주입**

`build_stock_page`의 `ctx = { ... }` 딕셔너리에 두 키 추가 (기존 `"foreign_spark": ...` 줄 다음):

```python
        "track_record": build_track_record(stock["code"], _fetch_dated_closes),
        "accuracy": briefing_accuracy(
            load_json(DATA_DIR / "briefings.json").get("briefings", [])
        ),
```

- [ ] **Step 3: 배선 동작 확인 (수동 스모크)**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -c "
from scripts.generate_html import _fetch_dated_closes, build_track_record, briefing_accuracy, load_json, DATA_DIR
tr = build_track_record('005930', _fetch_dated_closes)
print('삼성 픽수:', tr['count'], '도달:', tr['hit'], '진행:', tr['running'], '손절:', tr['stop'])
acc = briefing_accuracy(load_json(DATA_DIR / 'briefings.json').get('briefings', []))
print('적중률 코스피:', acc['kospi_pct'], '미국:', acc['us_pct'])
"`
Expected: `삼성 픽수: 3 도달: 2 진행: 1 손절: 0` (현재 데이터 기준, 픽 도달 수는 시세에 따라 달라질 수 있음) + 적중률 숫자 출력. 에러 없이 완료.

- [ ] **Step 4: 커밋**

```bash
git add scripts/generate_html.py
git commit -m "feat(종목): build_stock_page에 트랙레코드·적중률 ctx 주입"
```

---

## Task 7: detail.html 템플릿 — A·B 섹션 + CSS

**Files:**
- Modify: `scripts/templates/stocks/detail.html`
- Modify: `web/assets/stocks.css`

프로토(`web/stocks/005930-proto/index.html`)의 트랙레코드·적중률 마크업과 스타일을 템플릿/CSS로 이관한다. Jinja2 조건으로 데이터 없으면 섹션 생략.

- [ ] **Step 1: stocks.css에 A·B 섹션 스타일 추가**

`web/assets/stocks.css` 끝에 추가(프로토 인라인 `.np`·`.tr-*`·`.acc-*` 규칙 이관):

```css
/* 종목 상세 — 트랙레코드(A) / 적중률(B) */
.np{background:var(--canvas);border:1px solid var(--hair);border-radius:12px;overflow:hidden;margin-bottom:14px;box-shadow:var(--s1);}
.np__h{display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-bottom:1px solid var(--hair);}
.np__t{display:flex;align-items:center;gap:7px;font-size:14px;font-weight:700;color:var(--ink);}
.np__t svg{width:17px;height:17px;color:var(--primary);}
.np__s{font-size:11px;color:var(--muted);}
.tr-sum{display:flex;gap:18px;align-items:baseline;padding:12px 16px;background:var(--soft);border-bottom:1px solid var(--hair);font-size:13px;color:var(--muted);}
.tr-sum b{color:var(--ink);}
.tr-row{padding:11px 16px;border-bottom:1px solid var(--hair);}
.tr-row:last-child{border-bottom:none;}
.tr-top{display:flex;align-items:center;gap:8px;margin-bottom:5px;}
.tr-date{font-size:11px;font-weight:700;background:#E8F0FE;color:#1A4FA0;padding:2px 7px;border-radius:5px;white-space:nowrap;}
.tr-sig{font-size:12px;color:var(--muted);}
.tr-badge{margin-left:auto;font-size:11px;font-weight:700;padding:2px 8px;border-radius:5px;white-space:nowrap;}
.tr-badge.hit{background:#E3F5EA;color:#1A7F4B;}
.tr-badge.run{background:#FBF0DA;color:#B07400;}
.tr-badge.miss{background:#FBE3E3;color:#B33A3A;}
.tr-line{display:flex;align-items:baseline;gap:6px;font-size:12px;color:var(--muted);}
.tr-line b{color:var(--ink);}
.tr-ret{margin-left:auto;font-weight:700;}
.acc-grid{display:flex;gap:10px;padding:14px 16px 12px;}
.acc-cell{flex:1;background:var(--soft);border-radius:8px;padding:10px 12px;}
.acc-cell .l{font-size:12px;color:var(--muted);margin-bottom:3px;}
.acc-cell .v{font-size:22px;font-weight:800;color:var(--ink);}
.acc-cta{display:block;margin:0 16px 16px;text-align:center;font-size:13px;font-weight:700;color:var(--primary);text-decoration:none;padding:10px;background:#F0F7FF;border-radius:8px;}
```

- [ ] **Step 2: detail.html에 트랙레코드(A) 섹션 추가**

`detail.html`에서 헤더 카드(`hero2`) 닫힌 직후에 삽입. 값 포맷은 `"{:,.0f}".format(parse_price(...))`이 아니라 픽 원본 문자열(`entry`/`target`)을 그대로 노출(이미 "340,000원" 포맷). 수익률은 ctx의 채점값 사용.

```html
{% if track_record %}
<div class="np">
  <div class="np__h"><span class="np__t"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></svg>더블샷 AI 픽 트랙레코드</span><span class="np__s">종가 기준 실측</span></div>
  <div class="tr-sum"><span>{{ stock.name }}을(를) <b>{{ track_record.count }}번</b> 픽</span><span style="color:#1A7F4B">목표 도달 <b>{{ track_record.hit }}</b></span>{% if track_record.running %}<span style="color:#B07400">진행 중 <b>{{ track_record.running }}</b></span>{% endif %}{% if track_record.stop %}<span style="color:#B33A3A">손절 <b>{{ track_record.stop }}</b></span>{% endif %}</div>
  {% for p in track_record.picks %}
  <div class="tr-row">
    <div class="tr-top"><span class="tr-date">{{ p.date[5:]|replace('-','/') }} {{ p.btype }}</span><span class="tr-sig">{{ p.signal }}{% if p.scenario_tag %} · {{ p.scenario_tag }}{% endif %}</span>
      {% if p.result == 'hit' %}<span class="tr-badge hit">목표 도달</span>{% elif p.result == 'stop' %}<span class="tr-badge miss">손절</span>{% else %}<span class="tr-badge run">진행 중</span>{% endif %}</div>
    <div class="tr-line"><span>진입 <b>{{ p.entry }}</b></span>→<span>목표 <b>{{ p.target }}</b></span>
      {% if p.result == 'hit' %}<span class="tr-ret" style="color:var(--up)">최대 {{ '%+.1f'|format(p.max_ret_pct) }}%</span>
      {% elif p.result == 'stop' %}<span class="tr-ret" style="color:var(--dn)">손절 {{ '%+.1f'|format(p.cur_ret_pct) }}%</span>
      {% else %}<span class="tr-ret" style="color:{{ 'var(--up)' if p.cur_ret_pct >= 0 else 'var(--dn)' }}">현재 {{ '%+.1f'|format(p.cur_ret_pct) }}%</span>{% endif %}</div>
  </div>
  {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 3: detail.html 사이드바에 적중률(B) 섹션 추가**

`detail.html`의 우측 사이드바(`다른 섹터` 패널 다음, 사이드바 `<div>` 닫기 직전)에 삽입:

```html
{% if accuracy and (accuracy.kospi_pct is not none or accuracy.us_pct is not none) %}
<div class="np">
  <div class="np__h"><span class="np__t"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/></svg>더블샷 브리핑 적중률</span></div>
  <div class="acc-grid">
    {% if accuracy.kospi_pct is not none %}<div class="acc-cell"><div class="l">코스피 방향</div><div class="v">{{ accuracy.kospi_pct }}%</div></div>{% endif %}
    {% if accuracy.us_pct is not none %}<div class="acc-cell"><div class="l">미국 방향</div><div class="v">{{ accuracy.us_pct }}%</div></div>{% endif %}
  </div>
  <a class="acc-cta" href="https://doubleshot.space/briefings">매일 아침·저녁 AI 브리핑 받아보기 →</a>
</div>
{% endif %}
```

- [ ] **Step 4: 커밋**

```bash
git add scripts/templates/stocks/detail.html web/assets/stocks.css
git commit -m "feat(종목): 상세 템플릿에 트랙레코드·적중률 섹션 추가"
```

---

## Task 8: 통합 검증 — 삼성전자 재생성 + 프리뷰

**Files:** (검증만)

- [ ] **Step 1: 전체 모듈 테스트**

Run: `python3 -m pytest scripts/test_stock_track_record.py -q`
Expected: PASS (14 passed)

- [ ] **Step 2: 삼성전자 페이지 재생성**

Run: `cd "/Users/luke/Service App/double-shot" && python3 scripts/generate_html.py --stocks --only 005930` 
(만약 `--only` 플래그가 없으면 `--stocks`로 전체 생성. `build_all_stocks` 시그니처를 먼저 확인하고, 단일 종목 생성 경로가 없으면 `python3 -c "from scripts.generate_html import build_stock_page, ...; build_stock_page(...)"`로 005930만 생성.)
Expected: `web/stocks/005930/index.html` 갱신, 에러 없음.

- [ ] **Step 3: 생성물에 섹션 존재 확인**

Run: `grep -c "더블샷 AI 픽 트랙레코드\|더블샷 브리핑 적중률" web/stocks/005930/index.html`
Expected: `2` (두 섹션 모두 렌더)

- [ ] **Step 4: 픽 0 종목 게이팅 확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -c "
from scripts.stock_track_record import build_track_record
from scripts.generate_html import _fetch_dated_closes
print('두산에너빌리티 트랙레코드:', build_track_record('034020', _fetch_dated_closes))
"`
Expected: `None` (픽 0 → 섹션 자동 숨김). 단 034020가 픽 0인지 Task 사전 확인 — 픽 있는 종목이면 다른 픽 0 종목 코드로 교체.

- [ ] **Step 5: 프리뷰로 시각 확인**

`web/`를 정적 서버로 띄워(`preview_start`) `/stocks/005930/`를 열고, 트랙레코드(요약 + 픽별 행 + 결과 배지)와 사이드바 적중률이 프로토와 동일하게 렌더되는지 `preview_screenshot`으로 확인. 콘솔 에러 없는지 `preview_console_logs`.

- [ ] **Step 6: 커밋** (생성물)

```bash
git add web/stocks/005930/index.html
git commit -m "feat(종목): 삼성전자 트랙레코드·적중률 섹션 반영(재생성)"
```

---

## Self-Review 결과

- **스펙 커버리지:** A 트랙레코드(채굴 T2·채점 T3·조립 T4·렌더 T7), B 적중률(집계 T5·렌더 T7), 채점 규칙(15거래일·종가·도달/손절/진행 — T3), 데이터 게이팅(픽 0 → None → 섹션 숨김 T4·T7·T8), 틀린 픽 노출(stop 배지 T7) 모두 태스크 존재. 시그널 C·실측 재설계·네이버 재소싱·칩보드 청소는 명시적 범위 밖(후속 계획).
- **Placeholder:** 없음. 모든 코드 스텝에 실제 코드. (단 T8 Step 2의 `--only` 플래그·T8 Step 4의 픽 0 종목코드는 실행 시 확인 지시 포함 — 구현자가 실제 시그니처/데이터로 보정.)
- **타입 일관성:** `mine_picks`→dict(date,btype,name,signal,scenario_tag,entry,target,stop) → `score_pick`이 entry/target/stop/date 사용 → `build_track_record`가 병합(`{**p, **s}`)해 result·max_ret_pct·cur_ret_pct·days_to_target 추가 → 템플릿이 동일 키 참조. `briefing_accuracy`→kospi_pct/kospi_n/us_pct/us_n → 템플릿 동일 참조. 일치.
- **검증 가능성:** 채점은 합성 종가로 결정적 단위 테스트(T3). 통합은 실데이터 스모크(T6·T8).
