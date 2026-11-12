# 배당·커버드콜 ETF의 분배 품질(건전성)을 실측 집계하는 인컴 설계기 파이프라인
#!/usr/bin/env python3
"""
배당 인컴 설계기 유니버스 파이프라인 (v2 — 미국 ETF 추가).

국내: 순자산 일정 규모 이상의 '월배당' 배당·커버드콜 ETF (네이버 API)
미국: 큐레이션 목록 기반 월배당 ETF (yfinance)

핵심 지표 — 1년 가격 변화(price_1y, erosion과 같은 값):
    ≥ 0          : 분배하면서 가격을 지킴 → 건전(ok)
    ≥ −분배율/2   : 소폭 깎임 → 주의(warn)
    <  −분배율/2  : 분배금에 원금이 섞임(원금성) → 경고(bad)
  return_1y = 1년 총수익(가격 변화 + 받은 분배금, 재투자 없음)

데이터 소스:
  국내 - 유니버스/가격/시총 : finance.naver.com/api/sise/etfItemList.nhn (cp949)
  국내 - 분배율·1년 가격 변화·과세 : m.stock.naver.com/api/stock/{code}/etfAnalysis (Y1은 가격 변화)
  미국 - 가격·배당·AUM     : yfinance
  환율 - USD/KRW          : yfinance (USDKRW=X)

산출: web/data/income_etfs.json  (사이드바 랭킹 + 시뮬레이터 공용)

Usage:
  python3 scripts/build_income_etfs.py                 # 운영(순자산 1,000억+)
  python3 scripts/build_income_etfs.py --aum-floor 10000   # 1조+
  python3 scripts/build_income_etfs.py --no-us        # 미국 ETF 제외
"""
import argparse
import json
import math
import re
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 국내 인컴 ETF 이름 패턴 (2026-06-17)
NAME_PAT = re.compile(r"커버드콜|배당|프리미엄|인컴|고배당|위클리|데일리|리츠|CD금리|CD1년금리|KOFR금리|단기채권|미국채혼합")

# 미국 인컴 ETF 큐레이션 목록 (ticker → 한국어 표시명)
US_ETF_NAMES = {
    "JEPI":  "JPMorgan 에쿼티프리미엄 (JEPI)",
    "JEPQ":  "JPMorgan 나스닥 에쿼티프리미엄 (JEPQ)",
    "QYLD":  "Global X 나스닥100 커버드콜 (QYLD)",
    "RYLD":  "Global X Russell2000 커버드콜 (RYLD)",
    "XYLD":  "Global X S&P500 커버드콜 (XYLD)",
    "TLTW":  "iShares 20년+ 국채 커버드콜 (TLTW)",
    "HYGW":  "iShares HY회사채 커버드콜 (HYGW)",
    "SPYI":  "NEOS S&P500 고인컴 (SPYI)",
    "QQQI":  "NEOS 나스닥100 고인컴 (QQQI)",
    "DIVO":  "Amplify CWP 강화배당 (DIVO)",
    "SCHD":  "Schwab 미국배당 (SCHD)",
    "DVY":   "iShares 셀렉트배당 (DVY)",
    "PFF":   "iShares 우선주·인컴 (PFF)",
    "QYLG":  "Global X 나스닥100 50%커버드콜 (QYLG)",
    "XYLG":  "Global X S&P500 50%커버드콜 (XYLG)",
    "BST":   "BlackRock 사이언스·테크 인컴 (BST)",
    "UTF":   "Cohen&Steers 인프라 인컴 (UTF)",
    "PGX":   "Invesco 우선주 (PGX)",
    "NUSI":  "Nationwide 리스크관리 인컴 (NUSI)",
}


# ---------- 순수 함수 (네트워크 없음, 테스트 대상) ----------

def is_income_etf(name):
    """이름 패턴으로 배당·커버드콜 ETF 여부 판정."""
    return bool(name and NAME_PAT.search(name))


def return_y1(perf_list):
    """returnPerformanceList에서 Y1(1년 총수익) 값을 추출. 없거나 NaN/inf(벤더 오류)면 None.

    네이버 API가 드물게 value에 NaN을 실어 보낸다 — json.dump는 이를 그대로 리터럴
    NaN으로 직렬화해 프론트 JSON.parse가 통째로 실패하는 사고(income-designer 0건 표시)로
    이어지므로, 소스에서부터 유한하지 않은 값은 데이터 없음(None)으로 처리한다.
    """
    for p in perf_list or []:
        if p.get("periodTypeCode") == "Y1":
            v = p.get("value")
            if isinstance(v, (int, float)) and not math.isfinite(v):
                return None
            return v
    return None


