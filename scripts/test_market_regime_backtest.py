# 국면 판정 실데이터 리플레이 — 375영업일 픽스처로 스펙의 검증 기준 3개를 확인한다.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from market_regime_core import (WINDOW_DAYS, basket_cum, daily_frames,  # noqa: E402
                                resolve_regimes)

FIXTURE = Path(__file__).parent.parent / "web" / "data" / "regime-backtest-fixture.json"
CONFIG = Path(__file__).parent / "config" / "regime_baskets.json"


def _replay():
    closes = json.loads(FIXTURE.read_text())["closes"]
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    names = {b["key"]: b["name"] for b in cfg["baskets"]}
    order = [b["key"] for b in cfg["baskets"]]
    allowed = {b["key"] for b in cfg["baskets"] if b["scope"] == "global"}
    cal = sorted(closes["MSFT"])            # 기준 캘린더 = 미국 거래일

    rows = []
    for i in range(WINDOW_DAYS, len(cal)):
        win = cal[i - WINDOW_DAYS:i + 1]
        cums = {}
        for b in cfg["baskets"]:
            cum, n = basket_cum(b["members"], closes, win)
            if cum:
                cums[b["key"]] = cum
        frame = daily_frames(cums)[-1]
        rows.append({"date": cal[i], "frame": frame})

    frames = [r["frame"] for r in rows]
    res = resolve_regimes(frames, names, order, allowed)
    return [r["date"] for r in rows], res


def test_no_headline_failures():
    """스펙 검증 기준 — 문구 생성 실패 0건. None이 나오면 판정과 재료가 어긋난 것."""
    _, res = _replay()
    bad = [i for i, r in enumerate(res) if not r["headline"]]
    assert not bad, f"문구 생성 실패 {len(bad)}건"


def test_transition_count_under_limit():
    """전환이 잦으면 카드가 깜빡인다. 375일 기준 15회 이하."""
    dates, res = _replay()
    st = [r["state"] for r in res]
    flips = sum(1 for i in range(1, len(st)) if st[i] != st[i - 1])
    assert flips <= 15, f"전환 {flips}회 — 임계값 재검토 필요"


def test_reproduces_observed_regimes():
    """사용자 관찰 회귀 가드 — 5~6월 메모리 주도, 7월 이후 교체."""
    dates, res = _replay()
    by_date = {d: r for d, r in zip(dates, res)}
    assert by_date["2026-05-15"]["state"] == "lead"
    assert "메모리" in by_date["2026-05-15"]["headline"]
    assert by_date["2026-07-24"]["state"] == "swap"
    assert by_date["2026-08-06"]["state"] == "swap"


def test_korea_baskets_excluded_from_headline():
    """한국 바스켓은 헤드라인 주어가 되지 않는다 — read-through 전용."""
    _, res = _replay()
    assert not any("한국" in r["headline"] for r in res)
