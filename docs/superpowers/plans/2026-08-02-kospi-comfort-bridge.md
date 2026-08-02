# 코스피 브리핑 위로카드 재구성 + 밤사이 브리지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 아침 브리핑(`web/briefings/{date}/kospi/index.html`)에 두 가지를 반영한다 — (1) "이렇게 보는 이유" 섹션 제거 + "위로 한 줄" 카드에 텔레그램과 동기화된 구루 명언 추가, (2) 간밤 미국 정규장 vs 한국 직전 마감을 섹터별 %p로 비교하는 "밤사이 브리지" 신규 섹션.

**Architecture:** 두 기능 모두 LLM 미개입 — 위로카드는 정적 큐레이션 데이터(`data/guru_quotes.json`) 재사용, 브리지는 결정론적 수치 계산(`fetch_data.py`)이다. 두 기능 다 데이터 계산(파이썬 순수함수, 단위 테스트) → `generate_html.py` 컨텍스트 변환 → Jinja 템플릿 렌더 3단 구조를 따른다. 같은 템플릿 파일(`kospi.html`)을 건드리므로 Part 1(위로카드, 작고 독립적)을 먼저 끝내고 Part 2(브리지, 신규 데이터 파이프라인)를 진행한다 — 두 파트는 템플릿 내 서로 다른 위치를 건드려 충돌하지 않는다.

**Tech Stack:** Python 3(순수 함수 + pytest), Jinja2 템플릿, 순수 CSS(다크모드 변수 기반).

**참고 스펙:**
- [`docs/superpowers/specs/2026-08-02-kospi-comfort-card-design.md`](../specs/2026-08-02-kospi-comfort-card-design.md)
- [`docs/superpowers/specs/2026-08-02-overnight-bridge-design.md`](../specs/2026-08-02-overnight-bridge-design.md)

---

## Part 1 — 코스피 위로 카드 재구성

### Task 1: 명언 동기화 — `call_claude.py`가 오늘의 명언을 저장

**Files:**
- Modify: `scripts/call_claude.py`
- Test: `scripts/test_quote_today.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_quote_today.py` 신규 생성:

```python
# call_claude._save_todays_quote / _load_todays_quote_for_telegram 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 -m pytest scripts/test_quote_today.py -v"""
import json

import call_claude as cc


def test_save_todays_quote_writes_file(tmp_path, monkeypatch):
    quotes_file = tmp_path / "guru_quotes.json"
    quotes_file.write_text(
        json.dumps([{"quote": "테스트 명언", "author": "테스트 저자"}], ensure_ascii=False),
        encoding="utf-8",
    )
    out_file = tmp_path / "quote_today.json"
    monkeypatch.setattr(cc, "GURU_QUOTES_FILE", quotes_file)
    monkeypatch.setattr(cc, "QUOTE_TODAY_FILE", out_file)

    cc._save_todays_quote("2026-08-02")

    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved == {"date": "2026-08-02", "quote": "테스트 명언", "author": "테스트 저자"}


def test_save_todays_quote_missing_source_is_noop(tmp_path, monkeypatch):
    out_file = tmp_path / "quote_today.json"
    monkeypatch.setattr(cc, "GURU_QUOTES_FILE", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(cc, "QUOTE_TODAY_FILE", out_file)

    cc._save_todays_quote("2026-08-02")  # 예외 없이 조용히 아무 것도 안 함

    assert not out_file.exists()


def test_save_todays_quote_empty_list_is_noop(tmp_path, monkeypatch):
    quotes_file = tmp_path / "guru_quotes.json"
    quotes_file.write_text("[]", encoding="utf-8")
    out_file = tmp_path / "quote_today.json"
    monkeypatch.setattr(cc, "GURU_QUOTES_FILE", quotes_file)
    monkeypatch.setattr(cc, "QUOTE_TODAY_FILE", out_file)

    cc._save_todays_quote("2026-08-02")

    assert not out_file.exists()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest scripts/test_quote_today.py -v`
Expected: FAIL — `AttributeError: module 'call_claude' has no attribute '_save_todays_quote'` (그리고 `GURU_QUOTES_FILE`/`QUOTE_TODAY_FILE` 없음)

- [ ] **Step 3: `call_claude.py`에 상수·함수 추가**

`scripts/call_claude.py`의 `DATA_DIR = BASE_DIR / "data"` 줄(30번째 줄) 바로 아래에 추가:

```python
GURU_QUOTES_FILE = DATA_DIR / "guru_quotes.json"
QUOTE_TODAY_FILE = DATA_DIR / "quote_today.json"
```

`render_outputs` 함수(`def render_outputs(...)`) 바로 위에 새 함수 추가:

```python
def _save_todays_quote(date_str: str) -> None:
    """오늘 코스피 브리핑에 쓸 구루 명언을 하나 뽑아 quote_today.json에 저장한다.

    텔레그램(send_telegram.pick_quote)이 발송 직전 이 파일을 읽어 같은 명언을 쓴다
    — 웹·텔레그램이 같은 날 서로 다른 명언을 보여주지 않도록 뽑는 시점을 여기로 당긴다.
    실패해도 조용히 넘어간다(명언은 위로 카드의 부가 요소라 §0 실측 게이트 대상이 아님).
    """
    if not GURU_QUOTES_FILE.exists():
        return
    try:
        with open(GURU_QUOTES_FILE, encoding="utf-8") as f:
            quotes = json.load(f)
    except (json.JSONDecodeError, OSError):
        return
    if not quotes:
        return
    item = random.choice(quotes)
    with open(QUOTE_TODAY_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"date": date_str, "quote": item["quote"], "author": item["author"]},
            f, ensure_ascii=False, indent=2,
        )
```

