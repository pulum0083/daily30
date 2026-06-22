# 코스피 방향 — 선행신호 prior 보정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 시초가 브리핑의 방향 예측에 결정론적 선행신호(SOX·EWY·VIX·나스닥·선물) prior를 도입해, 전일 국내 등락 앵커링(모멘텀, 적중률 50%)으로 V반등을 놓치던 문제를 보정한다.

**Architecture:** ① `leading_signal.py` 순수 함수가 `latest_kospi.json`에서 prior(방향·강도)를 계산한다. ② `call_claude.py`가 매 kospi 생성 시 prior를 프롬프트에 주입한다(1차 교정 + SOX·선물 누락 갭 보완). ③ `validate_analysis.py`가 prior를 독립 재계산해, LLM 방향이 **strong prior와 정반대**면 `call_claude --force-direction`으로 1회 재생성(백스톱) + 관리자 알림. ④ 백테스트 하니스로 가중치·임계값을 확정하고 출시 게이트로 쓴다.

**Tech Stack:** Python 3.9, pytest, yfinance(백테스트), 기존 anthropic SDK 파이프라인.

---

## File Structure

- **Create** `scripts/leading_signal.py` — prior 계산 순수 함수 + 프롬프트 포맷터. 외부 의존성 없음.
- **Create** `scripts/test_leading_signal.py` — 단위 테스트(기존 `scripts/test_*.py` 컨벤션).
- **Modify** `scripts/call_claude.py` — kospi 프롬프트에 prior 주입 + `--force-direction` 인자.
- **Modify** `scripts/validate_analysis.py` — strong prior 모순 시 재생성 오버라이드 + 관리자 알림.
- **Modify** `scripts/diagnose_direction_signals.py` — 인라인 prior를 `leading_signal.compute_prior`로 교체하고 출시 기준 요약 출력.

용어: prior 방향은 `"상승"|"하락"|"중립"`. analysis의 `prediction.direction`은 `"상승 우위"|"하락 우위"` 등 → 비교는 부분 문자열(`"상승"`/`"하락"` 포함 여부)로 한다.

---

### Task 1: `leading_signal.py` — prior 계산 순수 함수

**Files:**
- Create: `scripts/leading_signal.py`
- Test: `scripts/test_leading_signal.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`scripts/test_leading_signal.py`:

```python
# 선행신호 prior 계산 단위 테스트
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leading_signal as ls


def _latest(sox=None, nasdaq=None, nq=None, ewy=None, vix=None):
    """latest_kospi.json 구조 일부를 흉내낸 fixture (SOX·나스닥·NQ는 market_data_js, EWY·VIX는 최상위)."""
    return {
        "market_data_js": {
            "sox": {"chg": sox} if sox is not None else {},
            "nasdaq": {"chg": nasdaq} if nasdaq is not None else {},
            "nq": {"chg": nq} if nq is not None else {},
        },
        "ewy": {"change_pct": ewy} if ewy is not None else {},
        "vix": {"change_pct": vix} if vix is not None else {},
    }


def test_extract_signals_mixed_paths():
    sig = ls.extract_signals(_latest(sox=5.61, nasdaq=0.86, nq=0.5, ewy=5.96, vix=-12.04))
    assert sig["sox"] == 5.61
    assert sig["nasdaq"] == 0.86
    assert sig["nq"] == 0.5
    assert sig["ewy"] == 5.96
    assert sig["vix"] == -12.04


def test_missing_fields_are_none():
    sig = ls.extract_signals({"market_data_js": {}})
    assert sig["sox"] is None and sig["ewy"] is None


def test_strong_up_reversal_6_09():
    # 6/09 아침: EWY +5.96, SOX +5.61, VIX -12 → 강한 상승 prior
    p = ls.compute_prior(_latest(sox=5.61, nasdaq=0.86, nq=0.5, ewy=5.96, vix=-12.04))
    assert p["direction"] == "상승"
    assert p["strength"] == "strong"


