# 뉴스 주장이 실측 시장데이터와 모순되면 차단하는 게이트 테스트.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_news import _drop_reality_contradictions, _claim_direction  # noqa: E402

# 2026-07-27 실측: WTI -6.05%, 브렌트 -6.67%
REAL_DOWN = {"oil": -6.05}
REAL_UP = {"oil": +3.20}


def test_direction_up_words():
    for t in ("국제유가 급등", "유가 상승세 지속", "유가 80달러 돌파", "유가 강세"):
        assert _claim_direction(t, "유가") == "up", t


def test_direction_down_words():
    for t in ("국제유가 급락", "유가 하락 전환", "유가 약세", "유가 폭락"):
        assert _claim_direction(t, "유가") == "down", t


def test_direction_none_when_absent():
    assert _claim_direction("코스피 외국인 순매수 확대", "유가") is None
    assert _claim_direction("국제유가 동향 주목", "유가") is None


def test_real_incident_oil_reversed():
    """실사고: 실측 -6.05%인데 '유가 상승·에너지주 강세'가 통과했다."""
    items = [
        "국제 유가(WTI 기준) 배럴당 80달러 돌파 → 에너지 관련주 상승세",
        "중동 지정학적 긴장 완화 속 국제유가 상승세 지속",
        "코스피 외국인 순매수 확대 → 대형주 강세",
    ]
    kept = _drop_reality_contradictions(items, REAL_DOWN)
    assert kept == [items[2]], kept


def test_matching_direction_survives():
    """실측과 방향이 같으면 통과시킨다."""
    items = ["중동 긴장 완화 → 국제유가 급락, 에너지주 약세"]
    assert _drop_reality_contradictions(items, REAL_DOWN) == items


def test_up_real_drops_down_claim():
    """반대 방향도 대칭으로 잡는다."""
    items = ["유가 급락으로 정유주 부담"]
    assert _drop_reality_contradictions(items, REAL_UP) == []


def test_no_real_data_fails_open():
    """실측이 없으면 판단하지 않는다 — 정상 항목 오제거 방지."""
    items = ["국제유가 급등 → 에너지주 강세"]
    assert _drop_reality_contradictions(items, {}) == items
    assert _drop_reality_contradictions(items, {"oil": None}) == items


def test_dict_form():
    items = [{"date": "2026-07-27", "text": "유가 상승세 → 에너지주 강세"}]
    assert _drop_reality_contradictions(items, REAL_DOWN) == []


def test_empty_input():
    assert _drop_reality_contradictions([], REAL_DOWN) == []
    assert _drop_reality_contradictions(None, REAL_DOWN) == []


if __name__ == "__main__":
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            fn_()
            print(f"✅ {name}")
    print("모든 테스트 통과")
