#!/usr/bin/env python3
"""
Market data fetcher for DailyB Investment Assistant.
Pre-collects ALL data needed for briefings so Claude makes ≤3 web searches per run.
"""

from __future__ import annotations  # `X | None` 어노테이션을 구버전 파이썬에서도 임포트 가능하게

import argparse
import json
import math
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# 역할별 모듈로 나눈 정의 — 원래 이름(fetch_data.X)으로도 그대로 읽힌다.
from market_common import (  # noqa: F401
    BASE_DIR, DATA_DIR, KST, UTC,
)
from market_universe import (  # noqa: F401
    SECTOR_FOCUS_STOCKS, US_CANDIDATES, SIDEBAR_TICKERS_KOSPI, SIDEBAR_TICKERS_US, BIGTECH_TICKERS, AI_INFRA_TICKERS,
)
from econ_calendar import fetch_earnings_near  # noqa: E402
import us_session_map  # noqa: E402
from econ_calendar import (  # noqa: F401
    _bucket_calendar_events, fetch_economic_calendar,
)
from investor_flow import (  # noqa: F401
    INVESTOR_TREND_URL, INVESTOR_TIME_URL, INVESTOR_TIME_DIR, INVESTOR_REGULAR_FROM, INVESTOR_REGULAR_UNTIL, INVESTOR_GUBUN,
    INVESTOR_INST_KEYS, _get_text, parse_investor_time_json, fetch_investor_time_rows, save_investor_time, load_investor_time,
    regular_session_investor, latest_investor_bizdate, fetch_investor_trading_kospi,
)
from price_quotes import (  # noqa: F401
    _PIN_ASIA_TICKERS, _pin_date_for, _truncate_at_pin, _yf_history, _prev_close_from_daily, _is_futures_like,
    _extended_hours_price, _NAVER_US_SUFFIX, _ET, _naver_us_basic, _num, naver_extended_quote,
    _yahoo_extended_fresh, _is_us_equity, FEED_ISSUES, FEED_ALERT_MIN_SUB, feed_alert_text, alert_feed_issues,
    _get_realtime_price, _recent_sessions, _ma200_position, get_ticker_full, get_hourly_sparkline,
)
from fx_rates import (  # noqa: F401
    _fx_change, _fx_from_naver_rows, _fx_from_manana, _fx_from_fawazahmed0, _fx_from_price_only, fetch_naver_usdkrw,
)

DATA_DIR.mkdir(exist_ok=True)


