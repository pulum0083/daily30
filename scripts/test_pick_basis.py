# 종목 픽 산출 근거 노출 + 손절가 20일선 검증 — 2026-09-02 신설.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import validate_analysis as va  # noqa: E402
from generate_html import _fmt_level  # noqa: E402


def _pick(**over):
    p = {"name": "SK하이닉스", "ticker": "000660", "price": "1,693,000원",
         "stop": "1,605,000원", "stop_pct": "-5.2%",
         "action_guide": "시가 대비 -1% 이내 진입. 목표: +3% 부근 / 손절: 20일선(약 1,605,000원) 이탈 시."}
    p.update(over)
    return p


def _run(pick, ma20, is_us=False):
    corr, warn = [], []
    va._verify_stop_against_ma20(pick, ma20, is_us, corr, warn)
    return corr, warn


def test_accurate_stop_untouched():
    """실사고 조사 당시 실제 값 — 오차 -0.17%면 손대지 않는다(오교정 방지)."""
    p = _pick()
    corr, _ = _run(p, 1607750)
    assert corr == []
    assert p["stop"] == "1,605,000원"


def test_wrong_stop_corrected_to_measured_ma20():
    """20일선이라 써놓고 전혀 다른 값이면 실측으로 덮어쓴다."""
    p = _pick(stop="1,400,000원")
    corr, _ = _run(p, 1607750)
    assert len(corr) == 1 and "손절가 교정" in corr[0]
    assert p["stop"] == "1,607,750원"
    # stop_pct도 현재가 기준으로 다시 만든다 (1,693,000 → 1,607,750 = -5.0%)
    assert p["stop_pct"] == "-5.0%"


def test_no_ma20_claim_is_not_judged():
    """20일선을 근거로 내세우지 않았으면 판단하지 않는다 — 다른 근거일 수 있다."""
    p = _pick(stop="1,400,000원", action_guide="시가 진입. 손절: 전 저점 이탈 시.")
    corr, _ = _run(p, 1607750)
    assert corr == [] and p["stop"] == "1,400,000원"


def test_ma20_claim_variants_detected():
    for guide in ["손절: 20일선 이탈", "20 일 선 이탈 시", "손절 20일 이동평균 하회", "stop at MA20", "20MA 이탈"]:
        p = _pick(stop="1,000,000원", action_guide=guide)
        corr, _ = _run(p, 1607750)
        assert corr, guide


def test_missing_ma20_is_fail_open():
    """실측 20일선이 없으면 판단하지 않는다 — 없는 근거로 교정하지 않는다."""
    p = _pick(stop="1,400,000원")
    for bad in (None, 0, "x"):
        corr, _ = _run(_pick(stop="1,400,000원"), bad)
        assert corr == []
    assert p["stop"] == "1,400,000원"


def test_us_pick_formats_in_dollars():
    p = _pick(name="NVDA", price="$180.00", stop="$120.00",
              action_guide="Stop below MA20.")
    corr, _ = _run(p, 175.5, is_us=True)
    assert p["stop"] == "$175.50"
    assert p["stop_pct"] == "-2.5%"


def test_unparseable_price_drops_stop_pct():
    """현재가를 못 읽으면 stop_pct를 지운다 — 틀린 비율을 남기지 않는다."""
    p = _pick(price="—", stop="1,400,000원")
    corr, warn = _run(p, 1607750)
    assert p["stop"] == "1,607,750원"
    assert "stop_pct" not in p and warn


def test_fmt_level():
    assert _fmt_level(1607750, "kospi") == "1,607,750원"
    assert _fmt_level(175.5, "us") == "$175.50"
    # 없으면 빈 문자열 — 카드에서 근거 문장이 통째로 빠진다(지어내지 않는다)
    assert _fmt_level(None, "kospi") == ""
    assert _fmt_level("x", "kospi") == ""
