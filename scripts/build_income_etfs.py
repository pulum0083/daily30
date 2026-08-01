# 배당·커버드콜 ETF의 분배 품질(건전성)을 실측 집계하는 인컴 설계기 파이프라인
#!/usr/bin/env python3
"""
배당 인컴 설계기 유니버스 파이프라인 (v2 — 미국 ETF 추가).

국내: 순자산 일정 규모 이상의 '월배당' 배당·커버드콜 ETF (네이버 API)
미국: 큐레이션 목록 기반 월배당 ETF (yfinance)

핵심 지표 — 가격침식 프록시:
  erosion = 총수익(Y1) − 분배율(TTM)
    ≥ 0          : 가격을 지키며 분배 → 건전(ok)
    ≥ −분배율/2   : 소폭 침식 → 주의(warn)
    <  −분배율/2  : 분배금에 원금이 섞임(원금성) → 경고(bad)

데이터 소스:
  국내 - 유니버스/가격/시총 : finance.naver.com/api/sise/etfItemList.nhn (cp949)
  국내 - 분배율·총수익·과세 : m.stock.naver.com/api/stock/{code}/etfAnalysis
  미국 - 가격·배당·AUM     : yfinance
  환율 - USD/KRW          : yfinance (USDKRW=X)

산출: web/data/income_etfs.json  (사이드바 랭킹 + 시뮬레이터 공용)

Usage:
  python3 scripts/build_income_etfs.py                 # 운영(순자산 7천억+)
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


def classify_health(yield_ttm, return_1y):
    """가격침식 프록시로 건전성 판정 → ('ok'|'warn'|'bad', erosion). 데이터 부족 시 (None, None)."""
    if yield_ttm is None or return_1y is None:
        return None, None
    erosion = round(return_1y - yield_ttm, 2)
    if erosion >= 0:
        return "ok", erosion
    if erosion >= -yield_ttm / 2:
        return "warn", erosion
    return "bad", erosion


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


def is_monthly(months, listed_date, today):
    """올해 지급 월(months)로 월배당 여부 판정. 분기·반기 배당 ETF를 걸러낸다.

    신생 펀드는 올해 분배 횟수가 적으므로 상장 후 경과한 '완료 월' 수를 기준으로 본다.
    이번 달은 아직 지급 전일 수 있어 1개월 여유를 둔다.
    """
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

            # 최근 12개월 배당만 집계
            recent = divs[divs.index >= one_year_ago]
            if len(recent) < 6:
                print(f"  skip {ticker} — 연 {len(recent)}회 배당 (월배당 아님)")
                continue

            yield_ttm = round(float(recent.sum()) / float(price_usd) * 100, 2)
            if yield_ttm <= 0:
                continue

            # 1년 총수익 = (현재가 - 1년전가 + 배당합) / 1년전가
            hist = t.history(period="400d")
            return_1y = None
            if len(hist) >= 200:
                tz = hist.index.tz
                cutoff = pd.Timestamp.now(tz=tz) - pd.DateOffset(years=1)
                past = hist[hist.index <= cutoff]
                if not past.empty:
                    p0 = float(past["Close"].iloc[-1])
                    p1 = float(hist["Close"].iloc[-1])
                    if p0 and math.isfinite(p0) and math.isfinite(p1):
                        return_1y = round((p1 - p0 + float(recent.sum())) / p0 * 100, 2)

            health, erosion = classify_health(yield_ttm, return_1y)
            price_krw = round(float(price_usd) * usd_krw) if usd_krw else None

            etfs.append({
                "code": ticker,
                "name": name,
                "aum_b": aum_b,
                "price_usd": round(float(price_usd), 2),
                "price_krw": price_krw,
                "yield_ttm": yield_ttm,
                "return_1y": return_1y,
                "erosion": erosion,
                "health": health,
                "is_cc": "커버드콜" in name,
                "low_confidence": False,
            })
            r_str = f"{return_1y}%" if return_1y is not None else "—"
            print(f"  ok   {ticker:6s} {name[:32]:34s} 분배 {yield_ttm}% · 총수익 {r_str} · ${aum_b}B")
            time.sleep(sleep)
        except Exception as e:
            print(f"  err  {ticker} — {e}")

    etfs.sort(key=lambda e: -(e["yield_ttm"] or 0))
    return etfs


# ---------- 조립 ----------

def build(aum_floor_eok, include_us=True, sleep=0.25):
    today = datetime.now(KST).date()
    cands = [c for c in fetch_universe() if (c[3] or 0) >= aum_floor_eok]
    cands.sort(key=lambda c: -(c[3] or 0))
    etfs = []
    for code, name, price, aum_eok in cands:
        a = fetch_analysis(code)
        if not a:
            continue
        div = a.get("dividend") or {}
        y = div.get("dividendYieldTtm")
        if not y or y <= 0:
            continue
        months = parse_months(div.get("dividendMonthThisYear"))
        if not is_monthly(months, a.get("listedDate"), today):
            continue
        r1y = return_y1(a.get("returnPerformanceList"))
        health, erosion = classify_health(y, r1y)
        etfs.append({
            "code": code,
            "name": name,
            "aum_jo": round(aum_eok / 10000, 2),
            "price": price,
            "yield_ttm": y,
            "return_1y": r1y,
            "erosion": erosion,
            "health": health,
            "is_cc": "커버드콜" in name,
            "dividend_months": months,
            "fee": a.get("totalFee"),
            "tax_type": a.get("taxationTypeCode"),
            "listed_date": a.get("listedDate"),
            "low_confidence": is_new_fund(a.get("listedDate"), today),
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
    ap.add_argument("--aum-floor", type=int, default=7000, help="국내 순자산 하한 (억원)")
    ap.add_argument("--out", default="web/data/income_etfs.json")
    ap.add_argument("--no-us", action="store_true", help="미국 ETF 수집 건너뜀")
    args = ap.parse_args()
    result = sanitize_nonfinite(build(args.aum_floor, include_us=not args.no_us))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    kr = result["coverage"]["kr_count"]
    us = result["coverage"]["us_count"]
    print(f"\n✓ 국내 {kr}개 + 미국 {us}개 = {kr+us}개 ETF → {args.out}")
    print("\n─── 국내 ETF ───")
    for e in result["etfs"]:
        flag = " ⚠신생" if e["low_confidence"] else ""
        print(f"  {e['health'] or '?':4s} {e['name'][:28]:30s} 분배 {e['yield_ttm']}% · 총수익 {e['return_1y']}% · 침식 {e['erosion']}%{flag}")


if __name__ == "__main__":
    main()