# CNN 공포·탐욕 지수 — 0~100 시장 심리 지표(투자자가 공포에 있는지 탐욕에 있는지).
# ⚠️ 2026-06-03에 제거된 옛 구현은 alternative.me/fng 를 "CNN Fear & Greed"라고 부르며
#    썼는데, 그건 **암호화폐** 심리 지수라 라벨과 실제 데이터가 달랐다(§0 위반). 다시
#    그 엔드포인트로 돌아가지 말 것 — 주식 시장 심리는 CNN dataviz가 정본이다.
_FNG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def get_fear_greed() -> dict:
    """CNN Fear & Greed Index 실측 수집. 실패하면 빈 dict(섹션 생략, §0)."""
    try:
        req = urllib.request.Request(_FNG_URL, headers={
            # 브라우저 헤더가 없으면 418을 준다 — GHA 러너(미국 Azure IP)에서 실측 확인.
            # 헤더를 붙이면 200 + 로컬과 동일한 값. 이 헤더 3줄을 지우지 말 것.
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://edition.cnn.com/",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode())
        fg = raw.get("fear_and_greed") or {}
        score = fg.get("score")
        if score is None:
            print("[fetch_data] Fear & Greed: score 없음 — 생략", file=sys.stderr)
            return {}
        out = {
            "score":      float(score),
            "rating":     (fg.get("rating") or "").strip().lower(),
            "prev_close": float(fg["previous_close"]) if fg.get("previous_close") is not None else None,
            "asof":       fg.get("timestamp"),   # ISO8601 (UTC)
            "source":     "cnn",
        }
        print(f"[fetch_data] Fear & Greed: {out['score']:.1f} ({out['rating']}) asof={out['asof']}")
        return out
    except Exception as e:
        # 실패해도 파이프라인을 막지 않는다 — 해당 행만 사라진다.
        print(f"[fetch_data] Fear & Greed API error: {e}", file=sys.stderr)
        return {}


# 미국 하이일드 회사채 스프레드 — ICE BofA US High Yield OAS(FRED BAMLH0A0HYM2).
# 신용이 낮은 미국 기업이 국채보다 더 얹어 내는 이자(%p). 빠르게 벌어지면 기업의 돈줄이 마른다는 신호다.
# FRED는 이 시리즈를 최근 3년치만 주고 하루 이틀 늦게 올린다 — 날짜(asof)를 함께 저장한다(§20).
_HY_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"


def parse_hy_csv(text: str) -> dict:
    """FRED CSV → 최신값·10거래일 변화·3년 분포 위치. 관측이 11개 미만이면 빈 dict."""
    rows = []
    for line in text.strip().splitlines()[1:]:
        parts = line.strip().split(",")
        if len(parts) != 2 or parts[1] in ("", "."):
            continue
        try:
            rows.append((parts[0], float(parts[1])))
        except ValueError:
            continue
    if len(rows) < 11:
        return {}
    date, val = rows[-1]
    base_date, base = rows[-11]
    vals = [v for _, v in rows]
    return {
        "value": val,
        "asof": date,
        "chg10": round(val - base, 2),
        "base_date": base_date,
        "pct_above": round(sum(v > val for v in vals) / len(vals) * 100),   # 3년 중 지금보다 높았던 날 비율
        # 직전 관측일 — 막대에 '어제' 점을 찍는다(10거래일 변화도 그날 기준으로 다시 잰다)
        "prev_value": rows[-2][1] if len(rows) >= 12 else None,
        "prev_date": rows[-2][0] if len(rows) >= 12 else None,
        "prev_chg10": round(rows[-2][1] - rows[-12][1], 2) if len(rows) >= 12 else None,
        "source": "fred:BAMLH0A0HYM2",
    }


def get_hy_spread() -> dict:
    """하이일드 스프레드 실측. 실패하면 빈 dict(행 생략, §0)."""
    text = ""
    try:
        req = urllib.request.Request(_HY_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode()
    except Exception as e:
        # 파이썬 urllib이 FRED에 붙지 못하는 경로가 있다(§86) — curl로 한 번 더
        try:
            import subprocess
            text = subprocess.run(["curl", "-s", "--max-time", "30", _HY_URL],
                                  capture_output=True, text=True, check=True).stdout
        except Exception as e2:
            print(f"[fetch_data] HY spread error: {e} / {e2}", file=sys.stderr)
            return {}
    out = parse_hy_csv(text)
    if out:
        print(f"[fetch_data] HY spread: {out['value']:.2f}% asof={out['asof']} 10일 {out['chg10']:+.2f}%p")
    else:
        print("[fetch_data] HY spread: 관측값 부족 — 생략", file=sys.stderr)
    return out


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
                    _c = naver["change_pct"]
                    _cs = f"{_c:+.2f}%" if _c is not None else "등락률 없음"
                    print(f"[fetch_data] sidebar {key}: {naver['price']:.2f} ({_cs}) [naver] [{len(sparkline)} pts]")
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
            "recent_sessions": data.get("recent_sessions", []),
        }
        result.append(entry)

    # Sort: crossing_up first, then above with small distance, then rest
    signal_priority = {"crossing_up": 0, "above": 1, "crossing_down": 2, "below": 3, "unknown": 4}
    result.sort(key=lambda x: (
        signal_priority.get(x["ma20_signal"], 4),
        abs(x["ma20_dist_pct"] or 999),
    ))
    return result


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


def _regular_session_change(ticker: str) -> dict | None:
    """미국 종목 하나의 **정규장 종가-종가** 등락률과 그 종가가 속한 세션 날짜를 돌려준다.

    반환: {"change_pct": float, "session_date": "YYYY-MM-DD"} 또는 None(수집 실패).

    **`get_ticker_full()`을 쓰면 안 된다.** 그쪽은 프리·애프터 체결가를 현재가로 채택한다(§26).
    직전 정규장 실측이 필요한 곳(미국 브리핑 `us_sector_session`, §79)은 일봉을 직접 읽는다.
    session_date는 마지막 일봉의 날짜(거래소 현지 = ET)다.
    """
    try:
        hist = _yf_history(ticker, period="1mo")  # interval 기본 1d, prepost 미지정 = 정규장만
        if hist is None or len(hist) < 2:
            return None
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None
        last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
        if not math.isfinite(last) or not math.isfinite(prev) or prev == 0:
            return None
        change = (last - prev) / prev * 100
        if not math.isfinite(change):
            return None
        session_date = closes.index[-1].date().isoformat()
    except Exception as e:
        print(f"[fetch_data] {ticker} 정규장 일봉 수집 실패({e})", file=sys.stderr)
        return None
    return {"change_pct": round(change, 2), "session_date": session_date}


def fetch_regular_session_changes(tickers) -> dict:
    """미국 티커들의 직전 정규장 등락률(네트워크). 티커 → _regular_session_change() 결과.
    실패한 티커는 키 자체가 빠진다 — 호출부가 결측으로 본다(§0).
    """
    out = {}
    for t in tickers:
        rec = _regular_session_change(t)
        if rec is not None:
            out[t] = rec
    return out


def fetch_kospi_data() -> dict:
    """Fetch ALL data needed for KOSPI morning briefing."""
    print("[fetch_data] Fetching KOSPI data...")

    # 1. Sidebar market data (hourly sparklines + price)
    print("[fetch_data]   → sidebar market data")
    market_data_js = build_sidebar_market_data(SIDEBAR_TICKERS_KOSPI)

    # 2. Additional macro tickers (not in sidebar)
    print("[fetch_data]   → macro tickers")
    macro_tickers = ["^GSPC", "^VIX", "BZ=F", "GC=F", "^TNX",
                     # ^IXIC·^DJI는 사이드바에도 있지만 그쪽은 period="1mo"라 52주 고·저가 없다.
                     # §28 게이트가 검증하는 네 지수(S&P500·나스닥·다우·SOX)의 52주 위치를
                     # 모델에게 미리 주려면 1년치를 읽는 이 경로가 필요하다.
                     "^IXIC", "^DJI",
                     "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "^SOX", "EWY",
                     # AI 인프라 — 메모리·칩·파운드리·서버·전력. 장 마감 뒤 실적 반응이 코스피 반도체로 이어진다(2026-11-18)
                     "MU", "AVGO", "TSM", "DELL", "VRT", "AMD", "ORCL",
                     "DRAM",  # Roundhill Memory & HBM ETF (삼성·하이닉스 연동 선행 지표)
                     # 미 지수선물 — 브리핑 생성 시각(07:25 KST)에 **유일하게 실시간인** 신호.
                     # SOX·나스닥·EWY는 전부 6시간 이상 묵은 미국장 종가다.
                     # NQ=F는 이미 사이드바(market_data_js.nq)에 있고, ES/YM은 그동안
                     # 미국 브리핑 경로에만 있어 코스피 prior가 쓰지 못했다.
                     "ES=F", "YM=F",
                     "^N225", "^HSI", "^TWII", "000001.SS"]  # 아시아 지역 지수 (catch-up 시그널)
    macro = {}
    for t in macro_tickers:
        d = get_ticker_full(t)
        if "error" not in d:
            macro[t] = d

    # VIX를 사이드바 market_data_js에 포함 (UI 표시용)
    if macro.get("^VIX"):
        market_data_js["vix"] = macro["^VIX"]

    # 공포·탐욕 지수 (CNN) — 사이드바 표시용. 실패 시 키 자체를 넣지 않는다.
    print("[fetch_data]   → fear & greed index")
    fng = get_fear_greed()
    if fng:
        market_data_js["fng"] = fng
    hy = get_hy_spread()
    if hy:
        market_data_js["hy"] = hy

    # 4. (2026-10-25 제거) 국내 켈로그 20일선 후보 — 코스피 아침의 상승 모멘텀 종목 코너를 뺐다.
    #    그 자리의 월봉 5개월선 안착 종목은 scripts/monthly_ma5.py가 따로 판정한다.

    # 5. 경제 지표 캘린더 (ForexFactory)
    print("[fetch_data]   → economic calendar")
    economic_calendar = fetch_economic_calendar()
    from session_label import prev_us_session
    _today_kst = datetime.now(KST)
    _prev_us = prev_us_session(_today_kst.date()) or _today_kst.date()

    # 6. 투자자별 순매수 (pykrx — 전 거래일)
    print("[fetch_data]   → investor trading (외국인/기관 순매수)")
    investor_trading = fetch_investor_trading_kospi()

    # 7. 섹터 대표 종목 데이터 (sector_focus 할루시네이션 방지)
    print("[fetch_data]   → sector focus stocks")
    sector_stocks = fetch_sector_stocks()

    # 8. 휴장 직후(post-holiday catch-up) 플래그 — 한국만 단독 휴장한 다음날 판정
    print("[fetch_data]   → post-holiday catch-up flag")
    try:
        from holiday_check import was_kospi_only_closed_previous_session
        post_holiday_catchup = was_kospi_only_closed_previous_session(datetime.now(KST).date())
    except Exception as e:
        print(f"[fetch_data] post-holiday check error: {e}", file=sys.stderr)
        post_holiday_catchup = False
    print(f"[fetch_data]   post_holiday_catchup={post_holiday_catchup}")
    try:   # 미국만 쉰 다음 날 — 미국 정규장 신호가 이미 코스피에 반영됐다(leading_signal이 점수에서 뺀다)
        from session_label import us_signals_stale
        us_signals_stale_flag = us_signals_stale(datetime.now(KST).date())
    except Exception as e:
        print(f"[fetch_data] us-signals-stale check error: {e}", file=sys.stderr)
        us_signals_stale_flag = False
    print(f"[fetch_data]   us_signals_stale={us_signals_stale_flag}")

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
        # 주요 지수의 52주 위치 — 모델이 "사상 최고" 같은 최상급을 쓸지 판단할 유일한 근거.
        # 이 값 없이 등락률만 보면 "+0.32% 상승"에서 "사상 최고 수준"으로 넘어가는 비약을
        # 막을 방법이 없다(2026-08-24·08-26 실사고 → 발행 차단). §28 게이트는 최종 방어선이고
        # 이건 1차 방어다. call_claude._index_position_directive()가 프롬프트로 옮긴다.
        "index_52w": {
            label: {k: macro[sym][k] for k in
                    ("price", "change_pct", "high_52w", "low_52w",
                     "pct_from_52w_high", "pct_from_52w_low")
                    if k in macro[sym]}
            for label, sym in (("S&P500", "^GSPC"), ("나스닥", "^IXIC"),
                               ("다우", "^DJI"), ("필라델피아 반도체", "^SOX"))
            if macro.get(sym, {}).get("high_52w")
        },
        # 최근 미국 세션 일지(날짜별 등락) — call_claude._us_session_log_directive()가 프롬프트로 옮긴다.
        "us_recent_sessions": {
            label: macro[sym]["recent_sessions"]
            for label, sym in (("나스닥", "^IXIC"), ("S&P500", "^GSPC"), ("필라델피아 반도체", "^SOX"))
            if macro.get(sym, {}).get("recent_sessions")
        },
        "gold":   macro.get("GC=F", {}),
        "rates":  {"us10y": macro.get("^TNX", {})},
        "bigtech": {t: macro.get(t, {}) for t in BIGTECH_TICKERS},
        "ai_infra": {t: macro[t] for t in AI_INFRA_TICKERS if t in macro},
        # 직전 미국장~오늘 사이 실적 발표 후보(야후 일정) — 발표 여부는 뉴스로 확인하게 한다(2026-11-18)
        "earnings_near": fetch_earnings_near(BIGTECH_TICKERS + AI_INFRA_TICKERS, _today_kst.date(), _prev_us),
        # 직전 미국 정규장 지도 — 지수·AI 칩·빅테크·섹터 ETF 정규장 등락(이슈 점검 '간밤 미국장' 카드, 2026-11-19)
        "us_session_map": us_session_map.collect(_prev_us.isoformat(), fetch_regular_session_changes),
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
        "us_signals_stale": us_signals_stale_flag,
        # 섹터 로테이션 — 대표 종목·ETF 전일 종가·등락률 (할루시네이션 방지용 실제 데이터)
        "sector_stocks": sector_stocks,
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
        "^IXIC", "^DJI", "^SOX",   # 200일선 이격(index_ma200) — 종목 홈 구조 신호
    ]
    macro = {}
    for t in macro_tickers:
        d = get_ticker_full(t)
        if "error" not in d:
            macro[t] = d

    # VIX를 사이드바 market_data_js에 포함 (UI 표시용)
    if macro.get("^VIX"):
        market_data_js["vix"] = macro["^VIX"]

    # 공포·탐욕 지수 (CNN) — 사이드바 표시용. 실패 시 키 자체를 넣지 않는다.
    print("[fetch_data]   → fear & greed index")
    fng = get_fear_greed()
    if fng:
        market_data_js["fng"] = fng
    hy = get_hy_spread()
    if hy:
        market_data_js["hy"] = hy

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
        # 직전 정규장 섹터 ETF 실측 — 이슈가 어느 섹터가 오르내렸는지 쓸 때의 근거(2026-11-05, §79)
        "us_sector_session": {
            name: fetch_regular_session_changes([t]).get(t)
            for name, t in (("금융", "XLF"), ("에너지", "XLE"), ("산업재", "XLI"), ("기술", "XLK"),
                            ("헬스케어", "XLV"), ("소비재", "XLY"), ("반도체", "SOXX"))
        },
        # 주요 지수의 200일선 이격(종가 기준) — 종목 홈 구조 신호가 밤에 보여준다(§68 ⑤)
        "index_ma200": {
            label: {"date": macro[sym]["close_date"], "pct": macro[sym]["ma200_close_pct"]}
            for label, sym in (("S&P500", "^GSPC"), ("나스닥", "^IXIC"), ("다우", "^DJI"), ("반도체", "^SOX"))
            if macro.get(sym, {}).get("close_date")
        },
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
        alert_feed_issues(args.type)
        print(f"[fetch_data] Done — type={args.type}")
    except Exception as e:
        print(f"[fetch_data] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
