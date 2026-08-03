#!/usr/bin/env python3
"""
Market data fetcher for DailyB Investment Assistant.
Pre-collects ALL data needed for briefings so Claude makes ≤3 web searches per run.
"""

from __future__ import annotations  # `X | None` 어노테이션을 구버전 파이썬에서도 임포트 가능하게

import argparse
import json
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")
UTC = pytz.utc

# 밤사이 브리지 — 섹터별 미국 비교 대상 티커(고정, 손으로 골랐다).
# ETF가 있는 섹터는 ETF 단독으로 쓴다(semicon·defense·battery·bio·finance) — 개별주 하나가
# 섹터 전체와 같은 가중치를 갖는 것을 피하기 위함. ETF가 마땅치 않은 섹터만 개별주를
# 평균한다(power: GEV+VRT, auto: TSLA+F). kind가 ETF·개별주 구분 없이 전부 "US"라
# 어느 티커를 쓸지는 자동화할 수 없어 티커 선택만 수동 매핑으로 남긴다.
# 표시 이름은 여기 담지 않는다 — stock_universe.json의 bellwethers[].name을 매 호출마다
# 그대로 가져와 쓴다(§20·§30 이중소스 재발 방지). 이름을 두 곳에 따로 두면 universe에서
# 이름이 바뀌어도 이 브리핑만 옛 이름을 계속 보여주게 된다.
# ⚠️ SECTOR_FOCUS_STOCKS(바로 아래, 중단된 sector_focus 섹션용)와 섹터 구성이 다르다.
# 재사용 금지 — stock_universe.json만 단일 소스로 쓴다.
BRIDGE_US_TICKERS = {
    "semicon": ["SOXX"],
    "power":   ["GEV", "VRT"],
    "defense": ["ITA"],
    "battery": ["LIT"],
    "auto":    ["TSLA", "F"],
    "bio":     ["XBI"],
    "finance": ["KBE"],
}

# 섹터 로테이션 대표 종목·ETF (sector_focus 브리핑용 실시간 데이터 수집)
SECTOR_FOCUS_STOCKS = {
    "semicon": {
        "etfs": [("SOX", "^SOX"), ("DRAM", "DRAM")],
        "ko":   [("005930.KS", "삼성전자"), ("000660.KS", "SK하이닉스"), ("042700.KS", "한미반도체")],
    },
    "power": {
        "etfs": [],
        "ko":   [("267260.KS", "HD현대일렉트릭"), ("010120.KS", "LS일렉트릭"), ("298040.KS", "효성중공업")],
    },
    "defense": {
        "etfs": [("ITA", "ITA")],
        "ko":   [("012450.KS", "한화에어로스페이스"), ("079550.KS", "LIG넥스원"), ("064350.KS", "현대로템")],
    },
    "ship": {
        "etfs": [],
        "ko":   [("329180.KS", "HD현대중공업"), ("042660.KS", "한화오션"), ("010140.KS", "삼성중공업")],
    },
    "battery": {
        "etfs": [("LIT", "LIT")],
        "ko":   [("373220.KS", "LG에너지솔루션"), ("247540.KS", "에코프로비엠"), ("006400.KS", "삼성SDI")],
    },
    "auto": {
        "etfs": [],
        "ko":   [("005380.KS", "현대차"), ("000270.KS", "기아"), ("012330.KS", "현대모비스")],
    },
    "bio": {
        "etfs": [("XBI", "XBI")],
        "ko":   [("207940.KS", "삼성바이오로직스"), ("068270.KS", "셀트리온"), ("000100.KS", "유한양행")],
    },
    "finance": {
        "etfs": [],
        "ko":   [("105560.KS", "KB금융"), ("055550.KS", "신한지주"), ("138040.KS", "메리츠금융지주")],
    },
}

# Korean stock candidates for Kellogg strategy screening
KOSPI_CANDIDATES = [
    ("005930.KS", "삼성전자"),
    ("000660.KS", "SK하이닉스"),
    ("042700.KS", "한미반도체"),
    ("005490.KS", "POSCO홀딩스"),
    ("035420.KS", "NAVER"),
    ("000270.KS", "기아"),
    ("005380.KS", "현대차"),
    ("068270.KS", "셀트리온"),
    ("035720.KS", "카카오"),
    ("051910.KS", "LG화학"),
    ("207940.KS", "삼성바이오로직스"),
    ("373220.KS", "LG에너지솔루션"),
    ("066570.KS", "LG전자"),
    ("012330.KS", "현대모비스"),
    ("086790.KS", "하나금융지주"),
]

# US stock candidates for Kellogg strategy screening
US_CANDIDATES = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA",
    "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC",
    "JPM", "BAC", "GS", "MS",
    "XOM", "CVX",
]

# Sidebar ticker mapping: key → yfinance ticker
SIDEBAR_TICKERS_KOSPI = {
    "kospi":  "^KS11",
    "kosdaq": "^KQ11",
    "nasdaq": "^IXIC",
    "nq":     "NQ=F",
    "dji":    "^DJI",
    "sox":    "^SOX",
    "oil":    "CL=F",
    "usd":    "USDKRW=X",
    "dxy":    "DX-Y.NYB",
}

SIDEBAR_TICKERS_US = {
    "kospi":  "^KS11",
    "kosdaq": "^KQ11",
    "nasdaq": "^IXIC",
    "nq":     "NQ=F",
    "dji":    "^DJI",
    "sox":    "^SOX",
    "oil":    "CL=F",
    "usd":    "USDKRW=X",
    "dxy":    "DX-Y.NYB",
}


