# 코스피 방향 prior 재보정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 시초가 방향 예측의 하락 편향을 교정한다 — 선행신호 prior를 SOX-heavy로 재가중하고, 비대칭 데드밴드를 도입하고, 이미 수집 중이나 미사용이던 USD/KRW 신호를 추가한다.

**Architecture:** 예측 방향은 `scripts/leading_signal.py`의 결정론적 prior가 좌우한다. 이 파일 하나만 외과적으로 고치고(신호 추출·가중치·밴드·표시), `scripts/diagnose_direction_signals.py` 백테스트 하네스를 회귀 게이트로 확장한다. 픽·HTML·프롬프트 파이프라인은 건드리지 않는다.

**Tech Stack:** Python 3.9, pytest, yfinance(백테스트 전용), pandas/numpy.

**설계 문서:** [docs/superpowers/specs/2026-07-05-kospi-prior-recalibration-design.md](../specs/2026-07-05-kospi-prior-recalibration-design.md)

---

## File Structure

- Modify: `scripts/leading_signal.py` — 신호 추출(`extract_signals`), 가중치(`SIGNAL_WEIGHTS`), 밴드(`compute_prior`), 표시(`format_prior_for_prompt`).
- Modify: `scripts/diagnose_direction_signals.py` — USD/KRW 다운로드·prior_score 반영, 밴드 결합prior 정확도·하락콜 정밀도 출력.
- Modify: `scripts/test_leading_signal.py` — 순수 함수 단위 테스트 (기존 파일에 append. ⚠️ `tests/` 아래에 같은 basename으로 새로 만들면 pytest 수집 충돌).

---

### Task 1: extract_signals에 USD/KRW 추가

**Files:**
- Modify: `scripts/leading_signal.py:28-34` (`extract_signals` 반환 dict)
- Modify: `scripts/test_leading_signal.py` (기존 파일에 append)

- [ ] **Step 1: 실패 테스트 작성**

`scripts/test_leading_signal.py` 생성:

```python
# 코스피 선행신호 prior 순수 함수 단위 테스트
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
import leading_signal as ls


def test_extract_signals_includes_usdkrw():
    latest = {
        "market_data_js": {"usd": {"chg": 0.5}, "sox": {"chg": 1.2}},
        "ewy": {"change_pct": -0.3},
    }
    sig = ls.extract_signals(latest)
    assert sig["usdkrw"] == 0.5
    assert sig["sox"] == 1.2
    assert sig["ewy"] == -0.3


def test_extract_signals_usdkrw_missing_is_none():
    sig = ls.extract_signals({"market_data_js": {}})
    assert sig["usdkrw"] is None
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_leading_signal.py -v`
Expected: FAIL — `KeyError: 'usdkrw'` (현재 `extract_signals`는 usdkrw 키를 반환하지 않음)

- [ ] **Step 3: 최소 구현**

`scripts/leading_signal.py`의 `extract_signals` 반환 dict에 usdkrw 한 줄 추가:

```python
    return {
        "sox":    from_mdj("sox"),
        "nasdaq": from_mdj("nasdaq"),
        "nq":     from_mdj("nq"),
        "ewy":    from_top("ewy"),
        "vix":    from_top("vix"),
        "usdkrw": from_mdj("usd"),   # market_data_js.usd.chg (원/달러 등락률, 원화 약세=하락 압력)
    }
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_leading_signal.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/leading_signal.py scripts/test_leading_signal.py
git commit -m "feat(예측): 선행신호 prior에 USD/KRW 신호 추출 추가"
```

---

### Task 2: 가중치 재보정 + 비대칭 데드밴드

**Files:**
- Modify: `scripts/leading_signal.py:9-10` (`SIGNAL_WEIGHTS`, `NEUTRAL_BAND`)
- Modify: `scripts/leading_signal.py:69-74` (`compute_prior` 판정부)
- Modify: `scripts/test_leading_signal.py`

- [ ] **Step 1: 실패 테스트 작성**

`scripts/test_leading_signal.py`에 아래 테스트를 추가 (기존 코드 기준으로 실패해야 함):