def test_weak_signal_no_strong_6_15():
    # 6/15 아침: EWY -0.75, SOX +1.52 (부호 불일치·약신호) → strong 아님
    p = ls.compute_prior(_latest(sox=1.52, nasdaq=0.3, nq=0.2, ewy=-0.75, vix=-9.05))
    assert p["strength"] != "strong"


def test_strong_down():
    # EWY -14.11, SOX -10.26, VIX +39.7 → 강한 하락 prior
    p = ls.compute_prior(_latest(sox=-10.26, nasdaq=-4.18, nq=-2.0, ewy=-14.11, vix=39.68))
    assert p["direction"] == "하락"
    assert p["strength"] == "strong"


def test_neutral_when_no_signals():
    p = ls.compute_prior({"market_data_js": {}})
    assert p["direction"] == "중립"
    assert p["strength"] == "weak"


def test_vix_contradiction_blocks_strong():
    # 상승 prior인데 VIX 급등(+15%) → 강한 모순 → strong 강등
    p = ls.compute_prior(_latest(sox=4.0, nasdaq=1.0, nq=0.5, ewy=4.0, vix=15.0))
    assert p["strength"] != "strong"


def test_format_prior_for_prompt_contains_values():
    p = ls.compute_prior(_latest(sox=5.61, nasdaq=0.86, nq=0.5, ewy=5.96, vix=-12.04))
    text = ls.format_prior_for_prompt(p)
    assert "상승" in text and "SOX" in text and "5.61" in text
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -m pytest scripts/test_leading_signal.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leading_signal'`

- [ ] **Step 3: 최소 구현**

`scripts/leading_signal.py`:

