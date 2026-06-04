# 산문 할루시네이션 검증 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `validate_analysis.py`에 픽 종목 실측 데이터와 산문 텍스트(reasons·scenario·watchpoints)를 교차검증하는 로직을 추가하고, 기존 브리핑 HTML을 소급 감사하는 스크립트를 작성한다.

**Architecture:** `enrich_picks_with_realdata()` 완료 후 `validate()` 내부에서 `validate_prose_against_picks()`를 호출한다. 픽에 이미 실측 `change_pct`가 채워져 있으므로 추가 API 호출 없음. 감사 스크립트는 독립 파일로 분리.

**Tech Stack:** Python 3.12, re, BeautifulSoup4 (감사 스크립트), 기존 `validate_analysis.py` 패턴 유지

---

## 파일 맵

| 파일 | 역할 |
|---|---|
| `scripts/validate_analysis.py` | 3개 함수 추가: `is_contradicted`, `_extract_change_claims`, `validate_prose_against_picks` |
| `scripts/audit_hallucinations.py` | 신규 — 기존 HTML 소급 감사 스크립트 |
| `tests/test_prose_validation.py` | 신규 — Task 1~3 단위 테스트 |

---

## Task 1: `is_contradicted()` — 불일치 판정 함수

**Files:**
- Modify: `scripts/validate_analysis.py` (기존 `find_forbidden` 함수 아래에 추가)
- Test: `tests/test_prose_validation.py`

- [ ] **Step 1: 테스트 파일 생성 및 실패 테스트 작성**

```python
# tests/test_prose_validation.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from validate_analysis import is_contradicted

def test_large_discrepancy_flagged():
    # AVGO 케이스: 실측 -0.49% vs 텍스트 +15.8%
    assert is_contradicted(15.8, -0.49) is True

def test_small_diff_passes():
    # +4.2% 텍스트 vs +4.0% 실측 → 허용 (5%p 이내)
    assert is_contradicted(4.2, 4.0) is False

def test_near_zero_real_uses_diff_only():
    # 실측 0.1% vs 텍스트 +10% → diff=9.9 > 5 → 차단
    assert is_contradicted(10.0, 0.1) is True

def test_near_zero_real_small_diff_passes():
    # 실측 0.1% vs 텍스트 +2% → diff=1.9 < 5 → 허용
    assert is_contradicted(2.0, 0.1) is False

def test_ratio_exactly_5x_flagged():
    # 실측 2% vs 텍스트 10% → ratio=5 → 차단
    assert is_contradicted(10.0, 2.0) is True

def test_ratio_below_5x_passes():
    # 실측 2% vs 텍스트 8% → diff=6>5 but ratio=4<5 → 허용
    assert is_contradicted(8.0, 2.0) is False
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd "/Users/luke/Service App/double-shot"
python -m pytest tests/test_prose_validation.py -v 2>&1 | head -20
```
Expected: `ImportError` 또는 `AttributeError: module 'validate_analysis' has no attribute 'is_contradicted'`

- [ ] **Step 3: `is_contradicted` 함수 구현**

`scripts/validate_analysis.py`에서 `find_forbidden()` 함수 정의 바로 아래에 추가:

```python
def is_contradicted(stated_pct: float, real_pct: float) -> bool:
    """산문에 기재된 % 수치가 실측 change_pct와 충돌하는지 판정.

    조건: diff > 5%p AND (실측 < 0.5% OR 배수 >= 5배)
    """
    diff = abs(stated_pct - real_pct)
    if diff <= 5.0:
        return False
    if abs(real_pct) < 0.5:
        return True
    return abs(stated_pct / real_pct) >= 5.0
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python -m pytest tests/test_prose_validation.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: 커밋**

```bash
git add scripts/validate_analysis.py tests/test_prose_validation.py
git commit -m "test+feat: is_contradicted() — 산문 % 불일치 판정 함수"
```

---

## Task 2: `_extract_change_claims()` — change claim 문장 추출

**Files:**
- Modify: `scripts/validate_analysis.py`
- Test: `tests/test_prose_validation.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_prose_validation.py`에 append:

```python
from validate_analysis import _extract_change_claims

