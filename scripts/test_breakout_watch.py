# 돌파 관찰 목록(§88) 테스트 — 돌파 판정·결과 추적·렌더 게이트·11/5 실데이터 렌더
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import breakout_watch as bw  # noqa: E402
import generate_html as gh  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "breakout_watch_20261105.json"
DAYS = pd.bdate_range("2026-01-01", periods=80)


def frame(vals: dict) -> pd.DataFrame:
    return pd.DataFrame(vals, index=DAYS[:len(next(iter(vals.values())))])


def test_breakout_counts_first_cross_within_window():
    n = 30
    h = np.full(n, 100.0)
    h[20] = 106.0                       # 조건일(15)로부터 5일째 첫 돌파
    h[22] = 107.0                       # 이미 넘은 뒤라 다시 세지 않는다
    kq = frame({"A": [i == 15 for i in range(n)]})
    pv = frame({"A": [105.0] * n})
    out = bw.find_breakouts(kq, frame({"A": h}), pv, 0, n - 1)
    assert out == [("A", 20, 15)]


def test_breakout_outside_window_is_ignored():
    n = 30
    h = np.full(n, 100.0)
    h[21] = 106.0                       # 조건일(15)로부터 6일째 — 창(5일) 밖
    kq = frame({"A": [i == 15 for i in range(n)]})
    out = bw.find_breakouts(kq, frame({"A": h}), frame({"A": [105.0] * n}), 0, n - 1)
    assert out == []


def test_same_stock_not_counted_again_within_10_days():
    n = 40
    h = np.full(n, 100.0)
    h[11], h[16], h[30] = 106, 106, 106
    q = [i in (10, 15, 29) for i in range(n)]
    pv = [105.0 if i < 13 else 110.0 if i < 20 else 105.0 for i in range(n)]
    pv[15] = 105.0
    out = bw.find_breakouts(frame({"A": q}), frame({"A": h}), frame({"A": pv}), 0, n - 1)
    assert [i for _, i, _ in out] == [11, 30]   # 16은 11과 5일 차이 — 뺀다


def _fake(monkeypatch, O, H, L, C, kq, pv10, N, lo20):
    monkeypatch.setattr(bw, "MIN_VALID", 1)
    rk = {b: C * 0 + 0.99 for b in ("1달", "3달", "6달")}
    ret = {b: C * 0 + 0.3 for b in ("1달", "3달", "6달")}
    monkeypatch.setattr(bw, "indicators", lambda *a: {"kq": kq, "pv10": pv10, "N": N, "lo20": lo20, "rk": rk, "ret": ret})


def _series(n, close):
    C = frame({"A": close})
    return C, C.copy(), C + 1, C - 1


def test_breakout_then_stop_goes_to_results(monkeypatch):
    n = 60
    close = [104.0] * n
    C, O, H, L = _series(n, close)
    H.iloc[50, 0] = 106                 # 50일째 돌파(기준선 105), 산 가격 = max(105, 시가 100) = 105
    L.iloc[55, 0] = 90                  # 55일째 저가가 손절선(105 − 2×2 = 101) 아래
    kq = frame({"A": [i == 48 for i in range(n)]})
    _fake(monkeypatch, O, H, L, C, kq, frame({"A": [105.0] * n}), frame({"A": [2.0] * n}), frame({"A": [50.0] * n}))
    r = bw.compute(O, H, L, C, DAYS[n - 1].date())
    assert r["today"] == [] and r["wait"] == []
    assert r["track"][0]["state"] == "stop" and r["track"][0]["days"] == 5
    assert r["track"][0]["pct"] == round((101 / 105 - 1) * 100, 1)


def test_today_breakout_card_and_live_stock_left_out_of_wait(monkeypatch):
    n = 60
    C, O, H, L = _series(n, [104.0] * n)
    H.iloc[59, 0] = 106
    kq = frame({"A": [i in (57, 59) for i in range(n)]})   # 오늘도 조건을 채웠지만 이미 돌파 — 기다림에 넣지 않는다
    _fake(monkeypatch, O, H, L, C, kq, frame({"A": [105.0] * n}), frame({"A": [2.0] * n}), frame({"A": [50.0] * n}))
    r = bw.compute(O, H, L, C, DAYS[n - 1].date())
    assert [x["t"] for x in r["today"]] == ["A"] and r["wait"] == []
    assert r["today"][0]["entry"] == 105.0 and r["today"][0]["stop"] == 101.0


