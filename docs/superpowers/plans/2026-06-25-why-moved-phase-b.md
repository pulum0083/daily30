# 왜 움직였나 — Phase B: 뉴스 핀 레이어 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 주도주/상세 곡선 위에 "왜 움직였나" 뉴스 핀을 얹는다 — RSS 실기사 + Gemini 선별 + 방향게이트로 `movers-why-{date}.json`을 만들고, 프론트가 곡선 위에 핀+번호 타임라인을 그린다.

**Architecture:** 신규 엔진 `scripts/fetch_movers_why.py`가 ① 네이버 실시간으로 41종목 장중 등락·거래량을 받아 주요 무버 최대 10종목을 추리고, ② 종목별 Google News RSS(오늘 기사) → Gemini 선별·요약·감성 → 방향게이트(`why`/`related`/`none`)로 events를 만들어 `web/data/movers-why-{date}.json`(+`movers-why-live.json`)에 저장한다. 프론트(홈 `index.html`·상세 `stocks.js`)가 이 JSON을 읽어 기존 곡선 위에 핀을 찍는다. 브리핑 파이프라인은 0줄 수정.

**Tech Stack:** Python(stdlib urllib/xml + google-genai), 네이버 polling.finance + Google News RSS, Vanilla JS(SVG), GitHub Actions schedule, pytest.

**전제:** Phase A 완료 — `api/intraday?code=` 실측 1분봉, 홈 `#why-moved`/`#wm-svg` 곡선, 상세 `#intra-card`/`#intra-svg` 곡선이 이미 동작한다. 이 위에 핀만 얹는다.

**정합성 규칙(운영규칙 0번):** 핀은 RSS 실기사·실제 출처 링크만. 날짜·헤드라인 생성 금지(RSS가 보장). 방향게이트가 LLM 인과 주장을 코드로 강등. 데이터 없으면 핀 숨김.

**재사용 (수정 금지, import만):** `scripts/fetch_news_live.py`의 `_fetch_rss`, `_GN_KR`, `_clean_title`, `_parse_rss_datetime`, `get_gemini_api_key`, `_UP_WORDS`, `_DOWN_WORDS`.

---

## File Structure

| 파일 | 책임 | 작업 |
| --- | --- | --- |
| `scripts/fetch_movers_why.py` | 무버 선별 + 뉴스·게이트 + JSON 산출 엔진 | Create |
| `scripts/test_movers_why.py` | 순수함수 단위 테스트(네트워크 없음) | Create |
| `web/data/movers-why-{date}.json`, `movers-why-live.json` | 종목별 events 산출물 | 엔진이 생성 |
| `web/stocks/index.html` | 홈 주도주 곡선에 핀+타임라인 | Modify |
| `web/assets/stocks.js` | 상세 곡선에 핀+타임라인 | Modify |
| `scripts/templates/stocks/detail.html` | 상세 타임라인 컨테이너 | Modify |
| `.github/workflows/kospi-news-live.yml` | 30분 cadence 스케줄에 엔진 추가 | Modify |

---

## Task 1: 엔진 — 무버 선별 순수함수 (TDD)

**Files:**
- Create: `scripts/fetch_movers_why.py`
- Create: `scripts/test_movers_why.py`

- [ ] **Step 1: 실패 테스트 작성** — `scripts/test_movers_why.py`

```python
# 왜움직였나 엔진 순수함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
import fetch_movers_why as m


def test_select_movers_threshold_and_dedup():
    rows = [
        {"code": "A", "name": "에이", "change_pct": 5.0, "surge": 1.1},   # |change|>=2 → 포함
        {"code": "B", "name": "비",  "change_pct": -3.0, "surge": 1.0},   # 하락 포함
        {"code": "C", "name": "씨",  "change_pct": 0.5, "surge": 2.0},    # surge>=1.5 → 포함
        {"code": "D", "name": "디",  "change_pct": 0.3, "surge": 1.1},    # 미달 → 제외
    ]
    out = m.select_movers(rows, max_n=10)
    codes = [r["code"] for r in out]
    assert "D" not in codes
    assert set(codes) == {"A", "B", "C"}


def test_select_movers_caps_at_max_n():
    rows = [{"code": str(i), "name": str(i), "change_pct": 9.0 - i*0.1, "surge": 1.0}
            for i in range(20)]
    out = m.select_movers(rows, max_n=10)
    assert len(out) == 10
    # 절대 등락 큰 순으로 잘렸는지 (가장 큰 change부터)
    assert out[0]["code"] == "0"
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_movers_why.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_movers_why'` 또는 `AttributeError: select_movers`.

