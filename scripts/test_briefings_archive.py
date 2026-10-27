# /briefings/ 정적 아카이브 — 2026-09-02 리다이렉트 스텁 제거 후 회귀 가드.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generate_html as g  # noqa: E402


def _publish(root, date, btype, snapshot=None, desc=None):
    """발행본 한 편을 디스크에 만든다(아카이브의 원본은 data/*.json이 아니라 이 파일들이다)."""
    d = root / date / btype
    d.mkdir(parents=True)
    meta = f'<meta name="description" content="{desc}">' if desc else ""
    (d / "index.html").write_text(f"<html><head>{meta}</head></html>", encoding="utf-8")
    if snapshot is not None:
        (d / "analysis_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False),
                                                  encoding="utf-8")


def test_groups_by_month_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    _publish(tmp_path, "2026-08-28", "kospi", {"reason_title": "8월 브리핑"})
    _publish(tmp_path, "2026-09-01", "us", {"todays_view": {"view_title": "9월 브리핑"}})
    _publish(tmp_path, "2026-09-02", "kospi", {"reason_title": "가장 최근"})
    ctx = g.build_archive_context()
    assert ctx["total"] == 3
    assert [m["label"] for m in ctx["months"]] == ["2026년 9월", "2026년 8월"]
    assert [d["date"] for d in ctx["months"][0]["days"]] == ["2026-09-02", "2026-09-01"]


def test_headline_priority(tmp_path, monkeypatch):
    """todays_view.view_title → reason_title → market_title → meta description."""
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    _publish(tmp_path, "2026-09-01", "kospi",
             {"todays_view": {"view_title": "관점"}, "reason_title": "근거"}, desc="설명")
    _publish(tmp_path, "2026-09-01", "close", {"market_title": "마감 제목"}, desc="설명")
    _publish(tmp_path, "2026-09-01", "us", None, desc="메타 설명만 있음")
    day = g.build_archive_context()["months"][0]["days"][0]
    got = {i["label"]: i["headline"] for i in day["briefings"]}
    assert got["코스피 예측"] == "관점"
    assert got["코스피 마감"] == "마감 제목"
    assert got["미국 시장"] == "메타 설명만 있음"


def test_no_headline_stays_empty(tmp_path, monkeypatch):
    """헤드라인이 없으면 비운다 — 지어내지 않는다(§0)."""
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    _publish(tmp_path, "2026-09-01", "kospi", None)
    assert g.build_archive_context()["months"][0]["days"][0]["briefings"][0]["headline"] == ""


def test_only_published_pages_listed(tmp_path, monkeypatch):
    """index.html이 없는 디렉터리(수집만 되고 미발행)는 목록에 넣지 않는다."""
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    _publish(tmp_path, "2026-09-01", "kospi", {"reason_title": "발행됨"})
    (tmp_path / "2026-09-01" / "close").mkdir()          # index.html 없음
    (tmp_path / "notadate").mkdir()                      # 날짜 아닌 디렉터리
    ctx = g.build_archive_context()
    assert ctx["total"] == 1
    assert len(ctx["months"][0]["days"]) == 1


def test_empty_archive_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    assert g.build_archive_context() == {"months": [], "total": 0}


def test_day_key_is_not_items(tmp_path, monkeypatch):
    """Jinja는 dict의 .items 메서드를 먼저 잡아 렌더가 깨진다 — 키 이름을 되돌리지 말 것."""
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    _publish(tmp_path, "2026-09-01", "kospi", {"reason_title": "x"})
    day = g.build_archive_context()["months"][0]["days"][0]
    assert "briefings" in day and "items" not in day


def test_rendered_page_has_no_redirect_and_no_bottom_list(tmp_path, monkeypatch):
    """구조 불변식 두 가지: JS 리다이렉트 없음, main.js가 다시 그리는 클래스 아님."""
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    monkeypatch.setattr(g, "STOCKS_HOME_HTML", tmp_path / "no-stocks.html")   # 실제 /stocks/ 페이지를 건드리지 않게
    _publish(tmp_path, "2026-09-01", "kospi", {"reason_title": "헤드라인 문장"})
    g.write_briefings_index()
    html = (tmp_path / "index.html").read_text()
    assert "location.replace" not in html
    assert "bottom-list" not in html        # patchBriefingList()가 최근 10일로 덮어쓰는 클래스
    # 최신 1편은 is-featured가 붙으므로 클래스 문자열 완전일치로 보지 않는다.
    assert 'class="arch-item' in html
    assert "헤드라인 문장" in html
    assert 'rel="canonical" href="https://doubleshot.space/briefings/"' in html


