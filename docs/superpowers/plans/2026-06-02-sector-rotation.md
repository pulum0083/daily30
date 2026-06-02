# 섹터 로테이션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 아침 브리핑의 "반도체 고정" 섹터 심층 섹션을 8개 섹터 하이브리드 로테이션으로 전환한다.

**Architecture:** `call_claude.py`의 `KOSPI_SYSTEM_PROMPT`에 8개 섹터 풀을 정적으로 박고, 최근 선정 이력(`data/sector_history_kospi.json`)을 user 메시지에 회피 힌트로 주입한다(기존 `signal_history` 패턴 복제). Claude가 고른 `sector_focus`를 코드에서 검증·보정(`pick_sector`)하고 이력에 저장한다. 템플릿은 `sector_semicon.html` → `sector_focus.html`로 일반화하되 CSS 클래스(`semicon-section-title`)는 유지한다.

**Tech Stack:** Python 3, anthropic SDK, Jinja2. 테스트는 stdlib assert 기반(`tests/test_sector_rotation.py`).

**작업 루트:** `/Users/ncsoft/m-project/double-shot` (모든 경로는 이 기준).

**참고 — 손대지 않는 것:**
- `US_SYSTEM_PROMPT`의 `sector_semicon` 블록 — generate_html이 US엔 안 읽어 이미 미사용. 범위 밖.
- `web/assets/style.css`의 `.semicon-section-title` — 템플릿에서 클래스명 유지하므로 변경 불필요.
- 코스피 **마감**(`KOSPI_CLOSE_SYSTEM_PROMPT`)·미국 브리핑.

---

## 파일 구조

| 파일 | 책임 | 변경 |
|---|---|---|
| `scripts/call_claude.py` | 섹터 풀 상수, 이력 I/O, 회피 힌트, 선정 검증, 프롬프트, 와이어링 | 수정 |
| `scripts/generate_html.py` | `sector_focus` → 템플릿 컨텍스트 매핑 | 수정 (572–575) |
| `scripts/templates/sections/sector_focus.html` | 동적 섹터 심층 섹션 (rename) | 신규(rename) |
| `scripts/templates/briefings/kospi.html` | include 파일명·조건 변수 | 수정 (32) |
| `data/sector_history_kospi.json` | 선정 이력 | 런타임 자동 생성 |
| `tests/test_sector_rotation.py` | 순수 함수 단위 테스트 | 신규 |
| `agents/kospi_morning.md`, `docs/PRD.md` | 문서 동기화 | 수정 |

---

## Task 1: 섹터 풀 상수 + 순수 헬퍼 함수 (TDD)

**Files:**
- Modify: `scripts/call_claude.py` (상수 블록 `DATA_DIR` 아래 ~line 29 부근, 헬퍼는 `build_avoidance_hint` 근처 ~line 625)
- Test: `tests/test_sector_rotation.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/test_sector_rotation.py`:

```python
# 섹터 로테이션 순수 함수 단위 테스트
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
import call_claude as cc


def test_sector_pool_has_8_unique_keys():
    keys = [s["key"] for s in cc.SECTOR_POOL]
    assert len(keys) == 8
    assert len(set(keys)) == 8
    for s in cc.SECTOR_POOL:
        assert s["key"] and s["name"] and s["emoji"]


def test_avoidance_hint_empty_when_no_history():
    assert cc.build_sector_avoidance_hint([]) == ""


def test_avoidance_hint_lists_recent_sector_names():
    history = [
        {"date": "2026-06-02", "sector_key": "semicon"},
        {"date": "2026-06-01", "sector_key": "defense"},
    ]
    hint = cc.build_sector_avoidance_hint(history, days=5)
    assert "반도체" in hint
    assert "방산" in hint
    assert "sector_focus" in hint


def test_pick_sector_keeps_valid_choice_and_injects_meta():
    focus = {"sector_key": "defense", "signal": "x", "paragraphs": ["a"]}
    result = cc.pick_sector(focus, recent_keys=[])
    assert result["sector_key"] == "defense"
    assert result["sector_name"] == "방산"
    assert result["emoji"] == "🛡️"
    assert result["signal"] == "x"
    assert result["paragraphs"] == ["a"]


def test_pick_sector_falls_back_when_key_invalid():
    result = cc.pick_sector({"sector_key": "nonsense"}, recent_keys=["semicon"])
    # 폴백은 최근(semicon) 제외하고 pool 순서상 첫 미사용 섹터(power)
    assert result["sector_key"] == "power"
    assert result["sector_name"] == "AI전력기기"


def test_pick_sector_handles_none_focus():
    result = cc.pick_sector(None, recent_keys=[])
    assert result["sector_key"] == "semicon"
    assert result["signal"] == ""
    assert result["paragraphs"] == []


if __name__ == "__main__":
    import inspect
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and inspect.isfunction(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `cd /Users/ncsoft/m-project/double-shot && python3 tests/test_sector_rotation.py`
Expected: FAIL — `AttributeError: module 'call_claude' has no attribute 'SECTOR_POOL'`

- [ ] **Step 3: 최소 구현 — 상수 추가**

`scripts/call_claude.py`에서 `KST = pytz.timezone("Asia/Seoul")` 줄(~line 29) **바로 아래**에 추가:

```python

