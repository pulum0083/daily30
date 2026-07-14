# US 브리핑 "오늘의 관점" 배경색 톤 신호 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** US 브리핑의 "오늘의 관점"(`tv-lead`) 카드 배경색을, 실측 시장 데이터로 결정론적으로 계산한 방향 신호(상승/하락/중립)에 맞춰 코스피와 동일한 방식으로 물들인다. 숫자·확률은 노출하지 않고, 채점하지 않고, 텔레그램에는 적용하지 않는다.

**Architecture:** `scripts/leading_signal.py`에 이미 있는 `compute_prior_us()`(프리마켓 선물·SOX·VIX 등 실측 데이터 기반 결정론적 계산, 현재는 Claude 프롬프트 참고용으로만 쓰임)를 재사용한다. `scripts/generate_html.py`에 새 순수 함수 `build_us_tone(market_data: dict) -> dict`를 추가해 `compute_prior_us()`의 결과(`"상승"/"하락"/"중립"`)를 CSS 클래스명(`"up"/"dn"/"neutral"`)으로 매핑하고, US 렌더 컨텍스트에 `dir_cls`로 주입한다. 템플릿(`sections/todays_view.html`)은 이미 `{{ dir_cls }}`를 쓰고 있으므로 수정 불필요 — `web/assets/style.css`에 `.tv-lead.dn`·`.tv-lead.neutral` 규칙만 추가하면 된다.

**Tech Stack:** Python 3.9+ (repo 시스템 파이썬으로 실행 가능, 신규 3.10+ 문법 금지), pytest, Jinja2, 순수 CSS(라이트/다크 테마 기존 토큰 재사용).

---

### Task 1: `build_us_tone()` 함수 작성 (TDD)

**Files:**
- Modify: `scripts/generate_html.py` (새 함수 추가 — 기존 `build_issues()` 함수 바로 아래, 대략 160행 부근)
- Test: `scripts/test_build_us_tone.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_build_us_tone.py` 파일을 새로 만든다:

```python
# build_us_tone: leading_signal.compute_prior_us() 방향 → CSS dir_cls 매핑 검증
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh


def _latest_us(sp=None, nq=None, dow=None, sox=None, vix=None):
    """latest_us.json 구조 일부를 흉내낸 fixture (test_leading_signal.py의 _latest_us와 동일 형태)."""
    return {
        "futures": {
            "sp500_fut":  {"change_pct": sp} if sp is not None else {},
            "nasdaq_fut": {"change_pct": nq} if nq is not None else {},
            "dow_fut":    {"change_pct": dow} if dow is not None else {},
        },
        "market_data_js": {"sox": {"chg": sox} if sox is not None else {}},
        "vix": {"change_pct": vix} if vix is not None else {},
    }


def test_up_signal_maps_to_up_class():
    market_data = _latest_us(sp=0.39, nq=1.11, dow=0.27, sox=1.05, vix=7.32)
    out = gh.build_us_tone(market_data)
    assert out == {"dir_cls": "up"}


def test_down_signal_maps_to_dn_class():
    market_data = _latest_us(sp=-0.5, dow=-0.3, sox=-2.0, vix=5.0)
    out = gh.build_us_tone(market_data)
    assert out == {"dir_cls": "dn"}


def test_neutral_signal_maps_to_neutral_class():
    market_data = {"futures": {}, "market_data_js": {}}
    out = gh.build_us_tone(market_data)
    assert out == {"dir_cls": "neutral"}


def test_no_numbers_or_score_leaked_in_output():
    # 반환값에 score·confidence 등 수치 필드가 절대 섞이지 않아야 한다 — dir_cls만 노출
    market_data = _latest_us(sp=0.39, nq=1.11, dow=0.27, sox=1.05, vix=7.32)
    out = gh.build_us_tone(market_data)
    assert set(out.keys()) == {"dir_cls"}
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python3 -m pytest scripts/test_build_us_tone.py -v`
Expected: FAIL — `AttributeError: module 'generate_html' has no attribute 'build_us_tone'`

- [ ] **Step 3: 최소 구현 작성**

`scripts/generate_html.py`에서 `build_issues()` 함수(약 147~160행) 바로 아래에 추가한다:

```python
def build_us_tone(market_data: dict) -> dict:
    """leading_signal.compute_prior_us() 방향(실측 프리마켓·SOX·VIX 기반)을
    '오늘의 관점' 배경색 CSS 클래스로 매핑한다. 숫자·점수는 절대 반환하지 않는다 —
    코스피 dir_cls와 동일한 방식으로 색만 동기화하되 채점 대상은 아니다."""
    from leading_signal import compute_prior_us
    prior = compute_prior_us(market_data)
    dir_map = {"상승": "up", "하락": "dn", "중립": "neutral"}
    return {"dir_cls": dir_map.get(prior["direction"], "neutral")}
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `python3 -m pytest scripts/test_build_us_tone.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_html.py scripts/test_build_us_tone.py
git commit -m "feat(us): build_us_tone() 추가 — 실측 신호를 dir_cls로 매핑"
```

---

### Task 2: US 렌더 컨텍스트에 `dir_cls` 주입

**Files:**
- Modify: `scripts/generate_html.py:955-965` (`elif internal_type == "us":` 블록)

- [ ] **Step 1: 현재 코드 확인**

`scripts/generate_html.py`의 `render_briefing()` 함수 내 US 분기(약 955~965행)는 현재 이렇다:

```python
    elif internal_type == "us":
        # 미국 이슈 중심 브리핑 — 예측 대신 오늘의 관점 + 이슈 카드. 성적표 사이드바 없음.
        ctx.update(build_issues(analysis))
        ctx.update(build_analyst_quotes(market_data))
        ctx["stock_picks"] = build_stock_picks(analysis, market_data, internal_type)
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["todays_view"] = analysis.get("todays_view")
        ctx["accuracy"] = False  # US 채점 탈퇴 — 성적표 사이드바 미표시
        tv = analysis.get("todays_view") or {}
        ctx["og_description"] = tv.get("view_title") or f"{target_date} 미국 시장 이슈 점검"
```

- [ ] **Step 2: `dir_cls` 계산 추가**

`ctx.update(build_issues(analysis))` 바로 다음 줄에 `ctx.update(build_us_tone(market_data))`를 추가한다 (Task 1에서 만든 함수 재사용, `market_data`는 이 함수가 이미 인자로 받는 `latest_us.json` 딕셔너리):

```python
    elif internal_type == "us":
        # 미국 이슈 중심 브리핑 — 예측 대신 오늘의 관점 + 이슈 카드. 성적표 사이드바 없음.
        ctx.update(build_issues(analysis))
        ctx.update(build_us_tone(market_data))
        ctx.update(build_analyst_quotes(market_data))
        ctx["stock_picks"] = build_stock_picks(analysis, market_data, internal_type)
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["todays_view"] = analysis.get("todays_view")
        ctx["accuracy"] = False  # US 채점 탈퇴 — 성적표 사이드바 미표시
        tv = analysis.get("todays_view") or {}
        ctx["og_description"] = tv.get("view_title") or f"{target_date} 미국 시장 이슈 점검"
