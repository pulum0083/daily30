# ETF 구성 데이터를 역집계해 종목별 패시브 자금 노출도를 산출한다
#!/usr/bin/env python3
"""
종목 → 패시브(ETF) 자금 노출도 파이프라인 (스파이크/MVP).

각 ETF의 AUM × 구성종목 비중을 역인덱스로 집계해, 개별 종목이
패시브 자금에 얼마나 노출돼 있는지 구조적 지표를 만든다. (인과 아님, 노출도)

지표:
  passive_value   = Σ(ETF_AUM × 비중)        — 종목에 연동된 패시브 자금(원)
  concentration   = passive_value / 시총       — 유동시총 대용(전체시총, 보수적)
  days_of_volume  = passive_value / ADV20      — 일평균 거래대금 며칠치

데이터 소스 (전부 네이버, 무인증):
  - ETF 유니버스 : finance.naver.com/api/sise/etfItemList.nhn
  - ETF AUM·구성 : m.stock.naver.com/api/stock/{code}/etfAnalysis  (TOP10만 제공)
  - 종목 시총     : m.stock.naver.com/api/stock/{code}/integration
  - 종목 ADV20    : api.stock.naver.com/chart/domestic/item/{code}/day

한계: 네이버는 ETF당 TOP10 구성종목만 제공 → 롱테일 비중 누락(과소집계).
      큰 비중은 대부분 TOP10에 잡히므로 타겟(중소형 테마주)엔 영향이 작다.

Usage:
  python3 scripts/build_etf_exposure.py --spike          # 분포만 출력(임계치 탐색)
  python3 scripts/build_etf_exposure.py --etf-top 120 --stock-top 60
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from statistics import quantiles

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _get(url, referer):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    return urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "replace")


def _getj(url, referer):
    return json.loads(_get(url, referer))


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
        # 순수 숫자 문자열
        digits = re.sub(r"[^\d]", "", s)
        return int(digits) if digits else None
    return total


def fetch_etf_universe(top_n):
    """거래대금(또는 거래량) 상위 ETF 코드 리스트."""
    j = _getj("https://finance.naver.com/api/sise/etfItemList.nhn",
              "https://finance.naver.com/")
    lst = j.get("result", {}).get("etfItemList", [])
    # 거래량(quant) 기준 정렬 — AUM 직접 필드가 목록엔 없어 거래량을 활동성 프록시로 사용
    lst = [x for x in lst if x.get("quant")]
    lst.sort(key=lambda x: x.get("quant", 0), reverse=True)
    return [(x["itemcode"], x["itemname"]) for x in lst[:top_n]]


def fetch_etf_holdings(code):
    """(aum_won, [(종목코드, 비중%), ...])  실패 시 (None, [])."""
    try:
        j = _getj(f"https://m.stock.naver.com/api/stock/{code}/etfAnalysis",
                  "https://m.stock.naver.com/")
    except Exception:
        return None, []
    aum = parse_kor_won(j.get("marketValue") or j.get("totalNav"))
    holds = []
    for h in j.get("etfTop10MajorConstituentAssets", []):
        ic = h.get("itemCode")
        w = h.get("etfWeight", "")
        wm = re.search(r"[\d.]+", str(w))
        if ic and wm:
            holds.append((ic, float(wm.group())))
    return aum, holds


def fetch_stock_mcap(code):
    try:
        j = _getj(f"https://m.stock.naver.com/api/stock/{code}/integration",
                  "https://m.stock.naver.com/")
    except Exception:
        return None, None
    mcap = None
    name = j.get("stockName")
    for b in j.get("totalInfos", []):
        if b.get("code") == "marketValue":
            mcap = parse_kor_won(b.get("value"))
    return name, mcap


def fetch_adv20(code):
    """네이버 일봉 20거래일 평균 거래대금(원). 실패 시 None."""
    try:
        from datetime import datetime, timedelta
        end = datetime.now().strftime("%Y%m%d") + "0000"
        start = (datetime.now() - timedelta(days=45)).strftime("%Y%m%d") + "0000"
        url = (f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
               f"?startDateTime={start}&endDateTime={end}")
        rows = _getj(url, "https://m.stock.naver.com/")
        vals = []
        for r in rows[-20:]:
            close = r.get("closePrice")
            vol = r.get("accumulatedTradingVolume")
            if close and vol:
                vals.append(close * vol)
        return sum(vals) / len(vals) if vals else None
    except Exception:
        return None


def pct(values, ps=(50, 75, 90, 95)):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {}
    out = {}
    n = len(vals)
    for p in ps:
        idx = min(n - 1, int(round(p / 100 * (n - 1))))
        out[p] = vals[idx]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etf-top", type=int, default=120)
    ap.add_argument("--stock-top", type=int, default=60)
    ap.add_argument("--spike", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.12)
    args = ap.parse_args()

    print(f"[1/4] ETF 유니버스 수집 (거래량 상위 {args.etf_top}) …", flush=True)
    universe = fetch_etf_universe(args.etf_top)
    print(f"      {len(universe)}개 ETF", flush=True)

    print("[2/4] ETF별 AUM·구성종목 수집 …", flush=True)
    reverse = {}   # 종목코드 -> passive_value(원)
    contrib = {}   # 종목코드 -> [(etf_name, weight, contrib_won)]
    etf_ok = 0
    for i, (code, name) in enumerate(universe):
        aum, holds = fetch_etf_holdings(code)
        if not aum or not holds:
            continue
        etf_ok += 1
        for ic, w in holds:
            cv = aum * w / 100.0
            reverse[ic] = reverse.get(ic, 0) + cv
            contrib.setdefault(ic, []).append((name, w, cv))
        if (i + 1) % 20 == 0:
            print(f"      {i+1}/{len(universe)} (유효 {etf_ok})", flush=True)
        time.sleep(args.sleep)
    print(f"      유효 ETF {etf_ok}개 · 역인덱스 종목 {len(reverse)}개", flush=True)

    # passive_value 상위 종목만 시총·ADV 보강 (낮은 노출은 민감주가 될 수 없음)
    ranked = sorted(reverse.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[:args.stock_top]
    print(f"[3/4] 상위 {len(top)}종목 시총·ADV20 보강 …", flush=True)

    rows = []
    for j, (ic, pv) in enumerate(top):
        nm, mcap = fetch_stock_mcap(ic)
        time.sleep(args.sleep)
        adv = fetch_adv20(ic)
        time.sleep(args.sleep)
        conc = (pv / mcap * 100) if mcap else None
        dov = (pv / adv) if adv else None
        rows.append({
            "code": ic, "name": nm,
            "passive_value": pv, "mcap": mcap,
            "concentration_pct": conc, "days_of_volume": dov,
        })
        if (j + 1) % 15 == 0:
            print(f"      {j+1}/{len(top)}", flush=True)

    print("[4/4] 분포 요약\n", flush=True)
    pv_all = [v for _, v in ranked]
    conc_vals = [r["concentration_pct"] for r in rows]
    dov_vals = [r["days_of_volume"] for r in rows]

    def fmt_won(x):
        if x is None:
            return "—"
        if x >= 1e12:
            return f"{x/1e12:.2f}조"
        return f"{x/1e8:.0f}억"

    print("■ passive_value 분포 (역인덱스 전체):")
    for p, v in pct(pv_all).items():
        print(f"    p{p}: {fmt_won(v)}")
    print("\n■ concentration(%) 분포 (상위 종목):")
    for p, v in pct(conc_vals).items():
        print(f"    p{p}: {v:.2f}%" if v is not None else f"    p{p}: —")
    print("\n■ days_of_volume 분포 (상위 종목):")
    for p, v in pct(dov_vals).items():
        print(f"    p{p}: {v:.1f}일" if v is not None else f"    p{p}: —")

    print("\n■ passive_value 상위 25종목:")
    print(f"    {'종목':<16}{'노출자금':>10}{'집중도':>9}{'거래일수':>9}")
    for r in rows[:25]:
        nm = (r["name"] or r["code"])[:14]
        c = f"{r['concentration_pct']:.1f}%" if r["concentration_pct"] is not None else "—"
        d = f"{r['days_of_volume']:.1f}일" if r["days_of_volume"] is not None else "—"
        print(f"    {nm:<16}{fmt_won(r['passive_value']):>10}{c:>9}{d:>9}")

    if not args.spike:
        out = {"rows": rows}
        with open("data/etf_exposure_spike.json", "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("\n저장: data/etf_exposure_spike.json")


if __name__ == "__main__":
    main()
