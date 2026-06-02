# 섹터 로테이션 순수 함수 단위 테스트
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
import call_claude as cc


def test_sector_pool_has_8_unique_keys():
    keys = [s["key"] for s in cc.SECTOR_POOL]
    assert len(keys) == 8
    assert len(set(keys)) == 8
    for s in cc.SECTOR_POOL:
        assert s["key"] and s["name"] and s["emoji"]


def test_avoidance_hint_empty_when_no_history():
    assert cc.build_sector_avoidance_hint([]) == ""


def test_avoidance_hint_lists_recent_sector_names():
    history = [
        {"date": "2026-06-02", "sector_key": "semicon"},
        {"date": "2026-06-01", "sector_key": "defense"},
    ]
    hint = cc.build_sector_avoidance_hint(history, days=5)
    assert "반도체" in hint
    assert "방산" in hint
    assert "sector_focus" in hint


def test_pick_sector_keeps_valid_choice_and_injects_meta():
    focus = {"sector_key": "defense", "signal": "x", "paragraphs": ["a"]}
    result = cc.pick_sector(focus, recent_keys=[])
    assert result["sector_key"] == "defense"
    assert result["sector_name"] == "방산"
    assert result["emoji"] == "🛡️"
    assert result["signal"] == "x"
    assert result["paragraphs"] == ["a"]


def test_pick_sector_falls_back_when_key_invalid():
    result = cc.pick_sector({"sector_key": "nonsense"}, recent_keys=["semicon"])
    assert result["sector_key"] == "power"
    assert result["sector_name"] == "AI전력기기"


def test_pick_sector_keeps_valid_recent_duplicate():
    # 스펙: 유효 키가 최근 이력과 중복이어도 강제 교체하지 않고 유지한다 (경고만).
    result = cc.pick_sector({"sector_key": "semicon", "signal": "s"}, recent_keys=["semicon", "defense"])
    assert result["sector_key"] == "semicon"
    assert result["sector_name"] == "반도체"


def test_pick_sector_handles_none_focus():
    result = cc.pick_sector(None, recent_keys=[])
    assert result["sector_key"] == "semicon"
    assert result["signal"] == ""
    assert result["paragraphs"] == []


if __name__ == "__main__":
    import inspect
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and inspect.isfunction(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