def test_change_claim_detects_jeonil():
    # "전일 +X%" 패턴
    text = "전일 <b>+15.80%</b> 폭등하며 20일선 위로 강하게 치솟은 종목이에요."
    claims = _extract_change_claims(text)
    assert claims == [15.80]

def test_change_claim_detects_poldeung():
    # "+X% 폭등" 패턴
    text = "단 하루에 +15.8% 폭등했거든요."
    claims = _extract_change_claims(text)
    assert claims == [15.8]

def test_change_claim_ignores_ma():
    # "MA 대비 +X%" 는 change claim이 아님
    text = "20일선 대비 +11% 이상 상회 중인 종목이에요."
    claims = _extract_change_claims(text)
    assert claims == []

def test_change_claim_ignores_target():
    # "목표 +X%" 는 change claim이 아님
    text = "목표 +8.5% / 손절 -5.2%"
    claims = _extract_change_claims(text)
    assert claims == []

def test_change_claim_detects_geupnak():
    # "-X% 급락" 패턴
    text = "엔비디아(NVDA)는 -3.62% 급락했어요."
    claims = _extract_change_claims(text)
    assert claims == [-3.62]
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_prose_validation.py::test_change_claim_detects_jeonil -v
```
Expected: `AttributeError: module 'validate_analysis' has no attribute '_extract_change_claims'`

- [ ] **Step 3: `_extract_change_claims` 구현**

`scripts/validate_analysis.py`의 `is_contradicted` 바로 아래에 추가:

```python
# change claim 컨텍스트 키워드 — 일간 변동률을 서술하는 문장에서만 % 추출
_CHANGE_CTX_RE = re.compile(
    r'(?:'
    r'전일\s*[+-]?\d'           # "전일 +X%"
    r'|단\s*하루에'              # "단 하루에 +X%"
    r'|하루\s*만에'              # "하루 만에 +X%"
    r'|[+-]?\d[\d.]*\s*%\s*(?:폭등|급등|폭락|급락|상승|하락|올랐|떨어|빠졌)'  # "+X% 폭등"
    r'|(?:폭등|급등|폭락|급락|상승|하락)\s*[+-]?\d'  # "폭등 +X%"
    r')'
)
_PCT_RE = re.compile(r'([+-]?\d+\.?\d*)\s*%')


def _extract_change_claims(text: str) -> list:
    """산문 텍스트에서 '일간 변동률'을 서술하는 % 수치만 추출한다.
    MA 대비, 목표 수익률, 손절 % 등은 제외.
    """
    if not isinstance(text, str):
        return []
    t = strip_tags(text)
    results = []
    for m in _CHANGE_CTX_RE.finditer(t):
        # 매치 전후 30자 범위에서 % 수치 추출
        window = t[max(0, m.start() - 5): m.end() + 30]
        for pm in _PCT_RE.finditer(window):
            try:
                results.append(float(pm.group(1)))
            except ValueError:
                pass
    return results
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python -m pytest tests/test_prose_validation.py -v
```
Expected: 11 PASSED

- [ ] **Step 5: 커밋**

```bash
git add scripts/validate_analysis.py tests/test_prose_validation.py
git commit -m "test+feat: _extract_change_claims() — change claim 문장 % 추출"
```

---

## Task 3: `validate_prose_against_picks()` — 메인 산문 검증 함수

**Files:**
- Modify: `scripts/validate_analysis.py`
- Test: `tests/test_prose_validation.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
from validate_analysis import validate_prose_against_picks

def _make_pick(ticker, name, change_pct):
    return {"ticker": ticker, "name": name, "change_pct": change_pct,
            "price": "$100", "change": f"{change_pct:+.2f}%",
            "scenario": "", "action_guide": ""}

