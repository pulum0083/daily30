# 월봉 5개월선 3개월 안착 스크리닝 테스트 — 판정·이번 달 조건·월초·월말 봉 누락·pin·수급 정보
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import monthly_ma5 as m

KST = ZoneInfo("Asia/Seoul")


def rows_from(month_closes, cur=None, fr=None):
    """{YYYYMM: 월말 종가} → 달마다 중간 1행 + 월말 1행의 일봉. cur=(YYYYMMDD, 종가)는 진행 중인 달."""
    out = []
    for i, (mo, c) in enumerate(sorted(month_closes.items())):
        out.append({"localDate": f"{mo}10", "closePrice": c * 0.9, "foreignRetentionRate": None})
        out.append({"localDate": f"{mo}28", "closePrice": c,
                    "foreignRetentionRate": (fr[i] if fr else 10.0)})
    if cur:
        out.append({"localDate": cur[0], "closePrice": cur[1], "foreignRetentionRate": 10.0})
    return out


ltd = lambda yyyymm: f"{yyyymm}28"   # 테스트용 '마지막 거래일'
TODAY = date(2026, 10, 25)

# 2026-01~09: 1~6월 횡보 후 7·8·9월 상승 — 9월 기준 3개월 연속 5개월선 위
BASE = {"202601": 100, "202602": 100, "202603": 100, "202604": 100, "202605": 100, "202606": 100,
        "202607": 110, "202608": 115, "202609": 120}


def test_passes_three_month_run_and_current_above():
    r = m.screen_one(rows_from(BASE, cur=("20261023", 121)), TODAY, ltd)
    assert r["streak"] == 3 and r["passed"]
    assert r["run_label"] == "7월~9월"
    assert r["last_complete"] == "202609" and r["now_date"] == "20261023"
    # 9월 5개월선 = (100+100+110+115+120)/5 = 109
    assert r["month_end_ma5"] == 109 and r["month_end_gap_pct"] == round((120 / 109 - 1) * 100, 2)
    # 이번 달 5개월선 = (100+110+115+120+121)/5
    assert r["strip"][-1]["cur"] and r["strip"][-1]["ma5"] == round((100 + 110 + 115 + 120 + 121) / 5, 2)
    assert [s["run"] for s in r["strip"]][-4:] == [True, True, True, False]


def test_current_month_below_ma5_is_excluded():
    # 완성 월봉은 3개월 안착이지만 이번 달에 5개월선 아래로 내려왔다 — 프로토타입 B안 문제 사례
    r = m.screen_one(rows_from(BASE, cur=("20261023", 100)), TODAY, ltd)
    assert r["streak"] == 3 and r["passed"] is False


def test_two_month_run_does_not_pass():
    b = dict(BASE, **{"202607": 100})
    r = m.screen_one(rows_from(b, cur=("20261023", 125)), TODAY, ltd)
    assert r["streak"] == 2 and not r["passed"]


def test_month_start_without_current_rows_judges_completed_months_only():
    # 11/2 07:25 — 11월 행이 아직 없다. 10월까지가 완성 월이고 이번 달 조건은 판단하지 않는다.
    b = dict(BASE, **{"202610": 125})
    r = m.screen_one(rows_from(b), date(2026, 11, 2), ltd)
    assert r["last_complete"] == "202610" and r["streak"] == 4 and r["passed"]
    assert r["mtd_pct"] is None and not r["strip"][-1]["cur"]


def test_missing_month_end_bar_after_aftermarket_start_skips_stock():
    rows = [r for r in rows_from(BASE, cur=("20261023", 121)) if r["localDate"] != "20260928"]
    assert m.screen_one(rows, TODAY, ltd) is None


def test_not_enough_months_returns_none():
    few = {k: BASE[k] for k in list(BASE)[-4:]}
    assert m.screen_one(rows_from(few, cur=("20261023", 121)), TODAY, ltd) is None


def test_foreign_ownership_change_is_info_only():
    fr = [10, 10, 10, 10, 10, 9.5, 9.0, 8.8, 8.4]   # 6월 말 9.5 → 9월 말 8.4
    r = m.screen_one(rows_from(BASE, cur=("20261023", 121), fr=fr), TODAY, ltd)
    assert r["fr_now"] == 8.4 and r["fr_chg_3m"] == -1.1
    assert r["passed"]   # 보유율이 줄어도 거르지 않는다(사용자 결정)


def test_run_skips_failed_and_sorts_by_streak(monkeypatch):
    monkeypatch.delenv("DS_PIN_SESSION_DATE", raising=False)
    long_run = dict(BASE, **{"202605": 105, "202606": 108})   # 5·6월도 선 위 → 연속 5개월
    data = {"A": rows_from(BASE, cur=("20261023", 121)),
            "B": rows_from(long_run, cur=("20261023", 130)),
            "C": []}
    res = m.run(now=datetime(2026, 10, 25, 7, 25, tzinfo=KST), fetch_rows=data.get,
                universe=[("A", "에이"), ("B", "비"), ("C", "씨")], last_trading_day=ltd)
    assert [x["code"] for x in res["items"]] == ["B", "A"]
    assert res["failed"] == ["C"] and res["screened"] == 2 and res["date"] == "2026-10-25"


def test_run_returns_none_when_every_fetch_fails(monkeypatch):
    monkeypatch.delenv("DS_PIN_SESSION_DATE", raising=False)
    res = m.run(now=datetime(2026, 10, 25, 7, 25, tzinfo=KST), fetch_rows=lambda c: [],
                universe=[("A", "에이")], last_trading_day=ltd)
    assert res is None


def test_pin_drops_rows_on_and_after_pin_date(monkeypatch):
    # 장 시작 후 재생성(§37) — pin 날짜의 진행 중인 봉을 '이번 달'로 쓰지 않는다
    monkeypatch.setenv("DS_PIN_SESSION_DATE", "2026-10-23")
    rows = rows_from(BASE, cur=("20261022", 121)) + [{"localDate": "20261023", "closePrice": 90,
                                                      "foreignRetentionRate": 10.0}]
    res = m.run(now=datetime(2026, 10, 23, 10, 0, tzinfo=KST), fetch_rows=lambda c: rows,
                universe=[("A", "에이")], last_trading_day=ltd)
    assert res["date"] == "2026-10-23"
    assert res["items"][0]["now_date"] == "20261022" and res["items"][0]["now_close"] == 121


def test_load_universe_reads_hub_46():
    u = m.load_universe()
    assert len(u) == 46 and len({c for c, _ in u}) == 46
