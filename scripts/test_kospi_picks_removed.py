# 상승 모멘텀 종목(LLM 픽) 제거 회귀 테스트 — 코스피 2026-10-25, 미국 2026-10-26(월봉 5개월선 코너로 대체)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc
import fetch_data as fd

SRC = (Path(__file__).resolve().parent / "call_claude.py").read_text(encoding="utf-8")


def test_kospi_prompt_has_no_picks():
    p = cc.KOSPI_SYSTEM_PROMPT
    for word in ("stock_picks", "켈로그", "kospi_candidates", "action_guide에 쓴 진입가"):
        assert word not in p, word


def test_us_prompt_has_no_picks():
    p = cc.US_SYSTEM_PROMPT
    for word in ("\"stock_picks\": [", "켈로그", "action_guide", "## 종목 선택"):
        assert word not in p, word


def test_kospi_candidates_no_longer_collected():
    assert not hasattr(fd, "KOSPI_CANDIDATES")
    assert hasattr(fd, "US_CANDIDATES")


def test_kospi_response_picks_are_dropped():
    # 모델이 습관처럼 stock_picks를 내보내도 코스피에서는 버린다
    assert 'if briefing_type in ("kospi", "us") and analysis.pop("stock_picks", None) is not None:' in SRC


def test_kospi_telegram_link_no_longer_mentions_picks():
    assert "전체 근거·종목 픽" not in SRC and 'link_line("전체 근거·이슈 점검", link)' in SRC


def test_us_telegram_link_no_longer_mentions_picks():
    assert "전체 이슈·종목 픽" not in SRC and 'link_line("전체 이슈 점검", link)' in SRC
