# 외국계 IB 코멘트 섹션 (코스피 오전 브리핑) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 오전 브리핑에 외국계 증권사·글로벌 IB의 한국 시장·대형주 코멘트를 무할루시네이션·원본링크 조건으로 표시하는 "🏦 외국계 시각" 섹션을 추가한다.

**Architecture:** 신규 스크립트 `fetch_ib_korea_views.py`가 Google News 한국어 RSS에서 화이트리스트 IB × 코스피/대형주 쿼리로 최근 24시간 기사를 실수집하고(실날짜·실출처), batchexecute로 발행사 원문 URL을 리졸브한 뒤, Gemini로 스탠스 요약·감성분류만 수행해 `data/ib_korea_views.json`을 만든다. `generate_html.py`가 이 데이터를 읽어 코스피 브리핑에만 다이제스트 카드로 렌더한다. 빈 날은 섹션 생략.

**Tech Stack:** Python 3.12, urllib(RSS·batchexecute), google-genai(Gemini 2.5 Flash Lite), Jinja2 템플릿, pytest, GitHub Actions.

**설계 문서:** `docs/superpowers/specs/2026-07-08-ib-korea-views-design.md`

---

## File Structure

- **Create** `scripts/fetch_ib_korea_views.py` — 수집·리졸브·요약·JSON 저장 (신규 진입점). 순수 헬퍼(하우스 매칭·24h 필터·time_label·감성정규화·중복제거) + I/O 함수 분리.
- **Create** `tests/test_ib_korea_views.py` — 순수 헬퍼 단위 테스트.
- **Create** `scripts/templates/sections/ib_korea_views.html` — `analyst_quotes.html` 클론(필드·타이틀 교체).
- **Modify** `scripts/generate_html.py` — `build_ib_korea_views()` 빌더 추가 + kospi 렌더 블록에서 ctx 병합.
- **Modify** `scripts/templates/briefings/kospi.html` — reasons 뒤·watchpoints 앞에 섹션 include.
- **Modify** `scripts/config/kospi.json` — `sections_main`에 `"ib_korea_views"` 추가(문서 일관성용).
- **Modify** `.github/workflows/daily_report.yml` — `kospi-briefing` job에 수집 스텝 추가.
- **Modify** `docs/SERVICE_RULES.md` — 신규 스크립트·섹션 운영 규칙 1개 문단 추가.

---

## Task 1: 순수 헬퍼 + 스크립트 스켈레톤 (TDD)

**Files:**
- Create: `scripts/fetch_ib_korea_views.py`
- Test: `tests/test_ib_korea_views.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_ib_korea_views.py`:

