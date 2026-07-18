# 종목별 뉴스 수집의 중복 제거와 og:image 추출을 검증하는 테스트
import sys
from datetime import datetime, timedelta
from email.utils import format_datetime
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


RSS_SUFFIX = """<rss><channel>
<item><title>로봇 도입 경계하는 현대차 노조 - 지디넷코리아</title><link>https://a.com/1</link>
<pubDate>Fri, 18 Jul 2026 09:40:00 GMT</pubDate><source>지디넷코리아</source></item>
<item><title>사측 직격한 현대차 노조 - 머니투데이 - 머니투데이</title><link>https://a.com/2</link>
<pubDate>Fri, 18 Jul 2026 09:30:00 GMT</pubDate><source>머니투데이</source></item>
<item><title>현대차그룹 보스턴다이나믹스 지분 확보 - 조선비즈 - Chosunbiz</title><link>https://a.com/3</link>
<pubDate>Fri, 18 Jul 2026 09:20:00 GMT</pubDate><source>Chosunbiz</source></item>
<item><title>아이오닉 5 N - 성능 리뷰 - 다나와 자동차</title><link>https://a.com/4</link>
<pubDate>Fri, 18 Jul 2026 09:10:00 GMT</pubDate><source>다나와 자동차</source></item>
<item><title>산업부 이익 분배 논의 안 해</title><link>https://a.com/5</link>
<pubDate>Fri, 18 Jul 2026 09:00:00 GMT</pubDate><source>v.daum.net</source></item>
</channel></rss>"""


def test_parse_rss_strips_single_source_suffix():
    # 구글 뉴스는 제목 끝에 " - 언론사"를 붙인다 — 표시 전에 제거한다
    item = fsn.parse_rss(RSS_SUFFIX)[0]
    assert item["title"] == "로봇 도입 경계하는 현대차 노조"
    assert item["source"] == "지디넷코리아"


def test_parse_rss_strips_duplicated_source_suffix():
    # 같은 언론사명이 두 번 붙는 경우가 있어 반복 제거해야 한다
    item = fsn.parse_rss(RSS_SUFFIX)[1]
    assert item["title"] == "사측 직격한 현대차 노조"
    assert item["source"] == "머니투데이"


def test_parse_rss_promotes_korean_name_over_domain_source():
    # source가 도메인·로마자면 제목에 남은 한글 언론사명을 출처로 승격한다
    item = fsn.parse_rss(RSS_SUFFIX)[2]
    assert item["title"] == "현대차그룹 보스턴다이나믹스 지분 확보"
    assert item["source"] == "조선비즈"


def test_parse_rss_keeps_legitimate_hyphen_in_title():
    # 제목 안의 진짜 " - "는 보존한다 — source와 일치하는 접미사만 제거한다
    item = fsn.parse_rss(RSS_SUFFIX)[3]
    assert item["title"] == "아이오닉 5 N - 성능 리뷰"
    assert item["source"] == "다나와 자동차"


def test_parse_rss_keeps_domain_source_when_no_better_name():
    # 대체할 이름이 없으면 도메인을 그대로 둔다 — 표시값을 지어내지 않는다
    item = fsn.parse_rss(RSS_SUFFIX)[4]
    assert item["title"] == "산업부 이익 분배 논의 안 해"
    assert item["source"] == "v.daum.net"


