# 지수 '사상 최고/최저' 정성 주장 실측 대조 게이트 테스트 (2026-07-29 실사고 §28)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_analysis import (  # noqa: E402
    find_superlative_violations,
    validate_index_superlatives,
)

# 2026-07-29 실측: 나스닥 24,876.91 (-0.22%), 52주 고점은 그보다 위
REAL = {
    "^IXIC": {"level": 24876.91, "change_pct": -0.22,
              "high_52w": 27500.0, "low_52w": 19000.0},
    "^SOX": {"level": 11035.68, "change_pct": -4.49,
             "high_52w": 13000.0, "low_52w": 8000.0},
}


def test_incident_claim_is_caught():
    """실사고 원문 — 숫자가 하나도 없는 '사상 최고치 경신' 주장."""
    text = "간밤 미국 증시는 나스닥이 사상 최고치를 경신하는 등 기술주 강세를 보였지만"
    assert find_superlative_violations(text, REAL), "실사고 문장을 못 잡음"


def test_html_tags_stripped():
    text = "🇺🇸 나스닥은 <b>사상 최고치</b>인데 지금 나스닥 선물은 <b>-0.78%</b>로 주춤해요."
    assert find_superlative_violations(text, REAL)


def test_genuine_record_high_passes():
    """실제로 신고가면 통과해야 한다 — 오탐이 나면 정상 브리핑을 막는다."""
    real = {"^IXIC": {"level": 27500.0, "change_pct": 1.2,
                      "high_52w": 27500.0, "low_52w": 19000.0}}
    assert not find_superlative_violations("나스닥이 사상 최고치를 경신했어요", real)


def test_other_subject_superlative_not_matched():
    """주어가 다른 최상급은 지수 주장으로 오인하지 않는다(앞뒤 25자 창)."""
    text = ("나스닥은 소폭 밀렸어요. 그동안 지정학 불안이 이어지면서 안전자산 선호가 커졌고, "
            "국제 금값은 사상 최고치를 새로 썼어요.")
    assert not find_superlative_violations(text, REAL)


def test_no_realdata_is_fail_open():
    assert not find_superlative_violations("나스닥이 사상 최고치를 경신", {})


def test_low_superlative_caught():
    real = {"^SOX": {"level": 11035.68, "change_pct": 2.1,
                     "high_52w": 13000.0, "low_52w": 8000.0}}
    hits = find_superlative_violations("필라델피아 반도체가 신저가를 썼어요", real)
    assert hits and "최저" in hits[0]


def test_list_item_dropped_scalar_blocks(monkeypatch=None):
    """리스트 항목은 제거, 스칼라 산문에 남으면 차단."""
    import validate_analysis as va
    orig = va._index_extremes
    va._index_extremes = lambda sym: REAL.get(sym)
    try:
        a = {
            "us_issues": [
                {"title": "나스닥 사상 최고치 경신", "body": "간밤 나스닥이 신고가를 썼어요"},
                {"title": "정상 항목", "body": "SOX가 <b>-4.49%</b> 밀렸어요"},
            ],
            "why": "SOX는 -4.49% 하락했어요.",
        }
        corr, warn, blocks = [], [], []
        validate_index_superlatives(a, corr, warn, blocks)
        assert len(a["us_issues"]) == 1, a["us_issues"]
        assert corr and not blocks

        a2 = {"why": "간밤 나스닥이 사상 최고치를 경신했어요."}
        corr, warn, blocks = [], [], []
        validate_index_superlatives(a2, corr, warn, blocks)
        assert blocks, "스칼라 산문 위반은 차단돼야 함"
    finally:
        va._index_extremes = orig


def test_no_superlative_skips_network():
    """최상급 표현이 없으면 실측 조회 자체를 하지 않는다."""
    import validate_analysis as va
    orig = va._index_extremes

    def boom(sym):
        raise AssertionError("네트워크 조회가 일어나면 안 됨")

    va._index_extremes = boom
    try:
        corr, warn, blocks = [], [], []
        validate_index_superlatives({"why": "나스닥이 -0.22% 밀렸어요."}, corr, warn, blocks)
        assert not (corr or warn or blocks)
    finally:
        va._index_extremes = orig


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"✅ {name}")
            except AssertionError as e:
                fails += 1
                print(f"❌ {name}: {e}")
    print("모든 테스트 통과" if not fails else f"{fails}건 실패")
    sys.exit(1 if fails else 0)
