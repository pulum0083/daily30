# ETF 구성 데이터를 역집계해 종목별 패시브 자금 노출도를 산출한다
#!/usr/bin/env python3
"""
종목 → 패시브(ETF) 자금 노출도 파이프라인 (v1).

각 ETF의 AUM × 구성종목 비중을 역인덱스로 집계해, 개별 종목이
패시브 자금에 얼마나 노출돼 있는지 구조적 지표를 만든다. (인과 아님, 노출도)

지표:
  passive_value   = Σ(ETF_AUM × 비중)        — 종목에 연동된 패시브 자금(원)
  concentration   = passive_value / 시총       — 유동시총 대용(전체시총, 보수적)
  days_of_volume  = passive_value / ADV20      — 일평균 거래대금 며칠치
  score           = 두 지표를 0~100으로 결합한 민감도 점수

뱃지 (절대 AND 임계, 2026-06-13 분포 앵커):
  high : days_of_volume ≥ 8  AND concentration ≥ 10%
  mid  : days_of_volume ≥ 4  AND concentration ≥ 5%
  None : 그 외(표시 안 함)

데이터 소스 (전부 네이버, 무인증):
  - ETF 유니버스 : finance.naver.com/api/sise/etfItemList.nhn
  - ETF AUM·구성 : m.stock.naver.com/api/stock/{code}/etfAnalysis  (TOP10만 제공)
  - 종목 시총     : m.stock.naver.com/api/stock/{code}/integration
  - 종목 ADV20    : api.stock.naver.com/chart/domestic/item/{code}/day

한계: 네이버는 ETF당 TOP10 구성종목만 제공 → 롱테일 비중 누락(과소집계).
      큰 비중은 대부분 TOP10에 잡히므로 타겟(중소형 테마주)엔 영향이 작다.

산출: data/etf_exposure.json  (destination 랭킹 + 종목 위젯 공용)

Usage:
  python3 scripts/build_etf_exposure.py                       # 운영(상위150/보강80)
  python3 scripts/build_etf_exposure.py --etf-top 80 --stock-top 40
"""
import argparse
import json
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 뱃지 임계 (절대 AND). 운영 중 분포 변화 시 이 상수만 조정.
TH_HIGH = {"dov": 8.0, "conc": 10.0}
TH_MID = {"dov": 4.0, "conc": 5.0}

# 리츠·인프라는 거래가 거의 없는 배당상품 → days_of_volume이 폭발(유동성 부재).
# "테마 ETF가 성장주를 흔든다"는 제품 내러티브와 다른 종류라 v1은 제외. (나중에 별도 뷰 검토)
RE_EXCLUDE = re.compile(r"리츠|인프라|리얼티|맥쿼리|켄달스퀘어|REIT", re.I)


# ---------- 순수 함수 (네트워크 없음, 테스트 대상) ----------

