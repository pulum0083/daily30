# 시장의 큰 흐름(국면) 섹션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 시그널 홈에 최근 6개월 국면(주도주 교체/지속/무주도)을 규칙으로 판정해 보여주는 섹션을 만든다.

**Architecture:** 순수 계산(`market_regime_core.py`)과 수집·출력(`build_market_regime.py`)을 분리한다. 코어는 네트워크 없이 단위 테스트되고, 백테스트 회귀 테스트가 같은 코어를 import해 375영업일 실데이터로 리플레이한다. 프런트는 `web/data/market-regime.json`을 읽어 상태별로 레이아웃을 바꾼다. LLM은 쓰지 않는다.

**Tech Stack:** Python 3.12 (pytest), Yahoo Finance chart API, 바닐라 JS (node:test + node:vm), 기존 `.block` CSS 규격

**Spec:** [docs/superpowers/specs/2026-08-07-market-regime-section-design.md](../specs/2026-08-07-market-regime-section-design.md)

---

## File Structure

| 파일 | 책임 |
| --- | --- |
| `scripts/config/regime_baskets.json` | 바스켓 정의 (7개). 데이터만, 로직 없음 |
| `scripts/market_regime_core.py` | 순수 계산 — 누적수익률·국면판정·히스테리시스·문구. **네트워크 없음** |
| `scripts/build_market_regime.py` | Yahoo 수집 → 코어 호출 → `web/data/market-regime.json` 기록 |
| `scripts/test_market_regime_core.py` | 코어 단위 테스트 |
| `scripts/test_market_regime_backtest.py` | 실데이터 375영업일 리플레이 회귀 |
| `web/data/regime-backtest-fixture.json` | 백테스트용 고정 실데이터 (네트워크 없이 재현) |
| `web/stocks/index.html` | 섹션 마크업 (코스피 주도주 아래) |
| `web/assets/stocks-home.js` | 렌더 함수 `regimeRender()` |
| `web/assets/stocks-home.css` | 섹션 스타일 |
| `web/assets/market-regime.test.mjs` | 프런트 렌더 테스트 |
| `.github/workflows/daily_report.yml` | 마감 잡에 빌드 스텝 추가 |

코어를 별도 파일로 빼는 이유: 백테스트가 네트워크 없이 같은 로직을 리플레이해야 하고, 수집 코드와 섞이면 그게 불가능하다.

---

### Task 1: 바스켓 설정 파일

**Files:**
- Create: `scripts/config/regime_baskets.json`

- [ ] **Step 1: 설정 파일 작성**

```json
{
  "_comment": "국면 판정용 바스켓. scripts/config/stock_universe.json(종목 상세용 벨웨더)과 별개 파일이다 — 목적이 다르고 SCHD·XLP·IWD 등은 벨웨더가 아니다. NVDA·MU·SOXX는 양쪽에 겹치므로 한쪽을 바꿀 때 다른 쪽도 확인할 것.",
  "window_days": 126,
  "baskets": [
    { "key": "memory",            "name": "메모리 반도체",  "scope": "global", "members": ["MU", "SOXX", "DRAM"] },
    { "key": "ai_infra",          "name": "AI 인프라",     "scope": "global", "members": ["NVDA", "MSFT", "AMZN", "AVGO"] },
    { "key": "consumer_platform", "name": "소비 플랫폼",    "scope": "global", "members": ["AAPL", "GOOGL", "META"] },
    { "key": "dividend_defensive","name": "배당 방어",      "scope": "global", "members": ["SCHD", "XLP", "XLU"] },
    { "key": "value_cyclical",    "name": "가치 경기민감",   "scope": "global", "members": ["IWD", "XLF", "XLE"] },
    { "key": "kr_semi",           "name": "한국 반도체",    "scope": "korea",  "members": ["005930.KS", "000660.KS"] },
    { "key": "kr_rest",           "name": "한국 그 외",     "scope": "korea",  "members": ["305720.KS", "449450.KS", "091170.KS", "091180.KS"] }
  ]
}
```

> 바스켓 이름에 `·`를 쓰지 않는다. 목록 구분자 `, `와 충돌해 `"가치·경기민감·배당·방어"`가 한 덩어리로 읽힌다(스펙 §문구).

- [ ] **Step 2: JSON 유효성 확인**

Run: `python3 -c "import json;d=json.load(open('scripts/config/regime_baskets.json'));print(len(d['baskets']),'baskets')"`
Expected: `7 baskets`

- [ ] **Step 3: 커밋**

```bash
git add scripts/config/regime_baskets.json
git commit -m "feat(종목시그널): 국면 판정 바스켓 설정 추가"
```

---

### Task 2: 코어 — 누적수익률과 결측 처리

**Files:**
- Create: `scripts/market_regime_core.py`
- Test: `scripts/test_market_regime_core.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# 국면 판정 코어 테스트 — 네트워크 없이 순수 함수만 검증한다.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from market_regime_core import basket_cum  # noqa: E402


def test_basket_cum_simple_average():
    """구성 종목 누적수익률의 단순평균. 시총가중 아님."""
    dates = ["d1", "d2", "d3"]
    closes = {"A": {"d1": 100, "d2": 110, "d3": 120},
              "B": {"d1": 100, "d2": 100, "d3": 100}}
    cum, n = basket_cum(["A", "B"], closes, dates)
    assert n == 2
    assert cum[0] == 0.0
    assert cum[2] == 10.0          # (+20% + 0%) / 2


def test_basket_cum_excludes_ticker_missing_at_window_start():
    """창 시작에 없던 종목은 평균에서 제외한다 — DRAM(2026-04-02 상장) 케이스."""
    dates = ["d1", "d2"]
    closes = {"A": {"d1": 100, "d2": 120},
              "LATE": {"d2": 50}}          # d1에 없음
    cum, n = basket_cum(["A", "LATE"], closes, dates)
    assert n == 1
    assert cum[1] == 20.0                  # LATE는 통째로 빠짐


def test_basket_cum_forward_fills_missing_mid_series():
    """중간 결측(한국 휴장일)은 직전 종가로 채운다."""
    dates = ["d1", "d2", "d3"]
    closes = {"KR": {"d1": 100, "d3": 110}}   # d2 없음
    cum, n = basket_cum(["KR"], closes, dates)
    assert cum[1] == 0.0                      # d1 종가 유지
    assert cum[2] == 10.0


def test_basket_cum_returns_none_when_no_member_usable():
    dates = ["d1", "d2"]
    closes = {"LATE": {"d2": 50}}
    cum, n = basket_cum(["LATE"], closes, dates)
    assert cum is None and n == 0
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: FAIL — `ImportError: cannot import name 'basket_cum'`

- [ ] **Step 3: 최소 구현**

```python
# 국면(주도주 교체/지속/무주도) 판정 순수 계산. 네트워크·파일 IO 없음 — 백테스트가 같은 코드를 리플레이한다.
from __future__ import annotations

from bisect import bisect_right