# 날짜 픽스처는 실행 시점 기준으로 만든다 — 날짜를 박아두면 다음 주에 조용히 깨진다.
def _rss_with_dates():
    now = datetime.now(fsn.KST)
    today = now.replace(hour=10, minute=17, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    yesterday = yesterday.replace(hour=23, minute=50)
    older = today - timedelta(days=3)
    xml = f"""<rss><channel>
<item><title>오늘 기사</title><link>https://a.com/1</link>
<pubDate>{format_datetime(today)}</pubDate><source>한국경제</source></item>
<item><title>어제 늦은 밤 기사</title><link>https://a.com/2</link>
<pubDate>{format_datetime(yesterday)}</pubDate><source>한국경제</source></item>
<item><title>사흘 전 기사</title><link>https://a.com/3</link>
<pubDate>{format_datetime(older)}</pubDate><source>한국경제</source></item>
<item><title>날짜 없는 기사</title><link>https://a.com/4</link>
<source>한국경제</source></item>
</channel></rss>"""
    return xml, today, older


def test_time_label_today_is_clock_time():
    xml, today, _ = _rss_with_dates()
    assert fsn.parse_rss(xml)[0]["time"] == today.strftime("%H:%M")


def test_time_label_yesterday_late_night_is_yesterday():
    # 경과 시간이 아니라 달력 날짜 기준이다 — 어제 23:50은 몇 시간 전이어도 "어제"다.
    xml, _, _ = _rss_with_dates()
    assert fsn.parse_rss(xml)[1]["time"] == "어제"


def test_time_label_older_than_yesterday_is_month_day():
    # 하루 넘은 기사를 "어제"로 표기하면 독자에게 거짓이 된다.
    xml, _, older = _rss_with_dates()
    assert fsn.parse_rss(xml)[2]["time"] == f"{older.month}/{older.day}"


def test_time_label_missing_pubdate_is_empty():
    xml, _, _ = _rss_with_dates()
    assert fsn.parse_rss(xml)[3]["time"] == ""


# 구글 뉴스 실제 피드처럼 순서가 뒤섞인 XML — 날짜는 실행 시점 기준으로 만든다.
def _rss_jumbled():
    now = datetime.now(fsn.KST)
    today = now.replace(hour=9, minute=57, second=0, microsecond=0)
    two_days = today - timedelta(days=2)
    three_days = today - timedelta(days=3)
    return f"""<rss><channel>
<item><title>이틀 전 기사</title><link>https://a.com/old2</link>
<pubDate>{format_datetime(two_days)}</pubDate><source>한국경제</source></item>
<item><title>오늘 기사</title><link>https://a.com/today</link>
<pubDate>{format_datetime(today)}</pubDate><source>한국경제</source></item>
<item><title>날짜 없는 기사</title><link>https://a.com/none</link>
<source>한국경제</source></item>
<item><title>사흘 전 기사</title><link>https://a.com/old3</link>
<pubDate>{format_datetime(three_days)}</pubDate><source>한국경제</source></item>
</channel></rss>"""


def test_parse_rss_sorts_newest_first():
    # 피드 순서는 발행 시각순이 아니다 — 실제 발행 시각으로 정렬해야 한다.
    titles = [i["title"] for i in fsn.parse_rss(_rss_jumbled())]
    assert titles[:3] == ["오늘 기사", "이틀 전 기사", "사흘 전 기사"]


def test_parse_rss_puts_undated_items_last_without_dropping():
    # 발행 시각을 못 읽은 기사는 버리지 않고 맨 뒤에 둔다.
    items = fsn.parse_rss(_rss_jumbled())
    assert len(items) == 4
    assert items[-1]["title"] == "날짜 없는 기사"
    assert items[-1]["published"] == ""


def test_merge_selects_five_newest_not_first_five():
    # 최신 5건이 입력 앞쪽 5건과 다른 경우 — 발행 시각 기준으로 골라야 한다.
    now = datetime.now(fsn.KST)
    # 오래된 3건이 앞, 최신 5건이 뒤에 오도록 배치한다.
    stale = [{"url": f"https://a.com/old{n}", "title": f"오래됨{n}",
              "time": "7/10", "source": "s",
              "published": (now - timedelta(days=10 + n)).isoformat()}
             for n in range(3)]
    fresh = [{"url": f"https://a.com/new{n}", "title": f"최신{n}",
              "time": "09:00", "source": "s",
              "published": (now - timedelta(minutes=n)).isoformat()}
             for n in range(5)]
    merged, todo = fsn.merge([], stale + fresh)
    assert [m["url"] for m in merged] == [f"https://a.com/new{n}" for n in range(5)]
    assert len(todo) == 5


RSS_ENTITIES = """<rss><channel>
<item><title>&quot;삼성전자&quot; 최대 실적&amp;신고가</title><link>https://a.com/1</link>
<pubDate>Fri, 18 Jul 2026 09:40:00 GMT</pubDate><source>한경매거진&amp;북</source></item>
<item><title>현대차 &#39;아이오닉 5 N&#39; 출시</title><link>https://a.com/2</link>
<pubDate>Fri, 18 Jul 2026 09:30:00 GMT</pubDate><source>대한경제</source></item>
</channel></rss>"""


def test_parse_rss_unescapes_html_entities():
    # 엔티티가 그대로 남으면 위젯에 &amp;·&quot;가 문자 그대로 노출된다.
    items = fsn.parse_rss(RSS_ENTITIES)
    assert items[0]["title"] == '"삼성전자" 최대 실적&신고가'
    assert items[0]["source"] == "한경매거진&북"
    assert items[1]["title"] == "현대차 '아이오닉 5 N' 출시"


def test_parse_rss_does_not_revive_escaped_tags():
    # 태그 제거 후 언이스케이프해야 &lt;script&gt;가 진짜 태그로 되살아나지 않는다.
    xml = ("<rss><channel><item><title>&lt;script&gt;위험&lt;/script&gt;</title>"
           "<link>https://a.com/1</link><source>대한경제</source></item>"
           "</channel></rss>")
    assert fsn.parse_rss(xml)[0]["title"] == "<script>위험</script>"


# UGC 플랫폼 글이 섞인 피드 — 날짜는 실행 시점 기준으로 만든다.
def _rss_with_ugc():
    now = datetime.now(fsn.KST).replace(second=0, microsecond=0)
    rows = [
        ("정상 기사1", "대한경제", now - timedelta(minutes=1)),
        ("블로그 글", "Naver Blog", now - timedelta(minutes=2)),
        ("카페 글", "네이버 카페", now - timedelta(minutes=3)),
        ("정상 기사2", "머니투데이", now - timedelta(minutes=4)),
        ("티스토리 글", "티스토리", now - timedelta(minutes=5)),
        ("정상 기사3", "서울경제", now - timedelta(minutes=6)),
        ("정상 기사4", "매일경제", now - timedelta(minutes=7)),
        ("정상 기사5", "코리아포스트", now - timedelta(minutes=8)),
        ("정상 기사6", "뉴시스", now - timedelta(minutes=9)),
    ]
    body = "".join(
        f"<item><title>{t}</title><link>https://a.com/{i}</link>"
        f"<pubDate>{format_datetime(d)}</pubDate><source>{s}</source></item>"
        for i, (t, s, d) in enumerate(rows)
    )
    return f"<rss><channel>{body}</channel></rss>"


def test_parse_rss_drops_ugc_platform_sources():
    # 블로그·카페 글은 "관련 뉴스"가 아니다.
    sources = [i["source"] for i in fsn.parse_rss(_rss_with_ugc())]
    assert "Naver Blog" not in sources
    assert "네이버 카페" not in sources
    assert "티스토리" not in sources


def test_parse_rss_keeps_publisher_with_similar_name():
    # "코리아포스트"는 언론사다 — 부분 일치로 잘라내면 안 된다.
    sources = [i["source"] for i in fsn.parse_rss(_rss_with_ugc())]
    assert "코리아포스트" in sources


def test_ugc_slot_is_backfilled_not_lost():
    # UGC를 걸러낸 자리는 다음 기사로 채워진다 — 5건이 4건으로 줄지 않는다.
    merged, _ = fsn.merge([], fsn.parse_rss(_rss_with_ugc()))
    assert len(merged) == 5
    assert [m["title"] for m in merged] == [
        "정상 기사1", "정상 기사2", "정상 기사3", "정상 기사4", "정상 기사5",
    ]


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
