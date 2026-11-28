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
from gen_testkit import gen_patch  # noqa: E402

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


def test_condition_void_if_close_drops_below_ma10_before_breakout():
    """백테스트와 같다 — 넘기 전에 종가가 10일선 아래로 내려가면 그 조건은 무효(2026-11-26)."""
    n = 30
    h = np.full(n, 100.0); h[19] = 106.0
    kq = frame({"A": [i == 15 for i in range(n)]})
    pv = frame({"A": [105.0] * n})
    c = np.full(n, 100.0); s10 = np.full(n, 99.0)
    assert bw.find_breakouts(kq, frame({"A": h}), pv, 0, n - 1, frame({"A": c}), frame({"A": s10})) == [("A", 19, 15)]
    c[17] = 98.0                        # 17일 종가가 10일선(99) 아래 — 무효
    assert bw.find_breakouts(kq, frame({"A": h}), pv, 0, n - 1, frame({"A": c}), frame({"A": s10})) == []


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
    gen_patch(monkeypatch, "DATA_DIR", p)
    if not bt:
        gen_patch(monkeypatch, "BREAKOUT_BACKTEST_PATH", tmp_path / "none.json")


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
    assert (b["n_wait"], len(b["today"]), len(b["track"]), b["n_done"], b["n_live"]) == (2, 1, 10, 5, 5)
    html = gh.make_env().get_template("sections/breakout_watch.html").render(**ctx)
    assert "에스티 로더" in html and "기준선보다 5.2% 아래" in html
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


def test_render_closed_below_entry_1124():
    """2026-11-24 — 장중에 기준선을 넘었다가 그 아래로 끝난 종목을 '넘었어요'로 쓰지 않고, 요약도 그 수를 센다(2026-11-26)."""
    snap = json.loads((Path(__file__).resolve().parents[1] / "web/briefings/2026-11-25/us/analysis_snapshot.json").read_text())
    ctx = gh.build_breakout_watch({"breakout_watch": snap["breakout_watch"]})
    b = ctx["bw"]
    assert (len(b["today"]), b["n_held"], b["n_live"], b["n_done"]) == (6, 2, 2, 3)
    assert b["summary"] == ("오늘 6종목이 장중에 최근 고점을 넘었고, 그중 리제네론·펜테어만 종가까지 그 위를 지켰어요. "
                            "앞서 돌파한 종목 중 2개는 아직 이어지고(평균 +5.7%), 3개는 끝났어요(평균 −6.4%).")
    html = gh.make_env().get_template("sections/breakout_watch.html").render(**ctx)
    assert "REGN · 기준선 $980.55 위" in html and "손절까지<br>6.5%" in html     # REGN 종가 987.09
    assert "장중만 · 기준선보다 3.6% 아래" in html                              # GEN 29.95
    assert "장중만 · 기준선 바로 아래" in html                                   # TSCO 39.45
    assert html.count('<tr class="weak">') == 4 + 3                              # 장중만 4 + 끝난 결과 3


def test_summary_sentences():
    from sections_us import _bw_summary
    t = lambda c, e, n="가 나": {"name": n, "close": c, "entry": e}
    assert _bw_summary([], []) == "오늘 최근 고점을 넘은 종목은 없어요."
    assert _bw_summary([t(2, 1)], []).endswith("모두 종가까지 그 위를 지켰어요.")
    assert "지킨 종목은 없었어요" in _bw_summary([t(1, 2)], [])
    assert _bw_summary([], [{"state": "live", "pct": 3.0}]).endswith("1개가 아직 이어지고 있어요(+3.0%).")
    # 진행 중이 여럿이면 앞 몇 개만 나열하지 않고 평균 하나로(2026-11-28 — 5개 중 3개만 보였다)
    live = [{"state": "live", "pct": v} for v in (0.1, 0.8, 2.3, 5.9, 3.2)]
    assert _bw_summary([], live).endswith("5개가 아직 이어지고 있어요(평균 +2.5%).")


def test_no_new_breakout_while_previous_is_live(monkeypatch):
    """앞 돌파가 진행 중이면 같은 종목의 새 돌파를 세지 않는다 — 2026-11-24 젠 디지털이 두 칸에 함께 나왔다(2026-11-26)."""
    n = 60
    C = frame({"A": [106.0] * n}); O, H, L = C.copy() - 2, C.copy(), C.copy() - 1   # 저가 105 > 손절선 103 — 앞 돌파가 이어진다
    H.iloc[40, 0] = 106; H.iloc[59, 0] = 112
    kq = frame({"A": [i in (38, 57) for i in range(n)]})
    pv = frame({"A": [105.0 if i < 50 else 110.0 for i in range(n)]})
    _fake(monkeypatch, O, H, L, C, kq, pv, frame({"A": [1.0] * n}), frame({"A": [50.0] * n}))
    r = bw.compute(O, H, L, C, DAYS[n - 1].date())
    assert r["today"] == [] and [x["from"] for x in r["track"]] == [DAYS[39].date().isoformat()]