WINDOW_DAYS = 126
COOL_THRESHOLD = -15.0   # 정점 대비 이만큼 이하면 '식음'
HIGH_THRESHOLD = -3.0    # 정점 대비 이 이내면 '신고점'
HYST_WINDOW = 5          # 히스테리시스 창(영업일)
HYST_MIN = 3             # 창 안에서 이만큼 이상 충족해야 인정
MIN_RUN = 10             # 이보다 짧은 국면은 직전 국면에 흡수


def _price_at(prices: dict, date: str, sorted_dates: list) -> float | None:
    """date의 종가. 없으면 직전 거래일 종가(한국·미국 캘린더 차이 보정).

    선형 스캔을 쓰면 백테스트가 375창 × 126일 × 19티커 × 500날짜로 폭발한다.
    날짜가 정렬돼 있으므로 이분 탐색으로 찾는다.
    """
    p = prices.get(date)
    if p is not None:
        return p
    i = bisect_right(sorted_dates, date)
    return prices[sorted_dates[i - 1]] if i else None


def basket_cum(members: list, closes: dict, dates: list) -> tuple[list | None, int]:
    """바스켓의 창 내 누적수익률(%)과 실제 사용된 종목 수.

    창 시작일에 값이 없는 종목은 통째로 제외한다 — 신규 상장 종목을 섞으면
    그 종목의 '상장 이후 수익률'이 6개월 수익률인 척 평균에 들어간다.
    """
    series = []
    for t in members:
        prices = closes.get(t) or {}
        if not prices:
            continue
        sd = sorted(prices)
        base = _price_at(prices, dates[0], sd)
        if base is None or base == 0:
            continue
        row = []
        for d in dates:
            p = _price_at(prices, d, sd)
            if p is None:
                row = None
                break
            row.append((p / base - 1) * 100)
        if row is not None:
            series.append(row)
    if not series:
        return None, 0
    cum = [round(sum(s[i] for s in series) / len(series), 4) for i in range(len(dates))]
    return cum, len(series)
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: `4 passed`

- [ ] **Step 5: 커밋**

```bash
git add scripts/market_regime_core.py scripts/test_market_regime_core.py
git commit -m "feat(종목시그널): 국면 코어 — 바스켓 누적수익률·결측 처리"
```

---

### Task 3: 코어 — 정점 대비 거리와 일별 플래그

**Files:**
- Modify: `scripts/market_regime_core.py`
- Test: `scripts/test_market_regime_core.py`

- [ ] **Step 1: 실패하는 테스트 추가 (파일 끝에 append)**

```python
from market_regime_core import daily_frames  # noqa: E402


def test_daily_frames_gap_from_running_peak():
    """gap은 '그 시점까지의 최고' 대비 거리다. 미래를 보지 않는다."""
    cums = {"a": [0.0, 10.0, 5.0]}
    fr = daily_frames(cums)
    assert fr[0]["a"]["gap"] == 0.0     # 첫날은 자기가 정점
    assert fr[1]["a"]["gap"] == 0.0     # 신고점
    assert fr[2]["a"]["gap"] == -5.0    # 정점 10에서 5 내려옴


def test_daily_frames_flags():
    cums = {"cooled": [0.0, 30.0, 10.0], "high": [0.0, 1.0, 2.0]}
    fr = daily_frames(cums)
    last = fr[2]
    assert last["cooled"]["is_cooled"] is True    # -20 <= -15
    assert last["cooled"]["is_high"] is False
    assert last["high"]["is_high"] is True        # gap 0 >= -3
    assert last["high"]["is_cooled"] is False


def test_daily_frames_threshold_boundaries():
    """경계값은 포함이다 — 정확히 -15.0이면 식음, -3.0이면 신고점."""
    fr = daily_frames({"x": [0.0, 100.0, 85.0]})   # gap = -15.0
    assert fr[2]["x"]["is_cooled"] is True
    fr2 = daily_frames({"y": [0.0, 100.0, 97.0]})  # gap = -3.0
    assert fr2[2]["y"]["is_high"] is True
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: FAIL — `ImportError: cannot import name 'daily_frames'`

- [ ] **Step 3: 구현 추가 (`market_regime_core.py` 끝에 append)**

```python
def daily_frames(cums: dict) -> list:
    """일자별 {key: {cum, peak, gap, is_cooled, is_high}}.

    peak은 그 시점까지의 러닝 최고다. 창 전체 최고를 쓰면 미래를 보게 된다.
    """
    keys = [k for k, v in cums.items() if v]
    if not keys:
        return []
    n = len(cums[keys[0]])
    frames = []
    peaks = {k: float("-inf") for k in keys}
    for i in range(n):
        row = {}
        for k in keys:
            v = cums[k][i]
            peaks[k] = max(peaks[k], v)
            gap = round(v - peaks[k], 4)
            row[k] = {
                "cum": round(v, 1),
                "peak": round(peaks[k], 1),
                "gap": round(gap, 1),
                "is_cooled": gap <= COOL_THRESHOLD,
                "is_high": gap >= HIGH_THRESHOLD,
            }
        frames.append(row)
    return frames
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: `7 passed`

- [ ] **Step 5: 커밋**

```bash
git add scripts/market_regime_core.py scripts/test_market_regime_core.py
git commit -m "feat(종목시그널): 국면 코어 — 러닝 정점 대비 거리·플래그"
```

---

### Task 4: 코어 — 히스테리시스를 판정 입력에 적용

**Files:**
- Modify: `scripts/market_regime_core.py`
- Test: `scripts/test_market_regime_core.py`

> **이 태스크가 스펙의 핵심 버그 방지 지점이다.** 히스테리시스를 상태 후처리로 걸면 상태는 '교체'인데 그날 재료가 없어 문구가 `"…에서 로 넘어가는 중"`으로 깨진다. 집합을 먼저 구하고 상태·문구가 **둘 다 그 집합에서** 재료를 가져가야 한다.

- [ ] **Step 1: 실패하는 테스트 추가**

```python
from market_regime_core import qualifying_sets, classify  # noqa: E402


def _frame(**kw):
    return {k: {"is_cooled": c, "is_high": h} for k, (c, h) in kw.items()}


def test_qualifying_needs_k_of_n_days():
    """최근 5일 중 3일 이상 충족해야 집합에 들어간다."""
    frames = [_frame(a=(False, True)) for _ in range(2)] + \
             [_frame(a=(True, False)) for _ in range(3)]
    cooled, rising = qualifying_sets(frames, 4)
    assert cooled == {"a"}      # 최근 5일 중 3일 cooled
    assert rising == set()      # 2일뿐이라 미달


def test_qualifying_short_window_at_start():
    """창이 5일보다 짧으면 있는 날 수 기준으로 판단한다."""
    frames = [_frame(a=(True, False)), _frame(a=(True, False))]
    cooled, _ = qualifying_sets(frames, 1)
    assert cooled == {"a"}      # 2일 전부 충족


def test_qualifying_restricts_to_allowed_keys():
    """헤드라인용 집합은 글로벌 바스켓으로 한정할 수 있어야 한다."""
    frames = [_frame(g=(True, False), kr=(True, False)) for _ in range(5)]
    cooled, _ = qualifying_sets(frames, 4, allowed={"g"})
    assert cooled == {"g"}


def test_classify_three_states():
    assert classify({"a"}, {"b"}) == "swap"
    assert classify(set(), {"b"}) == "lead"
    assert classify({"a"}, set()) == "none"
    assert classify(set(), set()) == "none"
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: FAIL — `ImportError: cannot import name 'qualifying_sets'`

- [ ] **Step 3: 구현 추가**

```python
def qualifying_sets(frames: list, i: int, allowed: set | None = None) -> tuple[set, set]:
    """i시점에서 '최근 HYST_WINDOW일 중 HYST_MIN일 이상' 조건을 만족한 바스켓 집합.

    히스테리시스를 상태가 아니라 이 입력 집합에 건다. 상태 판정과 문구 생성이
    둘 다 이 반환값만 쓰므로, 상태가 있으면 문구 재료도 반드시 있다.
    """
    lo = max(0, i - HYST_WINDOW + 1)
    window = frames[lo:i + 1]
    need = min(HYST_MIN, len(window))
    cool_n, high_n = {}, {}
    for row in window:
        for k, v in row.items():
            if allowed is not None and k not in allowed:
                continue
            if v["is_cooled"]:
                cool_n[k] = cool_n.get(k, 0) + 1
            if v["is_high"]:
                high_n[k] = high_n.get(k, 0) + 1
    return ({k for k, c in cool_n.items() if c >= need},
            {k for k, c in high_n.items() if c >= need})