def parse_kor_won(s):
    """'28조 2,132억' / '9,800억' / '16조 6,312억' → 정수(원). 숫자면 그대로."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    s = s.replace(",", "").strip()
    total = 0
    m = re.search(r"(\d+)\s*조", s)
    if m:
        total += int(m.group(1)) * 10**12
    m = re.search(r"(\d+)\s*억", s)
    if m:
        total += int(m.group(1)) * 10**8
    m = re.search(r"(\d+)\s*만", s)
    if m:
        total += int(m.group(1)) * 10**4
    if total == 0:
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else None
    return total


def classify_badge(conc, dov):
    """집중도(%)·거래일수 → 'high' | 'mid' | None."""
    if conc is None or dov is None:
        return None
    if dov >= TH_HIGH["dov"] and conc >= TH_HIGH["conc"]:
        return "high"
    if dov >= TH_MID["dov"] and conc >= TH_MID["conc"]:
        return "mid"
    return None


def composite_score(conc, dov, max_conc, max_dov):
    """두 지표를 관측 최댓값으로 정규화해 평균 → 0~100 정수."""
    if conc is None or dov is None or not max_conc or not max_dov:
        return None
    s = (min(conc / max_conc, 1.0) + min(dov / max_dov, 1.0)) / 2 * 100
    return round(s)


# ---------- 네트워크 ----------

def _getj(url, referer, encoding="utf-8"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    return json.loads(urllib.request.urlopen(req, timeout=12).read().decode(encoding, "replace"))


def fetch_etf_universe(top_n):
    """(거래량 상위 top_n [(코드,이름)], 전체 ETF 코드 set)."""
    # finance.naver.com 레거시 엔드포인트는 cp949(EUC-KR) — utf-8로 읽으면 ETF명이 깨진다.
    j = _getj("https://finance.naver.com/api/sise/etfItemList.nhn",
              "https://finance.naver.com/", encoding="cp949")
    lst = j.get("result", {}).get("etfItemList", [])
    all_codes = {x["itemcode"] for x in lst if x.get("itemcode")}
    active = [x for x in lst if x.get("quant")]
    active.sort(key=lambda x: x.get("quant", 0), reverse=True)
    return [(x["itemcode"], x["itemname"]) for x in active[:top_n]], all_codes


def fetch_etf_holdings(code):
    """(aum_won, [(종목코드, 비중%), ...]). 실패 시 (None, [])."""
    try:
        j = _getj(f"https://m.stock.naver.com/api/stock/{code}/etfAnalysis",
                  "https://m.stock.naver.com/")
    except Exception:
        return None, []
    aum = parse_kor_won(j.get("marketValue") or j.get("totalNav"))
    holds = []
    for h in j.get("etfTop10MajorConstituentAssets", []):
        ic = h.get("itemCode")
        wm = re.search(r"[\d.]+", str(h.get("etfWeight", "")))
        if ic and wm:
            holds.append((ic, float(wm.group()), h.get("itemName") or ""))
    return aum, holds


def fetch_stock_mcap(code):
    """(이름, 시총원). 실패 시 (None, None)."""
    try:
        j = _getj(f"https://m.stock.naver.com/api/stock/{code}/integration",
                  "https://m.stock.naver.com/")
    except Exception:
        return None, None
    mcap = None
    for b in j.get("totalInfos", []):
        if b.get("code") == "marketValue":
            mcap = parse_kor_won(b.get("value"))
    return j.get("stockName"), mcap


def fetch_adv20(code):
    """네이버 일봉 20거래일 평균 거래대금(원). 실패 시 None."""
    try:
        end = datetime.now().strftime("%Y%m%d") + "0000"
        start = (datetime.now() - timedelta(days=45)).strftime("%Y%m%d") + "0000"
        rows = _getj(
            f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
            f"?startDateTime={start}&endDateTime={end}", "https://m.stock.naver.com/")
        vals = [r["closePrice"] * r["accumulatedTradingVolume"]
                for r in rows[-20:]
                if r.get("closePrice") and r.get("accumulatedTradingVolume")]
        return sum(vals) / len(vals) if vals else None
    except Exception:
        return None


# ---------- 파이프라인 ----------

def build(etf_top, stock_top, sleep):
    universe, etf_codes = fetch_etf_universe(etf_top)
    print(f"[1/3] ETF {len(universe)}개 · 전체 ETF 코드 {len(etf_codes)}개 (역인덱스 제외용)")

    reverse, contrib = {}, {}
    etf_ok = 0
    for i, (code, name) in enumerate(universe):
        aum, holds = fetch_etf_holdings(code)
        if not aum or not holds:
            continue
        etf_ok += 1
        for ic, w, iname in holds:
            if ic in etf_codes:        # ETF가 다른 ETF의 구성종목으로 섞임 → 제외
                continue
            if RE_EXCLUDE.search(iname):   # 리츠·인프라 제외 (유동성 부재로 지표 왜곡)
                continue
            cv = aum * w / 100.0
            reverse[ic] = reverse.get(ic, 0) + cv
            contrib.setdefault(ic, []).append({"name": name, "weight_pct": w, "contrib_krw": cv})
        time.sleep(sleep)
    print(f"[2/3] 유효 ETF {etf_ok}개 · 역인덱스 종목 {len(reverse)}개 (ETF 제외 후)")

    ranked = sorted(reverse.items(), key=lambda kv: kv[1], reverse=True)[:stock_top]
    stocks = {}
    for ic, pv in ranked:
        name, mcap = fetch_stock_mcap(ic)
        time.sleep(sleep)
        adv = fetch_adv20(ic)
        time.sleep(sleep)
        conc = (pv / mcap * 100) if mcap else None
        dov = (pv / adv) if adv else None
        top_etfs = sorted(contrib[ic], key=lambda e: e["contrib_krw"], reverse=True)[:5]
        stocks[ic] = {
            "name": name, "passive_value_krw": round(pv), "mcap_krw": mcap,
            "concentration_pct": round(conc, 1) if conc is not None else None,
            "days_of_volume": round(dov, 1) if dov is not None else None,
            "badge": classify_badge(conc, dov),
            "top_etfs": [{"name": e["name"], "weight_pct": e["weight_pct"],
                          "contrib_krw": round(e["contrib_krw"])} for e in top_etfs],
        }
    print(f"[3/3] 상위 {len(stocks)}종목 시총·ADV20 보강 완료")

    # 민감도 점수 + destination 랭킹(뱃지 있는 종목, 거래일수 내림차순)
    flagged = [s for s in stocks.values() if s["badge"]]
    max_c = max((s["concentration_pct"] for s in flagged if s["concentration_pct"]), default=0)
    max_d = max((s["days_of_volume"] for s in flagged if s["days_of_volume"]), default=0)
    for code, s in stocks.items():
        s["score"] = composite_score(s["concentration_pct"], s["days_of_volume"], max_c, max_d)
    ranking = sorted(
        [{"code": c, **{k: stocks[c][k] for k in
          ("name", "concentration_pct", "days_of_volume", "score", "badge")},
          "top_etf": stocks[c]["top_etfs"][0]["name"] if stocks[c]["top_etfs"] else None}
         for c in stocks if stocks[c]["badge"]],
        key=lambda r: r["days_of_volume"], reverse=True)   # 기본 정렬 = 거래일수

    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "coverage": {"etf_count": etf_ok, "stock_count": len(stocks),
                     "note": "주요 ETF TOP10 구성 기준 추정, 소수 비중 누락 가능"},
        "thresholds": {"high": TH_HIGH, "mid": TH_MID},
        "ranking": ranking,
        "stocks": stocks,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etf-top", type=int, default=150)
    ap.add_argument("--stock-top", type=int, default=80)
    ap.add_argument("--sleep", type=float, default=0.12)
    ap.add_argument("--out", default="data/etf_exposure.json")
    args = ap.parse_args()

    out = build(args.etf_top, args.stock_top, args.sleep)
    with open(args.out, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n저장: {args.out}")
    print(f"패시브 민감주 {len(out['ranking'])}종목 (거래일수순 상위 10):")
    for r in out["ranking"][:10]:
        print(f"  {r['name']:<14} 집중도 {r['concentration_pct']:>5}% · "
              f"거래 {r['days_of_volume']:>5}일 · 민감도 {r['score']:>3} · [{r['badge']}]")


if __name__ == "__main__":
    main()