- [ ] **Step 3: 엔진 파일 생성 + select_movers 구현** — `scripts/fetch_movers_why.py`

```python
# "왜 움직였나" 엔진 — 무버 선별 + RSS·Gemini·방향게이트 → movers-why-{date}.json
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).parent.parent
WEB_DATA = REPO_ROOT / "web" / "data"
CONFIG_DIR = REPO_ROOT / "scripts" / "config"
SNAPSHOT_PATH = WEB_DATA / "stocks-snapshot.json"

MAX_MOVERS = 10
CHANGE_THRESHOLD = 2.0   # |등락률| %
SURGE_THRESHOLD = 1.5    # 거래량 / vol_avg20

# fetch_news_live 재사용 (수정 금지)
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def select_movers(rows: list[dict], max_n: int = MAX_MOVERS) -> list[dict]:
    """등락·거래량 무버 선별. |change|>=2 또는 surge>=1.5 충족분만, 절대등락 큰 순 max_n개."""
    cand = [r for r in rows
            if abs(r.get("change_pct") or 0) >= CHANGE_THRESHOLD
            or (r.get("surge") or 0) >= SURGE_THRESHOLD]
    cand.sort(key=lambda r: abs(r.get("change_pct") or 0), reverse=True)
    return cand[:max_n]
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_movers_why.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_movers_why.py scripts/test_movers_why.py
git commit -m "feat(왜움직였나): 무버 선별 순수함수 + 엔진 스켈레톤"
```

---

## Task 2: 엔진 — 네이버 실시간 파싱 + 무버 수집

**Files:**
- Modify: `scripts/fetch_movers_why.py`
- Modify: `scripts/test_movers_why.py`

- [ ] **Step 1: 파싱 실패 테스트 추가** — `scripts/test_movers_why.py`에 추가

```python
def test_parse_naver_realtime():
    data = {"datas": [{
        "itemCode": "005930", "stockName": "삼성전자",
        "closePrice": "358,500", "fluctuationsRatio": "5.29",
        "accumulatedTradingVolume": "12,345,678",
    }]}
    r = m.parse_naver_realtime(data, vol_avg20=6000000)
    assert r["code"] == "005930"
    assert r["name"] == "삼성전자"
    assert r["change_pct"] == 5.29
    assert r["volume"] == 12345678
    assert round(r["surge"], 2) == 2.06   # 12345678 / 6000000


def test_parse_naver_realtime_missing():
    assert m.parse_naver_realtime({"datas": []}, vol_avg20=1) is None
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_movers_why.py::test_parse_naver_realtime -v`
Expected: FAIL — `AttributeError: parse_naver_realtime`.

- [ ] **Step 3: 파싱 + 수집 구현** — `fetch_movers_why.py`에 추가

```python
_HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}


def _num(s) -> float:
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def parse_naver_realtime(data: dict, vol_avg20: float) -> dict | None:
    """네이버 polling 응답 → {code,name,change_pct,volume,surge}. 데이터 없으면 None."""
    datas = data.get("datas") or []
    if not datas:
        return None
    d = datas[0]
    vol = _num(d.get("accumulatedTradingVolume"))
    return {
        "code": d.get("itemCode", ""),
        "name": d.get("stockName", ""),
        "change_pct": _num(d.get("fluctuationsRatio")),
        "volume": vol,
        "surge": (vol / vol_avg20) if vol_avg20 else 0.0,
    }


def _load_universe() -> list[dict]:
    """stocks.json(41종목)에서 code·name 유니버스를 읽는다."""
    return json.loads((CONFIG_DIR / "stocks.json").read_text(encoding="utf-8"))


def _load_vol_avg20() -> dict:
    """스냅샷에서 종목별 vol_avg20을 읽는다(급증배수 계산용). 없으면 빈 dict."""
    if not SNAPSHOT_PATH.exists():
        return {}
    snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return {c: (v.get("vol_avg20") or 0) for c, v in (snap.get("stocks") or {}).items()}


def fetch_mover_rows() -> list[dict]:
    """유니버스 41종목의 네이버 실시간을 받아 무버 행 리스트를 만든다(네트워크)."""
    avg = _load_vol_avg20()
    rows = []
    for s in _load_universe():
        code = s["code"]
        url = f"https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
        try:
            req = urllib.request.Request(url, headers=_HDR)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            row = parse_naver_realtime(data, avg.get(code, 0))
            if row:
                rows.append(row)
        except Exception as e:
            print(f"[movers_why] {code} 실시간 실패: {e}")
    return rows
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_movers_why.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_movers_why.py scripts/test_movers_why.py
git commit -m "feat(왜움직였나): 네이버 실시간 파싱 + 무버 수집"
```