def classify(cooled: set, rising: set) -> str:
    """swap = 식은 것과 신고점이 동시에 / lead = 신고점만 / none = 신고점 없음."""
    if cooled and rising:
        return "swap"
    if rising:
        return "lead"
    return "none"
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: `11 passed`

- [ ] **Step 5: 커밋**

```bash
git add scripts/market_regime_core.py scripts/test_market_regime_core.py
git commit -m "feat(종목시그널): 국면 코어 — 히스테리시스를 판정 입력에 적용"
```

---

### Task 5: 코어 — 짧은 국면 흡수

**Files:**
- Modify: `scripts/market_regime_core.py`
- Test: `scripts/test_market_regime_core.py`

- [ ] **Step 1: 실패하는 테스트 추가**

```python
from market_regime_core import absorb_short_runs  # noqa: E402


def test_absorb_run_shorter_than_min():
    """10일 미만 구간은 직전 국면에 흡수된다."""
    states = ["lead"] * 12 + ["swap"] * 3 + ["lead"] * 12
    out = absorb_short_runs(states)
    assert set(out) == {"lead"}


def test_absorb_keeps_long_enough_run():
    states = ["lead"] * 12 + ["swap"] * 10 + ["lead"] * 12
    out = absorb_short_runs(states)
    assert out[12:22] == ["swap"] * 10


def test_absorb_does_not_touch_first_run():
    """첫 구간은 흡수할 직전 국면이 없다 — 짧아도 그대로 둔다."""
    states = ["swap"] * 3 + ["lead"] * 20
    out = absorb_short_runs(states)
    assert out[:3] == ["swap"] * 3


def test_absorb_empty():
    assert absorb_short_runs([]) == []
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: FAIL — `ImportError: cannot import name 'absorb_short_runs'`

- [ ] **Step 3: 구현 추가**

```python
def absorb_short_runs(states: list) -> list:
    """MIN_RUN보다 짧은 구간을 직전 국면에 흡수한다 — 카드가 깜빡이는 것을 막는다.

    첫 구간은 흡수 대상이 아니다(직전이 없다).
    """
    out = list(states)
    i = 0
    while i < len(out):
        j = i
        while j + 1 < len(out) and out[j + 1] == out[i]:
            j += 1
        if (j - i + 1) < MIN_RUN and i > 0:
            fill = out[i - 1]
            for t in range(i, j + 1):
                out[t] = fill
        i = j + 1
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: `15 passed`

- [ ] **Step 5: 커밋**

```bash
git add scripts/market_regime_core.py scripts/test_market_regime_core.py
git commit -m "feat(종목시그널): 국면 코어 — 짧은 국면 흡수"
```

---

### Task 6: 코어 — 조사 처리와 헤드라인 템플릿

**Files:**
- Modify: `scripts/market_regime_core.py`
- Test: `scripts/test_market_regime_core.py`

- [ ] **Step 1: 실패하는 테스트 추가**

```python
from market_regime_core import josa, headline  # noqa: E402

NAMES = {"memory": "메모리 반도체", "ai_infra": "AI 인프라",
         "value_cyclical": "가치 경기민감", "dividend_defensive": "배당 방어"}
ORDER = ["memory", "ai_infra", "value_cyclical", "dividend_defensive"]


def test_josa_by_final_consonant():
    assert josa("인프라") == "로"        # 받침 없음
    assert josa("가치 경기민감") == "으로"  # 받침 ㅁ
    assert josa("서울") == "로"          # ㄹ 종성은 '로'
    assert josa("방어") == "로"


def test_headline_swap_picks_most_cooled_and_top_two_high():
    """A = gap 최소(가장 많이 식은), B = cum 내림차순 최대 2개."""
    cum = {"memory": 89.4, "ai_infra": 17.2, "value_cyclical": 9.8, "dividend_defensive": -1.5}
    gap = {"memory": -53.2, "ai_infra": 0.0, "value_cyclical": 0.0, "dividend_defensive": -20.0}
    txt = headline("swap", {"memory", "dividend_defensive"},
                   {"ai_infra", "value_cyclical"}, cum, gap, NAMES, ORDER)
    assert txt == "주도주가 메모리 반도체에서 AI 인프라, 가치 경기민감으로 넘어가는 중이에요"


def test_headline_lead_uses_top_cumulative():
    cum = {"memory": 89.4, "ai_infra": 17.2}
    gap = {"memory": 0.0, "ai_infra": 0.0}
    txt = headline("lead", set(), {"memory"}, cum, gap, NAMES, ORDER)
    assert txt == "메모리 반도체 주도가 이어지고 있어요"


def test_headline_none_is_fixed_sentence():
    assert headline("none", set(), set(), {}, {}, NAMES, ORDER) == "뚜렷한 주도주가 없어요"


def test_headline_returns_none_when_material_missing():
    """상태는 swap인데 재료가 없으면 None. 억지로 문장을 만들지 않는다(§0)."""
    assert headline("swap", set(), {"ai_infra"}, {"ai_infra": 1.0}, {"ai_infra": 0.0},
                    NAMES, ORDER) is None


def test_headline_ties_break_by_declaration_order():
    """동점이면 설정 파일 선언 순서를 따른다 — 결정론 보장."""
    cum = {"ai_infra": 5.0, "value_cyclical": 5.0}
    gap = {"ai_infra": 0.0, "value_cyclical": 0.0}
    txt = headline("lead", set(), {"ai_infra", "value_cyclical"}, cum, gap, NAMES, ORDER)
    assert txt == "AI 인프라 주도가 이어지고 있어요"
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: FAIL — `ImportError: cannot import name 'josa'`

- [ ] **Step 3: 구현 추가**

```python
def josa(word: str) -> str:
    """받침에 따라 '으로/로'. 종성이 없거나 ㄹ이면 '로'."""
    ch = word.strip()[-1]
    code = ord(ch)
    if not (0xAC00 <= code <= 0xD7A3):
        return "로"
    jong = (code - 0xAC00) % 28
    return "로" if jong in (0, 8) else "으로"