# ─────────────────────────────────────────────────────────────────────────────
# 섹터 로테이션 풀 (코스피 아침 브리핑 — sector_focus)
# ─────────────────────────────────────────────────────────────────────────────
SECTOR_POOL = [
    {"key": "semicon", "name": "반도체",     "emoji": "🏭"},
    {"key": "power",   "name": "AI전력기기", "emoji": "⚡"},
    {"key": "defense", "name": "방산",       "emoji": "🛡️"},
    {"key": "ship",    "name": "조선",       "emoji": "🚢"},
    {"key": "battery", "name": "2차전지",    "emoji": "🔋"},
    {"key": "auto",    "name": "자동차",     "emoji": "🚗"},
    {"key": "bio",     "name": "바이오",     "emoji": "💊"},
    {"key": "finance", "name": "금융",       "emoji": "🏦"},
]
SECTOR_BY_KEY = {s["key"]: s for s in SECTOR_POOL}
```

- [ ] **Step 4: 최소 구현 — 순수 헬퍼 함수 추가**

`scripts/call_claude.py`에서 `build_avoidance_hint` 함수 정의(~line 625) **바로 위**에 추가:

```python
def build_sector_avoidance_hint(history: list, days: int = 5) -> str:
    """최근 N회 선정된 섹터를 회피 가이드 문자열로 포맷. history 비면 빈 문자열."""
    names = []
    for h in history[:days]:
        s = SECTOR_BY_KEY.get(h.get("sector_key"))
        if s:
            names.append(f"{s['emoji']} {s['name']}")
    if not names:
        return ""
    return (
        "\n## 🔄 섹터 로테이션 가이드\n"
        f"최근 다룬 섹터: {', '.join(names)}\n"
        "위 섹터는 가급적 피하고, 오늘 뉴스·시장 흐름상 가장 임팩트 큰 다른 섹터를 골라 "
        "sector_focus를 작성하세요. 단, 특정 섹터에 압도적 빅뉴스가 있으면 중복이어도 괜찮아요.\n"
    )


def pick_sector(focus: dict, recent_keys: list) -> dict:
    """Claude가 고른 sector_focus를 검증·보정한다.
    - sector_key가 풀에 없으면 최근(recent_keys) 제외하고 pool 순서상 첫 섹터로 폴백.
    - name·emoji는 항상 풀의 정본 값으로 덮어써 불일치를 막는다.
    - signal·paragraphs는 Claude 출력 유지.
    """
    focus = focus or {}
    key = focus.get("sector_key")
    if key not in SECTOR_BY_KEY:
        key = next(
            (s["key"] for s in SECTOR_POOL if s["key"] not in recent_keys),
            SECTOR_POOL[0]["key"],
        )
    meta = SECTOR_BY_KEY[key]
    result = dict(focus)
    result["sector_key"] = meta["key"]
    result["sector_name"] = meta["name"]
    result["emoji"] = meta["emoji"]
    result.setdefault("signal", "")
    result.setdefault("paragraphs", [])
    return result
```

- [ ] **Step 5: 테스트 실행해 통과 확인**

Run: `cd /Users/ncsoft/m-project/double-shot && python3 tests/test_sector_rotation.py`
Expected: PASS — `All 6 tests passed.`

- [ ] **Step 6: 커밋**

```bash
cd /Users/ncsoft/m-project/double-shot
git add scripts/call_claude.py tests/test_sector_rotation.py
git commit -m "feat: 섹터 로테이션 풀 상수·회피힌트·선정검증 헬퍼 추가"
```

---

## Task 2: 섹터 이력 파일 I/O (signal_history 패턴 복제)

**Files:**
- Modify: `scripts/call_claude.py` (`save_signal_to_history` 정의 ~line 611 바로 아래)

- [ ] **Step 1: 구현 — load/save 함수 추가**

`save_signal_to_history` 함수 끝(~line 622) **바로 아래**에 추가:

```python
def load_sector_history(briefing_type: str) -> list:
    """data/sector_history_{type}.json의 history 배열을 반환. 없으면 빈 리스트."""
    path = DATA_DIR / f"sector_history_{briefing_type}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("history", [])


