# 코스피 아침 '간밤 미국장' 카드 — 2026-11-18(ET) 정규장 실측 리플레이(네트워크 없음)
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh  # noqa: E402
import us_session_map as usm  # noqa: E402

PCT = {"^GSPC": -0.23, "^IXIC": 0.42, "^DJI": -1.11, "^SOX": 0.10,
       "NVDA": -2.89, "AMD": 5.31, "AVGO": 3.64, "MU": -1.00, "TSM": 0.81, "ORCL": -0.97,
       "AAPL": 0.15, "MSFT": 0.40, "AMZN": 3.82, "META": -0.40, "GOOGL": 0.80, "TSLA": 0.95,
       "XLK": 0.34, "XLC": 0.30, "XLY": 1.79, "XLP": -0.31, "XLE": -3.27, "XLF": -1.14, "XLV": -2.20,
       "XLI": -0.05, "XLB": -0.75, "XLRE": 0.07, "XLU": 0.30, "CIBR": 4.72, "IGV": 1.25}


def _changes(tickers, day="2026-11-18", stale=()):
    return {t: {"change_pct": PCT[t], "session_date": "2026-11-17" if t in stale else day} for t in tickers if t in PCT}


def test_incident_card():
    m = usm.collect("2026-11-18", _changes)
    c = usm.card(m)
    assert c["title"] == "지수는 혼조, 안에서는 크게 갈렸어요"
    assert c["check_line"] == ("AI 칩은 엔비디아·마이크론이 내리고 AMD·브로드컴이 올랐어요. "
                               "섹터는 보안이 가장 많이 오르고 에너지가 가장 많이 내렸어요.")
    g = {x["label"]: [(r["name"], r["pct"]) for r in x["marks"]] for x in c["groups"]}
    assert g["AI 칩"][0] == ("AMD", 5.31) and g["AI 칩"][-1] == ("엔비디아", -2.89)
    assert g["오른 섹터"] == [("보안", 4.72), ("경기소비재", 1.79), ("소프트웨어", 1.25)]
    assert g["내린 섹터"] == [("에너지", -3.27), ("헬스케어", -2.2), ("금융", -1.14)]


def test_other_day_bars_are_dropped():
    m = usm.collect("2026-11-18", lambda t: _changes(t, stale=("NVDA", "XLE")))
    assert "NVDA" not in [r["ticker"] for r in m["ai"]] and "XLE" not in [r["ticker"] for r in m["sectors"]]
    assert usm.collect("2026-11-18", lambda t: _changes(t, stale=("^GSPC", "^IXIC", "^DJI"))) is None   # 지수 1개뿐
    assert usm.collect("2026-11-18", lambda t: (_ for _ in ()).throw(RuntimeError("x"))) is None


def test_titles_and_josa():
    up = {"indices": [{"name": "S&P500", "pct": 1.0}, {"name": "나스닥", "pct": 1.2}], "ai": [], "bigtech": [], "sectors": []}
    assert usm.title_of(up) == "지수가 나란히 올랐어요"
    calm = {**up, "indices": [{"name": "S&P500", "pct": 0.2}, {"name": "나스닥", "pct": -0.1}],
            "ai": [{"name": "AMD", "pct": 0.5}]}
    assert usm.title_of(calm) == "지수는 혼조로 끝났어요"
    assert usm._ga("AMD") == "AMD가" and usm._ga("보안") == "보안이" and usm._ga("TSMC") == "TSMC가"
    only_up = {**up, "ai": [{"name": "AMD", "pct": 3.0}], "sectors": [{"name": "기술", "pct": 1.0}, {"name": "금융", "pct": 0.5}]}
    assert usm.line_of(only_up) == "AI 칩은 AMD가 크게 올랐어요. 섹터는 모두 올랐고 기술이 가장 많이 올랐어요."


def test_directive_gives_table_only_numbers():
    d = usm.directive(usm.collect("2026-11-18", _changes))
    assert "엔비디아 -2.89%" in d and "숫자는 위 표에 있는 것만" in d
    assert usm.directive(None) == ""


def test_build_snapshot_first_and_date_gate():
    m = usm.collect("2026-11-18", _changes)
    a = {"us_session_map": m}
    assert gh.build_us_session_map(a, {}, "2026-11-19")["us_map"]["session"] == "2026-11-18"
    md = {"generated_at": "2026-11-18T07:25:00+09:00", "us_session_map": m}
    assert gh.build_us_session_map({}, md, "2026-11-19") == {}          # 다른 날 시장 데이터는 쓰지 않는다
    a2 = {}
    md["generated_at"] = "2026-11-19T07:25:00+09:00"
    assert gh.build_us_session_map(a2, md, "2026-11-19")["us_map"] and a2["us_session_map"] == m   # 스냅샷에 남긴다


def test_template_uses_existing_card_format():
    c = usm.card(usm.collect("2026-11-18", _changes))
    html = gh.make_env().get_template("sections/issue_check.html").render(us_map=c, us_issue_label="간밤")
    assert '<div class="ic-card ic-card--us">' in html and "지수는 혼조, 안에서는 크게 갈렸어요" in html
    assert "간밤 미국 · 실측" in html and "ET 2026-11-18 정규장 종가" in html
    assert '<span class="ic-tk dn">엔비디아 <b>−2.89%</b></span>' in html
    json.dumps(c, ensure_ascii=False)                                   # 스냅샷에 저장할 수 있어야 한다
