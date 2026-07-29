# 수집 단계 지수 실측 대조 게이트 테스트 — 방향·레벨·최상급 (2026-07-29 실사고 §28)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_news import (  # noqa: E402
    _drop_prompt_slot_echoes,
    _drop_reality_contradictions,
)

# 2026-07-29 실측 (사이드바 fetch_data 기준): 나스닥 -0.22%, SOX -4.49%, S&P +0.24%
REAL = {
    "nasdaq": {"change_pct": -0.22, "level": 24876.91,
               "high_52w": 27500.0, "low_52w": 19000.0},
    "sp500": {"change_pct": 0.24, "level": 7411.98,
              "high_52w": 7600.0, "low_52w": 5800.0},
    "sox": {"change_pct": -4.49, "level": 11035.68,
            "high_52w": 13000.0, "low_52w": 8000.0},
    "oil": {"change_pct": -1.2, "level": 83.9, "high_52w": None, "low_52w": None},
}

# 실사고 원문 (data/news_summary_kospi.json, 2026-07-29 07:26 KST)
INCIDENT = (
    "간밤 미국 증시, 기술주 강세 속 혼조 마감. S&P 500 지수는 0.3% 상승한 5,500선을 "
    "돌파했으며, 나스닥 지수도 0.5% 오르며 사상 최고치를 경신했습니다."
)


def test_incident_item_is_dropped():
    assert _drop_reality_contradictions([INCIDENT], REAL) == []


def test_superlative_without_number_dropped():
    """숫자 없는 '사상 최고' 주장 — 등락률 게이트가 못 잡는 형태."""
    assert _drop_reality_contradictions(["나스닥이 사상 최고치를 경신했습니다"], REAL) == []


def test_level_wrong_but_direction_right_dropped():
    """방향은 맞고 레벨만 틀린 형태 — 방향 게이트만으론 통과한다."""
    items = ["S&P500 지수가 0.3% 상승하며 5,500선을 돌파했습니다"]
    assert _drop_reality_contradictions(items, REAL) == []


def test_correct_level_kept():
    items = ["S&P500이 7,400선을 회복하며 0.2% 올랐습니다"]
    assert _drop_reality_contradictions(items, REAL) == items


def test_direction_contradiction_still_works():
    """기존 §27 방향 게이트가 지수에도 그대로 적용된다."""
    assert _drop_reality_contradictions(["나스닥이 강세를 보이며 상승 마감"], REAL) == []


def test_measured_correct_narrative_kept():
    """실측과 일치하는 서술은 남는다 — 오제거는 브리핑을 비게 만든다."""
    items = ["나스닥이 0.22% 하락 마감했고, 필라델피아 반도체는 4.49% 급락했습니다"]
    assert _drop_reality_contradictions(items, REAL) == items


def test_fail_open_when_no_realdata():
    items = [INCIDENT]
    assert _drop_reality_contradictions(items, {}) == items


def test_oil_gate_unchanged():
    """§27 유가 게이트가 스냅샷 구조 변경 후에도 동작한다."""
    assert _drop_reality_contradictions(["국제유가가 상승세를 이어갔습니다"], REAL) == []
    keep = ["국제유가가 하락하며 에너지주가 밀렸습니다"]
    assert _drop_reality_contradictions(keep, REAL) == keep


def test_oil_dollar_level_gate():
    """유가는 자릿수가 짧아 지수 레벨 패턴에 안 걸린다 — 달러 표기를 따로 본다."""
    real = {"oil": {"change_pct": -1.2, "level": 83.91,
                    "high_52w": None, "low_52w": None}}
    assert _drop_reality_contradictions(["WTI가 배럴당 40달러 선까지 하락했습니다"], real) == []
    keep = ["WTI가 배럴당 84달러 선에서 하락 마감했습니다"]
    assert _drop_reality_contradictions(keep, real) == keep


def test_level_tolerance_is_not_hair_trigger():
    """±15% 안쪽 오차는 통과시킨다 — 벤치마크·시점 차이로 정상 항목을 오제거하지 않기 위함.

    실사고의 'WTI 78달러'(실측 83.91, -7%)는 이 정책상 의도적으로 통과한다.
    명백한 학습시점 레벨 날조(S&P 5,500 vs 7,412 = -26%)만 잡는 것이 이 게이트의 목적이다.
    """
    real = {"oil": {"change_pct": -1.2, "level": 83.91,
                    "high_52w": None, "low_52w": None}}
    keep = ["WTI는 배럴당 78달러 선에서 거래되며 하락했습니다"]
    assert _drop_reality_contradictions(keep, real) == keep


def test_slot_echo_dropped():
    """프롬프트 출력 예시의 슬롯 라벨을 그대로 되뱉은 항목 — 그라운딩 실패 신호."""
    items = [
        "국내 트랙 이슈 1 — 한국 증권거래소는 2026년 7월 29일 SK하이닉스 ADR 상장 이후…",
        "국내 트랙 이슈 2 — 한국은행 금융통화위원회는 기준금리를 동결했습니다.",
        "외국인이 코스피에서 2,881억원 순매도했습니다.",
    ]
    assert _drop_prompt_slot_echoes(items) == [items[2]]


def test_slot_echo_keeps_normal_text():
    items = ["코스피 이슈 정리: 외국인 순매도가 이어졌습니다", "SK하이닉스가 3% 올랐습니다"]
    assert _drop_prompt_slot_echoes(items) == items


def test_dict_items_supported():
    items = [{"date": "2026-07-29", "text": INCIDENT}]
    assert _drop_reality_contradictions(items, REAL) == []


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