def classify_health(yield_ttm, price_1y):
    """1년 가격 변화로 원금이 지켜졌는지 판정 → ('ok'|'warn'|'bad', 가격 변화). 데이터 부족 시 (None, None).

    분배금을 받고도 가격이 1년 전 이상이면 원금이 지켜진 것(건전), 분배율의 절반까지 내리면 주의,
    그보다 더 내리면 분배금 상당 부분이 원금에서 나온 것(원금성)이다.

    2026-11-12 정정: 예전엔 '1년 수익 − 분배율'로 쟀는데 1년 수익의 뜻이 시장마다 달랐다.
    국내(네이버 Y1)는 분배금이 빠진 가격 변화라 분배율을 한 번 더 빼 실제보다 나쁘게(60개 중 23개 오판),
    미국은 수정 종가에 분배금을 다시 더해 실제보다 좋게 나왔다. 이제 가격 변화를 직접 받는다.
    """
    if yield_ttm is None or price_1y is None:
        return None, None
    p = round(price_1y, 2)
    if p >= 0:
        return "ok", p
    if p >= -yield_ttm / 2:
        return "warn", p
    return "bad", p


def total_from_price(price_1y, yield_ttm):
    """국내 1년 총수익(분배금 재투자 없이) = 가격 변화 + 받은 분배금 ÷ 1년 전 가격.

    네이버 분배율(TTM)은 최근 1년 분배금 ÷ 현재가라, 1년 전 가격 기준으로 바꾸면 분배율 × (1 + 가격 변화)다.
    """
    if price_1y is None or yield_ttm is None:
        return None
    return round(price_1y + yield_ttm * (1 + price_1y / 100), 2)


def parse_months(s):
    """'1,2,3,4,5' → [1,2,3,4,5]. 빈 값이면 []."""
    if not s:
        return []
    return [int(x) for x in re.findall(r"\d+", str(s))]


def is_new_fund(listed_date, today):
    """상장 1년 미만이면 True (분배율 TTM 신뢰도 낮음 플래그). listed_date='YYYYMMDD'."""
    if not listed_date or len(str(listed_date)) != 8:
        return False
    try:
        d = datetime.strptime(str(listed_date), "%Y%m%d").date()
    except ValueError:
        return False
    return (today - d).days < 365


def is_monthly(months, listed_date, today, was_monthly=False):
    """올해 지급 월(months)로 월배당 여부 판정. 분기·반기 배당 ETF를 걸러낸다.

    신생 펀드는 올해 분배 횟수가 적으므로 상장 후 경과한 '완료 월' 수를 기준으로 본다.
    이번 달은 아직 지급 전일 수 있어 1개월 여유를 둔다.

    1월엔 '올해 지급 월'이 아직 비어 있어 모든 ETF가 월배당이 아닌 것으로 판정됐다(2026-10-28 점검에서 발견).
    네이버 응답엔 지난해 지급 월이 없으므로, 1월에는 직전 갱신 파일에서 월배당이었던 종목(was_monthly)을 그대로 인정한다.
    """
    if today.month == 1 and not months:
        return bool(was_monthly)
    if not months:
        return False
    start = date(today.year, 1, 1)
    if listed_date and len(str(listed_date)) == 8:
        try:
            ld = datetime.strptime(str(listed_date), "%Y%m%d").date()
            if ld > start:
                start = ld
        except ValueError:
            pass
    elapsed = (today.year - start.year) * 12 + (today.month - start.month)
    need = max(1, elapsed - 1)  # 직전 달 미지급 1개월 허용
    return len(months) >= need


