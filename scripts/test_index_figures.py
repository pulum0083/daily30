# 한글·기호 지수명(나스닥·S&P500) 등락률 검증 테스트 — 2026-07-27 부호 반전 사고 방지.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_analysis import _index_figures, _index_figure_wrong  # noqa: E402


def test_extracts_multiple_indices():
    """한 문장의 지수별 수치를 각각 자기 이름에 붙여 뽑는다."""
    text = "나스닥 <b>-0.64%</b>, S&P500 <b>+0.05%</b>로 지수는 엇갈렸어요."
    assert _index_figures(text) == {"^IXIC": -0.64, "^GSPC": 0.05}


def test_real_incident_sign_flip():
    """실사고: 실제 +0.05%인데 -0.05%로 서술 → 부호 반전 검출."""
    text = "나스닥 <b>-0.64%</b>, S&P500 <b>-0.05%</b>로 조정 마감하며 위험자산 선호가 약해졌어요."
    figs = _index_figures(text)
    assert figs["^GSPC"] == -0.05
    assert _index_figure_wrong(figs["^GSPC"], 0.05) is True
    assert _index_figure_wrong(figs["^IXIC"], -0.64) is False


def test_correct_text_passes():
    """정정된 본문은 통과해야 한다(오제거 방지)."""
    text = "나스닥 <b>-0.64%</b>, S&P500 <b>+0.05%</b>로 지수는 엇갈렸지만 매물이 반도체에 집중됐어요."
    figs = _index_figures(text)
    assert _index_figure_wrong(figs["^IXIC"], -0.64) is False
    assert _index_figure_wrong(figs["^GSPC"], 0.05) is False


def test_nasdaq100_futures_excluded():
    """나스닥100 선물은 일봉 실측과 기준이 달라 검증 대상에서 제외한다."""
    assert _index_figures("나스닥100 선물이 <b>+1.17%</b> 올랐어요.") == {}


def test_sox_alias():
    """필라델피아 반도체지수도 ^SOX로 해석한다."""
    assert _index_figures("필라델피아 반도체지수가 <b>-4.25%</b> 하락했어요.") == {"^SOX": -4.25}


def test_no_figure_no_claim():
    """수치 없이 이름만 있으면 검증 대상이 아니다."""
    assert _index_figures("나스닥이 하락 마감했어요.") == {}


def test_tolerance():
    """2%p 이내 차이는 허용, 초과는 검출."""
    assert _index_figure_wrong(-4.25, -4.40) is False
    assert _index_figure_wrong(-1.00, -4.40) is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("모든 테스트 통과")
