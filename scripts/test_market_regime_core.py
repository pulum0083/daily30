# 국면 판정 코어 테스트 — 네트워크 없이 순수 함수만 검증한다.
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from market_regime_core import basket_cum  # noqa: E402


def test_basket_cum_simple_average():
    """구성 종목 누적수익률의 단순평균. 시총가중 아님."""
    dates = ["d1", "d2", "d3"]
    closes = {"A": {"d1": 100, "d2": 110, "d3": 120},
              "B": {"d1": 100, "d2": 100, "d3": 100}}
    cum, n = basket_cum(["A", "B"], closes, dates)
    assert n == 2
    assert cum[0] == 0.0
    assert cum[2] == 10.0          # (+20% + 0%) / 2


def test_basket_cum_excludes_ticker_missing_at_window_start():
    """창 시작에 없던 종목은 평균에서 제외한다 — DRAM(2026-04-02 상장) 케이스."""
    dates = ["d1", "d2"]
    closes = {"A": {"d1": 100, "d2": 120},
              "LATE": {"d2": 50}}          # d1에 없음
    cum, n = basket_cum(["A", "LATE"], closes, dates)
    assert n == 1
    assert cum[1] == 20.0                  # LATE는 통째로 빠짐


def test_basket_cum_forward_fills_missing_mid_series():
    """중간 결측(한국 휴장일)은 직전 종가로 채운다."""
    dates = ["d1", "d2", "d3"]
    closes = {"KR": {"d1": 100, "d3": 110}}   # d2 없음
    cum, n = basket_cum(["KR"], closes, dates)
    assert cum[1] == 0.0                      # d1 종가 유지
    assert cum[2] == 10.0


def test_basket_cum_returns_none_when_no_member_usable():
    dates = ["d1", "d2"]
    closes = {"LATE": {"d2": 50}}
    cum, n = basket_cum(["LATE"], closes, dates)
    assert cum is None and n == 0


def test_basket_cum_empty_dates_returns_none():
    """빈 창은 크래시가 아니라 (None, 0) — 다른 계산 불가 경로와 동작을 맞춘다."""
    cum, n = basket_cum(["A"], {"A": {"d1": 100}}, [])
    assert cum is None and n == 0


def test_basket_cum_treats_nan_as_missing():
    """NaN 종가는 없는 데이터다. 조용히 평균에 섞이면 바스켓 전체가 NaN이 된다(§0)."""
    nan = float("nan")
    dates = ["d1", "d2", "d3"]
    closes = {"A": {"d1": 100, "d2": nan, "d3": 120}}
    cum, n = basket_cum(["A"], closes, dates)
    assert n == 1
    assert cum[1] == 0.0      # NaN 대신 직전 종가(d1) 사용
    assert cum[2] == 20.0
    assert all(v == v for v in cum), f"NaN이 남아있다: {cum}"


from market_regime_core import daily_frames  # noqa: E402


def test_daily_frames_gap_from_running_peak():
    """gap은 '그 시점까지의 최고' 대비 거리다. 미래를 보지 않는다."""
    cums = {"a": [0.0, 10.0, 5.0]}
    fr = daily_frames(cums)
    assert fr[0]["a"]["gap"] == 0.0     # 첫날은 자기가 정점
    assert fr[1]["a"]["gap"] == 0.0     # 신고점
    assert fr[2]["a"]["gap"] == -5.0    # 정점 10에서 5 내려옴


def test_daily_frames_flags():
    cums = {"cooled": [0.0, 30.0, 10.0], "high": [0.0, 1.0, 2.0]}
    fr = daily_frames(cums)
    last = fr[2]
    assert last["cooled"]["is_cooled"] is True    # -20 <= -15
    assert last["cooled"]["is_high"] is False
    assert last["high"]["is_high"] is True        # gap 0 >= -3
    assert last["high"]["is_cooled"] is False


