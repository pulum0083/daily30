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
