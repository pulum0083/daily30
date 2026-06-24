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
    vol = vol_avg20 = foreign = foreign_spark = None
    if market == "kr":
        # 한국은 네이버 일봉 한 번으로 종가+거래량+외국인보유율 동시 수집(토스 IP 차단 우회)
        rows = _naver_day_rows(symbol)
        closes = [float(r["closePrice"]) for r in rows if r.get("closePrice")]
        vols = [r["accumulatedTradingVolume"] for r in rows if r.get("accumulatedTradingVolume") not in (None, _VOL_SENTINEL)]
        frates = [r["foreignRetentionRate"] for r in rows if r.get("foreignRetentionRate") is not None]
        if vols:
            vol = int(vols[-1])
            vol_avg20 = int(sum(vols[-20:]) / len(vols[-20:]))
        if frates:
            foreign = round(float(frates[-1]), 2)
            foreign_spark = [round(float(x), 2) for x in frates[-20:]]
    else:
        closes = fetch_closes(symbol, market)
    if len(closes) < 2:
        print(f"[snapshot] {symbol}({name}) 데이터 부족 → 생략", file=sys.stderr)
        return None
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
    return rec


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
    for e in uni.get("etfs", []):
        rec = _build_etf(e["code"], e["name"])
        if rec:
            etfs[e["code"]] = rec
        else:
            print(f"[snapshot] ETF {e['code']}({e['name']}) 거래량 무효 → 생략", file=sys.stderr)
    for key, sec in uni["sectors"].items():
        for s in sec["stocks"]:
            rec = _build_one(s["code"], s["name"], key, "kr")
            if rec:
                stocks[s["code"]] = rec
        for b in sec.get("bellwethers", []):
            if b["t"] in bellwethers:
                continue
            rec = _build_one(b["t"], b["name"], key, "us")
            if rec:
                bellwethers[b["t"]] = {"name": b["name"], "close": rec["close"],
                                       "change_pct": rec["change_pct"]}
    return {
        "generated_at": datetime.now(KST).isoformat(),
        "stocks": stocks,
        "bellwethers": bellwethers,
        "etfs": etfs,
    }


def main():
    snap = build_snapshot()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[snapshot] {len(snap['stocks'])}종목 + {len(snap['bellwethers'])}벨웨더 + {len(snap['etfs'])}ETF → {OUT_PATH}")


if __name__ == "__main__":
    main()
