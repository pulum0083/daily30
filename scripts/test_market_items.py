# 시장 지표 사이드바(공포·탐욕 다이얼 + VIX·하이일드 스프레드 줄) 구성 테스트.
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_html import (build_market_items, build_fng_dial,  # noqa: E402
                           _fng_is_fresh, _fng_label)
from sections_shared import hy_state, _hy_is_fresh  # noqa: E402
from fetch_data import parse_hy_csv  # noqa: E402
from datetime import date

# 실행 시점 기준으로 잡는다. 고정 시각을 쓰면 며칠 뒤 스스로 썩는다 —
# build_fng_dial()이 내부에서 부르는 _fng_is_fresh()는 now 인자 없이 실제 벽시계와
# 대조하므로, 픽스처만 과거에 고정돼 있으면 5일 신선도 게이트(§39)에 걸려 다이얼이
# 통째로 생략되고 score·sub 키가 사라진다(2026-09-06 CI 적색 — 8/31에 고정한 값이
# 6일째 되던 날 터졌다). NOW를 상대 시각으로 두면 픽스처 사이의 관계
# (fresh=-22h, stale=-9d)는 그대로 유지되면서 시간이 지나도 깨지지 않는다.
NOW = datetime.now(timezone.utc)


def _md(**mdj):
    return {"market_data_js": mdj}


def _fresh_fng(**over):
    d = {"score": 54.43, "rating": "neutral", "prev_close": 58.17,
         "asof": (NOW - timedelta(hours=22)).isoformat(), "source": "cnn"}
    d.update(over)
    return d


def _fresh_hy(**over):
    d = {"value": 3.52, "asof": (NOW + timedelta(hours=9)).date().isoformat(), "chg10": 0.04,
         "pct_above": 8, "prev_value": 3.47, "prev_chg10": 0.15}
    d.update(over)
    return d


def test_rows_are_vix_then_hy():
    """지수·선물 행은 데이터가 있어도 그리지 않는다. 줄은 VIX → 하이일드 순."""
    md = _md(
        nasdaq={"base": 26541.35, "chg": 1.57, "data": [1, 2]},
        vix={"price": 14.51, "change_pct": -4.6},
        hy=_fresh_hy(),
        fng=_fresh_fng(),
    )
    assert [i["key"] for i in build_market_items(md, "kospi", "07:26")] == ["vix", "hy"]
    assert build_fng_dial(md, "kospi")["score"] == "54"


def test_fng_dial_values():
    d = build_fng_dial(_md(fng=_fresh_fng()), "us")
    assert d["score"] == "54"
    assert d["state"] == "중립"
    assert d["state_cls"] == "calm"
    assert d["delta"] == "−3.7p"            # 58.17 → 54.43
    assert d["prev"]["label"] == "어제 58.2"
    # 0점=왼쪽 끝(28,104), 50점=꼭대기(110,22), 100점=오른쪽 끝(192,104)
    assert build_fng_dial(_md(fng=_fresh_fng(score=0.0)), "us")["today"] == {"x": "28.0", "y": "104.0"}
    assert build_fng_dial(_md(fng=_fresh_fng(score=50.0)), "us")["today"] == {"x": "110.0", "y": "22.0"}
    assert build_fng_dial(_md(fng=_fresh_fng(score=100.0)), "us")["today"] == {"x": "192.0", "y": "104.0"}


def test_vix_row():
    it = build_market_items(_md(vix={"price": 35.89, "change_pct": 26.1955}), "kospi", "07:26")[0]
    assert it["val"] == "35.89" and it["badge"] == "불안" and it["badge_cls"] == "r"
    assert it["chg"] == "전일 28.44 · 하루 +26.2%"     # 전일 = 가격 ÷ (1 + 등락률)
    assert it["marker"] == 71.8                       # 0~50 막대
    assert it["prev_pos"] == 56.9 and it["prev_label"] == "어제 28.44"
    assert build_market_items(_md(vix={"price": 14.51, "change_pct": -4.6}), "kospi", "07:26")[0]["badge"] == "안정"


