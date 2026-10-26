# 미국 브리핑 '나스닥 체크' 섹션·텔레그램 경고 블록 테스트 — 네트워크 없이 10/23 월봉 픽스처로 돈다(§65)
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest_nasdaq_overheat as bt  # noqa: E402
import call_claude as cc  # noqa: E402
import generate_html as gh  # noqa: E402
import nasdaq_overheat as nq  # noqa: E402

FIX = json.loads((Path(__file__).parent / "fixtures" / "nasdaq_monthly_20261023.json").read_text(encoding="utf-8"))
MONTHS = FIX["months"]


def _data(gap=59.79, date="2026-10-23", streak=0):
    d = {"date": date, **nq.compute(MONTHS)}
    d["gap_pct"], d["streak"] = gap, streak
    return d


# ── 지표 ──
def test_compute_matches_prototype_numbers():
    r = nq.compute(MONTHS)
    assert round(r["gap_pct"], 1) == 59.8 and round(r["high"], 1) == 27722.8 and round(r["ma60"], 1) == 17349.5
    assert r["level"] == "ok" and r["streak"] == 0 and r["month"] == "2026-10"
    assert r["series"][0]["m"] == "2014-01" and r["peak"]["m"] == "2021-02" and round(r["peak"]["g"]) == 84


@pytest.mark.parametrize("gap,level", [(64.9, "ok"), (65.0, "caution"), (69.9, "caution"), (70.0, "warn")])
def test_level_boundaries(gap, level):
    assert nq.level_of(gap) == level


def test_monthly_uses_daily_high_not_month_bar():
    daily = [("2026-10-01", 100.0, 90.0, 95.0), ("2026-10-15", 130.0, 94.0, 120.0), ("2026-10-23", 110.0, 99.0, 101.0)]
    assert nq.monthly(daily) == [{"m": "2026-10", "high": 130.0, "low": 90.0, "close": 101.0, "last_date": "2026-10-23"}]


def test_compute_none_when_under_60_months():
    assert nq.compute(MONTHS[:59]) is None


# ── 백테스트 ──
def test_backtest_reproduces_prototype_stats():
    r = bt.backtest(MONTHS)
    assert r["months_over_caution"] == 55                                 # 주의 기준 65%(2026-10-26 60→65)
    assert r["caution_band"] == {"months": 8, "fwd12_n": 7, "fwd12_avg_pct": 28.3}
    assert r["warn"]["dd20_pct"] == 51.1 and r["all_dd20_pct"] == 18.8
    assert r["warn"]["periods"] == ["1997~2000", "2020~2021"]


def test_committed_backtest_file_matches_script():
    cfg = json.loads(gh.NASDAQ_BACKTEST_PATH.read_text(encoding="utf-8"))
    r = bt.backtest(MONTHS)
    for k in ("months_over_caution", "caution_band", "all_fwd12_avg_pct", "warn", "all_dd20_pct"):
        assert cfg[k] == r[k], k


# ── 페이지 컨텍스트·렌더 ──
def _ctx(tmp_path, monkeypatch, data, target="2026-10-23", analysis=None):
    monkeypatch.setattr(gh, "DATA_DIR", tmp_path)
    if data is not None:
        (tmp_path / "nasdaq_overheat.json").write_text(json.dumps(data), encoding="utf-8")
    return gh.build_nasdaq_check(analysis if analysis is not None else {}, target)


def test_no_data_omits_section(tmp_path, monkeypatch):
    assert _ctx(tmp_path, monkeypatch, None) == {}


def test_date_mismatch_omits_section(tmp_path, monkeypatch):
    assert _ctx(tmp_path, monkeypatch, _data(date="2026-10-22")) == {}


def test_missing_backtest_file_omits_section(tmp_path, monkeypatch):
    monkeypatch.setattr(gh, "NASDAQ_BACKTEST_PATH", tmp_path / "없음.json")
    assert _ctx(tmp_path, monkeypatch, _data()) == {}


