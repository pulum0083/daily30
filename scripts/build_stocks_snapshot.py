# 종목 유니버스 일봉 → 시세·52주·스파크라인·MA200 스냅샷 빌드
#!/usr/bin/env python3
"""실행: python3 scripts/build_stocks_snapshot.py
   stock_universe.json의 한국 종목(~41) + 섹터 벨웨더를 수집해
   web/data/stocks-snapshot.json 으로 저장한다. SERVICE_RULES 0번 준수.
   한국 종목은 네이버 일봉(종가+거래량+외국인보유율), 미국 벨웨더는 토스→yfinance.

   ⚠️ 장 마감 후 실행 전제. change_pct는 closes[-1] vs closes[-2]로 계산하므로,
   장중에 돌리면 마지막 캔들이 미완료 세션(움직이는 종가)이 되어 등락률이
   '직전 완료 세션 종가 대비'(validate_analysis 기준)와 어긋난다.
   CI에서는 kospi-close 잡(16:30 KST 이후)에서만 실행한다."""
import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import toss_client as tc

KST = timezone(timedelta(hours=9))
_VOL_SENTINEL = 2147483647  # 네이버 int32 오버플로 값 — 실측 아님, 사용 금지


def change_pct(closes):
    """직전 완료 세션 대비 등락률(%). 데이터 부족 시 None."""
    if len(closes) < 2:
        return None
    return round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)


def wk52_high_low(closes):
    """최근 252거래일 고가/저가. (hi, lo). 데이터 부족 시 있는 만큼."""
    if not closes:
        return None, None
    window = closes[-252:]
    return max(window), min(window)


def sparkline(closes, n):
    """최근 n개 종가. 부족하면 있는 만큼."""
    return closes[-n:]


def ma200(closes):
    """최근 200거래일 단순이동평균. 200개 미만이면 None."""
    if len(closes) < 200:
        return None
    window = closes[-200:]
    return round(sum(window) / len(window), 2)


def _toss_closes(symbol):
    """토스 일봉 종가 시계열(오래된→최신). 실패 시 []."""
    try:
        candles = tc.get_candles(symbol, interval="1d", count=300)
        return [float(c["closePrice"]) for c in candles if c.get("closePrice")]
    except Exception as e:
        print(f"[snapshot] toss {symbol} 실패: {e}", file=sys.stderr)
        return []