def _bucket_calendar_events(events: list, kst_now: datetime) -> dict:
    """고영향 이벤트를 추려 **발행 시각 기준 시제**(status)를 붙여 분류한다.

    날짜만 비교하면 그날 새벽에 이미 끝난 이벤트(예: 03:00 KST FOMC)가
    21:15 KST 미국 브리핑에서도 "오늘 예정"으로 남는다 — 2026-07-30 실사고.
    소스(ff_calendar_thisweek.json)는 `actual`을 **절대 채우지 않으므로**
    "actual이 비었으면 미발표"라는 판정은 쓸 수 없다. 시각 비교가 유일한 근거다.

    status: "released"(이미 발표됨) | "upcoming"(아직 안 나옴)
    """
    KEY_COUNTRIES = {"USD", "CNY", "KRW", "JPY", "EUR"}
    today_kst = kst_now.strftime("%Y-%m-%d")

    today_events, upcoming_events = [], []
    for ev in events:
        if ev.get("impact") != "High" or ev.get("country") not in KEY_COUNTRIES:
            continue
        try:
            dt_kst = datetime.fromisoformat(ev.get("date", "")).astimezone(KST)
        except Exception:
            continue  # 시제를 판정할 수 없는 이벤트는 버린다

        item = {
            "title":    ev.get("title", ""),
            "country":  ev.get("country", ""),
            "impact":   ev.get("impact", ""),
            "date_kst": dt_kst.strftime("%Y-%m-%d %H:%M KST"),
            "date_kst_date": dt_kst.strftime("%Y-%m-%d"),
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
            "actual":   ev.get("actual", ""),
            "status":   "released" if dt_kst <= kst_now else "upcoming",
        }

        if item["date_kst_date"] == today_kst:
            today_events.append(item)
        elif item["date_kst_date"] > today_kst:
            upcoming_events.append(item)

    return {"today": today_events, "upcoming": upcoming_events[:10]}


def fetch_economic_calendar() -> dict:
    """ForexFactory 주간 경제 캘린더에서 고영향 이벤트를 가져온다 (무료, API 키 불필요).

    Returns:
        {
          "today": [...],    # 오늘 KST 기준 고영향 이벤트 (각 항목에 status)
          "upcoming": [...], # 향후 5일 고영향 이벤트 (최대 10개)
        }
    """
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 DailyB/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read().decode("utf-8"))

        out = _bucket_calendar_events(events, datetime.now(KST))
        released = sum(1 for e in out["today"] if e["status"] == "released")
        print(f"[fetch_data] Economic calendar: today={len(out['today'])} "
              f"(released={released}), upcoming={len(out['upcoming'])}")
        return out

    except Exception as e:
        print(f"[fetch_data] Economic calendar error: {e}", file=sys.stderr)
        return {"today": [], "upcoming": []}


def fetch_investor_trading_kospi(date_str: str = None) -> dict:
    """NAVER Finance에서 코스피 투자자별 순매수 데이터를 가져온다 (인증 불필요).

    코스피 조회 기준일: 당일 시장 개장 전이므로 전 거래일 데이터 사용.

    Returns:
        {
          "date": "YYYYMMDD",
          "foreign":     {"net": int},  # 외국인합계 순매수 (단위: 백만원)
          "institution": {"net": int},  # 기관합계 순매수
          "individual":  {"net": int},  # 개인 순매수
        }
    """
    import re

    kst_now = datetime.now(KST)

    if date_str is None:
        # 전 거래일 (주말 건너뜀)
        target = kst_now - timedelta(days=1)
        while target.weekday() >= 5:  # 5=Sat, 6=Sun
            target -= timedelta(days=1)
        date_str = target.strftime("%Y%m%d")

    # 네이버 증권 KOSPI 지수 페이지의 "투자자별 매매동향" 파싱.
    # 구 investorTrend JSON API(api.stock.naver.com/.../investorTrend)는 폐기되어 404.
    # 마감 브리핑(fetch_closing_kospi.fetch_investor_trading)과 동일한 HTML 소스를 사용한다.
    # 07:30 실행 시점엔 시장이 마감 상태이므로 이 페이지는 직전 완료 세션(전 거래일) 수급을 보여준다.
    try:
        url = "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("euc-kr", errors="ignore")

        # "개인<br>..+N,NNN억...외국인<br>...-N,NNN억...기관<br>...+N,NNN억" 패턴
        m = re.search(
            r"개인<br>.*?([+-][0-9,]+).*?외국인<br>.*?([+-][0-9,]+).*?기관<br>.*?([+-][0-9,]+)",
            text, re.DOTALL,
        )
        if not m:
            print("[fetch_data] Investor trading: pattern not found", file=sys.stderr)
            return {}

        def _eok_to_mwon(s: str) -> int:
            # 억원 → 백만원 (×100). 다운스트림(supply_history·generate_html)이 기대하는 단위.
            return int(s.replace(",", "").replace("+", "")) * 100

        individual  = _eok_to_mwon(m.group(1))
        foreign     = _eok_to_mwon(m.group(2))
        institution = _eok_to_mwon(m.group(3))
        result = {
            "date":        date_str,
            "foreign":     {"net": foreign},
            "institution": {"net": institution},
            "individual":  {"net": individual},
        }
        print(f"[fetch_data] Investor trading ({date_str}): "
              f"foreign={foreign:+,}, institution={institution:+,}, individual={individual:+,} (백만원)")
        return result
    except Exception as e:
        print(f"[fetch_data] Investor trading error: {e}", file=sys.stderr)
        return {}


def _yf_history(ticker: str, retries: int = 3, **kwargs):
    """yfinance history() 호출을 최대 retries회 exponential backoff으로 재시도한다."""
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
            print(f"[fetch_data] {ticker} fetch failed (attempt {attempt + 1}/{retries}), retry in {delay}s", file=sys.stderr)
            time.sleep(delay)
    if last_exc:
        print(f"[fetch_data] {ticker} all retries failed: {last_exc}", file=sys.stderr)
    return pd.DataFrame()



def _prev_close_from_daily(closes, price: float) -> float | None:
    """일봉 종가 시리즈에서 `price`가 속한 세션의 '직전 세션 종가'를 구한다.

    yfinance `fast_info.previous_close`는 직전 세션이 아닌 더 과거 세션의 종가를
    돌려주는 경우가 있다(2026-07-27 실사고: EWY previous_close=172.964 = 7/21 종가,
    실제 직전 종가는 173.86 = 7/23 → 등락률이 -6.27%가 아닌 -5.78%로 표시됨).
    실시간 가격 자체(last_price)는 정확하므로, 기준가만 일봉에서 다시 구해 교정한다.

    실패하거나 판별 불가하면 None → 호출부가 기존 값을 유지한다.
    """
    try:
        if closes is None or len(closes) < 2 or not price:
            return None
        last = float(closes.iloc[-1])
        if not last:
            return None

        # ① price가 마지막 일봉 종가와 같으면 장 마감 상태 → 그 직전 종가가 기준가
        if abs(price - last) / last < 1e-4:
            return float(closes.iloc[-2])

        # ② 세션 진행 중(또는 시간외) — 마지막 일봉이 '오늘' 바인지로 갈린다.
        #    거래소 현지 시각 기준으로 판별한다(yfinance 인덱스는 거래소 tz).
        ts = closes.index[-1]
        tzinfo = getattr(ts, "tzinfo", None)
        if tzinfo is None:
            return None
        if ts.date() >= datetime.now(tzinfo).date():
            return float(closes.iloc[-2])  # 마지막 바 = 오늘 진행 중 바
        return last                        # 마지막 바 = 직전 세션 종가
    except Exception:
        return None


