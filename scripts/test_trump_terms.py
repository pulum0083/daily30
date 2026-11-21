# 트럼프 1기 vs 2기 S&P500 비교(trump_terms.py·longterm_pages.trump_context) 테스트 — 네트워크 없이 합성 일봉으로
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import longterm_pages as lp  # noqa: E402
import trump_terms as tt  # noqa: E402


def _series(start=date(1952, 12, 1), end=date(2026, 11, 20), step=1.0003):
    out, d, v = [], start, 100.0
    while d <= end:
        if d.weekday() < 5 and d.isoformat() != "2025-01-20":
            v *= step
            out.append((d.isoformat(), round(v, 4)))
        d += timedelta(days=1)
    return out


def _all(session="2026-11-20"):
    s = _series()
    return {sym: [r for r in s if r[0] <= session] for sym, _n, _g in tt.ASSETS}


def test_build_skips_when_session_bar_missing():
    assert tt.build(_all("2026-11-19"), "2026-11-20") is None


def test_build_assets_presidents_forward():
    d = tt.build(_all(), "2026-11-20")
    assert d["asof"] == "2026-11-20" and d["same"]["date"][:4] == "2018"
    assert [a["group"] for a in d["assets"]].count("us") == 5 and [a["group"] for a in d["assets"]].count("kr") == 5
    sp = d["assets"][0]
    assert sp["k"] == "S&P 500" and sp["t2"] > 0 and sp["end1"] > sp["t1"]
    names = [p["name"] for p in d["pres"]]
    assert names[0] == "아이젠하워" and names[-1] == "트럼프 2기"
    assert d["pres"][-1]["end"] is None and d["pres"][-2]["end"] is not None      # 2기는 진행 중
    assert set(d["fwd"]) == {"low3m", "m6", "m12", "end"} and d["fwd"]["end"]["date"] == "2021-01-19"


def test_asset_dropped_when_stale():
    s = _all()
    s["GC=F"] = [r for r in s["GC=F"] if r[0] <= "2026-10-01"]            # 수집이 멈춘 자산은 뺀다
    d = tt.build(s, "2026-11-20")
    assert "금" not in [a["k"] for a in d["assets"]]


def test_year_ends_completed_years_only():
    t = [[d, d / 10, ""] for d in range(0, 1462)]
    assert lp.year_ends(t) == [36.5, 73.0, 109.6, 146.1]
    assert lp.year_ends(t[:670]) == [36.5]                                    # 1년만 끝났다
    assert lp.year_ends(t[:300]) == []


def test_context_sentences_and_tables():
    c = lp.trump_context(tt.build(_all(), "2026-11-20"))["tr"]
    assert c["days"] == 669 and "취임 뒤 669일" in c["say"]
    assert len(c["us"]) == 5 and len(c["kr"]) == 5 and all("a_w" in r for r in c["us"])
    assert "S&amp;P 500은 1기 같은 날과" in c["us_say"]
    assert c["kr_say"].startswith("두 임기가 가장 크게 갈린 건")
    assert c["uw"]["a1"] and c["uw"]["b"] and "고점" in c["uw_say"]
    assert c["y1"] and c["y2"] == c["y2"][:2]
    assert c["pres_n"] == 18 and 0 <= c["pres_higher"] <= 18
    assert [r["key"] for r in c["ranges"]][-3:] == ["y3", "y4", "all"]


def test_kr_say_particle():
    rows = [{"k": "금", "t1": 1, "t2": 30}, {"k": "달러 지수", "t1": -4, "t2": -5}]
    assert lp._kr_say(rows) == "두 임기가 가장 크게 갈린 건 금이에요 — 1기 같은 날 +1.0%, 2기 지금 <b>+30.0%</b>. 달러는 두 임기 모두 약해졌어요."


def test_write_page_needs_matching_session(tmp_path, monkeypatch):
    import standalone_pages as sp
    d = tt.build(_all(), "2026-11-20")
    (tmp_path / "trump_terms.json").write_text(json.dumps(d), encoding="utf-8")
    monkeypatch.setattr(sp, "DATA_DIR", tmp_path)
    assert sp.write_trump_page("2026-11-25") is False                         # 직전 미국장(11/24)과 기준일이 다르면 쓰지 않는다