---

## Task 3: 엔진 — 방향 게이트 (TDD)

**Files:**
- Modify: `scripts/fetch_movers_why.py`
- Modify: `scripts/test_movers_why.py`

- [ ] **Step 1: 게이트 실패 테스트 추가** — `scripts/test_movers_why.py`에 추가

```python
def test_classify_tier():
    # 기사 0건 → none
    assert m.classify_tier(None, 5.0) == "none"
    # 긍정 헤드라인 + 상승 → why
    assert m.classify_tier({"sentiment": "pos", "headline": "엔비디아 공급 확대"}, 5.0) == "why"
    # 부정 헤드라인 + 하락 → why
    assert m.classify_tier({"sentiment": "neg", "headline": "실적 쇼크 급락"}, -4.0) == "why"
    # 긍정인데 하락 → 불일치 → related 강등
    assert m.classify_tier({"sentiment": "pos", "headline": "수주 호재"}, -4.0) == "related"
    # 헤드라인에 상승어 있는데 주가 하락 → related (코드 게이트)
    assert m.classify_tier({"sentiment": "neu", "headline": "급등 기대감"}, -4.0) == "related"
    # 중립·소폭 → related
    assert m.classify_tier({"sentiment": "neu", "headline": "거래량 증가"}, 0.5) == "related"
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_movers_why.py::test_classify_tier -v`
Expected: FAIL — `AttributeError: classify_tier`.

- [ ] **Step 3: 게이트 구현** — `fetch_movers_why.py`에 추가 (fetch_news_live 정규식 재사용)

```python
from fetch_news_live import _UP_WORDS, _DOWN_WORDS  # noqa: E402


def classify_tier(event: dict | None, change_pct: float) -> str:
    """방향 일치 게이트. event 없으면 none, 감성·헤드라인↔등락 일치면 why, 불일치면 related."""
    if not event:
        return "none"
    head = event.get("headline", "") or ""
    sent = event.get("sentiment", "neu")
    up = change_pct >= CHANGE_THRESHOLD
    down = change_pct <= -CHANGE_THRESHOLD
    # 코드 게이트: 헤드라인 방향어가 주가와 반대면 인과 단정 금지 → related
    if down and _UP_WORDS.search(head):
        return "related"
    if up and _DOWN_WORDS.search(head):
        return "related"
    # 감성↔방향 일치
    if (sent == "pos" and up) or (sent == "neg" and down):
        return "why"
    return "related"
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_movers_why.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_movers_why.py scripts/test_movers_why.py
git commit -m "feat(왜움직였나): 방향 일치 게이트(why/related/none)"
```

---

## Task 4: 엔진 — RSS + Gemini 선별·요약·감성 (종목별)

**Files:**
- Modify: `scripts/fetch_movers_why.py`

- [ ] **Step 1: 종목별 뉴스 1건 추출 함수 구현** — `fetch_movers_why.py`에 추가

`fetch_news_live`의 RSS·Gemini 키 헬퍼를 재사용한다. 종목명으로 RSS를 받아 오늘 기사 중 1건을 Gemini가 골라 요약·감성 분류. URL은 RSS item의 link에서 가져온다(생성 금지).

