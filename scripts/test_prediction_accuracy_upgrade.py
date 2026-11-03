# 미국 채점 재개·이슈 프리마켓 검증·나스닥 월간 텔레그램·하이퍼리퀴드 기록 테스트(2026-11-03)
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc  # noqa: E402
import check_accuracy as ca  # noqa: E402
import fit_us_close_prior as fit  # noqa: E402
import generate_html as gh  # noqa: E402
import hl_shadow_report as hr  # noqa: E402
import hl_signals as hs  # noqa: E402
import validate_analysis as va  # noqa: E402

KST = timezone(timedelta(hours=9))
# 11/3 21:16 실측(작업 로그 '연장시간대 체결 반영')
LATEST_1103 = {"us_candidates": [{"ticker": t, "change_pct": v} for t, v in
                                 [("MU", 2.57), ("AMD", 2.35), ("AVGO", 1.57), ("LRCX", 3.12),
                                  ("AMAT", 2.90), ("KLAC", 2.87), ("XOM", -0.4), ("CVX", -0.3)]]}


def _issue(**kw):
    return {"title": "필라델피아 반도체 지수 급락 — AI 자금 조달 부담 재부각",
            "body": "AI 투자 자금 우려가 다시 불거지면서 메모리·장비주 전반이 눌리고 있어요.",
            "down": {"label": "반도체·AI 인프라", "tickers": ["MU", "AMD", "AVGO", "LRCX", "AMAT", "KLAC"]}, **kw}


# ── 이슈 프리마켓 검증 ──
def test_real_incident_20261103_body_replaced_with_measured():
    a, corr = {"issues": [_issue()]}, []
    assert va.fix_issue_premarket_contradictions(a, LATEST_1103, corr) == 1
    body = a["issues"][0]["body"]
    assert body == "발행 시점 프리마켓에선 LRCX +3.1%·AMAT +2.9%·KLAC +2.9%로 오르고 있어요."
    assert "눌리고" not in body and corr


def test_past_tense_is_left_alone():
    a = {"issues": [_issue(body="직전 정규장에서 메모리·장비주가 밀렸어요.")]}
    assert va.fix_issue_premarket_contradictions(a, LATEST_1103, []) == 0
    assert "밀렸어요" in a["issues"][0]["body"]


def test_title_in_present_tense_drops_issue():
    a = {"issues": [_issue(title="메모리·장비주가 크게 밀려요"), {"title": "다른 이슈", "body": "그대로."}]}
    assert va.fix_issue_premarket_contradictions(a, LATEST_1103, []) == 1
    assert [i["title"] for i in a["issues"]] == ["다른 이슈"]


def test_small_or_mixed_moves_do_not_trigger():
    small = {"us_candidates": [{"ticker": "MU", "change_pct": 0.2}, {"ticker": "AMD", "change_pct": 0.3}]}
    mixed = {"us_candidates": [{"ticker": "MU", "change_pct": 2.0}, {"ticker": "AMD", "change_pct": -2.0}]}
    for latest in (small, mixed):
        a = {"issues": [_issue()]}
        assert va.fix_issue_premarket_contradictions(a, latest, []) == 0


def test_one_measured_ticker_is_not_enough():
    a = {"issues": [_issue(down={"label": "x", "tickers": ["MU", "ZZZ"]})]}
    assert va.fix_issue_premarket_contradictions(a, LATEST_1103, []) == 0


def test_up_side_mirror():
    latest = {"us_candidates": [{"ticker": "XOM", "change_pct": -1.2}, {"ticker": "CVX", "change_pct": -0.9}]}
    a = {"issues": [{"title": "유가 반등", "body": "에너지주가 오르고 있어요.", "up": {"label": "에너지", "tickers": ["XOM", "CVX"]}}]}
    assert va.fix_issue_premarket_contradictions(a, latest, []) == 1
    assert a["issues"][0]["body"] == "발행 시점 프리마켓에선 XOM -1.2%·CVX -0.9%로 내리고 있어요."


# ── 미국 채점 ──
@pytest.mark.parametrize("up,down,want", [(32, 68, "하락 우위"), (60, 40, "상승 우위"), (50, 50, "중립"), (None, None, "중립")])
def test_direction_from_pct(up, down, want):
    assert cc._direction_from_pct({"up_pct": up, "down_pct": down}) == want


