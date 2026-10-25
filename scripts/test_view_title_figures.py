# 헤드라인(view_title)의 등락률이 검증된 본문(key_drivers·recap)에 없으면 근거 문장으로 바꾸는 게이트 테스트
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_analysis as va

KD = [{"text": "<b>메타발 AI 투자 공포가 반도체 전반을 짓눌렀어요.</b> 필라델피아 반도체지수가 <b>-6.72%</b> 급락했어요.", "codes": []}]
RECAP = [{"text": "코스피가 기관 매도에 <b>-3.52%</b> 급락했어요.", "codes": []}]


def _run(title, kd=KD, recap=RECAP, btype="kospi"):
    a = {"todays_view": {"view_title": title, "recap": recap}, "key_drivers": kd}
    corr = []
    va.fix_view_title_figures(a, btype, corr)
    return a["todays_view"]["view_title"], corr


def test_figures_found_in_evidence_keep_title():
    t = "어제 -3.52% 맞았는데 또? 메타發 반도체 -6.72% 2차 충격"
    assert _run(t) == (t, [])


def test_sign_is_ignored():
    t = "반도체 6.72% 추락, 메타가 쏘아 올린 공포"
    assert _run(t)[0] == t


def test_unverified_figure_replaced_by_lead_sentence():
    title, corr = _run("메타發 쇼크, 반도체 -9.10% 붕괴")
    assert title == "메타발 AI 투자 공포가 반도체 전반을 짓눌렀어요."
    assert corr and "9.10" in corr[0]


def test_no_figures_untouched():
    t = "메타가 AI에 돈 쏟자 반도체가 울었다"
    assert _run(t) == (t, [])


def test_no_lead_strips_figure_only():
    title, corr = _run("메타發 쇼크, 반도체 -9.10% 붕괴", kd=[])
    assert "9.10" not in title and "메타發 쇼크" in title and corr


def test_other_briefing_types_skipped():
    t = "반도체 -9.10% 붕괴"
    assert _run(t, btype="us") == (t, [])


def test_validate_runs_gate_after_key_drivers():
    src = Path(va.__file__).read_text(encoding="utf-8")
    assert src.index("validate_key_drivers(a, btype") < src.index("fix_view_title_figures(a, btype")