```

- [ ] **Step 3: 코스피 렌더링 회귀 없는지 정적 확인**

`git diff scripts/generate_html.py`로 변경이 US 분기(`elif internal_type == "us":`) 안에만 있는지 확인한다. 코스피는 `else:` 분기의 `build_prediction()`이 여전히 `dir_cls`를 계산하므로 이번 변경과 무관하다.

Run: `git diff scripts/generate_html.py | grep "^+" | grep -v "build_us_tone"`
Expected: US 분기 관련 줄 외에 다른 변경 없음 (빈 결과 또는 방금 추가한 주석/코드 한 줄만).

- [ ] **Step 4: 커밋**

```bash
git add scripts/generate_html.py
git commit -m "feat(us): US 렌더 컨텍스트에 dir_cls 주입 (오늘의 관점 배경색용)"
```

---

### Task 3: CSS 규칙 추가 — `.tv-lead.dn`, `.tv-lead.neutral`

**Files:**
- Modify: `web/assets/style.css:1045-1048` (`.tv-lead` 블록 바로 아래)

- [ ] **Step 1: 현재 CSS 확인**

`web/assets/style.css` 1045~1048행 현재 상태:

```css
.tv-lead{background:linear-gradient(180deg,var(--primary-bg),transparent 70%);border:1px solid var(--primary-bg);border-radius:var(--r-lg);padding:20px 20px 22px;}
.tv-lead.up{background:linear-gradient(180deg,var(--up-bg),transparent 70%);border-color:var(--up-bg);}
.tv-kicker{font-size:11px;font-weight:800;letter-spacing:0.08em;color:var(--primary);text-transform:uppercase;margin-bottom:9px;}
.tv-lead.up .tv-kicker{color:var(--up);}
```

`--dn`·`--dn-bg`·`--surface-inset`·`--muted`는 이미 `:root`(라이트)·`.dark`(다크, 또는 미디어쿼리) 양쪽에 정의돼 있다(`web/assets/style.css:9-10`, 다크 테마 블록에도 동일 이름으로 존재) — 새 변수 정의 불필요.

- [ ] **Step 2: `.tv-lead.up` 다음 줄에 `.dn`·`.neutral` 규칙 추가**

```css
.tv-lead{background:linear-gradient(180deg,var(--primary-bg),transparent 70%);border:1px solid var(--primary-bg);border-radius:var(--r-lg);padding:20px 20px 22px;}
.tv-lead.up{background:linear-gradient(180deg,var(--up-bg),transparent 70%);border-color:var(--up-bg);}
.tv-lead.dn{background:linear-gradient(180deg,var(--dn-bg),transparent 70%);border-color:var(--dn-bg);}
.tv-lead.neutral{background:linear-gradient(180deg,var(--surface-inset),transparent 70%);border-color:var(--surface-inset);}
.tv-kicker{font-size:11px;font-weight:800;letter-spacing:0.08em;color:var(--primary);text-transform:uppercase;margin-bottom:9px;}
.tv-lead.up .tv-kicker{color:var(--up);}
.tv-lead.dn .tv-kicker{color:var(--dn);}
.tv-lead.neutral .tv-kicker{color:var(--muted);}
```

- [ ] **Step 3: 코스피 회귀 없는지 확인**

코스피의 `dir_cls`는 `build_prediction()`에서 `"up"` 또는 `""`(빈 문자열)만 반환하므로(`scripts/generate_html.py:170`), `.tv-lead.dn`·`.tv-lead.neutral` 규칙이 추가돼도 코스피 페이지에는 절대 매칭되지 않는다 — 코드 변경 없이 로직으로 확인.

Run: `grep -n 'dir_cls = ' scripts/generate_html.py`
Expected: `dir_cls = "up" if is_up else ("dn" if "하락" in direction else "")` 한 줄만 출력 — 코스피 쪽 `dir_cls`가 여전히 `up`/`dn`/`""` 중 하나만 반환함을 확인 (참고: 코스피의 `direction` 필드는 "상승 우위"/"하락 우위" 형태라 `"하락"` in direction이 항상 매칭돼 실질적으로 `""`(중립)는 코스피에서 거의 발생하지 않음 — 기존 동작 그대로 유지).

- [ ] **Step 4: 커밋**

```bash
git add web/assets/style.css
git commit -m "feat(us): tv-lead 하락/중립 배경색 CSS 규칙 추가"
```

---

### Task 4: 로컬 렌더로 3가지 케이스 시각 검증

**Files:**
- 없음 (검증 전용 태스크, 코드 변경 없음)

- [ ] **Step 1: 파이썬 3.9로 문법 호환 확인**

이 저장소의 `python3`는 3.9라 3.10+ 전용 문법(`X | None`)이 있는 스크립트는 직접 실행이 안 된다(과거 `fetch_data.py`에서 확인됨). `generate_html.py`는 3.9 호환 확인됨(Task 1~2 진행 중 `ast.parse`로 이미 검증). 실제 렌더는 아래처럼 `data/latest_us.json`을 임시로 편집해 3가지 케이스를 만든다.

- [ ] **Step 2: 상승 케이스 렌더**

```bash
cd "/Users/luke/Service App/double-shot"
cp data/latest_us.json /tmp/latest_us_backup.json
python3 -c "
import json
d = json.load(open('data/latest_us.json'))
d.setdefault('futures', {})
d['futures']['sp500_fut'] = {'change_pct': 0.8}
d['futures']['nasdaq_fut'] = {'change_pct': 1.2}
d['futures']['dow_fut'] = {'change_pct': 0.5}
d.setdefault('market_data_js', {})['sox'] = {'chg': 2.0}
d['vix'] = {'change_pct': -5.0}
json.dump(d, open('data/latest_us.json', 'w'), ensure_ascii=False, indent=2)
"
python3 scripts/generate_html.py --type us --date 2026-07-14 --data-file data/latest_us.json --force
grep -o 'open-section tv-lead [a-z]*' web/briefings/2026-07-14/us/index.html
```

Expected: `open-section tv-lead up` 출력.

- [ ] **Step 3: 하락 케이스 렌더**

```bash
python3 -c "
import json
d = json.load(open('data/latest_us.json'))
d['futures']['sp500_fut'] = {'change_pct': -0.8}
d['futures']['nasdaq_fut'] = {'change_pct': -1.2}
d['futures']['dow_fut'] = {'change_pct': -0.5}
d['market_data_js']['sox'] = {'chg': -2.5}
d['vix'] = {'change_pct': 8.0}
json.dump(d, open('data/latest_us.json', 'w'), ensure_ascii=False, indent=2)
"
python3 scripts/generate_html.py --type us --date 2026-07-14 --data-file data/latest_us.json --force
grep -o 'open-section tv-lead [a-z]*' web/briefings/2026-07-14/us/index.html
```

Expected: `open-section tv-lead dn` 출력.

- [ ] **Step 4: 중립 케이스 렌더**

```bash
python3 -c "
import json
d = json.load(open('data/latest_us.json'))
d['futures'] = {}
d['market_data_js']['sox'] = {}
d['vix'] = {}
json.dump(d, open('data/latest_us.json', 'w'), ensure_ascii=False, indent=2)
"
python3 scripts/generate_html.py --type us --date 2026-07-14 --data-file data/latest_us.json --force
grep -o 'open-section tv-lead [a-z]*' web/briefings/2026-07-14/us/index.html
```

Expected: `open-section tv-lead neutral` 출력.

- [ ] **Step 5: 원본 데이터 복구**

```bash
cp /tmp/latest_us_backup.json data/latest_us.json
python3 scripts/generate_html.py --type us --date 2026-07-14 --data-file data/latest_us.json --force
rm /tmp/latest_us_backup.json
```

이 스텝은 실제 서비스 데이터(`data/latest_us.json`, 그리고 재렌더된 `web/briefings/2026-07-14/us/index.html`)를 원상복구하는 것이 목적이다 — 검증용으로 임시 조작한 값을 라이브 브리핑에 남기지 않는다. 복구 후 `web/briefings/2026-07-14/us/index.html`이 검증 이전과 동일한지 `git diff --stat web/briefings/2026-07-14/us/index.html`로 확인하고, 차이가 있으면(예: `generated_at` 타임스탬프만 바뀌는 등) 커밋하지 않고 `git checkout -- web/briefings/2026-07-14/us/index.html`로 되돌린다.

- [ ] **Step 6: 브라우저로 라이트/다크 테마 시각 확인**

로컬 HTTP 서버로 `web/briefings/2026-07-14/us/index.html`을 열어 "오늘의 관점" 카드 배경색이 위 3가지 케이스에서 각각 붉은 계열/파란 계열/회색 계열로 보이는지 스크린샷으로 확인한다(Task 4 Step 2~4를 반복하며 매번 스크린샷). 다크 테마는 브라우저 리사이즈 툴의 `colorScheme: "dark"` 옵션으로 확인한다.

이 태스크는 코드를 남기지 않으므로 커밋할 것이 없다 — 검증만 하고 다음 태스크로 넘어간다.

---

## Self-Review Notes

- **스펙 커버리지**: 신호 소스 재사용(Task 1) · 계산 시점(Task 2, `market_data`는 렌더 시점 인자 재사용) · 매핑 규칙 3종(Task 1·3) · 적용 범위(템플릿 무변경, CSS만 추가 — Task 3) · 코스피 회귀 없음(Task 2·3 각각 확인 스텝) · 테스트 계획(Task 1 단위 테스트 + Task 4 렌더 확인) 모두 태스크로 커버됨.
- **범위 밖 항목**(이슈 카드 색상, 텔레그램, 채점 연동, 코스피 dir_cls 변경)은 어떤 태스크에서도 건드리지 않음 — 각 태스크의 diff가 스펙에 명시된 파일에만 한정됨.
- **타입 일관성**: `build_us_tone()` 반환값 `{"dir_cls": "up"|"dn"|"neutral"}`이 Task 1·2에서 동일하게 쓰임. 템플릿의 `{{ dir_cls }}` 변수명과도 일치(`sections/todays_view.html`, 수정 없음).
