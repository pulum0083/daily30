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
import re
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


def _fetch_naver_index(code: str) -> dict:
    """네이버 모바일 API에서 코스피/코스닥 실시간 종가를 반환한다.

    Yahoo(yfinance)는 한국 지수에 15~30분 지연이 있어 15:40 시점에 종가가 반영되지 않음.
    네이버는 동시호가 마감(15:30) 직후 closePrice가 확정되므로 우선 사용한다.
    """
    url = f"https://m.stock.naver.com/api/index/{code}/basic"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
        price = float(payload["closePrice"].replace(",", ""))
        abs_chg = float(payload["compareToPreviousClosePrice"].replace(",", ""))
        ratio = float(payload["fluctuationsRatio"].replace(",", ""))
        # compareToPreviousPrice.code: 2=상승, 5=하락, 3=보합, 1=상한, 4=하한
        direction = (payload.get("compareToPreviousPrice") or {}).get("code", "3")
        sign = 1 if direction in ("1", "2") else (-1 if direction in ("4", "5") else 0)
        return {
            "price": round(price, 2),
            "change_pct": round(sign * abs(ratio), 2),
            "change_abs": round(sign * abs(abs_chg), 2),
        }
    except Exception as e:
        print(f"[fetch_closing] naver index {code} failed: {e}", file=sys.stderr)
        return {}