def test_snapshot_first_and_stored(tmp_path, monkeypatch):
    a = {}
    ctx = _ctx(tmp_path, monkeypatch, _data(), analysis=a)
    assert a["nasdaq_overheat"]["date"] == "2026-10-23"                  # 정상이라 섹션은 숨겨도 스냅샷엔 남는다
    assert ctx == {}
    snap = {"nasdaq_overheat": _data(gap=72.4, date="2026-10-23", streak=3)}
    ctx2 = _ctx(tmp_path, monkeypatch, _data(gap=10.0), analysis=snap)   # 파일보다 스냅샷이 먼저
    assert ctx2["nq"]["gap"] == 72.4 and ctx2["nq"]["level"] == "warn"


def _render(ctx):
    return gh.make_env().get_template("sections/nasdaq_check.html").render(**ctx)


@pytest.mark.parametrize("gap,badge,cls", [(65.0, "⚠️ 주의", "is-caution"), (69.9, "⚠️ 주의", "is-caution"),
                                           (70.0, "🚨 경고", "is-warn")])
def test_render_badge_by_boundary(tmp_path, monkeypatch, gap, badge, cls):
    html = _render(_ctx(tmp_path, monkeypatch, _data(gap=gap, streak=2)))
    assert badge in html and cls in html and f"{gap:.1f}%" in html
    assert "65% 위 <b>2개월째</b>" in html


@pytest.mark.parametrize("gap", [59.79, 64.9])
def test_section_hidden_when_normal(tmp_path, monkeypatch, gap):
    # 정상 구간엔 섹션째 숨긴다 — 매일 같은 '정상'이 반복돼 뜻이 없었다(2026-10-26)
    assert _ctx(tmp_path, monkeypatch, _data(gap=gap)) == {}


def test_render_caution_case(tmp_path, monkeypatch):
    html = _render(_ctx(tmp_path, monkeypatch, _data(gap=66.0, streak=1)))
    assert "+66.0" in html and "27,722.8" in html and "17,349.5" in html and "이번 달 고점" in html
    assert "2014년 이후 월별 위치" in html and "최고 2021년 2월 84%" in html
    assert '<span style="left:65%">65</span>' in html and '<span class="nq-ax" style="top:' in html
    assert "nq-preview" not in html and "<text" not in html                # 미리보기 버튼 없음, SVG 안 글자 없음
    assert "<summary>근거와 면책 고지</summary>" in html and "55개월" in html and "+28.3%" in html and "65~70%" in html
    assert "51%</b>(전체 19%)" in html and "1997~2000년과 2020~2021년" in html and "매매 신호" not in html


def test_us_template_puts_section_under_issues():
    t = (gh.TEMPLATES_DIR / "briefings" / "us.html").read_text(encoding="utf-8")
    assert t.index("sections/_issues.html") < t.index("sections/nasdaq_check.html") < t.index("sections/analyst_quotes.html")


# ── 텔레그램 ──
def _tg(tmp_path, monkeypatch, gap):
    monkeypatch.setattr(gh, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {"prediction": {"up_pct": 40, "down_pct": 60}, "todays_view": {"view_title": "제목"},
                "issues": [{"title": "첫 이슈"}], "nasdaq_overheat": _data(gap=gap, streak=4)}
    cc.save_telegram_message("us", "2026-10-23", analysis)
    return (tmp_path / "telegram_message_us.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("gap", [59.9, 65.0, 69.9])
def test_telegram_no_block_under_70(tmp_path, monkeypatch, gap):
    assert "나스닥" not in _tg(tmp_path, monkeypatch, gap)


def test_telegram_block_at_70_after_watch_line(tmp_path, monkeypatch):
    text = _tg(tmp_path, monkeypatch, 72.4)
    assert ("👀 오늘 밤 볼 것\n첫 이슈\n\n🚨 나스닥 과열 경고 — 이번 달 고점이 60개월선보다 72.4% 위예요.\n"
            "※ 과거 70% 넘은 달 뒤 12개월 안에 -20% 넘게 빠진 경우가 51%였어요(전체 19%).") in text
    assert text.index("🚨") < text.index("🔗")


def test_telegram_no_block_without_data_or_backtest(tmp_path, monkeypatch):
    monkeypatch.setattr(gh, "NASDAQ_BACKTEST_PATH", tmp_path / "없음.json")
    assert "나스닥" not in _tg(tmp_path, monkeypatch, 80.0)
