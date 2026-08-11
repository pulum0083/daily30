# 성적표 "항상 상승" 기준선 병기 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 브리핑 "우리 성적표" 카드에 "매일 상승이라고만 답했을 때의 적중률"(기준선)을 게이지로 병기하고, 모달에 설명 문장과 월별 기준선을 추가한다.

**Architecture:** `build_scorecard()`가 이미 만드는 `scored` 리스트 위에 순수 함수 두 개(`_baseline_pct`, `_edge_cls`)를 얹어 컨텍스트를 늘린다. 템플릿·CSS는 기존 `.sc-*` 규칙 옆에 추가한다. 새 데이터 소스도, 새 JS도 없다.

**Tech Stack:** Python 3.12 + Jinja2 (`scripts/generate_html.py`), 정적 CSS (`web/assets/style.css`), pytest

**스펙:** [docs/superpowers/specs/2026-08-11-scorecard-baseline-design.md](../specs/2026-08-11-scorecard-baseline-design.md)

---

## File Structure

| 파일 | 책임 | 변경 |
| --- | --- | --- |
| `scripts/generate_html.py` | 기준선·우위 폭 계산, 템플릿 컨텍스트 조립 | 수정 (`build_scorecard` 주변) |
| `scripts/templates/sections/_scorecard.html` | 카드·모달 마크업 | 수정 |
| `web/assets/style.css` | 게이지·범례·설명 블록·기준 컬럼 스타일 | 수정 (2곳 삽입) |
| `scripts/test_scorecard_baseline.py` | 회귀 테스트 | 신설 |

**기존 브리핑 HTML은 재생성하지 않는다.** 다음 정규 발행(평일 07:25)부터 반영된다.

---

## Task 1: 기준선·색 판정 순수 함수

**Files:**
- Create: `scripts/test_scorecard_baseline.py`
- Modify: `scripts/generate_html.py` (`build_scorecard` 바로 위, 현재 1092번째 줄 앞)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`scripts/test_scorecard_baseline.py` 신규 생성. 파일 전체 내용:

```python
# 성적표 '항상 상승' 기준선 계산·표시 회귀 테스트 (스펙 2026-08-11)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_html import _baseline_pct, _edge_cls  # noqa: E402


def _row(date, is_correct, up):
    """채점 완료된 코스피 항목 하나.

    up=실제 상승 여부. predicted_direction은 is_correct와 앞뒤가 맞게 역산한다
    (맞혔으면 실제와 같은 방향을 예측한 것).
    """
    return {
        "date": date,
        "type": "kospi",
        "predicted_direction": "상승 우위" if (up == is_correct) else "하락 우위",
        "actual_direction": "상승" if up else "하락",
        "actual_change_pct": 1.0 if up else -1.0,
        "is_correct": is_correct,
    }


def test_baseline_counts_actual_up_days():
    """기준선 = 실제 상승일 비율. 상승 3 / 하락 2 → 60%."""
    rows = [
        _row("2026-04-01", True, True),
        _row("2026-04-02", False, True),
        _row("2026-04-03", True, True),
        _row("2026-04-06", True, False),
        _row("2026-04-07", False, False),
    ]
    assert _baseline_pct(rows) == 60


def test_baseline_excludes_unscored():
    """미채점 항목은 우리 적중률 표본에 없으므로 기준선에서도 빠진다.

    같은 표본이 아니면 비교 자체가 무의미하다 — 이 불변식을 계산 지점에서 보장한다.
    """
    rows = [
        _row("2026-04-01", True, True),
        _row("2026-04-02", True, False),
        {"date": "2026-04-03", "type": "kospi", "actual_direction": None,
         "actual_change_pct": None, "is_correct": None},
    ]
    # 채점된 2건 중 상승 1건 → 50%. 미채점을 세면 33%가 되어 틀린다.
    assert _baseline_pct(rows) == 50


def test_baseline_empty_does_not_divide_by_zero():
    assert _baseline_pct([]) == 0
    assert _baseline_pct([{"is_correct": None}]) == 0


def test_edge_cls_boundaries():
    """±10%p 경계. 최근 15건 기준 1건이 6.7%p라 한 자릿수 차이는 노이즈다."""
    assert _edge_cls(10) == "good"
    assert _edge_cls(9) == "flat"
    assert _edge_cls(0) == "flat"
    assert _edge_cls(-9) == "flat"
    assert _edge_cls(-10) == "bad"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest scripts/test_scorecard_baseline.py -q`
