# 네이버 stock.naver.com JSON 전환(§51) — 마감 시장 폭·업종·급등주·dpick·정규장 수급 수집 회귀 테스트
import json
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest
import pytz

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_closing_kospi as fc
import fetch_data as fd
import kr_official_closes  # noqa: F401 — isolated()가 sys.modules에서 찾는다

KST = pytz.timezone("Asia/Seoul")
FX = Path(__file__).resolve().parent / "fixtures" / "naver_market"


def fx(name):
    text = (FX / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    """실행마다 실패 목록을 비우고, 공식 종가 저장소(data/kr_official_closes.json)를 읽지 않게 한다."""
    monkeypatch.setattr(fc, "_source_failures", [])
    monkeypatch.setattr(fc, "_after_market_skips", [])
    for name in ("kr_official_closes", "scripts.kr_official_closes"):
        mod = sys.modules.get(name)
        if mod is not None:
            monkeypatch.setattr(mod, "_cache", {})


# ── 시장 폭 ──────────────────────────────────────────────────────────────────

def test_시장폭은_integration의_upDownStockInfo를_읽는다():
    # 2026-09-15 09:33 실응답 — upperCount 1 · riseCount 245 · lowerCount 0 · fallCount 609 · steadyCount 49
    assert fc.parse_market_breadth(fx("index_integration.json")) == {
        "up": 245, "down": 609, "unchanged": 49, "upper_limit": 1, "lower_limit": 0,
        "new_high": 0, "new_low": 0,
    }


def test_시장폭_옛_페이지처럼_빈_응답이면_비우고_실패로_기록한다():
    # 2026-09-14 실사고: finance.naver.com/sise/가 302 + 빈 본문을 줬는데 예외 없이 끝났다.
    assert fc.fetch_market_breadth(fetch=lambda url: {}) == {}
    assert fc._source_failures and fc._source_failures[0].startswith("market_breadth")


def test_시장폭_상승_하락이_모두_0이면_미수집으로_본다():
    payload = {"upDownStockInfo": {"upperCount": "0", "riseCount": "0", "lowerCount": "0",
                                   "fallCount": "0", "steadyCount": "0"}}
    assert fc.parse_market_breadth(payload) == {}


# ── 업종 ────────────────────────────────────────────────────────────────────

def test_업종_목록은_부호가_있는_등락률을_그대로_쓴다():
    groups = fc.parse_industry_groups(fx("industry_list.json"))
    assert len(groups) == 79
    assert groups[0] == {"no": 262, "name": "생명과학도구및서비스", "change_pct": 2.91}
    assert groups[-1] == {"no": 284, "name": "우주항공과국방", "change_pct": -4.89}


def test_업종_상위종목에서_코넥스를_뺀다():
    top = fc.parse_industry_top_stocks(fx("industry_278.json"), limit=3)
    assert [s["name"] for s in top] == ["시지트로닉스", "피에스케이홀딩스", "DB하이텍"]
    assert top[0]["change_pct"] == 10.65


def test_업종은_등락폭이_큰_5개와_각_상위종목을_돌려준다(monkeypatch):
    detail = fx("industry_278.json")
    calls = []

    def fetch(url):
        calls.append(url)
        return fx("industry_list.json") if url == fc.INDUSTRY_LIST_URL else detail

    monkeypatch.setattr(fc.time, "sleep", lambda s: None)
    out = fc.fetch_sector_performance(fetch=fetch, now=KST.localize(datetime(2026, 9, 15, 15, 45)))
    assert [s["name"] for s in out][:2] == ["우주항공과국방", "조선"]
    assert len(out) == 5 and all(len(s["stocks"]) == 3 for s in out)
    assert len(calls) == 6


# ── 급등주 ──────────────────────────────────────────────────────────────────

def test_급등주는_ETF_ETN을_빼고_형식을_유지한다():
    assert fc.parse_top_gainers(fx("stocks_up.json")) == [
        {"name": "SHD", "change_pct": "+29.97%", "price": "9,800원"},
        {"name": "명문제약", "change_pct": "+13.58%", "price": "1,405원"},
        {"name": "신풍", "change_pct": "+8.94%", "price": "1,133원"},
    ]


# ── dpick ───────────────────────────────────────────────────────────────────

def test_dpick_유니버스는_보통주만():
    assert fc.parse_dpick_universe(fx("stocks_quanttop.json"))[:2] == [("017900", "광전자"), ("004310", "현대약품")]


def test_9월14일_trend_종가_거래량을_정규장_값으로_바꾼다():
    # 실측: trend 종가 248,500·거래량 17,776,098은 20:00 애프터장까지 누적. 공식 종가 249,000,
    # 09:00~15:30 1분봉 거래량 합 16,559,147.
    rows = [r for r in fc.parse_stock_trend(fx("stock_trend_005930.json")) if r["date"] <= "20260914"]
    assert rows[0]["close"] == 248500 and rows[0]["vol"] == 17776098
    bars = fx("minute_005930_20260914.json")
    fixed = fc.regular_session_rows("005930", rows, fetch=lambda url: bars)
    assert fixed[0]["close"] == 249000 and fixed[0]["vol"] == 16559147
    assert fixed[1] == rows[1]   # 9/11은 애프터마켓 개장 전이라 그대로


def test_1분봉을_못_받으면_종가_거래량을_비운다():
    rows = [r for r in fc.parse_stock_trend(fx("stock_trend_005930.json")) if r["date"] <= "20260914"]

    def boom(url):
        raise OSError("timeout")

    fixed = fc.regular_session_rows("005930", rows, fetch=boom)
    assert fixed[0]["close"] is None and fixed[0]["vol"] is None


def _bar(ts, price, vol):
    return {"localDateTime": ts, "currentPrice": price, "accumulatedTradingVolume": vol}


def _dpick_fetch(today_trend=True):
    trend = [
        {"bizdate": "20260915", "closePrice": "10,500", "accumulatedTradingVolume": "3,000,000",
         "foreignerPureBuyQuant": "+100,000", "organPureBuyQuant": "+200,000"},
        {"bizdate": "20260914", "closePrice": "9,900", "accumulatedTradingVolume": "1,100,000",
         "foreignerPureBuyQuant": "-1", "organPureBuyQuant": "-1"},
    ] + [
        {"bizdate": f"202608{d:02d}", "closePrice": "10,000", "accumulatedTradingVolume": "1,000,000",
         "foreignerPureBuyQuant": "0", "organPureBuyQuant": "0"} for d in range(28, 10, -1)
    ]
    if not today_trend:
        trend = trend[1:]
    bars = [
        _bar("20260914090000", 9950, 400000), _bar("20260914153000", 10000, 600000),
        _bar("20260914160000", 9900, 100000),                       # 애프터장 — 빠져야 한다
        _bar("20260915090000", 10100, 2000000), _bar("20260915153000", 10300, 500000),
        _bar("20260915161000", 10500, 500000),                      # 애프터장 — 빠져야 한다
    ]
    universe = {"stocks": [{"stockEndType": "etf", "itemCode": "252670", "stockName": "KODEX 200선물인버스2X"},
                           {"stockEndType": "stock", "itemCode": "111111", "stockName": "가나전자"}]}

    def fetch(url):
        if "quantTop" in url:
            return universe
        if "/stock/111111/trend" in url:
            return trend
        if "/minute" in url:
            return bars
        raise AssertionError(f"예상 밖 URL {url}")
    return fetch


def test_dpick_등락률_거래대금은_정규장_값으로_계산한다():
    now = KST.localize(datetime(2026, 9, 15, 16, 30))
    picks = fc.fetch_dpick(now=now, fetch=_dpick_fetch())
    # 종가 10,300(15:30 1분봉) vs 전일 10,000 → +3.00%. 애프터장 10,500·9,900이면 +6.06%가 된다.
    # 거래대금 = 정규장 거래량 2,500,000 × 10,300 = 257.5억. 평균 = (257.5 + 100 × 19) / 20 = 107.875억.
    assert picks == [{
        "name": "가나전자", "code": "111111", "change_pct": 3.0, "trade_value_eok": 258,
        "trade_mult": 2.4, "frgn_eok": 10, "inst_eok": 21,
    }]


def test_dpick_오늘_행이_아직_없으면_건너뛴다():
    now = KST.localize(datetime(2026, 9, 15, 16, 30))
    assert fc.fetch_dpick(now=now, fetch=_dpick_fetch(today_trend=False)) == []
    assert fc._source_failures == []   # 원천 고장이 아니다 — §1의 정상 동작


def test_dpick_유니버스가_비면_원천_실패로_기록한다():
    assert fc.fetch_dpick(fetch=lambda url: {"stocks": []}) == []
    assert fc._source_failures == ["dpick: 거래량 상위 목록 0건"]


# ── 정규장 수급 ─────────────────────────────────────────────────────────────

def test_시간대별_표_실응답을_읽는다():
    rows = fd.parse_investor_time_page(fx("investor_time_20260914_p19.html"))
    assert rows[0] == {"t": "1534", "individual": 29722, "foreign": -32875, "institution": -11715}
    assert {"t": "1530", "individual": 29190, "foreign": -33231, "institution": -10843} in rows
    assert fd._investor_last_page(fx("investor_time_20260914_p19.html")) == 45


def _row(t, vals):
    return f"<tr><td class=\"date\">{t}</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>"


# 9/14 15:34 실측 행 — 개인 + 외국인 + 기관계 + 기타법인 = 0
CLOSE_ROW = ["29,722", "-32,875", "-11,715", "-5,369", "259", "-6,106", "9", "195", "-703", "14,868"]
AFTER_ROW = ["30,351", "-33,363", "-11,869", "-5,524", "259", "-6,105", "9", "195", "-703", "14,881"]
MID_ROW = ["29,190", "-33,231", "-10,843", "-6,857", "271", "-3,595", "10", "194", "-866", "14,884"]


def _pages(pages):
    last = len(pages)
    links = " ".join(f'<a href="?page={i}">' for i in range(1, last + 1))
    return {i + 1: "<table>" + "".join(_row(t, v) for t, v in rows) + "</table>" + links
            for i, rows in enumerate(pages)}


def _serve(pages):
    return lambda url: pages[int(url.rsplit("page=", 1)[1])]


def test_마감_잡은_애프터장_행이_아니라_1540_이하_첫_행을_쓴다():
    pages = _pages([
        [("16:25", AFTER_ROW), ("16:20", AFTER_ROW)],
        [("15:45", AFTER_ROW), ("15:40", CLOSE_ROW), ("15:36", CLOSE_ROW)],
        [("15:30", MID_ROW), ("15:28", MID_ROW)],
    ])
    got = fd.regular_session_investor("20260914", fetch_text=_serve(pages))
    assert got == {"date": "20260914", "asof": "1540", "foreign": {"net": -3287500},
                   "institution": {"net": -1171500}, "individual": {"net": 2972200}}


def test_정규장이_끝나기_전이면_비운다():
    pages = _pages([[("15:30", MID_ROW), ("15:28", MID_ROW)]])
    assert fd.regular_session_investor("20260915", fetch_text=_serve(pages)) == {}


def test_중간_페이지가_깨지면_비운다():
    pages = _pages([[("16:25", AFTER_ROW)], [], [("15:36", CLOSE_ROW)]])
    assert fd.regular_session_investor("20260914", fetch_text=_serve(pages)) == {}


def test_아침_브리핑은_네이버_집계일이_오늘이면_전_평일로_간다():
    seen = []
    pages = _pages([[("15:40", CLOSE_ROW)]])

    def fetch_text(url):
        seen.append(url.split("bizdate=")[1][:8])
        return pages[1]

    monday = KST.localize(datetime(2026, 9, 14, 7, 25))
    got = fd.fetch_investor_trading_kospi(now=monday, fetch_text=fetch_text,
                                          fetch_json=lambda url: {"bizdate": "20260914"})
    assert got["date"] == "20260911" and set(seen) == {"20260911"}

    tuesday = KST.localize(datetime(2026, 9, 15, 7, 25))
    got = fd.fetch_investor_trading_kospi(now=tuesday, fetch_text=fetch_text,
                                          fetch_json=lambda url: {"bizdate": "20260914"})
    assert got["date"] == "20260914"


# ── 저장·알림 가드 ─────────────────────────────────────────────────────────

GOOD = {"market_breadth": {"up": 1}, "sectors": [1], "top_gainers": [1], "investor_trading": {"x": 1}, "dpick": [1]}


def test_같은날_1540_이후_저장본의_값은_빈_수집으로_덮지_않는다():
    old = {"generated_at": "2026-09-15T16:26:00+09:00", **GOOD}
    new = {"generated_at": "2026-09-15T16:40:00+09:00", "market_breadth": {}, "sectors": [9],
           "top_gainers": [], "investor_trading": {}, "dpick": []}
    assert fc.preserve_same_day(new, old) == ["market_breadth", "top_gainers", "investor_trading", "dpick"]
    assert new["market_breadth"] == {"up": 1} and new["sectors"] == [9]


@pytest.mark.parametrize("old_at", ["2026-09-14T16:26:00+09:00", "2026-09-15T14:00:00+09:00", ""])
def test_다른날이나_장중에_만든_파일은_되살리지_않는다(old_at):
    new = {"generated_at": "2026-09-15T16:40:00+09:00", "market_breadth": {}}
    assert fc.preserve_same_day(new, {"generated_at": old_at, **GOOD}) == []
    assert new["market_breadth"] == {}


def _capture_alerts(monkeypatch):
    sent = []
    fake = types.ModuleType("send_telegram")
    fake.send_admin_alert = sent.append
    monkeypatch.setitem(sys.modules, "send_telegram", fake)
    monkeypatch.setitem(sys.modules, "scripts.send_telegram", fake)
    return sent


def test_9월14일처럼_전부_비면_관리자에게_알린다(monkeypatch):
    sent = _capture_alerts(monkeypatch)
    data = {"market_breadth": {}, "sectors": [], "top_gainers": [], "investor_trading": {}, "dpick": []}
    fc.alert_source_failures(data, ["market_breadth: 등락 종목 수를 읽지 못함"])
    assert len(sent) == 1
    assert "market_breadth, sectors, top_gainers, investor_trading" in sent[0]


def test_다_채워졌으면_알리지_않는다(monkeypatch):
    sent = _capture_alerts(monkeypatch)
    fc.alert_source_failures(dict(GOOD), [])
    assert sent == []


# ── 애프터장 가드 ───────────────────────────────────────────────────────────

AT_1625 = KST.localize(datetime(2026, 9, 15, 16, 25))


@pytest.mark.parametrize("hm,ok", [((8, 59), False), ((9, 0), True), ((15, 59), True), ((16, 0), False), ((16, 25), False)])
def test_목록_가격은_09시부터_16시_전까지만_정규장_값이다(hm, ok):
    assert fc.list_prices_regular(KST.localize(datetime(2026, 9, 15, *hm))) is ok


def test_16시_이후엔_업종_급등주를_조회하지_않고_비운다():
    def fetch(url):
        raise AssertionError("조회하면 안 된다")
    assert fc.fetch_sector_performance(fetch=fetch, now=AT_1625) == []
    assert fc.fetch_top_gainers(fetch=fetch, now=AT_1625) == []
    assert fc._after_market_skips == ["sectors", "top_gainers"] and fc._source_failures == []


def test_시장폭은_16시_이후에도_쓴다():
    # 9/15 실측: upDownStockInfo가 15:36·15:58·16:12 모두 같았다(애프터장 가격을 따르지 않는다).
    assert fc.fetch_market_breadth(fetch=lambda url: fx("index_integration.json"), now=AT_1625)["up"] == 245


def test_시간대로_비운_항목은_원천_고장_알림에서_뺀다(monkeypatch):
    sent = _capture_alerts(monkeypatch)
    monkeypatch.setattr(fc, "_after_market_skips", ["sectors", "top_gainers"])
    fc.alert_source_failures({**GOOD, "sectors": [], "top_gainers": []}, [])
    assert sent == []
    fc.alert_source_failures({**GOOD, "sectors": [], "top_gainers": [], "market_breadth": {}}, [])
    assert len(sent) == 1 and "빈 항목: market_breadth\n" in sent[0]