def _flat(ctx):
    return [i for m in ctx["months"] for d in m["days"] for i in d["briefings"]]


def test_newest_published_first_within_a_day():
    """하루 안에서도 최신 발행이 위 — 미국(21:15) → 마감(16:25) → 예측(07:25)."""
    assert g.ARCHIVE_TYPES == ["us", "close", "kospi"]


def test_only_newest_gets_dek(tmp_path, monkeypatch):
    """맨 위 최신 1편만 서브타이틀을 갖는다 — 전부 달면 목록이 훑기 어려워진다.

    같은 날 여러 편이 있으면 **가장 늦게 발행된 것**이 맨 위이자 featured다.
    """
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    _publish(tmp_path, "2026-09-02", "us",
             {"todays_view": {"view_title": "옛날", "dek": "옛날 요약"}})
    _publish(tmp_path, "2026-09-04", "kospi", {"reason_title": "그날 아침"})
    _publish(tmp_path, "2026-09-04", "close",
             {"reason_title": "그날 마감", "sc_summary": "마감 요약"})
    flat = _flat(g.build_archive_context())
    # 09-04엔 마감(16:25)이 예측(07:25)보다 나중이므로 마감이 맨 위이자 featured
    assert [i["headline"] for i in flat] == ["그날 마감", "그날 아침", "옛날"]
    assert flat[0]["dek"] == "마감 요약" and flat[0].get("featured") is True
    assert all("dek" not in i and "featured" not in i for i in flat[1:])


def test_featured_is_us_when_all_three_published(tmp_path, monkeypatch):
    """3종이 다 있는 날이면 미국(21:15)이 맨 위다."""
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    for t, title in (("kospi", "예측"), ("close", "마감"), ("us", "미국")):
        _publish(tmp_path, "2026-09-03", t, {"reason_title": title})
    flat = _flat(g.build_archive_context())
    assert [i["headline"] for i in flat] == ["미국", "마감", "예측"]
    assert flat[0].get("featured") is True


def test_dek_falls_back_to_sc_summary(tmp_path, monkeypatch):
    """마감 브리핑은 todays_view.dek이 없고 sc_summary가 같은 역할을 한다."""
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    _publish(tmp_path, "2026-09-04", "close",
             {"reason_title": "마감 제목", "sc_summary": "마감 요약 문장"})
    flat = g.build_archive_context()["months"][0]["days"][0]["briefings"]
    assert flat[0]["dek"] == "마감 요약 문장"


def test_missing_dek_is_empty(tmp_path, monkeypatch):
    """요약이 없으면 빈 문자열 → 템플릿에서 그 줄이 빠진다(지어내지 않는다)."""
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    _publish(tmp_path, "2026-09-04", "kospi", {"reason_title": "제목만"})
    assert g.build_archive_context()["months"][0]["days"][0]["briefings"][0]["dek"] == ""


def test_committed_archive_order_matches_archive_types():
    """커밋된 아카이브 HTML의 하루 안 순서가 ARCHIVE_TYPES와 일치해야 한다.

    2026-09-04 사고: 브리핑 잡이 재생성한 아카이브 위로 내 커밋이 rebase되면서,
    **충돌 없이** 날짜별로 순서가 뒤섞인 하이브리드 파일이 만들어졌다(9/3은 새 순서,
    9/4는 옛 순서). 생성물은 통째로 다시 쓰이는 파일이라 diff 병합이 성립하지 않는데
    git이 조용히 합쳐버린 것이라, 아무 경고도 없었다.

    이 테스트는 발행본 디스크가 아니라 **커밋된 결과물**을 검사하므로 그 상태를 잡는다.
    """
    page = g.BRIEFINGS_DIR / "index.html"
    if not page.exists():
        return                                  # 아카이브가 아직 없는 저장소는 검사 대상 아님
    html = page.read_text(encoding="utf-8")
    label_to_type = {v: k for k, v in g.BRIEFING_LABELS.items()}
    rank = {t: i for i, t in enumerate(g.ARCHIVE_TYPES)}

    # 날짜 블록별로 라벨이 나타난 순서를 뽑는다.
    import re
    for block in re.split(r'<section class="arch-day">', html)[1:]:
        labels = re.findall(r'class="arch-item__label">([^<]+)<', block)
        ranks = [rank[label_to_type[l]] for l in labels if l in label_to_type]
        date = re.search(r'class="arch-day__date">([^<]*)', block)
        assert ranks == sorted(ranks), (
            f"{date.group(1) if date else '?'} 날짜의 순서가 ARCHIVE_TYPES와 다릅니다: {labels}"
        )