```python
# 코스피 시초가 방향 예측용 선행신호 prior를 결정론적으로 계산하는 순수 모듈
"""
latest_kospi.json의 선행신호 등락률에서 방향 prior(상승/하락/중립)와 강도를 계산한다.
SOX·나스닥·NQ선물은 market_data_js.*.chg, EWY·VIX는 최상위 *.change_pct 에 있다.
가중치·임계값은 scripts/diagnose_direction_signals.py 백테스트로 확정한다(초기값은 74일 진단 기반).
"""

# 진단 기반 초기값 — 백테스트로 확정
SIGNAL_WEIGHTS = {"sox": 1.0, "ewy": 1.0, "nasdaq": 0.4, "nq": 0.3, "vix": -0.2}
NEUTRAL_BAND = 0.5   # |score| < band → 중립
T_EWY = 3.5          # strong 자격 EWY 임계 (%)
T_SOX = 3.0          # strong 자격 SOX 임계 (%)
VIX_CONTRA = 10.0    # 방향과 반대인 VIX 급변동(%) → strong 강등


def extract_signals(latest: dict) -> dict:
    """latest_kospi.json에서 선행신호 등락률을 추출. 누락 필드는 None."""
    mdj = latest.get("market_data_js") or {}

    def from_mdj(key):   # market_data_js.{key}.chg
        v = mdj.get(key)
        return v.get("chg") if isinstance(v, dict) else None

    def from_top(key):   # 최상위 {key}.change_pct
        v = latest.get(key)
        return v.get("change_pct") if isinstance(v, dict) else None

    return {
        "sox":    from_mdj("sox"),
        "nasdaq": from_mdj("nasdaq"),
        "nq":     from_mdj("nq"),
        "ewy":    from_top("ewy"),
        "vix":    from_top("vix"),
    }


def _strength(sig: dict, direction: str) -> str:
    sox, ewy, vix = sig.get("sox"), sig.get("ewy"), sig.get("vix")
    if direction == "중립" or sox is None or ewy is None or sox == 0 or ewy == 0:
        return "weak"
    agree = (sox > 0) == (ewy > 0)
    if not agree:
        return "weak"
    vix_contra = vix is not None and (
        (direction == "상승" and vix > VIX_CONTRA) or
        (direction == "하락" and vix < -VIX_CONTRA)
    )
    if (abs(ewy) >= T_EWY or abs(sox) >= T_SOX) and not vix_contra:
        return "strong"
    return "mid"


def compute_prior(latest: dict) -> dict:
    """선행신호 prior 계산.

    Returns: {"direction": "상승"|"하락"|"중립", "score": float,
              "strength": "strong"|"mid"|"weak", "signals": {...}}
    """
    sig = extract_signals(latest)
    score = 0.0
    used = False
    for key, w in SIGNAL_WEIGHTS.items():
        v = sig.get(key)
        if v is not None:
            score += w * v
            used = True
    if not used:
        return {"direction": "중립", "score": 0.0, "strength": "weak", "signals": sig}
    if score > NEUTRAL_BAND:
        direction = "상승"
    elif score < -NEUTRAL_BAND:
        direction = "하락"
    else:
        direction = "중립"
    return {
        "direction": direction,
        "score": round(score, 3),
        "strength": _strength(sig, direction),
        "signals": sig,
    }


def format_prior_for_prompt(prior: dict) -> str:
    """prior를 LLM 프롬프트에 주입할 한국어 텍스트 블록으로 포맷."""
    sig = prior["signals"]
    def fmt(v):
        return f"{v:+.2f}%" if isinstance(v, (int, float)) else "—"
    lines = [
        "\n## 🧭 선행신호 방향 prior (Python 결정론 계산 — 우선 참고)",
        f"- 계산 방향: **{prior['direction']}** (강도 {prior['strength']}, score {prior['score']})",
        f"- SOX {fmt(sig.get('sox'))} · 나스닥 {fmt(sig.get('nasdaq'))} · NQ선물 {fmt(sig.get('nq'))} "
        f"· EWY {fmt(sig.get('ewy'))} · VIX {fmt(sig.get('vix'))}",
        "- 이 값들은 직전 미국장 종가로, 전일 한국 마감 **이후** 정보를 반영한다.",
        "- **충돌 해소 규칙**: 전일 코스피가 ±3% 이상 크게 움직인 다음날, 위 선행신호가 전일 국내 방향과 "
        "모순되면 — 더 신선한 정보이므로 — **선행신호(prior) 방향을 따른다.** 전일 국내 등락에 앵커링하지 않는다.",
    ]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -m pytest scripts/test_leading_signal.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: 커밋**

```bash
cd "/Users/luke/Service App/double-shot"
git add scripts/leading_signal.py scripts/test_leading_signal.py
git commit -m "feat(방향 보정): 선행신호 prior 계산 모듈 + 단위 테스트"
```

---

### Task 2: 백테스트 하니스에 모듈 연결 (출시 게이트)

**Files:**
- Modify: `scripts/diagnose_direction_signals.py` (인라인 prior → `leading_signal.compute_prior`)

- [ ] **Step 1: 인라인 prior_score를 모듈 호출로 교체**

`scripts/diagnose_direction_signals.py`에서 `merged["prior_score"] = (...)` 블록을 제거하고, 각 행의 신호를 `leading_signal` 가중치로 계산하도록 바꾼다. 파일 상단 import에 추가:

```python
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from leading_signal import SIGNAL_WEIGHTS
```

`prior_score` 계산을 모듈 가중치로 통일:

```python
    merged["prior_score"] = (
        SIGNAL_WEIGHTS["sox"] * merged["sox"]
        + SIGNAL_WEIGHTS["ewy"] * merged["ewy"]
        + SIGNAL_WEIGHTS["nasdaq"] * merged["nasdaq"]
        + SIGNAL_WEIGHTS["vix"] * merged["vix"]
    )
```

(주의: 백테스트는 복원 가능한 종가 신호만 쓰므로 NQ선물 항은 제외 — 라이브 prior와의 차이를 파일 주석에 명시.)

- [ ] **Step 2: 출시 기준 한 줄 요약 출력 추가**

`main()` 말미에 결합 prior가 모멘텀 베이스라인을 상회하는지 PASS/FAIL 한 줄을 출력:

```python
    prior_hit, _, _ = hit(rules["결합prior"])
    mom_hit, _, _ = hit(rules["모멘텀(전일)"])
    verdict = "PASS" if prior_hit > mom_hit + 5 else "FAIL"
    print(f"\n[출시 게이트] 결합prior {prior_hit:.1f}% vs 모멘텀 {mom_hit:.1f}% → {verdict}")