```python
def test_up_band_lowered():
    # sox +0.3 → 신규 가중 1.5*0.3=0.45 > UP_BAND(0.3) → 상승
    #           (구 로직: 1.0*0.3=0.3, NEUTRAL_BAND 0.5 미만 → 중립)
    latest = {"market_data_js": {"sox": {"chg": 0.3}}}
    assert ls.compute_prior(latest)["direction"] == "상승"


def test_mild_negative_is_neutral_not_down():
    # sox -0.6 → 신규 1.5*-0.6=-0.9, DN_BAND(-1.2)보다 위 → 중립
    #           (구 로직: 1.0*-0.6=-0.6 < -0.5 → 하락. 이 하락 편향이 교정 대상)
    latest = {"market_data_js": {"sox": {"chg": -0.6}}}
    assert ls.compute_prior(latest)["direction"] == "중립"


def test_strong_negative_is_down():
    # sox -1.0 → 1.5*-1.0=-1.5 < DN_BAND(-1.2) → 하락
    latest = {"market_data_js": {"sox": {"chg": -1.0}}}
    assert ls.compute_prior(latest)["direction"] == "하락"


def test_usdkrw_weakening_pushes_down():
    # 원화 약세(usd +2.0)만 있어도 -0.8*2.0=-1.6 < -1.2 → 하락
    #  (구 로직: usdkrw 가중치 없음 → score 0 → 중립)
    latest = {"market_data_js": {"usd": {"chg": 2.0}}}
    assert ls.compute_prior(latest)["direction"] == "하락"
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_leading_signal.py -v`
Expected: FAIL — `test_up_band_lowered`, `test_mild_negative_is_neutral_not_down`, `test_usdkrw_weakening_pushes_down` 3건 실패 (`test_strong_negative_is_down`은 구·신 로직 모두 하락이라 통과할 수 있음)

- [ ] **Step 3: 최소 구현 — 가중치·밴드 상수 교체**

`scripts/leading_signal.py:9-10`의 두 줄을 교체:

```python
# 진단 기반 재보정값 — 백테스트(diagnose_direction_signals.py)로 확정
SIGNAL_WEIGHTS = {"sox": 1.5, "nasdaq": 0.5, "nq": 0.3, "ewy": 0.3, "vix": -0.2, "usdkrw": -0.8}
# 비대칭 데드밴드: 상승 드리프트(base 63% up)를 내장 — 하락 판정에 더 강한 음의 증거를 요구.
# 레짐 전환(하락장) 시 DN_BAND 재점검 필요.
UP_BAND =  0.3    # score >  UP_BAND → 상승
DN_BAND = -1.2    # score <  DN_BAND → 하락, 그 사이는 중립
```

- [ ] **Step 4: 최소 구현 — compute_prior 판정부 교체**

`scripts/leading_signal.py`의 `compute_prior` 내부 판정부 (현재 `if score > NEUTRAL_BAND:` … `else: direction = "중립"`)를 교체:

```python
    if score > UP_BAND:
        direction = "상승"
    elif score < DN_BAND:
        direction = "하락"
    else:
        direction = "중립"
```

- [ ] **Step 5: 통과 확인**

Run: `python3 -m pytest scripts/test_leading_signal.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: NEUTRAL_BAND 잔존 참조 없음 확인**

Run: `grep -n "NEUTRAL_BAND\b" scripts/leading_signal.py`
Expected: 코스피 쪽 참조 0건 (미국 prior의 `NEUTRAL_BAND_US`만 남아야 함 — 이 상수는 유지). 만약 코스피 `NEUTRAL_BAND` 참조가 남아 있으면 제거.

- [ ] **Step 7: 커밋**

```bash
git add scripts/leading_signal.py scripts/test_leading_signal.py
git commit -m "fix(예측): 코스피 prior SOX-heavy 재가중 + 비대칭 데드밴드로 하락 편향 교정"
```

---

### Task 3: 프롬프트 표시에 USD/KRW 한 줄 추가

**Files:**
- Modify: `scripts/leading_signal.py:91-92` (`format_prior_for_prompt` 신호 표시 줄)
- Modify: `scripts/test_leading_signal.py`

- [ ] **Step 1: 실패 테스트 작성**

`scripts/test_leading_signal.py`에 추가:

```python
def test_format_prior_shows_usdkrw():
    prior = ls.compute_prior({"market_data_js": {"sox": {"chg": 1.0}, "usd": {"chg": 0.4}}})
    text = ls.format_prior_for_prompt(prior)
    assert "원/달러" in text
    assert "+0.40%" in text
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_leading_signal.py::test_format_prior_shows_usdkrw -v`
Expected: FAIL — `assert "원/달러" in text` (현재 표시 줄에 원/달러 없음)

- [ ] **Step 3: 최소 구현**

`format_prior_for_prompt`의 신호 표시 줄(SOX·나스닥·NQ선물·EWY·VIX)에 원/달러를 삽입:

```python
        f"- SOX {fmt(sig.get('sox'))} · 나스닥 {fmt(sig.get('nasdaq'))} · NQ선물 {fmt(sig.get('nq'))} "
        f"· EWY {fmt(sig.get('ewy'))} · 원/달러 {fmt(sig.get('usdkrw'))} · VIX {fmt(sig.get('vix'))}",
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_leading_signal.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/leading_signal.py scripts/test_leading_signal.py
git commit -m "feat(예측): prior 프롬프트 블록에 원/달러 신호 표시 추가"
```

---

### Task 4: 백테스트 하네스 확장 + 회귀 게이트 검증

**Files:**
- Modify: `scripts/diagnose_direction_signals.py:22` (import), `:28-34` (`US_TICKERS`), `:77-82` (`prior_score`), `:90` 이후(밴드 결합prior 출력)

- [ ] **Step 1: import에 밴드 상수 추가**

`scripts/diagnose_direction_signals.py:22`를 교체:

```python
from leading_signal import SIGNAL_WEIGHTS, UP_BAND, DN_BAND
```

- [ ] **Step 2: US_TICKERS에 USD/KRW 추가**

`US_TICKERS` dict에 한 줄 추가:

```python
US_TICKERS = {
    "^IXIC": "nasdaq",
    "^GSPC": "sp500",
    "^SOX": "sox",
    "EWY": "ewy",
    "^VIX": "vix",
    "USDKRW=X": "usdkrw",
}
```

- [ ] **Step 3: prior_score에 USD/KRW 항 추가**

`merged["prior_score"] = (...)` 계산에 usdkrw 항을 추가. USD/KRW는 주말 데이터가 섞여 결측이 날 수 있으므로 `dropna`에 넣지 않고 `.fillna(0)`으로 처리:

```python
    merged["prior_score"] = (
        SIGNAL_WEIGHTS["sox"] * merged["sox"]
        + SIGNAL_WEIGHTS["ewy"] * merged["ewy"]
        + SIGNAL_WEIGHTS["nasdaq"] * merged["nasdaq"]
        + SIGNAL_WEIGHTS["vix"] * merged["vix"]
        + SIGNAL_WEIGHTS["usdkrw"] * merged["usdkrw"].fillna(0)
    )