Expected: FAIL — `ImportError: cannot import name '_baseline_pct' from 'generate_html'`

- [ ] **Step 3: 최소 구현**

`scripts/generate_html.py`에서 `def build_scorecard(internal_type: str) -> dict:` 바로 **위**에 두 함수를 추가한다.

```python
def _baseline_pct(rows: list) -> int:
    """구간 내 실제 상승일 비율(%). '매일 상승이라고만 답하는 예측기'의 적중률이다.

    우리 적중률과 반드시 같은 표본이어야 비교가 성립하므로, 미채점 항목은
    여기서도 직접 걸러낸다(호출자 필터링에 의존하지 않는다).
    상승 판정은 채점 로직(check_accuracy)이 기록한 actual_direction을 그대로 쓴다."""
    scored = [b for b in rows if b.get("is_correct") is not None]
    if not scored:
        return 0
    up = sum(1 for b in scored if b.get("actual_direction") == "상승")
    return round(up / len(scored) * 100)


def _edge_cls(edge: int) -> str:
    """우위 폭(%p) → 게이지 채움 색. ±10%p를 경계로 둔다.

    최근 15건 기준 1건이 6.7%p라 한 자릿수 차이는 표본 노이즈다. 경계를 0에 두면
    +3%p 같은 사실상 무차이를 초록으로 칠해 없는 우위를 주장하게 된다."""
    if edge >= 10:
        return "good"
    if edge <= -10:
        return "bad"
    return "flat"
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest scripts/test_scorecard_baseline.py -q`
Expected: PASS — `4 passed`

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_html.py scripts/test_scorecard_baseline.py
git commit -m "feat(성적표): '항상 상승' 기준선·우위 색 판정 순수 함수

기준선은 우리 적중률과 같은 표본(채점 완료분)에서만 센다 — 미채점이
한쪽에만 섞이면 비교가 무의미해지므로 계산 지점에서 직접 거른다.
색 경계 ±10%p는 최근 15건 기준 1건이 6.7%p인 표본 노이즈를 반영한 값.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: build_scorecard 컨텍스트 확장

**Files:**
- Modify: `scripts/generate_html.py` (`build_scorecard`, 현재 1092–1170줄)
- Modify: `scripts/test_scorecard_baseline.py` (테스트 추가)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`scripts/test_scorecard_baseline.py` 맨 위 import 줄을 아래로 교체한다.

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_html  # noqa: E402
from generate_html import _baseline_pct, _edge_cls, build_scorecard  # noqa: E402
```

그리고 파일 **맨 끝**에 아래를 추가한다.

```python
def _fixture_rows():
    """4월 10건 + 5월 10건 = 20건. 기대값은 손으로 계산해 아래 테스트에 박아둔다.

    4월 — 상승 8(1~8일차) / 적중 6(1~6일차)  → 우리 60%, 기준 80%, 우위 -20%p
    5월 — 상승 3(1~3일차) / 적중 8(1~8일차)  → 우리 80%, 기준 30%, 우위 +50%p
    누적 20건 — 적중 14(70%), 상승 11(55%)   → 우위 +15%p
    최근 15건(4월 6~10일차 + 5월 전체) — 적중 9(60%), 상승 6(40%) → 우위 +20%p
    """
    rows = []
    for i in range(1, 11):
        rows.append(_row(f"2026-04-{i:02d}", is_correct=(i <= 6), up=(i <= 8)))
    for i in range(1, 11):
        rows.append(_row(f"2026-05-{i:02d}", is_correct=(i <= 8), up=(i <= 3)))
    return rows


