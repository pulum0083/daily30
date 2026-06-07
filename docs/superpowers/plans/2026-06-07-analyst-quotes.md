# 월가 코멘트 섹션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미국 브리핑에 월가 애널리스트 12명의 48시간 이내 실발언을 Gemini google_search로 수집해 카드 섹션으로 표시한다.

**Architecture:** 독립 스크립트 `fetch_analyst_quotes.py`가 Gemini + google_search로 발언을 수집해 `data/analyst_quotes.json`으로 저장. `generate_html.py`가 이를 읽어 Jinja2 템플릿 컨텍스트에 주입. GHA us-briefing job에 `continue-on-error: true` step으로 추가해 기존 파이프라인을 보호.

**Tech Stack:** Python 3.12, google-genai (Gemini 2.5 Flash Lite + google_search), Jinja2, GitHub Actions

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `scripts/fetch_analyst_quotes.py` | 신규 — Gemini로 발언 수집·분류·저장 |
| `scripts/templates/sections/analyst_quotes.html` | 신규 — 카드 UI 템플릿 |
| `scripts/config/us.json` | 수정 — `sections_main`에 `analyst_quotes` 추가 |
| `scripts/generate_html.py` | 수정 — `build_analyst_quotes()` 빌더 추가 |
| `.github/workflows/daily_report.yml` | 수정 — us-briefing job에 step 추가 |
| `web/assets/style.css` | **이미 완료** — analyst 카드 CSS 추가됨 |

---

## Task 1: `fetch_analyst_quotes.py` 작성

**Files:**
- Create: `scripts/fetch_analyst_quotes.py`

- [ ] **Step 1: 파일 생성**