def _naver_day_rows(code):
    """네이버 일봉 전체 행(오래된→최신). closePrice·accumulatedTradingVolume·foreignRetentionRate 포함. 실패 시 []."""
    try:
        end = datetime.now().strftime("%Y%m%d") + "0000"
        start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d") + "0000"
        url = (f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
               f"?startDateTime={start}&endDateTime={end}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except Exception as e:
        print(f"[snapshot] naver day {code} 실패: {e}", file=sys.stderr)
        return []


def _naver_closes(code):
    """네이버 일봉 종가만. 실패 시 []."""
    return [float(r["closePrice"]) for r in _naver_day_rows(code) if r.get("closePrice")]


def _last_bar_date(rows):
    """change_pct()의 closes[-1]에 실제로 대응하는 마지막 종가 봉의 날짜(YYYY-MM-DD).
    rows는 _naver_day_rows()가 준 오래된→최신 원본 행 — closePrice 없는 행(휴장·결측)은
    건너뛰고 실제로 종가가 있는 마지막 행의 localDate(YYYYMMDD, 실측 확인됨)를 쓴다.
    유효한 행이 하나도 없으면 None."""
    for r in reversed(rows):
        d = r.get("localDate")
        if r.get("closePrice") and d and len(str(d)) == 8:
            s = str(d)
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


def _reconcile_session_date(bar_dates):
    """한국 종목별 마지막 봉 날짜들에서 스냅샷 전체의 session_date를 엄격하게 결정한다.
    조회에 실패한 종목(None)은 투표에서 제외하고, 응답한 종목들의 날짜가 전부 같을 때만
    그 날짜를 채택한다. 하나라도 엇갈리면(예: 일부 종목만 최신 봉이 아직 안 올라옴)
    다수결이나 최빈값으로 추정하지 않고 None을 반환한다 — 완전성보다 정합성(§0)."""
    dates = {d for d in bar_dates if d}
    if len(dates) == 1:
        return next(iter(dates))
    return None


def _to_int(s):
    """'-847,969'·'+1,864' 같은 네이버 문자열을 정수로. 빈값/None → None."""
    if s is None:
        return None
    s = str(s).replace(",", "").replace("+", "").strip()
    if s in ("", "-", "N/A"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _q_label(key):
    """'202509' → '25Q3'. 분기 키를 짧은 라벨로."""
    if not key or len(key) < 6:
        return key or ""
    yy, mm = key[2:4], key[4:6]
    q = {"03": "1", "06": "2", "09": "3", "12": "4"}.get(mm, "")
    return f"{yy}Q{q}" if q else f"{yy}.{mm}"


def parse_supply5(rows, n=5):
    """네이버 trend 응답(최신순)에서 최근 n일 종목별 순매수 수량(주)을 시간순(오래된→최신)으로.
    각 항목: {date:'6/26', i:개인, o:기관, f:외국인}. 셋 다 None이면 제외."""
    out = []
    for r in rows[:n]:
        bd = str(r.get("bizdate", ""))
        date = f"{int(bd[4:6])}/{int(bd[6:8])}" if len(bd) == 8 else bd
        i = _to_int(r.get("individualPureBuyQuant"))
        o = _to_int(r.get("organPureBuyQuant"))
        f = _to_int(r.get("foreignerPureBuyQuant"))
        if i is None and o is None and f is None:
            continue
        out.append({"date": date, "i": i or 0, "o": o or 0, "f": f or 0})
    out.reverse()  # 오래된→최신
    return out


def parse_financials(finance_info, n=5):
    """네이버 finance/quarter 응답에서 최근 n분기 매출·영업이익(억원)을 시간순으로.
    각 항목: {q:'25Q3', rev:매출, op:영업이익, est:컨센서스추정여부}. 매출·영업이익 둘 다 없으면 제외."""
    if not finance_info:
        return []
    titles = finance_info.get("trTitleList", [])[-n:]
    rows = {r.get("title"): r.get("columns", {}) for r in finance_info.get("rowList", [])}
    rev_col = rows.get("매출액", {})
    op_col = rows.get("영업이익", {})
    out = []
    for t in titles:
        key = t.get("key")
        rev = _to_int((rev_col.get(key) or {}).get("value"))
        op = _to_int((op_col.get(key) or {}).get("value"))
        if rev is None and op is None:
            continue
        out.append({"q": _q_label(key), "rev": rev, "op": op,
                    "est": t.get("isConsensus") == "Y"})
    return out


# 연간 실적 컨센서스 수집 대상 — 리포트가 지목한 3종목만(스코프 좁혀 QA 단순화, §후속 확대)
ANNUAL_FIN_CODES = {"005930", "000660", "005380"}


def parse_financials_annual(finance_info):
    """네이버 finance/annual 응답에서 연도별 매출·영업이익(억원)을 순서대로.
    각 항목: {year:'2026', rev:매출, op:영업이익, est:컨센서스추정여부}.
    구조적 sanity 게이트(운영규칙 0): 매출 결측/≤0 또는 영업이익>매출(불가능)인 연도는 폐기.
    컨센서스 값의 크기 자체는 손대지 않는다(벤더 실측)."""
    if not finance_info:
        return []
    titles = finance_info.get("trTitleList", [])
    rows = {r.get("title"): r.get("columns", {}) for r in finance_info.get("rowList", [])}
    rev_col = rows.get("매출액", {})
    op_col = rows.get("영업이익", {})
    out = []
    for t in titles:
        key = t.get("key") or ""
        rev = _to_int((rev_col.get(key) or {}).get("value"))
        op = _to_int((op_col.get(key) or {}).get("value"))
        if rev is None or rev <= 0:
            continue
        if op is not None and op > rev:
            continue
        out.append({"year": key[:4], "rev": rev, "op": op,
                    "est": t.get("isConsensus") == "Y"})
    return out


def _naver_supply5(code):
    """종목별 일별 투자자 순매수 수량(외국인·기관·개인). 실패 시 []."""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/trend"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"})
        rows = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return parse_supply5(rows) if isinstance(rows, list) else []
    except Exception as e:
        print(f"[snapshot] naver supply {code} 실패: {e}", file=sys.stderr)
        return []


