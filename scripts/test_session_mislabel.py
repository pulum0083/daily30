# 프리장에 거래되지 않는 지수를 '프리마켓에서'로 서술하는 오표기를 잡는 게이트 테스트.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_analysis import find_session_mislabels  # noqa: E402


def test_real_incident_sox_premarket():
    """실사고(2026-07-27 재생성): SOX 금요일 종가(-4.25%)를 '프리마켓에서 눌린다'로 서술."""
    issues = [{
        "title": "SOX(반도체지수) 약세 — 프리마켓 선물과 엇갈리는 신호",
        "body": "지수 선물은 오르는데 반도체지수(SOX)는 프리마켓에서 눌리고 있어요.",
    }]
    bad = find_session_mislabels(issues)
    assert len(bad) == 1
    assert bad[0]["subject"] == "SOX"


def test_nasdaq_index_premarket():
    """나스닥 '지수'도 프리장엔 갱신되지 않는다."""
    issues = [{"title": "나스닥 지수 프리마켓에서 하락", "body": ""}]
    assert len(find_session_mislabels(issues)) == 1


def test_futures_premarket_is_fine():
    """선물은 프리장에도 거래된다 — 오표기가 아니다."""
    issues = [
        {"title": "나스닥 선물 프리마켓 강세", "body": "나스닥100 선물이 프리마켓에서 오르고 있어요."},
        {"title": "S&P 선물 프리마켓 반등", "body": ""},
    ]
    assert find_session_mislabels(issues) == []


def test_individual_stocks_premarket_is_fine():
    """개별주·ETF는 프리장에 실제로 거래된다."""
    issues = [{"title": "애플 프리마켓 강세", "body": "AMD·브로드컴이 프리마켓에서 올랐어요."}]
    assert find_session_mislabels(issues) == []


def test_index_without_premarket_wording_is_fine():
    """세션 표현이 없으면 판단하지 않는다."""
    issues = [{"title": "SOX 지난주 급락", "body": "반도체지수(SOX)가 금요일 크게 밀렸어요."}]
    assert find_session_mislabels(issues) == []


def test_corrected_wording_passes():
    """정정본은 통과해야 한다(회귀 방지)."""
    issues = [{
        "title": "지난주 금요일 반도체 급락 — 프리마켓에선 되돌림 시도",
        "body": "반도체지수(SOX)는 지난 금요일 크게 밀렸어요. 다만 오늘 프리마켓에서는 "
                "AMD·브로드컴 같은 주요 반도체주가 나란히 오르며 낙폭을 되돌리는 흐름이에요.",
    }]
    assert find_session_mislabels(issues) == []


def test_empty():
    assert find_session_mislabels([]) == []
    assert find_session_mislabels(None) == []


if __name__ == "__main__":
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            fn_()
            print(f"✅ {name}")
    print("모든 테스트 통과")
