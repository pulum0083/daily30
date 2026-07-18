# 종목별 뉴스 수집의 중복 제거와 og:image 추출을 검증하는 테스트
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_stock_news as fsn

RSS = """<rss><channel>
<item><title>삼성전자 HBM4 공급 임박</title><link>https://a.com/1</link>
<pubDate>Fri, 18 Jul 2026 09:40:00 GMT</pubDate><source>이데일리</source></item>
<item><title>메모리 사이클 반등</title><link>https://a.com/2</link>
<pubDate>Fri, 18 Jul 2026 08:55:00 GMT</pubDate><source>한국경제</source></item>
</channel></rss>"""


def test_parse_rss_extracts_items():
    items = fsn.parse_rss(RSS)
    assert len(items) == 2
    assert items[0]["title"] == "삼성전자 HBM4 공급 임박"
    assert items[0]["url"] == "https://a.com/1"
    assert items[0]["source"] == "이데일리"


def test_merge_keeps_existing_summaries():
    # 이미 요약된 기사는 재요약하지 않는다 — Gemini 호출 비용이 여기서 결정된다
    old = [{"url": "https://a.com/1", "title": "옛 제목", "summary": "이미 요약됨",
            "thumb": "t.jpg", "time": "09:40", "source": "이데일리"}]
    new = [{"url": "https://a.com/1", "title": "삼성전자 HBM4 공급 임박",
            "time": "09:40", "source": "이데일리"},
           {"url": "https://a.com/2", "title": "메모리 사이클 반등",
            "time": "08:55", "source": "한국경제"}]
    merged, todo = fsn.merge(old, new)
    assert [m["url"] for m in merged] == ["https://a.com/1", "https://a.com/2"]
    assert merged[0]["summary"] == "이미 요약됨"
    assert merged[0]["thumb"] == "t.jpg"
    assert [t["url"] for t in todo] == ["https://a.com/2"]


def test_merge_refreshes_title_of_existing_item():
    # 요약은 보존하되 제목·시각은 최신 RSS 값으로 갱신한다
    old = [{"url": "https://a.com/1", "title": "옛 제목", "summary": "요약",
            "thumb": None, "time": "08:00", "source": "이데일리"}]
    new = [{"url": "https://a.com/1", "title": "새 제목", "time": "09:40",
            "source": "이데일리"}]
    merged, todo = fsn.merge(old, new)
    assert merged[0]["title"] == "새 제목"
    assert merged[0]["summary"] == "요약"
    assert todo == []


def test_merge_caps_at_five():
    new = [{"url": f"https://a.com/{i}", "title": f"t{i}", "time": "09:00",
            "source": "s"} for i in range(8)]
    merged, _ = fsn.merge([], new)
    assert len(merged) == 5


def test_extract_og_image():
    html = '<meta property="og:image" content="https://img.com/a.jpg">'
    assert fsn.extract_og_image(html) == "https://img.com/a.jpg"


def test_extract_og_image_handles_reversed_attribute_order():
    html = '<meta content="https://img.com/b.jpg" property="og:image">'
    assert fsn.extract_og_image(html) == "https://img.com/b.jpg"


def test_extract_og_image_returns_none_when_absent():
    # 썸네일 없는 기사가 반드시 생긴다 — 폴백이 동작해야 한다
    assert fsn.extract_og_image("<html><body>no meta</body></html>") is None