def _is_futures_like(ticker: str) -> bool:
    """선물·지수·금리 심볼인가 (롤오버 가드 적용 대상).

    개별 주식·ETF는 롤오버가 없다. 가드를 개별주에 적용하면 프리마켓 실체결가를
    '롤오버 갭'으로 오인해 정규장 종가로 되돌린다(2026-07-27: XOM 프리마켓 -3.19%가
    +4.15%로 부호까지 반전). 가드가 쓰는 1시간봉은 prepost를 포함하지 않기 때문이다.
    """
    t = (ticker or "").upper()
    return t.endswith("=F") or t.startswith("^") or t.endswith("=X")


def _extended_hours_price(intraday, fast_last: float | None, now=None,
                          max_age_hours: float = 12.0) -> float | None:
    """프리마켓·애프터마켓을 포함한 '지금 이 시점'의 최근 체결가를 돌려준다.

    yfinance `fast_info.last_price`는 **연장시간대(프리·애프터) 체결을 반영하지 않는다** —
    프리마켓 한복판에도 직전 정규장 종가를 그대로 준다(2026-07-27 실측: 프리마켓에서
    MU가 938.18에 거래되는데 fast_info는 금요일 종가 920.95를 반환).
    미국 브리핑은 21:15 KST = 프리마켓 한복판에 발행되므로, 이 값을 그대로 쓰면
    "발행 시점 데이터"가 아니라 항상 직전 세션 종가가 실린다(운영 규칙 0 위반).

    판정은 **값이 아니라 타임스탬프**로 한다 — fast_info 값을 5분봉에서 되찾는 방식은
    공식 종가와 봉 종가가 미세하게 달라 자주 빗나간다(실측에서 10종목 중 4종목 실패).
    `prepost=True` intraday의 마지막 바가 `max_age_hours` 이내로 신선하면 그 값을 쓰고,
    비어 있거나 오래됐으면(주말·휴장·데이터 지연) fast_last를 유지한다(fail-open).
    """
    if intraday is None or len(intraday) == 0:
        return float(fast_last) if fast_last else None
    closes = intraday["Close"].dropna()
    if not len(closes):
        return float(fast_last) if fast_last else None

    last_ts = closes.index[-1]
    if now is None:
        now = datetime.now(last_ts.tzinfo) if last_ts.tzinfo else datetime.now()
    age_h = (now - last_ts).total_seconds() / 3600.0
    if age_h > max_age_hours:
        # 마지막 체결이 너무 오래됨 — 주말·휴장 구간이라 연장시간대가 아니다.
        return float(fast_last) if fast_last else float(closes.iloc[-1])
    return float(closes.iloc[-1])


def _get_realtime_price(ticker: str) -> tuple[float, float] | None:
    """장 중/프리마켓 현재가와 전일 종가를 반환한다.

    fast_info로 기준가(전일 종가)를 잡되, 현재가는 prepost intraday로 교차 검증해
    **연장시간대 체결을 반영한다**(fast_info는 프리·애프터를 반영하지 않는다 — 위 함수 참조).
    실패 시 None 반환 → 호출부에서 일봉 fallback 처리.
    """
    import yfinance as yf

    intraday = None
    try:
        intraday = _yf_history(ticker, period="2d", interval="5m", prepost=True)
    except Exception:
        intraday = None

    # 1순위: fast_info (기준가) + intraday 교차 검증 (현재가)
    try:
        fi = yf.Ticker(ticker).fast_info
        last = fi.last_price
        prev = fi.previous_close
        if last and prev and float(last) > 0 and float(prev) > 0:
            live = _extended_hours_price(intraday, float(last))
            if live and live > 0 and abs(live - float(last)) > 0.005:
                print(
                    f"[fetch_data] {ticker} 연장시간대 체결 반영: "
                    f"{float(last):.2f} → {live:.2f}",
                    file=sys.stderr,
                )
            return float(live or last), float(prev)
    except Exception:
        pass

    # 2순위: fast_info 실패 시 intraday만으로 구성
    try:
        if intraday is not None and not intraday.empty:
            intraday_closes = intraday["Close"].dropna()
            if len(intraday_closes) > 0:
                # 전일 종가는 intraday에서 날짜 경계로 구분
                today = intraday_closes.index[-1].date()
                prev_closes = intraday_closes[intraday_closes.index.date < today]
                if not prev_closes.empty:
                    return float(intraday_closes.iloc[-1]), float(prev_closes.iloc[-1])
    except Exception:
        pass

    return None