def _fetch_naver_usdkrw() -> dict:
    """USD/KRW 종가·등락률.
    1차: Toss Open API (공식, 안정적)
    2차: manana.kr
    3차: fawazahmed0 CDN
    4차: 네이버 모바일 API
    """
    # 1차: Toss Open API
    try:
        try:
            import scripts.toss_client as tc
        except ImportError:
            import toss_client as tc
        price = tc.get_exchange_rate("USD", "KRW")
        if price:
            return {"price": round(price, 2), "change_pct": 0.0, "change_abs": 0.0}
    except Exception as e:
        print(f"[fetch_closing] Toss USDKRW failed: {e}", file=sys.stderr)

    # 2차: manana.kr
    try:
        req = urllib.request.Request(
            "https://api.manana.kr/exchange/rate/KRW/USD.json",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            rows = json.loads(resp.read())
        if rows and isinstance(rows, list) and rows[0].get("rate"):
            price = float(rows[0]["rate"])
            prev = float(rows[1]["rate"]) if len(rows) >= 2 and rows[1].get("rate") else None
            chg_abs = round(price - prev, 2) if prev else 0.0
            chg_pct = round((price - prev) / prev * 100, 2) if prev else 0.0
            return {"price": round(price, 2), "change_pct": chg_pct, "change_abs": chg_abs}
    except Exception as e:
        print(f"[fetch_closing] manana.kr USDKRW failed: {e}", file=sys.stderr)

    # 2차: fawazahmed0 CDN
    try:
        req = urllib.request.Request(
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        rate = data.get("usd", {}).get("krw")
        if rate:
            return {"price": round(float(rate), 2), "change_pct": 0.0, "change_abs": 0.0}
    except Exception as e:
        print(f"[fetch_closing] fawazahmed0 USDKRW failed: {e}", file=sys.stderr)

    # 3차: 네이버 모바일 API
    try:
        url = "https://m.stock.naver.com/front-api/marketIndex/prices?reutersCode=FX_USDKRW&category=exchange&pageSize=10&page=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
        rows = payload.get("result") or []
        if len(rows) >= 2:
            price = float(rows[0]["closePrice"].replace(",", ""))
            prev  = float(rows[1]["closePrice"].replace(",", ""))
            chg_abs = round(price - prev, 2)
            chg_pct = round((price - prev) / prev * 100, 2) if prev else 0.0
            return {"price": round(price, 2), "change_pct": chg_pct, "change_abs": chg_abs}
    except Exception as e:
        print(f"[fetch_closing] naver USDKRW failed: {e}", file=sys.stderr)

    return {}


def get_closing_price(ticker: str) -> dict:
    """마감 종가·등락률을 반환한다.

    한국 지수·환율은 네이버 실시간 API를 우선 사용하고, 실패 시 yfinance(지연 있음)로 폴백한다.
    그 외 (NQ=F / ES=F / CL=F 등) 해외 티커는 yfinance만 사용.
    """
    naver_first = {
        "^KS11":   lambda: _fetch_naver_index("KOSPI"),
        "^KQ11":   lambda: _fetch_naver_index("KOSDAQ"),
        "USDKRW=X": _fetch_naver_usdkrw,
    }
    if ticker in naver_first:
        result = naver_first[ticker]()
        if result and "price" in result:
            return result
        print(f"[fetch_closing] {ticker} naver miss → yfinance fallback", file=sys.stderr)

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

    import re
    result = []

    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    name_pat   = re.compile(r'<a[^>]+href="/item/main[^"]+"\s*class="tltle">([^<]+)</a>')
    rate_pat   = re.compile(r'\+(\d+\.\d+)%')
    price_pat  = re.compile(r'<td\s+class="number">\s*([\d,]+)\s*</td>')

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


def fetch_sector_top_stocks(detail_path: str, limit: int = 3) -> list[dict]:
    """네이버 테마 상세 페이지에서 등락률 상위 종목을 반환한다.

    Args:
        detail_path: "/sise/sise_group_detail.naver?type=theme&no=591" 형태
    Returns:
        [{"name": str, "change_pct": float}, ...]
    """
    import re
    url = f"https://finance.naver.com{detail_path}"
    try:
        req = urllib.request.Request(url, headers=NAVER_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("euc-kr", errors="replace")
    except Exception as e:
        print(f"[fetch_closing] sector detail fetch failed ({detail_path}): {e}", file=sys.stderr)
        return []

    name_pat = re.compile(r'<a href="/item/main\.naver\?code=\d+">([^<]+)</a>')
    pct_pat  = re.compile(r'<span class="tah p11 (red\d+|blu\d+|nv01)">\s*([+\-]?[\d.]+)%\s*</span>')

    # 종목명 단위로 row를 잘라낸 뒤 그 뒤 1500자 안에서 등락률을 잡아낸다.
    stocks: list[dict] = []
    seen: set[str] = set()
    for m in name_pat.finditer(html):
        name = m.group(1).strip()
        if name in seen:
            continue
        seen.add(name)
        chunk = html[m.end():m.end() + 1500]
        pct_matches = pct_pat.findall(chunk)
        if pct_matches:
            color, val = pct_matches[0]
            try:
                pct = float(val)
                if color.startswith("blu"):
                    pct = -abs(pct)
                stocks.append({"name": name, "change_pct": round(pct, 2)})
            except ValueError:
                continue

    stocks.sort(key=lambda x: x["change_pct"], reverse=True)
    return stocks[:limit]


def fetch_sector_performance() -> list[dict]:
    """네이버 그룹별 시세에서 섹터 등락률과 섹터별 상위 종목을 가져온다.

    Returns list of {"name": str, "change_pct": float, "stocks": [{"name", "change_pct"}, ...]}
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
    tr_pat = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
    link_pat = re.compile(r'<a[^>]+href="(/sise/sise_group_detail\.naver\?[^"]*)">([^<]+)</a>')
    rate_pat = re.compile(r'<span[^>]*class="[^"]*\b(red|blu)\d*[^"]*"[^>]*>\s*\+?([\d.]+)%\s*</span>')

    for m in tr_pat.finditer(html):
        row = m.group(1)
        link_m = link_pat.search(row)
        rate_m = rate_pat.search(row)
        if link_m and rate_m:
            href = link_m.group(1).replace("&amp;", "&")
            name = link_m.group(2).strip()
            color = rate_m.group(1)
            val = float(rate_m.group(2))
            chg = val if color == "red" else -val
            result.append({
                "name": name,
                "change_pct": round(chg, 2),
                "_href": href,
            })

    # 등락률 절대값 기준으로 영향이 큰 섹터 상위 5개 반환
    result.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    final = result[:5]

    # 각 섹터의 상위 종목 2~3개 추가
    for sec in final:
        sec["stocks"] = fetch_sector_top_stocks(sec.pop("_href"), limit=3)
        time.sleep(0.3)  # 네이버 부담 줄이기

    print(f"[fetch_closing] sectors: {len(final)}개 (종목 포함)")
    return final


# ─────────────────────────────────────────────────────────────────────────────
# 투자자별 순매수 (네이버, 기존 fetch_data.py 로직 재사용)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_investor_trading() -> dict:
    """당일 외국인·기관·개인 순매수를 반환한다. 네이버 증권 PC 페이지 HTML 파싱."""
    kst_now  = datetime.now(KST)
    date_str = kst_now.strftime("%Y%m%d")
    try:
        url = "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("euc-kr", errors="ignore")
        # "개인<br>..+N,NNN억...외국인<br>...-N,NNN억...기관<br>...+N,NNN억" 패턴
        m = re.search(
            r"개인<br>.*?([+-][0-9,]+).*?외국인<br>.*?([+-][0-9,]+).*?기관<br>.*?([+-][0-9,]+)",
            text, re.DOTALL
        )
        if not m:
            print("[fetch_closing] investor trading: pattern not found", file=sys.stderr)
            return {}
        def _parse_eok(s: str) -> int:
            # 억원 단위 → 백만원 단위 (×100) 로 변환해 기존 구조와 통일
            return int(s.replace(",", "").replace("+", "")) * 100
        individual = _parse_eok(m.group(1))
        foreign    = _parse_eok(m.group(2))
        institution= _parse_eok(m.group(3))
        result = {
            "date": date_str,
            "foreign":     {"net": foreign},
            "institution": {"net": institution},
            "individual":  {"net": individual},
        }
        print(f"[fetch_closing] investor trading ({date_str}): foreign={foreign:+,} individual={individual:+,} institution={institution:+,} (백만원)")
        return result
    except Exception as e:
        print(f"[fetch_closing] investor trading naver error: {e}", file=sys.stderr)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 장중 5분봉 (9:00~15:20 KST)
# ─────────────────────────────────────────────────────────────────────────────

def _despike_intraday(prices: list, threshold: float = 0.015) -> list:
    """장중 5분봉의 반전 스파이크(yfinance 장 시작 오틱)를 이웃값으로 보정한다.

    이웃 봉 대비 threshold(기본 1.5%) 이상 같은 방향으로 튀었다가 곧바로
    되돌아오는 단일 봉을 이웃 평균(내부)·이웃값(양 끝)으로 대체한다.
    좌→우 순차 적용이라 장 시작부의 연속 오틱도 직전 보정값을 기준으로 흡수된다.
    """
    n = len(prices)
    if n < 3:
        return list(prices)
    out = list(prices)
    for i in range(n):
        if i == 0:
            nb = out[1]
            if nb and abs(out[0] - nb) / nb > threshold:
                out[0] = nb
        elif i == n - 1:
            nb = out[i - 1]
            if nb and abs(out[i] - nb) / nb > threshold:
                out[i] = nb
        else:
            prev_, next_ = out[i - 1], out[i + 1]
            if not prev_ or not next_:
                continue
            dprev = (out[i] - prev_) / prev_
            dnext = (out[i] - next_) / next_
            if abs(dprev) > threshold and abs(dnext) > threshold and (dprev > 0) == (dnext > 0):
                out[i] = round((prev_ + next_) / 2, 2)
    return out


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
    prices = _despike_intraday(prices)   # 장 시작 오틱 등 반전 스파이크 보정
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
# 코스피 거래대금
# ─────────────────────────────────────────────────────────────────────────────

def fetch_trade_amount() -> dict:
    """코스피 당일 거래대금을 반환한다. (억원 단위)

    네이버 폴링 API의 accumulatedTradingValueRaw(원 단위)를 사용한다.
    """
    url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
        datas = payload.get("datas", [])
        if not datas:
            return {}
        raw = datas[0].get("accumulatedTradingValueRaw", "")
        if not raw:
            return {}
        val = float(str(raw).replace(",", ""))
        eok = round(val / 1e8)
        if eok <= 0:
            return {}
        jo = eok // 10000
        rem = eok % 10000
        formatted = f"{jo}조 {rem:,}억원" if jo > 0 else f"{eok:,}억원"
        print(f"[fetch_closing] 거래대금: {formatted}")
        return {"amount_eok": eok, "formatted": formatted}
    except Exception as e:
        print(f"[fetch_closing] trade amount failed: {e}", file=sys.stderr)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 시장 폭 (상한가·하한가·신고가·신저가·상승·하락·보합 종목 수)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_market_breadth() -> dict:
    """코스피 시장 폭 데이터를 반환한다. 네이버 증권 메인 페이지 HTML 파싱."""
    try:
        url = "https://finance.naver.com/sise/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("euc-kr", errors="ignore")
        # 등락종목 섹션: uup(상한가) / up(상승) / noc(보합) / dn(하락) / ddn(하한가)
        def _extract(cls: str) -> int:
            m = re.search(rf'class="{cls}"[^>]*>\s*<a[^>]*>([0-9,]+)<', text)
            return int(m.group(1).replace(",", "")) if m else 0
        upper_limit = _extract("uup")
        up          = _extract("up")
        unchanged   = _extract("noc")
        # 하락/하한가는 하락 section에서 파싱
        dn_m  = re.search(r'class="dn"[^>]*>\s*<a[^>]*>([0-9,]+)<', text)
        ddn_m = re.search(r'class="ddn"[^>]*>\s*<a[^>]*>([0-9,]+)<', text)
        down        = int(dn_m.group(1).replace(",", "")) if dn_m else 0
        lower_limit = int(ddn_m.group(1).replace(",", "")) if ddn_m else 0
        if up == 0 and down == 0:
            print("[fetch_closing] market breadth: parsing failed", file=sys.stderr)
            return {}
        result = {
            "up": up, "down": down, "unchanged": unchanged,
            "upper_limit": upper_limit, "lower_limit": lower_limit,
            "new_high": 0, "new_low": 0,
        }
        print(f"[fetch_closing] 시장 폭: 상승 {up} / 하락 {down} / 상한가 {upper_limit}")
        return result
    except Exception as e:
        print(f"[fetch_closing] market breadth naver error: {e}", file=sys.stderr)
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# 거래대금 급증 + 수급 동반 종목 (외국인·기관 동시 순매수)
# ─────────────────────────────────────────────────────────────────────────────
# 데이터 제약: KRX 종목별 순매수 '금액' 소스가 막혀 있어(LOGOUT), 네이버 종목별
# 일별 순매매 '수량'에 종가를 곱한 근사 금액(억원)을 사용한다.

DPICK_ETF_KEYWORDS = ("KODEX", "TIGER", "KOSEF", "ARIRANG", "KBSTAR", "HANARO",
                      "PLUS", "RISE", "ACE ", "SOL ", "TIMEFOLIO", "레버리지", "인버스", "선물")


def _dpick_num(cell: str) -> float:
    s = re.sub(r"<[^>]+>", "", cell).strip().replace(",", "").replace("%", "").replace("+", "")
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return 0


def _fetch_frgn_daily(code: str) -> list:
    """종목별 외국인·기관 일별 순매매(수량) — 네이버 item/frgn. 최신순 행 리스트."""
    url = f"https://finance.naver.com/item/frgn.naver?code={code}"
    try:
        req = urllib.request.Request(url, headers=NAVER_HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("euc-kr", errors="replace")
    except Exception:
        return []
    rows = []
    for r in re.split(r"</tr>", html):
        if "gray03" not in r:
            continue
        date_m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", r)
        if not date_m:
            continue
        cells = re.findall(r'<td[^>]*class="num"[^>]*>(.*?)</td>', r, re.DOTALL)
        if len(cells) >= 6:
            rows.append({
                "date": f"{date_m.group(1)}-{date_m.group(2)}-{date_m.group(3)}",
                "close": _dpick_num(cells[0]),   # 종가
                "chg":   _dpick_num(cells[2]),   # 등락률(%)
                "vol":   _dpick_num(cells[3]),   # 거래량(주)
                "inst":  _dpick_num(cells[4]),   # 기관 순매매량(주)
                "frgn":  _dpick_num(cells[5]),   # 외국인 순매매량(주)
            })
    return rows


def fetch_dpick(universe: int = 20, limit: int = 3, min_mult: float = 1.5) -> list:
    """거래대금 급증 × 외국인·기관 동시 순매수 종목을 반환한다.

    universe(코스피 거래량 상위)에서 ETF를 제외하고, 각 종목의 일별 외국인·기관
    순매매로 (ⓐ거래대금이 20일 평균 대비 min_mult배 이상 급증, ⓑ외국인·기관 동시
    순매수)를 만족하는 종목을 거래대금 순으로 선별한다.
    """
    url = "https://finance.naver.com/sise/sise_quant.naver?sosok=0"  # 코스피 거래량 상위
    try:
        req = urllib.request.Request(url, headers=NAVER_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("euc-kr", errors="replace")
    except Exception as e:
        print(f"[fetch_closing] dpick universe fetch failed: {e}", file=sys.stderr)
        return []

    pairs = re.findall(r'/item/main\.naver\?code=(\d{6})"[^>]*class="tltle">([^<]+)</a>', html)
    cand = [(c, n.strip()) for c, n in pairs
            if not any(k in n for k in DPICK_ETF_KEYWORDS)][:universe]

    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    picks = []
    for code, name in cand:
        rows = _fetch_frgn_daily(code)
        if not rows:
            continue
        today = rows[0]
        # 당일 데이터가 아직 올라오지 않은 경우(어제 데이터) → 스킵
        if today.get("date") != today_str:
            print(f"[fetch_closing] dpick {name}({code}): 최신 행={today.get('date')} ≠ 오늘={today_str} → 스킵")
            continue
        close = today["close"]
        if close <= 0:
            continue
        tv = today["vol"] * close / 1e8                          # 당일 거래대금(억)
        recent = rows[:20]
        avg = sum(x["vol"] * x["close"] for x in recent) / len(recent) / 1e8
        mult = tv / avg if avg else 0
        frgn_eok = today["frgn"] * close / 1e8
        inst_eok = today["inst"] * close / 1e8
        if frgn_eok > 0 and inst_eok > 0 and mult >= min_mult:
            picks.append({
                "name": name, "code": code,
                "change_pct": round(today["chg"], 2),
                "trade_value_eok": round(tv),
                "trade_mult": round(mult, 1),
                "frgn_eok": round(frgn_eok),
                "inst_eok": round(inst_eok),
            })
    picks.sort(key=lambda p: -p["trade_value_eok"])
    picks = picks[:limit]
    print(f"[fetch_closing] dpick: {[p['name'] for p in picks]}")
    return picks


# ─────────────────────────────────────────────────────────────────────────────
# 코스피 200 시총 상위 10종목
# ─────────────────────────────────────────────────────────────────────────────

def fetch_kospi200_top10() -> list:
    """코스피 200 시총 상위 10종목을 반환한다. 네이버 marketValue API 사용."""
    url = "https://m.stock.naver.com/api/stocks/marketValue?market=KS&size=10"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
        stocks = payload.get("stocks", [])
        result = []
        for i, s in enumerate(stocks[:10], 1):
            code = s.get("compareToPreviousPrice", {}).get("code", "3")
            ratio = float(s.get("fluctuationsRatio", "0") or "0")
            if code == "2":
                chg_disp = f"▲ +{ratio:.2f}%"
                cls = "up"
            elif code == "5":
                chg_disp = f"▼ {ratio:.2f}%"
                cls = "down"
            else:
                chg_disp = "0.00%"
                cls = "flat"
            result.append({
                "rank": i, "name": s.get("stockName", ""),
                "price": s.get("closePrice", ""), "change_pct": chg_disp, "cls": cls,
            })
        print(f"[fetch_closing] KOSPI200 TOP10: {len(result)}종목")
        return result
    except Exception as e:
        print(f"[fetch_closing] KOSPI200 top10 naver error: {e}", file=sys.stderr)
    return []


# ─────────────────────────────────────────────────────────────────────────────
# 전체 수집
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ai_semicon_stocks() -> list:
    """AI 반도체 대표 종목 (KRX 2개 + US 3개) 현재가·등락률을 반환한다."""
    from pykrx import stock as krx
    kst_now  = datetime.now(KST)
    date_str = kst_now.strftime("%Y%m%d")

    result = []

    # 국내 종목: 삼성전자, SK하이닉스
    krx_stocks = [("005930", "삼성전자", "🇰🇷"), ("000660", "SK하이닉스", "🇰🇷")]
    for code, name, flag in krx_stocks:
        try:
            df = krx.get_market_ohlcv(date_str, date_str, code)
            if df.empty:
                continue
            price = int(df["종가"].iloc[0])
            chg   = float(df["등락률"].iloc[0])
            cls   = "up" if chg > 0 else ("down" if chg < 0 else "neutral")
            arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "")
            result.append({
                "name": name, "flag": flag,
                "price": f"{price:,}",
                "chg_pct": f"{arrow} {abs(chg):.2f}%",
                "cls": cls,
            })
        except Exception as e:
            print(f"[fetch_closing] ai_semicon {name}: {e}", file=__import__("sys").stderr)

    # 해외 종목: Micron, Intel, AMD (전날 종가 기준 — 한국 마감 시 미국 장 미개장)
    us_stocks = [("MU", "Micron", "🇺🇸"), ("INTC", "Intel", "🇺🇸"), ("AMD", "AMD", "🇺🇸")]
    for ticker, name, flag in us_stocks:
        try:
            hist = _yf_history(ticker, period="2d", interval="1d")
            if hist is None or hist.empty:
                continue
            row   = hist.iloc[-1]
            price = float(row["Close"])
            prev  = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
            chg   = ((price - prev) / prev * 100) if prev else 0
            cls   = "up" if chg > 0 else ("down" if chg < 0 else "neutral")
            arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "")
            result.append({
                "name": name, "flag": flag,
                "price": f"${price:.2f}",
                "chg_pct": f"{arrow} {abs(chg):.2f}%",
                "cls": cls,
            })
        except Exception as e:
            print(f"[fetch_closing] ai_semicon {name}: {e}", file=__import__("sys").stderr)

    print(f"[fetch_closing] AI 반도체 종목: {len(result)}개")
    return result


def fetch_closing_data() -> dict:
    print("[fetch_closing] 코스피 마감 데이터 수집 시작...")

    print("[fetch_closing]   → 지수 (KOSPI / KOSDAQ / USD/KRW)")
    kospi  = get_closing_price("^KS11")
    kosdaq = get_closing_price("^KQ11")
    usdkrw = get_closing_price("USDKRW=X")

    print("[fetch_closing]   → 프리마켓 선물")
    nq_fut  = get_closing_price("NQ=F")
    sp_fut  = get_closing_price("ES=F")
    wti     = get_closing_price("CL=F")

    print("[fetch_closing]   → 섹터 성과 (네이버)")
    sectors = fetch_sector_performance()

    print("[fetch_closing]   → 급등주 TOP 3 (네이버, 참고용)")
    top_gainers = fetch_top_gainers(limit=3)

    print("[fetch_closing]   → 장중 5분봉 (스파크라인)")
    intraday = fetch_intraday_kospi()

    print("[fetch_closing]   → 투자자별 순매수")
    investor = fetch_investor_trading()

    print("[fetch_closing]   → 거래대금")
    trade_amount = fetch_trade_amount()

    print("[fetch_closing]   → 시장 폭")
    market_breadth = fetch_market_breadth()

    print("[fetch_closing]   → 거래대금 급증 + 수급 동반 종목")
    dpick = fetch_dpick()

    print("[fetch_closing]   → 코스피 200 TOP10")
    kospi200_top10 = fetch_kospi200_top10()

    print("[fetch_closing]   → AI 반도체 종목")
    ai_semicon_stocks = fetch_ai_semicon_stocks()

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "kospi-close",
        "indices": {
            "kospi":  kospi,
            "kosdaq": kosdaq,
            "usdkrw": usdkrw,
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
        "trade_amount": trade_amount,
        "market_breadth": market_breadth,
        "dpick": dpick,
        "kospi200_top10": kospi200_top10,
        "ai_semicon_stocks": ai_semicon_stocks,
    }

    out = DATA_DIR / "latest_kospi_close.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_closing] 저장 완료 → {out}")
    return data


if __name__ == "__main__":
    fetch_closing_data()
