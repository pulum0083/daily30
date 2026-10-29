# 마감 브리핑 — 어제와 비교(D)·섹터별 등락(B)·주도주 3종목(E) 수집·렌더 테스트(2026-10-29, 10/28 실측 리플레이)
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_closing_kospi as fc  # noqa: E402
import generate_html as gh  # noqa: E402

FX = Path(__file__).resolve().parent / "fixtures" / "vs_close_20261028.json"


def _vs():
    return fc.parse_vs_close(json.loads(FX.read_text(encoding="utf-8")), "2026-10-28")


def test_parse_vs_close_10_28():
    v = _vs()
    assert v["kospi"] == {"t": 6.63, "y": 3.09, "diff": 3.54}
    assert v["amp"]["t"] == 5.09 and v["amp"]["y"] == 2.28 and v["vol"]["diff"] == 21.88
    assert v["verdict"] == "어제보다 더 올랐어요" and len(v["sectors"]) == 8


def test_parse_vs_close_rejects_other_day_or_status():
    p = json.loads(FX.read_text(encoding="utf-8"))
    assert fc.parse_vs_close(p, "2026-10-29") == {}
    assert fc.parse_vs_close(dict(p, status="early"), "2026-10-28") == {}


def test_build_close_vs_line_and_sector_bars():
    out = gh.build_close_vs(_vs())
    cells = {c["lbl"]: c for c in out["vs_line"]["cells"]}
    assert cells["코스피"]["val"] == "+6.63%" and cells["코스피"]["sub"] == "어제 +3.09%"
    assert cells["거래량"]["val"] == "+21.9%" and cells["거래량"]["sub"] == "2억 2,320만주"
    assert cells["진폭"]["val"] == "5.09%" and cells["진폭"]["sub"] == "어제 2.28%"
    assert out["vs_line"]["basis"] == "10/27 vs 10/28 · 15:30 확정"
    bars = out["sector_bars"]
    assert [b["name"] for b in bars][:2] == ["반도체", "금융"] and bars[0]["w"] == 50.0
    assert bars[1]["move"] == "▲4" and bars[0]["move"] == "" and bars[-1]["neg"]


def test_frgn_5days_excludes_today():
    rows = [{"date": d, "frgn": f} for d, f in
            [("20261028", 999), ("20261027", 1052520), ("20261026", -984399), ("20261023", -868997),
             ("20261022", -585787), ("20261021", 2055241), ("20261020", 1)]]
    assert fc.frgn_5days(rows, "20261028") == {"sum": 668578, "from": "20261021", "to": "20261027"}
    assert fc.frgn_5days(rows[:3], "20261028") is None


def test_build_close_leaders_formats():
    rows = gh.build_close_leaders([
        {"name": "삼성전자", "close": 242000.0, "change_pct": 9.01, "frgn5": {"sum": 668578, "from": "20261021", "to": "20261027"}},
        {"name": "SK하이닉스", "close": 1487000.0, "change_pct": 10.89, "frgn5": {"sum": -656006, "from": "20261021", "to": "20261027"}},
        {"name": "현대차", "close": None, "change_pct": 1.89},
    ])
    assert len(rows) == 2
    assert rows[0]["close"] == "242,000" and rows[0]["chg"] == "▲ +9.01%" and rows[0]["frgn5"] == "+66.9만주"
    assert rows[1]["frgn5"] == "−65.6만주" and rows[1]["frgn5_cls"] == "dn" and rows[0]["frgn5_range"] == "10/21~10/27"


def test_sections_skip_other_day():
    ctx = gh.build_close_sections({}, {"vs_close": _vs(), "generated_at": "2026-10-28T16:30:00+09:00",
                                      "leaders": [{"name": "a", "close": 1, "change_pct": 1}]}, "KOSPI", "2026-10-29")
    assert "vs_line" not in ctx and "sector_bars" not in ctx and "leaders" not in ctx
