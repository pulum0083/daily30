# 응답 잘림 감지 — 2026-09-04 max_tokens=4096 truncation 사고 방지.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import call_claude as cc  # noqa: E402


def test_max_tokens_headroom():
    """분석 호출의 max_tokens가 관측된 출력(4096 상한 도달)보다 넉넉해야 한다.

    2026-09-04 이전엔 4096이었고, 성공한 실행조차 Output=4096으로 정확히 상한에
    붙어 있었다 — JSON이 우연히 닫히면 통과하고 아니면 터지는 상태였다.
    """
    src = (Path(__file__).parent / "call_claude.py").read_text()
    import re
    vals = [int(m) for m in re.findall(r"max_tokens=(\d+)", src)]
    assert vals, "max_tokens 호출이 없습니다"
    assert max(vals) >= 8192, f"분석 호출 max_tokens가 너무 작습니다: {vals}"
    assert 4096 not in vals, f"4096은 실측으로 부족한 값입니다: {vals}"


def test_truncation_is_reported_as_truncation(monkeypatch):
    """잘림을 JSON 파싱 오류로 위장하지 않고 명시적으로 보고한다."""
    src = (Path(__file__).parent / "call_claude.py").read_text()
    assert 'stop_reason", None) == "max_tokens"' in src
    assert "max_tokens에서 잘렸습니다" in src
