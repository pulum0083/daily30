# 코스피 아침이 밤사이 미국 실적·시간외 반응을 놓치지 않는지 — 2026-11-18 엔비디아 실적 누락 실사고 리플레이
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_testkit import news_patch, data_patch  # noqa: E402
import fetch_news as fn  # noqa: E402
import news_gate_earnings as ge  # noqa: E402
import news_rss as nr  # noqa: E402
import news_sources as ns  # noqa: E402
import price_quotes as pq  # noqa: E402
import prompt_directives as pd_  # noqa: E402

KST = pytz.timezone("Asia/Seoul")
TODAY = date(2026, 11, 18)


# ── ① 실적 게이트 — 야후 기록이 밀린 발표 직후 ──────────────────────────────────

def test_vendor_lag_counts_as_fresh_release():
    # 엔비디아: 기록상 직전 발표 8/26(84일 전), 일정은 11/18 → 방금 발표
    assert ge._vendor_lag_age(84, [date(2026, 11, 18)], TODAY) == 0
    assert ge._vendor_lag_age(None, [date(2026, 11, 17)], TODAY) == 0


def test_really_old_earnings_still_stale():
    assert ge._vendor_lag_age(49, [date(2026, 12, 24)], TODAY) == 49     # 마이크론 — 기록이 최근이면 그대로
    assert ge._vendor_lag_age(84, [date(2026, 11, 22)], TODAY) == 84     # 일정이 아직 멀면 그대로(지어낸 실적 차단)
    assert ge._vendor_lag_age(84, [date(2026, 11, 10)], TODAY) == 84     # 일정이 지난 지 오래면 그대로
    assert ge._vendor_lag_age(84, [], TODAY) == 84


def test_incident_catalyst_survives_gate():
    items = [{"date": "2026-11-18", "text": "엔비디아(NVDA) 3분기 매출 1158억달러로 예상 상회 → 시간외 상승"}]
    out = ge._drop_stale_earnings(items, TODAY, age_fn=lambda t, d: ge._vendor_lag_age(84, [date(2026, 11, 18)], d))
    assert len(out) == 1


# ── ② 코스피 아침 RSS — 창·합치기 ───────────────────────────────────────────

def _rss(*items):
    body = "".join(f"<item><title>{t} - 매체</title><link>https://x/{i}</link><pubDate>{p}</pubDate></item>"
                   for i, (t, p) in enumerate(items))
    return f"<rss><channel>{body}</channel></rss>".encode()


def test_fetch_rss_since_window(monkeypatch):
    xml = _rss(("어제 오후 기사", "Tue, 17 Nov 2026 08:00:00 GMT"),       # 17:00 KST — 창 안
               ("어제 오전 기사", "Tue, 17 Nov 2026 01:00:00 GMT"),       # 10:00 KST — 창 밖
               ("새벽 실적 기사", "Tue, 17 Nov 2026 21:24:00 GMT"))       # 11/18 06:24 KST
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return xml
    monkeypatch.setattr(ns.urllib.request, "urlopen", lambda *a, **k: R())
    since = KST.localize(datetime(2026, 11, 17, 16, 0))
    got = [a["title"] for a in ns.fetch_rss("https://x/rss", "2026-11-18", since=since)]
    assert got == ["어제 오후 기사", "새벽 실적 기사"]
    assert [a["title"] for a in ns.fetch_rss("https://x/rss", "2026-11-18")] == ["새벽 실적 기사"]   # since 없으면 예전대로 오늘만


def test_kospi_rss_since_covers_weekend():
    assert nr._kospi_rss_since(TODAY) == KST.localize(datetime(2026, 11, 17, 16, 0))
    assert nr._kospi_rss_since(date(2026, 11, 16)) == KST.localize(datetime(2026, 11, 13, 16, 0))   # 월요일 → 금요일 오후부터


def test_merge_puts_rss_first_and_drops_duplicates():
    gem = {"catalysts": ["엔비디아 실적 발표 시간외 상승 → 반도체 강세", "한은 총재 발언 → 금리 기대 변화"],
           "key_indicators": ["국내 지표"]}
    rss = {"catalysts": ["엔비디아 실적 발표 뒤 시간외 상승 → 반도체 강세 기대"],
           "catalyst_sources": [{"source": "뉴스1", "published_at": "2026-11-18T06:24:59+09:00"}]}
    out = fn.merge_rss_catalysts(gem, rss)
    assert out["catalysts"] == ["엔비디아 실적 발표 뒤 시간외 상승 → 반도체 강세 기대", "한은 총재 발언 → 금리 기대 변화"]
    assert out["catalyst_sources"][0]["source"] == "뉴스1" and out["key_indicators"] == ["국내 지표"]
    assert fn.merge_rss_catalysts(gem, {"catalysts": []}) is gem


