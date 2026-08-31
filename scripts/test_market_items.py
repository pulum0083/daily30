# 시장 지표 사이드바(VIX + 공포·탐욕 지수) 구성 테스트 — 2026-08-31 2개 항목 축소.
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_html import build_market_items, _fng_is_fresh, _fng_label  # noqa: E402

NOW = datetime(2026, 8, 31, 22, 25, tzinfo=timezone.utc)


def _md(**mdj):
    return {"market_data_js": mdj}


def _fresh_fng(**over):
    d = {"score": 54.43, "rating": "neutral", "prev_close": 58.17,
         "asof": (NOW - timedelta(hours=22)).isoformat(), "source": "cnn"}
    d.update(over)
    return d


def test_only_two_items():
    """지수·선물 행은 데이터가 있어도 더 이상 그리지 않는다."""
    items = build_market_items(_md(
        nasdaq={"base": 26541.35, "chg": 1.57, "data": [1, 2]},
        sox={"base": 11882.17, "chg": 2.33, "data": [1, 2]},
        nq={"base": 29622.25, "chg": 1.14, "data": [1, 2]},
        vix={"price": 14.51, "change_pct": -4.6},
        fng=_fresh_fng(),
    ), "kospi", "07:26")
    assert [i["name"] for i in items] == ["VIX 공포지수", "공포·탐욕 지수"]
    assert all("spark_id" not in i for i in items)


def test_fng_row_values():
    items = build_market_items(_md(fng=_fresh_fng()), "us", "21:16")
    fng = items[0]
    assert fng["val"] == "54"
    assert fng["chg"] == "-3.7p"          # 58.17 → 54.43
    assert fng["chg_cls"] == "down"
    assert fng["badge"] == "중립"
    assert fng["info_modal"] == "fng-modal"


def test_vix_row_unchanged():
    items = build_market_items(_md(vix={"price": 14.51, "change_pct": -4.6}), "kospi", "07:26")
    assert items == [{
        "name": "VIX 공포지수", "info_modal": "vix-modal", "val": "14.51",
        "chg": "-4.60%", "chg_cls": "down", "badge": "안정", "badge_cls": "calm",
    }]


def test_missing_data_omits_row():
    """수집 실패 → 행을 그리지 않는다(§0 — 없으면 비운다)."""
    assert build_market_items(_md(), "kospi", "07:26") == []
    assert build_market_items(_md(fng=_fresh_fng()), "close", "16:25") == []


def test_stale_fng_dropped():
    """수집이 조용히 죽었을 때 낡은 점수를 계속 보여주지 않는다(§20)."""
    old = _fresh_fng(asof=(NOW - timedelta(days=9)).isoformat())
    assert _fng_is_fresh(old, now=NOW) is False
    assert _fng_is_fresh(_fresh_fng(), now=NOW) is True
    # 주말·연휴로 3일 묵은 것은 정상 — 표시한다.
    assert _fng_is_fresh(_fresh_fng(asof=(NOW - timedelta(days=3)).isoformat()), now=NOW) is True


def test_broken_fng_dropped():
    assert _fng_is_fresh({"score": 50}, now=NOW) is False            # asof 없음
    assert _fng_is_fresh(_fresh_fng(asof="어제"), now=NOW) is False   # 파싱 실패
    assert _fng_is_fresh(_fresh_fng(score=None), now=NOW) is False


def test_prev_close_missing_leaves_change_blank():
    """전일 값이 없으면 0.0p로 채우지 않고 비운다 — 보합이라는 틀린 주장 방지."""
    items = build_market_items(_md(fng=_fresh_fng(prev_close=None)), "us", "21:16")
    assert items[0]["chg"] == "" and items[0]["chg_cls"] == ""


def test_label_falls_back_to_score_band():
    """CNN 등급이 없거나 모르는 값이면 점수 구간으로 되돌린다."""
    assert _fng_label(12.0, None) == ("극단적 공포", "high")
    assert _fng_label(30.0, "") == ("공포", "elevated")
    assert _fng_label(50.0, "unknown-rating") == ("중립", "calm")
    assert _fng_label(60.0, None) == ("탐욕", "elevated")
    assert _fng_label(88.0, None) == ("극단적 탐욕", "high")
    # 등급이 있으면 그것을 우선한다(경계값에서 CNN 표기와 어긋나지 않게).
    assert _fng_label(55.0, "Neutral") == ("중립", "calm")


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"✓ {name}")
            except Exception:
                fails += 1
                print(f"✗ {name}")
                traceback.print_exc()
    sys.exit(1 if fails else 0)
