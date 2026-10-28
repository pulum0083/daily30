# 텔레그램 말풍선 폭 — 본문 줄을 NARROW_WIDTH(21칸) 폭에서 접는지(사용자 요청 2026-10-27, 폭 2026-10-28 조정)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import send_telegram as st

MSG = """🇰🇷 코스피 시초가 예측 | 2026.10.27

📈 <b>상승 우위 83%</b> (신뢰도 74%)

🎯 <b>코스피 5500 붕괴 다음날, 뉴욕은 반도체부터 다시 샀다</b>

👀 개장 후 볼 것
이번 주 목요일 새벽 FOMC 회의 결과와 연준 기자회견이 예정돼 있어요. 금리 발표 자체보다 성명서 문구와 향후 정책 방향 코멘트가 핵심 변수예요.

🔗 전체 근거·이슈 점검 → https://doubleshot.space/briefings/2026-10-27/kospi/"""


def test_width_is_21():
    assert st.NARROW_WIDTH == 21.0


def test_every_text_line_fits_width():
    out = st.narrow_lines(MSG)
    for line in out.split("\n"):
        if "http" in line:
            continue
        assert st._visible_w(line) <= st.NARROW_WIDTH, line


def test_words_and_tags_are_kept():
    out = st.narrow_lines(MSG)
    assert out.replace("\n", " ").split() == MSG.replace("\n", " ").split()   # 접기만 하고 글자는 그대로(주소 줄 나눔 포함)
    assert out.count("<b>") == out.count("</b>") == 2


def test_link_and_short_lines_untouched():
    out = st.narrow_lines(MSG).split("\n")
    i = out.index("🔗 전체 근거·이슈 점검 →")                        # 설명과 주소를 나눈다
    assert out[i + 1] == "https://doubleshot.space/briefings/2026-10-27/kospi/"
    assert "📈 <b>상승 우위 83%</b> (신뢰도 74%)" in out


def test_quote_block_is_narrowed_too():
    q = '💡 <i>"연준과 싸우지 마라. 금리가 시장 방향을 결정한다. 그리고 추세는 친구다."</i>'
    out = st.narrow_lines(q)
    assert "\n" in out and all(st._visible_w(l) <= st.NARROW_WIDTH for l in out.split("\n"))


def test_link_line_shows_url_on_its_own_line():
    """바로가기는 주소를 그대로 보인다(2026-10-28 오후 되돌림) — 접을 땐 설명과 주소를 두 줄로 나눈다."""
    line = st.link_line("전체 근거·이슈 점검", "https://doubleshot.space/briefings/2026-10-28/kospi/")
    assert line == "🔗 전체 근거·이슈 점검 → https://doubleshot.space/briefings/2026-10-28/kospi/"
    assert st.narrow_lines(line) == "🔗 전체 근거·이슈 점검 →\nhttps://doubleshot.space/briefings/2026-10-28/kospi/"


def test_no_single_short_word_left_on_last_line():
    """마지막 줄에 짧은 단어 하나만 남기지 않는다(2026-10-28 '…다시 / 샀다')."""
    out = st.narrow_lines("🎯 <b>코스피 5500 붕괴 다음날, 뉴욕은 반도체부터 다시 샀다</b>", width=24).split("\n")
    assert out[-1] != "샀다</b>"
    assert out[-1].startswith("다시")
