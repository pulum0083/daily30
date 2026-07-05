# 코스피 방향 prior 재보정 — 하락 편향 교정 + USD/KRW 신호 추가

작성일: 2026-07-05
상태: 설계 승인 대기
선행 문서: [2026-06-22-kospi-direction-leading-signal-prior-design.md](2026-06-22-kospi-direction-leading-signal-prior-design.md)
대상 파일: `scripts/leading_signal.py` (주), `scripts/diagnose_direction_signals.py` (검증)

---

## 1. 문제 정의

코스피 시초가 방향 예측이 **체계적 하락 편향**을 보인다. 실측 성적(`data/briefings.json`, 채점 완료 58건):

- 코스피 방향 적중률 **64%** (37/58), 최근 25건은 60%로 하락 추세.
- **혼동행렬**: 예측=상승 적중 75%(27/36) vs **예측=하락 적중 45%(10/22)**.
- 즉 모델이 "하락 우위"를 내면 절반 이상 틀린다. 실제 상승일 비율(base rate)이 63~67%인데 prior가 이를 반영하지 못한다.

원인은 두 가지다.

**(A) 결합 prior가 최강 신호를 희석한다.** 백테스트(84거래일, 2026-03~07):

| 룰 | 적중률 | 하락콜 정밀도 |
|---|---|---|
| 무조건 상승 (base rate) | 63.1% | — |
| 현행 결합 prior (sox1·ewy1·nasdaq0.4·nq0.3·vix-0.2, 대칭밴드 ±0.5) | 65.5% | 53% (32건) |
| SOX 단독 (부호) | 67.9% | 58% |

EWY는 단독 적중률 61.4%로 5개 신호 중 최약인데, SOX와 동일 가중 1.0으로 들어가 결합 prior를 SOX 단독보다 **낮게** 만든다.

**(B) 데드밴드가 대칭이라 상승 드리프트를 무시한다.** 상승일이 63% 나오는 레짐에서 score가 0 부근으로 대칭 판정하면 하락 콜이 과다 발화한다.

## 2. 목표 · 성공 기준

`diagnose_direction_signals.py`(USD/KRW 반영하도록 확장)를 재실행했을 때:

1. 결합 prior 적중률 **≥ 67%** 그리고 현행(65.5%) 대비 상승.
2. 하락콜 정밀도 **≥ 58%** (현행 53% 대비 개선).
3. 결합 prior가 SOX 단독보다 낮지 않을 것.
4. `[출시 게이트]` 라인(결합prior > 모멘텀)이 계속 PASS.

백테스트 근거(같은 84일 표본, USD/KRW 포함):

| 룰 | 적중률 | 하락콜 정밀도 |
|---|---|---|
| SOX-heavy 재가중 + 비대칭밴드 | 67.9% | 58% (26건) |
| **+ USD/KRW 추가** | **69.0%** | **61% (23건)** |

## 3. 설계 (접근 A — prior 재보정)

신호가 실제로 계산되는 `scripts/leading_signal.py` 한 곳을 외과적으로 수정한다. 사후 캘리브레이션 레이어(접근 B)나 프롬프트 주입(접근 C)은 복잡도·비결정성 때문에 채택하지 않는다.

### 3.1 USD/KRW 신호 추가 (`extract_signals`)

USD/KRW 등락률은 이미 `fetch_data`가 매 실행 수집해 `latest_kospi.json`의 `market_data_js["usd"]["chg"]`에 있으나 prior에는 미사용이다. 환율은 외국인 자금 방향의 직접 프록시라 이론·실증 모두 부합한다.

```python
# extract_signals() 반환에 추가
"usdkrw": from_mdj("usd"),   # market_data_js.usd.chg (원/달러 등락률)
```

부호 규약: **원화 약세(USD/KRW 상승) = 코스피 하락 압력** → 가중치는 음수.

### 3.2 가중치 재보정 (`SIGNAL_WEIGHTS`)

