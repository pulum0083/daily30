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

# 2026-09-15 네이버가 finance.naver.com/sise·item 페이지를 stock.naver.com(클라이언트 렌더)으로 옮겨
# 옛 HTML 정규식이 예외 없이 0행을 읽었다(§51). 새 페이지가 부르는 JSON API로 바꿨다.
M_API = "https://m.stock.naver.com/api"
KOSPI_INTEGRATION_URL = f"{M_API}/index/KOSPI/integration"
INDUSTRY_LIST_URL = f"{M_API}/stocks/industry?page=1&pageSize=100"
INDUSTRY_DETAIL_URL = M_API + "/stocks/industry/{no}?page=1&pageSize=40"
STOCKS_UP_URL = f"{M_API}/stocks/up/KOSPI?page=1&pageSize=60"
QUANT_TOP_URL = f"{M_API}/stocks/quantTop/KOSPI?page=1&pageSize=100"
STOCK_TREND_URL = M_API + "/stock/{code}/trend?pageSize=20"
MINUTE_RANGE_URL = ("https://api.stock.naver.com/chart/domestic/item/{code}/minute"
                    "?startDateTime={start}0900&endDateTime={end}1530")

# 원천 구조가 바뀌어 목록 자체를 못 읽은 수집기 — fetch_closing_data가 모아 관리자에게 알린다.
_source_failures: list[str] = []