def get_ticker_full(ticker: str) -> dict:
    """
    Fetch 1 year daily history for a ticker.
    Returns: price, change_pct, volume, sparkline (10 daily closes),
             ma20, ma20_dist_pct, ma20_sparkline (10 pts),
             ma200, ma200_dist_pct, ma200_sparkline (10 pts).
    """
    try:
        hist = _yf_history(ticker, period="1y")
        if len(hist) < 2:
            return {"error": "insufficient data"}

        closes = hist["Close"].dropna()

        # 장 중/프리마켓 실시간 가격 우선, 실패 시 일봉 fallback
        rt = _get_realtime_price(ticker)
        if rt is not None:
            price, prev_price = rt
            # fast_info.previous_close가 과거 세션 종가를 주는 경우가 있어 일봉으로 교정
            fixed = _prev_close_from_daily(closes, price)
            if fixed and abs(fixed - prev_price) / fixed > 1e-4:
                print(f"[fetch_data] {ticker}: previous_close 교정 {prev_price:.4f} → {fixed:.4f}",
                      file=sys.stderr)
                prev_price = fixed
        else:
            price = float(closes.iloc[-1])
            prev_price = float(closes.iloc[-2])
        change_pct = (price - prev_price) / prev_price * 100

        # Futures rollover guard: same as build_sidebar_market_data.
        # Applies to commodity/rate futures (BZ=F, CL=F, GC=F, ^TNX, etc.) ONLY —
        # 개별주에 적용하면 프리마켓 실체결가를 롤오버 갭으로 오인해 되돌린다.
        try:
            h = _yf_history(ticker, period="5d", interval="1h") \
                if _is_futures_like(ticker) else None
            hc = h["Close"].dropna() if h is not None else []
            if len(hc) >= 25:
                hp = float(hc.iloc[-1])
                gap = abs(price - hp) / hp if hp != 0 else 0
                if gap > 0.03:
                    hp_prev = float(hc.iloc[max(0, len(hc) - 25)])
                    price = hp
                    change_pct = (hp - hp_prev) / hp_prev * 100 if hp_prev != 0 else 0
                    print(
                        f"[fetch_data] {ticker}: rollover detected (gap={gap:.1%}) → hourly override",
                        file=sys.stderr,
                    )
        except Exception:
            pass

        result = {
            "price":      round(price, 4),
            "change_pct": round(change_pct, 4),
            "volume":     int(hist["Volume"].iloc[-1]),
            "sparkline":  [round(float(p), 4) for p in closes.iloc[-20:].tolist()],
        }

        if len(closes) >= 20:
            ma20_series = closes.rolling(20).mean().dropna()
            ma20 = float(ma20_series.iloc[-1])
            result["ma20"] = round(ma20, 4)
            result["ma20_dist_pct"] = round((price - ma20) / ma20 * 100, 2)
            result["ma20_sparkline"] = [round(float(v), 4) for v in ma20_series.iloc[-20:].tolist()]

            # MA20 signal: crossing_up = previously below, now above
            if len(ma20_series) >= 2:
                prev_close = float(closes.iloc[-2])
                prev_ma20 = float(ma20_series.iloc[-2])
                if prev_close < prev_ma20 and price >= ma20:
                    result["ma20_signal"] = "crossing_up"
                elif prev_close >= prev_ma20 and price < ma20:
                    result["ma20_signal"] = "crossing_down"
                elif price >= ma20:
                    result["ma20_signal"] = "above"
                else:
                    result["ma20_signal"] = "below"

        if len(closes) >= 200:
            ma200_series = closes.rolling(200).mean().dropna()
            ma200 = float(ma200_series.iloc[-1])
            result["ma200"] = round(ma200, 4)
            result["ma200_dist_pct"] = round((price - ma200) / ma200 * 100, 2)
            result["ma200_sparkline"] = [round(float(v), 4) for v in ma200_series.iloc[-20:].tolist()]

        return result
    except Exception as e:
        return {"error": str(e)}


def get_hourly_sparkline(ticker: str, n: int = 10) -> list:
    """Get last n hourly closing prices for sidebar sparklines."""
    try:
        hist = _yf_history(ticker, period="5d", interval="1h")
        closes = hist["Close"].dropna()
        if len(closes) > 0:
            return [round(float(p), 4) for p in closes.iloc[-n:].tolist()]
    except Exception as e:
        print(f"[fetch_data] Hourly sparkline error {ticker}: {e}", file=sys.stderr)
    return []


def build_sidebar_market_data(sidebar_map: dict) -> dict:
    """
    Build the window.MARKET_DATA object for sidebar injection.
    Returns dict ready to be JSON-serialised as window.MARKET_DATA.
    """
    import math

    market_data = {}
    for key, ticker in sidebar_map.items():
        try:
            # USD/KRW: 네이버 실시간 API 1순위, yfinance는 sparkline 전용 폴백
            # yfinance USDKRW=X는 주말 데이터 혼입·지연 문제로 가격이 틀릴 수 있다.
            if key == "usd":
                naver = fetch_naver_usdkrw()
                hourly_hist = _yf_history(ticker, period="5d", interval="1h")
                hourly_closes = hourly_hist["Close"].dropna()
                sparkline = [round(float(p), 4) for p in hourly_closes.iloc[-10:].tolist()] if len(hourly_closes) >= 1 else []
                if naver and "price" in naver:
                    market_data[key] = {
                        "base": naver["price"],
                        "chg":  naver["change_pct"],
                        "data": sparkline,
                    }
                    print(f"[fetch_data] sidebar {key}: {naver['price']:.2f} ({naver['change_pct']:+.2f}%) [naver] [{len(sparkline)} pts]")
                    continue
                # 네이버 실패 → yfinance 폴백 (아래 공통 로직으로 진행)
                print(f"[fetch_data] sidebar {key}: naver failed → yfinance fallback", file=sys.stderr)

            # Use 1mo period for reliability (5d can be too short after long weekends)
            hist = _yf_history(ticker, period="1mo")
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                print(f"[fetch_data] sidebar {key}/{ticker}: insufficient data ({len(closes)} closes)", file=sys.stderr)
                continue

            # 장 중/프리마켓 실시간 가격 우선, 실패 시 일봉 fallback
            rt = _get_realtime_price(ticker)
            if rt is not None:
                price, prev = rt
                # fast_info.previous_close가 과거 세션 종가를 주는 경우가 있어 일봉으로 교정
                fixed = _prev_close_from_daily(closes, price)
                if fixed and abs(fixed - prev) / fixed > 1e-4:
                    print(f"[fetch_data] sidebar {key}/{ticker}: previous_close 교정 "
                          f"{prev:.4f} → {fixed:.4f}", file=sys.stderr)
                    prev = fixed
            else:
                price = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])

            if math.isnan(price) or math.isnan(prev) or prev == 0:
                print(f"[fetch_data] sidebar {key}/{ticker}: invalid price (price={price}, prev={prev})", file=sys.stderr)
                continue
            chg = round((price - prev) / prev * 100, 2)

            # Fetch hourly data: used for sparkline and futures rollover sanity check.
            # Futures contracts (CL=F, BZ=F, NQ=F, etc.) roll monthly — the "last daily close"
            # from yfinance can jump to the new contract's price, creating a 4-8% artificial gap.
            # If daily close deviates >3% from the latest hourly close, the daily data is stale
            # due to rollover; override with hourly-based price and 24h-ago comparison.
            hourly_hist = _yf_history(ticker, period="5d", interval="1h")
            hourly_closes = hourly_hist["Close"].dropna()

            if len(hourly_closes) >= 2:
                hourly_price = float(hourly_closes.iloc[-1])
                gap = abs(price - hourly_price) / hourly_price if hourly_price != 0 else 0
                if gap > 0.03:
                    # Rollover detected: switch to hourly-based price and 24h change
                    hourly_prev = float(hourly_closes.iloc[max(0, len(hourly_closes) - 25)])
                    price = round(hourly_price, 2)
                    chg = round((hourly_price - hourly_prev) / hourly_prev * 100, 2) if hourly_prev != 0 else 0
                    print(
                        f"[fetch_data] sidebar {key}/{ticker}: rollover detected "
                        f"(daily={closes.iloc[-1]:.2f}, hourly={hourly_price:.2f}, gap={gap:.1%}) "
                        f"→ switched to hourly data",
                        file=sys.stderr,
                    )
                sparkline = [round(float(p), 4) for p in hourly_closes.iloc[-10:].tolist()]
            else:
                sparkline = [round(float(p), 4) for p in closes.iloc[-10:].tolist()]

            market_data[key] = {
                "base": round(price, 2),
                "chg":  chg,
                "data": sparkline,
            }
            print(f"[fetch_data] sidebar {key}: {price:.2f} ({chg:+.2f}%) [{len(sparkline)} pts]")
        except Exception as e:
            print(f"[fetch_data] sidebar {key}/{ticker}: {e}", file=sys.stderr)

    return market_data