```python
import re  # noqa: E402
import urllib.parse  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402
from fetch_news_live import _GN_KR, _clean_title, _parse_rss_datetime, get_gemini_api_key  # noqa: E402

_SENT_PROMPT = """종목 "{name}"의 오늘 기사 목록입니다. 주가에 가장 영향이 큰 기사 1건을 골라,
요약 1문장과 감성을 분류하세요. 사실만, 추측·생성 금지.

[기사 목록]
{lst}

[출력 — JSON만, 마크다운 없이]
{{"idx": 0, "summary": "한 문장 요약", "sentiment": "pos|neg|neu"}}
"""


def _fetch_stock_articles(name: str, today: str, max_items: int = 8) -> list[dict]:
    """종목명 Google News RSS에서 오늘 기사 + link(url)까지 수집한다."""
    url = _GN_KR + urllib.parse.quote(f"{name} 주가")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print(f"[movers_why] {name} RSS 실패: {e}")
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        pub_date, pub_time = _parse_rss_datetime(item.findtext("pubDate") or "")
        if not title or pub_date != today:
            continue
        src_el = item.find("source")
        out.append({
            "headline": _clean_title(title),
            "time": pub_time or "09:00",
            "url": (item.findtext("link") or "").strip(),
            "source": (src_el.text or "").strip() if src_el is not None else "",
        })
        if len(out) >= max_items:
            break
    return out


def pick_event(name: str, today: str) -> dict | None:
    """종목 기사 중 Gemini가 1건 선별·요약·감성. 기사 0건이면 None."""
    articles = _fetch_stock_articles(name, today)
    if not articles:
        return None
    from google import genai
    from google.genai import types
    lst = "\n".join(f'{i}. "{a["headline"]}" ({a["source"]})' for i, a in enumerate(articles))
    prompt = _SENT_PROMPT.format(name=name, lst=lst)
    try:
        client = genai.Client(api_key=get_gemini_api_key())
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=200),
        )
        raw = (resp.text or "").strip()
        mt = re.search(r"\{[\s\S]*\}", raw)
        parsed = json.loads(mt.group(0)) if mt else {}
    except Exception as e:
        print(f"[movers_why] {name} Gemini 실패: {e}")
        return None
    idx = parsed.get("idx")
    if not isinstance(idx, int) or not (0 <= idx < len(articles)):
        return None
    a = articles[idx]
    sent = parsed.get("sentiment", "neu")
    if sent not in ("pos", "neg", "neu"):
        sent = "neu"
    return {
        "time": a["time"], "headline": a["headline"], "url": a["url"],
        "source": a["source"], "summary": (parsed.get("summary") or "").strip(),
        "sentiment": sent,
    }
```

- [ ] **Step 2: import 무결성 확인 (네트워크 없이 모듈 로드)**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import fetch_movers_why as m; print('ok', bool(m.pick_event), bool(m._fetch_stock_articles))"`
Expected: `ok True True` (모듈이 깨짐 없이 import — 기존 테스트도 그대로 통과해야 함).
Run: `python3 -m pytest scripts/test_movers_why.py -v` → 5 passed 유지.

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_movers_why.py
git commit -m "feat(왜움직였나): 종목별 RSS 수집 + Gemini 선별·요약·감성"
```

---

## Task 5: 엔진 — main 오케스트레이션 + 산출물 JSON

**Files:**
- Modify: `scripts/fetch_movers_why.py`

- [ ] **Step 1: why 한 줄 생성 + main 구현** — `fetch_movers_why.py`에 추가

`why` 한 줄은 요약을 부드러운 연결어로 감싼다(새 사실 생성 금지). tier가 `related`면 인과 단정 표현을 피한다.

```python
def _why_line(event: dict, tier: str) -> str:
    summ = event.get("summary") or event.get("headline")
    if tier == "why":
        return summ
    return f"{summ} (개별 인과 단정 안 함)"


def build_payload(today: str) -> dict:
    """무버 선별 → 종목별 뉴스·게이트 → 산출물 dict."""
    movers = select_movers(fetch_mover_rows())
    stocks = []
    for r in movers:
        event = pick_event(r["name"], today)
        tier = classify_tier(event, r["change_pct"])
        events = []
        if event and tier != "none":
            events = [{
                "time": event["time"], "headline": event["headline"],
                "url": event["url"], "source": event["source"],
                "why": _why_line(event, tier), "tier": tier,
                "sentiment": event["sentiment"],
            }]
        stocks.append({
            "code": r["code"], "name": r["name"],
            "changePct": round(r["change_pct"], 2),
            "surge": round(r.get("surge") or 0, 2),
            "events": events,
        })
    return {"generated_at": datetime.now(KST).isoformat(), "date": today, "stocks": stocks}