```python
#!/usr/bin/env python3
# Gemini google_search로 월가 애널리스트 12명의 최근 발언을 수집·분류하는 스크립트
"""
Usage:
    python3 scripts/fetch_analyst_quotes.py

출력: data/analyst_quotes.json
  - 48시간 이내 실발언만 수집 (없으면 빈 배열)
  - 최대 4명, published_at 기준 최신순 정렬
  - sentiment: bull | bear | neu (Gemini 자동 분류)
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pytz

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")

ANALYSTS = [
    {"name": "Tom Lee",               "affiliation": "Fundstrat",               "initials": "TL"},
    {"name": "Ed Yardeni",            "affiliation": "Yardeni Research",         "initials": "EY"},
    {"name": "Dan Ives",              "affiliation": "Wedbush",                  "initials": "DI"},
    {"name": "Mike Wilson",           "affiliation": "Morgan Stanley",           "initials": "MW"},
    {"name": "Savita Subramanian",    "affiliation": "Bank of America",          "initials": "SS"},
    {"name": "Bill Ackman",           "affiliation": "Pershing Square",          "initials": "BA"},
    {"name": "Stan Druckenmiller",    "affiliation": "Duquesne Family Office",   "initials": "SD"},
    {"name": "Mohamed El-Erian",      "affiliation": "Allianz",                  "initials": "ME"},
    {"name": "Jeff Gundlach",         "affiliation": "DoubleLine Capital",       "initials": "JG"},
    {"name": "Ray Dalio",             "affiliation": "Bridgewater Associates",   "initials": "RD"},
    {"name": "Cathie Wood",           "affiliation": "ARK Invest",               "initials": "CW"},
    {"name": "Michael Burry",         "affiliation": "Scion Asset Management",   "initials": "MB"},
]

MAX_QUOTES = 4


def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        config_file = BASE_DIR / "config.json"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                cfg = json.load(f)
            key = cfg.get("gemini", {}).get("api_key", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return key


def build_prompt(now_kst: datetime) -> str:
    now_str = now_kst.strftime("%Y-%m-%d %H:%M KST")
    cutoff_str = "48시간 이내 (기준: " + now_str + ")"
    analyst_list = "\n".join(
        f'- {a["name"]} ({a["affiliation"]})'
        for a in ANALYSTS
    )
    return f"""\
현재 시각은 {now_str}입니다.

아래 월가 애널리스트·투자자 12명 각각에 대해 Google Search로 최근 발언을 검색해 주세요.
수집 기준: {cutoff_str} 이내에 실제 인터뷰·기사·SNS에서 한 발언만 포함.

대상 인물:
{analyst_list}

각 인물에 대해:
1. 최근 {cutoff_str} 이내 시장 전망 관련 발언이 있는지 검색
2. 있으면: 실제 발언 내용(한국어 번역), 출처, 발언 일시 추출
3. 없으면: 해당 인물을 결과에서 완전히 제외

⚠️ 매우 중요: 검색 결과에 실제로 존재하는 발언만 포함하세요.
발언이 검색되지 않으면 해당 인물을 results 배열에서 제외하세요.
발언 내용을 추측·생성·요약하지 마세요. 검색된 원문 기반 번역만 허용합니다.

sentiment 분류 기준:
- "bull": 시장 상승 전망, 매수 추천, 낙관적 견해
- "bear": 시장 하락 전망, 매도 추천, 비관적 견해
- "neu": 중립, 조건부, 혼조

time_label 형식: 발언이 오늘(KST 기준)이면 "오늘 HH:MM", 어제면 "어제 HH:MM"

출력 형식 (JSON 배열만, 다른 텍스트 없이):
[
  {{
    "name": "인물 이름 (영문, 원래 표기)",
    "affiliation": "소속 기관",
    "initials": "이니셜 2자",
    "quote": "한국어 번역 발언 (원문 기반, 2-4문장)",
    "source": "출처 매체명",
    "published_at": "ISO 8601 datetime (KST, 예: 2026-06-06T23:14:00+09:00)",
    "time_label": "어제 23:14",
    "sentiment": "bull"
  }}
]

발언이 하나도 없으면 빈 배열 [] 를 반환하세요.
"""


def fetch_analyst_quotes() -> list:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    client = genai.Client(api_key=get_gemini_api_key())
    now_kst = datetime.now(KST)
    prompt = build_prompt(now_kst)

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
            max_output_tokens=2048,
        ),
    )

    if not response.text:
        finish = getattr(response.candidates[0], "finish_reason", "UNKNOWN") if response.candidates else "NO_CANDIDATES"
        raise RuntimeError(f"Gemini returned empty response (finish_reason={finish})")

    raw = response.text.strip()

    # JSON 블록 추출 (마크다운 펜스 제거)
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        raw = m.group(0)

    quotes = json.loads(raw)
    if not isinstance(quotes, list):
        return []

    # initials 보정: ANALYSTS 정의 기준으로 덮어쓰기
    initials_map = {a["name"]: a["initials"] for a in ANALYSTS}
    for q in quotes:
        q["initials"] = initials_map.get(q.get("name", ""), q.get("initials", "??"))

    # published_at 기준 최신순 정렬 후 MAX_QUOTES 보존
    def sort_key(q):
        try:
            from datetime import timezone
            import dateutil.parser
            return dateutil.parser.parse(q.get("published_at", "2000-01-01T00:00:00+09:00"))
        except Exception:
            return datetime(2000, 1, 1, tzinfo=KST)

    quotes.sort(key=sort_key, reverse=True)
    return quotes[:MAX_QUOTES]


def main():
    print("[fetch_analyst_quotes] 월가 애널리스트 발언 수집 시작")
    out_path = DATA_DIR / "analyst_quotes.json"

    try:
        quotes = fetch_analyst_quotes()
        print(f"[fetch_analyst_quotes] 수집 완료: {len(quotes)}명")
    except Exception as e:
        print(f"[fetch_analyst_quotes] ERROR: {e}", file=sys.stderr)
        # 실패 시 빈 배열 저장 (섹션 생략)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)
        print(f"[fetch_analyst_quotes] 빈 배열 저장 → {out_path}")
        sys.exit(0)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(quotes, f, ensure_ascii=False, indent=2)
    print(f"[fetch_analyst_quotes] 저장 완료 → {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: requirements.txt에 python-dateutil 확인**

```bash
grep "dateutil\|python-dateutil" requirements.txt
```

없으면 추가:
```bash
echo "python-dateutil" >> requirements.txt
```

- [ ] **Step 3: 로컬 실행 테스트 (GEMINI_API_KEY 필요)**

```bash
cd "/Users/luke/Service App/double-shot"
python3 scripts/fetch_analyst_quotes.py
```

성공 시:
```
[fetch_analyst_quotes] 월가 애널리스트 발언 수집 시작
[fetch_analyst_quotes] 수집 완료: N명
[fetch_analyst_quotes] 저장 완료 → data/analyst_quotes.json
```

- [ ] **Step 4: 출력 JSON 검증**

```bash
cat data/analyst_quotes.json
```

확인:
- 배열 형식
- 각 항목에 `name`, `affiliation`, `initials`, `quote`, `source`, `published_at`, `time_label`, `sentiment` 존재
- `sentiment` 값이 `bull` / `bear` / `neu` 중 하나
- 최대 4개 이하

- [ ] **Step 5: 커밋**

```bash
git add scripts/fetch_analyst_quotes.py requirements.txt
git commit -m "feat: 월가 애널리스트 발언 수집 스크립트 추가 (fetch_analyst_quotes.py)"
```

---

## Task 2: Jinja2 섹션 템플릿 작성

**Files:**
- Create: `scripts/templates/sections/analyst_quotes.html`

- [ ] **Step 1: 템플릿 파일 생성**

```html
{# 월가 코멘트 섹션 — 애널리스트 12명 48h 이내 실발언 카드 (미국 브리핑) #}
{% if analyst_quotes %}
<div class="open-section">
  <div class="open-section__title" style="display:flex;align-items:center;gap:6px;">
    <span>💬 월가 코멘트</span>
    <span style="font-size:11px;font-weight:400;color:var(--muted);margin-left:auto;">48h 이내 실발언</span>
  </div>
  {% for item in analyst_quotes %}
  <div class="analyst-card">
    <div class="analyst-card__top">
      <div class="analyst-avatar">{{ item.initials }}</div>
      <div class="analyst-meta">
        <div class="analyst-name">{{ item.name }}</div>
        <div class="analyst-affil">{{ item.affiliation }}</div>
      </div>
      <span class="analyst-badge {{ item.sentiment }}">{% if item.sentiment == 'bull' %}강세{% elif item.sentiment == 'bear' %}약세{% else %}중립{% endif %}</span>
    </div>
    <div class="analyst-quote">{{ item.quote }}</div>
    <div class="analyst-footer">
      <span class="analyst-source">{{ item.source }}</span>
      <span class="analyst-time">{{ item.time_label }}</span>
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/sections/analyst_quotes.html
git commit -m "feat: 월가 코멘트 섹션 Jinja2 템플릿 추가"
```

---

## Task 3: `us.json` config 수정

**Files:**
- Modify: `scripts/config/us.json`

- [ ] **Step 1: 현재 내용 확인**

```bash
cat scripts/config/us.json
```

현재 `sections_main`:
```json
["prediction", "reasons", "nh_stock", "watchpoints", "stock_picks"]
```

- [ ] **Step 2: `analyst_quotes` 삽입 (nh_stock 뒤, watchpoints 앞)**

`scripts/config/us.json`을 다음과 같이 수정:

```json
{
  "type": "us",
  "index_name": "S&P500",
  "template": "briefings/us.html",
  "pred_title": "S&P500 방향 예측",
  "url_prefix": "us",
  "scheduled_time": "21:20",
  "gnb_time": "21:20",
  "sections_main": ["prediction", "reasons", "nh_stock", "analyst_quotes", "watchpoints", "stock_picks"],
  "sections_sidebar": ["accuracy", "market_data"]
}
```

- [ ] **Step 3: 커밋**

```bash
git add scripts/config/us.json
git commit -m "feat: us.json에 analyst_quotes 섹션 선언 추가"
```

---

## Task 4: `generate_html.py`에 빌더 추가

**Files:**
- Modify: `scripts/generate_html.py`

`render_briefing()` 함수 안에서 `us` 타입일 때 `analyst_quotes` 컨텍스트를 주입한다.

- [ ] **Step 1: `build_analyst_quotes()` 함수 추가**

`generate_html.py`에서 `build_accuracy()` 함수 정의 바로 위에 다음을 삽입:

```python
def build_analyst_quotes() -> list:
    """analyst_quotes.json을 읽어 반환. 없으면 빈 배열."""
    path = DATA_DIR / "analyst_quotes.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []
```

- [ ] **Step 2: `render_briefing()`에서 us 타입 컨텍스트에 주입**

`render_briefing()` 함수 안 `else` 블록(kospi/us 공통)에서 `ctx["watch_items"]` 줄 바로 아래에 추가:

```python
        if internal_type == "us":
            ctx["analyst_quotes"] = build_analyst_quotes()
        else:
            ctx["analyst_quotes"] = []
```

- [ ] **Step 3: `us.html` 템플릿에 섹션 include 추가**

`scripts/templates/briefings/us.html`을 열어 `{% if watch_items %}` 줄 바로 위에 추가:

```html
            {% if analyst_quotes %}{% include "sections/analyst_quotes.html" %}{% endif %}
```

완성 후 해당 블록 (`us.html`의 reasons 아래 구간):
```html
            {% include "sections/reasons.html" %}
            <div class="divider"></div>
            {% if analyst_quotes %}{% include "sections/analyst_quotes.html" %}{% endif %}
            {% if watch_items %}{% include "sections/watchpoints.html" %}<div class="divider"></div>{% endif %}
            {% if stock_picks %}{% include "sections/stock_picks.html" %}{% endif %}
```

> `divider`는 us.html에 이미 reasons 뒤에 1개 있음. analyst_quotes.html 내부에 divider를 넣지 말 것 (이중 구분선 방지).

- [ ] **Step 4: 로컬 렌더 테스트**

`data/analyst_quotes.json`이 있어야 함 (Task 1 Step 3에서 생성됨). 없으면:
```bash
echo '[{"name":"Tom Lee","affiliation":"Fundstrat","initials":"TL","quote":"테스트 발언입니다.","source":"CNBC","published_at":"2026-06-07T10:00:00+09:00","time_label":"오늘 10:00","sentiment":"bull"}]' > data/analyst_quotes.json
```

렌더:
```bash
python3 scripts/generate_html.py --type us --data-file data/latest_us.json --date 2026-06-07
```

출력 확인:
```bash
grep -c "analyst-card" web/briefings/2026-06-07/us/index.html
```
`1` 이상이면 성공.

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_html.py scripts/templates/briefings/us.html
git commit -m "feat: generate_html에 analyst_quotes 빌더 추가 및 us 템플릿 include 연결"
```

---

## Task 5: GHA workflow에 step 추가

**Files:**
- Modify: `.github/workflows/daily_report.yml`

- [ ] **Step 1: us-briefing job에 step 삽입**

`daily_report.yml`에서 `📰 뉴스 요약 (Gemini Flash)` step과 `✨ Claude 분석 생성` step 사이에 삽입:

```yaml
      - name: 💬 애널리스트 발언 수집 (Gemini google_search)
        if: steps.holiday.outputs.open == 'true'
        continue-on-error: true
        run: python3 scripts/fetch_analyst_quotes.py
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
```

삽입 후 해당 구간:
```yaml
      - name: 📰 뉴스 요약 (Gemini Flash)
        if: steps.holiday.outputs.open == 'true'
        continue-on-error: true
        run: python3 scripts/fetch_news.py --type us

      - name: 💬 애널리스트 발언 수집 (Gemini google_search)
        if: steps.holiday.outputs.open == 'true'
        continue-on-error: true
        run: python3 scripts/fetch_analyst_quotes.py
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}

      - name: ✨ Claude 분석 생성 (Prompt Caching + JSON only)
        if: steps.holiday.outputs.open == 'true'
        run: python3 scripts/call_claude.py --type us --no-html
```

- [ ] **Step 2: 커밋 & 푸시**

```bash
git add .github/workflows/daily_report.yml
git commit -m "feat: GHA us-briefing job에 애널리스트 발언 수집 step 추가"
git push
```

---

## Task 6: 브라우저 최종 검증

- [ ] **Step 1: 로컬 서버 확인**

```bash
# 서버가 이미 실행 중이어야 함 (port 8788)
curl -s http://localhost:8788/preview-us.html | grep -c "analyst-card"
```
`1` 이상이면 OK.

- [ ] **Step 2: 섹션 위치 확인**

브라우저에서 `http://localhost:8788/briefings/2026-06-07/us/index.html` 열기 (Task 4 Step 4에서 생성됨).

스크롤해서 확인:
1. 긴급 점검 본문 다음에 `💬 월가 코멘트` 섹션이 나타남
2. 카드가 렌더링됨 (아바타, 이름, 소속, 뱃지, 발언, 출처, 시간)
3. 관전 포인트 섹션이 그 다음에 나타남

- [ ] **Step 3: 발언 없는 경우 테스트**

```bash
echo '[]' > data/analyst_quotes.json
python3 scripts/generate_html.py --type us --data-file data/latest_us.json --date 2026-06-07
grep -c "analyst-card" web/briefings/2026-06-07/us/index.html || echo "0 — 섹션 생략 확인됨"
```

`0` 또는 "섹션 생략 확인됨" 출력이면 성공.

- [ ] **Step 4: preview-us.html 정리 (임시 목업 제거)**

`web/preview-us.html`에서 브레인스토밍 중 추가한 목업 analyst 카드 블록 제거:

```bash
# 확인
grep -n "analyst\|월가 코멘트" web/preview-us.html
```

해당 블록(`<!-- ★ 월가 코멘트 -->` 부터 `</div>` 닫힘까지) 수동 삭제 후:

```bash
git add web/preview-us.html web/assets/style.css
git commit -m "chore: preview-us.html 목업 정리"
```

> `web/assets/style.css`의 analyst CSS는 실제 운영에 쓰이므로 유지.