```

- [ ] **Step 3: 실행해 회귀 없는지 확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 scripts/diagnose_direction_signals.py 2026-03-01 2>&1 | tail -5`
Expected: 표본·적중률 출력 + 마지막 줄 `[출시 게이트] ... → PASS` (결합prior 67%대 > 모멘텀 50%)

- [ ] **Step 4: 커밋**

```bash
cd "/Users/luke/Service App/double-shot"
git add scripts/diagnose_direction_signals.py
git commit -m "feat(방향 보정): 백테스트 하니스를 prior 모듈에 연결 + 출시 게이트 판정"
```

---

### Task 3: `call_claude.py` — prior 프롬프트 주입 + `--force-direction`

**Files:**
- Modify: `scripts/call_claude.py` — `call_claude()` 시그니처(1061행), 프롬프트 조립부(1097행 근처), `main()` 인자(1244행 근처)·호출부(1285행 근처)

- [ ] **Step 1: prior 주입 — `call_claude()` 시그니처와 본문 수정**

`scripts/call_claude.py:1061` 의 함수 시그니처를 다음으로 변경:

```python
def call_claude(briefing_type: str, date_str: str, force_direction: str | None = None) -> dict:
```

같은 함수 안, 뉴스 요약을 붙이는 줄(현재 1099-1100행 `if news_summary:` 블록) **직후**에 prior 주입 블록을 추가:

```python
    # 선행신호 방향 prior 주입 (kospi 전용) — SOX·선물 등 market_data_js 누락 신호도 함께 전달
    if briefing_type == "kospi":
        from leading_signal import compute_prior, format_prior_for_prompt
        prior = compute_prior(market_data)
        user_content += format_prior_for_prompt(prior)
        print(f"[call_claude] Leading-signal prior: {prior['direction']} ({prior['strength']}, score {prior['score']})")
```

(주의: `compute_prior`는 `market_data` 전체를 받는다 — `analysis_data`가 아니다. `market_data`에 `market_data_js`가 살아 있어야 SOX·나스닥·NQ를 읽을 수 있다.)

- [ ] **Step 2: `--force-direction` 강제 지시 블록 추가**

Step 1에서 추가한 prior 주입 블록 **다음에** 이어서:

```python
    # 검증게이트 오버라이드 재생성용 — 방향 강제 (validate_analysis가 --force-direction으로 재호출)
    if force_direction:
        user_content += (
            f"\n## ⛔ 방향 강제 지시 (필수)\n"
            f"이번 브리핑의 `prediction.direction`은 반드시 **{force_direction}**로 한다. "
            f"reasons·reason_title·telegram_signals 등 모든 본문을 이 방향과 일관되게 작성한다. "
            f"선행신호 prior가 전일 국내 등락보다 우선한다는 판단에 따른 강제다.\n"
        )
        print(f"[call_claude] ⛔ force_direction = {force_direction}")
```

- [ ] **Step 3: `main()`에 CLI 인자·호출 연결**

`scripts/call_claude.py` main()의 argparse 블록(현재 `--render` 추가 직후, 1247행 근처)에 추가:

```python
    parser.add_argument(
        "--force-direction", default=None,
        help="prediction.direction 강제 (검증게이트 오버라이드 재생성용)",
    )
```

그리고 비-render 흐름의 호출부(현재 1285행 `analysis = call_claude(args.type, date_str)`)를 변경:

```python
        analysis = call_claude(args.type, date_str, force_direction=args.force_direction)
```