# ── /stocks/ 최근 브리핑 정적 목록(2026-10-27, §70) ──
def _stocks_page(tmp_path, monkeypatch):
    page = tmp_path / "stocks.html"
    page.write_text(f"<ol>\n      {g.RECENT_START}\n      {g.RECENT_END}\n      </ol>", encoding="utf-8")
    monkeypatch.setattr(g, "STOCKS_HOME_HTML", page)
    return page


def test_recent_briefings_newest_first_and_only_first_has_dek(tmp_path, monkeypatch):
    root = tmp_path / "b"
    monkeypatch.setattr(g, "BRIEFINGS_DIR", root)
    _publish(root, "2026-10-26", "us", {"todays_view": {"view_title": "미국 제목", "dek": "미국 요약"}})
    _publish(root, "2026-10-27", "kospi", {"todays_view": {"view_title": "코스피 제목", "dek": "코스피 요약"}})
    _publish(root, "2026-10-27", "close", {"reason_title": "마감 <b>제목</b>", "dek": "외국인 <b>5,929억원</b><i>x</i>"})
    page = _stocks_page(tmp_path, monkeypatch)
    assert g.write_stocks_recent_briefings() is True
    out = page.read_text(encoding="utf-8")
    assert out.index("/2026-10-27/close/") < out.index("/2026-10-27/kospi/") < out.index("/2026-10-26/us/")
    assert "10/27(화) · 코스피 마감" in out and '<div class="rb-h">마감 제목</div>' in out
    assert "외국인 <b>5,929억원</b>x" in out          # 마감 dek(2026-10-25~)도 읽고, <b>만 남긴다
    assert "코스피 요약" not in out and "미국 요약" not in out   # 요약은 맨 위 1편만


def test_recent_briefings_rerun_is_stable_and_skips_without_markers(tmp_path, monkeypatch):
    root = tmp_path / "b"
    monkeypatch.setattr(g, "BRIEFINGS_DIR", root)
    _publish(root, "2026-10-27", "kospi", {"reason_title": "제목"})
    page = _stocks_page(tmp_path, monkeypatch)
    g.write_stocks_recent_briefings()
    first = page.read_text(encoding="utf-8")
    g.write_stocks_recent_briefings()
    assert page.read_text(encoding="utf-8") == first
    page.write_text("<html>표시 없음</html>", encoding="utf-8")
    assert g.write_stocks_recent_briefings() is False
    assert page.read_text(encoding="utf-8") == "<html>표시 없음</html>"


def test_committed_stocks_page_has_recent_markers():
    s = (Path(__file__).parent.parent / "web" / "stocks" / "index.html").read_text(encoding="utf-8")
    assert g.RECENT_START in s and g.RECENT_END in s
    assert "비상업적" not in s and "밸류에이션 시그널" not in s and "장중 이슈" not in s


def test_rss_lists_newest_first_with_head_titles(tmp_path, monkeypatch):
    """RSS(2026-10-27) — 최신순, 제목은 페이지 <head>와 같은 briefing_head, 유효한 XML."""
    import xml.dom.minidom
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    _publish(tmp_path, "2026-10-26", "us", {"todays_view": {"view_title": 'S&P "반등"', "dek": "선물이 올라요."},
                                           "generated_at": "2026-10-26T21:17:00+09:00"})
    _publish(tmp_path, "2026-10-27", "close", {"market_title": "개미만 팔았다"})
    assert g.write_briefings_rss() is True
    doc = xml.dom.minidom.parse(str(tmp_path / "rss.xml"))
    items = doc.getElementsByTagName("item")
    titles = [i.getElementsByTagName("title")[0].firstChild.data for i in items]
    assert titles == ["코스피 마감 시황 10월 27일 | 개미만 팔았다", '미국 증시 전망 10월 26일 | S&P "반등"']
    dates = [i.getElementsByTagName("pubDate")[0].firstChild.data for i in items]
    assert dates == ["Tue, 27 Oct 2026 16:30:00 +0900", "Mon, 26 Oct 2026 21:17:00 +0900"]   # 스냅샷 시각 없으면 정해진 발행 시각


def test_rss_not_written_without_briefings(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    assert g.write_briefings_rss() is False
    assert not (tmp_path / "rss.xml").exists()