def test_daily_frames_threshold_boundaries():
    """경계값은 포함이다 — 정확히 -15.0이면 식음, -3.0이면 신고점."""
    fr = daily_frames({"x": [0.0, 100.0, 85.0]})   # gap = -15.0
    assert fr[2]["x"]["is_cooled"] is True
    fr2 = daily_frames({"y": [0.0, 100.0, 97.0]})  # gap = -3.0
    assert fr2[2]["y"]["is_high"] is True


def test_daily_frames_rejects_mismatched_lengths():
    """길이가 다른 시계열은 조용히 자르거나 죽지 않고 명시적으로 실패한다.
    딕셔너리 키 순서에 따라 크래시하거나 데이터가 사라지던 문제의 회귀 가드."""
    with pytest.raises(ValueError):
        daily_frames({"a": [0.0, 10.0, 5.0], "b": [0.0, 10.0]})


def test_daily_frames_rejects_nan():
    """NaN은 결측이다. 조용히 통과시키면 그날의 플래그가 '정상'으로 오판된다(§0)."""
    nan = float("nan")
    with pytest.raises(ValueError):
        daily_frames({"a": [0.0, nan, 5.0]})


def test_daily_frames_gap_matches_displayed_value_at_rounding_boundary():
    """gap 표시값과 is_cooled 판정이 같은 값에서 나와야 한다 — 이중 반올림으로 어긋나면 안 된다."""
    fr = daily_frames({"x": [0.0, 100.0, 85.04]})
    last = fr[2]["x"]
    assert last["gap"] == -15.0
    assert last["is_cooled"] is True   # gap이 -15.0으로 보이는데 플래그가 False면 모순


from market_regime_core import qualifying_sets, classify  # noqa: E402


def _frame(**kw):
    return {k: {"is_cooled": c, "is_high": h} for k, (c, h) in kw.items()}


def test_qualifying_needs_k_of_n_days():
    """최근 5일 중 3일 이상 충족해야 집합에 들어간다."""
    frames = [_frame(a=(False, True)) for _ in range(2)] + \
             [_frame(a=(True, False)) for _ in range(3)]
    cooled, rising = qualifying_sets(frames, 4)
    assert cooled == {"a"}      # 최근 5일 중 3일 cooled
    assert rising == set()      # 2일뿐이라 미달


def test_qualifying_short_window_at_start():
    """창이 5일보다 짧으면 있는 날 수 기준으로 판단한다."""
    frames = [_frame(a=(True, False)), _frame(a=(True, False))]
    cooled, _ = qualifying_sets(frames, 1)
    assert cooled == {"a"}      # 2일 전부 충족


def test_qualifying_restricts_to_allowed_keys():
    """헤드라인용 집합은 글로벌 바스켓으로 한정할 수 있어야 한다."""
    frames = [_frame(g=(True, False), kr=(True, False)) for _ in range(5)]
    cooled, _ = qualifying_sets(frames, 4, allowed={"g"})
    assert cooled == {"g"}


def test_classify_three_states():
    assert classify({"a"}, {"b"}) == "swap"
    assert classify(set(), {"b"}) == "lead"
    assert classify({"a"}, set()) == "none"
    assert classify(set(), set()) == "none"


def test_qualifying_rejects_out_of_range_i():
    """i가 범위를 벗어나면 조용히 잘린 결과 대신 명시적으로 실패한다.
    i=len(frames)(흔한 off-by-one)가 정상 마지막 날과 똑같은 결과를 내던 문제의 회귀 가드."""
    frames = [{"a": {"is_cooled": True, "is_high": False}}] * 5
    with pytest.raises(ValueError):
        qualifying_sets(frames, 5)
    with pytest.raises(ValueError):
        qualifying_sets(frames, -1)


