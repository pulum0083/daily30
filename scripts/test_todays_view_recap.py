# '오늘의 관점' 지난 장 복기(recap) 목록 렌더 회귀 테스트 (네트워크 없이 템플릿만 렌더)
"""2026-08-18 실사고: .tv-col li는 불릿(::before) + 텍스트 한 덩어리를 위한 display:flex인데,
recap <li>가 텍스트와 <b>를 직접 자식으로 뒀다. flex 컨테이너의 직접 자식은 각각 별도
flex item으로 승격되므로(텍스트 조각·<b> 각각), 문장이 <b> 태그 경계마다 쪼개져 좁은
칸에서 단어 단위로 줄바꿈되며 페이지가 깨져 보였다. outlook(오늘 볼 것) <li>는 처음부터
전체를 <span> 하나로 감싸 flex item이 1개뿐이라 문제가 없었다 — recap도 같은 패턴으로 맞춘다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as g  # noqa: E402


def _render(recap, outlook=None):
    tpl = g.make_env().get_template("sections/todays_view.html")
    return tpl.render(
        todays_view={
            "view_title": "테스트 제목",
            "dek": "",
            "recap": recap,
            "outlook": outlook or [],
        },
        analysis_format="split",
        dir_cls="up",
    )


def test_recap_li_wraps_content_in_single_span():
    """recap <li>의 직접 자식은 <span> 하나뿐이어야 한다 — flex item 분열 방지."""
    html = _render([{"text": "코스피가 <b>+1.64%</b> 올랐어요."}])
    assert "<li><span>코스피가 <b>+1.64%</b> 올랐어요.</span></li>" in html


def test_recap_with_multiple_bold_numbers_stays_single_flex_item():
    """실사고 재현 — 한 문장에 <b>가 여러 개 섞여도 li 직접 자식은 span 1개."""
    text = "메모리 반도체 ETF(DRAM)가 <b>+6.49%</b>, EWY가 <b>+3.94%</b> 폭등했어요."
    html = _render([{"text": text}])
    li_start = html.index("<li>")
    li_end = html.index("</li>", li_start)
    li_inner = html[li_start + len("<li>"):li_end]
    assert li_inner == f"<span>{text}</span>", (
        "li의 직접 자식이 span 하나가 아니다 — .tv-col li{display:flex}에서 "
        "text/<b>가 각각 별도 flex item으로 승격돼 문장이 쪼개진다")


def test_outlook_li_still_wraps_in_span_unchanged():
    """outlook은 원래부터 정상이던 패턴 — 이번 수정으로 건드리지 않았는지 확인."""
    html = _render([], outlook=[{"tag": "watch", "text": "관전 포인트예요."}])
    assert '<li><span><span class="tv-tag tv-tag--watch">관전</span>관전 포인트예요.</span></li>' in html
