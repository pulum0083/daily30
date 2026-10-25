# 코스피 아침 상승 모멘텀 종목(LLM 픽) 제거 회귀 테스트 — 미국 브리핑 픽은 그대로 남아야 한다(2026-10-25)
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


def test_us_prompt_keeps_picks():
    assert "stock_picks" in cc.US_SYSTEM_PROMPT and "us_candidates" in cc.US_SYSTEM_PROMPT


def test_kospi_candidates_no_longer_collected():
    assert not hasattr(fd, "KOSPI_CANDIDATES")
    assert hasattr(fd, "US_CANDIDATES")


def test_kospi_response_picks_are_dropped():
    # 모델이 습관처럼 stock_picks를 내보내도 코스피에서는 버린다
    assert 'if briefing_type == "kospi" and analysis.pop("stock_picks", None) is not None:' in SRC


def test_kospi_telegram_link_no_longer_mentions_picks():
    assert "전체 근거·종목 픽" not in SRC and "🔗 전체 근거·이슈 점검 → " in SRC