SOX를 최강 신호로 승격하고 EWY를 강등한다. 최종 수치는 §4 백테스트로 확정하되, 승인된 시작값은 다음과 같다.

```python
SIGNAL_WEIGHTS = {
    "sox":    1.5,   # 최강 단일 신호 (단독 67.9%) — 승격
    "nasdaq": 0.5,
    "nq":     0.3,   # 프리마켓 선물 — 신선도 보정용 유지 (백테스트 표본엔 미포함, 소가중)
    "ewy":    0.3,   # 최약 신호 — 강등 (1.0 → 0.3)
    "vix":   -0.2,
    "usdkrw":-0.8,   # 신규 — 원화 약세 = 하락 압력
}
```

### 3.3 비대칭 데드밴드

대칭 `NEUTRAL_BAND = 0.5`를 상·하 분리한다. 상승 드리프트를 prior에 내장하되, "무조건 상승" 하드코딩이 아니라 **"하락 판정에는 더 강한 음의 증거를 요구"**하는 설계다.

```python
UP_BAND =  0.3    # score >  +0.3 → 상승
DN_BAND = -1.2    # score <  -1.2 → 하락, 그 사이는 중립
```

`compute_prior`의 판정부를 `NEUTRAL_BAND` 단일 비교에서 `UP_BAND`/`DN_BAND` 이중 비교로 교체한다. `NEUTRAL_BAND` 상수는 제거한다.

### 3.4 건드리지 않는 것

- `_strength()` 게이트는 그대로 둔다 (SOX·EWY 부호 일치 기준). USD/KRW를 strong 판정에 넣는 건 이번 범위 밖(향후 과제). 오버라이드는 여전히 strong일 때만 발동하므로 보수적으로 유지된다.
- 미국 prior(`compute_prior_us` 등)는 이번 변경 대상 아님. 코스피 전용 문제다.
- `format_prior_for_prompt` 텍스트 블록에 USD/KRW 한 줄 추가(표시용). 로직 변경 없음.

## 4. 검증

`scripts/diagnose_direction_signals.py`를 확장해 회귀 게이트로 쓴다.

1. `US_TICKERS`에 `"USDKRW=X": "usdkrw"` 추가 — 결합 prior 평가에 USD/KRW 반영.
2. 재실행 후 §2 성공 기준 4개 모두 충족 확인.
3. 미충족 시 §3.2 가중치·§3.3 밴드를 표본 내에서 재조정하되, **정확한 수치보다 방향성(SOX>결합, USD/KRW 추가, 비대칭밴드)이 견고**하므로 소수점 과최적화는 피한다.

최소 단위 검증(신규 또는 기존 테스트 파일에 추가):

- `extract_signals`가 `market_data_js.usd.chg`에서 `usdkrw`를 뽑는다.
- 밴드 경계: score `+0.4`→상승, `-0.8`→중립, `-1.5`→하락.

## 5. 한계 · 비목표 (YAGNI)

- **in-sample 튜닝**: 84일 표본 내 최적화라 실측 개선폭은 백테스트(+3.5pp)보다 작을 수 있다. 배포 후 `briefings.json` 실측으로 재확인한다.
- **레짐 의존**: 비대칭밴드는 상승장(63% up) 기준이다. 하락장 전환 시 DN_BAND를 재점검한다(설계에 명시적 주석).
- **대만(TWII) 제외**: USD/KRW 위에 얹으면 추가 이득 0 (69.0% 동일). 넣지 않는다.
- **토큰 지수 제외**: AI 추론 토큰 처리량은 월·분기 저빈도라 "오늘 방향" prior엔 부적합. 방향이 아닌 중기 confidence 톤 요소로는 여지가 있으나 **별도 건**으로 분리한다.
- **사후 캘리브레이션 레이어(접근 B) 제외**: 이득이 A와 겹치고 복잡도만 는다.

## 6. 롤백

단일 파일 변경이므로 `git revert`로 즉시 원복. 배포 전 `diagnose_direction_signals.py` 게이트가 PASS를 강제하므로 성적 저하 상태로는 배포되지 않는다.
