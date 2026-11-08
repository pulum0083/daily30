# S&P 500 200일선 체크 — 계산·섹션 컨텍스트·텔레그램 줄 테스트(네트워크 없음)
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc  # noqa: E402
import generate_html as gh  # noqa: E402
import sp500_ma200 as sp  # noqa: E402

SESSION = date(2026, 11, 6)


def _closes(n_tickers=460, days=230, end="2026-11-06"):
    """평평한 100 → 마지막 이틀만 바꿔 넘는 종목을 만든다."""
    idx = pd.bdate_range(end=end, periods=days)
    df = pd.DataFrame(100.0, index=idx, columns=[f"T{i}" for i in range(n_tickers)])
    df.iloc[-2, :200] = 100.5                          # 전날도 같은 편에 둔다
    df.iloc[-2, 200:] = 99.5
    df.iloc[-1, :200] = 101.0                          # 200개는 200일선 위
    df.iloc[-1, 200:] = 99.0
    df.iloc[-2, 200:205] = 101.0                       # T200~T204: 전날 위 → 오늘 아래(아래로)
    df.iloc[-2, :3] = 99.0                             # T0~T2: 전날 아래 → 오늘 위(위로)
    df.iloc[-1, 5] = 150.0                             # T5: 과열
    return df


NAMES = {f"T{i}": (f"Co {i}", "Financials" if i % 2 else "Utilities") for i in range(460)}


def test_compute_crossings_hot_and_breadth():
    r = sp.compute(_closes(), NAMES, SESSION)
    assert r["asof"] == "2026-11-06" and r["n"] == 460 and r["above"] == 200
    assert r["above_pct"] == round(200 / 460 * 100, 1)
    assert [x["t"] for x in r["below"]] == ["T200", "T201", "T202", "T203", "T204"]
    assert [x["t"] for x in r["up"]] == ["T0", "T1", "T2"]
    assert [x["t"] for x in r["hot"]] == ["T5"] and r["hot"][0]["sec"] == "금융"
    assert r["breadth"][-1] == ["2026-11-06", r["above_pct"]]


def test_compute_refuses_wrong_session_and_too_few():
    assert sp.compute(_closes(end="2026-11-05"), NAMES, SESSION) is None      # 직전 정규장 봉이 없다
    later = _closes(end="2026-11-09")                                          # 다음 봉은 버리고 11/6로 계산
    assert sp.compute(later, NAMES, SESSION)["asof"] == "2026-11-06"
    assert sp.compute(_closes(n_tickers=300), NAMES, SESSION) is None          # 450개 밑이면 실패


DATA = {"date": "2026-11-09", "asof": "2026-11-06", "prev": "2026-11-05", "n": 500, "above": 294,
        "above_pct": 58.8, "above_pct_prev": 61.4, "breadth": [["2026-08-14", 66.0], ["2026-11-06", 58.8]],
        "below": [{"t": t, "n": t, "sec": "금융", "chg": -1.0, "gap": -0.5, "cap": 1} for t in
                  ["IBM", "AXP", "VZ", "INTU", "PNC", "KKR", "ORLY", "AZO", "HIG", "CPRT"]],
        "up": [{"t": "AMD", "n": "AMD", "sec": "기술", "chg": 11.04, "gap": 7.9, "cap": 1}],
        "hot": [{"t": "MRNA", "n": "Moderna", "sec": "헬스케어", "chg": 5.27, "gap": 177.9},
                {"t": "CRL", "n": "CRL", "sec": "헬스케어", "chg": 7.8, "gap": 50.3}]}


def _with_file(tmp_path, monkeypatch, data):
    (tmp_path / "sp500_ma200.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(gh, "DATA_DIR", tmp_path)


def test_section_context_and_render(tmp_path, monkeypatch):
    _with_file(tmp_path, monkeypatch, DATA)
    a = {}
    ctx = gh.build_sp500_ma200(a, "2026-11-09")["spx"]
    assert a["sp500_ma200"]["asof"] == "2026-11-06"                           # 스냅샷에 남는다
    assert ctx["asof_label"] == "11/6(금) 종가 기준" and ctx["dp"] == -2.6
    assert ctx["hot"][0]["x"] == "2.8" and ctx["below_secs"] == "금융 10"
    html = gh.make_env().get_template("sections/sp500_ma200.html").render(spx=ctx)
    assert "200일선 아래로" in html and "200일선 위로" in html and "새로" not in html
    assert "🔥 과열" in html and "200일선보다 40% 넘게 높아요" in html
    assert "+2개 더 보기" in html and html.count('class="spx-chip"') == 11
    assert "평균의 2.8배" in html


def test_section_skipped_on_date_mismatch_and_empty_groups(tmp_path, monkeypatch):
    _with_file(tmp_path, monkeypatch, DATA)
    assert gh.build_sp500_ma200({}, "2026-11-10") == {}
    ctx = gh.build_sp500_ma200({"sp500_ma200": dict(DATA, hot=[], up=[])}, "2026-11-10")["spx"]   # 스냅샷 우선
    html = gh.make_env().get_template("sections/sp500_ma200.html").render(spx=ctx)
    assert "과열" not in html and "200일선 위로" not in html and "200일선 아래로" in html


def test_telegram_lines(tmp_path, monkeypatch):
    _with_file(tmp_path, monkeypatch, DATA)
    assert cc._sp500_lines({}, "2026-11-09") == [
        "", "📏 S&P 500 200일선 위 58.8% (전날 61.4%)", "이탈 IBM·AXP·VZ 외 7개", "과열 MRNA·CRL"]
    assert cc._sp500_lines({}, "2026-11-10") == []
