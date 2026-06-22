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