def build_stock_candidates(candidates: list[tuple]) -> list[dict]:
    """
    Fetch full data for stock candidates and sort by Kellogg signal quality.
    Returns list of candidate dicts including sparklines for stockCharts injection.
    """
    result = []
    for ticker, name in candidates:
        data = get_ticker_full(ticker)
        if "error" in data:
            print(f"[fetch_data] candidate {ticker} ({name}): {data['error']}", file=sys.stderr)
            continue

        entry = {
            "ticker":          ticker,
            "name":            name,
            "price":           data["price"],
            "change_pct":      data["change_pct"],
            "volume":          data.get("volume", 0),
            "ma20":            data.get("ma20"),
            "ma20_dist_pct":   data.get("ma20_dist_pct"),
            "ma20_signal":     data.get("ma20_signal", "unknown"),
            "ma200":           data.get("ma200"),
            "ma200_dist_pct":  data.get("ma200_dist_pct"),
            # stockCharts-ready arrays
            "sparkline":       data.get("sparkline", []),
            "ma20_sparkline":  data.get("ma20_sparkline", []),
            "ma200_sparkline": data.get("ma200_sparkline", []),
        }
        result.append(entry)

    # Sort: crossing_up first, then above with small distance, then rest
    signal_priority = {"crossing_up": 0, "above": 1, "crossing_down": 2, "below": 3, "unknown": 4}
    result.sort(key=lambda x: (
        signal_priority.get(x["ma20_signal"], 4),
        abs(x["ma20_dist_pct"] or 999),
    ))
    return result