`render_outputs` 함수 본문 맨 앞(`if briefing_type == "kospi-close":` 줄 바로 위)에 삽입:

```python
    if briefing_type == "kospi":
        _save_todays_quote(date_str)

```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest scripts/test_quote_today.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/call_claude.py scripts/test_quote_today.py
git commit -m "feat(코스피): 코스피 브리핑 렌더 시 오늘의 명언을 quote_today.json에 저장"
```

---

### Task 2: `send_telegram.py`가 `quote_today.json`을 우선 사용하도록 수정

**Files:**
- Modify: `scripts/send_telegram.py:187-196` (`pick_quote`)
- Test: `scripts/test_pick_quote.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_pick_quote.py` 신규 생성:

```python
# send_telegram.pick_quote 동기화 로직 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 -m pytest scripts/test_pick_quote.py -v"""
import json
from datetime import datetime

import pytz

import send_telegram as st

KST = pytz.timezone("Asia/Seoul")


def _today_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def test_pick_quote_uses_quote_today_when_date_matches(tmp_path, monkeypatch):
    quote_today = tmp_path / "quote_today.json"
    quote_today.write_text(
        json.dumps({"date": _today_str(), "quote": "오늘의 명언", "author": "오늘 저자"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "QUOTE_TODAY_FILE", quote_today)
    monkeypatch.setattr(st, "GURU_QUOTES_FILE", tmp_path / "unused.json")  # 폴백 경로 안 타는지 확인용

    result = st.pick_quote()

    assert "오늘의 명언" in result
    assert "오늘 저자" in result


def test_pick_quote_falls_back_when_date_stale(tmp_path, monkeypatch):
    quote_today = tmp_path / "quote_today.json"
    quote_today.write_text(
        json.dumps({"date": "2000-01-01", "quote": "옛날 명언", "author": "옛날 저자"}, ensure_ascii=False),
        encoding="utf-8",
    )
    quotes_file = tmp_path / "guru_quotes.json"
    quotes_file.write_text(
        json.dumps([{"quote": "폴백 명언", "author": "폴백 저자"}], ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "QUOTE_TODAY_FILE", quote_today)
    monkeypatch.setattr(st, "GURU_QUOTES_FILE", quotes_file)

    result = st.pick_quote()

    assert "폴백 명언" in result
    assert "옛날 명언" not in result


def test_pick_quote_falls_back_when_quote_today_missing(tmp_path, monkeypatch):
    quotes_file = tmp_path / "guru_quotes.json"
    quotes_file.write_text(
        json.dumps([{"quote": "폴백 명언2", "author": "폴백 저자2"}], ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(st, "QUOTE_TODAY_FILE", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(st, "GURU_QUOTES_FILE", quotes_file)

    result = st.pick_quote()

    assert "폴백 명언2" in result
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest scripts/test_pick_quote.py -v`
Expected: FAIL — `AttributeError: module 'send_telegram' has no attribute 'QUOTE_TODAY_FILE'`

- [ ] **Step 3: `send_telegram.py` 수정**

`scripts/send_telegram.py:182` 부근 `GURU_QUOTES_FILE = DATA_DIR / "guru_quotes.json"` 줄 바로 아래에 추가:

```python
QUOTE_TODAY_FILE = DATA_DIR / "quote_today.json"
```

기존 `pick_quote()` 함수(187~196번째 줄)를 교체:

```python
def pick_quote() -> str:
    """오늘 코스피 브리핑이 뽑아둔 quote_today.json을 우선 쓰고,
    없거나 날짜가 오늘이 아니면 guru_quotes.json에서 랜덤으로 뽑는다.
    (웹·텔레그램이 같은 날 다른 명언을 보여주지 않도록 동기화 — kospi 타입만 quote_today.json을 씀)"""
    import random
    import pytz
    from datetime import datetime

    if QUOTE_TODAY_FILE.exists():
        try:
            with open(QUOTE_TODAY_FILE, encoding="utf-8") as f:
                today_quote = json.load(f)
            today_str = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d")
            if today_quote.get("date") == today_str and today_quote.get("quote"):
                return f"\n\n━━━━━━━━━━━━━━━━━━━━\n💡 <i>\"{today_quote['quote']}\"</i>\n— {today_quote['author']}"
        except (json.JSONDecodeError, OSError):
            pass

    if not GURU_QUOTES_FILE.exists():
        return ""
    with open(GURU_QUOTES_FILE, encoding="utf-8") as f:
        quotes = json.load(f)
    if not quotes:
        return ""
    item = random.choice(quotes)
    return f"\n\n━━━━━━━━━━━━━━━━━━━━\n💡 <i>\"{item['quote']}\"</i>\n— {item['author']}"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest scripts/test_pick_quote.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/send_telegram.py scripts/test_pick_quote.py
git commit -m "feat(텔레그램): 명언을 quote_today.json과 동기화, 없으면 기존 랜덤 폴백"
```

---

### Task 3: `generate_html.py`가 `quote_today.json`을 읽어 컨텍스트에 주입

**Files:**
- Modify: `scripts/generate_html.py`
- Test: `scripts/test_load_quote_today.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_load_quote_today.py` 신규 생성:

```python
# generate_html._load_quote_today 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 -m pytest scripts/test_load_quote_today.py -v"""
import json

import generate_html as g


def test_load_quote_today_returns_dict_when_date_matches(tmp_path, monkeypatch):
    p = tmp_path / "quote_today.json"
    p.write_text(
        json.dumps({"date": "2026-08-02", "quote": "명언", "author": "저자"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(g, "QUOTE_TODAY_FILE", p)

    result = g._load_quote_today("2026-08-02")

    assert result == {"quote": "명언", "author": "저자"}


def test_load_quote_today_empty_when_date_mismatch(tmp_path, monkeypatch):
    p = tmp_path / "quote_today.json"
    p.write_text(
        json.dumps({"date": "2026-08-01", "quote": "명언", "author": "저자"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(g, "QUOTE_TODAY_FILE", p)

    assert g._load_quote_today("2026-08-02") == {}


def test_load_quote_today_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "QUOTE_TODAY_FILE", tmp_path / "does_not_exist.json")

    assert g._load_quote_today("2026-08-02") == {}


def test_load_quote_today_empty_when_malformed(tmp_path, monkeypatch):
    p = tmp_path / "quote_today.json"
    p.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(g, "QUOTE_TODAY_FILE", p)

    assert g._load_quote_today("2026-08-02") == {}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest scripts/test_load_quote_today.py -v`
Expected: FAIL — `AttributeError: module 'generate_html' has no attribute 'QUOTE_TODAY_FILE'`

- [ ] **Step 3: `generate_html.py`에 상수·함수 추가**

`scripts/generate_html.py:39`(`WEB_DIR = BASE_DIR / "web"` 줄) 바로 아래에 추가:

```python
QUOTE_TODAY_FILE = DATA_DIR / "quote_today.json"
```

`build_reasons` 함수(406번째 줄 부근) 바로 위에 새 함수 추가:

```python
def _load_quote_today(target_date: str) -> dict:
    """quote_today.json이 이 브리핑 날짜와 일치할 때만 {quote, author}를 반환한다.
    call_claude.py의 render_outputs()가 코스피 타입일 때만 이 파일을 쓴다."""
    if not QUOTE_TODAY_FILE.exists():
        return {}
    try:
        q = load_json(QUOTE_TODAY_FILE)
    except (json.JSONDecodeError, OSError):
        return {}
    if q.get("date") != target_date or not q.get("quote") or not q.get("author"):
        return {}
    return {"quote": q["quote"], "author": q["author"]}
```

`render_briefing` 함수의 `else:` 분기(코스피 타입, 1143번째 줄 부근 `ctx.update(build_prediction(...))` 다음 줄)에 추가:

```python
        ctx["quote_today"] = _load_quote_today(target_date)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest scripts/test_load_quote_today.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_html.py scripts/test_load_quote_today.py
git commit -m "feat(HTML생성): quote_today.json을 코스피 브리핑 컨텍스트에 주입"
```

---

### Task 4: 템플릿 — "이렇게 보는 이유" 제거 + 위로 카드 C2 재구성

**Files:**
- Modify: `scripts/templates/briefings/kospi.html:42`
- Modify: `scripts/templates/sections/_comfort_line.html`
- Modify: `web/assets/style.css`

- [ ] **Step 1: `kospi.html`에서 "이렇게 보는 이유" include 제거**

`scripts/templates/briefings/kospi.html`에서:

```jinja
            {% if key_drivers %}{% include "sections/reasons.html" %}{% endif %}
            {% if comfort_line %}{% include "sections/_comfort_line.html" %}{% endif %}
```

→

```jinja
            {% if comfort_line %}{% include "sections/_comfort_line.html" %}{% endif %}
```

(`key_drivers` 데이터 생성·검증 로직은 건드리지 않는다 — 렌더링 include 한 줄만 제거.)

- [ ] **Step 2: `_comfort_line.html`을 C2(따옴표 글리프) 구조로 교체**

`scripts/templates/sections/_comfort_line.html` 전체를 교체:

```jinja
{# 위로 카드 — quote_today(구루 명언) 있으면 위에 주인공으로, 없으면 위로 한 줄만. C2: 따옴표 글리프. #}
<div class="comfort-line">
  {% if quote_today %}
  <div class="guru-quote">
    <p class="guru-quote__mark" aria-hidden="true">&ldquo;</p>
    <p class="guru-quote__text">{{ quote_today.quote }}</p>
    <p class="guru-quote__author">— {{ quote_today.author }}</p>
  </div>
  <div class="guru-quote__hr"></div>
  {% endif %}
  <div class="comfort-line__row">
    <div class="comfort-line__badge">
      <svg class="comfort-line__icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
    </div>
    <p class="comfort-line__text">{{ comfort_line | safe }}</p>
  </div>
</div>
```

- [ ] **Step 3: CSS 추가 — 기존 `.comfort-line` 리팩터 + 신규 `.guru-quote*`**

`web/assets/style.css:268-271` 기존 블록:

```css
.comfort-line{display:flex;align-items:center;gap:10px;margin-top:14px;padding:14px 16px;background:var(--surface-soft);border-radius:12px;}
.comfort-line__badge{flex-shrink:0;width:30px;height:30px;border-radius:50%;background:var(--surface-inset);display:flex;align-items:center;justify-content:center;}
.comfort-line__icon{color:var(--muted);}
.comfort-line__text{margin:0;font-size:14px;line-height:1.6;color:var(--ink);text-align:left;}
```

→ 교체(`.comfort-line`은 카드 컨테이너로, flex 레이아웃은 새 `.comfort-line__row`로 이동):

```css
.comfort-line{margin-top:14px;padding:14px 16px;background:var(--surface-soft);border-radius:12px;}
.comfort-line__row{display:flex;align-items:center;gap:10px;}
.comfort-line__badge{flex-shrink:0;width:30px;height:30px;border-radius:50%;background:var(--surface-inset);display:flex;align-items:center;justify-content:center;}
.comfort-line__icon{color:var(--muted);}
.comfort-line__text{margin:0;font-size:14px;line-height:1.6;color:var(--ink);text-align:left;}
.guru-quote__mark{font-family:Georgia,serif;font-size:38px;line-height:1;color:var(--hairline);margin:0 0 -6px;user-select:none;}
.guru-quote__text{margin:0;font-size:15px;line-height:1.6;font-weight:600;color:var(--ink);letter-spacing:-.01em;}
.guru-quote__author{margin:8px 0 0;font-size:13px;color:var(--muted);font-weight:500;}
.guru-quote__hr{height:1px;background:var(--hairline);margin:13px 0;}
```

(`.comfort-line`·`.comfort-line__badge`·`.comfort-line__icon`·`.comfort-line__text`는 이 템플릿에서만 쓰인다 — 리팩터 전 `grep -rln "comfort-line" scripts/templates/ web/assets/`로 재확인했다.)

- [ ] **Step 4: 로컬 렌더로 확인**

```bash
python3 scripts/generate_html.py --type kospi --date 2026-07-31 --data-file data/latest_kospi.json --force
```

Expected: 에러 없이 완료. (`data/latest_kospi.json`이 로컬에 없으면 아무 최근 날짜의 `web/briefings/{date}/kospi/analysis_snapshot.json`을 `--data-file`로 지정해 재실행 — 이 스텝은 코드 문법·Jinja 렌더 오류만 잡는 용도이므로 날짜 정합성 게이트에 걸리면 다른 과거 날짜로 재시도한다.)

Run: `grep -c "rz-title" web/briefings/2026-07-31/kospi/index.html`
Expected: `0` ("이렇게 보는 이유" 섹션이 사라졌는지 확인)

Run: `grep -c "guru-quote" web/briefings/2026-07-31/kospi/index.html`
Expected: `1` 이상 (quote_today가 없으면 이 블록 자체가 안 나올 수 있음 — `data/quote_today.json`이 로컬에 없다면 정상적으로 0일 수 있다. 그 경우 Task 1에서 만든 `_save_todays_quote`를 수동으로 한 번 실행해 파일을 만든 뒤 재확인한다.)

이 스텝에서 생성된 `web/briefings/2026-07-31/...` 변경분은 검증용이므로 `git diff`로 확인 후 `git checkout -- web/briefings/2026-07-31/` 로 되돌린다(라이브 브리핑 파일을 실수로 커밋하지 않기 위함 — §12·§18 원칙).

- [ ] **Step 5: 커밋**

```bash
git add scripts/templates/briefings/kospi.html scripts/templates/sections/_comfort_line.html web/assets/style.css
git commit -m "feat(코스피): 이렇게 보는 이유 제거, 위로 카드에 구루 명언 추가(C2)"
```

---

## Part 2 — 밤사이 브리지

### Task 5: `fetch_data.py`에 `fetch_overnight_bridge()` 순수함수 추가

**Files:**
- Modify: `scripts/fetch_data.py`
- Test: `scripts/test_overnight_bridge.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_overnight_bridge.py` 신규 생성:

```python
# fetch_data.fetch_overnight_bridge 순수함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 -m pytest scripts/test_overnight_bridge.py -v"""
from datetime import datetime, timedelta

import fetch_data as m

KST = m.KST


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _snapshot(generated_at: str) -> dict:
    return {
        "generated_at": generated_at,
        "stocks": {
            "005930": {"name": "삼성전자", "change_pct": 28.38},
            "000660": {"name": "SK하이닉스", "change_pct": 24.0},
            "267260": {"name": "HD현대일렉트릭", "change_pct": 20.13},
            "010120": {"name": "LS일렉트릭", "change_pct": 18.0},
        },
    }


def _macro(**overrides) -> dict:
    base = {
        "SOXX": {"change_pct": 8.5},
        "GEV": {"change_pct": 6.0}, "VRT": {"change_pct": 5.08},
        "ITA": {"change_pct": 0.79},
        "LIT": {"change_pct": 4.6},
        "TSLA": {"change_pct": 0.5}, "F": {"change_pct": 0.28},
        "XBI": {"change_pct": 2.4},
        "JPM": {"change_pct": -0.1}, "KBE": {"change_pct": -0.38},
    }
    base.update(overrides)
    return base


def test_normal_case_returns_seven_sectors_no_ship():
    today = datetime.now(KST)
    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(today)))

    assert rows is not None
    sectors = {r["sector"] for r in rows}
    assert "조선" not in sectors
    assert len(rows) <= 7

    semicon = next(r for r in rows if r["sector"] == "반도체")
    assert semicon["us_change"] == 8.5
    assert semicon["kr_change"] == 26.19  # (28.38+24.0)/2
    assert semicon["gap_pp"] == 17.7


def test_one_us_bellwether_missing_drops_only_that_sector():
    today = datetime.now(KST)
    macro = _macro()
    del macro["SOXX"]  # 반도체 미국 측 결측

    rows = m.fetch_overnight_bridge(macro, _snapshot(_iso(today)))

    sectors = {r["sector"] for r in rows}
    assert "반도체" not in sectors
    assert "전력기기" in sectors  # 나머지는 정상


def test_monday_case_not_treated_as_stale():
    # 금요일 16:33 생성 스냅샷을 월요일 07:25에 읽는 상황 (날짜 차이 3일)
    friday = datetime.now(KST) - timedelta(days=3)
    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(friday)))

    assert rows is not None
    assert len(rows) > 0


def test_stale_snapshot_returns_none():
    old = datetime.now(KST) - timedelta(days=6)
    rows = m.fetch_overnight_bridge(_macro(), _snapshot(_iso(old)))

    assert rows is None


def test_all_sectors_fail_returns_none():
    rows = m.fetch_overnight_bridge({}, _snapshot(_iso(datetime.now(KST))))

    assert rows is None


def test_2026_07_27_incident_replay_shows_double_count():
    """§24 실사고 리플레이 — EWY -6.27%는 같은 날 코스피 -5.72% 급락을 이미 반영한 값이었다.
    반도체 섹터로 근사 재현: 미국이 크게 밀렸는데 한국도 비슷하게 밀리면 gap이 0에 가까워야
    '이미 반영됨'이 드러난다(선반영이 거의 없다는 뜻)."""
    macro = _macro(SOXX={"change_pct": -4.25})
    snapshot = {
        "generated_at": _iso(datetime.now(KST)),
        "stocks": {
            "005930": {"name": "삼성전자", "change_pct": -5.72},
            "000660": {"name": "SK하이닉스", "change_pct": -5.72},
        },
    }

    rows = m.fetch_overnight_bridge(macro, snapshot)

    semicon = next(r for r in rows if r["sector"] == "반도체")
    assert semicon["gap_pp"] < 3.0  # 미국도 이미 밀렸으므로 갭이 크지 않아야 함(이중계상 아님을 확인)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest scripts/test_overnight_bridge.py -v`
Expected: FAIL — `AttributeError: module 'fetch_data' has no attribute 'fetch_overnight_bridge'`

- [ ] **Step 3: `fetch_data.py`에 구현 추가**

`scripts/fetch_data.py`의 `SECTOR_FOCUS_STOCKS = {` 정의(26번째 줄) 바로 위에 추가:

```python
# 밤사이 브리지 — 섹터별 미국 비교 대상 (ETF 있으면 ETF 단독, 없으면 개별주 평균).
# stock_universe.json의 bellwethers를 손으로 골랐다 — ETF 여부가 데이터에 없어 수동 매핑.
# ⚠️ SECTOR_FOCUS_STOCKS(바로 아래, 중단된 sector_focus 섹션용)와 섹터 구성이 다르다.
# 재사용 금지 — stock_universe.json만 단일 소스로 쓴다(§20·§30 이중소스 재발 방지).
BRIDGE_US_LEG = {
    "semicon": (["SOXX"], "반도체 ETF"),
    "power":   (["GEV", "VRT"], "GE Vernova·Vertiv"),
    "defense": (["ITA"], "방산 ETF"),
    "battery": (["LIT"], "리튬 ETF"),
    "auto":    (["TSLA", "F"], "테슬라·포드"),
    "bio":     (["XBI"], "바이오 ETF"),
    "finance": (["JPM", "KBE"], "JP모건·은행 ETF"),
}
_BRIDGE_MAX_STALE_DAYS = 5
```

`fetch_sector_stocks()` 함수(706번째 줄 부근) 바로 아래에 새 함수 추가:

```python
def fetch_overnight_bridge(macro: dict, snapshot: dict) -> list | None:
    """섹터별 간밤 미국 정규장 vs 한국 직전 마감 등락 비교(§24 이중계상 UI화, 순수함수).

    macro: get_ticker_full() 결과 딕셔너리 (티커 → {price, change_pct, ...}, 실패한 티커는 키 자체가 없음).
    snapshot: web/data/stocks-snapshot.json 파싱 결과.
    반환: [{"sector","us_label","us_change","kr_label","kr_change","gap_pp"}, ...] 또는 None(섹션 생략).
    """
    snap_date_str = str(snapshot.get("generated_at") or "")[:10]
    try:
        snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date()
    except ValueError:
        print("[fetch_data] overnight_bridge: stocks-snapshot.json generated_at 파싱 실패 — 섹션 생략", file=sys.stderr)
        return None
    if (datetime.now(KST).date() - snap_date).days > _BRIDGE_MAX_STALE_DAYS:
        print(f"[fetch_data] overnight_bridge: stocks-snapshot.json이 {_BRIDGE_MAX_STALE_DAYS}일 넘게 스테일 — 섹션 생략", file=sys.stderr)
        return None

    universe_path = BASE_DIR / "scripts" / "config" / "stock_universe.json"
    with open(universe_path, encoding="utf-8") as f:
        sectors = json.load(f)["sectors"]

    snap_stocks = snapshot.get("stocks") or {}
    rows = []
    for key, (us_tickers, us_label) in BRIDGE_US_LEG.items():
        cfg = sectors.get(key)
        if not cfg:
            continue
        us_vals = [macro[t]["change_pct"] for t in us_tickers
                   if macro.get(t, {}).get("change_pct") is not None]
        if not us_vals:
            print(f"[fetch_data] overnight_bridge: {key} 미국 벨웨더 수집 실패 — 해당 섹터 생략", file=sys.stderr)
            continue

        kr_codes = [s["code"] for s in cfg.get("stocks", [])[:2]]
        kr_vals, kr_names = [], []
        for code in kr_codes:
            s = snap_stocks.get(code)
            if s and s.get("change_pct") is not None:
                kr_vals.append(s["change_pct"])
                kr_names.append(s.get("name", code))
        if not kr_vals:
            print(f"[fetch_data] overnight_bridge: {key} 한국 대표종목 데이터 없음 — 해당 섹터 생략", file=sys.stderr)
            continue

        us_change = round(sum(us_vals) / len(us_vals), 2)
        kr_change = round(sum(kr_vals) / len(kr_vals), 2)
        rows.append({
            "sector": cfg.get("label", key),
            "us_label": us_label,
            "us_change": us_change,
            "kr_label": "·".join(kr_names),
            "kr_change": kr_change,
            "gap_pp": round(kr_change - us_change, 1),
        })

    return rows or None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest scripts/test_overnight_bridge.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/fetch_data.py scripts/test_overnight_bridge.py
git commit -m "feat(밤사이브리지): 섹터별 미국 등락 비교 순수함수 추가"
```

---

### Task 6: `fetch_kospi_data()`에 배선 — 벨웨더 수집·스냅샷 로드·데이터 병합

**Files:**
- Modify: `scripts/fetch_data.py:739-747` (`macro_tickers`), `scripts/fetch_data.py:770-772` (섹션 7 다음), `scripts/fetch_data.py:774-825` (`data = {...}`)

- [ ] **Step 1: `macro_tickers` 리스트에 벨웨더 티커 추가**

`scripts/fetch_data.py:739-747`:

```python
    macro_tickers = ["^GSPC", "^VIX", "BZ=F", "GC=F", "^TNX",
                     "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "^SOX", "EWY",
                     "DRAM",  # Roundhill Memory & HBM ETF (삼성·하이닉스 연동 선행 지표)
                     # 미 지수선물 — 브리핑 생성 시각(07:25 KST)에 **유일하게 실시간인** 신호.
                     # SOX·나스닥·EWY는 전부 6시간 이상 묵은 미국장 종가다.
                     # NQ=F는 이미 사이드바(market_data_js.nq)에 있고, ES/YM은 그동안
                     # 미국 브리핑 경로에만 있어 코스피 prior가 쓰지 못했다.
                     "ES=F", "YM=F",
                     "^N225", "^HSI", "^TWII", "000001.SS"]  # 아시아 지역 지수 (catch-up 시그널)
```

→

```python
    macro_tickers = ["^GSPC", "^VIX", "BZ=F", "GC=F", "^TNX",
                     "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "^SOX", "EWY",
                     "DRAM",  # Roundhill Memory & HBM ETF (삼성·하이닉스 연동 선행 지표)
                     # 미 지수선물 — 브리핑 생성 시각(07:25 KST)에 **유일하게 실시간인** 신호.
                     # SOX·나스닥·EWY는 전부 6시간 이상 묵은 미국장 종가다.
                     # NQ=F는 이미 사이드바(market_data_js.nq)에 있고, ES/YM은 그동안
                     # 미국 브리핑 경로에만 있어 코스피 prior가 쓰지 못했다.
                     "ES=F", "YM=F",
                     "^N225", "^HSI", "^TWII", "000001.SS",  # 아시아 지역 지수 (catch-up 시그널)
                     # 밤사이 브리지 섹터 벨웨더 (NVDA는 위에 이미 있음, BRIDGE_US_LEG 참고)
                     "MU", "SOXX", "GEV", "VRT", "ITA", "LMT", "ALB", "LIT",
                     "TSLA", "F", "XBI", "LLY", "JPM", "KBE"]
```

- [ ] **Step 2: 섹션 7(`sector_stocks`) 다음에 브리지 계산 추가**

`scripts/fetch_data.py:770-772`:

```python
    # 7. 섹터 대표 종목 데이터 (sector_focus 할루시네이션 방지)
    print("[fetch_data]   → sector focus stocks")
    sector_stocks = fetch_sector_stocks()
```

바로 다음 줄에 추가:

```python

    # 7b. 밤사이 브리지 — 섹터별 간밤 미국 vs 한국 직전 마감 (§24 이중계상 UI화)
    print("[fetch_data]   → overnight bridge")
    try:
        with open(BASE_DIR / "web" / "data" / "stocks-snapshot.json", encoding="utf-8") as f:
            _bridge_snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[fetch_data] overnight_bridge: stocks-snapshot.json 로드 실패 ({e}) — 섹션 생략", file=sys.stderr)
        _bridge_snapshot = {}
    overnight_bridge = fetch_overnight_bridge(macro, _bridge_snapshot)
```

- [ ] **Step 3: `data = {...}` 딕셔너리에 필드 추가**

`scripts/fetch_data.py`의 `data = {` 블록에서 `"sector_stocks": sector_stocks,` 줄(823번째 줄 부근) 바로 다음에 추가:

```python
        "sector_stocks": sector_stocks,
        # 밤사이 브리지 — 섹터별 간밤 미국 vs 한국 직전 마감 %p 비교. None이면 섹션 생략.
        "overnight_bridge": overnight_bridge,
```

- [ ] **Step 4: 문법·임포트 확인 (네트워크 호출 없이)**

Run: `python3 -c "import ast; ast.parse(open('scripts/fetch_data.py').read())"`
Expected: 에러 없이 종료(문법 오류 없음)

Run: `python3 -m pytest scripts/test_overnight_bridge.py -v`
Expected: PASS (6 passed) — Task 5에서 만든 테스트가 `fetch_data.py` 재파싱에도 여전히 통과하는지 회귀 확인.

- [ ] **Step 5: 커밋**

```bash
git add scripts/fetch_data.py
git commit -m "feat(밤사이브리지): fetch_kospi_data에 벨웨더 수집·브리지 계산 배선"
```

---

### Task 7: `generate_html.py` — `overnight_bridge` 컨텍스트 변환

**Files:**
- Modify: `scripts/generate_html.py`
- Test: `scripts/test_build_overnight_bridge.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_build_overnight_bridge.py` 신규 생성:

```python
# generate_html.build_overnight_bridge 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 -m pytest scripts/test_build_overnight_bridge.py -v"""
import generate_html as g


def test_formats_positive_gap_as_seonbanyeong():
    market_data = {"overnight_bridge": [
        {"sector": "반도체", "us_label": "반도체 ETF", "us_change": 8.5,
         "kr_label": "삼성전자·SK하이닉스", "kr_change": 28.38, "gap_pp": 19.9},
    ]}

    result = g.build_overnight_bridge(market_data)

    row = result["overnight_bridge"][0]
    assert row["us_change_fmt"] == "+8.50%"
    assert row["us_cls"] == "up"
    assert row["kr_change_fmt"] == "+28.38%"
    assert row["gap_fmt"] == "+19.9%p"
    assert row["gap_cls"] == "up"
    assert row["gap_word"] == "선반영"


def test_formats_negative_gap_as_mibanyeong():
    market_data = {"overnight_bridge": [
        {"sector": "바이오", "us_label": "바이오 ETF", "us_change": 2.4,
         "kr_label": "삼성바이오로직스·셀트리온", "kr_change": -2.25, "gap_pp": -4.6},
    ]}

    result = g.build_overnight_bridge(market_data)

    row = result["overnight_bridge"][0]
    assert row["kr_cls"] == "dn"
    assert row["gap_cls"] == "dn"
    assert row["gap_word"] == "미반영"


def test_zero_gap_is_neutral():
    market_data = {"overnight_bridge": [
        {"sector": "2차전지", "us_label": "리튬 ETF", "us_change": 4.6,
         "kr_label": "LG에너지솔루션·에코프로비엠", "kr_change": 4.6, "gap_pp": 0.0},
    ]}

    result = g.build_overnight_bridge(market_data)

    row = result["overnight_bridge"][0]
    assert row["gap_cls"] == ""
    assert row["gap_word"] == "동조"


def test_none_bridge_returns_empty_list():
    result = g.build_overnight_bridge({"overnight_bridge": None})

    assert result == {"overnight_bridge": []}


def test_missing_key_returns_empty_list():
    result = g.build_overnight_bridge({})

    assert result == {"overnight_bridge": []}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest scripts/test_build_overnight_bridge.py -v`
Expected: FAIL — `AttributeError: module 'generate_html' has no attribute 'build_overnight_bridge'`

- [ ] **Step 3: `generate_html.py`에 구현 추가**

`build_reasons` 함수(406번째 줄 부근) 바로 위, `_load_quote_today`(Task 3에서 추가) 다음에 새 함수 추가:

```python
def build_overnight_bridge(market_data: dict) -> dict:
    """market_data['overnight_bridge'](fetch_data.fetch_overnight_bridge 산출, 원시 숫자)를
    템플릿용 표시 문자열로 변환. 항목 없으면 빈 리스트 → 템플릿에서 섹션 자동 생략."""
    rows = []
    for row in (market_data.get("overnight_bridge") or []):
        gap = row["gap_pp"]
        rows.append({
            "sector": row["sector"],
            "us_label": row["us_label"],
            "us_change_fmt": f"{row['us_change']:+.2f}%",
            "us_cls": "up" if row["us_change"] >= 0 else "dn",
            "kr_label": row["kr_label"],
            "kr_change_fmt": f"{row['kr_change']:+.2f}%",
            "kr_cls": "up" if row["kr_change"] >= 0 else "dn",
            "gap_fmt": f"{gap:+.1f}%p",
            "gap_cls": "up" if gap > 0 else ("dn" if gap < 0 else ""),
            "gap_word": "선반영" if gap > 0 else ("미반영" if gap < 0 else "동조"),
        })
    return {"overnight_bridge": rows}
```

`render_briefing` 함수의 `else:` 분기(코스피 타입)에서 `ctx.update(build_prediction(...))` 다음 줄에 추가(Task 3의 `ctx["quote_today"] = ...`와 같은 자리, 둘 다 있어도 순서 무관):

```python
        ctx.update(build_overnight_bridge(market_data))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest scripts/test_build_overnight_bridge.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_html.py scripts/test_build_overnight_bridge.py
git commit -m "feat(밤사이브리지): overnight_bridge 표시용 컨텍스트 변환 함수 추가"
```

---

### Task 8: 템플릿·CSS — `_overnight_bridge.html` 신규 + `kospi.html` 배선

**Files:**
- Create: `scripts/templates/sections/_overnight_bridge.html`
- Modify: `scripts/templates/briefings/kospi.html:39`
- Modify: `web/assets/style.css`

- [ ] **Step 1: 신규 템플릿 작성**

`scripts/templates/sections/_overnight_bridge.html` 신규 생성:

```jinja
{# 밤사이 브리지 — 간밤 미국 정규장 vs 한국 직전 마감, 섹터별 %p 차이. LLM 미개입(§0 산문 검증 대상 아님). #}
{% if overnight_bridge %}
<div class="open-section">
  <div class="open-section__title">밤사이 미국 → 오늘 국장</div>
  <p class="bridge-sub">간밤 미국 정규장 등락과 한국 직전 마감(전일) 등락의 차이입니다.</p>
  <div class="bridge-list">
    {% for row in overnight_bridge %}
    <div class="bridge-row">
      <span class="bridge-sector">{{ row.sector }}</span>
      <span class="bridge-leg">미 <b class="{{ row.us_cls }}">{{ row.us_change_fmt }}</b> <span class="bridge-label">{{ row.us_label }}</span></span>
      <span class="bridge-leg">한 <b class="{{ row.kr_cls }}">{{ row.kr_change_fmt }}</b> <span class="bridge-label">{{ row.kr_label }}</span></span>
      <span class="bridge-gap {{ row.gap_cls }}">{{ row.gap_word }} {{ row.gap_fmt }}</span>
    </div>
    {% endfor %}
  </div>
  <p class="bridge-note">선반영은 한국이 미국 평균보다 이미 더 크게 움직였다는 뜻, 미반영은 아직 못 따라갔다는 뜻입니다. %p는 두 시장 평균 등락률의 차이일 뿐 오늘 방향을 보장하지 않습니다. 조선은 대응 미국 지표가 없어 제외했습니다.</p>
</div>
{% endif %}
```

- [ ] **Step 2: `kospi.html`에 include 추가**

`scripts/templates/briefings/kospi.html:39`:

```jinja
            {% if us_issues %}{% include "sections/_us_issues.html" %}{% endif %}
            {% if todays_view %}{% include "sections/prediction_strip.html" %}{% else %}{% include "sections/prediction.html" %}{% endif %}
```

→

```jinja
            {% if us_issues %}{% include "sections/_us_issues.html" %}{% endif %}
            {% include "sections/_overnight_bridge.html" %}
            {% if todays_view %}{% include "sections/prediction_strip.html" %}{% else %}{% include "sections/prediction.html" %}{% endif %}
```

(가드는 템플릿 내부의 `{% if overnight_bridge %}`가 이미 처리하므로 include 자체엔 조건 불필요 — `_us_issues.html`과 달리 이 섹션은 컨텍스트 변수가 항상 존재(빈 리스트 가능)하기 때문.)

- [ ] **Step 3: CSS 추가**

`web/assets/style.css`의 `.guru-quote__hr{...}` 줄(Task 4에서 추가, 268번째 줄 부근) 바로 다음에 추가:

```css
.bridge-sub{font-size:13px;color:var(--muted);margin:0 0 12px;line-height:1.5;}
.bridge-list{display:grid;gap:0;}
.bridge-row{display:grid;grid-template-columns:76px 1fr 1fr 96px;align-items:center;gap:8px;padding:10px 0;border-bottom:1px solid var(--hairline);font-size:13px;}
.bridge-row:last-child{border-bottom:0;}
.bridge-sector{font-weight:500;color:var(--ink);}
.bridge-leg{color:var(--muted);}
.bridge-leg b{font-weight:500;}
.bridge-leg b.up{color:var(--up);}
.bridge-leg b.dn{color:var(--dn);}
.bridge-label{opacity:.7;}
.bridge-gap{text-align:right;font-weight:500;font-variant-numeric:tabular-nums;color:var(--ink);}
.bridge-gap.up{color:var(--up);}
.bridge-gap.dn{color:var(--dn);}
.bridge-note{font-size:13px;color:var(--muted);margin-top:12px;line-height:1.55;}
```

- [ ] **Step 4: 로컬 렌더로 확인 (데이터 있는 경우·없는 경우 둘 다)**

```bash
python3 scripts/generate_html.py --type kospi --date 2026-07-31 --data-file data/latest_kospi.json --force
```

Run: `grep -c "밤사이 미국" web/briefings/2026-07-31/kospi/index.html`
Expected: `data/latest_kospi.json`에 `overnight_bridge`가 없으면 `0`(정상 — 섹션 생략 확인). 있으면 `1`.

수동으로 `overnight_bridge` 필드가 있는 상태를 만들어 렌더 확인(선택, 데이터 없을 때만):

```bash
python3 -c "
import json
d = json.load(open('data/latest_kospi.json'))
d['overnight_bridge'] = [
    {'sector':'반도체','us_label':'반도체 ETF','us_change':8.5,'kr_label':'삼성전자·SK하이닉스','kr_change':28.38,'gap_pp':19.9},
    {'sector':'바이오','us_label':'바이오 ETF','us_change':2.4,'kr_label':'삼성바이오로직스·셀트리온','kr_change':-2.25,'gap_pp':-4.6},
]
json.dump(d, open('/tmp/latest_kospi_bridge_test.json','w'), ensure_ascii=False)
"
python3 scripts/generate_html.py --type kospi --date 2026-07-31 --data-file /tmp/latest_kospi_bridge_test.json --force
```

Run: `grep -c "선반영\|미반영" web/briefings/2026-07-31/kospi/index.html`
Expected: `2` (반도체=선반영, 바이오=미반영 두 행 모두 렌더됨을 확인)

이 스텝에서 생성된 `web/briefings/2026-07-31/...` 변경분은 `git checkout -- web/briefings/2026-07-31/`로 되돌린다(§12·§18 — 검증용 재생성 산출물을 라이브 브리핑에 커밋하지 않는다).

- [ ] **Step 5: 브라우저로 다크모드·모바일 확인**

`mcp__Claude_Browser__preview_start`로 `web/briefings/2026-07-31/kospi/index.html`을 로컬에서 열어(정적 파일이므로 `file://` 경로 또는 간단한 정적 서버) 라이트/다크·데스크톱/모바일(≤600px)에서 밤사이 브리지 섹션과 위로 카드가 깨지지 않는지 확인한다. `bridge-row`의 4열 그리드가 600px에서 텍스트가 겹치면 `@media(max-width:600px)` 블록(`web/assets/style.css:812` 부근)에 `.bridge-row{grid-template-columns:1fr 74px;}` 같은 보정을 추가한다(실제로 깨질 때만 — 없으면 이 보정은 생략).

- [ ] **Step 6: 커밋**

```bash
git add scripts/templates/sections/_overnight_bridge.html scripts/templates/briefings/kospi.html web/assets/style.css
git commit -m "feat(밤사이브리지): 신규 섹션 템플릿 추가 및 코스피 브리핑에 배선"
```

---

## 마무리 확인

- [ ] **전체 테스트 스위트 실행**

Run: `python3 -m pytest scripts/ -q`
Expected: 기존 테스트 전부 통과 + 이번에 추가한 4개 테스트 파일(quote_today, pick_quote, load_quote_today, overnight_bridge, build_overnight_bridge — 총 5개 신규 파일) 통과. FAIL 있으면 해당 Task로 돌아가 수정.

- [ ] **`git status`로 라이브 브리핑 파일 오염 여부 확인**

Run: `git status --short`
Expected: `scripts/`·`web/assets/style.css`·`docs/` 변경만 있고 `web/briefings/2026-07-31/` 등 검증용으로 재생성했던 라이브 파일은 없어야 한다(Task 4·8의 Step 4에서 `git checkout --`로 되돌렸는지 재확인).
