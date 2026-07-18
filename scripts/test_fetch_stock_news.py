# 종목별 뉴스 수집의 중복 제거와 og:image 추출을 검증하는 테스트
import json
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


def test_merge_keeps_recovered_publisher_over_bare_domain():
    # 복구한 발행사명은 summary·thumb과 같은 파생 데이터다 — 폴링마다 도메인으로 되돌아가면
    # 기사가 상위 5건에 남아 있는 내내 위젯에 도메인이 노출된다.
    old = [{"url": "https://a.com/1", "title": "제목", "summary": "요약이에요.",
            "thumb": None, "time": "09:00", "source": "이비엔(EBN)뉴스센터"}]
    new = [{"url": "https://a.com/1", "title": "제목", "time": "09:30",
            "source": "ebn.co.kr"}]
    merged, _ = fsn.merge(old, new)
    assert merged[0]["source"] == "이비엔(EBN)뉴스센터"


def test_merge_lets_fresh_publisher_name_override_stored_one():
    # RSS가 제대로 된 언론사명을 주기 시작하면 그쪽이 이긴다 — 통째로 보존하지 않는다.
    old = [{"url": "https://a.com/1", "title": "제목", "summary": "요약이에요.",
            "thumb": None, "time": "09:00", "source": "옛언론사"}]
    new = [{"url": "https://a.com/1", "title": "제목", "time": "09:30",
            "source": "새언론사"}]
    merged, _ = fsn.merge(old, new)
    assert merged[0]["source"] == "새언론사"


def test_merge_still_refreshes_title_and_time_on_carry_over():
    # 출처 보존이 제목·시각까지 얼려버리면 안 된다 — 그 둘은 실제로 바뀌는 값이다.
    old = [{"url": "https://a.com/1", "title": "옛 제목", "summary": "요약이에요.",
            "thumb": "t.jpg", "time": "08:00", "source": "이비엔(EBN)뉴스센터"}]
    new = [{"url": "https://a.com/1", "title": "새 제목", "time": "09:30",
            "source": "ebn.co.kr"}]
    merged, _ = fsn.merge(old, new)
    assert merged[0]["title"] == "새 제목"
    assert merged[0]["time"] == "09:30"
    assert merged[0]["source"] == "이비엔(EBN)뉴스센터"


def test_merge_source_carry_over_does_not_retrigger_summarize():
    # 출처를 보존해도 todo 판정은 summary 유무로만 한다 — 여기가 무너지면 비용 모델이 깨진다.
    old = [{"url": "https://a.com/1", "title": "제목", "summary": "요약이에요.",
            "thumb": None, "time": "09:00", "source": "이비엔(EBN)뉴스센터"}]
    new = [{"url": "https://a.com/1", "title": "제목", "time": "09:30",
            "source": "ebn.co.kr"}]
    _, todo = fsn.merge(old, new)
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


def test_build_prompt_lists_all_titles():
    items = [{"title": "제목A", "source": "S1"}, {"title": "제목B", "source": "S2"}]
    p = fsn.build_prompt("삼성전자", items)
    assert "제목A" in p and "제목B" in p
    assert "삼성전자" in p
    assert "해요체" in p
    assert "습니다" in p  # 합쇼체 금지 문구 포함 확인
    assert "JSON" in p


def test_apply_summaries_matches_by_index():
    merged = [{"url": "u1", "summary": ""}, {"url": "u2", "summary": "기존"}]
    todo = [{"url": "u1"}]
    fsn.apply_summaries(merged, todo, ["새 요약이에요."])
    assert merged[0]["summary"] == "새 요약이에요."
    assert merged[1]["summary"] == "기존"


def test_apply_summaries_tolerates_short_response():
    # Gemini가 요청보다 적게 돌려줘도 죽지 않아야 한다
    merged = [{"url": "u1", "summary": ""}, {"url": "u2", "summary": ""}]
    todo = [{"url": "u1"}, {"url": "u2"}]
    fsn.apply_summaries(merged, todo, ["하나만 왔어요."])
    assert merged[0]["summary"] == "하나만 왔어요."
    assert merged[1]["summary"] == ""


def test_apply_summaries_tolerates_long_response():
    # Gemini가 요청보다 많이 돌려줘도 초과분은 무시한다
    merged = [{"url": "u1", "summary": ""}]
    todo = [{"url": "u1"}]
    fsn.apply_summaries(merged, todo, ["요약이에요.", "여분1", "여분2"])
    assert merged[0]["summary"] == "요약이에요."


def test_summarize_returns_empty_without_api_key(monkeypatch):
    # 키가 없으면 HTTP 호출 자체를 하지 않아야 한다 — 조용히 실패해도 절대 죽지 않는다
    monkeypatch.setattr(fsn, "get_gemini_api_key", lambda: "")

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("GEMINI_API_KEY 없이 HTTP 호출을 시도했다")

    monkeypatch.setattr(fsn.urllib.request, "urlopen", _fail_if_called)

    result = fsn.summarize("삼성전자", [{"title": "제목", "source": "S"}])
    assert result == []