def save_sector_to_history(briefing_type: str, date_str: str, sector_key: str, keep: int = 10) -> None:
    """오늘 선정 섹터를 date 기준 upsert. 최근 keep개만 보관 (최신순)."""
    path = DATA_DIR / f"sector_history_{briefing_type}.json"
    history = [h for h in load_sector_history(briefing_type) if h.get("date") != date_str]
    history.append({"date": date_str, "sector_key": sector_key})
    history.sort(key=lambda h: h.get("date", ""), reverse=True)
    history = history[:keep]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"history": history}, f, ensure_ascii=False, indent=2)
    print(f"[call_claude] Saved sector history → {path} ({len(history)} entries)")
```

- [ ] **Step 2: 스모크 테스트 — 임시 디렉터리로 라운드트립 확인**

Run:
```bash
cd /Users/ncsoft/m-project/double-shot && python3 -c "
import sys, pathlib, tempfile
sys.path.insert(0, 'scripts')
import call_claude as cc
cc.DATA_DIR = pathlib.Path(tempfile.mkdtemp())
cc.save_sector_to_history('kospi', '2026-06-02', 'semicon')
cc.save_sector_to_history('kospi', '2026-06-03', 'defense')
h = cc.load_sector_history('kospi')
assert h[0] == {'date': '2026-06-03', 'sector_key': 'defense'}, h
assert len(h) == 2, h
print('PASS sector history roundtrip')
"
```
Expected: `PASS sector history roundtrip`

- [ ] **Step 3: 커밋**

```bash
cd /Users/ncsoft/m-project/double-shot
git add scripts/call_claude.py
git commit -m "feat: 섹터 선정 이력 파일 I/O 추가 (sector_history_kospi.json)"
```

---

## Task 3: KOSPI_SYSTEM_PROMPT — 반도체 고정 → sector_focus 일반화

**Files:**
- Modify: `scripts/call_claude.py` (line 178, 209–222, 224, 265–273)

- [ ] **Step 1: 섹터 규칙 블록 교체 (209–222)**

기존 블록(`### 반도체 섹터 브리핑(sector_semicon) 작성 규칙` ~ `- 수치는 <b> 태그로 강조. 반도체 관련 뉴스가 없어도 구조적 관점으로 작성.`)을 아래로 교체:

```text
### 오늘의 섹터 브리핑(sector_focus) 작성 규칙
코스피 아침 브리핑 하단에 붙는 "오늘의 섹터" 심층 분석. 매일 아래 8개 섹터 풀에서 1개를 골라 작성한다.

| sector_key | 섹터명 | 대표 종목 |
|---|---|---|
| semicon | 반도체 | 삼성전자, SK하이닉스, 한미반도체 |
| power | AI전력기기 | HD현대일렉트릭, LS일렉트릭, 효성중공업 |
| defense | 방산 | 한화에어로스페이스, LIG넥스원, 현대로템 |
| ship | 조선 | HD현대중공업, 한화오션, 삼성중공업 |
| battery | 2차전지 | LG에너지솔루션, 에코프로비엠, 삼성SDI |
| auto | 자동차 | 현대차, 기아, 현대모비스 |
| bio | 바이오 | 삼성바이오로직스, 셀트리온, 유한양행 |
| finance | 금융 | KB금융, 신한지주, 메리츠금융 |

- **섹터 선택**: 오늘 뉴스·시장 흐름상 가장 임팩트 큰 섹터 1개를 고른다. user 메시지에 "섹터 로테이션 가이드"가 있으면 최근 다룬 섹터는 피한다.
- **sector_key / sector_name**: 위 표의 값 그대로 사용한다.
- **signal**: 오늘 그 섹터의 핵심을 한 문장으로. 마침표 종결. 30자 이내.
  예시: "HBM 수요는 건재. 삼성 수율 인증 지연이 SK하이닉스에 계속 유리하게 작용 중."
- **paragraphs**: 3개 문단. 각 문단은 해요체 2~3문장.
  - 1문단: 오늘 그 섹터의 핵심 모멘텀 또는 이슈 (관련 정량 수치 있으면 활용)
  - 2문단: 종목별 차별화 시각 — 같은 섹터 안 승자 vs 패자를 구체 종목명으로 대비
  - 3문단: 리스크 요인 또는 변곡점 시그널
- 수치는 <b> 태그로 강조. 관련 뉴스가 없어도 구조적 관점으로 작성한다.
- 반도체는 SOX·DRAM ETF 수치를 활용할 수 있다. 그 외 섹터는 뉴스와 구조적 관점 중심으로 쓴다.
```