def regular_dividends(amounts, cap=12, spike=2.5):
    """최근 12개월 분배금에서 1회성 특별분배를 빼고 정기 분배만 남긴다(최근 cap회까지).

    2026-10-28 점검: QYLG·XYLG·BST가 연말 자본이득 특별분배(정기분의 10~17배)까지 연 분배율에 넣어
    17.2%·12.6%·14.0%로 나왔다(정기분 기준 약 7.5%·5.3%·6.2%). 중앙값의 spike배를 넘는 분배를 특별분배로 본다.
    1년 구간 양 끝에 같은 달 분배가 두 번 걸리면 13회가 되므로 최근 cap회만 쓴다.
    """
    vals = [float(a) for a in amounts if a is not None and math.isfinite(float(a)) and float(a) > 0]
    if not vals:
        return [], []
    srt = sorted(vals)
    mid = srt[len(srt) // 2] if len(srt) % 2 else (srt[len(srt) // 2 - 1] + srt[len(srt) // 2]) / 2
    regular = [v for v in vals if v <= mid * spike]
    special = [v for v in vals if v > mid * spike]
    return regular[-cap:], special


def enough_kr(new_count, prev_count, ratio=0.5):
    """국내 수집 결과가 직전 파일의 절반도 안 되면 원천 고장으로 보고 덮어쓰지 않는다(§47 — 0건 정상 종료 의심)."""
    if not prev_count:
        return new_count > 0
    return new_count >= prev_count * ratio



# ---------- 건전성 보드 지표 (2026-11-12, 네트워크 없음) ----------
# 화면: /stocks/income-designer/ 기본 화면(건전성 보드). 숫자는 전부 여기서 만든다 — 화면은 계산하지 않는다.

def category(name, is_cc):
    """'cc'(커버드콜·옵션 인컴) | 'bond'(채권·금리·우선주) | 'div'(배당주)."""
    n = name or ""
    if is_cc or "프리미엄" in n or "고인컴" in n:
        return "cc"
    if re.search(r"채권|국채|CD|KOFR|금리|우선주|회사채", n):
        return "bond"
    return "div"


def _ago(rows, today, days):
    """rows=[(YYYY-MM-DD, 종가)] 오름차순 → today에서 days일 전 이하의 마지막 종가."""
    cut = (today - timedelta(days=days)).isoformat()
    past = [c for d, c in rows if d <= cut]
    return past[-1] if past else None


def price_change(rows, today, days):
    """days일 전 대비 마지막 종가 변화(%). 그만큼 오래된 기록이 없으면 None."""
    if not rows:
        return None
    p0 = _ago(rows, today, days)
    if not p0:
        return None
    return round((rows[-1][1] / p0 - 1) * 100, 2)


def weekly_spark(rows, today):
    """최근 1년 종가를 5거래일마다 한 점으로(마지막 날은 꼭 넣는다). {'d': 날짜들, 'p': 종가들}."""
    cut = (today - timedelta(days=365)).isoformat()
    yr = [(d, c) for d, c in rows if d > cut]
    if len(yr) < 2:
        return None
    pts = yr[::5]
    if pts[-1] != yr[-1]:
        pts.append(yr[-1])
    return {"d": [d for d, _ in pts], "p": [round(c, 4) for _, c in pts]}


def monthly_dist(divs, today, price):
    """지난달까지 12개월의 월별 분배. divs=[(YYYY-MM-DD, 금액)]. 이번 달은 아직 지급 전일 수 있어 뺀다.

    [{'m': 'YYYY-MM', 'amt': 그달 합, 'n': 횟수, 'pct': 합 ÷ 지금 가격 × 100}]
    """
    out = []
    ym = today.year * 12 + today.month - 1
    for k in range(12, 0, -1):
        y, m = divmod(ym - k, 12)
        key = f"{y:04d}-{m + 1:02d}"
        ms = [a for d, a in divs if d[:7] == key]
        amt = round(sum(ms), 4)
        out.append({"m": key, "amt": amt, "n": len(ms),
                    "pct": round(amt / price * 100, 3) if price else None})
    return out


def dist_trend(divs, today):
    """최근 3개월 분배 평균 ÷ 1년 전 같은 시기(9~12개월 전) 분배 평균 − 1(%). 양쪽 다 2회 이상일 때만."""
    def window(lo, hi):
        a = (today - timedelta(days=hi)).isoformat()
        b = (today - timedelta(days=lo)).isoformat()
        return [x for d, x in divs if a < d <= b]
    recent, year_ago = window(0, 92), window(273, 365)
    if len(recent) < 2 or len(year_ago) < 2:
        return None
    r, y = sum(recent) / len(recent), sum(year_ago) / len(year_ago)
    return round((r / y - 1) * 100, 1) if y else None


# 기초 지수 비교 — 같은 지수를 추종하는 같은 시장 상장 ETF가 있을 때만(국내는 원화끼리, 미국은 달러끼리라 환율 영향이 빠진다)
KR_BENCH = {  # 키 → (비교 ETF 코드, 표시 이름)
    "nasdaq": ("133690", "나스닥100"), "sp500": ("360750", "S&P500"), "semi": ("381180", "미국 반도체"),
    "kospi": ("069500", "코스피200"), "krsemi": ("091160", "국내 반도체"), "usdiv": ("458730", "미국 배당다우존스"),
}
US_BENCH = {  # 티커 → (비교 티커, 표시 이름)
    "QYLD": ("QQQ", "나스닥100"), "QYLG": ("QQQ", "나스닥100"), "JEPQ": ("QQQ", "나스닥100"), "QQQI": ("QQQ", "나스닥100"),
    "XYLD": ("SPY", "S&P500"), "XYLG": ("SPY", "S&P500"), "SPYI": ("SPY", "S&P500"),
    "RYLD": ("IWM", "러셀2000"), "TLTW": ("TLT", "미국 20년+ 국채"), "HYGW": ("HYG", "하이일드 회사채"),
}


def kr_bench_key(base_index):
    """네이버 etfBaseIndex(기초 지수 이름) → KR_BENCH 키. 모르면 None(비교하지 않는다)."""
    b = (base_index or "").replace(" ", "").upper()
    if "NASDAQ-100" in b or "NASDAQ100" in b:
        return "nasdaq"
    if b.startswith("S&P500") or "S&P500COVERED" in b or "S&P50010%" in b:
        return "sp500"
    if "USLISTEDSEMICONDUCTOR" in b:
        return "semi"
    if "KRX반도체" in b or "FNGUIDE반도체" in b:
        return "krsemi"
    if b.startswith("코스피200") and "금융" not in b:
        return "kospi"
    if "DIVIDEND100" in b:
        return "usdiv"
    return None


# ---------- 네트워크 (국내) ----------

def _getj(url, referer, encoding="utf-8"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    return json.loads(urllib.request.urlopen(req, timeout=12).read().decode(encoding, "replace"))


def fetch_universe():
    """[(코드, 이름, 현재가, 시총_억)] — 인컴 이름 패턴만. finance.naver.com은 cp949."""
    j = _getj("https://finance.naver.com/api/sise/etfItemList.nhn",
              "https://finance.naver.com/", encoding="cp949")
    lst = j.get("result", {}).get("etfItemList", [])
    out = []
    for x in lst:
        name = x.get("itemname", "")
        if not is_income_etf(name):
            continue
        out.append((x.get("itemcode"), name, x.get("nowVal"), x.get("marketSum", 0)))
    return out


def fetch_analysis(code):
    """etfAnalysis dict 또는 None."""
    try:
        return _getj(f"https://m.stock.naver.com/api/stock/{code}/etfAnalysis",
                     "https://m.stock.naver.com/")
    except Exception:
        return None



def fetch_kr_daily(code, today):
    """네이버 일봉 [(YYYY-MM-DD, 종가)] 최근 약 13개월. 실패하면 []."""
    start = (today - timedelta(days=400)).strftime("%Y%m%d") + "0000"
    end = (today + timedelta(days=1)).strftime("%Y%m%d") + "0000"
    try:
        rows = _getj(f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime={start}&endDateTime={end}",
                     "https://m.stock.naver.com/")
    except Exception:
        return []
    out = []
    for r in rows or []:
        d, c = r.get("localDate"), r.get("closePrice")
        if d and c:
            out.append((f"{d[:4]}-{d[4:6]}-{d[6:8]}", float(c)))
    return sorted(out)


def fetch_yahoo_divs(symbol, today):
    """야후 분배 이력 [(YYYY-MM-DD, 금액)] 최근 약 13개월. 국내 ETF는 '.KS'. 실패하면 [].

    국내 ETF의 '가격'은 야후가 네이버와 크게 달라 쓰지 않는다 — 분배 이력만 쓴다(2026-11-12 대조:
    분배율 합계는 네이버 TTM과 일치, 1년 가격은 TIGER 배당커버드콜 야후 +10% vs 네이버 +42%).
    """
    try:
        import yfinance as yf
        dv = yf.Ticker(symbol).dividends
    except Exception:
        return []
    cut = (today - timedelta(days=400)).isoformat()
    out = []
    for ts, amt in dv.items():
        d = ts.strftime("%Y-%m-%d")
        if d > cut and amt and math.isfinite(float(amt)):
            out.append((d, float(amt)))
    return sorted(out)


def kr_bench_totals():
    """국내 비교 ETF의 1년 총수익(가격 변화 + 분배금, 재투자 없음) — 보드의 총수익과 같은 잣대."""
    out = {}
    for key, (code, label) in KR_BENCH.items():
        a = fetch_analysis(code)
        if not a:
            continue
        p1y = return_y1(a.get("returnPerformanceList"))
        y = (a.get("dividend") or {}).get("dividendYieldTtm") or 0
        tot = total_from_price(p1y, y)
        if tot is not None:
            out[key] = {"name": label, "total_1y": tot}
    return out


# ---------- 네트워크 (미국 — yfinance) ----------

def fetch_usd_krw():
    """현재 USD/KRW 환율. yfinance 실패 시 open.er-api 폴백. 모두 실패 시 None."""
    try:
        import yfinance as yf
        t = yf.Ticker("USDKRW=X")
        price = t.fast_info.get("last_price")
        if price and price > 1000:
            return round(float(price), 1)
    except Exception as e:
        print(f"  yfinance 환율 실패: {e}")
    try:
        import urllib.request as ur, json as _j
        r = _j.loads(ur.urlopen("https://open.er-api.com/v6/latest/USD", timeout=8).read())
        rate = r.get("rates", {}).get("KRW")
        if rate and rate > 1000:
            print(f"  open.er-api 폴백: {rate}")
            return round(float(rate), 1)
    except Exception as e:
        print(f"  open.er-api 환율 실패: {e}")
    return None


def us_total_1y(yf, ticker, cache):
    """미국 비교 ETF의 1년 총수익(실제 종가 기준 가격 변화 + 받은 분배금, 재투자 없음). 실패하면 None."""
    if ticker in cache:
        return cache[ticker]
    val = None
    try:
        import pandas as pd
        t = yf.Ticker(ticker)
        h = t.history(period="400d", auto_adjust=False)
        cutoff = pd.Timestamp.now(tz=h.index.tz) - pd.DateOffset(years=1)
        past = h[h.index <= cutoff]
        if not past.empty:
            p0, p1 = float(past["Close"].iloc[-1]), float(h["Close"].iloc[-1])
            dv = t.dividends
            got = float(dv[dv.index > cutoff].sum()) if not dv.empty else 0.0
            val = round((p1 - p0 + got) / p0 * 100, 2)
    except Exception as e:
        print(f"  bench {ticker} 실패: {e}")
    cache[ticker] = val
    return val


def build_us(usd_krw, sleep=0.5):
    """yfinance로 미국 인컴 ETF 수집. 월배당(연 6회+) ETF만 포함."""
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        print("  yfinance 미설치 — pip install yfinance pandas")
        return []

    one_year_ago = pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=1)
    etfs = []
    bench_cache = {}

    for ticker, name in US_ETF_NAMES.items():
        try:
            t = yf.Ticker(ticker)
            info = t.info

            price_usd = info.get("regularMarketPrice") or info.get("previousClose")
            if not price_usd:
                print(f"  skip {ticker} — 가격 없음")
                continue

            aum_usd = info.get("totalAssets") or 0
            aum_b = round(aum_usd / 1e9, 1)

            divs = t.dividends
            if divs.empty:
                print(f"  skip {ticker} — 배당 이력 없음")
                continue

            # 최근 12개월 배당만 집계 — 분배율은 정기 분배만(특별분배 제외), 총수익엔 받은 돈 전부를 넣는다
            recent = divs[divs.index > one_year_ago]
            regular, special = regular_dividends(list(recent.values))
            if len(regular) < 6:
                print(f"  skip {ticker} — 연 {len(regular)}회 정기 배당 (월배당 아님)")
                continue

            yield_ttm = round(sum(regular) / float(price_usd) * 100, 2)
            if yield_ttm <= 0:
                continue
            if special:
                print(f"  note {ticker} — 특별분배 {len(special)}회(${sum(special):.3f}) 분배율에서 제외")

            # 1년 총수익 = (현재가 - 1년전가 + 배당합) / 1년전가
            # auto_adjust=False — 기본값(True)은 분배금이 반영된 수정 종가라, 분배금을 다시 더하면 두 번 센다
            # (2026-11-12 발견: QQQI 1년 총수익이 실제 +8%인데 +22%로 나왔다)
            hist = t.history(period="400d", auto_adjust=False)
            return_1y = price_1y = None
            if len(hist) >= 200:
                tz = hist.index.tz
                cutoff = pd.Timestamp.now(tz=tz) - pd.DateOffset(years=1)
                past = hist[hist.index <= cutoff]
                if not past.empty:
                    p0 = float(past["Close"].iloc[-1])
                    p1 = float(hist["Close"].iloc[-1])
                    if p0 and math.isfinite(p0) and math.isfinite(p1):
                        return_1y = round((p1 - p0 + float(recent.sum())) / p0 * 100, 2)
                        price_1y = round((p1 / p0 - 1) * 100, 2)

            health, erosion = classify_health(yield_ttm, price_1y)
            price_krw = round(float(price_usd) * usd_krw) if usd_krw else None
            today = datetime.now(KST).date()
            rows = [(ix.strftime("%Y-%m-%d"), float(c)) for ix, c in hist["Close"].items() if math.isfinite(float(c))]
            dlist = [(ix.strftime("%Y-%m-%d"), float(a)) for ix, a in divs.items() if math.isfinite(float(a))]
            bench = None
            if ticker in US_BENCH:
                bt = us_total_1y(yf, US_BENCH[ticker][0], bench_cache)
                if bt is not None:
                    bench = {"name": US_BENCH[ticker][1], "total_1y": bt}

            etfs.append({
                "code": ticker,
                "name": name,
                "aum_b": aum_b,
                "price_usd": round(float(price_usd), 2),
                "price_krw": price_krw,
                "yield_ttm": yield_ttm,
                "return_1y": return_1y,
                "price_1y": price_1y,
                "erosion": erosion,
                "health": health,
                "is_cc": "커버드콜" in name,
                "low_confidence": False,
                "category": category(name, "커버드콜" in name),
                "price_3m": price_change(rows, today, 91),
                "spark": weekly_spark(rows, today),
                "dist_months": monthly_dist(dlist, today, float(price_usd)),
                "dist_trend": dist_trend(dlist, today),
                "bench": bench,
            })
            r_str = f"{return_1y}%" if return_1y is not None else "—"
            print(f"  ok   {ticker:6s} {name[:32]:34s} 분배 {yield_ttm}% · 총수익 {r_str} · ${aum_b}B")
            time.sleep(sleep)
        except Exception as e:
            print(f"  err  {ticker} — {e}")

    etfs.sort(key=lambda e: -(e["yield_ttm"] or 0))
    return etfs


# ---------- 조립 ----------

def build(aum_floor_eok, include_us=True, sleep=0.25, prev_kr_codes=None):
    today = datetime.now(KST).date()
    prev_monthly = set(prev_kr_codes or [])
    cands = [c for c in fetch_universe() if (c[3] or 0) >= aum_floor_eok]
    cands.sort(key=lambda c: -(c[3] or 0))
    etfs = []
    kr_bench = kr_bench_totals()
    print(f"  국내 비교 지수 {len(kr_bench)}/{len(KR_BENCH)}개: " + ", ".join(f"{v['name']} {v['total_1y']}%" for v in kr_bench.values()))
    for code, name, price, aum_eok in cands:
        a = fetch_analysis(code)
        if not a:
            continue
        div = a.get("dividend") or {}
        y = div.get("dividendYieldTtm")
        if not y or y <= 0:
            continue
        months = parse_months(div.get("dividendMonthThisYear"))
        if not is_monthly(months, a.get("listedDate"), today, was_monthly=code in prev_monthly):
            continue
        p1y = return_y1(a.get("returnPerformanceList"))   # 네이버 Y1은 분배금이 빠진 가격 변화다
        health, erosion = classify_health(y, p1y)
        r1y = total_from_price(p1y, y)
        is_cc = "커버드콜" in name
        rows = fetch_kr_daily(code, today)
        dlist = fetch_yahoo_divs(f"{code}.KS", today)
        bk = kr_bench_key(a.get("etfBaseIndex")) if category(name, is_cc) == "cc" else None
        etfs.append({
            "code": code,
            "name": name,
            "aum_jo": round(aum_eok / 10000, 2),
            "price": price,
            "yield_ttm": y,
            "return_1y": r1y,
            "price_1y": p1y,
            "erosion": erosion,
            "health": health,
            "is_cc": is_cc,
            "dividend_months": months,
            "fee": a.get("totalFee"),
            "tax_type": a.get("taxationTypeCode"),
            "listed_date": a.get("listedDate"),
            "low_confidence": is_new_fund(a.get("listedDate"), today),
            "category": category(name, is_cc),
            "price_3m": next((p.get("value") for p in a.get("returnPerformanceList") or []
                              if p.get("periodTypeCode") == "M3" and isinstance(p.get("value"), (int, float))), None),
            "spark": weekly_spark(rows, today),
            "dist_months": monthly_dist(dlist, today, price),
            "dist_trend": dist_trend(dlist, today),
            "base_index": a.get("etfBaseIndex"),
            "bench": kr_bench.get(bk) if bk else None,
        })
        time.sleep(sleep)
    etfs.sort(key=lambda e: -(e["yield_ttm"] or 0))

    us_etfs = []
    usd_krw = None
    if include_us:
        print("\n─── 미국 ETF 수집 ───")
        usd_krw = fetch_usd_krw()
        if usd_krw:
            print(f"  USD/KRW = {usd_krw}")
        else:
            print("  환율 조회 실패 — price_krw=null")
        us_etfs = build_us(usd_krw)

    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "usd_krw": usd_krw,
        "aum_floor_eok": aum_floor_eok,
        "coverage": {
            "kr_count": len(etfs),
            "us_count": len(us_etfs),
            "note": f"국내 {aum_floor_eok}억+ 월배당 ETF + 미국 큐레이션 ETF",
        },
        "etfs": etfs,
        "us_etfs": us_etfs,
    }


