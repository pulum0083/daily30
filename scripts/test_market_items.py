# 시장 지표 사이드바(VIX + 공포·탐욕 지수) 구성 테스트 — 2026-08-31 2개 항목 축소.
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_html import (build_market_items, build_fng_dial,  # noqa: E402
                           _fng_is_fresh, _fng_label)

NOW = datetime(2026, 8, 31, 22, 25, tzinfo=timezone.utc)


def _md(**mdj):
    return {"market_data_js": mdj}


def _fresh_fng(**over):
    d = {"score": 54.43, "rating": "neutral", "prev_close": 58.17,
         "asof": (NOW - timedelta(hours=22)).isoformat(), "source": "cnn"}
    d.update(over)
    return d


def test_only_vix_row_remains():
    """지수·선물 행은 데이터가 있어도 더 이상 그리지 않는다(공포·탐욕은 다이얼로 분리)."""
    md = _md(
        nasdaq={"base": 26541.35, "chg": 1.57, "data": [1, 2]},
        sox={"base": 11882.17, "chg": 2.33, "data": [1, 2]},
        nq={"base": 29622.25, "chg": 1.14, "data": [1, 2]},
        vix={"price": 14.51, "change_pct": -4.6},
        fng=_fresh_fng(),
    )
    assert [i["name"] for i in build_market_items(md, "kospi", "07:26")] == ["VIX 공포지수"]
    assert build_fng_dial(md, "kospi")["score"] == "54"


def test_fng_dial_values():
    d = build_fng_dial(_md(fng=_fresh_fng()), "us")
    assert d["score"] == "54"
    assert d["state"] == "중립"
    assert d["state_cls"] == "calm"
    assert d["sub"] == "전일 58.2 · -3.7p"   # 58.17 → 54.43
    # 0점=왼쪽(-90°), 50점=위(0°), 100점=오른쪽(+90°)
    assert d["needle_deg"] == 7.97
    assert build_fng_dial(_md(fng=_fresh_fng(score=0.0)), "us")["needle_deg"] == -90.0
    assert build_fng_dial(_md(fng=_fresh_fng(score=50.0)), "us")["needle_deg"] == 0.0
    assert build_fng_dial(_md(fng=_fresh_fng(score=100.0)), "us")["needle_deg"] == 90.0


def test_vix_row_unchanged():
    items = build_market_items(_md(vix={"price": 14.51, "change_pct": -4.6}), "kospi", "07:26")
    assert items == [{
        "name": "VIX 공포지수", "info_modal": "vix-modal", "val": "14.51",
        "chg": "-4.60%", "chg_cls": "down", "badge": "안정", "badge_cls": "calm",
    }]


def test_missing_data_omits_row():
    """수집 실패 → 행·다이얼을 그리지 않는다(§0 — 없으면 비운다)."""
    assert build_market_items(_md(), "kospi", "07:26") == []
    assert build_fng_dial(_md(), "kospi") == {}
    # 마감 브리핑은 이 패널 자체를 쓰지 않는다.
    assert build_fng_dial(_md(fng=_fresh_fng()), "close") == {}
    assert build_market_items(_md(vix={"price": 14.51, "change_pct": -4.6}), "close", "16:25") == []


def test_stale_fng_dial_dropped():
    """낡은 점수로 다이얼을 그리지 않는다 — 게이트가 다이얼 경로에도 걸려 있어야 한다."""
    old = _fresh_fng(asof=(NOW - timedelta(days=9)).isoformat())
    assert build_fng_dial(_md(fng=old), "kospi") == {}


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


def test_prev_close_missing_leaves_sub_blank():
    """전일 값이 없으면 0.0p로 채우지 않고 비운다 — 보합이라는 틀린 주장 방지."""
    assert build_fng_dial(_md(fng=_fresh_fng(prev_close=None)), "us")["sub"] == ""


def test_session_rollover_leaves_sub_blank():
    """CNN 프리마켓 롤오버 실사고(2026-08-31): score == previous_close면 비운다.

    미국 브리핑은 21:15 KST(= 프리마켓)에 나가는데, 그 시각 CNN은 직전 종가를 이미
    previous_close로 넘겨놓고 새 세션 값은 아직 내지 않아 두 값이 완전히 같아진다.
    그대로 두면 '+0.0p'(보합)라는 틀린 주장이 매일 발행된다.
    """
    same = _fresh_fng(score=54.4285714285714, prev_close=54.4285714285714)
    assert build_fng_dial(_md(fng=same), "us")["sub"] == ""
    # 표시상 0.0p로 반올림되는 미세 변화도 같은 이유로 비운다.
    assert build_fng_dial(_md(fng=_fresh_fng(score=54.43, prev_close=54.40)), "us")["sub"] == ""
    # 0.1p부터는 정상 표시한다(오제거 방지).
    assert build_fng_dial(_md(fng=_fresh_fng(score=54.5, prev_close=54.4)), "us")["sub"] \
        == "전일 54.4 · +0.1p"


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