def fetch_naver_usdkrw() -> dict:
    """USD/KRW 현재가·전일 대비 등락률.
    1차: manana.kr (chipboard 동일 소스, 안정적)
    2차: fawazahmed0 CDN (chipboard 동일 소스)
    3차: 네이버 모바일 API
    실패 시 빈 dict 반환 → 호출부에서 yfinance 폴백 처리.
    """
    # 1차: manana.kr
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
            chg_pct = round((price - prev) / prev * 100, 2) if prev else 0.0
            return {"price": round(price, 2), "change_pct": chg_pct}
    except Exception as e:
        print(f"[fetch_data] manana.kr USDKRW failed: {e}", file=sys.stderr)

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
            return {"price": round(float(rate), 2), "change_pct": 0.0}
    except Exception as e:
        print(f"[fetch_data] fawazahmed0 USDKRW failed: {e}", file=sys.stderr)

    # 3차: 네이버 모바일 API
    try:
        url = (
            "https://m.stock.naver.com/front-api/marketIndex/prices"
            "?reutersCode=FX_USDKRW&category=exchange&pageSize=10&page=1"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
        rows = payload.get("result") or []
        if len(rows) >= 2:
            price = float(rows[0]["closePrice"].replace(",", ""))
            prev  = float(rows[1]["closePrice"].replace(",", ""))
            chg_pct = round((price - prev) / prev * 100, 2) if prev else 0.0
            return {"price": round(price, 2), "change_pct": chg_pct}
    except Exception as e:
        print(f"[fetch_data] naver USDKRW failed: {e}", file=sys.stderr)

    return {}


def _get_price_change(ticker: str) -> dict | None:
    """ticker의 최신 종가와 전일 대비 등락률을 수집한다 (5d 히스토리, 경량).

    USDKRW=X 같은 외환 티커는 일요일 데이터가 포함되어 '전일'이 주말로
    잡히는 문제가 있다. 평일(월~금) 행만 남겨서 비교한다.
    """
    try:
        hist = _yf_history(ticker, period="5d")
        closes = hist["Close"].dropna()
        # 외환 등 주말 포함 티커: 평일만 필터링
        weekday_closes = closes[closes.index.dayofweek < 5]
        if len(weekday_closes) >= 2:
            closes = weekday_closes
        if len(closes) < 2:
            return None
        price = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        change_pct = round((price - prev) / prev * 100, 2)
        return {"price": round(price, 2), "change_pct": change_pct}
    except Exception:
        return None


def fetch_sector_stocks() -> dict:
    """섹터별 대표 종목·ETF의 전일 종가·등락률을 수집한다.
    sector_focus 브리핑에서 Claude가 실제 수치를 인용할 수 있도록 한다.
    """
    result = {}
    for sector_key, cfg in SECTOR_FOCUS_STOCKS.items():
        stocks = []
        for ticker, name in cfg["ko"]:
            d = _get_price_change(ticker)
            if d:
                stocks.append({"name": name, "ticker": ticker, **d})
            else:
                print(f"[fetch_data] sector stock {ticker}({name}) 수집 실패", file=sys.stderr)
        etfs = {}
        for etf_name, etf_ticker in cfg["etfs"]:
            d = _get_price_change(etf_ticker)
            if d:
                etfs[etf_name] = {"ticker": etf_ticker, **d}
            else:
                print(f"[fetch_data] sector ETF {etf_ticker} 수집 실패", file=sys.stderr)
        result[sector_key] = {"stocks": stocks, "etfs": etfs}
    return result


def _bridge_change_pct(entry) -> float | None:
    """등락률을 숫자일 때만 꺼낸다 — None·문자열은 결측 취급(평균 계산 시 TypeError 방지).
    bool은 int의 서브클래스라 isinstance(True, int)가 True로 나오므로 별도로 걸러낸다
    (예: "change_pct": true 가 1.0%로 둔갑하는 사고 방지)."""
    if not isinstance(entry, dict):
        return None
    v = entry.get("change_pct")
    if isinstance(v, bool):
        return None
    return float(v) if isinstance(v, (int, float)) else None


def fetch_overnight_bridge(macro: dict, snapshot: dict, today: date | None = None) -> list | None:
    """섹터별 간밤 미국 정규장 vs 한국 직전 마감 등락 비교(§24 이중계상 UI화, 순수함수).

    macro: get_ticker_full() 결과 딕셔너리 (티커 → {price, change_pct, ...}, 실패한 티커는 키 자체가 없음).
    snapshot: web/data/stocks-snapshot.json 파싱 결과.
    today: 기준 날짜(KST). 생략하면 실행 시각의 KST 날짜. 테스트에서 시계 고정용으로만 넘긴다.
    반환: [{"sector","us_label","us_change","kr_label","kr_change","gap_pp","kr_session_date"}, ...]
          또는 None(섹션 생략).

    신선도는 snapshot.get("generated_at")(스냅샷을 "언제 만들었나")가 아니라
    snapshot.get("session_date")(실제로 반영된 한국 종목 마지막 봉이 "며칠자 장인가")로
    판정한다. generated_at은 네이버가 아직 당일 봉을 안 올린 채로 잡이 실행되면 실제
    반영된 봉보다 하루 앞서갈 수 있다(build_stocks_snapshot.py 상단 경고 참조) — 그
    어긋남을 그대로 두면 "N일 이내" 검사든 "직전 개장일과 정확히 일치" 검사든 잘못된
    날짜를 옳다고 통과시킨다. session_date는 build_stocks_snapshot.py가 실제 종가 봉의
    날짜에서 직접 뽑아 기록하므로 이 값만 신뢰한다. session_date가 없으면(구버전 스냅샷
    등) generated_at으로 폴백하지 않고 섹션을 생략한다 — 폴백은 이 사고를 그대로
    재현하는 길이다.
    """
    if not isinstance(macro, dict) or not isinstance(snapshot, dict):
        print("[fetch_data] overnight_bridge: 입력 형식이 예상과 달라 섹션 생략", file=sys.stderr)
        return None

    session_date_str = snapshot.get("session_date")
    if not isinstance(session_date_str, str) or not session_date_str:
        print("[fetch_data] overnight_bridge: stocks-snapshot.json에 session_date가 없음 — 섹션 생략", file=sys.stderr)
        return None
    try:
        snap_date = datetime.strptime(session_date_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"[fetch_data] overnight_bridge: session_date({session_date_str}) 파싱 실패 — 섹션 생략", file=sys.stderr)
        return None

    # stock_universe.json 로드 실패와 동일한 이유로 fail-closed — 임포트 실패가 그대로
    # 새어나가면 07:25 코스피 데이터 수집 전체가 죽는다. 섹션만 생략하고 넘어간다.
    try:
        try:
            from scripts.session_label import prev_kospi_session
        except ImportError:
            from session_label import prev_kospi_session
    except ImportError as e:
        print(f"[fetch_data] overnight_bridge: session_label 임포트 실패({e}) — 섹션 생략", file=sys.stderr)
        return None

    ref_date = today or datetime.now(KST).date()
    prev_session = prev_kospi_session(ref_date)
    if prev_session is None or snap_date != prev_session:
        print(
            f"[fetch_data] overnight_bridge: session_date({snap_date})가 직전 코스피 개장일"
            f"({prev_session})과 불일치 — 섹션 생략",
            file=sys.stderr,
        )
        return None

    # 유니버스는 저장소에 커밋된 파일이라 정상 상태에선 항상 읽히지만,
    # 여기서 예외가 나면 브리핑 발행 자체가 죽는다 — 섹션만 생략하고 넘어간다.
    universe_path = BASE_DIR / "scripts" / "config" / "stock_universe.json"
    try:
        with open(universe_path, encoding="utf-8") as f:
            sectors = json.load(f)["sectors"]
        if not isinstance(sectors, dict):
            raise ValueError("sectors가 객체가 아님")
    except Exception as e:
        print(f"[fetch_data] overnight_bridge: stock_universe.json 로드 실패({e}) — 섹션 생략", file=sys.stderr)
        return None

    snap_stocks = snapshot.get("stocks")
    if not isinstance(snap_stocks, dict):
        print("[fetch_data] overnight_bridge: stocks-snapshot.json stocks 형식 오류 — 섹션 생략", file=sys.stderr)
        return None

    rows = []
    for key, us_tickers in BRIDGE_US_TICKERS.items():
        cfg = sectors.get(key)
        if not isinstance(cfg, dict):
            continue

        # 표시 이름은 stock_universe.json bellwethers에서만 가져온다(§20·§30).
        # 거기 없는 티커는 검증된 이름이 없으므로 결측 취급하고 건너뛴다 — 이름 없이
        # 티커만으로 라벨을 지어내지 않는다.
        bw_names = {
            b["t"]: b.get("name") for b in (cfg.get("bellwethers") or [])
            if isinstance(b, dict) and b.get("t")
        }
        us_contrib = []
        for t in us_tickers:
            name = bw_names.get(t)
            if not name:
                print(
                    f"[fetch_data] overnight_bridge: {key} 티커 {t}가 bellwethers에 없어 "
                    "표시 이름 불명 — 결측 취급",
                    file=sys.stderr,
                )
                continue
            v = _bridge_change_pct(macro.get(t))
            if v is not None:
                us_contrib.append((name, v))
        if not us_contrib:
            print(f"[fetch_data] overnight_bridge: {key} 미국 벨웨더 수집 실패 — 해당 섹터 생략", file=sys.stderr)
            continue

        kr_codes = [s["code"] for s in (cfg.get("stocks") or [])[:2] if isinstance(s, dict) and s.get("code")]
        kr_vals, kr_names = [], []
        for code in kr_codes:
            s = snap_stocks.get(code)
            v = _bridge_change_pct(s)
            if v is not None:
                kr_vals.append(v)
                kr_names.append(s.get("name") or code)
        if not kr_vals:
            print(f"[fetch_data] overnight_bridge: {key} 한국 대표종목 데이터 없음 — 해당 섹터 생략", file=sys.stderr)
            continue

        us_vals = [v for _, v in us_contrib]
        us_change = round(sum(us_vals) / len(us_vals), 2)
        kr_change = round(sum(kr_vals) / len(kr_vals), 2)
        rows.append({
            "sector": cfg.get("label", key),
            "us_label": "·".join(name for name, _ in us_contrib),
            "us_change": us_change,
            "kr_label": "·".join(kr_names),
            "kr_change": kr_change,
            "gap_pp": round(kr_change - us_change, 1),
            "kr_session_date": snap_date.isoformat(),
        })

    return rows or None


def fetch_kospi_data() -> dict:
    """Fetch ALL data needed for KOSPI morning briefing."""
    print("[fetch_data] Fetching KOSPI data...")

    # 1. Sidebar market data (hourly sparklines + price)
    print("[fetch_data]   → sidebar market data")
    market_data_js = build_sidebar_market_data(SIDEBAR_TICKERS_KOSPI)

    # 2. Additional macro tickers (not in sidebar)
    print("[fetch_data]   → macro tickers")
    macro_tickers = ["^GSPC", "^VIX", "BZ=F", "GC=F", "^TNX",
                     "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "^SOX", "EWY",
                     "DRAM",  # Roundhill Memory & HBM ETF (삼성·하이닉스 연동 선행 지표)
                     # 미 지수선물 — 브리핑 생성 시각(07:25 KST)에 **유일하게 실시간인** 신호.
                     # SOX·나스닥·EWY는 전부 6시간 이상 묵은 미국장 종가다.
                     # NQ=F는 이미 사이드바(market_data_js.nq)에 있고, ES/YM은 그동안
                     # 미국 브리핑 경로에만 있어 코스피 prior가 쓰지 못했다.
                     "ES=F", "YM=F",
                     "^N225", "^HSI", "^TWII", "000001.SS",  # 아시아 지역 지수 (catch-up 시그널)
                     # overnight_bridge 섹터 벨웨더 — BRIDGE_US_TICKERS(위 상수) 참조.
                     "SOXX", "GEV", "VRT", "ITA", "LIT", "TSLA", "F", "XBI", "KBE"]
    macro = {}
    for t in macro_tickers:
        d = get_ticker_full(t)
        if "error" not in d:
            macro[t] = d

    # VIX를 사이드바 market_data_js에 포함 (UI 표시용)
    if macro.get("^VIX"):
        market_data_js["vix"] = macro["^VIX"]

    # 4. Korean stock candidates (Kellogg strategy screening)
    print("[fetch_data]   → KOSPI candidates")
    kospi_candidates = build_stock_candidates(KOSPI_CANDIDATES)

    # 5. 경제 지표 캘린더 (ForexFactory)
    print("[fetch_data]   → economic calendar")
    economic_calendar = fetch_economic_calendar()

    # 6. 투자자별 순매수 (pykrx — 전 거래일)
    print("[fetch_data]   → investor trading (외국인/기관 순매수)")
    investor_trading = fetch_investor_trading_kospi()

    # 7. 섹터 대표 종목 데이터 (sector_focus 할루시네이션 방지)
    print("[fetch_data]   → sector focus stocks")
    sector_stocks = fetch_sector_stocks()

    # 7b. 간밤 미국-한국 섹터 갭 브리지 (overnight_bridge, §24 이중계상 UI화)
    print("[fetch_data]   → overnight bridge")
    snapshot_path = BASE_DIR / "web" / "data" / "stocks-snapshot.json"
    # 이 섹션은 부가 요소다 — 스냅샷을 읽다 어떤 예외가 나든 브리핑 발행 자체를 막지 않는다.
    # FileNotFoundError·JSONDecodeError만 잡으면 PermissionError·UnicodeDecodeError·
    # IsADirectoryError가 그대로 올라가 07:25 브리핑이 통째로 죽는다(§0 부칙).
    # fetch_overnight_bridge 안의 stock_universe.json 로드도 같은 이유로 except Exception이다.
    try:
        with open(snapshot_path, encoding="utf-8") as f:
            stocks_snapshot = json.load(f)
    except Exception as e:
        print(f"[fetch_data] overnight_bridge: 스냅샷 로드 실패({type(e).__name__}: {e}) — 섹션 생략", file=sys.stderr)
        stocks_snapshot = {}
    overnight_bridge = fetch_overnight_bridge(macro, stocks_snapshot)

    # 8. 휴장 직후(post-holiday catch-up) 플래그 — 한국만 단독 휴장한 다음날 판정
    print("[fetch_data]   → post-holiday catch-up flag")
    try:
        from holiday_check import was_kospi_only_closed_previous_session
        post_holiday_catchup = was_kospi_only_closed_previous_session(datetime.now(KST).date())
    except Exception as e:
        print(f"[fetch_data] post-holiday check error: {e}", file=sys.stderr)
        post_holiday_catchup = False
    print(f"[fetch_data]   post_holiday_catchup={post_holiday_catchup}")

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "kospi",
        # Ready-to-inject MARKET_DATA (just add stockCharts from picked candidates)
        "market_data_js": market_data_js,
        # Macro data
        "sp500":  macro.get("^GSPC", {}),
        "vix":    macro.get("^VIX", {}),
        "ewy":    macro.get("EWY", {}),
        "dram_etf": macro.get("DRAM", {}),  # Roundhill Memory ETF (HBM·DRAM 수요 선행)
        # 미 지수선물 (07:25 KST 기준 실시간). nasdaq_fut은 사이드바와 같은 NQ=F를 재사용한다.
        "futures": {
            "sp500_fut":  macro.get("ES=F", {}),
            "nasdaq_fut": market_data_js.get("nq", {}),
            "dow_fut":    macro.get("YM=F", {}),
        },
        "oil": {
            "wti":   market_data_js.get("oil", {}),
            "brent": macro.get("BZ=F", {}),
        },
        "gold":   macro.get("GC=F", {}),
        "rates":  {"us10y": macro.get("^TNX", {})},
        "bigtech": {t: macro.get(t, {}) for t in ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]},
        # 경제 지표 캘린더 (오늘 + 이번주 고영향 이벤트)
        "economic_calendar": economic_calendar,
        # 투자자별 순매수 (외국인/기관/개인 — 전 거래일 KRX 기준)
        "investor_trading": investor_trading,
        # 아시아 지역 지수 (직전 거래일 종가) — 한국 단독 휴장 다음날 catch-up 시그널
        "asia_regional": {
            "nikkei":   macro.get("^N225", {}),
            "hangseng": macro.get("^HSI", {}),
            "taiwan":   macro.get("^TWII", {}),
            "shanghai": macro.get("000001.SS", {}),
        },
        # True면 어제 한국만 휴장 + 미국 개장 — EWY보다 asia_regional이 더 정확한 선행 지표
        "post_holiday_catchup": post_holiday_catchup,
        # Kellogg screening — sorted by signal quality
        # Claude picks 3-5 from this list; use sparkline/ma20_sparkline/ma200_sparkline for stockCharts
        "kospi_candidates": kospi_candidates,
        # 섹터 로테이션 — 대표 종목·ETF 전일 종가·등락률 (할루시네이션 방지용 실제 데이터)
        "sector_stocks": sector_stocks,
        # 간밤 미국-한국 섹터 갭 브리지 — None이면 섹션 생략 (§0 없으면 비운다)
        "overnight_bridge": overnight_bridge,
    }

    # 품질 게이트: 핵심 지수 데이터 누락 시 발행 중단
    missing = [k for k in ("sp500", "vix") if not data.get(k, {}).get("price")]
    if missing or not data.get("market_data_js"):
        print(f"[fetch_data] ERROR: 핵심 시장 데이터 누락 {missing or ['market_data_js']} — 발행 중단", file=sys.stderr)
        sys.exit(1)

    out_path = DATA_DIR / "latest_kospi.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_data] KOSPI data saved → {out_path}")
    return data


