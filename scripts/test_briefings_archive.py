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
    _publish(tmp_path, "2026-09-01", "kospi", {"reason_title": "헤드라인 문장"})
    g.write_briefings_index()
    html = (tmp_path / "index.html").read_text()
    assert "location.replace" not in html
    assert "bottom-list" not in html        # patchBriefingList()가 최근 10일로 덮어쓰는 클래스
    assert 'class="arch-item"' in html
    assert "헤드라인 문장" in html
    assert 'rel="canonical" href="https://doubleshot.space/briefings/"' in html