def headline(state, cooled, rising, cum, gap, names, order):
    """상태별 문구. 재료가 없으면 None — 억지로 만들지 않는다(§0).

    A = cooled 중 gap 오름차순 1개, B = rising 중 cum 내림차순 최대 2개,
    C = rising 중 cum 내림차순 1개. 동점은 order(선언 순서)로 깬다.
    """
    def rank(keys, metric, reverse):
        return sorted(keys, key=lambda k: (-metric[k] if reverse else metric[k],
                                           order.index(k) if k in order else 999))

    if state == "none":
        return "뚜렷한 주도주가 없어요"
    if state == "lead":
        if not rising:
            return None
        top = rank(rising, cum, True)[0]
        return f"{names[top]} 주도가 이어지고 있어요"
    if state == "swap":
        if not cooled or not rising:
            return None
        frm = names[rank(cooled, gap, False)[0]]
        tos = [names[k] for k in rank(rising, cum, True)[:2]]
        joined = ", ".join(tos)
        return f"주도주가 {frm}에서 {joined}{josa(joined)} 넘어가는 중이에요"
    return None
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: `21 passed`

- [ ] **Step 5: 커밋**

```bash
git add scripts/market_regime_core.py scripts/test_market_regime_core.py
git commit -m "feat(종목시그널): 국면 코어 — 조사 분기·헤드라인 템플릿"
```

---

### Task 7: 코어 — 국면 단위 문구 확정 파이프라인

**Files:**
- Modify: `scripts/market_regime_core.py`
- Test: `scripts/test_market_regime_core.py`

- [ ] **Step 1: 실패하는 테스트 추가**

```python
from market_regime_core import resolve_regimes  # noqa: E402


def _mk_frames(n, cooled_keys, high_keys):
    return [{k: {"is_cooled": k in cooled_keys, "is_high": k in high_keys,
                 "cum": 10.0 if k in high_keys else -30.0,
                 "gap": 0.0 if k in high_keys else -40.0}
             for k in ("memory", "ai_infra")} for _ in range(n)]


def test_resolve_holds_one_sentence_per_regime():
    """같은 국면 안에서는 문장이 바뀌지 않는다."""
    frames = _mk_frames(30, {"memory"}, {"ai_infra"})
    out = resolve_regimes(frames, NAMES, ORDER, {"memory", "ai_infra"})
    texts = {r["headline"] for r in out}
    assert len(texts) == 1
    assert out[0]["state"] == "swap"


def test_resolve_marks_regime_start():
    frames = _mk_frames(30, {"memory"}, {"ai_infra"})
    out = resolve_regimes(frames, NAMES, ORDER, {"memory", "ai_infra"})
    assert all(r["regime_index"] == 0 for r in out)


def test_resolve_never_emits_null_headline():
    """스펙의 검증 기준 — 문구 생성 실패 0건."""
    frames = _mk_frames(30, set(), set())     # 신고점 없음 → none
    out = resolve_regimes(frames, NAMES, ORDER, {"memory", "ai_infra"})
    assert all(r["headline"] for r in out)
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: FAIL — `ImportError: cannot import name 'resolve_regimes'`

- [ ] **Step 3: 구현 추가**

```python
def resolve_regimes(frames: list, names: dict, order: list, allowed: set) -> list:
    """일자별 [{state, headline, regime_index}].

    문구는 국면 단위로 한 번 확정한다 — 같은 국면 안에서 문장이 매일 미묘하게
    달라지면 '국면'이라는 개념 자체가 흐려진다. 그 국면에서 재료가 유효한 가장
    최근 값으로 만들어 국면 내내 유지한다.
    """
    raw = []
    for i in range(len(frames)):
        cooled, rising = qualifying_sets(frames, i, allowed)
        raw.append((classify(cooled, rising), cooled, rising))
    states = absorb_short_runs([r[0] for r in raw])

    out = [None] * len(frames)
    i = 0
    regime_index = 0
    while i < len(states):
        j = i
        while j + 1 < len(states) and states[j + 1] == states[i]:
            j += 1
        text = None
        for t in range(j, i - 1, -1):        # 국면 안에서 가장 최근 유효 재료
            cooled, rising = qualifying_sets(frames, t, allowed)
            cum = {k: v["cum"] for k, v in frames[t].items()}
            gap = {k: v["gap"] for k, v in frames[t].items()}
            text = headline(states[i], cooled, rising, cum, gap, names, order)
            if text:
                break
        for t in range(i, j + 1):
            out[t] = {"state": states[i], "headline": text, "regime_index": regime_index}
        regime_index += 1
        i = j + 1
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_market_regime_core.py -q`
Expected: `24 passed`

- [ ] **Step 5: 커밋**

```bash
git add scripts/market_regime_core.py scripts/test_market_regime_core.py
git commit -m "feat(종목시그널): 국면 코어 — 국면 단위 문구 확정"
```

---

### Task 8: 실데이터 백테스트 픽스처

**Files:**
- Create: `scripts/build_market_regime.py` (수집부만)
- Create: `web/data/regime-backtest-fixture.json`

- [ ] **Step 1: 수집 함수 작성**

```python
# 국면 데이터 빌더 — Yahoo 일봉을 받아 market_regime_core로 계산하고 JSON을 굽는다.
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pytz

sys.path.insert(0, str(Path(__file__).parent))
from market_regime_core import WINDOW_DAYS  # noqa: E402