def test_gap_up_day_judged_by_pivot_not_entry():
    """시가가 기준선 위에서 열린 날 — 종가가 산 가격(시가)보다 낮아도 기준선 위면 '장중에만 넘음'이 아니다(2026-11-26)."""
    d = {"asof": "2026-11-24", "today": [{"t": "A", "name": "에이", "close": 103.0, "chg": 1.0, "pivot": 100.0,
                                         "entry": 105.0, "stop": 95.0}], "wait": [], "track": []}
    b = gh.build_breakout_watch({"breakout_watch": d})["bw"]
    assert b["today"][0]["below"] is None and b["n_held"] == 1


def test_today_percent_is_vs_breakout_price():
    """오늘 돌파의 %도 그 뒤 결과처럼 돌파한 가격 대비다 — 11/25 차터는 하루 +8.4%지만 돌파 가격 대비 +3.3%(2026-11-28)."""
    d = {"asof": "2026-11-25", "today": [{"t": "CHTR", "name": "차터", "close": 147.27, "chg": 8.39, "pivot": 142.6,
                                         "entry": 142.6, "stop": 129.44}], "wait": [], "track": []}
    ctx = gh.build_breakout_watch({"breakout_watch": d})
    assert ctx["bw"]["today"][0]["gain"] == 3.3
    html = gh.make_env().get_template("sections/breakout_watch.html").render(**ctx)
    assert "+3.3%" in html and "+8.4%" not in html and "돌파한 가격 대비 · 종가도 넘음 1" in html


def test_wait_includes_earlier_condition_not_yet_broken(monkeypatch):
    """조건이 며칠 전에만 맞았어도 아직 돌파·무효가 아니면 '기다리는 중'에 넣는다 — 그 조건으로 내일 돌파할 수 있다(2026-11-28)."""
    n = 60
    C, O, H, L = _series(n, [104.0] * n)
    kq = frame({"A": [i == 57 for i in range(n)]})                 # 사흘 전에만 조건
    pv = frame({"A": [105.0 if i == 57 else 108.0 for i in range(n)]})
    _fake(monkeypatch, O, H, L, C, kq, pv, frame({"A": [2.0] * n}), frame({"A": [50.0] * n}))
    r = bw.compute(O, H, L, C, DAYS[n - 1].date())
    assert [x["t"] for x in r["wait"]] == ["A"]
    w = r["wait"][0]
    assert w["pivot"] == 105.0 and w["stop"] == 101.0 and w["since"] == DAYS[57].date().isoformat()


def test_wait_drops_earlier_condition_after_close_below_ma10():
    """넘기 전에 종가가 10일선 아래로 내려가면 그 조건은 무효 — 기다리는 중에서도 뺀다."""
    n = 30
    kq = frame({"A": [i == 26 for i in range(n)]})
    H = frame({"A": [100.0] * n}); pv = frame({"A": [105.0] * n})
    c = np.full(n, 100.0); c[28] = 98.0
    args = (kq, H, frame({"A": c}), pv, frame({"A": [99.0] * n}), n - 1, set(), {})
    assert bw.pending(*args) == {}
    c[28] = 100.0
    assert bw.pending(kq, H, frame({"A": c}), pv, frame({"A": [99.0] * n}), n - 1, set(), {}) == {"A": 26}


def test_wait_lists_every_later_breakout_on_the_eve(monkeypatch):
    """돌파한 종목은 모두 그 전날 '기다리는 중' 후보였다 — pending과 find_breakouts가 같은 조건일을 본다."""
    rng = np.random.default_rng(1)
    n, cols = 80, [f"T{j}" for j in range(30)]
    kq = pd.DataFrame(rng.random((n, len(cols))) < 0.08, index=DAYS[:n], columns=cols)
    H = pd.DataFrame(100 + rng.random((n, len(cols))) * 8, index=DAYS[:n], columns=cols)
    pv = H.rolling(10, min_periods=1).max()
    C = H - 1; s10 = C.rolling(10, min_periods=1).mean() - 0.5
    for t, i, k in bw.find_breakouts(kq, H, pv, 10, n - 1, C, s10):
        assert t in bw.pending(kq, H, C, pv, s10, i - 1, set(), {}), (t, i, k)
