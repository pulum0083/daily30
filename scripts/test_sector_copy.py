# 섹터 페이지 카피 로더 — 2026-09-02 파이썬 리터럴 딕셔너리에서 데이터 파일로 분리.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generate_html as g  # noqa: E402

SECTORS = ["semicon", "power", "defense", "ship", "battery", "auto", "bio", "finance"]


def test_all_sectors_have_copy():
    """8개 섹터 전부 카피가 있어야 한다 — 하나라도 비면 그 페이지만 조용히 얇아진다."""
    for key in SECTORS:
        c = g._sector_copy(key)
        assert c.get("lead"), key
        assert c.get("intro"), key
        assert c.get("composition"), key


def test_copy_is_substantial():
    """§ 얇은 설명은 thin content 판정을 부른다 — 섹터당 최소 300자."""
    for key in SECTORS:
        c = g._sector_copy(key)
        total = len(c["lead"]) + len(c["intro"]) + len(c["composition"])
        assert total >= 300, f"{key}: {total}자"


def test_intros_are_distinct():
    """8개 페이지가 같은 문단을 쓰면 중복 콘텐츠가 된다."""
    intros = [g._sector_copy(k)["intro"] for k in SECTORS]
    assert len(set(intros)) == len(intros)


def test_unknown_key_is_empty():
    """없는 섹터는 빈 dict → 템플릿에서 문단이 통째로 빠진다(§0 — 없으면 비운다)."""
    assert g._sector_copy("nonexistent") == {}


def test_missing_file_is_safe(monkeypatch, tmp_path):
    """카피 파일이 없어도 페이지 생성은 계속돼야 한다(경고만)."""
    monkeypatch.setattr(g, "_SECTOR_COPY_PATH", tmp_path / "없는파일.json")
    assert g._sector_copy("semicon") == {}


def test_config_key_matches_universe():
    """stock_universe.json의 섹터 키와 어긋나면 카피가 조용히 누락된다."""
    universe = json.loads((g.CONFIG_DIR / "stock_universe.json").read_text(encoding="utf-8"))
    keys = set(universe["sectors"])
    copy = json.loads((g.CONFIG_DIR / "sector_copy.json").read_text(encoding="utf-8"))
    copy_keys = set(k for k in copy if not k.startswith("_"))
    assert keys == copy_keys, f"universe만: {keys - copy_keys} / copy만: {copy_keys - keys}"


def test_bellwether_links_are_existence_gated():
    """상세 페이지가 실제로 있는 벨웨더만 링크한다 — 없는 페이지로 링크하면 죽은 링크(§36)."""
    semicon = g._sector_bellwether_links("semicon")
    assert [b["url"] for b in semicon] == ["/stocks/us/nvda/", "/stocks/us/mu/", "/stocks/us/soxx/"]
    # 벨웨더는 정의돼 있지만 상세 페이지가 없는 섹터는 빈 리스트 → 그 줄이 통째로 빠진다
    for key in ("auto", "finance", "power", "defense", "battery", "bio"):
        assert g._sector_bellwether_links(key) == [], key
    # 벨웨더 자체가 없는 섹터
    assert g._sector_bellwether_links("ship") == []


def test_bellwether_unknown_sector_is_safe():
    assert g._sector_bellwether_links("nonexistent") == []
