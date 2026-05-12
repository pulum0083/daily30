# 코스피 마감 시황 데이터 수집 (지수 + 섹터 + 급등주 TOP3)
#!/usr/bin/env python3
"""
KOSPI 마감 시황 데이터를 수집한다.

수집 항목:
  - KOSPI / KOSDAQ / 원달러 마감 지수 (yfinance)
  - 미국 프리마켓 선물 (NQ, ES, WTI)
  - 섹터별 등락률 (네이버 증권 크롤링)
  - 당일 급등주 TOP 3 (네이버 증권 크롤링)

Usage:
    python3 scripts/fetch_closing_kospi.py
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")

NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


# ─────────────────────────────────────────────────────────────────────────────
# yfinance 래퍼 (재시도 포함)
# ─────────────────────────────────────────────────────────────────────────────

def _yf_history(ticker: str, retries: int = 3, **kwargs):
    import yfinance as yf
    import pandas as pd
    last_exc = None
    for attempt in range(retries):
        try:
            hist = yf.Ticker(ticker).history(**kwargs)
            if not hist.empty:
                return hist
        except Exception as e:
            last_exc = e
        if attempt < retries - 1:
            delay = 2 ** attempt
            print(f"[fetch_closing] {ticker} retry {attempt+1} in {delay}s", file=sys.stderr)
            time.sleep(delay)
    if last_exc:
        print(f"[fetch_closing] {ticker} failed: {last_exc}", file=sys.stderr)
    import pandas as pd
    return pd.DataFrame()


def get_closing_price(ticker: str) -> dict:
    """마감 종가·등락률을 반환한다."""
    hist = _yf_history(ticker, period="5d", interval="1d")
    if len(hist) < 2:
        return {"error": "insufficient data"}
    closes = hist["Close"].dropna()
    price = float(closes.iloc[-1])
    prev  = float(closes.iloc[-2])
    if prev == 0:
        return {"error": "zero prev close"}
    chg_pct = round((price - prev) / prev * 100, 2)
    chg_abs = round(price - prev, 2)
    return {"price": round(price, 2), "change_pct": chg_pct, "change_abs": chg_abs}


def get_volume(ticker: str) -> int:
    """당일 거래량을 반환한다."""
    hist = _yf_history(ticker, period="2d", interval="1d")
    if hist.empty:
        return 0
    return int(hist["Volume"].iloc[-1])


# ─────────────────────────────────────────────────────────────────────────────
# 네이버 증권 — 급등주 TOP 3
# ─────────────────────────────────────────────────────────────────────────────

class _RiseTableParser(HTMLParser):
    """네이버 증권 상승률 순위 페이지에서 종목명·등락률·현재가를 파싱한다."""

    def __init__(self):
        super().__init__()
        self.stocks = []
        self._in_td = False
        self._cls = ""
        self._cur: dict = {}
        self._buf = ""
        self._collecting = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "td":
            cls = attrs.get("class", "")
            self._in_td = True
            self._cls = cls
            self._buf = ""
        if tag == "a" and "name" in attrs:
            if self._cur.get("name"):
                pass
            self._cur.setdefault("_link_name", attrs.get("title", ""))

    def handle_data(self, data):
        if self._in_td:
            self._buf += data.strip()

    def handle_endtag(self, tag):
        if tag == "td" and self._in_td:
            val = self._buf.strip()
            cls = self._cls
            if "name" in cls and val:
                if self._cur:
                    self.stocks.append(self._cur)
                self._cur = {"name": val}
            elif "rate" in cls and val:
                self._cur["change_pct"] = val
            elif "price" in cls and val and "change_pct" in self._cur:
                if "price" not in self._cur:
                    self._cur["price"] = val
            self._in_td = False
            self._buf = ""
        if tag == "table" and self.stocks:
            if self._cur and "name" in self._cur:
                self.stocks.append(self._cur)
                self._cur = {}


def fetch_top_gainers(limit: int = 3) -> list[dict]:
    """네이버 증권 코스피 등락률 순위 1~3위를 반환한다.

    Returns list of {"name": str, "change_pct": str, "price": str}
    """
    url = "https://finance.naver.com/sise/sise_rise.naver?sosok=0"
    try:
        req = urllib.request.Request(url, headers=NAVER_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("euc-kr", errors="replace")
    except Exception as e:
        print(f"[fetch_closing] top gainers fetch failed: {e}", file=sys.stderr)
        return []

    # 간단한 정규식 파싱 — 테이블 구조가 복잡해 태그 파서 대신 정규식 사용
    import re
    result = []
    # 패턴: 종목 링크 → 이름, 바로 뒤에 등락률 셀
    pattern = re.compile(
        r'<a[^>]+href="/item/main[^"]+"\s*>([^<]+)</a>'   # 종목명
        r'.*?'
        r'<td[^>]*class="[^"]*rate[^"]*"[^>]*>\s*'        # 등락률 셀
        r'<span[^>]*>\+?([\d.]+)%</span>',                 # 등락률 값
        re.DOTALL,
    )
    price_pattern = re.compile(
        r'<td[^>]*class="[^"]*number[^"]*"[^>]*>\s*([\d,]+)\s*</td>'
    )

    # 종목별 블록 분리 (tr 단위)
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    name_pat   = re.compile(r'<a[^>]+href="/item/main[^"]+"\s*title="([^"]+)"')
    rate_pat   = re.compile(r'class="[^"]*rate[^"]*"[^>]*>\s*<span[^>]*>\+?([\d.]+)%')
    price_pat  = re.compile(r'class="[^"]*number[^"]*"[^>]*>\s*([\d,]+)\s*</td>')

    for m in tr_pattern.finditer(html):
        row = m.group(1)
        name_m  = name_pat.search(row)
        rate_m  = rate_pat.search(row)
        price_m = price_pat.search(row)
        if name_m and rate_m and price_m:
            result.append({
                "name":       name_m.group(1).strip(),
                "change_pct": f"+{rate_m.group(1)}%",
                "price":      price_m.group(1).strip() + "원",
            })
        if len(result) >= limit:
            break

    print(f"[fetch_closing] top gainers: {[r['name'] for r in result]}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 네이버 증권 — 섹터 성과
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_IDS = {
    "반도체":       "G25",
    "IT·소프트웨어": "G26",
    "바이오·헬스케어": "G27",
    "자동차":       "G35",
    "금융·은행":    "G40",
    "에너지·화학":  "G14",
    "철강·소재":    "G15",
}


def fetch_sector_performance() -> list[dict]:
    """네이버 그룹별 시세에서 섹터 등락률을 가져온다.

    Returns list of {"name": str, "change_pct": float}
    """
    url = "https://finance.naver.com/sise/sise_group.naver"
    try:
        req = urllib.request.Request(url, headers=NAVER_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("euc-kr", errors="replace")
    except Exception as e:
        print(f"[fetch_closing] sector fetch failed: {e}", file=sys.stderr)
        return []

    import re
    result = []
    # 각 그룹 행: 그룹명 + 등락률
    row_pat = re.compile(
        r'<a[^>]+href="/sise/sise_group_detail\.naver\?[^"]*"[^>]*>([^<]+)</a>'
        r'.*?'
        r'<td[^>]*>\s*<span[^>]*class="([^"]*)"[^>]*>([\d.]+)</span>',
        re.DOTALL,
    )
    for m in row_pat.finditer(html):
        name = m.group(1).strip()
        cls  = m.group(2)
        val  = float(m.group(3))
        chg  = val if "up" in cls or "red" in cls else -val
        result.append({"name": name, "change_pct": round(chg, 2)})

    # SECTOR_IDS에 없는 섹터는 제외하고, 있는 섹터만 순서대로 반환
    sector_names = list(SECTOR_IDS.keys())
    mapped = {r["name"]: r["change_pct"] for r in result}

    final = []
    for sname in sector_names:
        if sname in mapped:
            final.append({"name": sname, "change_pct": mapped[sname]})
        # 데이터 없으면 skip

    # 데이터가 너무 적으면 raw 결과 상위 7개 반환
    if len(final) < 3 and result:
        final = sorted(result, key=lambda x: x["change_pct"], reverse=True)[:7]

    print(f"[fetch_closing] sectors: {len(final)}개")
    return final


# ─────────────────────────────────────────────────────────────────────────────
# 투자자별 순매수 (네이버, 기존 fetch_data.py 로직 재사용)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_investor_trading() -> dict:
    """당일 외국인·기관·개인 순매수를 반환한다."""
    kst_now  = datetime.now(KST)
    date_str = kst_now.strftime("%Y%m%d")

    apis = [
        f"https://api.stock.naver.com/api/index/KOSPI/investorTrend?bizDate={date_str}",
        f"https://m.stock.naver.com/api/index/KOSPI/investorTrend?bizDate={date_str}",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Mobile Safari/537.36",
        "Referer": "https://m.stock.naver.com/",
        "Accept": "application/json",
    }
    INVESTOR_MAP = {
        "FO": "foreign", "OT": "institution", "PE": "individual",
        "외국인": "foreign", "기관": "institution", "개인": "individual",
    }
    for url in apis:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            rows = data if isinstance(data, list) else data.get("investorList", data.get("list", []))
            result: dict = {"date": date_str}
            for row in rows:
                inv = row.get("investorType") or row.get("tp") or row.get("type") or row.get("name") or ""
                key = INVESTOR_MAP.get(inv)
                if not key:
                    continue
                net = row.get("netBuyAmount") or row.get("net") or row.get("netBuy") or 0
                result[key] = {"net": int(str(net).replace(",", "") or 0)}
            if len(result) > 1:
                return result
        except Exception as e:
            print(f"[fetch_closing] investor trading error: {e}", file=sys.stderr)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 장중 5분봉 (9:00~15:20 KST)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_intraday_kospi() -> dict:
    """당일 KOSPI 5분봉 데이터를 반환한다.

    Returns:
        {
          "prices":    [float, ...],   # 9:00~15:20 종가 리스트
          "high":      float,
          "high_idx":  int,
          "low":       float,
          "low_idx":   int,
        }
    """
    hist = _yf_history("^KS11", period="1d", interval="5m")
    if hist is None or hist.empty:
        print("[fetch_closing] intraday: no data", file=sys.stderr)
        return {}

    closes = hist["Close"].dropna()
    if len(closes) == 0:
        return {}

    # KST 기준 09:00~15:20 구간만 필터
    try:
        idx = closes.index.tz_convert(KST)
        mask = (idx.hour > 9) | ((idx.hour == 9) & (idx.minute >= 0))
        mask &= (idx.hour < 15) | ((idx.hour == 15) & (idx.minute <= 20))
        closes = closes[mask]
    except Exception:
        pass  # 타임존 변환 실패 시 전체 사용

    if len(closes) == 0:
        return {}

    prices = [round(float(p), 2) for p in closes.tolist()]
    high_val = max(prices)
    low_val  = min(prices)
    print(f"[fetch_closing] intraday: {len(prices)}봉, 고점={high_val}, 저점={low_val}")
    return {
        "prices":   prices,
        "high":     high_val,
        "high_idx": prices.index(high_val),
        "low":      low_val,
        "low_idx":  prices.index(low_val),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 전체 수집
# ─────────────────────────────────────────────────────────────────────────────

def fetch_closing_data() -> dict:
    print("[fetch_closing] 코스피 마감 데이터 수집 시작...")

    print("[fetch_closing]   → 지수 (KOSPI / KOSDAQ / USD/KRW)")
    kospi  = get_closing_price("^KS11")
    kosdaq = get_closing_price("^KQ11")
    usdkrw = get_closing_price("USDKRW=X")

    # KOSPI 거래대금 근사 (거래량 × 평균단가 — 정확하지 않으나 참고용)
    kospi_vol = get_volume("^KS11")

    print("[fetch_closing]   → 프리마켓 선물")
    nq_fut  = get_closing_price("NQ=F")
    sp_fut  = get_closing_price("ES=F")
    wti     = get_closing_price("CL=F")

    print("[fetch_closing]   → 섹터 성과 (네이버)")
    sectors = fetch_sector_performance()

    print("[fetch_closing]   → 급등주 TOP 3 (네이버)")
    top_gainers = fetch_top_gainers(limit=3)

    print("[fetch_closing]   → 장중 5분봉 (스파크라인)")
    intraday = fetch_intraday_kospi()

    print("[fetch_closing]   → 투자자별 순매수")
    investor = fetch_investor_trading()

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "kospi-close",
        "indices": {
            "kospi":  kospi,
            "kosdaq": kosdaq,
            "usdkrw": usdkrw,
            "kospi_volume": kospi_vol,
        },
        "futures": {
            "nq":  nq_fut,
            "sp":  sp_fut,
            "wti": wti,
        },
        "sectors": sectors,
        "top_gainers": top_gainers,
        "investor_trading": investor,
        "intraday": intraday,
    }

    out = DATA_DIR / "latest_kospi_close.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_closing] 저장 완료 → {out}")
    return data


if __name__ == "__main__":
    fetch_closing_data()