def _naver_financials(code):
    """종목별 분기 매출·영업이익(억원, 컨센서스 추정 플래그 포함). 실패 시 []."""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/finance/quarter"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return parse_financials(data.get("financeInfo"))
    except Exception as e:
        print(f"[snapshot] naver finance {code} 실패: {e}", file=sys.stderr)
        return []


def _naver_financials_annual(code):
    """종목별 연간 매출·영업이익(억원, 컨센서스 플래그 포함). 실패 시 []."""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/finance/annual"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return parse_financials_annual(data.get("financeInfo"))
    except Exception as e:
        print(f"[snapshot] naver finance/annual {code} 실패: {e}", file=sys.stderr)
        return []


def _yf_closes(ticker):
    """yfinance 폴백(미국). 실패 시 []."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="400d").dropna(subset=["Close"])
        return [float(x) for x in hist["Close"].tolist()]
    except Exception as e:
        print(f"[snapshot] yfinance {ticker} 실패: {e}", file=sys.stderr)
        return []


def fetch_closes(symbol, market):
    """market='kr'|'us'. 토스 우선, 폴백 분기. 한국은 6자리 코드만."""
    closes = _toss_closes(symbol)
    if closes:
        return closes
    return _naver_closes(symbol) if market == "kr" else _yf_closes(symbol)


UNIVERSE_PATH = Path(__file__).parent / "config" / "stock_universe.json"
OUT_PATH = Path(__file__).parent.parent / "web" / "data" / "stocks-snapshot.json"


def load_universe():
    return json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))


def _build_one(symbol, name, sector, market):
    """종목 하나의 스냅샷 레코드를 만든다. (rec, bar_date) 튜플을 반환한다 —
    bar_date는 market='kr'일 때만 채워지는, change_pct의 closes[-1]에 대응하는 실제 봉 날짜다.
    실패 시 (None, None)."""
    vol = vol_avg20 = foreign = foreign_spark = None
    supply5 = financials = financials_annual = None
    bar_date = None
    if market == "kr":
        # 한국은 네이버 일봉 한 번으로 종가+거래량+외국인보유율 동시 수집(토스 IP 차단 우회)
        rows = _naver_day_rows(symbol)
        closes = [float(r["closePrice"]) for r in rows if r.get("closePrice")]
        bar_date = _last_bar_date(rows)
        vols = [r["accumulatedTradingVolume"] for r in rows if r.get("accumulatedTradingVolume") not in (None, _VOL_SENTINEL)]
        frates = [r["foreignRetentionRate"] for r in rows if r.get("foreignRetentionRate") is not None]
        if vols:
            vol = int(vols[-1])
            vol_avg20 = int(sum(vols[-20:]) / len(vols[-20:]))
        if frates:
            foreign = round(float(frates[-1]), 2)
            foreign_spark = [round(float(x), 2) for x in frates[-20:]]
        supply5 = _naver_supply5(symbol)        # 종목별 5일 순매수 수량
        financials = _naver_financials(symbol)  # 분기 매출·영업이익
        if symbol in ANNUAL_FIN_CODES:
            financials_annual = _naver_financials_annual(symbol)  # 연간 매출·영업이익(3종목)
    else:
        closes = fetch_closes(symbol, market)
    if len(closes) < 2:
        print(f"[snapshot] {symbol}({name}) 데이터 부족 → 생략", file=sys.stderr)
        return None, None
    hi, lo = wk52_high_low(closes)
    rec = {
        "name": name, "sector": sector,
        "close": closes[-1],
        "change_pct": change_pct(closes),
        "wk52_high": hi, "wk52_low": lo,
        "spark5": sparkline(closes, 5),
        "spark20": sparkline(closes, 20),
        "ma200": ma200(closes),
    }
    if vol is not None:
        rec["vol"] = vol
        rec["vol_avg20"] = vol_avg20
    if foreign is not None:
        rec["foreign_rate"] = foreign
        rec["foreign_spark"] = foreign_spark
    if supply5:
        rec["supply5"] = supply5
    if financials:
        rec["financials"] = financials
    if financials_annual:
        rec["financials_annual"] = financials_annual
    return rec, bar_date


def _build_etf(code, name):
    """ETF 거래량 수집(네이버 일봉). 최근 세션 거래량이 오버플로 센티넬이면 제외(현재 거래량 미상)."""
    rows = _naver_day_rows(code)
    if not rows:
        return None
    last_vol = rows[-1].get("accumulatedTradingVolume")
    if last_vol in (None, _VOL_SENTINEL):
        return None
    vols = [r["accumulatedTradingVolume"] for r in rows
            if r.get("accumulatedTradingVolume") not in (None, _VOL_SENTINEL)]
    closes = [float(r["closePrice"]) for r in rows if r.get("closePrice")]
    return {
        "name": name,
        "vol": int(last_vol),
        "vol_avg20": int(sum(vols[-20:]) / len(vols[-20:])),
        "change_pct": change_pct(closes),
    }


def build_snapshot():
    uni = load_universe()
    stocks, bellwethers, etfs = {}, {}, {}
    kr_bar_dates = []
    for e in uni.get("etfs", []):
        rec = _build_etf(e["code"], e["name"])
        if rec:
            etfs[e["code"]] = rec
        else:
            print(f"[snapshot] ETF {e['code']}({e['name']}) 거래량 무효 → 생략", file=sys.stderr)
    for key, sec in uni["sectors"].items():
        for s in sec["stocks"]:
            rec, bar_date = _build_one(s["code"], s["name"], key, "kr")
            if rec:
                stocks[s["code"]] = rec
                kr_bar_dates.append(bar_date)
        for b in sec.get("bellwethers", []):
            if b["t"] in bellwethers:
                continue
            rec, _ = _build_one(b["t"], b["name"], key, "us")
            if rec:
                bellwethers[b["t"]] = {"name": b["name"], "close": rec["close"],
                                       "change_pct": rec["change_pct"]}

    # session_date: 한국 종목들의 마지막 봉 날짜가 전부 일치할 때만 채택(§0 — 엇갈리면 생략).
    # 밤사이 브리지(fetch_data.fetch_overnight_bridge)가 이 값으로만 세션 정합성을 게이트한다.
    session_date = _reconcile_session_date(kr_bar_dates)
    if session_date is None:
        distinct = sorted({d for d in kr_bar_dates if d})
        if len(distinct) > 1:
            print(f"[snapshot] 종목별 마지막 봉 날짜가 엇갈림({distinct}) — session_date 생략", file=sys.stderr)
        else:
            print("[snapshot] 유효한 한국 종목 봉 날짜를 하나도 얻지 못함 — session_date 생략", file=sys.stderr)

    result = {
        "generated_at": datetime.now(KST).isoformat(),
        "stocks": stocks,
        "bellwethers": bellwethers,
        "etfs": etfs,
    }
    if session_date is not None:
        result["session_date"] = session_date
    return result


def main():
    snap = build_snapshot()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[snapshot] {len(snap['stocks'])}종목 + {len(snap['bellwethers'])}벨웨더 + {len(snap['etfs'])}ETF → {OUT_PATH}")


if __name__ == "__main__":
    main()
