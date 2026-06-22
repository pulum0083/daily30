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