- [ ] **Step 2: 필수 필드·참조 문구 수정 (178, 224)**

- line 178: `reasons, watch_items, sector_semicon 등 모든 출력에서` → `reasons, watch_items, sector_focus 등 모든 출력에서`
- line 224: `**[필수] JSON에 반드시 포함해야 하는 필드: prediction, reason_title, reasons, stock_picks, sector_semicon**` → `**[필수] JSON에 반드시 포함해야 하는 필드: prediction, reason_title, reasons, stock_picks, sector_focus**`

- [ ] **Step 3: JSON 예시 교체 (265–273)**

기존 `"sector_semicon": { ... }` 블록 전체를 아래로 교체:

```text
  "sector_focus": {
    "sector_key": "semicon",
    "sector_name": "반도체",
    "emoji": "🏭",
    "signal": "HBM 수요는 건재. 삼성 수율 인증 지연이 SK하이닉스에 계속 유리하게 작용 중.",
    "paragraphs": [
      "엔비디아 Blackwell 출하가 본격화되면서 HBM3E 수요가 예상보다 오래 이어지고 있어요. SK하이닉스는 이 사이클의 직접 수혜 위치를 유지하고 있어요.",
      "삼성전자는 HBM4 수율 이슈가 아직 해소됐다는 공식 신호가 없어요. 수율 인증 공시를 확인한 뒤 진입하는 게 안전해요.",
      "지금 가장 중요한 리스크는 경쟁이 아니라 빅테크의 자본지출 피로예요. 엔비디아 가이던스가 꺾이는 순간이 이 사이클의 변곡점이 될 거예요."
    ]
  }
```

- [ ] **Step 4: 구문 검증 (프롬프트 문자열 깨짐 없는지)**

Run: `cd /Users/ncsoft/m-project/double-shot && python3 -c "import sys; sys.path.insert(0,'scripts'); import call_claude as cc; assert 'sector_focus' in cc.KOSPI_SYSTEM_PROMPT; assert 'sector_semicon' not in cc.KOSPI_SYSTEM_PROMPT.split('US_SYSTEM_PROMPT')[0]; print('PASS kospi prompt updated')"`
Expected: `PASS kospi prompt updated`

- [ ] **Step 5: 커밋**

```bash
cd /Users/ncsoft/m-project/double-shot
git add scripts/call_claude.py
git commit -m "feat: KOSPI 프롬프트 반도체 고정 → sector_focus 8섹터 일반화"
```

---

## Task 4: call_claude()에 동적 선정 와이어링

**Files:**
- Modify: `scripts/call_claude.py` (회피힌트 주입 ~line 851 부근, 응답 후 저장 ~line 888 부근, 함수 `call_claude` 내부)

- [ ] **Step 1: 섹터 회피 힌트 주입**

`call_claude()` 안에서 기존 시그널 회피 힌트 블록(`if briefing_type in ("kospi", "us"):` … `build_avoidance_hint(history, days=3)` … `user_content += hint`) **바로 아래**에 추가:

```python
    # 섹터 로테이션 가이드: 최근 선정 섹터 회피 (kospi 아침만)
    if briefing_type == "kospi":
        sector_history = load_sector_history("kospi")
        sector_hint = build_sector_avoidance_hint(sector_history, days=5)
        if sector_hint:
            user_content += sector_hint
            print(f"[call_claude] Sector rotation hint injected ({len(sector_history[:5])} recent)")
```

- [ ] **Step 2: 응답 후 sector_focus 검증·이력 저장**

`call_claude()` 안에서 응답을 파싱한 `analysis` 가 만들어진 뒤(기존 `save_signal_to_history(briefing_type, date_str, signals)` 호출 블록) **바로 아래**에 추가:

