# 예측 성적표(/accuracy/)·방법론(/methodology/) 페이지 생성 테스트 (2026-11-05, §80)
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import generate_html as g  # noqa: E402
import leading_signal as ls  # noqa: E402
import record_pages as rp  # noqa: E402
from fit_open_gap_prior import legacy_split  # noqa: E402
from verify_publish_gate import check_html, expected_pages, SITE_BASE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def row(date, typ, pred, up, ok, actual, **kw):
    return {"date": date, "type": typ, "predicted_direction": pred, "up_pct": up, "down_pct": 100 - up,
            "is_correct": ok, "actual_direction": actual, **kw}


SAMPLE = [
    row("2026-10-13", "kospi", "하락 우위", 28, True, "하락", basis="open", actual_open_pct=-3.1),
    row("2026-10-14", "kospi", "상승 우위", 63, True, "상승", basis="open", actual_open_pct=0.44),
    row("2026-10-20", "kospi", "상승 우위", 83, False, "하락", basis="open", actual_open_pct=-0.6),
    row("2026-10-21", "kospi", "상승 우위", 73, None, None, basis="open"),           # 미채점 — 세지 않는다
    row("2026-09-30", "kospi", "상승 우위", 70, True, "상승"),                          # 종가 기준(예전)
    row("2026-10-01", "kospi", "중립", 50, False, "하락"),
    row("2026-10-30", "us", "상승 우위", 62, True, "상승"),
    row("2026-11-02", "us", "하락 우위", 40, False, "상승", backfilled=True),
]


def test_accuracy_stats_and_baseline():
    a = rp.build_accuracy(SAMPLE)
    k = a["kospi"]["stat"]
    assert (k["n"], k["hit"], k["pct"]) == (3, 2, 66.7)        # 미채점 10/21은 빠진다
    assert (k["base_n"], k["base"]) == (1, 33.3)               # 매일 '상승'이라고 찍었다면
    assert [d["date"] for d in a["kospi"]["days"]] == ["10/20", "10/14", "10/13"]   # 최신이 위
    assert a["kospi"]["days"][0] == {"date": "10/20", "wd": "화", "side": "up", "pct": 83, "ok": False, "gap": -0.6}
    assert a["legacy"]["stat"]["n"] == 2                        # 종가 기준 기록은 따로
    u = a["us"]
    assert (u["stat"]["n"], u["stat"]["hit"]) == (2, 1)
    assert u["backfilled"] == {"n": 1, "from": "11/2", "to": "11/2"}
    assert [m["label"] for m in u["monthly"]] == ["10월", "11월"]
    assert a["asof"] == "11월 2일"


def test_accuracy_calibration_uses_bigger_side():
    a = rp.build_accuracy(SAMPLE)
    labels = {c["label"]: (c["n"], c["hit"]) for c in a["kospi"]["calib"]}
    assert labels == {"60~69%": (1, 1), "70~79%": (1, 1), "80% 이상": (1, 0)}   # 하락 28% → 큰 쪽 72%


def test_accuracy_empty_means_no_page():
    assert rp.build_accuracy([]) == {}
    assert rp.build_accuracy([row("2026-10-21", "kospi", "상승 우위", 73, None, None, basis="open")]) == {}


def test_methodology_reads_files_not_literals():
    m = rp.build_methodology()
    assert [w["w"] for w in m["weights"]] == list(ls.SIGNAL_WEIGHTS.values())
    assert (m["prob_a"], m["prob_b"], m["side_up"], m["side_dn"]) == (ls.PROB_A, ls.PROB_B, ls.SIDE_UP, ls.SIDE_DN)
    bands = json.loads((ROOT / "scripts/config/us_close_prior.json").read_text())["bands"]
    assert [b["up"] for b in m["us"]["bands"]] == [b["up_pct"] for b in bands]
    assert m["us"]["bands"][0]["label"].endswith("미만") and m["us"]["bands"][-1]["label"].endswith("이상")
    assert m["kospi"]["days"] > 0 and m["kospi"]["legacy_split"]["days"] > 0


def test_methodology_missing_file_drops_section(monkeypatch, tmp_path):
    monkeypatch.setattr(rp, "CONFIG_DIR", tmp_path)
    m = rp.build_methodology()
    assert m["kospi"] is None and m["us"] is None and m["ma5"] is None and m["nq"] is None
    html = g.make_env().get_template("pages/methodology.html").render(**m, canonical_url=f"{SITE_BASE}/methodology/")
    assert 'id="m-us"' not in html and 'id="m-kospi"' in html     # 파일이 없으면 그 칸만 빠진다


def _render(slug, ctx):
    url = f"{SITE_BASE}/{slug}/"
    ctx = dict(ctx, canonical_url=url, seo_jsonld=[g._jsonld(g._breadcrumb([("홈", "/stocks/"), (slug, f"/{slug}/")]))])
    return g.make_env().get_template(f"pages/{slug}.html").render(**ctx), url


def test_pages_pass_publish_gate_with_real_data():
    briefings = json.loads((ROOT / "data/briefings.json").read_text())["briefings"]
    for slug, ctx in (("accuracy", rp.build_accuracy(briefings)), ("methodology", rp.build_methodology())):
        html, url = _render(slug, ctx)
        assert check_html(html, url) == [], slug
        assert "None" not in html and "{{" not in html, slug


def test_pages_are_in_sitemap_and_gate_list():
    urls = {u for _, u in expected_pages()}
    assert {f"{SITE_BASE}/accuracy/", f"{SITE_BASE}/methodology/"} <= urls
    sm = (ROOT / "web/sitemap.xml").read_text()
    assert "<loc>https://doubleshot.space/accuracy/</loc>" in sm and "<loc>https://doubleshot.space/methodology/</loc>" in sm


def test_legacy_split_scores_open_close_intraday():
    k = pd.DataFrame({"kdate": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05"]),
                      "openPrice": [100, 102, 99], "closePrice": [101, 100, 103]})
    rows = [row("2026-10-02", "kospi", "상승 우위", 70, False, "하락"),     # 시가 102 ≥ 101 맞음, 종가 100 < 101 틀림, 장중 하락 틀림
            row("2026-10-05", "kospi", "하락 우위", 30, False, "상승"),     # 시가 99 < 100 맞음, 종가 103 틀림, 장중 상승 틀림
            row("2026-10-06", "kospi", "중립", 50, True, "상승"),            # 방향 없는 날은 세지 않는다
            row("2026-10-02", "kospi", "상승 우위", 70, True, "상승", basis="open")]   # 시초가 기준은 대상 밖
    s = legacy_split(rows, k)
    assert s == {"days": 2, "from": "2026-10-02", "to": "2026-10-05",
                 "open_hit_pct": 100.0, "close_hit_pct": 0.0, "intraday_hit_pct": 0.0}


def test_links_point_to_record_pages():
    for f in ("scripts/templates/base.html", "web/stocks/index.html", "web/about/index.html",
              "web/glossary/index.html", "web/legal/disclaimer/index.html"):
        t = (ROOT / f).read_text()
        assert 'href="/accuracy/"' in t and 'href="/methodology/"' in t, f
    assert 'href="/accuracy/"' in (ROOT / "scripts/templates/sections/_scorecard.html").read_text()
