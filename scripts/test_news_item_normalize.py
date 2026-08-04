# 뉴스 항목 정규화 경계 테스트 — LLM이 키 이름을 바꿔도 모든 게이트가 같은 텍스트를 보는지 검증.
# 2026-08-04 실사고: Gemini가 catalysts 항목을 {"date","catalyst"}로 반환했는데
# _drop_stale_earnings는 c["text"]만 읽어 텍스트가 빈 문자열이 됐고, 41일 전 마이크론 실적이
# "실적 촉매 아님"으로 판정돼 무검증 통과했다(_filter_stale_catalysts만 "catalyst" 폴백이 있었음).
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn

TODAY = date(2026, 8, 4)
MU_TEXT = "마이크론(MU)의 3분기 실적 예상치 상회 → 프리마켓에서 반도체 관련주(AMD, QCOM) 강세"


def _fake_age(mapping):
    return lambda t, today: mapping.get(t)


# ─── _item_text: 키 이름에 의존하지 않는다 ───

def test_item_text_plain_string():
    assert fn._item_text(MU_TEXT) == MU_TEXT


def test_item_text_standard_schema():
    assert fn._item_text({"date": "2026-08-04", "text": MU_TEXT, "ticker": "MU"}) == MU_TEXT


def test_item_text_catalyst_key_variant():
    """실사고 형태 — 프롬프트가 요구한 text 대신 catalyst 키로 왔다."""
    assert fn._item_text({"date": "2026-08-04", "catalyst": MU_TEXT}) == MU_TEXT


def test_item_text_unknown_key_variant():
    """본 적 없는 키 이름이어도 본문을 찾아낸다 — 키 목록을 늘리는 방식이면 또 뚫린다."""
    assert fn._item_text({"date": "2026-08-04", "event": MU_TEXT, "ticker": "MU"}) == MU_TEXT
    assert fn._item_text({"headline": MU_TEXT}) == MU_TEXT


def test_item_text_ignores_date_and_ticker_values():
    """날짜·티커 값이 본문으로 오인되면 안 된다."""
    assert fn._item_text({"date": "2026-08-04", "ticker": "MU"}) == ""


def test_item_text_empty_shapes():
    assert fn._item_text(None) == ""
    assert fn._item_text({}) == ""
    assert fn._item_text(123) == ""


# ─── 정규화: 게이트가 보는 텍스트를 하나로 만든다 ───

def test_normalize_unifies_shapes():
    items = [MU_TEXT, {"date": "2026-08-04", "catalyst": "테슬라 신규 배터리 발표 → TSLA 강세"}]
    out = fn._normalize_news_items(items)
    assert all(isinstance(i, dict) and "text" in i for i in out)
    assert [i["text"] for i in out] == [MU_TEXT, "테슬라 신규 배터리 발표 → TSLA 강세"]
    assert out[1]["date"] == "2026-08-04"


def test_normalize_preserves_ticker():
    out = fn._normalize_news_items([{"date": "2026-08-04", "text": MU_TEXT, "ticker": "MU"}])
    assert out[0]["ticker"] == "MU"


def test_normalize_drops_textless_items():
    """본문을 못 찾은 항목은 검증이 불가능하므로 버린다(§0 — 완전성보다 정합성)."""
    assert fn._normalize_news_items([{"date": "2026-08-04", "ticker": "MU"}, MU_TEXT]) == [
        {"date": "", "text": MU_TEXT, "ticker": ""}
    ]


# ─── 실사고 리플레이: 정규화 후에는 어닝 게이트가 실제로 발화한다 ───

def test_stale_earnings_gate_catches_key_variant_after_normalize():
    raw = [
        "골드만삭스(GS)의 2분기 순이익 예상치 하회 → 시간외 거래에서 금융주 약세 전환",
        {"date": "2026-08-04", "catalyst": MU_TEXT},
    ]
    kept = fn._drop_stale_earnings(
        fn._normalize_news_items(raw), TODAY, age_fn=_fake_age({"GS": 21, "MU": 41})
    )
    assert [fn._item_text(c) for c in kept] == []


def test_stale_earnings_gate_keeps_fresh_earnings_after_normalize():
    raw = [{"date": "2026-08-04", "catalyst": MU_TEXT}]
    kept = fn._drop_stale_earnings(
        fn._normalize_news_items(raw), TODAY, age_fn=_fake_age({"MU": 0})
    )
    assert [fn._item_text(c) for c in kept] == [MU_TEXT]


def test_placeholder_gate_sees_key_variant():
    raw = [{"date": "2026-08-04", "catalyst": "C 은행, 순이자마진 하회 발표 → 금융 섹터 우려"}]
    assert fn._drop_placeholder_entities(fn._normalize_news_items(raw)) == []


# ─── 스키마 신호는 정규화 전 원본에서 측정해야 한다 ───

def test_schema_signal_fires_on_dict_without_text():
    """실사고 당일 원본 형태 — dict인데 text 키가 없다."""
    raw = {"catalysts": ["문자열 촉매", {"date": "2026-08-04", "catalyst": MU_TEXT}]}
    assert "catalysts_schema_violation" in fn._grounding_failure_signals(raw)


def test_schema_signal_fires_on_all_strings():
    raw = {"catalysts": ["문자열 촉매 1", "문자열 촉매 2"]}
    assert "catalysts_schema_violation" in fn._grounding_failure_signals(raw)


def test_schema_signal_silent_on_valid_schema():
    raw = {"catalysts": [{"date": "2026-08-04", "text": MU_TEXT, "ticker": "MU"}]}
    assert fn._grounding_failure_signals(raw) == []


def test_schema_signal_silent_on_empty_catalysts():
    assert fn._grounding_failure_signals({"catalysts": []}) == []


# ─── 그라운딩 증거(출처) 신호 ───

def test_no_source_signal_when_zero_chunks():
    """검색 쿼리는 날렸지만 출처가 하나도 안 붙은 응답 — 실측상 2.5-flash-lite의 상시 상태."""
    raw = {"catalysts": [{"date": "2026-08-04", "text": MU_TEXT, "ticker": "MU"}]}
    assert "no_grounding_sources" in fn._grounding_failure_signals(raw, grounding_chunks=0)


def test_no_source_signal_absent_when_chunks_present():
    raw = {"catalysts": [{"date": "2026-08-04", "text": MU_TEXT, "ticker": "MU"}]}
    assert fn._grounding_failure_signals(raw, grounding_chunks=3) == []


def test_no_source_signal_skipped_when_unknown():
    """조회 자체가 불가능하면 판단하지 않는다(fail-open)."""
    raw = {"catalysts": [{"date": "2026-08-04", "text": MU_TEXT, "ticker": "MU"}]}
    assert fn._grounding_failure_signals(raw, grounding_chunks=None) == []


def test_incident_replay_two_signals_discard():
    """실사고 원본: 스키마 위반 + 출처 0 → 2신호 → 뉴스 전체 폐기."""
    raw = {"catalysts": [{"date": "2026-08-04", "catalyst": MU_TEXT}]}
    assert fn._is_grounding_failure(raw, grounding_chunks=0)


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            try:
                fn_()
                print(f"  ✓ {name}")
            except Exception:
                fails += 1
                print(f"  ✗ {name}")
                traceback.print_exc()
    print(f"\n{'FAILED' if fails else 'ALL PASS'} ({fails} failures)")
    sys.exit(1 if fails else 0)