```python
    # sector_focus 검증·보정 후 이력 저장 (kospi 아침만)
    if briefing_type == "kospi":
        recent_keys = [h.get("sector_key") for h in load_sector_history("kospi")[:5]]
        analysis["sector_focus"] = pick_sector(analysis.get("sector_focus"), recent_keys)
        save_sector_to_history("kospi", date_str, analysis["sector_focus"]["sector_key"])
        print(f"[call_claude] Sector focus → {analysis['sector_focus']['sector_key']}")
```

> 확인: 이 블록은 `analysis` 변수가 존재하고 `return analysis` **이전**이어야 한다. `save_signal_to_history` 호출 위치가 그 조건을 만족하므로 같은 자리에 둔다.

- [ ] **Step 3: import 회귀 확인**

Run: `cd /Users/ncsoft/m-project/double-shot && python3 -c "import sys; sys.path.insert(0,'scripts'); import call_claude; print('PASS import ok')" && python3 tests/test_sector_rotation.py`
Expected: `PASS import ok` 그리고 `All 6 tests passed.`

- [ ] **Step 4: 커밋**

```bash
cd /Users/ncsoft/m-project/double-shot
git add scripts/call_claude.py
git commit -m "feat: call_claude에 섹터 회피힌트 주입·선정 검증·이력 저장 와이어링"
```

---

## Task 5: generate_html.py — sector_focus 컨텍스트 매핑

**Files:**
- Modify: `scripts/generate_html.py` (572–575)

- [ ] **Step 1: 매핑 교체**

기존 블록:
```python
        if internal_type == "kospi":
            ss = analysis.get("sector_semicon") or {}
            if ss.get("signal"):
                ctx["semicon_signal"] = ss["signal"]
                ctx["semicon_paragraphs"] = ss.get("paragraphs", [])
```
을 아래로 교체 (구 아카이브 호환 위해 `sector_semicon` 폴백 유지):
```python
        if internal_type == "kospi":
            sf = analysis.get("sector_focus") or analysis.get("sector_semicon") or {}
            if sf.get("signal"):
                ctx["sector_emoji"] = sf.get("emoji", "🏭")
                ctx["sector_name"] = sf.get("sector_name", "반도체")
                ctx["sector_signal"] = sf["signal"]
                ctx["sector_paragraphs"] = sf.get("paragraphs", [])
```

- [ ] **Step 2: 구문 확인**

Run: `cd /Users/ncsoft/m-project/double-shot && python3 -c "import ast; ast.parse(open('scripts/generate_html.py').read()); print('PASS syntax ok')"`
Expected: `PASS syntax ok`

- [ ] **Step 3: 커밋**

```bash
cd /Users/ncsoft/m-project/double-shot
git add scripts/generate_html.py
git commit -m "feat: generate_html sector_focus 매핑 (emoji·name 동적, 구 필드 폴백)"
```

---

## Task 6: 템플릿 rename + 동적 타이틀 + include 갱신

**Files:**
- Rename: `scripts/templates/sections/sector_semicon.html` → `scripts/templates/sections/sector_focus.html`
- Modify: `scripts/templates/briefings/kospi.html` (32)

- [ ] **Step 1: 템플릿 rename**

```bash
cd /Users/ncsoft/m-project/double-shot
git mv scripts/templates/sections/sector_semicon.html scripts/templates/sections/sector_focus.html
```

- [ ] **Step 2: sector_focus.html 내용 교체**

`scripts/templates/sections/sector_focus.html` 전체를 아래로 교체 (CSS 클래스 `semicon-section-title` 유지 — style.css 호환):

```html
{# 오늘의 섹터 심층 브리핑 — 관전 포인트 위, 블릿 형태 #}
<div class="open-section">
  <div class="open-section__title semicon-section-title">{{ sector_emoji }} {{ sector_name }} 섹터 — {{ sector_signal }}</div>
  <div class="reason-block">
    <ul>
      {% for para in sector_paragraphs %}
      <li>{{ para | safe }}</li>
      {% endfor %}
    </ul>
  </div>
</div>
```

- [ ] **Step 3: kospi.html include·조건 변수 갱신 (line 32)**

기존:
```html
            {% if semicon_signal %}{% include "sections/sector_semicon.html" %}<div class="divider"></div>{% endif %}
```
을:
```html
            {% if sector_signal %}{% include "sections/sector_focus.html" %}<div class="divider"></div>{% endif %}
```

- [ ] **Step 4: 잔여 참조 확인 (다른 곳에서 옛 이름 참조 없는지)**

