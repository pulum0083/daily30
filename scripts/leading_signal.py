# 코스피 시초가 방향 예측용 선행신호 prior를 결정론적으로 계산하는 순수 모듈
"""
latest_kospi.json의 선행신호 등락률에서 방향 prior(상승/하락/중립)와 강도를 계산한다.
SOX·나스닥·NQ선물은 market_data_js.*.chg, EWY·VIX는 최상위 *.change_pct 에 있다.
가중치·임계값은 scripts/diagnose_direction_signals.py 백테스트로 확정한다(초기값은 74일 진단 기반).
"""

# 진단 기반 재보정값 — 백테스트(diagnose_direction_signals.py)로 확정
SIGNAL_WEIGHTS = {"sox": 1.5, "nasdaq": 0.5, "nq": 0.3, "ewy": 0.3, "vix": -0.2, "usdkrw": -0.8}
# 비대칭 데드밴드: 상승 드리프트(base 63% up)를 내장 — 하락 판정에 더 강한 음의 증거를 요구.
# 레짐 전환(하락장) 시 DN_BAND 재점검 필요.
UP_BAND =  0.3    # score >  UP_BAND → 상승
DN_BAND = -1.2    # score <  DN_BAND → 하락, 그 사이는 중립
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

    def from_fut(key):   # futures.{key}.change_pct
        v = (latest.get("futures") or {}).get(key)
        return v.get("change_pct") if isinstance(v, dict) else None

    return {
        "sox":    from_mdj("sox"),
        "nasdaq": from_mdj("nasdaq"),
        "nq":     from_mdj("nq"),
        "ewy":    from_top("ewy"),
        "vix":    from_top("vix"),
        "usdkrw": from_mdj("usd"),   # market_data_js.usd.chg (원/달러 등락률, 원화 약세=하락 압력)
        # 아래 둘은 가중 합산에 직접 쓰지 않고 EWY 잔차 계산에만 쓴다
        "kospi":  from_mdj("kospi"),               # 직전 코스피 세션 등락률
        "post_holiday": bool(latest.get("post_holiday_catchup")),
        # 실시간 미 지수선물 — 아직 score에 넣지 않는다(가중치 미피팅). 프롬프트 참고용.
        "es":     from_fut("sp500_fut"),
        "ym":     from_fut("dow_fut"),
    }


def ewy_residual(sig: dict):
    """EWY 등락률에서 '이미 실현된 코스피 등락분'을 뺀 잔차.

    EWY(iShares MSCI Korea)는 같은 날 코스피 종가를 그대로 반영한다. 그래서 EWY 등락률을
    통째로 선행신호로 쓰면 **어제 이미 일어난 하락을 오늘 악재로 두 번 세게 된다.**
    (2026-07-24: 코스피 -5.72%, EWY -6.27% → 실제 신규 정보는 잔차 -0.55%뿐인데
     기존 계산은 -6.27×0.3 = -1.88을 통째로 넣어 그것만으로 DN_BAND(-1.2)를 넘겼다.)
    §24가 서사 차원에서 명시한 방지 룰을 prior 계산에도 적용한 것이다.

    잔차 = EWY% − 직전 코스피 세션% — 즉 **미국 시간대에 새로 매겨진 한국 가격**만 남긴다.
    환율 조정은 하지 않는다. usdkrw가 이미 별도 항(가중 -0.8)으로 들어가 있어
    여기서 또 반영하면 FX를 이중 계상한다.

    두 경우엔 잔차를 쓰지 않고 원본 EWY를 그대로 돌려준다.
      · 코스피 등락률이 없을 때 — 뺄 기준이 없다
      · 한국만 단독 휴장한 다음날(post_holiday_catchup) — 두 값의 세션 날짜가 어긋난다.
        이때 EWY 등락은 코스피에 아직 반영된 적 없는 '진짜 신규 정보'가 맞다.
    """
    ewy = sig.get("ewy")
    if ewy is None:
        return None
    kospi = sig.get("kospi")
    if kospi is None or sig.get("post_holiday"):
        return ewy
    return round(ewy - kospi, 3)


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
    # EWY는 원본이 아니라 잔차로 합산한다(이중 계상 제거). 표시용 원본은 signals에 그대로 남긴다.
    sig["ewy_resid"] = ewy_residual(sig)
    score = 0.0
    used = False
    for key, w in SIGNAL_WEIGHTS.items():
        v = sig["ewy_resid"] if key == "ewy" else sig.get(key)
        if v is not None:
            score += w * v
            used = True
    if not used:
        return {"direction": "중립", "score": 0.0, "strength": "weak", "signals": sig}
    if score > UP_BAND:
        direction = "상승"
    elif score < DN_BAND:
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
        f"· EWY {fmt(sig.get('ewy'))} · 원/달러 {fmt(sig.get('usdkrw'))} · VIX {fmt(sig.get('vix'))}",
        "- 이 값들은 직전 미국장 종가로, 전일 한국 마감 **이후** 정보를 반영한다.",
    ]
    live = [(n, sig.get(k)) for n, k in (("S&P선물", "es"), ("NQ선물", "nq"), ("다우선물", "ym"))
            if sig.get(k) is not None]
    if live:
        lines.append(
            "- **지금 이 순간 살아있는 유일한 신호 — 미 지수선물**: "
            + " · ".join(f"{n} {fmt(v)}" for n, v in live)
            + ". 위 SOX·나스닥·EWY는 전부 직전 미국장 **종가**라 6시간 이상 묵은 값이고, 선물은"
            " 브리핑 생성 시각까지 계속 거래된 값이다. **종가와 선물 방향이 엇갈리면 선물이 더 신선한"
            " 정보다.** (단 선물은 아직 score 가중 합산에 넣지 않았으므로 위 score에는 반영돼 있지 않다 —"
            " 판단할 때 별도로 감안하라.)"
        )
    resid = sig.get("ewy_resid")
    if resid is not None and sig.get("kospi") is not None and resid != sig.get("ewy"):
        lines.append(
            f"- **EWY 이중 계상 주의**: EWY {fmt(sig.get('ewy'))} 중 직전 코스피 {fmt(sig.get('kospi'))}는"
            f" **이미 실현된 하락/상승분**이다. 오늘 새로 들어온 정보는 잔차 **{fmt(resid)}**뿐이다."
            " prior는 이 잔차로 계산했다. 본문에서도 EWY 등락률 전체를 '간밤 새로 들어온 악재/호재'로"
            " 쓰지 말고, 쓰려면 반드시 직전 코스피 등락률과 함께 제시해 중복분을 드러내라."
        )
    lines += [
        "- **충돌 해소 규칙**: 전일 코스피가 ±3% 이상 크게 움직인 다음날, 위 선행신호가 전일 국내 방향과 "
        "모순되면 — 더 신선한 정보이므로 — **선행신호(prior) 방향을 따른다.** 전일 국내 등락에 앵커링하지 않는다.",
    ]
    return "\n".join(lines) + "\n"


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


