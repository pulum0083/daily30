# catalysts 날짜 게이트(_filter_stale_catalysts)가 오래된 사건을 버리고 최신·미상은 유지하는지 검증.
# 2026-07-15~20 실사고: 7/15 발표 ASML 실적이 사흘 넘게 '오늘 프리마켓 촉매'로 재등장.
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn

TODAY = date(2026, 7, 20)


def test_drops_stale_dated_catalyst():
    # ASML 회귀 시나리오: 7/15 발표분은 오늘(7/20) 기준 이틀 이상 전 → 제외
    out = fn._filter_stale_catalysts(
        ["[2026-07-15] ASML 2분기 실적 호조 → 반도체 장비주 강세"], TODAY
    )
    assert out == []


def test_dict_form_drops_stale_keeps_text():
    # 프롬프트가 요구하는 구조화 형태({date,text})에서 오래된 항목 제외
    out = fn._filter_stale_catalysts([
        {"date": "2026-07-15", "text": "ASML 2분기 실적 → 반도체 장비주 강세"},
        {"date": "2026-07-20", "text": "유가 급등 → 에너지주 강세"},
    ], TODAY)
    assert out == ["유가 급등 → 에너지주 강세"]


def test_dict_form_missing_date_is_kept():
    out = fn._filter_stale_catalysts([
        {"text": "날짜 없는 거시 촉매 → 지수 전반"},
    ], TODAY)
    assert out == ["날짜 없는 거시 촉매 → 지수 전반"]


def test_dict_form_empty_text_skipped():
    out = fn._filter_stale_catalysts([{"date": "2026-07-20", "text": ""}], TODAY)
    assert out == []


def test_keeps_today_and_strips_prefix():
    out = fn._filter_stale_catalysts(
        ["[2026-07-20] 중동 정세 긴장으로 유가 급등 → 에너지주 강세"], TODAY
    )
    assert out == ["중동 정세 긴장으로 유가 급등 → 에너지주 강세"]


def test_keeps_yesterday_boundary():
    # cutoff = today-1 이므로 어제(7/19)는 유지
    out = fn._filter_stale_catalysts(
        ["[2026-07-19] 대형 은행 실적 서프라이즈 → 금융주 동반 강세"], TODAY
    )
    assert out == ["대형 은행 실적 서프라이즈 → 금융주 동반 강세"]


def test_keeps_undated_macro_catalyst():
    # 날짜 접두사 없는 거시·지정학 촉매는 버리지 않는다(유가/호르무즈 보호)
    text = "호르무즈 해협 긴장 재부각 가능성 → 유가·에너지주 변동성"
    assert fn._filter_stale_catalysts([text], TODAY) == [text]


def test_malformed_date_prefix_is_held_not_dropped():
    # 파싱 불가 접두사는 판단 보류 → 접두사만 떼고 유지
    out = fn._filter_stale_catalysts(["[2026-13-40] 이상한 날짜 → 그래도 유지"], TODAY)
    assert out == ["이상한 날짜 → 그래도 유지"]


def test_mixed_batch_keeps_only_fresh_and_undated():
    out = fn._filter_stale_catalysts([
        "[2026-07-15] 옛 ASML 실적 → 장비주",       # 제외
        "[2026-07-20] 오늘 유가 급등 → 에너지주",     # 유지
        "날짜 없는 거시 촉매 → 지수 전반",             # 유지
    ], TODAY)
    assert out == [
        "오늘 유가 급등 → 에너지주",
        "날짜 없는 거시 촉매 → 지수 전반",
    ]


def test_ignores_non_string_items():
    out = fn._filter_stale_catalysts(["[2026-07-20] ok", None, 123], TODAY)
    assert out == ["ok"]
