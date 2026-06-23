# 종목 유니버스 일봉 → 시세·52주·스파크라인·MA200 스냅샷 빌드
#!/usr/bin/env python3
"""실행: python3 scripts/build_stocks_snapshot.py
   stock_universe.json의 ~48 한국 종목 + 섹터 벨웨더를 토스 캔들로 수집해
   web/data/stocks-snapshot.json 으로 저장한다. SERVICE_RULES 0번 준수."""
import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import toss_client as tc

KST = timezone(timedelta(hours=9))


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


def _naver_closes(code):
    """네이버 일봉 폴백(한국). 실패 시 []."""
    try:
        end = datetime.now().strftime("%Y%m%d") + "0000"
        start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d") + "0000"
        url = (f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
               f"?startDateTime={start}&endDateTime={end}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        rows = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return [float(r["closePrice"]) for r in rows if r.get("closePrice")]
    except Exception as e:
        print(f"[snapshot] naver {code} 실패: {e}", file=sys.stderr)
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
    closes = fetch_closes(symbol, market)
    if len(closes) < 2:
        print(f"[snapshot] {symbol}({name}) 데이터 부족 → 생략", file=sys.stderr)
        return None
    hi, lo = wk52_high_low(closes)
    return {
        "name": name, "sector": sector,
        "close": closes[-1],
        "change_pct": change_pct(closes),
        "wk52_high": hi, "wk52_low": lo,
        "spark5": sparkline(closes, 5),
        "spark20": sparkline(closes, 20),
        "ma200": ma200(closes),
    }


def build_snapshot():
    uni = load_universe()
    stocks, bellwethers = {}, {}
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
    }


def main():
    snap = build_snapshot()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[snapshot] {len(snap['stocks'])}종목 + {len(snap['bellwethers'])}벨웨더 → {OUT_PATH}")


if __name__ == "__main__":
    main()