def test_removes_contradicted_reason():
    analysis = {
        "stock_picks": [_make_pick("AVGO", "AVGO (브로드컴)", -0.49)],
        "reasons": [
            "📈 선물이 약세예요.",
            "💡 브로드컴(AVGO)이 단 하루에 +15.8% 폭등했거든요.",
            "🌏 아시아 증시가 하락했어요.",
        ],
        "watch_items": [],
    }
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    assert len(analysis["reasons"]) == 2
    assert any("AVGO" in c for c in corrections)

def test_keeps_valid_reason():
    analysis = {
        "stock_picks": [_make_pick("META", "META (메타)", 4.24)],
        "reasons": ["META가 +4.2% 상승했어요."],
        "watch_items": [],
    }
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    assert len(analysis["reasons"]) == 1

def test_removes_contradicted_scenario_sentence():
    pick = _make_pick("AVGO", "AVGO (브로드컴)", -0.49)
    pick["scenario"] = "전일 +15.80% 폭등하며 20일선 위로 강하게 치솟은 종목이에요. 반도체 온기가 유입되고 있어요."
    analysis = {"stock_picks": [pick], "reasons": ["a", "b"], "watch_items": []}
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    scenario = analysis["stock_picks"][0]["scenario"]
    assert "+15.80%" not in scenario
    assert "반도체 온기" in scenario

def test_removes_contradicted_watchpoint():
    analysis = {
        "stock_picks": [_make_pick("AVGO", "AVGO (브로드컴)", -0.49)],
        "reasons": ["a", "b"],
        "watch_items": [
            {"icon": "💡", "label": "AVGO 모멘텀",
             "text": "브로드컴이 +15.8% 폭등했어요."},
            {"icon": "📅", "label": "NFP",
             "text": "내일 발표 예정이에요."},
        ],
    }
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    assert len(analysis["watch_items"]) == 1
    assert analysis["watch_items"][0]["label"] == "NFP"

def test_blocks_when_reasons_below_min():
    analysis = {
        "stock_picks": [_make_pick("AVGO", "AVGO (브로드컴)", -0.49)],
        "reasons": [
            "💡 AVGO +15.8% 폭등했어요.",  # 제거 대상
            "🌏 AVGO 단 하루에 +15.8% 급등했어요.",  # 제거 대상
        ],
        "watch_items": [],
    }
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    assert len(blocks) > 0

