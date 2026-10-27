# 브리핑 공유 카드(og:image) 생성과 실패 시 태그 제거 테스트
import io

from PIL import Image

from generate_html import strip_og_image
from og_card import _readout, make_card, UP, DN


def test_card_is_1200x630_png():
    a = {"prediction": {"basis": "open", "direction": "상승 우위", "up_pct": 83},
         "todays_view": {"view_title": "코스피 5500 붕괴 다음날, 뉴욕은 반도체부터 다시 샀다"}}
    png = make_card(a, "kospi", "2026-10-27")
    assert Image.open(io.BytesIO(png)).size == (1200, 630)


def test_no_headline_no_card():
    assert make_card({"prediction": {"up_pct": 60}}, "us", "2026-10-26") is None


def test_readout_uses_published_numbers_only():
    assert _readout({"prediction": {"direction": "하락 우위", "up_pct": 30}}, "kospi") == ("하락 우위 70%", DN)
    assert _readout({"prediction": {"up_pct": 68, "down_pct": 32}}, "us") == ("상승 우위 68%", UP)
    assert _readout({"prediction": {"up_pct": 50, "down_pct": 50}}, "us") is None
    assert _readout({"prediction": {"direction": "상승 우위", "up_pct": 70}}, "close") is None   # 마감 카드엔 수치 없음


def test_long_headline_is_cut_not_overflowing():
    a = {"todays_view": {"view_title": "아주 긴 헤드라인 " * 30}}
    assert make_card(a, "close", "2026-10-27") is not None


def test_strip_og_image_when_card_missing():
    head = ('<meta property="og:image" content="https://x/og.png">\n'
            '<meta name="twitter:card" content="summary_large_image">\n'
            '<meta name="twitter:image" content="https://x/og.png">\n')
    out = strip_og_image(head)
    assert "og.png" not in out
    assert '<meta name="twitter:card" content="summary">' in out