def test_main_kospi_merges_rss_and_survives_rss_failure(monkeypatch, tmp_path):
    news_patch(monkeypatch, "DATA_DIR", tmp_path)
    news_patch(monkeypatch, "fetch_and_summarize", lambda t: {"catalysts": ["국내 사건 → 영향"], "key_indicators": [], "headlines": []})
    news_patch(monkeypatch, "fetch_and_summarize_rss", lambda t: {"catalysts": ["엔비디아 실적 → 반도체"], "catalyst_sources": []})
    monkeypatch.setattr(sys, "argv", ["fetch_news.py", "--type", "kospi"])
    fn.main()
    import json
    saved = json.loads((tmp_path / "news_summary_kospi.json").read_text(encoding="utf-8"))
    assert saved["catalysts"][0] == "엔비디아 실적 → 반도체"

    def boom(t):
        raise RuntimeError("RSS 장애")
    news_patch(monkeypatch, "fetch_and_summarize_rss", boom)
    fn.main()
    saved = json.loads((tmp_path / "news_summary_kospi.json").read_text(encoding="utf-8"))
    assert saved["catalysts"] == ["국내 사건 → 영향"]                      # RSS가 죽어도 브리핑은 계속


# ── ③ 시간외 움직임을 정규장 등락과 떼어 낸다 ────────────────────────────────────

def _hist(closes):
    idx = pd.date_range("2025-11-18", periods=len(closes), freq="B", tz="America/New_York")
    return pd.DataFrame({"Close": closes, "Volume": [1] * len(closes)}, index=idx)


def test_since_close_fields_for_us_equity(monkeypatch):
    closes = [100.0] * 250 + [156.15, 155.46]
    data_patch(monkeypatch, "_yf_history", lambda *a, **k: _hist(closes))
    data_patch(monkeypatch, "_get_realtime_price", lambda t: (161.82, 156.15))
    d = pq.get_ticker_full("NVDA")
    assert d["regular_close"] == 155.46 and d["regular_change_pct"] == -0.44 and d["since_close_pct"] == 4.09
    assert "since_close_pct" not in pq.get_ticker_full("^SOX")             # 지수엔 시간외가 없다


def test_no_since_close_when_price_is_the_close(monkeypatch):
    closes = [100.0] * 250 + [156.15, 155.46]
    data_patch(monkeypatch, "_yf_history", lambda *a, **k: _hist(closes))
    data_patch(monkeypatch, "_get_realtime_price", lambda t: (155.46, 156.15))
    assert "since_close_pct" not in pq.get_ticker_full("NVDA")


def test_after_hours_directive():
    data = {"bigtech": {"NVDA": {"since_close_pct": 4.09, "regular_change_pct": -0.44},
                        "AAPL": {"since_close_pct": -0.4, "regular_change_pct": -0.25}},
            "ai_infra": {"DELL": {"since_close_pct": 6.39, "regular_change_pct": 0.7}}}
    d = pd_._after_hours_directive(data)
    assert d.index("델(DELL)") < d.index("엔비디아(NVDA)")                  # 크게 움직인 순
    assert "엔비디아(NVDA): 정규장 -0.44% 마감 → 마감 뒤 시간외 +4.09%" in d
    assert "AAPL" not in d                                                  # 1% 미만은 적지 않는다
    assert pd_._after_hours_directive({"bigtech": {"AAPL": {"since_close_pct": 0.3}}}) == ""


# ── ④ 실적 후보(야후 일정) — 발표했다고 단정하지 않고 뉴스로 확인하게 한다 ──────────

def test_earnings_near_window(monkeypatch):
    import econ_calendar as ec
    import yfinance as yf
    cal = {"NVDA": [date(2026, 11, 18)], "AMD": [date(2026, 11, 25)], "MU": [date(2026, 11, 17)], "ORCL": []}

    class T:
        def __init__(self, t): self.calendar = {"Earnings Date": cal.get(t, [])}
    monkeypatch.setattr(yf, "Ticker", T)
    got = ec.fetch_earnings_near(["NVDA", "AMD", "MU", "ORCL"], date(2026, 11, 18), date(2026, 11, 17))
    assert [g["ticker"] for g in got] == ["NVDA", "MU"]


def test_directive_lists_earnings_candidates_without_moves():
    d = pd_._after_hours_directive({"earnings_near": [{"ticker": "AMD", "calendar_date": "2026-11-18"}]})
    assert "AMD(AMD): 일정 2026-11-18" in d and "발표됐다고 쓰지 않는다" in d
    assert "장 마감 뒤 움직임 (지금" not in d                                 # 움직임이 없으면 그 칸은 없다