def sanitize_nonfinite(obj):
    """dict/list를 재귀 순회해 NaN·Infinity를 None으로 치환.

    json.dump(allow_nan=True 기본값)는 float('nan')을 리터럴 NaN으로 그대로 써버리는데,
    이건 유효한 JSON이 아니라 브라우저 JSON.parse가 통째로 실패한다(2026-08-02 실사고 —
    income-designer 페이지가 "전체 ETF 보기 (0)"으로 조용히 빈 화면이 됨). 소스 단계
    가드(return_y1 등)와 별개로, 예기치 못한 경로로 NaN이 섞여도 발행 직전에 반드시 걸러
    발행 중단 대신 "그 항목만 null(데이터 부족)"로 낮춰 서비스를 지킨다.
    """
    if isinstance(obj, dict):
        return {k: sanitize_nonfinite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_nonfinite(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aum-floor", type=int, default=1000, help="국내 순자산 하한 (억원)")
    ap.add_argument("--out", default="web/data/income_etfs.json")
    ap.add_argument("--no-us", action="store_true", help="미국 ETF 수집 건너뜀")
    args = ap.parse_args()
    prev = {}
    try:
        with open(args.out, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        pass
    prev_kr = [e.get("code") for e in (prev.get("etfs") or []) if isinstance(e, dict)]
    result = sanitize_nonfinite(build(args.aum_floor, include_us=not args.no_us, prev_kr_codes=prev_kr))
    if not enough_kr(result["coverage"]["kr_count"], len(prev_kr)):
        raise SystemExit(f"✗ 국내 {result['coverage']['kr_count']}개 — 직전 {len(prev_kr)}개의 절반 미만이라 원천 고장으로 보고 "
                         f"{args.out}을 덮어쓰지 않아요")
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    kr = result["coverage"]["kr_count"]
    us = result["coverage"]["us_count"]
    print(f"\n✓ 국내 {kr}개 + 미국 {us}개 = {kr+us}개 ETF → {args.out}")
    print("\n─── 국내 ETF ───")
    for e in result["etfs"]:
        flag = " ⚠신생" if e["low_confidence"] else ""
        print(f"  {e['health'] or '?':4s} {e['name'][:28]:30s} 분배 {e['yield_ttm']}% · 총수익 {e['return_1y']}% · 1년 가격 {e['price_1y']}%{flag}")


if __name__ == "__main__":
    main()
