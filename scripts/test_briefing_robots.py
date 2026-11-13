# 30일 지난 브리핑의 noindex·sitemap 제외 회귀 테스트(2026-11-13, 애드센스 재신청 준비)
import generate_html as g

INDEX = g.ROBOTS_INDEX
NOINDEX = g.ROBOTS_NOINDEX


def _page(root, d, t, head):
    p = root / d / t
    p.mkdir(parents=True)
    (p / "index.html").write_text(f"<html><head>\n{head}\n<title>x</title></head><body>본문</body></html>", encoding="utf-8")
    return p / "index.html"


def test_30일_경계():
    assert g.briefing_indexed("2026-10-14", "2026-11-13")       # 30일째는 색인
    assert not g.briefing_indexed("2026-10-13", "2026-11-13")   # 31일째부터 noindex


def test_오래된_브리핑만_noindex로_바뀌고_본문은_그대로(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    old = _page(tmp_path, "2026-09-01", "kospi", INDEX)
    new = _page(tmp_path, "2026-11-12", "us", INDEX)
    assert g.apply_briefing_robots("2026-11-13") == 1
    assert NOINDEX in old.read_text() and INDEX not in old.read_text()
    assert "<body>본문</body>" in old.read_text()
    assert new.read_text().count(INDEX) == 1
    assert g.apply_briefing_robots("2026-11-13") == 0          # 두 번 돌려도 바뀌지 않는다


def test_robots_메타가_없는_옛_발행본엔_넣는다(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    p = _page(tmp_path, "2026-07-12", "kospi", '<meta charset="UTF-8">')
    g.apply_briefing_robots("2026-11-13")
    assert p.read_text().count(NOINDEX) == 1


def test_재생성으로_색인_메타가_돌아와도_다시_noindex(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "BRIEFINGS_DIR", tmp_path)
    p = _page(tmp_path, "2026-08-01", "close", NOINDEX)
    p.write_text(p.read_text().replace(NOINDEX, INDEX))
    assert g.apply_briefing_robots("2026-11-13") == 1 and NOINDEX in p.read_text()


def test_sitemap엔_30일_안의_브리핑만(tmp_path, monkeypatch):
    import json
    from datetime import datetime
    bdir, web, data = tmp_path / "b", tmp_path / "web", tmp_path / "data"
    for p in (bdir, web, data):
        p.mkdir()
    today = datetime.now(g.KST).date()
    recent = today.isoformat()
    old = today.replace(year=today.year - 1).isoformat()
    for d in (recent, old):
        _page(bdir, d, "kospi", INDEX)
    (data / "briefings.json").write_text(json.dumps({"briefings": [{"date": recent}, {"date": old}]}))
    monkeypatch.setattr(g, "BRIEFINGS_DIR", bdir)
    monkeypatch.setattr(g, "WEB_DIR", web)
    monkeypatch.setattr(g, "DATA_DIR", data)
    monkeypatch.setattr(g, "CONFIG_DIR", tmp_path / "noconfig")
    g.write_sitemap_xml()
    sm = (web / "sitemap.xml").read_text()
    assert f"/briefings/{recent}/kospi/" in sm
    assert f"/briefings/{old}/kospi/" not in sm
    assert NOINDEX in (bdir / old / "kospi" / "index.html").read_text()