def fetch_us_data() -> dict:
    """Fetch ALL data needed for US market evening briefing."""
    print("[fetch_data] Fetching US data...")

    # 1. Sidebar market data
    print("[fetch_data]   → sidebar market data")
    market_data_js = build_sidebar_market_data(SIDEBAR_TICKERS_US)

    # 2. Macro + futures
    print("[fetch_data]   → macro tickers")
    macro_tickers = [
        "^GSPC", "^VIX", "^TNX", "BZ=F", "GC=F",
        "ES=F", "YM=F",
        "^N225", "^HSI",
        "^GDAXI", "^FTSE", "^FCHI",
        "DRAM",   # Roundhill Memory & HBM ETF
    ]
    macro = {}
    for t in macro_tickers:
        d = get_ticker_full(t)
        if "error" not in d:
            macro[t] = d

    # VIX를 사이드바 market_data_js에 포함 (UI 표시용)
    if macro.get("^VIX"):
        market_data_js["vix"] = macro["^VIX"]

    # 4. US stock candidates
    print("[fetch_data]   → US candidates")
    us_candidate_pairs = [(t, t) for t in US_CANDIDATES]
    us_candidates = build_stock_candidates(us_candidate_pairs)
    # Overwrite name with ticker for US stocks
    for c in us_candidates:
        c["name"] = c["ticker"]

    # 5. 경제 지표 캘린더 (ForexFactory)
    print("[fetch_data]   → economic calendar")
    economic_calendar = fetch_economic_calendar()

    data = {
        "generated_at": datetime.now(KST).isoformat(),
        "type": "us",
        "market_data_js": market_data_js,
        "sp500":    macro.get("^GSPC", {}),
        "vix":      macro.get("^VIX", {}),
        "rates":    {"us10y": macro.get("^TNX", {})},
        "oil": {
            "wti":   market_data_js.get("oil", {}),
            "brent": macro.get("BZ=F", {}),
        },
        "gold":     macro.get("GC=F", {}),
        "futures": {
            "sp500_fut":   macro.get("ES=F", {}),
            "nasdaq_fut":  market_data_js.get("nq", {}),
            "dow_fut":     macro.get("YM=F", {}),
        },
        "asia": {
            "nikkei":   macro.get("^N225", {}),
            "kospi":    market_data_js.get("kospi", {}),
            "hangseng": macro.get("^HSI", {}),
        },
        "europe": {
            "dax":  macro.get("^GDAXI", {}),
            "ftse": macro.get("^FTSE", {}),
            "cac":  macro.get("^FCHI", {}),
        },
        "bigtech": {
            t: next((c for c in us_candidates if c["ticker"] == t), {})
            for t in ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA"]
        },
        "dram_etf":  macro.get("DRAM", {}),  # Roundhill Memory ETF (HBM·DRAM 수요 선행)
        # 경제 지표 캘린더 (오늘 + 이번주 고영향 이벤트)
        "economic_calendar": economic_calendar,
        "us_candidates": us_candidates,
    }

    # 품질 게이트: S&P500·VIX 누락 시 발행 중단
    missing = [k for k in ("sp500", "vix") if not data.get(k, {}).get("price")]
    if missing or not data.get("market_data_js"):
        print(f"[fetch_data] ERROR: 핵심 시장 데이터 누락 {missing or ['market_data_js']} — 발행 중단", file=sys.stderr)
        sys.exit(1)

    out_path = DATA_DIR / "latest_us.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[fetch_data] US data saved → {out_path}")
    return data



def main():
    parser = argparse.ArgumentParser(description="Fetch market data for DailyB")
    parser.add_argument(
        "--type",
        choices=["kospi", "us"],
        required=True,
        help="Type of briefing data to fetch",
    )
    args = parser.parse_args()

    try:
        if args.type == "kospi":
            fetch_kospi_data()
        elif args.type == "us":
            fetch_us_data()
        print(f"[fetch_data] Done — type={args.type}")
    except Exception as e:
        print(f"[fetch_data] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