# ── 미국 브리핑용 prior (advisory 주입 전용 — 하드 오버라이드 없음) ──────────────
# 미국 브리핑은 개장 전 프리마켓 선물(ES/NQ/YM)이 가장 신선한 선행신호다.
# EWY는 한국 외국인 프록시라 무관하므로 쓰지 않는다.
US_SIGNAL_WEIGHTS = {"sp500_fut": 1.0, "nasdaq_fut": 1.0, "dow_fut": 0.3, "sox": 0.5, "vix": -0.2}
NEUTRAL_BAND_US = 0.3   # 선물은 변동폭이 작아 코스피보다 좁은 데드밴드
T_FUT_US = 0.5          # strength 표기용 선물 임계 (%) — advisory라 게이트 아님


def extract_signals_us(latest: dict) -> dict:
    """latest_us.json에서 미국 선행신호 등락률을 추출. 누락 필드는 None."""
    futures = latest.get("futures") or {}
    mdj = latest.get("market_data_js") or {}

    def from_fut(key):   # futures.{key}.change_pct
        v = futures.get(key)
        return v.get("change_pct") if isinstance(v, dict) else None

    sox = mdj.get("sox")
    vix = latest.get("vix")
    return {
        "sp500_fut":  from_fut("sp500_fut"),
        "nasdaq_fut": from_fut("nasdaq_fut"),
        "dow_fut":    from_fut("dow_fut"),
        "sox":        sox.get("chg") if isinstance(sox, dict) else None,
        "vix":        vix.get("change_pct") if isinstance(vix, dict) else None,
    }


def _strength_us(sig: dict, direction: str) -> str:
    """미국 prior 강도 (표기용 — 오버라이드 게이트 아님)."""
    prim = [x for x in (sig.get("sp500_fut"), sig.get("nasdaq_fut")) if x is not None and x != 0]
    if direction == "중립" or not prim:
        return "weak"
    agree = all((x > 0) == (prim[0] > 0) for x in prim)
    if not agree:
        return "weak"
    vix = sig.get("vix")
    vix_contra = vix is not None and (
        (direction == "상승" and vix > VIX_CONTRA) or
        (direction == "하락" and vix < -VIX_CONTRA)
    )
    if any(abs(x) >= T_FUT_US for x in prim) and not vix_contra:
        return "strong"
    return "mid"


def compute_prior_us(latest: dict) -> dict:
    """미국 브리핑 선행신호 prior 계산 (반환 형태는 compute_prior와 동일)."""
    sig = extract_signals_us(latest)
    score = 0.0
    used = False
    for key, w in US_SIGNAL_WEIGHTS.items():
        v = sig.get(key)
        if v is not None:
            score += w * v
            used = True
    if not used:
        return {"direction": "중립", "score": 0.0, "strength": "weak", "signals": sig}
    if score > NEUTRAL_BAND_US:
        direction = "상승"
    elif score < -NEUTRAL_BAND_US:
        direction = "하락"
    else:
        direction = "중립"
    return {
        "direction": direction,
        "score": round(score, 3),
        "strength": _strength_us(sig, direction),
        "signals": sig,
    }


def format_prior_for_prompt_us(prior: dict) -> str:
    """미국 prior를 LLM 프롬프트에 주입할 한국어 텍스트 블록으로 포맷 (advisory)."""
    sig = prior["signals"]
    def fmt(v):
        return f"{v:+.2f}%" if isinstance(v, (int, float)) else "—"
    lines = [
        "\n## 🧭 선행신호 방향 prior (Python 결정론 계산 — 우선 참고)",
        f"- 계산 방향: **{prior['direction']}** (강도 {prior['strength']}, score {prior['score']})",
        f"- S&P선물 {fmt(sig.get('sp500_fut'))} · 나스닥선물 {fmt(sig.get('nasdaq_fut'))} "
        f"· 다우선물 {fmt(sig.get('dow_fut'))} · SOX {fmt(sig.get('sox'))} · VIX {fmt(sig.get('vix'))}",
        "- 이 값들은 미국장 개장 전 프리마켓 선물·반도체로, 전일 미국 현물 마감 **이후** 정보를 반영한다.",
        "- **충돌 해소 규칙**: 전일 미국 현물이 크게 움직였더라도 프리마켓 선물(S&P·나스닥)·SOX가 그와 "
        "모순되면 — 더 신선한 정보이므로 — 선물 방향을 우선 참고한다. 전일 마감에 앵커링하지 않는다.",
    ]
    return "\n".join(lines) + "\n"