def test_save_and_score_us_prediction(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    (tmp_path / "latest_us.json").write_text(json.dumps({"futures": {"sp500_fut": {"change_pct": -0.18}}}), encoding="utf-8")
    cc.save_prediction_to_briefings("us", "2026-11-03", {"prediction": {"up_pct": 35, "down_pct": 65}})
    path = tmp_path / "briefings.json"
    row = json.loads(path.read_text(encoding="utf-8"))["briefings"][0]
    assert row["predicted_direction"] == "하락 우위" and row["prior_up_pct"] == 45 and "basis" not in row

    monkeypatch.setattr(ca, "load_briefings", lambda: json.loads(path.read_text(encoding="utf-8")))
    monkeypatch.setattr(ca, "save_briefings", lambda d: path.write_text(json.dumps(d), encoding="utf-8"))
    monkeypatch.setattr(ca, "get_sp500_close_vs_prev_close", lambda d: (100.0, 101.0, -0.99))
    ca.check_accuracy("2026-11-03", "us")
    row = json.loads(path.read_text(encoding="utf-8"))["briefings"][0]
    assert row["is_correct"] is True and row["actual_direction"] == "하락" and row["actual_change_pct"] == -0.99


def test_summary_no_longer_marks_us_retired(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "WEB_DATA_DIR", tmp_path)
    monkeypatch.setattr(ca, "load_briefings", lambda: {"briefings": [
        {"date": "2026-11-02", "type": "us", "is_correct": True}, {"date": "2026-11-03", "type": "us", "is_correct": False}]})
    ca.write_accuracy_summary()
    us = json.loads((tmp_path / "accuracy-summary.json").read_text(encoding="utf-8"))["us"]
    assert us["scored"] == 2 and us["hit"] == 1 and "retired" not in us and us["basis"] == "close"


# ── 선물 구간표 ──
def test_fit_uses_previous_es_daily_close_and_hides_late_bars():
    pub = datetime(2026, 11, 3, 21, 15, tzinfo=KST).timestamp()
    es_h = [(pub - 3600, 101.0), (pub - 1800, 999.0)]          # 21:15 전에 끝나지 않은 봉은 쓰지 않는다
    es_d = [(date(2026, 11, 2), 100.0), (date(2026, 11, 3), 500.0)]
    sp_d = [(date(2026, 11, 2), 200.0), (date(2026, 11, 3), 198.0)]
    rows = fit.build_rows(es_h, es_d, sp_d)
    assert len(rows) == 1 and round(rows[0]["es"], 2) == 1.0 and round(rows[0]["sp"], 2) == -1.0


def test_committed_band_table_is_monotonic():
    cfg = json.loads(fit.OUT.read_text(encoding="utf-8"))
    ups = [b["up_pct"] for b in cfg["bands"]]
    assert ups == sorted(ups) and sum(b["days"] for b in cfg["bands"]) == cfg["days"]


# ── 나스닥 월간 텔레그램 ──
NQ = {"nasdaq_overheat": {"gap_pct": 47.41, "series": [{"m": "2026-09", "g": 58.89}, {"m": "2026-10", "g": 59.87}, {"m": "2026-11", "g": 47.41}]}}


def _briefings_dir(tmp_path, monkeypatch, dates):
    monkeypatch.setattr(gh, "BRIEFINGS_DIR", tmp_path)
    for d in dates:
        (tmp_path / d / "us").mkdir(parents=True)
        (tmp_path / d / "us" / "index.html").write_text("x")


def test_month_lines_on_first_briefing(tmp_path, monkeypatch):
    _briefings_dir(tmp_path, monkeypatch, ["2026-10-30"])
    assert cc._nasdaq_month_lines(NQ, "2026-11-02") == [
        "", "📊 나스닥 체크 10월 +59.9% · ✓ 정상", "9월 +58.9%에서 +1.0%p, 주의 기준은 60%예요."]


def test_month_lines_same_on_rerun_of_first_day(tmp_path, monkeypatch):
    _briefings_dir(tmp_path, monkeypatch, ["2026-11-02"])              # 첫날 발행본이 생긴 뒤 같은 날짜를 다시 만들어도 같다
    assert cc._nasdaq_month_lines(NQ, "2026-11-02")


def test_month_lines_only_once_a_month(tmp_path, monkeypatch):
    _briefings_dir(tmp_path, monkeypatch, ["2026-11-02"])
    assert cc._nasdaq_month_lines(NQ, "2026-11-03") == []


def test_month_lines_level_and_january(tmp_path, monkeypatch):
    _briefings_dir(tmp_path, monkeypatch, [])
    a = {"nasdaq_overheat": {"series": [{"m": "2026-11", "g": 61.0}, {"m": "2026-12", "g": 72.4}]}}
    assert cc._nasdaq_month_lines(a, "2027-01-04") == [
        "", "📊 나스닥 체크 12월 +72.4% · 🚨 경고", "11월 +61.0%에서 +11.4%p, 주의 기준은 60%예요.",
        "※ 과거 70% 넘은 달 뒤 12개월 안에 -20% 넘게 빠진 경우가 51%였어요(전체 19%)."]


def test_month_lines_missing_data(tmp_path, monkeypatch):
    _briefings_dir(tmp_path, monkeypatch, [])
    monkeypatch.setattr(gh, "_read_nasdaq_overheat", lambda d: None)
    assert cc._nasdaq_month_lines({}, "2026-11-02") == []


# ── 하이퍼리퀴드 기록 ──
def _c(dt_kst, close):
    return {"t": int(dt_kst.timestamp() * 1000), "c": str(close)}


def test_hl_move_from_1530_candle():
    base = datetime(2026, 11, 2, 15, 30, tzinfo=KST)
    now = datetime(2026, 11, 3, 7, 25, tzinfo=KST)
    cs = [_c(base - timedelta(minutes=15), 100), _c(base, 150), _c(now - timedelta(minutes=10), 98)]
    assert hs.move_pct(cs, base.timestamp(), now.timestamp()) == -2.0      # 15:15 봉(15:30 마감)이 기준


def test_hl_stale_or_missing_is_none():
    base = datetime(2026, 11, 2, 15, 30, tzinfo=KST)
    now = datetime(2026, 11, 3, 7, 25, tzinfo=KST)
    assert hs.move_pct([_c(base - timedelta(minutes=15), 100)], base.timestamp(), now.timestamp()) is None
    assert hs.move_pct([_c(now - timedelta(minutes=10), 98)], base.timestamp(), now.timestamp()) is None


def test_hl_coin_failure_keeps_others(monkeypatch):
    monkeypatch.setattr(hs, "prev_kospi_session", lambda d: date(2026, 11, 2))
    base = datetime(2026, 11, 2, 15, 30, tzinfo=KST)
    now = datetime(2026, 11, 3, 7, 25, tzinfo=KST)

    def fetch(coin, s, e):
        if coin == "KR200":
            raise OSError("down")
        return [_c(base - timedelta(minutes=15), 100), _c(now - timedelta(minutes=10), 101)]
    assert set(hs.collect(date(2026, 11, 3), now.timestamp(), fetch)) == {"SMSN", "SKHX", "EWY"}


def test_hl_is_recorded_not_prompted(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    (tmp_path / "hl_signals.json").write_text(json.dumps({"date": "2026-11-03", "moves": {"KR200": -1.6}}), encoding="utf-8")
    assert cc._hl_snapshot("2026-11-03") == {"hl": {"KR200": -1.6}}
    assert cc._hl_snapshot("2026-11-04") == {}                             # 다른 날 파일은 쓰지 않는다
    assert Path(cc.__file__).read_text(encoding="utf-8").count("hl_signals") == 2   # 설명 주석과 기록 함수뿐 — 프롬프트 경로에 없다


def test_shadow_report_counts():
    rows = [{"type": "kospi", "hl": {"KR200": 1.0}, "prior_score": -2.0, "up_pct": 60, "actual_open_pct": 0.5},
            {"type": "kospi", "hl": {"KR200": -1.0}, "prior_score": -2.0, "up_pct": 30, "actual_open_pct": -0.5},
            {"type": "kospi", "prior_score": 1.0, "actual_open_pct": 1.0}]
    r = hr.report(rows)
    assert r["KR200"] == {"hit": 2, "n": 2} and r["prior"] == {"hit": 1, "n": 2} and r["AI"] == {"hit": 2, "n": 2}