def test_qualifying_needs_more_than_short_window_all_pass():
    """짧은 창에서 일부만 충족하면 제외된다 — need가 항상 전부 통과시키는 버그의 회귀 가드."""
    frames = [{"a": {"is_cooled": True, "is_high": False}},
              {"a": {"is_cooled": False, "is_high": False}}]
    cooled, _ = qualifying_sets(frames, 1)
    assert cooled == set()   # 2일 중 1일만 충족 — need=min(3,2)=2에 미달


from market_regime_core import absorb_short_runs  # noqa: E402


def test_absorb_run_shorter_than_min():
    """10일 미만 구간은 직전 국면에 흡수된다."""
    states = ["lead"] * 12 + ["swap"] * 3 + ["lead"] * 12
    out = absorb_short_runs(states)
    assert set(out) == {"lead"}


def test_absorb_keeps_long_enough_run():
    states = ["lead"] * 12 + ["swap"] * 10 + ["lead"] * 12
    out = absorb_short_runs(states)
    assert out[12:22] == ["swap"] * 10


def test_absorb_does_not_touch_first_run():
    """첫 구간은 흡수할 직전 국면이 없다 — 짧아도 그대로 둔다."""
    states = ["swap"] * 3 + ["lead"] * 20
    out = absorb_short_runs(states)
    assert out[:3] == ["swap"] * 3


def test_absorb_empty():
    assert absorb_short_runs([]) == []


from market_regime_core import josa, headline  # noqa: E402

NAMES = {"memory": "메모리 반도체", "ai_infra": "AI 인프라",
         "value_cyclical": "가치 경기민감", "dividend_defensive": "배당 방어"}
ORDER = ["memory", "ai_infra", "value_cyclical", "dividend_defensive"]


def test_josa_by_final_consonant():
    assert josa("인프라") == "로"        # 받침 없음
    assert josa("가치 경기민감") == "으로"  # 받침 ㅁ
    assert josa("서울") == "로"          # ㄹ 종성은 '로'
    assert josa("방어") == "로"


def test_headline_swap_picks_most_cooled_and_top_two_high():
    """A = gap 최소(가장 많이 식은), B = cum 내림차순 최대 2개."""
    cum = {"memory": 89.4, "ai_infra": 17.2, "value_cyclical": 9.8, "dividend_defensive": -1.5}
    gap = {"memory": -53.2, "ai_infra": 0.0, "value_cyclical": 0.0, "dividend_defensive": -20.0}
    txt = headline("swap", {"memory", "dividend_defensive"},
                   {"ai_infra", "value_cyclical"}, cum, gap, NAMES, ORDER)
    assert txt == "주도주가 메모리 반도체에서 AI 인프라, 가치 경기민감으로 넘어가는 중이에요"


def test_headline_lead_uses_top_cumulative():
    cum = {"memory": 89.4, "ai_infra": 17.2}
    gap = {"memory": 0.0, "ai_infra": 0.0}
    txt = headline("lead", set(), {"memory"}, cum, gap, NAMES, ORDER)
    assert txt == "메모리 반도체 주도가 이어지고 있어요"


def test_headline_none_is_fixed_sentence():
    assert headline("none", set(), set(), {}, {}, NAMES, ORDER) == "뚜렷한 주도주가 없어요"


def test_headline_returns_none_when_material_missing():
    """상태는 swap인데 재료가 없으면 None. 억지로 문장을 만들지 않는다(§0)."""
    assert headline("swap", set(), {"ai_infra"}, {"ai_infra": 1.0}, {"ai_infra": 0.0},
                    NAMES, ORDER) is None


def test_headline_ties_break_by_declaration_order():
    """동점이면 설정 파일 선언 순서를 따른다 — 결정론 보장."""
    cum = {"ai_infra": 5.0, "value_cyclical": 5.0}
    gap = {"ai_infra": 0.0, "value_cyclical": 0.0}
    txt = headline("lead", set(), {"ai_infra", "value_cyclical"}, cum, gap, NAMES, ORDER)
    assert txt == "AI 인프라 주도가 이어지고 있어요"
