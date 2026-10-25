# 월봉 5개월선 3개월 안착 조건의 과거 성과 — 브리핑 코너 하단 '12개월 상승 비율' 문장의 출처(재실행 가능)
"""
화면의 "같은 조건 뒤 12개월 동안 오른 경우는 N%"를 코드·템플릿에 박지 않기 위한 스크립트다(§20).
산출물 scripts/config/monthly_ma5_backtest.json 을 커밋하고, generate_html이 그 파일을 읽는다.

방법
- 대상: 코스피200 **현재** 구성종목(지금 살아남은 종목으로 과거를 돌려 생존 편향이 있다 — 기준선도 함께 부풀어 있으므로
  조건의 효과는 기준선과의 차이로 본다).
- 신호: 3개월째 안착이 처음 완성된 달(streak == 3)의 월말 종가에서 산 것으로 본다. 판정은 monthly_ma5와 같은 함수(§30).
- 기준선: 같은 종목·같은 기간의 모든 달.
- 기간: 신호 2011-01 ~ 2025-08. 결과 창은 2026-08 월말까지 — 2026-09 이후 네이버 일봉 종가는 애프터장을 포함해(§48) 쓰지 않는다.
- 이번 달 조건(라이브 판정의 ②)은 월말 시점엔 정의되지 않아 백테스트하지 않는다.
"""
import json
import statistics as st
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import monthly_ma5 as mm  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent / "config" / "monthly_ma5_backtest.json"
UA = {"User-Agent": "Mozilla/5.0"}
SIGNAL_FROM, SIGNAL_TO, RESULT_TO = "201101", "202508", "202608"
HORIZONS = (3, 6, 12)


def _get(url):
    for i in range(3):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read())
        except Exception:
            time.sleep(1 + i)
    return None


def kospi200_codes():
    codes = []
    for pg in range(1, 11):
        rows = _get(f"https://m.stock.naver.com/api/index/KPI200/enrollStocks?page={pg}&pageSize=50") or []
        new = [r["itemCode"] for r in rows if r.get("itemCode") and r["itemCode"] not in codes]
        if not new:
            break
        codes += new
    return codes


def daily(code):
    return _get(f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
                f"?startDateTime=200901010000&endDateTime={RESULT_TO}310000") or []


def kospi_month_closes():
    rows = _get("https://api.stock.naver.com/chart/domestic/index/KOSPI/month"
                f"?startDateTime=200901010000&endDateTime={RESULT_TO}310000") or []
    return {r["localDate"][:6]: float(r["closePrice"]) for r in rows}


def summarize(rows, h):
    v = [x["r"][h] for x in rows if x["r"][h] is not None]
    ex = [x["r"][h] - x["k"][h] for x in rows if x["r"][h] is not None and x["k"][h] is not None]
    if not v:
        return None
    return {"n": len(v), "win_pct": round(sum(a > 0 for a in v) / len(v) * 100, 1),
            "median_pct": round(st.median(v) * 100, 1),
            "loss10_pct": round(sum(a <= -0.10 for a in v) / len(v) * 100, 1),
            "beat_kospi_pct": round(sum(a > 0 for a in ex) / len(ex) * 100, 1) if ex else None}


def main():
    codes = kospi200_codes()
    if len(codes) < 150:
        print(f"[backtest_ma5] 코스피200 구성종목 {len(codes)}개만 받음 — 중단", file=sys.stderr)
        sys.exit(1)
    with ThreadPoolExecutor(8) as ex:
        data = dict(zip(codes, ex.map(daily, codes)))
    km = kospi_month_closes()
    kms = sorted(km)

    def fwd(series, i, h):
        j = i + h
        return None if j >= len(series) or series[j]["m"] > RESULT_TO else series[j]["close"] / series[i]["close"] - 1

    def kfwd(m, h):
        if m not in km:
            return None
        i = kms.index(m)
        return None if i + h >= len(kms) or kms[i + h] > RESULT_TO else km[kms[i + h]] / km[m] - 1

    base, signal = [], []
    for code in codes:
        ms = mm.annotate([m for m in mm.month_end_series(data.get(code)) if m["m"] <= RESULT_TO])
        for i, x in enumerate(ms):
            if not (SIGNAL_FROM <= x["m"] <= SIGNAL_TO) or x["ma5"] is None:
                continue
            row = {"r": {h: fwd(ms, i, h) for h in HORIZONS}, "k": {h: kfwd(x["m"], h) for h in HORIZONS}}
            base.append(row)
            if x["streak"] == mm.MIN_STREAK:
                fr0 = ms[i - mm.MIN_STREAK]["fr"] if i >= mm.MIN_STREAK else None
                row = dict(row, fr_chg=(x["fr"] - fr0) if (x["fr"] is not None and fr0 is not None) else None)
                signal.append(row)

    kept = [s for s in signal if s.get("fr_chg") is not None and s["fr_chg"] >= 0]
    dropped = [s for s in signal if s.get("fr_chg") is not None and s["fr_chg"] < 0]
    out = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "universe": "코스피200 현재 구성종목",
        "universe_n": len(codes),
        "signal_period": f"{SIGNAL_FROM[:4]}-{SIGNAL_FROM[4:]}~{SIGNAL_TO[:4]}-{SIGNAL_TO[4:]}",
        "years_label": f"{SIGNAL_FROM[:4]}~{int(SIGNAL_TO[:4])}",
        "method": "3개월째 안착이 처음 완성된 달의 월말 종가 기준. 기준선은 같은 종목·기간의 모든 달. 생존 편향 있음.",
        "horizons": {str(h): {"signal": summarize(signal, h), "base": summarize(base, h),
                              "foreign_kept": summarize(kept, h), "foreign_dropped": summarize(dropped, h)}
                     for h in HORIZONS},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    h12 = out["horizons"]["12"]
    print(f"[backtest_ma5] 신호 {h12['signal']['n']}건 · 12개월 상승 {h12['signal']['win_pct']}% "
          f"(기준선 {h12['base']['win_pct']}%) → {OUT}")


if __name__ == "__main__":
    main()