def _get_json(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _num(v):
    """네이버 문자열 숫자("+3,478", "-8.47", "1,209") → float. 비었거나 숫자가 아니면 None."""
    try:
        return float(str(v).replace(",", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def _source_failed(name: str, detail: str) -> None:
    _source_failures.append(f"{name}: {detail}")
    print(f"[fetch_closing] {name}: {detail}", file=sys.stderr)


# KRX 애프터마켓(16:00~20:00, §48)이 열리면 목록 API의 현재가·등락률과 업종 등락률이 애프터장 가격을 따른다.
# 2026-09-15 실측(15:58 → 16:12): 업종 79개 중 71개의 등락률이 바뀌고 종목 현재가도 움직였다. 시장 폭
# (upDownStockInfo)은 15:36·15:58·16:12 모두 254/623/40으로 그대로였다. 목록의 localTradedAt은 체결이 없어도
# 조회 시각으로 갱신돼 판정에 쓸 수 없다. 그래서 시각으로 판정한다 — 09:00~16:00 밖이면 업종·급등주를 비운다.
_after_market_skips: list[str] = []


def list_prices_regular(now=None) -> bool:
    """목록·업종 API 가격이 정규장 값인 시간대(09:00~16:00 KST)인가."""
    hhmm = (now or datetime.now(KST)).strftime("%H%M")
    return "0900" <= hhmm < "1600"


def _after_market_skip(name: str) -> None:
    _after_market_skips.append(name)
    print(f"[fetch_closing] {name}: 16:00 이후엔 목록 가격이 애프터장 값이라 비운다(§51)", file=sys.stderr)


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
    """USD/KRW 종가·등락률. 구현은 fetch_data.fetch_naver_usdkrw() 한 곳에만 둔다.

    예전엔 이 파일이 같은 수집을 독자적으로 구현했고, 그쪽 1순위(토스)가 등락률을
    리터럴 0.0으로 채우는 바람에 발행된 마감 브리핑 12건 전부가 '▲ +0.00%'로
    나갔다. 같은 판정을 두 곳에서 각자 구현하면 한쪽만 고쳐지고 다른 쪽은 몇 주씩
    방치돼도 겉보기엔 둘 다 정상으로 보인다(§20·§30). 위임으로 소스를 하나로 묶는다.
    """
    try:
        try:
            from scripts.fetch_data import fetch_naver_usdkrw
        except ImportError:
            from fetch_data import fetch_naver_usdkrw
        return fetch_naver_usdkrw()
    except Exception as e:
        print(f"[fetch_closing] USDKRW failed: {e}", file=sys.stderr)
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


def parse_top_gainers(payload, limit: int = 3) -> list[dict]:
    """/api/stocks/up/KOSPI 응답 → 상승률 상위 보통주(ETF·ETN 제외). 목록은 상승률 내림차순이다."""
    result = []
    for s in (payload or {}).get("stocks") or []:
        ratio = _num(s.get("fluctuationsRatio"))
        if s.get("stockEndType") != "stock" or ratio is None or ratio <= 0 or not s.get("closePrice"):
            continue
        result.append({
            "name":       str(s.get("stockName", "")).strip(),
            "change_pct": f"+{ratio:.2f}%",
            "price":      f"{s['closePrice']}원",
        })
        if len(result) >= limit:
            break
    return result


def fetch_top_gainers(limit: int = 3, fetch=_get_json, now=None) -> list[dict]:
    """코스피 등락률 순위 1~3위를 반환한다.

    Returns list of {"name": str, "change_pct": str, "price": str}
    """
    if not list_prices_regular(now):
        _after_market_skip("top_gainers")
        return []
    try:
        payload = fetch(STOCKS_UP_URL)
        result = parse_top_gainers(payload, limit)
    except Exception as e:
        print(f"[fetch_closing] top gainers fetch failed: {e}", file=sys.stderr)
        payload, result = {}, []
    if not result:
        _source_failed("top_gainers", "상승률 상위 목록 0건")
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


def parse_industry_groups(payload) -> list[dict]:
    """/api/stocks/industry 응답 → [{"no", "name", "change_pct"}]. 업종 번호는 옛 sise_group_detail과 같다."""
    out = []
    for g in (payload or {}).get("groups") or []:
        chg = _num(g.get("changeRate"))
        if g.get("no") is None or not g.get("name") or chg is None:
            continue
        out.append({"no": g["no"], "name": str(g["name"]).strip(), "change_pct": round(chg, 2)})
    return out


def parse_industry_top_stocks(payload, limit: int = 3) -> list[dict]:
    """/api/stocks/industry/{no} 응답 → 등락률 상위 코스피·코스닥 보통주. 코넥스(sosok 2)는 뺀다 —
    옛 업종 상세 페이지엔 없었고, 거래 1주로 +14%가 찍히는 종목이 상위를 차지한다."""
    stocks = []
    for s in (payload or {}).get("stocks") or []:
        chg = _num(s.get("fluctuationsRatio"))
        if s.get("sosok") not in ("0", "1") or s.get("stockEndType") != "stock" or chg is None:
            continue
        stocks.append({"name": str(s.get("stockName", "")).strip(), "change_pct": round(chg, 2)})
    stocks.sort(key=lambda x: x["change_pct"], reverse=True)
    return stocks[:limit]


def fetch_sector_performance(fetch=_get_json, now=None) -> list[dict]:
    """네이버 업종별 시세에서 섹터 등락률과 섹터별 상위 종목을 가져온다.

    Returns list of {"name": str, "change_pct": float, "stocks": [{"name", "change_pct"}, ...]}
    """
    if not list_prices_regular(now):
        _after_market_skip("sectors")
        return []
    try:
        groups = parse_industry_groups(fetch(INDUSTRY_LIST_URL))
    except Exception as e:
        print(f"[fetch_closing] sector fetch failed: {e}", file=sys.stderr)
        groups = []
    if not groups:
        _source_failed("sectors", "업종 목록 0건")
        return []

    # 등락률 절대값 기준으로 영향이 큰 섹터 상위 5개 반환
    groups.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    final = []
    for g in groups[:5]:
        try:
            detail = fetch(INDUSTRY_DETAIL_URL.format(no=g["no"]))
            stocks = parse_industry_top_stocks(detail, limit=3)
        except Exception as e:
            print(f"[fetch_closing] sector detail fetch failed ({g['no']}): {e}", file=sys.stderr)
            detail, stocks = {}, []
        final.append({"name": g["name"], "change_pct": g["change_pct"], "stocks": stocks})
        time.sleep(0.3)  # 네이버 부담 줄이기

    print(f"[fetch_closing] sectors: {len(final)}개 (종목 포함)")
    return final


# ─────────────────────────────────────────────────────────────────────────────
# 투자자별 순매수 — 구현은 fetch_data.fetch_investor_trading_kospi() 한 곳에만 둔다(§30)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_investor_trading() -> dict:
    """당일 외국인·기관·개인 순매수(정규장 마감 15:31~15:40 기준). 없으면 {}.

    16:25 마감 잡 시점엔 네이버 하루 합계에 애프터장 체결이 섞여 있으므로(§51) 시간대별 표를 쓴다.
    """
    try:
        try:
            from scripts.fetch_data import fetch_investor_trading_kospi
        except ImportError:
            from fetch_data import fetch_investor_trading_kospi
        result = fetch_investor_trading_kospi(date_str=datetime.now(KST).strftime("%Y%m%d"))
    except Exception as e:
        print(f"[fetch_closing] investor trading error: {e}", file=sys.stderr)
        result = {}
    if not result:
        _source_failed("investor_trading", "정규장 마감 수급 행 없음")
    return result

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

def parse_market_breadth(payload) -> dict:
    """/api/index/KOSPI/integration 응답의 upDownStockInfo → 시장 폭. 읽지 못하면 {}."""
    info = (payload or {}).get("upDownStockInfo") or {}
    vals = {k: _num(info.get(k)) for k in ("riseCount", "fallCount", "steadyCount", "upperCount", "lowerCount")}
    if any(v is None for v in vals.values()) or (vals["riseCount"] == 0 and vals["fallCount"] == 0):
        return {}
    return {
        "up": int(vals["riseCount"]), "down": int(vals["fallCount"]), "unchanged": int(vals["steadyCount"]),
        "upper_limit": int(vals["upperCount"]), "lower_limit": int(vals["lowerCount"]),
        "new_high": 0, "new_low": 0,
    }


def fetch_market_breadth(fetch=_get_json, now=None) -> dict:
    """코스피 시장 폭 데이터를 반환한다."""
    try:
        payload = fetch(KOSPI_INTEGRATION_URL)
        result = parse_market_breadth(payload)
    except Exception as e:
        print(f"[fetch_closing] market breadth naver error: {e}", file=sys.stderr)
        payload, result = {}, {}
    if not result:
        _source_failed("market_breadth", "등락 종목 수를 읽지 못함")
        return {}
    print(f"[fetch_closing] 시장 폭: 상승 {result['up']} / 하락 {result['down']} / 상한가 {result['upper_limit']}")
    return result

# ─────────────────────────────────────────────────────────────────────────────
# 거래대금 급증 + 수급 동반 종목 (외국인·기관 동시 순매수)
# ─────────────────────────────────────────────────────────────────────────────
# 데이터 제약: KRX 종목별 순매수 '금액' 소스가 막혀 있어(LOGOUT), 네이버 종목별
# 일별 순매매 '수량'에 종가를 곱한 근사 금액(억원)을 사용한다.

def parse_dpick_universe(payload, universe: int = 20) -> list[tuple[str, str]]:
    """/api/stocks/quantTop/KOSPI 응답 → 거래량 상위 보통주 [(코드, 이름)]. ETF·ETN은 stockEndType으로 뺀다."""
    out = []
    for s in (payload or {}).get("stocks") or []:
        if s.get("stockEndType") == "stock" and s.get("itemCode"):
            out.append((str(s["itemCode"]), str(s.get("stockName", "")).strip()))
    return out[:universe]


def parse_stock_trend(payload) -> list[dict]:
    """/api/stock/{code}/trend 응답 → 최신순 [{date, close, vol, frgn, inst}] (수량은 주)."""
    rows = []
    for r in payload if isinstance(payload, list) else []:
        vals = [_num(r.get(k)) for k in ("closePrice", "accumulatedTradingVolume",
                                         "foreignerPureBuyQuant", "organPureBuyQuant")]
        if not r.get("bizdate") or any(v is None for v in vals):
            continue
        rows.append({"date": str(r["bizdate"]), "close": vals[0], "vol": vals[1], "frgn": vals[2], "inst": vals[3]})
    return rows


def regular_session_rows(code: str, rows: list[dict], fetch=_get_json) -> list[dict]:
    """2026-09-14(애프터마켓 개장) 이후 행의 종가·거래량을 정규장 값으로 바꾼다.

    trend의 종가·거래량은 20:00 애프터장까지 누적된 값이다(9/14 삼성전자 실측: 종가 248,500 / 공식 249,000,
    거래량 17,776,098 / 정규장 1분봉 합 16,559,147). 종가는 kr_official_closes(§48), 거래량은 같은 날
    09:00~15:30 1분봉 거래량 합으로 채운다. 구하지 못한 값은 None으로 비워 둔다 — 틀린 값으로 채우지 않는다.
    """
    try:
        from scripts.kr_official_closes import AFTERMARKET_START, official_close
    except ImportError:
        from kr_official_closes import AFTERMARKET_START, official_close
    recent = sorted(r["date"] for r in rows if r["date"] >= AFTERMARKET_START)
    if not recent:
        return rows
    try:
        bars = fetch(MINUTE_RANGE_URL.format(code=code, start=recent[0], end=recent[-1]))
    except Exception as e:
        print(f"[fetch_closing] dpick {code} 1분봉 조회 실패: {e}", file=sys.stderr)
        bars = []
    by_date: dict[str, list] = {}
    for b in bars if isinstance(bars, list) else []:
        ts = str(b.get("localDateTime", "")) if isinstance(b, dict) else ""
        if len(ts) >= 12 and "0900" <= ts[8:12] <= "1530":
            by_date.setdefault(ts[:8], []).append(b)

    def served(url):  # kr_official_closes가 부르는 15:30 1분봉 조회를 이미 받은 봉으로 대신한다
        return by_date.get(url.split("startDateTime=")[1][:8], [])

    out = []
    for r in rows:
        if r["date"] < AFTERMARKET_START:
            out.append(r)
            continue
        day = by_date.get(r["date"])
        close = official_close(code, r["date"], fetch=served)
        vol = sum(float(b.get("accumulatedTradingVolume") or 0) for b in day) if day else None
        out.append({**r, "close": close, "vol": vol})
    return out


def fetch_dpick(universe: int = 20, limit: int = 3, min_mult: float = 1.5, now=None, fetch=_get_json) -> list:
    """거래대금 급증 × 외국인·기관 동시 순매수 종목을 반환한다.

    universe(코스피 거래량 상위 보통주)의 일별 외국인·기관 순매매로 (ⓐ거래대금이 최근 평균 대비 min_mult배
    이상 급증, ⓑ외국인·기관 동시 순매수)를 만족하는 종목을 거래대금 순으로 선별한다.
    종가·등락률·거래대금은 정규장 값만 쓴다(§48·§51).
    """
    now = now or datetime.now(KST)
    today = now.strftime("%Y%m%d")
    try:
        cand = parse_dpick_universe(fetch(QUANT_TOP_URL), universe)
    except Exception as e:
        print(f"[fetch_closing] dpick universe fetch failed: {e}", file=sys.stderr)
        cand = []
    if not cand:
        _source_failed("dpick", "거래량 상위 목록 0건")
        return []

    picks = []
    for code, name in cand:
        try:
            rows = parse_stock_trend(fetch(STOCK_TREND_URL.format(code=code)))
        except Exception as e:
            print(f"[fetch_closing] dpick {name}({code}) trend 조회 실패: {e}", file=sys.stderr)
            continue
        # 당일 데이터가 아직 올라오지 않은 경우(어제 데이터) → 스킵
        if not rows or rows[0]["date"] != today:
            print(f"[fetch_closing] dpick {name}({code}): 최신 행={rows[0]['date'] if rows else None} ≠ 오늘={today} → 스킵")
            continue
        rows = regular_session_rows(code, rows, fetch)
        cur = rows[0]
        prev = rows[1] if len(rows) > 1 else {}
        if not cur["close"] or not cur["vol"] or not prev.get("close"):
            print(f"[fetch_closing] dpick {name}({code}): 정규장 종가·거래량 없음 → 스킵")
            continue
        close = cur["close"]
        tv = cur["vol"] * close / 1e8                              # 당일 거래대금(억)
        hist = [x for x in rows[:20] if x["close"] and x["vol"]]
        if len(hist) < 5:
            print(f"[fetch_closing] dpick {name}({code}): 정규장 거래량 {len(hist)}일뿐 → 스킵")
            continue
        avg = sum(x["vol"] * x["close"] for x in hist) / len(hist) / 1e8
        mult = tv / avg if avg else 0
        frgn_eok = cur["frgn"] * close / 1e8
        inst_eok = cur["inst"] * close / 1e8
        if frgn_eok > 0 and inst_eok > 0 and mult >= min_mult:
            picks.append({
                "name": name, "code": code,
                "change_pct": round((close - prev["close"]) / prev["close"] * 100, 2),
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


# 거래일이면 비어 있을 수 없는 네이버 수집 결과. 비었다면 원천 구조가 바뀐 것이다(§47·§51).
REQUIRED_NAVER_KEYS = ("market_breadth", "sectors", "top_gainers", "investor_trading")
PRESERVE_KEYS = REQUIRED_NAVER_KEYS + ("dpick",)
PRESERVE_AFTER_HHMM = "1540"


def preserve_same_day(data: dict, old: dict) -> list[str]:
    """같은 날 15:40 이후에 저장된 파일이 가진 값을, 이번에 빈손이 된 키에만 되살린다.

    §1은 dpick이 비면 16:30 뒤 재실행하라고 한다. 그 재실행에서 원천이 흔들려 시장 폭이 비면
    이미 받은 정규장 값을 빈 값으로 덮어쓰게 된다. 날짜가 다르거나 장중에 만든 파일이면 되살리지 않는다.
    """
    new_at, old_at = str(data.get("generated_at", "")), str((old or {}).get("generated_at", ""))
    if not old_at or old_at[:10] != new_at[:10] or old_at[11:16].replace(":", "") < PRESERVE_AFTER_HHMM:
        return []
    kept = []
    for k in PRESERVE_KEYS:
        if not data.get(k) and old.get(k):
            data[k] = old[k]
            kept.append(k)
    return kept


def alert_source_failures(data: dict, failures: list[str]) -> None:
    missing = [k for k in REQUIRED_NAVER_KEYS if not data.get(k) and k not in _after_market_skips]
    if not missing and not failures:
        return
    try:
        try:
            from scripts.send_telegram import send_admin_alert
        except ImportError:
            from send_telegram import send_admin_alert
        send_admin_alert(
            "[Double-Shot] 코스피 마감 데이터 수집 일부 실패 — 해당 섹션은 비운 채로 발행됩니다\n"
            f"빈 항목: {', '.join(missing) or '없음'}\n"
            + "\n".join(failures) + "\n"
            "네이버 원천(stock.naver.com JSON) 구조 변경을 의심하세요(SERVICE_RULES §51).\n"
            "확인: python3 scripts/fetch_closing_kospi.py"
        )
    except Exception as e:
        print(f"[fetch_closing] 관리자 알림 실패: {e}", file=sys.stderr)


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
    try:
        kept = preserve_same_day(data, json.loads(out.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        kept = []
    if kept:
        print(f"[fetch_closing] 이번 수집이 비어 같은 날 저장본 값을 유지: {kept}", file=sys.stderr)
    alert_source_failures(data, [f for f in _source_failures if f.split(":")[0] not in kept])
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_closing] 저장 완료 → {out}")
    return data


if __name__ == "__main__":
    fetch_closing_data()