- [ ] **Step 4: 컴파일·스모크 확인 (API 미호출)**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -c "import sys; sys.path.insert(0,'scripts'); import call_claude; import inspect; print('force_direction' in inspect.signature(call_claude.call_claude).parameters)"`
Expected: `True`

(전체 생성은 API 키·시장데이터가 필요하므로 통합 단계(Task 5)에서 dry-run.)

- [ ] **Step 5: 커밋**

```bash
cd "/Users/luke/Service App/double-shot"
git add scripts/call_claude.py
git commit -m "feat(방향 보정): kospi 프롬프트 선행신호 prior 주입 + --force-direction"
```

---

### Task 4: `validate_analysis.py` — strong prior 모순 시 재생성 오버라이드

**Files:**
- Modify: `scripts/validate_analysis.py` — `main()` (현재 1004행 근처, `result = validate(...)` 이후)
- Test: `scripts/test_leading_signal.py` (모순 판정 헬퍼 테스트 추가)

오버라이드는 **kospi 전용**, **strong prior가 LLM 방향과 정반대**일 때만 발동한다. 발동 시 `call_claude.py --type kospi --no-html --force-direction <prior>` 를 서브프로세스로 1회 재호출해 일관된 산문으로 재생성하고, 재생성본을 다시 검증한 뒤 관리자 알림을 보낸다.

- [ ] **Step 1: 모순 판정 헬퍼 테스트 작성**

`scripts/test_leading_signal.py` 끝에 추가:

```python
def test_direction_contradicts_strong():
    assert ls.prior_contradicts_direction({"direction": "상승", "strength": "strong"}, "하락 우위") is True
    assert ls.prior_contradicts_direction({"direction": "상승", "strength": "strong"}, "상승 우위") is False
    # mid 강도는 오버라이드 비대상
    assert ls.prior_contradicts_direction({"direction": "상승", "strength": "mid"}, "하락 우위") is False
    # 중립 prior는 비대상
    assert ls.prior_contradicts_direction({"direction": "중립", "strength": "strong"}, "하락 우위") is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -m pytest scripts/test_leading_signal.py::test_direction_contradicts_strong -q`
Expected: FAIL — `AttributeError: module 'leading_signal' has no attribute 'prior_contradicts_direction'`

- [ ] **Step 3: 헬퍼 구현 (`leading_signal.py`에 추가)**

`scripts/leading_signal.py` 끝에 추가:

```python
def prior_contradicts_direction(prior: dict, llm_direction: str) -> bool:
    """strong prior가 LLM 방향과 정반대인지. (오버라이드 발동 조건)"""
    if prior.get("strength") != "strong":
        return False
    pd = prior.get("direction")
    if pd == "상승" and "하락" in (llm_direction or ""):
        return True
    if pd == "하락" and "상승" in (llm_direction or ""):
        return True
    return False
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -m pytest scripts/test_leading_signal.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: `validate_analysis.py` main()에 오버라이드 단계 추가**

`scripts/validate_analysis.py`의 `main()`에서 `result = validate(analysis, latest, btype)` 와 그 아래 `result["corrections"] = ...` 사이(현재 1005행 근처)에 삽입:

```python
    # 4-b) 선행신호 prior 오버라이드 (kospi 전용) — strong prior가 LLM 방향과 정반대면 재생성
    if btype == "kospi":
        import subprocess
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from leading_signal import compute_prior, prior_contradicts_direction
        prior = compute_prior(latest)
        llm_dir = (result["analysis"].get("prediction") or {}).get("direction", "")
        if prior_contradicts_direction(prior, llm_dir):
            print(f"[validate] 🧭 선행신호 오버라이드: LLM '{llm_dir}' ↔ strong prior '{prior['direction']}' "
                  f"(score {prior['score']}) — {prior['direction']}로 재생성", file=sys.stderr)
            # 교정본을 먼저 저장(재호출이 analysis_kospi.json을 다시 읽지 않도록은 아님 — 재호출이 새로 생성해 덮어씀)
            regen = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "call_claude.py"),
                 "--type", "kospi", "--no-html", "--force-direction", prior["direction"]],
            )
            if regen.returncode == 0:
                analysis = load_json(analysis_path)          # 재생성본 로드
                result = validate(analysis, latest, btype)   # 재검증(산문 교정)
                send_admin_alert(
                    f"🧭 <b>kospi</b> 방향 오버라이드\n"
                    f"LLM: {llm_dir} → prior: {prior['direction']} (강도 strong, score {prior['score']})\n"
                    f"SOX {prior['signals'].get('sox')} / EWY {prior['signals'].get('ewy')} / VIX {prior['signals'].get('vix')}"
                )
            else:
                send_admin_alert(f"⚠️ kospi 방향 오버라이드 재생성 실패(rc={regen.returncode}) — LLM 방향 {llm_dir} 유지 발행")
```

