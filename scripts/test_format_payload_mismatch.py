# 형식↔본문 불일치 게이트 테스트 — 찍힌 analysis_format의 본문이 비면 빈 껍데기가 렌더된다.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_analysis as v


def _core():
    """split으로 내려앉아도 렌더할 내용이 있는 최소 페이로드."""
    return {
        "todays_view": {
            "view_title": "반도체가 지수를 통째로 끌고 가는 장",
            "dek": "간밤 미 반도체 지표가 급등했어요.",
            "recap": [{"text": "반도체 대형주가 지수를 끌어올렸어요."}],
            "outlook": [{"tag": "event", "text": "오늘 밤 미국 PPI 발표가 있어요."}],
        },
        "key_drivers": [{"text": "외국인 자금이 들어오고 있어요."}],
    }


def _run(analysis):
    corrections, warnings, blocks = [], [], []
    v.fix_format_payload_mismatch(analysis, corrections, warnings, blocks)
    return corrections, warnings, blocks


def test_keynum_without_num_cards_falls_back_to_split():
    """2026-08-13 실사고 — keynum으로 찍혔는데 num_cards가 없어 빈 그리드가 발행됐다."""
    a = dict(_core(), analysis_format="keynum")
    corrections, warnings, blocks = _run(a)
    assert a["analysis_format"] == "split"
    assert not blocks
    assert any("keynum" in c and "split" in c for c in corrections), corrections


def test_keynum_with_num_cards_is_untouched():
    a = dict(_core(), analysis_format="keynum",
             num_cards=[{"label": "외국인 수급", "value": "+537억"}])
    corrections, warnings, blocks = _run(a)
    assert a["analysis_format"] == "keynum"
    assert not corrections and not blocks


def test_split_needs_no_format_fields():
    """split은 형식별 필드가 없는 형식이라 검사 대상이 아니다."""
    a = dict(_core(), analysis_format="split")
    corrections, warnings, blocks = _run(a)
    assert a["analysis_format"] == "split"
    assert not corrections and not blocks


def test_each_format_detects_empty_body():
    for fmt, field in [("qa", "qa_items"), ("signal", "sig_items"),
                       ("flow", "flow_steps"), ("scenario", "sc_left_items")]:
        empty = dict(_core(), analysis_format=fmt)
        _run(empty)
        assert empty["analysis_format"] == "split", f"{fmt}: 빈 본문을 못 잡았다"

        filled = dict(_core(), analysis_format=fmt, **{field: [{"x": 1}]})
        _run(filled)
        assert filled["analysis_format"] == fmt, f"{fmt}: 정상 본문을 잘못 바꿨다"


def test_why_what_so_needs_any_of_three():
    a = dict(_core(), analysis_format="why_what_so")
    _run(a)
    assert a["analysis_format"] == "split"

    b = dict(_core(), analysis_format="why_what_so", what="오늘은 반도체가 끌어요.")
    _run(b)
    assert b["analysis_format"] == "why_what_so"


def test_blocks_when_no_core_content_left():
    """내려앉힐 곳조차 없으면 빈 브리핑이 나간다 — 발행을 막는다(§0)."""
    a = {"analysis_format": "keynum"}          # todays_view·key_drivers 둘 다 없음
    corrections, warnings, blocks = _run(a)
    assert blocks, "본문이 통째로 비었는데 발행을 막지 않았다"
    assert a["analysis_format"] == "keynum"    # 차단이므로 교정하지 않는다


def test_core_survives_on_key_drivers_alone():
    """todays_view가 없어도 key_drivers가 있으면 근거 섹션은 렌더된다 — 차단하지 않는다."""
    a = {"analysis_format": "keynum", "key_drivers": [{"text": "외국인 순매수예요."}]}
    corrections, warnings, blocks = _run(a)
    assert not blocks
    assert a["analysis_format"] == "split"


def test_unknown_format_warns_but_does_not_change():
    """미등록 형식은 판단 근거가 없다 — 조용히 통과시키지 말고 경고만 남긴다."""
    a = dict(_core(), analysis_format="brandnew")
    corrections, warnings, blocks = _run(a)
    assert a["analysis_format"] == "brandnew"
    assert warnings and not corrections and not blocks


def test_missing_format_is_noop():
    a = _core()
    corrections, warnings, blocks = _run(a)
    assert "analysis_format" not in a
    assert not corrections and not warnings and not blocks


def test_registry_covers_every_rotation_format():
    """형식 풀에 형식을 추가하고 여기 등록을 빠뜨리면 이 게이트가 조용히 헛돈다."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import call_claude
    missing = [f for f in call_claude.FORMAT_POOL_KOSPI if f not in v.FORMAT_BODY_FIELDS]
    assert not missing, f"FORMAT_BODY_FIELDS에 미등록: {missing}"
    missing_close = [f for f in call_claude.FORMAT_POOL_CLOSE if f not in v.FORMAT_BODY_FIELDS]
    assert not missing_close, f"FORMAT_BODY_FIELDS에 미등록(close): {missing_close}"