def test_hy_row():
    it = build_market_items(_md(hy=_fresh_hy()), "us", "21:15")[0]
    assert it["val"] == "3.52%" and it["badge"] == "확대 없음" and it["badge_cls"] == "g"
    assert it["chg"] == "전일 3.47% · 10거래일 +0.04%p"
    assert it["marker"] == 4.0 and it["prev_pos"] == 15.0 and it["prev_label"] == "전일 +0.15%p"
    assert it["when"].endswith("지난 3년 중 이보다 높았던 날 8%")
    # 줄어든 날은 0에 붙인다(막대는 0~+1.0%p)
    assert build_market_items(_md(hy=_fresh_hy(chg10=-0.2)), "us", "21:15")[0]["marker"] == 0.0


def test_hy_state_rules():
    assert hy_state(3.5, 0.49) == ("확대 없음", "g")
    assert hy_state(3.5, 0.50) == ("경고", "y")
    assert hy_state(5.2, 0.10) == ("강한 경고", "r")   # 5%p 이상에서 계속 벌어짐
    assert hy_state(5.2, -0.10) == ("확대 없음", "g")  # 5%p 위여도 줄어드는 중이면 아님


def test_hy_stale_dropped():
    today = date(2026, 11, 23)
    assert _hy_is_fresh({"asof": "2026-11-19"}, today=today) is True
    assert _hy_is_fresh({"asof": "2026-11-10"}, today=today) is False
    assert _hy_is_fresh({"asof": "어제"}, today=today) is False
    old = _fresh_hy(asof="2020-01-01")
    assert build_market_items(_md(hy=old), "us", "21:15") == []


def test_parse_hy_csv():
    rows = ["observation_date,BAMLH0A0HYM2"] + [f"2026-11-{d:02d},{3.00 + d / 100:.2f}" for d in range(1, 13)]
    rows.insert(5, "2026-10-31,.")             # 빈 값(.)은 건너뛴다
    out = parse_hy_csv("\n".join(rows))
    assert out["value"] == 3.12 and out["asof"] == "2026-11-12"
    assert out["chg10"] == 0.10 and out["base_date"] == "2026-11-02"
    assert out["prev_value"] == 3.11 and out["prev_chg10"] == 0.10
    assert parse_hy_csv("observation_date,BAMLH0A0HYM2\n2026-11-01,3.0") == {}


def test_missing_data_omits_row():
    """수집 실패 → 행·다이얼을 그리지 않는다(§0 — 없으면 비운다)."""
    assert build_market_items(_md(), "kospi", "07:26") == []
    assert build_fng_dial(_md(), "kospi") == {}
    # 마감 브리핑은 이 패널 자체를 쓰지 않는다.
    assert build_fng_dial(_md(fng=_fresh_fng()), "close") == {}
    assert build_market_items(_md(vix={"price": 14.51, "change_pct": -4.6}), "close", "16:25") == []
    assert build_market_items(_md(hy=_fresh_hy()), "close", "16:25") == []


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
    """전일 값이 없으면 0.0p로 채우지 않고 비운다 — 보합이라는 틀린 주장 방지. 어제 점도 뺀다."""
    d = build_fng_dial(_md(fng=_fresh_fng(prev_close=None)), "us")
    assert d["delta"] == "" and d["prev"] is None


def test_session_rollover_leaves_sub_blank():
    """CNN 프리마켓 롤오버 실사고(2026-08-31): score == previous_close면 비운다.

    미국 브리핑은 21:15 KST(= 프리마켓)에 나가는데, 그 시각 CNN은 직전 종가를 이미
    previous_close로 넘겨놓고 새 세션 값은 아직 내지 않아 두 값이 완전히 같아진다.
    그대로 두면 '+0.0p'(보합)라는 틀린 주장이 매일 발행된다.
    """
    same = _fresh_fng(score=54.4285714285714, prev_close=54.4285714285714)
    assert build_fng_dial(_md(fng=same), "us")["delta"] == ""
    # 표시상 0.0p로 반올림되는 미세 변화도 같은 이유로 비운다.
    assert build_fng_dial(_md(fng=_fresh_fng(score=54.43, prev_close=54.40)), "us")["prev"] is None
    # 0.1p부터는 정상 표시한다(오제거 방지).
    assert build_fng_dial(_md(fng=_fresh_fng(score=54.5, prev_close=54.4)), "us")["delta"] == "+0.1p"


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