def test_breakout_stopped_same_day_is_not_today(monkeypatch):
    n = 60
    C, O, H, L = _series(n, [104.0] * n)
    H.iloc[59, 0] = 106
    L.iloc[59, 0] = 100                 # 그날 저가가 손절선(101) 아래 — 그날 손절(불리한 가정)
    kq = frame({"A": [i == 58 for i in range(n)]})
    _fake(monkeypatch, O, H, L, C, kq, frame({"A": [105.0] * n}), frame({"A": [2.0] * n}), frame({"A": [50.0] * n}))
    r = bw.compute(O, H, L, C, DAYS[n - 1].date())
    assert r["today"] == [] and r["track"][0]["state"] == "stop" and r["track"][0]["days"] == 0


def test_missing_session_bar_returns_none(monkeypatch):
    n = 60
    C, O, H, L = _series(n, [104.0] * n)
    monkeypatch.setattr(bw, "MIN_VALID", 1)
    assert bw.compute(O, H, L, C, date(2027, 1, 4)) is None


def _write(tmp_path, monkeypatch, data, bt=True):
    p = tmp_path / "data"
    p.mkdir()
    (p / "breakout_watch.json").write_text(json.dumps(data, ensure_ascii=False))
    monkeypatch.setattr(gh, "DATA_DIR", p)
    if not bt:
        monkeypatch.setattr(gh, "BREAKOUT_BACKTEST_PATH", tmp_path / "none.json")


def test_build_skips_on_date_mismatch(tmp_path, monkeypatch):
    d = json.loads(FIX.read_text()) | {"date": "2026-11-06"}
    _write(tmp_path, monkeypatch, d)
    assert gh.build_breakout_watch({}, "2026-11-07") == {}
    a = {}
    assert gh.build_breakout_watch(a, "2026-11-06")["bw"]["asof_label"] == "11/5(목) 종가 기준"
    assert a["breakout_watch"]["asof"] == "2026-11-05"          # 스냅샷에 남는다


def test_build_skips_without_backtest_file(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, json.loads(FIX.read_text()), bt=False)
    assert gh.build_breakout_watch({}, "") == {}


def test_build_skips_when_all_empty():
    assert gh.build_breakout_watch({"breakout_watch": {"asof": "2026-11-13", "today": [], "wait": [], "track": []}}) == {}


def test_render_1105_replay():
    a = {"breakout_watch": json.loads(FIX.read_text())}
    ctx = gh.build_breakout_watch(a)
    b = ctx["bw"]
    assert (b["n_wait"], len(b["today"]), len(b["track"]), b["win"], b["lose"], b["n_live"]) == (2, 1, 10, 2, 3, 5)
    html = gh.make_env().get_template("sections/breakout_watch.html").render(**ctx)
    assert "에스티 로더" in html and "$113.53" in html and "손절선까지 <b>1.8%</b>" in html
    assert "아무 날에나 산 경우(+0.16R)" in html and "추천" not in html


def test_us_template_includes_section_after_sp500():
    src = (Path(gh.TEMPLATES_DIR) / "briefings" / "us.html").read_text()
    assert src.index("sp500_ma200.html") < src.index("breakout_watch.html") < src.index('class="divider"')


def test_order_by_cap_sorts_all_lists_and_trims():
    r = {"today": [{"t": "S"}, {"t": "B"}],
         "wait": [{"t": f"W{i}"} for i in range(8)],
         "track": [{"t": "X"}, {"t": "Y"}, {"t": "Z"}]}
    caps = {"B": 3e12, "S": 1e10, "W7": 9e11, "W3": 5e11, "Y": 2e11, "Z": 1e11}
    bw.order_by_cap(r, caps)
    assert [x["t"] for x in r["today"]] == ["B", "S"]
    assert [x["t"] for x in r["wait"]][:2] == ["W7", "W3"] and len(r["wait"]) == 6 and r["wait_more"] == 2
    assert [x["t"] for x in r["track"]] == ["Y", "Z", "X"]          # 시총을 못 읽은 X는 뒤로
    assert r["track"][2]["cap"] is None and r["today"][0]["cap"] == 3e12


def test_cap_label():
    assert gh._cap_label(3.92e12) == "$3.9조" and gh._cap_label(8.5e10) == "$850억" and gh._cap_label(None) == ""