Run: `cd /Users/ncsoft/m-project/double-shot && grep -rn "sector_semicon.html\|semicon_signal\|semicon_paragraphs" scripts/ | grep -v "node_modules"`
Expected: 출력 없음 (모두 정리됨)

- [ ] **Step 5: 커밋**

```bash
cd /Users/ncsoft/m-project/double-shot
git add scripts/templates/sections/sector_focus.html scripts/templates/briefings/kospi.html
git commit -m "feat: sector_semicon.html → sector_focus.html 일반화, include·변수 갱신"
```

---

## Task 7: 엔드투엔드 렌더 검증

**Files:** (변경 없음 — 검증 전용)

- [ ] **Step 1: 샘플 analysis로 HTML 렌더 스모크 테스트**

Run:
```bash
cd /Users/ncsoft/m-project/double-shot && python3 -c "
import sys, pathlib
sys.path.insert(0, 'scripts')
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('scripts/templates'))
t = env.get_template('sections/sector_focus.html')
html = t.render(sector_emoji='🛡️', sector_name='방산', sector_signal='수출 모멘텀 지속.', sector_paragraphs=['한화에어로 강세예요.', '리스크는 환율이에요.'])
assert '방산 섹터' in html and '🛡️' in html and 'semicon-section-title' in html, html
print('PASS sector_focus template renders')
print(html)
"
```
Expected: `PASS sector_focus template renders` 와 렌더된 HTML (제목에 `🛡️ 방산 섹터 — 수출 모멘텀 지속.`).

- [ ] **Step 2: 전체 테스트 재실행**

Run: `cd /Users/ncsoft/m-project/double-shot && python3 tests/test_sector_rotation.py`
Expected: `All 6 tests passed.`

---

## Task 8: 문서 동기화

**Files:**
- Modify: `agents/kospi_morning.md`, `docs/PRD.md`

- [ ] **Step 1: agents/kospi_morning.md 갱신**

`agents/kospi_morning.md`에서 섹터 관련 서술이 있으면 "반도체 섹터 고정" → "8개 풀 중 1개 자동 선정(sector_focus, 최근 5회 회피)"로 수정한다. Step 3 JSON 예시에 `sector_semicon` 언급이 있으면 `sector_focus`(sector_key·sector_name·emoji 포함)로 바꾼다.

> 참고: 런타임 경로는 `call_claude.py`의 `KOSPI_SYSTEM_PROMPT`이며 이 파일은 문서/대체 경로다. 내용 동기화만 한다.

- [ ] **Step 2: docs/PRD.md 갱신**

`docs/PRD.md`의 코스피 아침 브리핑 설명에 "섹터 심층 = 8개 풀 하이브리드 로테이션(sector_focus)" 한 줄을 반영하고, 변경 이력 표에 `2026-06-02 | 코스피 아침 섹터 로테이션 도입 (sector_semicon → sector_focus)` 행을 추가한다.

- [ ] **Step 3: 커밋**

```bash
cd /Users/ncsoft/m-project/double-shot
git add agents/kospi_morning.md docs/PRD.md
git commit -m "docs: 섹터 로테이션(sector_focus) 반영 — 에이전트·PRD 동기화"
```

---

## Self-Review 결과

- **스펙 커버리지:** 섹터풀 8개(Task1·3) · sector_focus 데이터모델(Task1·3) · 하이브리드 선정+이력(Task1·2·4) · MVP 데이터범위(Task3 프롬프트) · 템플릿 일반화(Task6) · generate_html 매핑(Task5) · 재미레이어(Task3 paragraphs 규칙) · 문서(Task8) — 모두 태스크에 매핑됨.
- **스펙과의 의도적 차이:** 스펙 4-4는 "generate_html이 이력 append"라 했으나, 기존 `signal_history` 저장이 `call_claude`에 있어 일관성을 위해 **이력 저장을 call_claude로 이동**(Task4). 동작·결과 동일.
- **타입 일관성:** `pick_sector`/`build_sector_avoidance_hint`/`SECTOR_POOL`/`SECTOR_BY_KEY`/`load_sector_history`/`save_sector_to_history` 시그니처가 Task 전반에서 일치. 템플릿 변수 `sector_emoji·sector_name·sector_signal·sector_paragraphs`가 generate_html(Task5)·템플릿(Task6)·렌더검증(Task7)에서 동일.
- **플레이스홀더:** 없음.