(주의: 재생성본이 강제 방향이므로 재검증에서 다시 오버라이드가 발동하지 않는다 — 무한루프 없음. `Path`는 파일 상단에서 이미 import됨.)

- [ ] **Step 6: 단위 테스트 전체 통과 확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -m pytest scripts/test_leading_signal.py scripts/test_validate_analysis.py -q`
Expected: PASS (전체)

- [ ] **Step 7: 커밋**

```bash
cd "/Users/luke/Service App/double-shot"
git add scripts/leading_signal.py scripts/test_leading_signal.py scripts/validate_analysis.py
git commit -m "feat(방향 보정): 검증게이트 strong prior 오버라이드 재생성 + 관리자 알림"
```

---

### Task 5: 통합 dry-run (텔레그램 미발송)

**Files:** (수정 없음 — 검증만)

전제: `ANTHROPIC_API_KEY` 설정 + `data/latest_kospi.json` 존재. **텔레그램 발송 금지**(SERVICE_RULES 8) — `--no-html` 사용, send_telegram 미실행, `TELEGRAM_*` 환경변수 unset 권장.

- [ ] **Step 1: prior가 프롬프트에 주입되는지 확인 (생성 1회)**

Run:
```bash
cd "/Users/luke/Service App/double-shot"
python3 scripts/call_claude.py --type kospi --no-html --date 2026-06-22 2>&1 | grep -i "prior\|force"
```
Expected: `[call_claude] Leading-signal prior: <방향> (<강도>, score <n>)` 출력. force 라인은 없음(강제 미지정).

- [ ] **Step 2: 생성된 분석의 방향 확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -c "import json; a=json.load(open('data/analysis_kospi.json')); print(a['prediction'])"`
Expected: `prediction.direction`이 당일 prior와 정합적(강한 강세 신호면 상승 우위 등).

- [ ] **Step 3: 검증게이트 통과 확인 (오버라이드 발동 여부 로그)**

Run: `cd "/Users/luke/Service App/double-shot" && python3 scripts/validate_analysis.py --type kospi 2>&1 | tail -10`
Expected: 오버라이드 미발동(정합 시) 또는 `🧭 선행신호 오버라이드 ... 재생성` 로그 후 정상 종료(rc 0). 관리자 알림 키 미설정 시 "알림 건너뜀".

- [ ] **Step 4: 백테스트 출시 게이트 PASS 재확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 scripts/diagnose_direction_signals.py 2026-03-01 2>&1 | tail -1`
Expected: `[출시 게이트] ... → PASS`

- [ ] **Step 5: 마무리 — verification-before-completion 스킬로 증거 확인 후 PR 준비**

전체 테스트: `python3 -m pytest scripts/test_leading_signal.py scripts/test_validate_analysis.py tests/ -q`
모두 PASS면 브랜치 `feature/kospi-direction-prior` PR 준비.

---

## Self-Review (작성자 점검 완료)

- **스펙 커버리지**: A=Task1, B=Task3, C=Task4, D=Task2, 검증계획=Task5. 모든 컴포넌트에 태스크 대응. ✓
- **타입 일관성**: `compute_prior`/`extract_signals`/`format_prior_for_prompt`/`prior_contradicts_direction` 시그니처가 Task1·3·4에서 일치. prior dict 키(`direction`/`score`/`strength`/`signals`) 통일. 방향 문자열 비교는 부분 문자열 규칙으로 명시. ✓
- **placeholder**: 모든 코드 스텝에 실제 코드 포함, "적절히 처리" 류 없음. 가중치·임계값은 의도된 초기값(백테스트로 확정)이며 Task2가 그 확정 절차. ✓
- **알려진 한계**: 백테스트는 NQ선물·뉴스 미포함(주석 명시). strong 임계값(T_EWY/T_SOX)은 Task2 백테스트 결과에 따라 조정 가능 — 초기값으로 출시 게이트 PASS 확인 후 필요 시 튜닝.