```python
# 외국계 IB 코멘트 수집기의 순수 헬퍼(하우스 매칭·24h 필터·라벨·감성·중복제거) 단위 테스트
import sys, os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from fetch_ib_korea_views import (
    _match_house, _within_24h, _time_label, _normalize_sentiment, _dedup_by_house, KST,
)

def test_match_house_basic():
    h = _match_house("모건스탠리 삼성·SK하이닉스 비중 축소 권고")
    assert h is not None and h["name"] == "모건스탠리" and h["initials"] == "MS"

def test_match_house_alias():
    assert _match_house("JP모간, 코스피 목표 상향")["initials"] == "JPM"
    assert _match_house("골드만, 삼성전자 슈퍼사이클")["name"] == "골드만삭스"

def test_match_house_acronym_case_insensitive():
    assert _match_house("ubs, 한국 증시 비중확대")["initials"] == "UBS"

def test_match_house_none():
    assert _match_house("삼성전자 3분기 실적 발표") is None
    assert _match_house("국내 증권사 코스피 전망") is None

def test_within_24h():
    now = datetime(2026, 7, 8, 7, 20, tzinfo=KST)
    assert _within_24h(datetime(2026, 7, 8, 6, 0, tzinfo=KST), now) is True
    assert _within_24h(datetime(2026, 7, 7, 9, 51, tzinfo=KST), now) is True   # 21.5h 전
    assert _within_24h(datetime(2026, 7, 7, 6, 0, tzinfo=KST), now) is False   # 25.3h 전
    assert _within_24h(datetime(2026, 7, 9, 0, 0, tzinfo=KST), now) is False   # 미래

def test_time_label():
    now = datetime(2026, 7, 8, 7, 20, tzinfo=KST)
    assert _time_label(datetime(2026, 7, 8, 6, 0, tzinfo=KST), now) == "오늘 06:00"
    assert _time_label(datetime(2026, 7, 7, 9, 51, tzinfo=KST), now) == "어제 09:51"

def test_normalize_sentiment():
    assert _normalize_sentiment("bullish") == "bull"
    assert _normalize_sentiment("BEAR") == "bear"
    assert _normalize_sentiment("neutral") == "neu"
    assert _normalize_sentiment("긍정") == "neu"   # 알 수 없는 값 → neu

def test_dedup_by_house_keeps_latest_max3():
    now = datetime(2026, 7, 8, 7, 20, tzinfo=KST)
    def cand(name, h, m):
        return {"house": name, "initials": "XX",
                "published_at": datetime(2026, 7, 8, h, m, tzinfo=KST)}
    cands = [
        cand("모건스탠리", 6, 0),
        cand("모건스탠리", 9, 51),   # 같은 하우스 더 최근 → 이게 남아야
        cand("JP모건", 5, 0),
        cand("골드만삭스", 4, 0),
        cand("UBS", 3, 0),           # 4번째 하우스 → 최대 3건 컷
    ]
    out = _dedup_by_house(cands, max_items=3)
    assert len(out) == 3
    ms = [c for c in out if c["house"] == "모건스탠리"]
    assert len(ms) == 1 and ms[0]["published_at"].hour == 9
    # 최신순 정렬
    assert [c["published_at"] for c in out] == sorted(
        [c["published_at"] for c in out], reverse=True)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_ib_korea_views.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_ib_korea_views'`

- [ ] **Step 3: 스크립트 스켈레톤 + 순수 헬퍼 구현**

`scripts/fetch_ib_korea_views.py`:

```python
#!/usr/bin/env python3
# 외국계 증권사·글로벌 IB의 한국 시장·대형주 코멘트를 Google News RSS로 수집·요약하는 스크립트
"""
Usage:
    python3 scripts/fetch_ib_korea_views.py

출력: data/ib_korea_views.json
  - Google News 한국어 RSS에서 화이트리스트 IB × 코스피/대형주 쿼리로 최근 24시간 기사만 수집
  - 제목/요약에 화이트리스트 IB명이 실제로 박혀 있어야 채택 (귀속 불가하면 버림)
  - IB당 1건, 최대 3건 (동일 IB는 가장 최근 1건)
  - batchexecute로 발행사 원문 URL 리졸브 → 실패 시 Google News 링크 폴백
  - Gemini는 제목+요약 기반 스탠스 요약(해요체)·bull/bear/neu 분류만 수행 (날짜·URL·출처 생성 불가)
  - 대상 없으면 빈 배열 저장 (섹션 생략, 파이프라인 보호)
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
KST = timezone(timedelta(hours=9))

MAX_ITEMS = 3

# 화이트리스트 IB — aliases 중 하나라도 제목/요약에 있으면 채택. 리스트 순서대로 first-match.
HOUSES = [
    {"name": "골드만삭스",   "initials": "GS",   "aliases": ["골드만삭스", "골드만"]},
    {"name": "모건스탠리",   "initials": "MS",   "aliases": ["모건스탠리", "모간스탠리"]},
    {"name": "JP모건",      "initials": "JPM",  "aliases": ["jp모건", "jp모간", "제이피모건", "jp 모건"]},
    {"name": "UBS",         "initials": "UBS",  "aliases": ["ubs"]},
    {"name": "씨티",         "initials": "Citi", "aliases": ["씨티그룹", "씨티"]},
    {"name": "노무라",       "initials": "NOM",  "aliases": ["노무라"]},
    {"name": "맥쿼리",       "initials": "MQ",   "aliases": ["맥쿼리"]},
    {"name": "HSBC",        "initials": "HSBC", "aliases": ["hsbc"]},
    {"name": "CLSA",        "initials": "CLSA", "aliases": ["clsa"]},
    {"name": "번스타인",     "initials": "BST",  "aliases": ["번스타인"]},
    {"name": "BofA",        "initials": "BofA", "aliases": ["뱅크오브아메리카", "bofa", "메릴린치"]},
    {"name": "바클레이스",   "initials": "BARC", "aliases": ["바클레이스", "바클레이즈"]},
]

VALID_SENTIMENTS = {"bull", "bear", "neu"}
_SENT_MAP = {"bullish": "bull", "bearish": "bear", "neutral": "neu"}


def _match_house(text: str) -> dict | None:
    """제목/요약 text에 화이트리스트 IB alias가 있으면 해당 하우스 dict 반환, 없으면 None."""
    low = text.lower()
    for h in HOUSES:
        if any(a in low for a in h["aliases"]):
            return h
    return None


def _within_24h(dt: datetime, now: datetime) -> bool:
    """dt가 now 기준 최근 24시간 이내(과거 방향)이고 미래가 아니면 True."""
    if dt > now:
        return False
    return (now - dt) <= timedelta(hours=24)


def _time_label(dt: datetime, now: datetime) -> str:
    """오늘(KST)이면 '오늘 HH:MM', 어제면 '어제 HH:MM', 그 밖이면 'M/D HH:MM'."""
    d0 = now.astimezone(KST).date()
    d = dt.astimezone(KST).date()
    hm = dt.astimezone(KST).strftime("%H:%M")
    if d == d0:
        return f"오늘 {hm}"
    if (d0 - d).days == 1:
        return f"어제 {hm}"
    return f"{d.month}/{d.day} {hm}"


def _normalize_sentiment(s: str) -> str:
    low = str(s).strip().lower()
    if low in _SENT_MAP:
        return _SENT_MAP[low]
    return low if low in VALID_SENTIMENTS else "neu"


def _dedup_by_house(cands: list[dict], max_items: int = MAX_ITEMS) -> list[dict]:
    """동일 하우스는 published_at 최신 1건만 유지, 최신순 정렬 후 max_items건 반환."""
    seen: dict[str, dict] = {}
    for c in cands:
        name = c["house"]
        if name not in seen or c["published_at"] > seen[name]["published_at"]:
            seen[name] = c
    ordered = sorted(seen.values(), key=lambda c: c["published_at"], reverse=True)
    return ordered[:max_items]


if __name__ == "__main__":
    from fetch_ib_korea_views import main  # noqa
    main()
```

