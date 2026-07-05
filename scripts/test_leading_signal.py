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


def test_direction_contradicts_strong():
    assert ls.prior_contradicts_direction({"direction": "상승", "strength": "strong"}, "하락 우위") is True
    assert ls.prior_contradicts_direction({"direction": "상승", "strength": "strong"}, "상승 우위") is False
    # mid 강도는 오버라이드 비대상
    assert ls.prior_contradicts_direction({"direction": "상승", "strength": "mid"}, "하락 우위") is False
    # 중립 prior는 비대상
    assert ls.prior_contradicts_direction({"direction": "중립", "strength": "strong"}, "하락 우위") is False


# ── 미국 브리핑 prior (advisory) ───────────────────────────────────────────────
def _latest_us(sp=None, nq=None, dow=None, sox=None, vix=None):
    """latest_us.json 구조 일부를 흉내낸 fixture (선물은 futures.*.change_pct, SOX는 market_data_js)."""
    return {
        "futures": {
            "sp500_fut":  {"change_pct": sp} if sp is not None else {},
            "nasdaq_fut": {"change_pct": nq} if nq is not None else {},
            "dow_fut":    {"change_pct": dow} if dow is not None else {},
        },
        "market_data_js": {"sox": {"chg": sox} if sox is not None else {}},
        "vix": {"change_pct": vix} if vix is not None else {},
    }


def test_extract_signals_us_paths():
    sig = ls.extract_signals_us(_latest_us(sp=0.39, nq=1.11, dow=0.27, sox=1.05, vix=7.32))
    assert sig["sp500_fut"] == 0.39
    assert sig["nasdaq_fut"] == 1.11
    assert sig["dow_fut"] == 0.27
    assert sig["sox"] == 1.05
    assert sig["vix"] == 7.32


def test_compute_prior_us_up_from_futures():
    # 선물 상승 + SOX 상승 → 상승 prior (전일 현물 약세와 무관하게)
    p = ls.compute_prior_us(_latest_us(sp=0.39, nq=1.11, dow=0.27, sox=1.05, vix=7.32))
    assert p["direction"] == "상승"


def test_compute_prior_us_handles_missing_futures():
    # nasdaq_fut 누락(None)이어도 안전하게 계산
    p = ls.compute_prior_us(_latest_us(sp=-0.5, dow=-0.3, sox=-2.0, vix=5.0))
    assert p["direction"] == "하락"
    assert p["signals"]["nasdaq_fut"] is None


def test_compute_prior_us_neutral_when_empty():
    p = ls.compute_prior_us({"futures": {}, "market_data_js": {}})
    assert p["direction"] == "중립" and p["strength"] == "weak"


def test_format_prior_us_contains_futures():
    p = ls.compute_prior_us(_latest_us(sp=0.39, nq=1.11, dow=0.27, sox=1.05, vix=7.32))
    text = ls.format_prior_for_prompt_us(p)
    assert "선물" in text and "SOX" in text and "1.11" in text


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
