# 마감 브리핑 세 줄 요약(brief) 형식 — 렌더·검증 게이트·프롬프트 테스트(2026-10-29)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude  # noqa: E402
import generate_html as gh  # noqa: E402
import validate_analysis as v  # noqa: E402

BRIEF = {
    "analysis_format": "brief",
    "market_title": "SK하이닉스가 쏜 실적 로켓, 코스피를 6000 위로 다시 태웠다",
    "dek": "SK하이닉스 역대 최대 실적에 반도체가 지수를 끌어올렸어요.",
    "brief_lines": [
        {"k": "원인", "text": "역대 최대 실적·주주환원 발표로 반도체 고점 우려가 걷혔어요."},
        {"k": "주도", "text": "SK하이닉스 <b>+10.89%</b>, 삼성전자 <b>+9.01%</b> — 외국인·기관이 함께 샀어요."},
        {"k": "다음", "text": "상승이 이어질지, 차익실현이 나올지가 관건이에요."},
    ],
}



def test_close_format_is_fixed_brief():
    assert call_claude.FORMAT_POOL_CLOSE == ["brief"]
    assert "brief" in v.FORMAT_BODY_FIELDS


def test_brief_template_renders_three_lines():
    env = gh.make_env()
    html = env.get_template("sections/close_brief.html").render(
        reason_title=BRIEF["market_title"], close_dek=BRIEF["dek"], brief_lines=BRIEF["brief_lines"])
    assert html.count('<li>') == 3 and '<span class="k">원인</span>' in html and "<b>+10.89%</b>" in html
    assert "WHY" not in html


def test_brief_without_lines_keeps_title_and_dek():
    a = dict(BRIEF, brief_lines=[])
    corr, warn, blocks = [], [], []
    v.fix_format_payload_mismatch(a, corr, warn, blocks)
    assert a["analysis_format"] == "brief" and not blocks


def test_headline_craft_in_all_three_prompts():
    for p in (call_claude.KOSPI_SYSTEM_PROMPT, call_claude.US_SYSTEM_PROMPT, call_claude.KOSPI_CLOSE_SYSTEM_PROMPT):
        assert "[카피 원칙]" in p and "<<HEADLINE_CRAFT>>" not in p and "비유" in p
    assert "brief_lines" in call_claude.KOSPI_CLOSE_SYSTEM_PROMPT
    assert '"so_what"' not in call_claude.KOSPI_CLOSE_SYSTEM_PROMPT