KST = pytz.timezone("Asia/Seoul")
CONFIG_PATH = Path(__file__).parent / "config" / "regime_baskets.json"
OUT_PATH = Path(__file__).parent.parent / "web" / "data" / "market-regime.json"
UA = {"User-Agent": "Mozilla/5.0"}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def fetch_daily_closes(ticker: str, rng: str = "2y") -> dict:
    """{'YYYY-MM-DD': close}. 실패 시 빈 dict — 호출부가 바스켓에서 제외한다."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={rng}&interval=1d")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read())
        r = data["chart"]["result"][0]
        ts = r["timestamp"]
        closes = r["indicators"]["quote"][0]["close"]
        return {datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"): c
                for t, c in zip(ts, closes) if c is not None}
    except Exception as e:
        print(f"[regime] {ticker} 수집 실패: {e}", file=sys.stderr)
        return {}


def fetch_all(cfg: dict, rng: str = "2y") -> dict:
    out = {}
    for b in cfg["baskets"]:
        for t in b["members"]:
            if t not in out:
                out[t] = fetch_daily_closes(t, rng)
    return out
```

- [ ] **Step 2: 픽스처 생성 스크립트 실행**

```bash
python3 - <<'PY'
import sys, json
sys.path.insert(0, 'scripts')
from build_market_regime import load_config, fetch_all
cfg = load_config()
closes = fetch_all(cfg, "2y")
missing = [t for t, v in closes.items() if not v]
assert not missing, f"수집 실패: {missing}"
json.dump({"closes": closes}, open("web/data/regime-backtest-fixture.json", "w"), ensure_ascii=False)
print("티커", len(closes), "· 최장 시계열", max(len(v) for v in closes.values()))
PY
```

Expected: `티커 19 · 최장 시계열 501` (DRAM만 87 내외 — 2026-04-02 상장이라 정상)

- [ ] **Step 3: 커밋**

```bash
git add scripts/build_market_regime.py web/data/regime-backtest-fixture.json
git commit -m "feat(종목시그널): 국면 수집부 + 백테스트 픽스처"
```

---

### Task 9: 백테스트 회귀 테스트

**Files:**
- Create: `scripts/test_market_regime_backtest.py`

> 스펙의 검증 기준 3개를 그대로 테스트로 옮긴다 — 문구 실패 0건, 사용자 관찰 국면 재현, 전환 15회 이하.

- [ ] **Step 1: 테스트 작성**

```python
# 국면 판정 실데이터 리플레이 — 375영업일 픽스처로 스펙의 검증 기준 3개를 확인한다.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from market_regime_core import (WINDOW_DAYS, basket_cum, daily_frames,  # noqa: E402
                                resolve_regimes)

FIXTURE = Path(__file__).parent.parent / "web" / "data" / "regime-backtest-fixture.json"
CONFIG = Path(__file__).parent / "config" / "regime_baskets.json"


def _replay():
    closes = json.loads(FIXTURE.read_text())["closes"]
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    names = {b["key"]: b["name"] for b in cfg["baskets"]}
    order = [b["key"] for b in cfg["baskets"]]
    allowed = {b["key"] for b in cfg["baskets"] if b["scope"] == "global"}
    cal = sorted(closes["MSFT"])            # 기준 캘린더 = 미국 거래일

    rows = []
    for i in range(WINDOW_DAYS, len(cal)):
        win = cal[i - WINDOW_DAYS:i + 1]
        cums = {}
        for b in cfg["baskets"]:
            cum, n = basket_cum(b["members"], closes, win)
            if cum:
                cums[b["key"]] = cum
        frame = daily_frames(cums)[-1]
        rows.append({"date": cal[i], "frame": frame})

    frames = [r["frame"] for r in rows]
    res = resolve_regimes(frames, names, order, allowed)
    return [r["date"] for r in rows], res


def test_no_headline_failures():
    """스펙 검증 기준 — 문구 생성 실패 0건. None이 나오면 판정과 재료가 어긋난 것."""
    _, res = _replay()
    bad = [i for i, r in enumerate(res) if not r["headline"]]
    assert not bad, f"문구 생성 실패 {len(bad)}건"


def test_transition_count_under_limit():
    """전환이 잦으면 카드가 깜빡인다. 375일 기준 15회 이하."""
    dates, res = _replay()
    st = [r["state"] for r in res]
    flips = sum(1 for i in range(1, len(st)) if st[i] != st[i - 1])
    assert flips <= 15, f"전환 {flips}회 — 임계값 재검토 필요"


def test_reproduces_observed_regimes():
    """사용자 관찰 회귀 가드 — 5~6월 메모리 주도, 7월 이후 교체."""
    dates, res = _replay()
    by_date = {d: r for d, r in zip(dates, res)}
    assert by_date["2026-05-15"]["state"] == "lead"
    assert "메모리" in by_date["2026-05-15"]["headline"]
    assert by_date["2026-07-24"]["state"] == "swap"
    assert by_date["2026-08-06"]["state"] == "swap"


def test_korea_baskets_excluded_from_headline():
    """한국 바스켓은 헤드라인 주어가 되지 않는다 — read-through 전용."""
    _, res = _replay()
    assert not any("한국" in r["headline"] for r in res)
```

- [ ] **Step 2: 실행**

Run: `python3 -m pytest scripts/test_market_regime_backtest.py -q -s`
Expected: `4 passed`

> 실패하면 임계값(`COOL_THRESHOLD`/`HIGH_THRESHOLD`/`HYST_*`/`MIN_RUN`)을 조정하지 말고 **먼저 어느 기준이 깨졌는지 출력**해 원인을 확인할 것. 임계값은 백테스트로 고른 값이라 임의 변경 시 스펙과 어긋난다.

- [ ] **Step 3: 커밋**

```bash
git add scripts/test_market_regime_backtest.py
git commit -m "test(종목시그널): 국면 판정 실데이터 리플레이 회귀"
```

---

### Task 10: JSON 빌더 완성

**Files:**
- Modify: `scripts/build_market_regime.py`

- [ ] **Step 1: 빌드·출력 함수 추가 (파일 끝에 append)**

```python
def build(closes: dict, cfg: dict) -> dict:
    """오늘 시점 국면 산출물. 창은 마지막 WINDOW_DAYS 영업일."""
    from market_regime_core import basket_cum, daily_frames, resolve_regimes

    names = {b["key"]: b["name"] for b in cfg["baskets"]}
    order = [b["key"] for b in cfg["baskets"]]
    allowed = {b["key"] for b in cfg["baskets"] if b["scope"] == "global"}

    cal = sorted(closes["MSFT"])
    if len(cal) < WINDOW_DAYS + 1:
        raise RuntimeError(f"캘린더 부족: {len(cal)}일 < {WINDOW_DAYS + 1}일")

    # 국면 이력을 위해 최근 120일치도 같이 계산한다(regime_since 산출용)
    hist_n = min(120, len(cal) - WINDOW_DAYS)
    frames, spark_by_key, meta = [], {}, {}
    for i in range(len(cal) - hist_n, len(cal)):
        win = cal[i - WINDOW_DAYS:i + 1]
        cums = {}
        for b in cfg["baskets"]:
            cum, n = basket_cum(b["members"], closes, win)
            if cum:
                cums[b["key"]] = cum
                if i == len(cal) - 1:
                    spark_by_key[b["key"]] = [round(v, 1) for v in cum[::5]]
                    meta[b["key"]] = n
        frames.append(daily_frames(cums)[-1])

    res = resolve_regimes(frames, names, order, allowed)
    last, last_frame = res[-1], frames[-1]

    since = cal[-1]
    for i in range(len(res) - 1, 0, -1):
        if res[i]["regime_index"] != res[i - 1]["regime_index"]:
            since = cal[len(cal) - hist_n + i]
            break

    baskets = []
    for b in cfg["baskets"]:
        k = b["key"]
        if k not in last_frame:
            continue
        f = last_frame[k]
        baskets.append({"key": k, "name": b["name"], "scope": b["scope"],
                        "cum": f["cum"], "peak": f["peak"], "gap": f["gap"],
                        "is_high": f["is_high"], "spark": spark_by_key.get(k, []),
                        "members": b["members"], "n_used": meta.get(k, 0)})

    kr = {b["key"]: last_frame[b["key"]]["cum"]
          for b in cfg["baskets"] if b["scope"] == "korea" and b["key"] in last_frame}
    korea = None
    if "kr_semi" in kr and "kr_rest" in kr:
        korea = {"semi": kr["kr_semi"], "rest": kr["kr_rest"],
                 "gap": round(kr["kr_semi"] - kr["kr_rest"], 1)}

    out = {"generated_at": datetime.now(KST).isoformat(),
           "session_date": cal[-1],
           "window_days": WINDOW_DAYS,
           "state": last["state"], "headline": last["headline"],
           "regime_since": since, "baskets": baskets}
    if korea:
        out["korea"] = korea
    return out


def main():
    cfg = load_config()
    closes = fetch_all(cfg)
    usable = {t: v for t, v in closes.items() if v}
    print(f"[regime] 수집 {len(usable)}/{len(closes)} 티커", file=sys.stderr)
    result = build(closes, cfg)
    if not result["headline"]:
        raise RuntimeError("헤드라인 생성 실패 — 판정과 재료가 어긋났다")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[regime] {result['state']} · \"{result['headline']}\" → {OUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 픽스처로 build() 검증 (네트워크 없이)**

```bash
python3 - <<'PY'
import sys, json
sys.path.insert(0, 'scripts')
from build_market_regime import build, load_config
closes = json.load(open("web/data/regime-backtest-fixture.json"))["closes"]
r = build(closes, load_config())
assert r["headline"], "헤드라인 없음"
assert r["state"] in ("swap", "lead", "none")
assert len(r["baskets"]) == 7
print(r["state"], "|", r["headline"])
print("regime_since", r["regime_since"], "| korea", r.get("korea"))
PY
```

Expected: `swap | 주도주가 메모리 반도체에서 …` 형태 출력, `regime_since` 날짜와 `korea` dict 표시

- [ ] **Step 3: 실제 실행**

Run: `python3 scripts/build_market_regime.py`
Expected: `[regime] swap · "…" → …/web/data/market-regime.json`

- [ ] **Step 4: 커밋**

```bash
git add scripts/build_market_regime.py web/data/market-regime.json
git commit -m "feat(종목시그널): 국면 JSON 빌더"
```

---

### Task 11: 프런트 — 마크업과 신선도 가드

**Files:**
- Modify: `web/stocks/index.html` (코스피 주도주 블록 직후)
- Create: `web/assets/market-regime.test.mjs`
- Modify: `web/assets/stocks-home.js`

- [ ] **Step 1: 마크업 추가**

`web/stocks/index.html`에서 코스피 주도주 블록이 끝나는 지점(`⚡ 상승 모멘텀 종목` 블록 직전)에 삽입한다.

```html
    <!-- 시장의 큰 흐름 — 최근 6개월 국면. regimeRender()가 채운다.
         데이터가 없거나 5일 넘게 낡으면 JS가 is-hidden을 유지한다(§0·§20). -->
    <div class="block regime-block is-hidden" id="regime-block">
      <div class="block__h">
        <span class="block__t"><span class="ic">🌊</span>시장의 큰 흐름</span>
        <span class="block__s" id="regime-asof">—</span>
      </div>
      <div class="regime-body" id="regime-body"></div>
    </div>
```

- [ ] **Step 2: 실패하는 프런트 테스트 작성**

```javascript
// 국면 섹션 렌더 테스트 — stocks-home.js를 node:vm에서 실제 로드해 검증한다.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const noop = () => {};

function mkEl() {
  const e = { classList: { _s: new Set(), add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); }, contains(c) { return this._s.has(c); }, toggle: noop },
    dataset: {}, style: {}, children: [], innerHTML: '', textContent: '',
    addEventListener: noop, appendChild: noop, setAttribute: noop,
    getAttribute: () => null, querySelector: () => null, querySelectorAll: () => [],
    getBoundingClientRect: () => ({ top: 0, left: 0, width: 0, height: 0 }) };
  return e;
}

function load() {
  const store = {};
  const els = new Proxy(store, { get(t, id) {
    if (typeof id !== 'string') return t[id];
    if (!t[id]) t[id] = mkEl();
    return t[id];
  } });
  const win = {
    location: { pathname: '/stocks/', hash: '' },
    addEventListener: noop, setInterval: () => 0, setTimeout: () => 0,
    fetch: () => Promise.reject(new Error('no network')),
    matchMedia: () => ({ matches: false, addEventListener: noop }),
    sessionStorage: { getItem: () => null, setItem: noop },
    document: { readyState: 'complete', getElementById: (id) => els[id],
      querySelector: () => mkEl(), querySelectorAll: () => [],
      createElement: () => mkEl(), addEventListener: noop,
      body: mkEl(), documentElement: mkEl(), head: mkEl() },
  };
  win.window = win;
  const ctx = createContext(win);
  runInContext(readFileSync(join(HERE, 'stocks-home.js'), 'utf8'), ctx);
  return { api: win.__marketRegime, els };
}

const FRESH = new Date().toISOString();
const SWAP = { generated_at: FRESH, session_date: '2026-08-07', state: 'swap',
  headline: '주도주가 메모리 반도체에서 AI 인프라로 넘어가는 중이에요',
  regime_since: '2026-06-24',
  baskets: [
    { key: 'memory', name: '메모리 반도체', scope: 'global', cum: 89.4, peak: 142.6,
      gap: -53.2, is_high: false, spark: [0, 50, 142, 89] },
    { key: 'ai_infra', name: 'AI 인프라', scope: 'global', cum: 17.2, peak: 17.2,
      gap: 0, is_high: true, spark: [0, 5, 10, 17] }],
  korea: { semi: 51.2, rest: -11.2, gap: 62.4 } };

test('swap — 좌우 2단을 그리고 블록을 보여준다', () => {
  const { api, els } = load();
  api.regimeRender(SWAP);
  assert.equal(els['regime-block'].classList.contains('is-hidden'), false);
  assert.match(els['regime-body'].innerHTML, /식는 중/);
  assert.match(els['regime-body'].innerHTML, /뜨는 중/);
  assert.match(els['regime-body'].innerHTML, /메모리 반도체/);
});

test('lead — 좌우 2단 없이 한 장으로 접힌다', () => {
  const { api, els } = load();
  api.regimeRender({ ...SWAP, state: 'lead', headline: '메모리 반도체 주도가 이어지고 있어요' });
  assert.doesNotMatch(els['regime-body'].innerHTML, /뜨는 중/);
  assert.match(els['regime-body'].innerHTML, /주도가 이어지고 있어요/);
});

test('none — 무주도 문구만 나온다', () => {
  const { api, els } = load();
  api.regimeRender({ ...SWAP, state: 'none', headline: '뚜렷한 주도주가 없어요' });
  assert.match(els['regime-body'].innerHTML, /뚜렷한 주도주가 없어요/);
  assert.doesNotMatch(els['regime-body'].innerHTML, /식는 중/);
});

test('5일 넘게 낡으면 섹션을 표시하지 않는다', () => {
  const { api, els } = load();
  const old = new Date(Date.now() - 6 * 864e5).toISOString();
  api.regimeRender({ ...SWAP, generated_at: old });
  assert.equal(els['regime-block'].classList.contains('is-hidden'), true);
});

test('데이터가 없거나 헤드라인이 비면 표시하지 않는다', () => {
  const { api, els } = load();
  api.regimeRender(null);
  assert.equal(els['regime-block'].classList.contains('is-hidden'), true);
  api.regimeRender({ ...SWAP, headline: '' });
  assert.equal(els['regime-block'].classList.contains('is-hidden'), true);
});

test('한국 read-through는 격차를 함께 보여준다', () => {
  const { api, els } = load();
  api.regimeRender(SWAP);
  assert.match(els['regime-body'].innerHTML, /62/);
});
```

- [ ] **Step 3: 실패 확인**

Run: `node --test web/assets/market-regime.test.mjs`
Expected: FAIL — `Cannot read properties of undefined (reading 'regimeRender')`

- [ ] **Step 4: 렌더 함수 구현**

`web/assets/stocks-home.js` 끝의 다른 IIFE들과 같은 자리에 추가한다.

```javascript
/* ── 시장의 큰 흐름(국면) — web/data/market-regime.json ── */
(function(){
  var STALE_DAYS=5;
  function fmtPct(v){ return (v>=0?'+':'−')+Math.abs(v).toFixed(1)+'%'; }
  function cls(v){ return v>=0?'up':'dn'; }
  function spark(vals,color){
    if(!vals||vals.length<2) return '';
    var lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals);
    if(hi===lo) hi=lo+1;
    var pts=vals.map(function(v,i){
      return (3+i*194/(vals.length-1)).toFixed(1)+','+(31-(v-lo)/(hi-lo)*28).toFixed(1);
    }).join(' ');
    return '<svg viewBox="0 0 200 34" class="regime-spark" preserveAspectRatio="none">'
      +'<polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="2" '
      +'stroke-linejoin="round"/></svg>';
  }
  function card(b,kind){
    var high=b.is_high?'<span class="regime-pill">6개월 최고</span>':'';
    var sub=kind==='cool'
      ? '정점 '+fmtPct(b.peak)+' → 지금 '+fmtPct(b.cum)
      : '누적 '+fmtPct(b.cum);
    return '<div class="regime-item"><div class="regime-n">'+b.name+high+'</div>'
      +'<div class="regime-s">'+sub+'</div>'
      +spark(b.spark, kind==='cool'?'#2775ED':'#E03131')+'</div>';
  }
  function regimeRender(d){
    var box=document.getElementById('regime-block');
    var body=document.getElementById('regime-body');
    var asof=document.getElementById('regime-asof');
    if(!box||!body) return;
    // 없으면 비운다 — 낡은 국면이 계속 진짜처럼 보이는 게 가장 위험하다(§0·§20)
    if(!d||!d.headline||!d.generated_at){ box.classList.add('is-hidden'); return; }
    var age=(Date.now()-new Date(d.generated_at).getTime())/864e5;
    if(!(age>=0)||age>STALE_DAYS){
      box.classList.add('is-hidden');
      console.warn('[regime] 데이터가 '+Math.round(age)+'일 지났습니다 — 섹션 생략');
      return;
    }
    var g=(d.baskets||[]).filter(function(b){return b.scope==='global';});
    var cooled=g.slice().sort(function(a,b){return a.gap-b.gap;})[0];
    var rising=g.filter(function(b){return b.is_high;})
                .sort(function(a,b){return b.cum-a.cum;}).slice(0,2);
    var html='<div class="regime-hd">'+d.headline+'</div>'
      +'<div class="regime-sub">최근 6개월 누적 기준'
      +(d.regime_since?' · '+d.regime_since.slice(5).replace('-','/')+'부터':'')+'</div>';
    if(d.state==='swap' && cooled && rising.length){
      html+='<div class="regime-swap">'
        +'<div class="regime-col is-cool"><div class="regime-lab">식는 중</div>'+card(cooled,'cool')+'</div>'
        +'<div class="regime-arrow">→</div>'
        +'<div class="regime-col is-hot"><div class="regime-lab">뜨는 중</div>'
        +rising.map(function(b){return card(b,'hot');}).join('')+'</div></div>';
    } else {
      var top=g.slice().sort(function(a,b){return b.cum-a.cum;})[0];
      if(top) html+='<div class="regime-single">'+card(top,'hot')+'</div>';
    }
    if(d.korea){
      html+='<div class="regime-kr">🇰🇷 한국은 반도체 <b>'+fmtPct(d.korea.semi)
        +'</b> vs 그 외 <b>'+fmtPct(d.korea.rest)+'</b> — 격차 <b>'
        +Math.abs(d.korea.gap).toFixed(0)+'%p</b></div>';
    }
    body.innerHTML=html;
    if(asof&&d.session_date) asof.textContent='최근 6개월 · '
      +d.session_date.slice(5).replace('-','/')+' 기준';
    box.classList.remove('is-hidden');
  }
  function regimeLoad(){
    fetch('/data/market-regime.json',{cache:'no-store'})
      .then(function(r){return r.ok?r.json():null;})
      .then(regimeRender)
      .catch(function(){ regimeRender(null); });
  }
  window.__marketRegime={regimeRender:regimeRender, regimeLoad:regimeLoad};
  if(typeof window.addEventListener==='function') window.addEventListener('load', regimeLoad);
})();
```

- [ ] **Step 5: 통과 확인**

Run: `node --test web/assets/market-regime.test.mjs`
Expected: `6 pass, 0 fail`

- [ ] **Step 6: 커밋**

```bash
git add web/stocks/index.html web/assets/stocks-home.js web/assets/market-regime.test.mjs
git commit -m "feat(종목시그널): 국면 섹션 렌더 + 신선도 가드"
```

---

### Task 12: CSS와 반응형

**Files:**
- Modify: `web/assets/stocks-home.css`
- Modify: `web/stocks/index.html` (캐시버스터)

- [ ] **Step 1: 스타일 추가 (`.vsavg` 규칙 근처, 데스크톱 영역)**

```css
/* 시장의 큰 흐름(국면) — 좌우 교체판. 상태가 swap이 아니면 .regime-single 한 장으로 접힌다. */
.regime-hd{font-size:17px;font-weight:800;color:var(--ink);line-height:1.42;letter-spacing:-.2px;}
.regime-sub{font-size:11.5px;color:var(--muted);margin-top:4px;}
.regime-body{padding:15px 16px 16px;}
.regime-swap{display:grid;grid-template-columns:1fr 34px 1fr;align-items:stretch;margin-top:13px;}
.regime-col{border-radius:10px;padding:11px 12px;}
.regime-col.is-cool{border:1px solid #CFE0FF;background:#F7FAFF;}
.regime-col.is-hot{border:1px solid #FFC9C9;background:#FFF8F8;}
.regime-arrow{display:flex;align-items:center;justify-content:center;font-size:19px;color:var(--muted);}
.regime-lab{font-size:10px;font-weight:800;margin-bottom:8px;}
.is-cool .regime-lab{color:#2775ED;}
.is-hot .regime-lab{color:#E03131;}
.regime-item + .regime-item{margin-top:9px;}
.regime-n{font-size:12.5px;font-weight:800;color:var(--ink);display:flex;align-items:center;gap:6px;}
.regime-s{font-size:10.5px;color:var(--muted);margin:2px 0 7px;}
.regime-pill{font-size:9.5px;font-weight:800;padding:1.5px 6px;border-radius:999px;background:#FFF0F0;color:#E03131;}
.regime-spark{width:100%;height:34px;display:block;}
.regime-single{margin-top:13px;border:1px solid var(--hair);border-radius:10px;padding:11px 12px;}
.regime-kr{margin-top:11px;padding:9px 11px;border-radius:8px;font-size:11.5px;line-height:1.55;
  background:#F3F8FF;border:1px solid #CFE0FF;color:#1B5FC4;}
```

- [ ] **Step 2: 모바일 규칙 추가 (`@media` 블록 안, `.vsavg{width:42px}` 근처)**

```css
  /* 좌우 2단은 모바일에서 상하로 접고 화살표를 아래 방향으로 돌린다. */
  .regime-swap{grid-template-columns:1fr;}
  .regime-arrow{height:26px;}
  .regime-arrow::before{content:'↓';}
  .regime-arrow{font-size:0;}
  .regime-arrow::before{font-size:19px;}
  .regime-hd{font-size:15.5px;}
```

- [ ] **Step 3: 캐시버스터 올리기**

`web/stocks/index.html`에서 두 줄을 수정한다.

```
/assets/stocks-home.css?v=10  →  ?v=11
/assets/stocks-home.js?v=9    →  ?v=10
```

- [ ] **Step 4: 브라우저 확인**

```bash
python3 -m http.server 8792 --directory web &
```

`http://localhost:8792/stocks/` 접속 → 코스피 주도주 아래에 `🌊 시장의 큰 흐름` 카드가 보이고, 좌우 2단이 렌더되는지 확인. 375px 뷰포트에서 상하로 접히는지도 확인.

Expected: 가로 스크롤 넘침 0, 콘솔 에러 0

- [ ] **Step 5: 커밋**

```bash
git add web/assets/stocks-home.css web/stocks/index.html
git commit -m "feat(종목시그널): 국면 섹션 스타일·반응형"
```

---

### Task 13: 워크플로 연결

**Files:**
- Modify: `.github/workflows/daily_report.yml`

- [ ] **Step 1: 스텝 추가**

`📈 종목 스냅샷 빌드 (시세·52주)` 스텝 **직후**(현재 466행 부근)에 삽입한다.

```yaml
      - name: 🌊 시장 국면 빌드 (최근 6개월)
        if: steps.holiday.outputs.open == 'true'
        continue-on-error: true   # 종목 서비스용 — 실패해도 마감 브리핑 발행은 계속(직전 JSON 유지)
        timeout-minutes: 5
        run: python3 scripts/build_market_regime.py
```

> `continue-on-error`를 붙이는 이상 실패가 조용해진다(§32). 신선도 가드가 5일 뒤 섹션을 숨기므로 사용자에게 잘못된 값이 나가지는 않는다.

- [ ] **Step 2: 커밋 대상 확인**

마감 잡의 `💾 HTML & 데이터 커밋` 스텝(488행)이 `git add web/ data/`로 넓게 잡는다. `web/data/market-regime.json`은 이 잡이 단독 소유하므로 그대로 포함되면 된다 — 별도 스텝 불필요. 다른 워크플로가 이 파일을 쓰지 않는지 확인한다.

Run: `grep -rn "market-regime" .github/workflows/`
Expected: `daily_report.yml`의 새 스텝 1건만

- [ ] **Step 3: YAML 유효성 확인**

Run: `python3 -c "import yaml;d=yaml.safe_load(open('.github/workflows/daily_report.yml'));print('jobs:',list(d['jobs']))"`
Expected: `jobs: ['kospi-briefing', 'us-briefing', 'kospi-close-briefing', 'kospi-accuracy']`

- [ ] **Step 4: 커밋**

```bash
git add .github/workflows/daily_report.yml
git commit -m "ci(종목시그널): 마감 잡에 국면 빌드 스텝 추가"
```

---

### Task 14: 전체 검증

- [ ] **Step 1: 파이썬 전체 스위트**

Run: `python3 -m pytest scripts/ tests/ -q`
Expected: 전부 통과 (기존 726건 + 신규 약 28건)

- [ ] **Step 2: 노드 전체 스위트**

Run: `node --test api/*.test.mjs web/assets/*.test.mjs`
Expected: 전부 통과 (기존 218건 + 신규 6건)

- [ ] **Step 3: 빌더 재실행 후 산출물 점검**

```bash
python3 scripts/build_market_regime.py
python3 -c "
import json;d=json.load(open('web/data/market-regime.json'))
assert d['headline'], '헤드라인 없음'
assert d['state'] in ('swap','lead','none')
assert len(d['baskets'])==7, len(d['baskets'])
assert all(b['n_used']>0 for b in d['baskets']), '구성 종목 0개인 바스켓 있음'
print(d['state'],'|',d['headline'])
print('session_date',d['session_date'],'| since',d['regime_since'])
"
```

Expected: 검증 통과 + 상태·문구 출력

- [ ] **Step 4: 최종 커밋**

```bash
git add web/data/market-regime.json
git commit -m "chore(종목시그널): 국면 데이터 초기 산출물"
```

---

## Self-Review

**스펙 커버리지**

| 스펙 항목 | 태스크 |
| --- | --- |
| 배치 (코스피 주도주 아래) | 11 |
| 바스켓 7개 · 별도 config | 1 |
| 126영업일 롤링 · 단순평균 | 2 |
| 결측 종목 제외 · `n_used` | 2, 14 |
| 한국 거래일 정렬 (직전값) | 2 |
| 러닝 정점 대비 거리 | 3 |
| 임계값 3종 | 3, 4, 5 |
| 히스테리시스를 입력에 적용 | 4 |
| 최소 국면 10일 | 5 |
| 상태 3종 | 4 |
| 문구 템플릿 3종 · 슬롯 정렬 | 6 |
| 조사 분기 | 6 |
| 국면 단위 문구 확정 | 7 |
| 헤드라인 글로벌 한정 | 7, 9 |
| 한국 read-through | 10, 11 |
| JSON 스키마 | 10 |
| `swap`/`lead`/`none` 레이아웃 | 11 |
| 반응형 | 12 |
| `.ds-asof` 미사용 | 11 (`regime-asof` 별도 요소) |
| 신선도 가드 5일 | 11 |
| 파이프라인 · `continue-on-error` | 13 |
| 문구 실패 0건 검증 | 9 |
| 관찰 국면 재현 검증 | 9 |
| 전환 15회 이하 검증 | 9 |

누락 없음.

**플레이스홀더 스캔** — 모든 스텝에 실제 코드·명령·기대 출력이 있다. "적절히 처리" 류 없음.

**타입 일관성** — `basket_cum` → `(list|None, int)`, `daily_frames` → `list[dict]`, `qualifying_sets` → `(set, set)`, `resolve_regimes` → `list[dict]`로 태스크 2·3·4·7·9·10에서 동일하게 쓰인다. 프런트는 `window.__marketRegime.regimeRender`로 태스크 11 테스트·구현이 일치한다.

**주의** — 태스크 9의 `test_reproduces_observed_regimes`는 픽스처를 재생성하면 날짜 기준이 바뀔 수 있다. 픽스처는 태스크 8에서 한 번 만들고 커밋한 뒤 재생성하지 않는다.