```

- [ ] **Step 4: 밴드 결합prior 정확도·하락콜 정밀도 출력 추가**

`truth = np.sign(merged["kospi"])`가 정의된 직후(rules dict 생성 부근)에 아래 블록을 추가한다. 프로덕션 `compute_prior`와 동일한 비대칭 밴드 의미(중립→상승 드리프트)로 예측을 만들고 정확도·하락콜 정밀도를 출력한다:

```python
    # ── 밴드 적용 결합prior (프로덕션 compute_prior와 동일 의미) ──
    banded = np.where(merged["prior_score"] > UP_BAND, 1,
                      np.where(merged["prior_score"] < DN_BAND, -1, 1))  # 중립→상승(드리프트)
    banded = pd.Series(banded, index=merged.index)
    band_acc = (banded == truth).mean() * 100
    dncall = banded == -1
    dnprec = (truth[dncall] == -1).mean() * 100 if int(dncall.sum()) else float("nan")
    print(f"\n밴드결합prior  적중 {band_acc:.1f}%  하락콜 {int(dncall.sum())}건 정밀도 {dnprec:.0f}%")
```

- [ ] **Step 5: 백테스트 실행 — 성공 기준 확인**

Run: `python3 scripts/diagnose_direction_signals.py 2026-03-01`

Expected (성공 기준 — 라이브 yfinance 데이터라 수치는 소폭 변동 가능):
- `SOX부호` ≈ 68% 부근.
- `결합prior`(부호) 가 `SOX부호`보다 **낮지 않을 것** (재가중 효과).
- `밴드결합prior 적중` **≥ 67%** (목표 ≈69%), 현행 65.5% 대비 상승.
- `밴드결합prior … 정밀도` **≥ 58%** (목표 ≈61%).
- `[출시 게이트] … → PASS` 유지.

미충족 시: 설계 §3.2 가중치(SOX 1.3~1.7, usdkrw -0.6~-1.0)·§3.3 밴드(DN_BAND -1.0~-1.4)를 표본 내에서 재조정하되 소수점 과최적화 금지. 조정 후 Task 2 단위 테스트가 여전히 PASS인지 재확인.

- [ ] **Step 6: 전체 테스트 재확인**

Run: `python3 -m pytest scripts/test_leading_signal.py -v`
Expected: PASS (7 passed) — 가중치 재조정이 있었다면 경계 테스트 값이 여전히 유효한지 확인.

- [ ] **Step 7: 커밋**

```bash
git add scripts/diagnose_direction_signals.py
git commit -m "test(예측): 백테스트 하네스에 USD/KRW·밴드 결합prior 회귀 게이트 추가"
```

---

## 배포 유의

- 푸시·배포는 사용자 지시 시에만. `git push` 시 `deploy.yml`이 자동 배포된다.
- 실측 효과는 배포 후 `data/briefings.json` 채점 누적으로 재확인한다(in-sample 개선폭보다 작을 수 있음).
- 범위 밖(이번 계획 제외): 토큰 지수(중기 confidence 톤 별도 건), 대만 TWII, 사후 캘리브레이션 레이어, USD/KRW를 `_strength` strong 게이트에 반영.