def test_skips_kospi_close():
    # kospi-close는 stock_picks 없음 → 아무것도 안 함
    analysis = {"reasons": ["테스트"], "watch_items": []}
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "kospi-close", corrections, warnings, blocks)
    assert corrections == [] and blocks == []
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
python -m pytest tests/test_prose_validation.py -k "test_removes_contradicted_reason" -v
```
Expected: `AttributeError: module 'validate_analysis' has no attribute 'validate_prose_against_picks'`

- [ ] **Step 3: `validate_prose_against_picks` 구현**

`scripts/validate_analysis.py`의 `_extract_change_claims` 바로 아래에 추가:

```python
def validate_prose_against_picks(analysis: dict, btype: str,
                                  corrections: list, warnings: list, blocks: list) -> None:
    """픽 실측 데이터와 reasons·scenario·watchpoints 산문을 교차검증한다.

    불일치 문장/항목을 제거하고 corrections에 기록.
    kospi-close는 stock_picks가 없으므로 skip.
    """
    if btype == "kospi-close":
        return

    picks = analysis.get("stock_picks")
    if not isinstance(picks, list) or not picks:
        return

    # 픽 실측 테이블 구성 (enrich 완료 후 change_pct가 float로 채워져 있음)
    ticker_real: dict = {}
    name_real: dict = {}
    for p in picks:
        chg = p.get("change_pct")
        if not isinstance(chg, (int, float)):
            continue
        tk = (p.get("ticker") or "").strip().upper()
        nm = (p.get("name") or "").strip()
        if tk:
            ticker_real[tk] = float(chg)
        if nm:
            name_real[nm] = float(chg)
        # 이름에서 짧은 식별자 추출: "AVGO (브로드컴)" → "AVGO", "브로드컴"
        parts = re.split(r'[\s()/·]', nm)
        for part in parts:
            part = part.strip()
            if len(part) >= 2:
                name_real.setdefault(part, float(chg))

    def real_chg_for_text(text: str):
        """텍스트에 언급된 픽 티커/이름을 찾아 실측 change_pct 반환. 없으면 None."""
        t = strip_tags(text)
        for tk, chg in ticker_real.items():
            if tk in t:
                return chg
        for nm, chg in sorted(name_real.items(), key=lambda x: -len(x[0])):
            if nm in t:
                return chg
        return None

    # ── reasons 검증 ──────────────────────────────────────────────
    reasons = analysis.get("reasons")
    if isinstance(reasons, list):
        kept = []
        for item in reasons:
            real = real_chg_for_text(item)
            if real is None:
                kept.append(item)
                continue
            # change claim % 추출 후 교차검증
            claims = _extract_change_claims(item)
            bad = [c for c in claims if is_contradicted(c, real)]
            if bad:
                corrections.append(
                    f"reasons 항목 제거 (실측 {real:+.2f}% vs 텍스트 {bad}): {item[:60]}"
                )
            else:
                kept.append(item)
        if len(kept) < REASONS_MIN:
            blocks.append(
                f"reasons가 {len(kept)}개로 과소 — prose 교정 후 부족 (최소 {REASONS_MIN})"
            )
        analysis["reasons"] = kept

    # ── 픽 scenario 검증 ──────────────────────────────────────────
    for pick in picks:
        scenario = pick.get("scenario") or ""
        if not scenario:
            continue
        chg = pick.get("change_pct")
        if not isinstance(chg, (int, float)):
            continue
        real = float(chg)
        # 문장 단위 분리 (마침표, 。, ！, ？ 기준)
        sentences = re.split(r'(?<=[.。!?])\s*', scenario)
        kept_sentences = []
        for sent in sentences:
            claims = _extract_change_claims(sent)
            bad = [c for c in claims if is_contradicted(c, real)]
            if bad:
                corrections.append(
                    f"픽 '{pick.get('name')}' scenario 문장 제거 "
                    f"(실측 {real:+.2f}% vs 텍스트 {bad}): {sent[:60]}"
                )
            else:
                kept_sentences.append(sent)
        new_scenario = " ".join(s for s in kept_sentences if s.strip())
        if not new_scenario.strip():
            warnings.append(f"픽 '{pick.get('name')}' scenario 전체 제거됨 — 수동 확인 필요")
        pick["scenario"] = new_scenario

    # ── watchpoints 검증 ─────────────────────────────────────────
    watch_key = "watch_items" if "watch_items" in analysis else "watchpoints"
    watch = analysis.get(watch_key)
    if isinstance(watch, list):
        kept = []
        for item in watch:
            text = item.get("text") or item.get("label") or ""
            real = real_chg_for_text(text)
            if real is None:
                kept.append(item)
                continue
            claims = _extract_change_claims(text)
            bad = [c for c in claims if is_contradicted(c, real)]
            if bad:
                corrections.append(
                    f"watchpoint 항목 제거 (실측 {real:+.2f}% vs 텍스트 {bad}): "
                    f"{item.get('label', '')}"
                )
            else:
                kept.append(item)
        analysis[watch_key] = kept
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
python -m pytest tests/test_prose_validation.py -v
```
Expected: 17 PASSED (Task 1 6 + Task 2 5 + Task 3 6)

- [ ] **Step 5: 커밋**

```bash
git add scripts/validate_analysis.py tests/test_prose_validation.py
git commit -m "test+feat: validate_prose_against_picks() — 산문 할루시네이션 교차검증"
```

---

## Task 4: `validate()` 호출 연결

**Files:**
- Modify: `scripts/validate_analysis.py:417-500` (`validate()` 함수 내부)

- [ ] **Step 1: `validate()` 내부 picks 처리 블록 직후에 호출 삽입**

`scripts/validate_analysis.py`의 `validate()` 함수에서 picks 처리 블록(`a["stock_picks"] = kept` 라인) 바로 다음에 추가:

현재 코드 (약 453~454번째 줄):
```python
        a["stock_picks"] = kept

    # 3) 계층 2 — 리스트형 본문
