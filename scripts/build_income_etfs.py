# 배당·커버드콜 ETF의 분배 품질(건전성)을 실측 집계하는 인컴 설계기 파이프라인
#!/usr/bin/env python3
"""
배당 인컴 설계기 유니버스 파이프라인 (v1).

순자산 일정 규모 이상의 '월배당' 배당·커버드콜 ETF를 모아, 분배율 대비 실제
총수익으로 "분배 품질(건전성)"을 판정한다. 분기·반기 배당 ETF는 dividendMonthThisYear
기준으로 걸러낸다(is_monthly).

핵심 지표 — 가격침식 프록시:
  erosion = 총수익(Y1) − 분배율(TTM)
    ≥ 0          : 가격을 지키며 분배 → 건전(ok)
    ≥ −분배율/2   : 소폭 침식 → 주의(warn)
    <  −분배율/2  : 분배금에 원금이 섞임(원금성) → 경고(bad)

  명시적 원금분배(ROC) 분해는 네이버에 없다. 위 프록시가 대체한다.
  총수익·NAV는 분배금 재투자 기준이라 가격만의 변화는 총수익−분배율로 추정.

데이터 소스 (전부 네이버, 무인증):
  - 유니버스/가격/시총 : finance.naver.com/api/sise/etfItemList.nhn (cp949)
  - 분배율·총수익·과세 : m.stock.naver.com/api/stock/{code}/etfAnalysis

산출: data/income_etfs.json  (사이드바 랭킹 + 시뮬레이터 공용)

Usage:
  python3 scripts/build_income_etfs.py                 # 운영(순자산 7천억+)
  python3 scripts/build_income_etfs.py --aum-floor 10000   # 1조+
"""
import argparse
import json
import re
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 인컴 ETF 이름 패턴 — 배당·분배 목적 상품. (실행 분포로 확정, 2026-06-13)
NAME_PAT = re.compile(r"커버드콜|배당|프리미엄|인컴|고배당|위클리|데일리|리츠")


# ---------- 순수 함수 (네트워크 없음, 테스트 대상) ----------

def is_income_etf(name):
    """이름 패턴으로 배당·커버드콜 ETF 여부 판정."""
    return bool(name and NAME_PAT.search(name))


def return_y1(perf_list):
    """returnPerformanceList에서 Y1(1년 총수익) 값을 추출. 없으면 None."""
    for p in perf_list or []:
        if p.get("periodTypeCode") == "Y1":
            return p.get("value")
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


# ---------- 네트워크 ----------

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


# ---------- 조립 ----------

def build(aum_floor_eok, sleep=0.25):
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
            continue  # 월배당 ETF만 — 분기·반기 배당 제외
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
            "dividend_months": months,
            "fee": a.get("totalFee"),
            "tax_type": a.get("taxationTypeCode"),
            "listed_date": a.get("listedDate"),
            "low_confidence": is_new_fund(a.get("listedDate"), today),
        })
        time.sleep(sleep)
    etfs.sort(key=lambda e: -(e["yield_ttm"] or 0))
    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "aum_floor_eok": aum_floor_eok,
        "coverage": {"etf_count": len(etfs),
                     "note": f"순자산 {aum_floor_eok//10000}조+ 배당·커버드콜 ETF" if aum_floor_eok >= 10000
                             else f"순자산 {aum_floor_eok}억+ 배당·커버드콜 ETF"},
        "etfs": etfs,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aum-floor", type=int, default=7000, help="순자산 하한 (억원)")
    ap.add_argument("--out", default="data/income_etfs.json")
    args = ap.parse_args()
    result = build(args.aum_floor)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✓ {result['coverage']['etf_count']}개 ETF → {args.out}")
    for e in result["etfs"]:
        flag = " ⚠신생" if e["low_confidence"] else ""
        print(f"  {e['health'] or '?':4s} {e['name'][:28]:30s} 분배 {e['yield_ttm']}% · 총수익 {e['return_1y']}% · 침식 {e['erosion']}%{flag}")


if __name__ == "__main__":
    main()