(참고: 마지막 `if __name__` 블록의 `main`은 Task 4에서 정의한다. Task 1~3 동안에는 스크립트를 직접 실행하지 않고 pytest로만 검증하므로 문제 없다. Task 4에서 `main()`을 추가한 뒤 정상 실행된다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_ib_korea_views.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/fetch_ib_korea_views.py tests/test_ib_korea_views.py
git commit -m "feat(외국계 시각): IB 코멘트 수집기 순수 헬퍼 + 단위 테스트"
```

---

## Task 2: RSS 24시간 수집 (쿼리 세트 + 후보 추출)

**Files:**
- Modify: `scripts/fetch_ib_korea_views.py`

기존 `fetch_news_live._fetch_rss`는 `pub_date == today` 정확일치라 24시간 창(어제 포함)에 못 쓴다. 전용 페처를 이 스크립트에 둔다.

- [ ] **Step 1: 쿼리 세트 + RSS 후보 수집 함수 추가**

`scripts/fetch_ib_korea_views.py`의 순수 헬퍼 아래, `if __name__` 블록 위에 추가:

```python
_GN_KR = "https://news.google.com/rss/search?hl=ko&gl=KR&ceid=KR:ko&q="
_HDR = {"User-Agent": "Mozilla/5.0"}

# 화이트리스트 IB × 한국 시장·대형주 조합 쿼리. 커버리지 확보용으로 넉넉히.
_QUERIES = [
    "외국계 증권사 코스피",
    "골드만삭스 삼성전자", "골드만삭스 코스피",
    "모건스탠리 SK하이닉스", "모건스탠리 코스피",
    "JP모건 코스피", "JP모건 한국 증시",
    "UBS 코스피", "노무라 한국 증시", "씨티 코스피",
    "맥쿼리 삼성전자", "HSBC 한국 증시", "CLSA 코스피",
]


def _clean_title(title: str) -> str:
    """Google News RSS 제목 끝 '- 출처명' 제거."""
    title = re.sub(r"\s*-\s*[^-]{1,30}$", "", title.strip())
    return re.sub(r"\s{2,}", " ", title).strip()


def _fetch_rss_candidates(now: datetime) -> list[dict]:
    """쿼리 세트로 RSS를 돌며 24h 이내·IB 귀속 가능한 후보를 수집한다.

    각 후보: {house, initials, title, desc, source, link, published_at(datetime)}
    """
    seen_titles: set[str] = set()
    cands: list[dict] = []
    for q in _QUERIES:
        url = _GN_KR + urllib.parse.quote(q)
        try:
            req = urllib.request.Request(url, headers=_HDR)
            with urllib.request.urlopen(req, timeout=12) as r:
                root = ET.fromstring(r.read())
        except Exception as e:
            print(f"[ib_views] RSS 실패 ({q}): {e}", file=sys.stderr)
            continue
        for item in root.iter("item"):
            title = _clean_title((item.findtext("title") or "").strip())
            desc = re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip()[:200]
            link = (item.findtext("link") or "").strip()
            src_el = item.find("source")
            source = (src_el.text or "").strip() if src_el is not None else ""
            try:
                pub = parsedate_to_datetime((item.findtext("pubDate") or "")).astimezone(KST)
            except Exception:
                continue
            if not title or title in seen_titles:
                continue
            if not _within_24h(pub, now):
                continue
            house = _match_house(title + " " + desc)
            if house is None:
                continue
            seen_titles.add(title)
            cands.append({
                "house": house["name"], "initials": house["initials"],
                "title": title, "desc": desc, "source": source,
                "link": link, "published_at": pub,
            })
    return cands
```

- [ ] **Step 2: 수동 검증 — 오늘 실제 후보가 잡히는지 확인**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 -c "
import sys; sys.path.insert(0, 'scripts')
from datetime import datetime
from fetch_ib_korea_views import _fetch_rss_candidates, KST
c = _fetch_rss_candidates(datetime.now(KST))
print('후보', len(c), '건')
for x in c[:6]:
    print(' ', x['initials'], x['published_at'].strftime('%m-%d %H:%M'), x['source'], '|', x['title'][:50])
"
```
Expected: 후보 1건 이상 출력, 각 항목이 화이트리스트 이니셜·24h 이내 시각을 가짐. (0건이면 그날 외국계 보도가 없는 정상 상황일 수 있으니, `모건스탠리 SK하이닉스` 등 최근 활발한 주제를 `_QUERIES`에서 확인.)

- [ ] **Step 3: 커밋**

```bash
git add scripts/fetch_ib_korea_views.py
git commit -m "feat(외국계 시각): RSS 24시간 후보 수집 (쿼리 세트 + IB 귀속 필터)"
```

---

## Task 3: Google News 원문 URL 리졸브 (batchexecute + 폴백)

**Files:**
- Modify: `scripts/fetch_ib_korea_views.py`

Google News RSS 링크(`news.google.com/rss/articles/CBMi...`)는 batchexecute로 발행사 원문 URL을 얻는다. 실패 시 원래 Google News 링크를 그대로 쓴다(그래도 브라우저에서 실기사로 리다이렉트됨).

- [ ] **Step 1: 리졸버 함수 추가**

`scripts/fetch_ib_korea_views.py`의 `_fetch_rss_candidates` 아래에 추가:

```python
_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"


def _resolve_gnews_url(link: str) -> str:
    """Google News 기사 링크를 발행사 원문 URL로 리졸브한다. 실패 시 원래 link 반환."""
    if "/rss/articles/" not in link:
        return link
    try:
        art = link.split("/articles/")[1].split("?")[0]
        req = urllib.request.Request(link, headers=_HDR)
        with urllib.request.urlopen(req, timeout=12) as r:
            page = r.read().decode("utf-8", "ignore")
        sig = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sig and ts):
            return link
        inner = (
            '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
            'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
            f'"{art}",{ts.group(1)},"{sig.group(1)}"]'
        )
        payload = [[["Fbv4je", inner, None, "generic"]]]
        body = "f.req=" + urllib.parse.quote(json.dumps(payload))
        req2 = urllib.request.Request(
            _BATCH_URL, data=body.encode(),
            headers={**_HDR, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        with urllib.request.urlopen(req2, timeout=12) as r:
            raw = r.read().decode("utf-8", "ignore")
        seg = raw.split("garturlres")[1] if "garturlres" in raw else raw
        m = re.search(r'(https?://[^\\"]+)', seg)
        return m.group(1) if m else link
    except (urllib.error.URLError, TimeoutError, OSError, IndexError):
        return link
```

- [ ] **Step 2: 수동 검증 — 실제 리졸브 확인**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 -c "
import sys; sys.path.insert(0, 'scripts')
from datetime import datetime
from fetch_ib_korea_views import _fetch_rss_candidates, _resolve_gnews_url, KST
c = _fetch_rss_candidates(datetime.now(KST))
if not c:
    print('후보 0건 — 다른 날 재시도'); raise SystemExit
u = _resolve_gnews_url(c[0]['link'])
print('resolved:', u[:110])
print('발행사 도메인 리졸브 성공' if 'news.google.com' not in u else '폴백(google news 링크)')
"
```
Expected: `resolved: https://www.<발행사>.com/...` 형태(발행사 도메인). 리졸브 실패 시 폴백 메시지가 떠도 정상(링크는 여전히 동작).

- [ ] **Step 3: 커밋**

```bash
git add scripts/fetch_ib_korea_views.py
git commit -m "feat(외국계 시각): Google News 링크 → 발행사 원문 URL 리졸브 (batchexecute + 폴백)"
```

---

## Task 4: Gemini 요약·분류 + build_views + main

**Files:**
- Modify: `scripts/fetch_ib_korea_views.py`

- [ ] **Step 1: 요약·분류 + 오케스트레이션 + main 추가**

`scripts/fetch_ib_korea_views.py`의 `_resolve_gnews_url` 아래, `if __name__` 블록 위에 추가. `get_gemini_api_key`는 기존 `fetch_news_live`에서 재사용:

```python
sys.path.insert(0, str(BASE_DIR / "scripts"))
from fetch_news_live import get_gemini_api_key  # noqa: E402


_SUMMARY_PROMPT = """다음은 외국계 증권사(글로벌 IB)의 한국 시장·종목 관련 견해를 다룬 국내 기사입니다.
이 IB가 어떤 스탠스를 밝혔는지 1~2문장 한국어로 요약하고, 감성을 분류하세요.

규칙:
- 반드시 해요체(예: ~했어요, ~봤어요)로 끝내세요. '~다', '~습니다'체 금지.
- 제목·요약에 없는 내용을 생성하지 마세요. 목표가·지수 레벨 등 숫자는 제목·요약에 실제로
  있으면 그대로 써도 되지만, 없으면 절대 만들지 마세요.
- sentiment: 상승/비중확대/매수 견해면 "bull", 하락/비중축소/매도 견해면 "bear", 중립·혼조면 "neu".

[제목] {title}
[요약] {desc}

출력(JSON만, 다른 텍스트 없이):
{{"summary": "...", "sentiment": "bull"}}"""


def _summarize_and_classify(title: str, desc: str) -> dict | None:
    """제목+요약으로 스탠스 요약문·감성을 생성한다. 실패 시 None."""
    from google import genai
    from google.genai import types
    try:
        client = genai.Client(api_key=get_gemini_api_key())
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=_SUMMARY_PROMPT.format(title=title, desc=desc),
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=300),
        )
        raw = (resp.text or "").strip()
    except Exception as e:
        print(f"[ib_views] Gemini 요약 실패: {e}", file=sys.stderr)
        return None
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    summary = str(obj.get("summary", "")).strip()
    if not summary:
        return None
    return {"summary": summary, "sentiment": _normalize_sentiment(obj.get("sentiment", "neu"))}


def build_views(now: datetime) -> list[dict]:
    cands = _dedup_by_house(_fetch_rss_candidates(now))
    views: list[dict] = []
    for c in cands:
        sc = _summarize_and_classify(c["title"], c["desc"])
        if not sc:
            print(f"[ib_views] SKIP(요약 실패): {c['title'][:40]}", file=sys.stderr)
            continue
        views.append({
            "house": c["house"],
            "initials": c["initials"],
            "summary": sc["summary"],
            "source": c["source"],
            "url": _resolve_gnews_url(c["link"]),
            "published_at": c["published_at"].isoformat(),
            "time_label": _time_label(c["published_at"], now),
            "sentiment": sc["sentiment"],
        })
    return views


def main() -> None:
    now = datetime.now(KST)
    out_path = DATA_DIR / "ib_korea_views.json"
    try:
        views = build_views(now)
    except Exception as e:
        print(f"[ib_views] ERROR: {e}", file=sys.stderr)
        views = []
    payload = {"generated_at": now.isoformat(), "date": now.strftime("%Y-%m-%d"), "views": views}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ib_views] {len(views)}건 저장 → {out_path}")
```

그리고 파일 맨 아래 `if __name__` 블록을 아래로 교체(Task 1의 임시 import 제거):

```python
if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 단위 테스트 회귀 확인**

Run: `python3 -m pytest tests/test_ib_korea_views.py -v`
Expected: PASS (8 passed) — 순수 헬퍼는 그대로.

- [ ] **Step 3: 엔드투엔드 수동 실행 (GEMINI_API_KEY 필요)**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 scripts/fetch_ib_korea_views.py && python3 -m json.tool data/ib_korea_views.json
```
Expected: `data/ib_korea_views.json` 생성. `views` 각 항목이 `house·initials·summary(해요체)·source·url·published_at(24h 이내)·time_label·sentiment(bull/bear/neu)`를 가짐. 대상 없으면 `"views": []`. 각 `url`을 브라우저로 열어 실기사로 이동하는지 1건 확인.

- [ ] **Step 4: 커밋**

```bash
git add scripts/fetch_ib_korea_views.py
git commit -m "feat(외국계 시각): Gemini 스탠스 요약·감성분류 + build_views + main"
```

---

## Task 5: HTML 렌더링 (빌더 + 템플릿 + kospi 배선)

**Files:**
- Create: `scripts/templates/sections/ib_korea_views.html`
- Modify: `scripts/generate_html.py` (build_analyst_quotes 근처 + kospi ctx 블록)
- Modify: `scripts/templates/briefings/kospi.html`
- Modify: `scripts/config/kospi.json`

- [ ] **Step 1: 섹션 템플릿 생성**

`scripts/templates/sections/ib_korea_views.html`:

```html
{# 외국계 IB 코멘트 다이제스트 카드 — ib_korea_views 리스트가 비면 전체 생략 #}
{% if ib_korea_views %}
<div class="open-section analyst-quotes-section">
  <div class="open-section__title" style="display:flex;align-items:center;gap:6px;">
    <span>🏦 외국계 시각</span>
    <span style="font-size:11px;font-weight:400;color:var(--muted);margin-left:auto;text-transform:none;letter-spacing:0;">최근 24시간</span>
  </div>
  {% for v in ib_korea_views %}
  <div class="analyst-card">
    <div class="analyst-card__top">
      <div class="analyst-avatar">{{ v.initials }}</div>
      <div class="analyst-meta">
        <div class="analyst-name">{{ v.house }}</div>
        <div class="analyst-affil">글로벌 IB</div>
      </div>
      <span class="analyst-badge {{ v.sentiment }}">{% if v.sentiment == 'bull' %}강세{% elif v.sentiment == 'bear' %}약세{% else %}중립{% endif %}</span>
    </div>
    <div class="analyst-quote">{{ v.summary }}</div>
    <div class="analyst-footer">
      <a class="analyst-source" href="{{ v.url }}" target="_blank" rel="noopener noreferrer">{{ v.source }} <span class="analyst-source-arrow">→</span></a>
      <span class="analyst-time">{{ v.time_label }}</span>
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 2: 빌더 추가**

`scripts/generate_html.py`의 `build_analyst_quotes` 함수(현재 567행) 바로 아래에 추가:

```python
def build_ib_korea_views() -> dict:
    """외국계 IB 코멘트 섹션 컨텍스트 빌더 (코스피 전용).

    url이 없는 항목은 표시하지 않는다(원본 링크 이동 보장). 데이터 없으면 빈 리스트 →
    템플릿에서 섹션 자체 생략.
    """
    views_path = BASE_DIR / "data" / "ib_korea_views.json"
    if not views_path.exists():
        return {"ib_korea_views": []}
    with open(views_path, encoding="utf-8") as f:
        payload = json.load(f)
    views = [v for v in payload.get("views", []) if v.get("url")]
    return {"ib_korea_views": views}
```

- [ ] **Step 3: kospi 렌더 블록에서 ctx 병합**

`scripts/generate_html.py`의 `if internal_type == "kospi":` 블록(현재 763행 근처) 안, `uls = analysis.get("us_linked_story")` 줄 **앞**에 한 줄 추가:

```python
        if internal_type == "kospi":
            ctx.update(build_ib_korea_views())
            uls = analysis.get("us_linked_story") or {}
```

- [ ] **Step 4: kospi.html에 include 삽입**

`scripts/templates/briefings/kospi.html`의 reasons 블록 뒤 `<div class="divider"></div>`(현재 34행) 다음 줄에 삽입:

```html
            <div class="divider"></div>
            {% if ib_korea_views %}{% include "sections/ib_korea_views.html" %}<div class="divider"></div>{% endif %}
```

- [ ] **Step 5: kospi.json sections_main 문서 갱신**

`scripts/config/kospi.json` 9행을 아래로 교체(문서 일관성용, 코드가 읽지는 않음):

```json
  "sections_main": ["prediction", "reasons", "ib_korea_views", "watchpoints", "stock_picks"],
```

- [ ] **Step 6: 수동 렌더 검증**

먼저 데이터가 없으면 섹션이 생략되는지, 있으면 렌더되는지 둘 다 확인한다.

데이터 있는 상태로 오늘 코스피 브리핑 재생성:
```bash
cd "/Users/luke/Service App/double-shot" && python3 scripts/fetch_ib_korea_views.py && python3 scripts/generate_html.py --type kospi --date $(TZ=Asia/Seoul date +%F) --data-file data/latest_kospi.json && grep -c "외국계 시각" web/briefings/$(TZ=Asia/Seoul date +%F)/kospi/index.html
```
Expected: 데이터가 1건 이상이면 `1`(섹션 렌더), `views: []`면 `0`(생략). reasons 뒤·watchpoints 앞 위치인지 눈으로 확인.

> ⚠️ SERVICE_RULES 2번: `--data-file`이 필요하고, 해당 날짜 `analysis_snapshot.json`이 있으면 그게 우선된다. 실행 후 `git status`로 오늘 브리핑 HTML 외에 예상치 못한 변경이 없는지 확인하고, 검증용으로 재생성한 HTML은 커밋하지 않는다(실제 발행은 워크플로우가 담당).

- [ ] **Step 7: 커밋 (검증용 재생성 HTML 제외)**

```bash
git add scripts/templates/sections/ib_korea_views.html scripts/generate_html.py scripts/templates/briefings/kospi.html scripts/config/kospi.json
git commit -m "feat(외국계 시각): 코스피 브리핑 렌더링 (빌더·템플릿·배선)"
```

---

## Task 6: GitHub Actions 배선 + 운영 규칙 문서

**Files:**
- Modify: `.github/workflows/daily_report.yml`
- Modify: `docs/SERVICE_RULES.md`

- [ ] **Step 1: kospi-briefing job에 수집 스텝 추가**

`.github/workflows/daily_report.yml`의 `kospi-briefing` job에서 "📰 뉴스 요약" 스텝(현재 90~93행) **뒤**, "✨ Claude 분석 생성" 스텝(현재 95행) **앞**에 삽입. `GEMINI_API_KEY` env는 뉴스 요약 스텝과 동일하게 설정:

```yaml
      - name: 🏦 외국계 IB 코멘트 수집 (Gemini, 실패해도 발행 계속)
        continue-on-error: true
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python3 scripts/fetch_ib_korea_views.py
```

> 이 데이터는 `call_claude` 분석 입력이 아니라 `generate_html`이 직접 소비하므로 validate_analysis 파이프라인 순서에 영향이 없다. `--render` 시점에 파일만 있으면 된다.
>
> **커밋·gitignore는 추가 작업 불필요(확인 완료):** `data/ib_korea_views.json`은 `.gitignore`의 어떤 패턴(`data/latest_*`, `data/analysis_*` 등)에도 안 걸려 기본 추적된다. `data/analyst_quotes.json`도 동일하게 git 추적 중이다. kospi-briefing 커밋 스텝이 이미 `git add web/ data/`라 자동 포함되므로 workflow·gitignore 변경이 없다.

- [ ] **Step 2: SERVICE_RULES.md에 운영 규칙 추가**

`docs/SERVICE_RULES.md`의 "월가 애널리스트 발언 수집 — `fetch_analyst_quotes.py`" 문단 아래에 추가:

```markdown
### 외국계 IB 코멘트 수집 — `fetch_ib_korea_views.py`

- Google News 한국어 RSS로 화이트리스트 IB(골드만·모건스탠리·JP모건·UBS·씨티·노무라·맥쿼리·HSBC·CLSA·번스타인·BofA·바클레이스) × 코스피/대형주 쿼리로 **최근 24시간** 국내 2차 보도를 실수집.
- 제목/요약에 화이트리스트 IB명이 실제로 있어야 채택(귀속 불가 시 제외). IB당 1건, 최대 3건.
- 원문 링크: Google News 링크를 batchexecute로 발행사 원문 URL로 리졸브, 실패 시 Google News 링크 폴백(둘 다 실기사 연결).
- Gemini는 **요약·분류만** — 날짜·URL·출처는 RSS 실데이터라 생성 불가. 목표가·지수 숫자는 제목·요약에 있으면 허용, 없으면 생성 금지. 해요체 고정.
- **다이제스트 방식**: 원문 발언 전문을 갖고 있지 않으므로 큰따옴표 버바텀 인용을 하지 않고 스탠스 요약 + 원문 링크로 제시.
- 출력: `data/ib_korea_views.json`. 대상 없으면 `views: []` → 섹션 생략(파이프라인 보호).
- 표시: 코스피 오전 브리핑 "🏦 외국계 시각" 섹션(reasons 뒤·stock_picks 앞). `generate_html.build_ib_korea_views()`가 url 없는 항목 제외.
- kospi-briefing job에서 `fetch_news.py` 직후, `call_claude.py` 직전 실행. `continue-on-error: true`.
```

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/daily_report.yml docs/SERVICE_RULES.md
git commit -m "feat(외국계 시각): kospi-briefing 잡 수집 스텝 + 운영 규칙 문서"
```

---

## Task 7: 최종 검증

- [ ] **Step 1: 전체 테스트**

Run: `python3 -m pytest tests/ -v`
Expected: 기존 테스트 + `test_ib_korea_views.py` 8건 모두 PASS.

- [ ] **Step 2: 엔드투엔드 재확인**

Run:
```bash
cd "/Users/luke/Service App/double-shot" && python3 scripts/fetch_ib_korea_views.py && python3 -m json.tool data/ib_korea_views.json | head -30
```
Expected: 정상 산출(또는 빈 배열). `url` 1건을 브라우저로 열어 실기사 이동 확인.

- [ ] **Step 3: 최종 상태 확인 (검증용 HTML 미커밋)**

Run: `git status`
Expected: 커밋되지 않은 것은 검증 과정에서 재생성된 오늘자 브리핑 HTML·`data/*.json` 산출물뿐. 실제 발행은 워크플로우가 담당하므로 이들은 커밋하지 않는다.

---

## 자기 점검 결과 (작성자 확인)

- **스펙 커버리지:** 소스(RSS)·24h·귀속필터·리졸브·다이제스트·화이트리스트·표시·배선·빈날생략·검증기준 → Task 1~7에 각각 매핑됨.
- **플레이스홀더:** 모든 코드 블록에 실제 구현 포함, TBD 없음. Task 1의 임시 `if __name__` import는 Task 4에서 명시적으로 교체.
- **타입 일관성:** `_match_house`(dict|None), `_within_24h`/`_time_label`(datetime, now), `_dedup_by_house`(published_at=datetime), `build_views`가 datetime→isoformat 변환, 템플릿 필드(house·initials·summary·source·url·time_label·sentiment)와 빌더 출력 일치.
- **주의점:** `data/ib_korea_views.json`의 gitignore/커밋 처리(Task 6 Step 2)는 `analyst_quotes.json` 관례를 실제로 확인해 맞출 것.