def main():
    today = datetime.now(KST).strftime("%Y-%m-%d")
    payload = build_payload(today)
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    dated = WEB_DATA / f"movers-why-{today}.json"
    live = WEB_DATA / "movers-why-live.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    dated.write_text(text, encoding="utf-8")
    live.write_text(text, encoding="utf-8")
    n_pinned = sum(1 for s in payload["stocks"] if s["events"])
    print(f"[movers_why] {len(payload['stocks'])} movers, {n_pinned} with news → {dated.name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 모듈 무결성 + 테스트 유지 확인**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import fetch_movers_why as m; print('ok', bool(m.build_payload), bool(m.main))"`
Expected: `ok True True`.
Run: `python3 -m pytest scripts/test_movers_why.py -v` → 5 passed.

- [ ] **Step 3: 실데이터 스모크 실행 (네트워크 — 장중/장후 모두 산출물은 나옴)**

Run: `python3 scripts/fetch_movers_why.py`
Expected: `web/data/movers-why-{today}.json` 생성. 콘솔에 `N movers, M with news`. JSON 검증:
Run: `python3 -c "import json,glob; f=sorted(glob.glob('web/data/movers-why-*.json'))[-1]; d=json.load(open(f)); print('stocks',len(d['stocks'])); print('tiers',[ (s['code'], (s['events'][0]['tier'] if s['events'] else 'none')) for s in d['stocks']][:5])"`
Expected: stocks ≤ 10, tier가 why/related/none 중 하나. (Gemini가 실패해도 tier=none으로 안전 산출.)

- [ ] **Step 4: 산출물은 커밋하지 않음 (gitignore 확인)**

Run: `git status --short web/data/movers-why-*.json`
산출물 JSON은 워크플로우가 생성·커밋하므로, 여기서는 **커밋하지 않는다**. `git stash`나 그대로 두되 다음 커밋에 포함시키지 말 것.

- [ ] **Step 5: Commit (엔진 코드만)**

```bash
git add scripts/fetch_movers_why.py
git commit -m "feat(왜움직였나): main 오케스트레이션 + movers-why-{date}.json 산출"
```

---

## Task 6: 프론트 — 홈 주도주 곡선에 핀 + 타임라인

**Files:**
- Modify: `web/stocks/index.html` (Phase A `#why-moved` 스크립트 IIFE)

- [ ] **Step 1: 핀·타임라인 렌더 추가**

Phase A의 `#why-moved` 스크립트(`window.whyMovedRender`/`draw`/`backfill` 보유)에 movers-why 로딩과 핀 그리기를 추가한다. `#why-moved` 안 `#wm-svg` 뒤에 `<div id="wm-tl"></div>`가 없으면 마크업에 추가하고, 스크립트 상단에 데이터 캐시·헬퍼를 넣는다.

마크업: `#why-moved`의 `</div>` 직전(svg·메타 span 뒤)에 추가:
```html
      <div id="wm-tl"></div>
```

스크립트: IIFE 안 `var buf={};` 다음에 추가:
```js
      var whyData={};   // code -> events[]
      var X0i=14,X1i=626,YTi=22,YBi=150;
      function timeToX(t){var p=(t||'09:00').split(':'),mm=(+p[0])*60+(+p[1]);return X0i+(X1i-X0i)*Math.min(1,Math.max(0,(mm-540)/(930-540)));}
      function loadWhy(){
        var d=new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);
        fetch('/data/movers-why-'+d+'.json').then(function(r){return r.ok?r.json():fetch('/data/movers-why-live.json').then(function(x){return x.ok?x.json():null;});})
          .then(function(j){ if(j&&j.stocks){ j.stocks.forEach(function(s){ whyData[s.code]=s.events||[]; }); if(buf[curCode])draw(curCode); } }).catch(function(){});
      }
```

`draw(code)`의 `svg.innerHTML = ...` 직후(곡선·끝점 그린 뒤)에 핀 오버레이를 append하고 타임라인을 렌더하도록 추가:
```js
        // 뉴스 핀 오버레이 (Phase B)
        var evs=whyData[code]||[], coords=pts.split(' ').map(function(p){var a=p.split(',');return {x:+a[0],y:+a[1]};});
        function yAtX(x){var b=coords[0];for(var i=0;i<coords.length;i++){if(Math.abs(coords[i].x-x)<Math.abs(b.x-x))b=coords[i];}return b.y;}
        var pinSvg='';
        evs.forEach(function(e,i){var x=timeToX(e.time),y=yAtX(x),f=e.tier==='why'?'#E03131':'#fff',st=e.tier==='why'?'#E03131':'#94A3B8',tc=e.tier==='why'?'#fff':'#64748B';
          pinSvg+='<line x1="'+x.toFixed(1)+'" y1="'+y.toFixed(1)+'" x2="'+x.toFixed(1)+'" y2="'+(y-24).toFixed(1)+'" stroke="'+st+'" stroke-width="1.3"/>'
            +'<circle cx="'+x.toFixed(1)+'" cy="'+(y-31).toFixed(1)+'" r="10" fill="'+f+'" stroke="'+st+'" stroke-width="1.6"/>'
            +'<text x="'+x.toFixed(1)+'" y="'+(y-27).toFixed(1)+'" font-size="11" font-weight="800" fill="'+tc+'" text-anchor="middle">'+(i+1)+'</text>';});
        svg.innerHTML += pinSvg;
        var tl=document.getElementById('wm-tl');
        if(tl){ tl.innerHTML = evs.length ? evs.map(function(e,i){var lbl=e.tier==='why'?'왜':'관련',nbg=e.tier==='why'?'background:#E03131;color:#fff;':'background:#fff;color:#64748B;border:1.5px solid #CBD5E1;',tcss=e.tier==='why'?'color:#E03131;background:#FEF2F2;':'color:#64748B;background:#F1F5F9;';
          return '<div style="display:flex;gap:9px;padding:7px 0;border-bottom:1px solid #F1F5F9;"><div style="flex:none;width:20px;height:20px;border-radius:50%;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;'+nbg+'">'+(i+1)+'</div><div style="flex:1;min-width:0;"><div style="font-size:11px;font-weight:700;color:#94A3B8;">'+e.time+'</div><div style="font-size:13px;font-weight:700;line-height:1.4;margin:1px 0 2px;"><a href="'+e.url+'" target="_blank" rel="noopener" style="color:#0F172A;text-decoration:none;">'+e.headline+'</a><span style="font-size:10px;font-weight:800;border-radius:5px;padding:1px 6px;margin-left:6px;'+tcss+'">'+lbl+'</span></div><div style="font-size:12px;color:#334155;">'+e.why+'</div><div style="font-size:11px;color:#94A3B8;margin-top:2px;">출처 · '+e.source+'</div></div></div>';}).join('')
          : '<div style="font-size:12px;color:#64748B;padding:10px 2px;text-align:center;">📭 오늘 관련 뉴스 없음 · 수급/테마 추정</div>'; }
```

마지막으로 IIFE 끝 `backfill(curCode);` 옆에 `loadWhy();` 호출 추가.

- [ ] **Step 2: 프리뷰 검증** (vercel dev 실행 중, localhost:3000)

먼저 산출물이 있어야 함: `python3 scripts/fetch_movers_why.py` 1회 실행(없으면 핀 0개가 정상).
preview로 `/stocks/` 로드 → preview_eval:
`document.querySelectorAll('#wm-svg circle').length` ≥ 1 (끝점) ; 무버에 뉴스 있으면 `#wm-tl` 항목 ≥ 1.
콘솔 에러 0. 뉴스 없는 종목 타일 선택 시 "오늘 관련 뉴스 없음" 표기.

- [ ] **Step 3: Commit**

```bash
git add web/stocks/index.html
git commit -m "feat(왜움직였나): 홈 주도주 곡선에 뉴스 핀 + 타임라인"
```

---

## Task 7: 프론트 — 상세 페이지 곡선에 핀 + 타임라인

**Files:**
- Modify: `scripts/templates/stocks/detail.html` (intra-card)
- Modify: `web/assets/stocks.js` (Phase A intraday IIFE)

- [ ] **Step 1: 타임라인 컨테이너 추가** — `detail.html`의 `#intra-card` 안 `</div>` 직전(svg 뒤)에 추가:

```html
        <div id="intra-tl" style="margin-top:6px;"></div>
```

- [ ] **Step 2: stocks.js intraday IIFE에 핀·타임라인 추가**

Phase A IIFE에서 곡선 그린 뒤(`card.style.display='';` 직전) movers-why를 fetch해 핀+타임라인을 그린다. 코드 매핑은 `card` 의 `data-code` 사용.

`web/assets/stocks.js`의 intraday IIFE 안, `var pts=...` 계산 직후·`document.getElementById('intra-svg').innerHTML=...` 다음에 추가:
```js
    var coords2=vals.map(function(v,i){return {x:X0+(X1-X0)*(i/(n-1)),y:YB-(YB-YT)*((v-lo)/span)};});
    function yAtX2(x){var b=coords2[0];for(var i=0;i<coords2.length;i++){if(Math.abs(coords2[i].x-x)<Math.abs(b.x-x))b=coords2[i];}return b.y;}
    function t2x(t){var p=(t||'09:00').split(':'),mm=(+p[0])*60+(+p[1]);return X0+(X1-X0)*Math.min(1,Math.max(0,(mm-540)/(930-540)));}
    var dnow=new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);
    fetch('/data/movers-why-'+dnow+'.json').then(function(r){return r.ok?r.json():null;}).then(function(j){
      if(!j||!j.stocks)return;
      var me=j.stocks.filter(function(s){return s.code===code;})[0];
      var evs=(me&&me.events)||[];
      var svgEl=document.getElementById('intra-svg'),add='';
      evs.forEach(function(e,i){var x=t2x(e.time),y=yAtX2(x),f=e.tier==='why'?'#E03131':'#fff',st=e.tier==='why'?'#E03131':'#94A3B8',tc=e.tier==='why'?'#fff':'#64748B';
        add+='<line x1="'+x.toFixed(1)+'" y1="'+y.toFixed(1)+'" x2="'+x.toFixed(1)+'" y2="'+(y-24).toFixed(1)+'" stroke="'+st+'" stroke-width="1.3"/><circle cx="'+x.toFixed(1)+'" cy="'+(y-31).toFixed(1)+'" r="10" fill="'+f+'" stroke="'+st+'" stroke-width="1.6"/><text x="'+x.toFixed(1)+'" y="'+(y-27).toFixed(1)+'" font-size="11" font-weight="800" fill="'+tc+'" text-anchor="middle">'+(i+1)+'</text>';});
      svgEl.innerHTML+=add;
      var tl=document.getElementById('intra-tl');
      if(tl&&evs.length){ tl.innerHTML=evs.map(function(e,i){var lbl=e.tier==='why'?'왜':'관련',nbg=e.tier==='why'?'background:#E03131;color:#fff;':'background:#fff;color:#64748B;border:1.5px solid #CBD5E1;',tcss=e.tier==='why'?'color:#E03131;background:#FEF2F2;':'color:#64748B;background:#F1F5F9;';
        return '<div style="display:flex;gap:9px;padding:7px 0;border-bottom:1px solid #F1F5F9;"><div style="flex:none;width:20px;height:20px;border-radius:50%;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;'+nbg+'">'+(i+1)+'</div><div style="flex:1;min-width:0;"><div style="font-size:11px;font-weight:700;color:#94A3B8;">'+e.time+'</div><div style="font-size:13px;font-weight:700;line-height:1.4;margin:1px 0 2px;"><a href="'+e.url+'" target="_blank" rel="noopener" style="color:#0F172A;text-decoration:none;">'+e.headline+'</a><span style="font-size:10px;font-weight:800;border-radius:5px;padding:1px 6px;margin-left:6px;'+tcss+'">'+lbl+'</span></div><div style="font-size:12px;color:#334155;">'+e.why+'</div><div style="font-size:11px;color:#94A3B8;margin-top:2px;">출처 · '+e.source+'</div></div></div>';}).join(''); }
    }).catch(function(){});
```

- [ ] **Step 3: 한 종목 재생성 후 검증**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import generate_html as g, json; s=[x for x in json.load(open('scripts/config/stocks.json')) if x['code']=='005930'][0]; print(g.build_stock_page(s, []))"`
Run: `grep -c 'intra-tl' web/stocks/005930/index.html` → `1`.
preview `/stocks/005930/` → 콘솔 에러 0. movers-why에 005930 이벤트가 있으면 `#intra-svg circle` 증가 + `#intra-tl` 항목 표시. 없으면 곡선만(정상).
검증 후 `git checkout web/stocks/005930/index.html` (재생성 산출물 폐기 — 전체 재생성은 별도).

- [ ] **Step 4: Commit (템플릿·JS만)**

```bash
git add scripts/templates/stocks/detail.html web/assets/stocks.js
git commit -m "feat(왜움직였나): 상세 페이지 곡선에 뉴스 핀 + 타임라인"
```

---

## Task 8: GHA 스케줄 — 30분 cadence 엔진 추가

**Files:**
- Modify: `.github/workflows/kospi-news-live.yml`

기존 `.github/workflows/kospi-news-live.yml`은 `workflow_dispatch`로 trigger되며(cron-job.org가 30분 cadence dispatch), `run` job에 `📰 이슈 수집`(fetch_news_live.py) → `💾 JSON 커밋 & 푸시` → `🚀 GitHub Pages 배포` 스텝이 있다. env에 `GEMINI_API_KEY`가 이미 주입돼 있고, 의존성은 `google-genai`. **이 워크플로우는 자동으로 main 커밋·push·gh-pages 배포한다** — 즉 이 변경이 push되면 엔진이 라이브로 돈다(로컬에선 영향 없음).

- [ ] **Step 1: `📰 이슈 수집` 스텝 다음에 movers-why 스텝 추가**

`- name: 📰 이슈 수집` 스텝(`run: python3 scripts/fetch_news_live.py`) 바로 뒤에 삽입(`continue-on-error: true`로 뉴스 잡 보호, env는 job-level GEMINI_API_KEY 상속):

```yaml
      - name: 📈 왜 움직였나 수집
        continue-on-error: true
        run: python3 scripts/fetch_movers_why.py
```

- [ ] **Step 2: 커밋 스텝의 `git add`에 movers-why 산출물 추가**

`💾 JSON 커밋 & 푸시` 스텝의 첫 `git add` 라인을 아래처럼 movers-why 포함으로 교체:

```yaml
          git add web/data/kospi-news-live.json "web/data/kospi-news-$(TZ=Asia/Seoul date +'%Y-%m-%d').json" web/data/movers-why-live.json "web/data/movers-why-$(TZ=Asia/Seoul date +'%Y-%m-%d').json" 2>/dev/null || true
```

(그 다음 줄의 `git add web/data/kospi-news-live.json` 폴백은 그대로 둔다.)

- [ ] **Step 3: YAML 문법 검증**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/kospi-news-live.yml')); print('yaml ok')"`
Expected: `yaml ok`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/kospi-news-live.yml
git commit -m "ci(왜움직였나): movers-why 엔진 30분 cadence 스케줄 추가"
```

---

## Task 9: 정리 — 임시 시안 파일 제거

**Files:**
- Delete: `web/preview-movers-why.html`, `web/preview-hub-pins.html`

- [ ] **Step 1: 시안 파일 제거 (설계 레퍼런스 역할 종료, 스펙 문서로 남음)**

```bash
git rm web/preview-movers-why.html web/preview-hub-pins.html
git commit -m "chore(왜움직였나): Phase B 시안 프리뷰 파일 제거"
```

(두 파일이 git에 커밋된 적 없으면 `rm`으로 삭제 후 커밋 불필요 — 산출물 파일 정리만.)

---

## 검증 기준 (Phase B 완료 정의)

1. `fetch_movers_why.py`가 무버 최대 10종목을 추리고 `movers-why-{date}.json`을 산출(임계값 미달 종목 제외).
2. 방향게이트: 긍정+상승→`why`, 긍정+하락/방향어 반대→`related`, 기사 0건→`none` (단위 테스트로 강제).
3. 홈 주도주 곡선 위에 핀이 실제 시각에 찍히고 번호 타임라인과 연결, 타일 스왑 시 종목별로 바뀐다.
4. 상세 페이지 곡선에도 동일 핀·타임라인. 뉴스 없으면 "오늘 관련 뉴스 없음" 정직 표기.
5. 휴장일·데이터 없음·Gemini 실패 시 깨짐 없이 숨김(tier=none), 콘솔 에러 0.
6. 모든 핀에 실제 RSS 출처 링크. 날짜·헤드라인 생성 0 (RSS pub_date 보장).

## 후속 (범위 밖)

- 전체 41종목 상세 페이지 재생성·커밋(핀은 클라이언트 fetch라 재생성 없이도 표시되나, 타임라인 컨테이너 `#intra-tl`는 재생성 필요 → Task 7 후 `--stocks` 1회).
- 2차: 클릭 시 실시간 RSS 보강, ETF·비주도주 확대.