def _ctx(monkeypatch, tmp_path, rows):
    """briefings.json 픽스처를 주입하고 build_scorecard를 돌린다.

    실제 data/briefings.json을 읽으면 다음 채점 때 숫자가 바뀌어 테스트가 깨진다.
    """
    (tmp_path / "briefings.json").write_text(
        json.dumps({"briefings": rows}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(generate_html, "DATA_DIR", tmp_path)
    return build_scorecard("kospi")


def test_card_baseline_values(monkeypatch, tmp_path):
    ctx = _ctx(monkeypatch, tmp_path, _fixture_rows())
    assert ctx["sc_recent15_pct"] == 60
    assert ctx["sc_recent15_base"] == 40
    assert ctx["sc_cum_pct"] == 70
    assert ctx["sc_cum_base"] == 55


def test_displayed_edge_matches_displayed_numbers(monkeypatch, tmp_path):
    """사용자가 암산한 값과 표시된 우위가 어긋나면 안 된다 — 반올림값끼리 뺀다."""
    ctx = _ctx(monkeypatch, tmp_path, _fixture_rows())
    assert ctx["sc_recent15_edge"] == ctx["sc_recent15_pct"] - ctx["sc_recent15_base"]
    assert ctx["sc_cum_edge"] == ctx["sc_cum_pct"] - ctx["sc_cum_base"]
    assert ctx["sc_recent15_edge"] == 20
    assert ctx["sc_cum_edge"] == 15


def test_gauge_colors_follow_edge(monkeypatch, tmp_path):
    ctx = _ctx(monkeypatch, tmp_path, _fixture_rows())
    assert ctx["sc_recent15_gcls"] == "good"   # +20%p
    assert ctx["sc_cum_gcls"] == "good"        # +15%p


def test_monthly_rows_carry_baseline(monkeypatch, tmp_path):
    """기준선에 진 달이 그대로 드러나야 한다 — 4월은 우리 60% vs 기준 80%."""
    ctx = _ctx(monkeypatch, tmp_path, _fixture_rows())
    by_label = {m["label"]: m for m in ctx["sc_monthly"]}
    assert by_label["4월"]["pct"] == 60
    assert by_label["4월"]["base_pct"] == 80
    assert by_label["5월"]["pct"] == 80
    assert by_label["5월"]["base_pct"] == 30


def test_card_omitted_below_five_scored(monkeypatch, tmp_path):
    """표본 5건 미만이면 카드 자체를 생략하는 기존 가드가 유지된다."""
    rows = [_row(f"2026-04-{i:02d}", True, True) for i in range(1, 5)]
    assert _ctx(monkeypatch, tmp_path, rows) == {}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python3 -m pytest scripts/test_scorecard_baseline.py -q`
Expected: FAIL — `KeyError: 'sc_recent15_base'`

- [ ] **Step 3: build_scorecard를 고친다**

`scripts/generate_html.py`에서 아래 세 군데를 바꾼다.

**(a)** 현재 1112–1115줄 (`r15 = scored[-15:]` 블록)을 아래로 교체한다. `pct(r15)`를 두 번 호출하던 것을 변수로 묶고 기준선·우위를 함께 구한다.

```python
    r15 = scored[-15:]
    r15_pct = pct(r15)
    cum_pct = pct(scored)
    r15_base = _baseline_pct(r15)
    cum_base = _baseline_pct(scored)
    # 우위는 원본 실수 차이가 아니라 화면에 뜬 반올림값끼리의 차이로 구한다 —
    # 사용자가 73 − 53을 암산했을 때 표시된 +20%p와 어긋나면 안 된다.
    r15_edge = r15_pct - r15_base
    cum_edge = cum_pct - cum_base
    hits = [b for b in scored if b["is_correct"]]
    hit_avg = (sum(abs(b.get("actual_change_pct") or 0) for b in hits) / len(hits)) if hits else 0
```

**(b)** 현재 1124–1135줄 (월별 적중률 블록)을 아래로 교체한다. 카운터 대신 월별 행 리스트를 모아 `_baseline_pct`를 재사용한다 — 기준선 정의가 한 곳에만 있어야 한다.

```python
    # 월별 적중률 (최근 5개월) — 같은 달 기준선을 함께 실어 진 달이 드러나게 한다
    from collections import defaultdict
    mon = defaultdict(list)
    for b in scored:
        mon[b["date"][:7]].append(b)
    monthly = []
    for mkey in sorted(mon)[-5:]:
        rows_m = mon[mkey]
        p = pct(rows_m)
        monthly.append({
            "label": f"{int(mkey[5:7])}월",
            "pct": p,
            "cls": cls(p),
            "base_pct": _baseline_pct(rows_m),
        })
```

**(c)** 현재 1157–1170줄 (return dict)에서 `sc_recent15_pct`·`sc_recent15_cls` 두 줄을 아래로 교체하고, `sc_cum_cls` 다음 줄에 기준선 필드를 끼워 넣는다. 최종 형태:

```python
    return {
        "sc_recent15_pct": r15_pct,
        "sc_recent15_cls": cls(r15_pct),
        "sc_cum_pct": cum_pct,
        "sc_cum_cls": cls(cum_pct),
        "sc_cum_count": len(scored),
        # 기준선 = 매일 '상승'이라고만 답했을 때의 적중률
        "sc_recent15_base": r15_base,
        "sc_recent15_edge": r15_edge,
        "sc_recent15_gcls": _edge_cls(r15_edge),
        "sc_cum_base": cum_base,
        "sc_cum_edge": cum_edge,
        "sc_cum_gcls": _edge_cls(cum_edge),
        "sc_hit_avg": f"{hit_avg:.1f}%",
        "sc_hit": hit30, "sc_miss": miss30, "sc_pending": pending,
        "sc_hit_pct": round(hit30 / total * 100),
        "sc_miss_pct": round(miss30 / total * 100),
        "sc_pending_pct": round(pending / total * 100),
        "sc_monthly": monthly,
        "sc_recent": recent,
    }
```

교체 대상 1112–1115줄에는 원래 `cum_pct = pct(scored)`가 포함돼 있다. 위 (a) 블록이 그 줄을 그대로 품고 있으므로 **중복 정의가 남지 않는지 교체 후 확인한다** (`grep -c "cum_pct = pct(scored)" scripts/generate_html.py` → `1`).

- [ ] **Step 4: 통과를 확인한다**

Run: `python3 -m pytest scripts/test_scorecard_baseline.py -q`
Expected: PASS — `9 passed`

- [ ] **Step 5: 실데이터로 값을 눈으로 확인한다**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0,'scripts')
from generate_html import build_scorecard
c = build_scorecard('kospi')
print('최근15', c['sc_recent15_pct'], 'vs', c['sc_recent15_base'], c['sc_recent15_edge'], c['sc_recent15_gcls'])
print('누적  ', c['sc_cum_pct'], 'vs', c['sc_cum_base'], c['sc_cum_edge'], c['sc_cum_gcls'])
for m in c['sc_monthly']: print(m['label'], m['pct'], 'vs', m['base_pct'])
"
```
Expected (2026-08-11 기준 실데이터):
```
최근15 73 vs 53 20 good
누적   65 vs 62 3 flat
4월 69 vs 75
5월 67 vs 72
6월 62 vs 62
7월 64 vs 45
8월 67 vs 67
```
누적이 `flat`(회색)으로 나오는 것이 핵심이다 — +3%p를 초록으로 칠하지 않는다.

- [ ] **Step 6: 커밋**

```bash
git add scripts/generate_html.py scripts/test_scorecard_baseline.py
git commit -m "feat(성적표): build_scorecard에 기준선·우위·월별 기준선 컨텍스트 추가

월별 집계를 카운터에서 행 리스트로 바꿔 _baseline_pct를 재사용한다 —
기준선 정의가 두 곳에 생기지 않게 한다. 우위는 반올림값끼리 빼서
화면 숫자와 암산 결과가 어긋나지 않게 했다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: 카드 게이지 + 범례

**Files:**
- Modify: `scripts/templates/sections/_scorecard.html:5-9`
- Modify: `web/assets/style.css:1193` 뒤

- [ ] **Step 1: 카드 마크업을 고친다**

`scripts/templates/sections/_scorecard.html`의 3–14줄(`<div class="sc-card">` 블록)을 아래로 교체한다. 세 번째 칸(적중일 평균)은 대응하는 기준선이 없으므로 게이지를 붙이지 않는다.

```html
<div class="sc-card">
  <div class="sc-card__h"><span class="sc-dot"></span>우리 성적표</div>
  <div class="sc-stats">
    <div class="sc-stat">
      <div class="sc-stat__v {{ sc_recent15_cls }}">{{ sc_recent15_pct }}%</div>
      <div class="sc-stat__l">최근 15건</div>
      {# 막대=우리 적중률, 세로선=매일 '상승'이라고만 답했을 때의 적중률 #}
      <div class="scg">
        <div class="scg__track"><i class="scg__fill {{ sc_recent15_gcls }}" style="width:{{ sc_recent15_pct }}%"></i><i class="scg__mark" style="left:{{ sc_recent15_base }}%"></i></div>
        <div class="scg__cap">기준선 {{ sc_recent15_base }}%</div>
      </div>
    </div>
    <div class="sc-stat">
      <div class="sc-stat__v {{ sc_cum_cls }}">{{ sc_cum_pct }}%</div>
      <div class="sc-stat__l">누적 {{ sc_cum_count }}건</div>
      <div class="scg">
        <div class="scg__track"><i class="scg__fill {{ sc_cum_gcls }}" style="width:{{ sc_cum_pct }}%"></i><i class="scg__mark" style="left:{{ sc_cum_base }}%"></i></div>
        <div class="scg__cap">기준선 {{ sc_cum_base }}%</div>
      </div>
    </div>
    <div class="sc-stat"><div class="sc-stat__v">{{ sc_hit_avg }}</div><div class="sc-stat__l">적중일 평균</div></div>
  </div>
  <div class="sc-legend">
    <span><i class="sc-legend__bar"></i>우리 적중률</span>
    <span><i class="sc-legend__mk"></i>항상 "상승" 기준선</span>
  </div>
  <div class="sc-bar">
    <i class="sc-bar__h" style="width:{{ sc_hit_pct }}%"></i><i class="sc-bar__m" style="width:{{ sc_miss_pct }}%"></i><i class="sc-bar__p" style="width:{{ sc_pending_pct }}%"></i>
  </div>
  <button class="sc-card__cta" data-modal-open="scorecard-modal">틀린 날까지 전부 공개해요 <span>→</span></button>
</div>
```

- [ ] **Step 2: CSS를 추가한다**

`web/assets/style.css`의 `.sc-card__cta:hover{opacity:.75;}` 줄(현재 1193줄) **바로 뒤**에 삽입한다.

```css
/* 성적표 기준선 게이지 — 막대=우리 적중률, 세로선=항상 '상승' 기준선 */
.scg{margin-top:7px;}
.scg__track{height:4px;border-radius:999px;background:var(--surface-inset);position:relative;}
.scg__fill{position:absolute;left:0;top:0;bottom:0;border-radius:999px;}
.scg__fill.good{background:#16A34A;}.scg__fill.flat{background:#9CA3AF;}.scg__fill.bad{background:var(--up);}
.scg__mark{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink);opacity:.55;}
.scg__cap{font-size:9px;color:var(--muted);margin-top:5px;font-variant-numeric:tabular-nums;}
.sc-legend{display:flex;gap:14px;justify-content:center;align-items:center;margin-top:9px;font-size:10px;color:var(--muted);}
.sc-legend span{display:flex;align-items:center;gap:5px;}
.sc-legend__bar{display:block;width:14px;height:4px;border-radius:999px;background:#16A34A;}
.sc-legend__mk{display:block;width:2px;height:10px;background:var(--ink);opacity:.55;}
```

- [ ] **Step 3: 렌더가 깨지지 않는지 확인한다**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0,'scripts')
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from generate_html import build_scorecard
env = Environment(loader=FileSystemLoader('scripts/templates'))
html = env.get_template('sections/_scorecard.html').render(**build_scorecard('kospi'))
assert 'scg__mark' in html and 'sc-legend' in html, '게이지·범례 미렌더'
assert '{{' not in html, '미치환 변수 잔존'
print('OK', len(html), 'bytes')
"
```
Expected: `OK <숫자> bytes` (에러 없이 통과)

- [ ] **Step 4: 커밋**

```bash
git add scripts/templates/sections/_scorecard.html web/assets/style.css
git commit -m "feat(성적표): 카드에 기준선 게이지 2개 + 범례 추가

적중률 65%가 무엇 대비 좋은 것인지 화면에 근거가 없었다. 막대 끝과
세로선의 간격으로 우위 폭이 숫자를 읽기 전에 전달된다 — 누적 칸은
둘이 거의 붙어 '차이 없음'이 그대로 드러난다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: 모달 설명 블록 + 월별 기준선 컬럼

**Files:**
- Modify: `scripts/templates/sections/_scorecard.html` (모달 본문)
- Modify: `web/assets/style.css` (`.sc-mrate__v` 줄 뒤)

- [ ] **Step 1: 모달 마크업을 고친다**

`scripts/templates/sections/_scorecard.html`에서 아래 **원문 세 줄**(모달 본문의 월별 적중률 섹션 시작 부분)을 찾는다. Task 3에서 카드가 길어져 줄 번호가 밀렸으므로 **줄 번호가 아니라 내용으로 찾는다.**

```html
      <div class="sc-modal-sec">월별 적중률</div>
      <div class="sc-mrate">
        {% for m in sc_monthly %}
```

이 지점부터 그 `{% endfor %}`와 닫는 `</div>`까지(총 5줄)를 아래 블록으로 교체한다. 설명 문장이 월별 섹션 **앞**에 오도록 함께 넣는다.

**모달 안의 `<div class="sc-stats">` 블록은 건드리지 않는다** — 모달에는 게이지를 넣지 않는다(카드에서 이미 봤다). "최근 예측 결과" 블록도 변경 없다.

```html
      {# 기준선이라는 낯선 단어를 이 문장이 그 자리에서 정의한다 #}
      <p class="scs">같은 기간 매일 <b>"상승"이라고만</b> 답하면 최근 15건 <b>{{ sc_recent15_base }}%</b>, 누적 <b>{{ sc_cum_base }}%</b>를 맞혀요. 코스피가 오르는 날이 더 많기 때문이에요. 그래서 적중률만으로는 잘한 건지 알 수 없고, 이 기준선을 얼마나 넘었는지가 진짜 성적이에요 — 우리는 <span class="{{ sc_recent15_gcls }}">{{ '%+d'|format(sc_recent15_edge) }}%p</span> · <span class="{{ sc_cum_gcls }}">{{ '%+d'|format(sc_cum_edge) }}%p</span>였어요.</p>

      <div class="sc-modal-sec">월별 적중률 <span class="sc-modal-sec__sub">(오른쪽 = 기준선)</span></div>
      <div class="sc-mrate">
        {% for m in sc_monthly %}
        <div class="sc-mrate__row"><span class="sc-mrate__m">{{ m.label }}</span><div class="sc-mrate__bar"><i class="{{ m.cls }}" style="width:{{ m.pct }}%"></i></div><span class="sc-mrate__v">{{ m.pct }}%</span><span class="sc-mrate__b">기준 {{ m.base_pct }}%</span></div>
        {% endfor %}
      </div>
```

월별 막대 색(`m.cls`)은 **바꾸지 않는다.** 절대 적중률 기준 색이고, 이걸 우위 폭 기준으로 바꾸면 카드 게이지와 다른 의미의 색이 같은 팔레트로 섞인다. 월별 행에서 기준선은 숫자로만 전달한다.

- [ ] **Step 2: CSS를 추가한다**

`web/assets/style.css`의 `.sc-mrate__v{...}` 줄 **바로 뒤**에 삽입한다.

```css
.sc-mrate__b{font-size:11px;color:var(--muted);width:56px;text-align:right;font-variant-numeric:tabular-nums;flex-shrink:0;}
.sc-modal-sec__sub{font-size:11px;font-weight:600;color:var(--muted);}
.scs{margin-top:12px;padding:9px 11px;background:var(--surface-inset);border-radius:var(--r-sm);font-size:11px;line-height:1.65;color:var(--muted);}
.scs b{color:var(--ink);font-weight:700;}
.scs .good{color:#16A34A;font-weight:800;}.scs .flat{color:var(--ink);font-weight:800;}.scs .bad{color:var(--up);font-weight:800;}
```

- [ ] **Step 3: 렌더를 확인한다**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0,'scripts')
from jinja2 import Environment, FileSystemLoader
from generate_html import build_scorecard
env = Environment(loader=FileSystemLoader('scripts/templates'))
html = env.get_template('sections/_scorecard.html').render(**build_scorecard('kospi'))
assert '기준 75%' in html, '4월 기준선 미렌더'
assert '+3%p' in html and '+20%p' in html, '우위 표기 미렌더'
assert '{{' not in html, '미치환 변수 잔존'
print('OK')
"
```
Expected: `OK`

`기준 75%`는 4월(우리 69% vs 기준 75%)이 기준선에 **진** 달로 실제 노출되는지 확인하는 것이다.

- [ ] **Step 4: 커밋**

```bash
git add scripts/templates/sections/_scorecard.html web/assets/style.css
git commit -m "feat(성적표): 모달에 기준선 설명 문장 + 월별 기준선 컬럼

카드 CTA가 '틀린 날까지 전부 공개해요'인데, 기준선에 진 달을 감추면
그 약속과 어긋난다 — 4·5월이 기준선 미달(-6%p·-5%p)로 그대로 노출된다.
월별 막대 색은 기존 절대 적중률 기준을 유지한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: 시각 검증 + 전체 회귀

**Files:** 없음 (검증만)

- [ ] **Step 1: 실제 컨텍스트로 미리보기 HTML을 만든다**

`web/` 아래를 오염시키지 않도록 스크래치패드에 만든다.

Run:
```bash
SP=/private/tmp/claude-501/-Users-ncsoft-my-project-double-shot/dd82d62f-a01b-42cd-9265-0afe975a86d4/scratchpad
python3 -c "
import sys; sys.path.insert(0,'scripts')
from jinja2 import Environment, FileSystemLoader
from generate_html import build_scorecard
env = Environment(loader=FileSystemLoader('scripts/templates'))
card = env.get_template('sections/_scorecard.html').render(**build_scorecard('kospi'))
open('$SP/scorecard-preview.html','w',encoding='utf-8').write(
  '<!doctype html><meta charset=utf-8><link rel=stylesheet href=\"file://$PWD/web/assets/style.css\">'
  '<body style=\"background:var(--surface-soft);padding:24px\">'
  '<div style=\"max-width:420px;margin:0 auto\">' + card + '</div>'
  '<style>.info-modal-backdrop{position:static;display:block;background:none;margin-top:28px}'
  '.info-modal{box-shadow:var(--s1);border:1px solid var(--hairline);border-radius:16px;padding:18px;background:var(--canvas)}</style>'
)
print('$SP/scorecard-preview.html')
"
```
Expected: 경로가 출력됨. (모달은 원래 숨겨져 있으므로 검증용으로 강제 노출시킨다.)

- [ ] **Step 2: 브라우저로 열어 눈으로 확인한다**

`mcp__Claude_Browser__navigate`로 위 파일의 `file://` 절대경로를 열고(브라우저 패널이 닫혀 있으면 `mcp__Claude_Browser__preview_start`에 같은 URL을 준다), `mcp__Claude_Browser__computer`의 `screenshot`으로 찍는다.

확인 항목 네 가지.
1. 최근 15건 칸 — 막대가 **초록**이고 세로선보다 확실히 길다
2. 누적 칸 — 막대가 **회색**이고 세로선과 거의 붙어 있다
3. 범례 두 항목이 한 줄에 들어간다 (좁은 폭에서 줄바꿈으로 깨지지 않는다)
4. 모달 월별 행에서 `기준 N%`가 오른쪽 끝에 정렬되고, 4·5월 기준선이 우리 값보다 높다

- [ ] **Step 3: 다크 모드도 확인한다**

`mcp__Claude_Browser__resize_window`에 `colorScheme: "dark"`를 주고 다시 스크린샷.
확인: 세로선(`--ink` 55% 투명도)이 어두운 배경에서도 보이는지, 회색 막대(`#9CA3AF`)가 트랙(`--surface-inset`)과 구분되는지.

구분이 안 되면 `.scg__mark`의 `opacity`를 다크에서만 올린다.

```css
@media(prefers-color-scheme:dark){.scg__mark{opacity:.8;}}
```

- [ ] **Step 4: 전체 회귀 테스트**

Run: `python3 -m pytest scripts/ -q`
Expected: 전부 통과 (기존 통과 수 + 9). 실패가 있으면 그 테스트가 `build_scorecard` 출력을 기대하고 있는지 먼저 확인한다.

- [ ] **Step 5: 남은 변경이 있으면 커밋**

Step 3에서 CSS를 손봤을 때만 해당한다.

```bash
git add web/assets/style.css
git commit -m "fix(성적표): 다크 모드에서 기준선 세로선 대비 보정

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 6: 정리**

```bash
rm -f /private/tmp/claude-501/-Users-ncsoft-my-project-double-shot/dd82d62f-a01b-42cd-9265-0afe975a86d4/scratchpad/scorecard-preview.html
```

---

## 완료 기준

- [ ] `python3 -m pytest scripts/ -q` 전부 통과
- [ ] 실데이터 기준 누적 칸이 **회색**(+3%p)으로 렌더된다 — 없는 우위를 초록으로 주장하지 않는다
- [ ] 모달 월별에 4월 `기준 75%`, 5월 `기준 72%`가 노출된다 (기준선에 진 달을 감추지 않는다)
- [ ] 라이트/다크 모두에서 세로선이 보인다
- [ ] `web/briefings/` 아래 기존 HTML은 하나도 바뀌지 않았다 (`git status`로 확인)

## 범위 밖

신뢰도(confidence) 표기는 이 계획에 없다. 캘리브레이션이 깨져 있는 것은 확인했으나(70%대 예측이 60%대보다 낮음) `prediction_strip.html`이라는 별개 화면이라 별도 건으로 다룬다.