```

변경 후:
```python
        a["stock_picks"] = kept

    # 2-b) 산문 교차검증 — 픽 실측 vs reasons·scenario·watchpoints
    if btype in ("kospi", "us"):
        validate_prose_against_picks(a, btype, corrections, warnings, blocks)

    # 3) 계층 2 — 리스트형 본문
```

- [ ] **Step 2: 전체 테스트 실행**

```bash
python -m pytest tests/test_prose_validation.py -v
```
Expected: 17 PASSED

- [ ] **Step 3: 실제 파이프라인 dry-run (분석 파일이 있을 때)**

```bash
# 테스트용 dummy analysis 파일 생성 후 확인
python scripts/validate_analysis.py --type us 2>&1 | head -20
```
Expected: `[validate] ... 없음 — 검증 건너뜀` (분석 파일 없을 때) 또는 교정 로그 출력

- [ ] **Step 4: 커밋**

```bash
git add scripts/validate_analysis.py
git commit -m "feat: validate()에 validate_prose_against_picks() 호출 연결"
```

---

## Task 5: 소급 감사 스크립트 `audit_hallucinations.py`

**Files:**
- Create: `scripts/audit_hallucinations.py`

- [ ] **Step 1: 스크립트 작성**

```python
#!/usr/bin/env python3
# 기존 발행 브리핑 HTML에서 픽 badge % vs 산문 텍스트 % 불일치를 스캔한다.
"""
사용법: python3 scripts/audit_hallucinations.py
출력: [WARN] 날짜/타입  종목  badge=X%  location="텍스트 발췌"
"""
import re
import sys
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("pip install beautifulsoup4 후 실행하세요", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web" / "briefings"

# validate_analysis의 함수 재사용
sys.path.insert(0, str(ROOT / "scripts"))
from validate_analysis import is_contradicted, _extract_change_claims, strip_tags

PCT_RE = re.compile(r'([+-]?\d+\.?\d*)\s*%')


def parse_pct(text: str):
    """'+4.24%' → 4.24, '-0.49%' → -0.49, None if fail."""
    m = re.search(r'([+-]?\d+\.?\d*)\s*%', strip_tags(text or ""))
    return float(m.group(1)) if m else None


def audit_html(path: Path) -> list:
    """HTML 파일에서 불일치 항목을 찾아 리스트로 반환."""
    issues = []
    briefing_id = "/".join(path.parts[-4:-1])  # 예: 2026-06-04/us
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # 픽 카드 순회
    for card in soup.select(".stock-pick-card"):
        name_el = card.select_one(".stock-pick-card__name")
        chg_el = card.select_one(".stock-pick-card__change")
        scen_el = card.select_one(".stock-pick-card__scenario")
        if not (name_el and chg_el):
            continue

        name = name_el.get_text(strip=True)
        badge_pct = parse_pct(chg_el.get_text(strip=True))
        if badge_pct is None:
            continue

        # scenario 검사
        if scen_el:
            scen_text = scen_el.get_text()
            claims = _extract_change_claims(scen_text)
            for c in claims:
                if is_contradicted(c, badge_pct):
                    issues.append(
                        f"[WARN] {briefing_id}  {name}  "
                        f"badge={badge_pct:+.2f}%  scenario={c:+.2f}%  "
                        f"diff={abs(c-badge_pct):.2f}%p"
                    )

    # reasons 검사
    for li in soup.select(".reason-block li"):
        text = li.get_text()
        # 픽 이름/티커 매칭
        for card in soup.select(".stock-pick-card"):
            name_el = card.select_one(".stock-pick-card__name")
            chg_el = card.select_one(".stock-pick-card__change")
            if not (name_el and chg_el):
                continue
            badge_pct = parse_pct(chg_el.get_text(strip=True))
            if badge_pct is None:
                continue
            name = name_el.get_text(strip=True)
            # 이름 파트 중 하나가 텍스트에 있으면 매칭
            parts = [p.strip() for p in re.split(r'[\s()/·]', name) if len(p.strip()) >= 2]
            if any(p in text for p in parts):
                claims = _extract_change_claims(text)
                for c in claims:
                    if is_contradicted(c, badge_pct):
                        issues.append(
                            f"[WARN] {briefing_id}  {name}  "
                            f"badge={badge_pct:+.2f}%  reasons='{text[:80].strip()}'"
                        )
                        break

    return issues


def main():
    found = []
    for html_path in sorted(WEB_DIR.glob("**/index.html")):
        # kospi 아침, us 브리핑만
        parts = html_path.parts
        if len(parts) < 2:
            continue
        btype = parts[-2]
        if btype not in ("kospi", "us"):
            continue
        issues = audit_html(html_path)
        found.extend(issues)

    if not found:
        print("✅ 할루시네이션 의심 항목 없음")
    else:
        for issue in found:
            print(issue)
        print(f"\n총 {len(found)}건 발견 — 수동 확인 후 필요시 HTML 패치")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 스크립트 실행 확인**

```bash
cd "/Users/luke/Service App/double-shot"
pip install beautifulsoup4 -q
python3 scripts/audit_hallucinations.py
```
Expected: 출력 결과 확인 (이미 패치된 AVGO는 나오지 않아야 함)

- [ ] **Step 3: 커밋**

```bash
git add scripts/audit_hallucinations.py
git commit -m "feat: audit_hallucinations.py — 기존 브리핑 HTML 소급 감사 스크립트"
```

---

## Task 6: 전체 검증 & 최종 커밋

- [ ] **Step 1: 전체 테스트 실행**

```bash
python -m pytest tests/test_prose_validation.py -v
```
Expected: 17 PASSED, 0 FAILED

- [ ] **Step 2: 감사 스크립트 최종 실행**

```bash
python3 scripts/audit_hallucinations.py
```
Expected: 이슈 없거나, 있으면 목록 출력 후 수동 확인

- [ ] **Step 3: 최종 push**

```bash
git push
```

---

## 셀프 리뷰 체크리스트

| 항목 | 확인 |
|---|---|
| 스펙 섹션 2-1 (픽 실측 테이블) | Task 3 구현에 포함 ✅ |
| 스펙 섹션 2-2 (is_contradicted) | Task 1 ✅ |
| 스펙 섹션 2-3 (% 추출) | Task 2 ✅ |
| 스펙 섹션 2-4 reasons | Task 3 ✅ |
| 스펙 섹션 2-4 scenario | Task 3 ✅ |
| 스펙 섹션 2-4 watchpoints | Task 3 ✅ |
| 스펙 섹션 2-5 REASONS_MIN 가드 | Task 3 ✅ |
| 스펙 섹션 3 (kospi-close skip) | Task 3 테스트 포함 ✅ |
| 스펙 섹션 4 (감사 스크립트) | Task 5 ✅ |
| 스펙 섹션 6 테스트 기준 | Tasks 1~3에서 모두 커버 ✅ |
| watch_items vs watchpoints 키 차이 | Task 3에서 양쪽 처리 ✅ |
| 플레이스홀더(TBD/TODO) 없음 | ✅ |