def test_summarize_returns_empty_when_no_todo_items(monkeypatch):
    # todo가 비어 있으면(가장 흔한 폴링) 애초에 Gemini를 호출하지 않는다 — 비용 모델의 핵심
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("todo가 비었는데 HTTP 호출을 시도했다")

    monkeypatch.setattr(fsn.urllib.request, "urlopen", _fail_if_called)
    assert fsn.summarize("삼성전자", []) == []


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_summarize_parses_gemini_response(monkeypatch):
    monkeypatch.setattr(fsn, "get_gemini_api_key", lambda: "fake-key")
    gemini_body = json.dumps({
        "candidates": [{"content": {"parts": [{"text": '["요약1이에요.", "요약2이에요."]'}]}}]
    }).encode("utf-8")
    monkeypatch.setattr(
        fsn.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(gemini_body)
    )
    result = fsn.summarize("삼성전자", [{"title": "제목A", "source": "S"}, {"title": "제목B", "source": "S"}])
    assert result == ["요약1이에요.", "요약2이에요."]


def test_summarize_returns_empty_on_http_error(monkeypatch):
    monkeypatch.setattr(fsn, "get_gemini_api_key", lambda: "fake-key")

    def _raise(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(fsn.urllib.request, "urlopen", _raise)
    assert fsn.summarize("삼성전자", [{"title": "제목", "source": "S"}]) == []


def test_enrich_new_items_recovers_publisher_from_bare_domain(monkeypatch):
    merged = [{"url": "https://v.daum.net/v/123", "source": "v.daum.net", "thumb": None}]
    todo = [{"url": "https://v.daum.net/v/123"}]

    html_page = (
        '<meta property="og:site_name" content="이데일리">'
        '<meta property="og:image" content="https://img.com/a.jpg">'
    )
    monkeypatch.setattr(fsn, "_fetch", lambda url, timeout=15: html_page)

    fsn.enrich_new_items(merged, todo)
    assert merged[0]["source"] == "이데일리"
    assert merged[0]["thumb"] == "https://img.com/a.jpg"


def test_enrich_new_items_keeps_proper_publisher_name(monkeypatch):
    # 이미 정상적인 한글 언론사명이면 og:site_name이 달라도 절대 덮어쓰지 않는다
    merged = [{"url": "https://a.com/1", "source": "한국경제", "thumb": None}]
    todo = [{"url": "https://a.com/1"}]

    html_page = '<meta property="og:site_name" content="다른이름">'
    monkeypatch.setattr(fsn, "_fetch", lambda url, timeout=15: html_page)

    fsn.enrich_new_items(merged, todo)
    assert merged[0]["source"] == "한국경제"


def test_enrich_new_items_leaves_domain_when_site_name_absent(monkeypatch):
    # og:site_name이 없으면 도메인이어도 임의로 값을 만들어내지 않는다 (운영규칙 0)
    merged = [{"url": "https://ebn.co.kr/1", "source": "ebn.co.kr", "thumb": None}]
    todo = [{"url": "https://ebn.co.kr/1"}]

    html_page = "<html><body>no meta</body></html>"
    monkeypatch.setattr(fsn, "_fetch", lambda url, timeout=15: html_page)

    fsn.enrich_new_items(merged, todo)
    assert merged[0]["source"] == "ebn.co.kr"
    assert merged[0]["thumb"] is None


def test_resolve_gnews_url_passes_through_non_gnews_links():
    # 구글 뉴스 리다이렉트 형태가 아니면 네트워크 호출 없이 그대로 반환한다
    assert fsn._resolve_gnews_url("https://v.daum.net/v/123") == "https://v.daum.net/v/123"


def test_enrich_new_items_never_promotes_google_news_as_publisher(monkeypatch):
    # 구글 뉴스 링크 리졸브가 실패해 인터스티셜 페이지를 그대로 fetch하면
    # og:site_name이 "Google News"로 나온다 — 발행사명이 아니므로 절대 승격하지 않는다.
    link = "https://news.google.com/rss/articles/abc123"
    merged = [{"url": link, "source": "v.daum.net", "thumb": None}]
    todo = [{"url": link}]

    monkeypatch.setattr(fsn, "_resolve_gnews_url", lambda url: url)  # 리졸브 실패 시뮬레이션
    html_page = (
        '<meta property="og:site_name" content="Google News">'
        '<meta property="og:image" content="https://lh3.googleusercontent.com/icon.png">'
    )
    monkeypatch.setattr(fsn, "_fetch", lambda url, timeout=15: html_page)

    fsn.enrich_new_items(merged, todo)
    assert merged[0]["source"] == "v.daum.net"
