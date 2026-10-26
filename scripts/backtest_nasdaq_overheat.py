# 나스닥 월봉 고점 vs 60개월선 구간별 과거 성과 — '나스닥 체크' 하단 설명·텔레그램 경고 문장의 출처(재실행 가능)
"""
화면·텔레그램의 "60% 넘은 달 N개월", "70% 넘은 달 뒤 12개월 안 −20% 비율 N%"를 코드·템플릿에 박지 않기 위한
스크립트다(§20). 산출물 scripts/config/nasdaq_overheat_backtest.json 을 커밋하고 generate_html이 읽는다.

방법(판정은 nasdaq_overheat와 같은 함수, §30)
- 대상: 1990-01 이후 60개월선을 계산할 수 있는 모든 달.
- 12개월 뒤 수익률: 12개월 뒤 월말 종가 ÷ 그 달 월말 종가 − 1.
- 12개월 안 −20%: 다음 12개월 월 저가의 최솟값 ÷ 그 달 월말 종가 − 1 ≤ −20%.
- 12개월 뒤 결과가 아직 없는 달은 그 통계에서만 뺀다(구간 달 수에는 넣는다).
실행:  python3 scripts/backtest_nasdaq_overheat.py   (네트워크 필요 — 야후 일봉)
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nasdaq_overheat as nq  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent / "config" / "nasdaq_overheat_backtest.json"
SINCE = "1990-01"
HORIZON = 12
DD = -20.0


def _year_runs(years: list) -> list:
    """[1997,1998,1999,2000,2020,2021] → ['1997~2000', '2020~2021']."""
    runs, start, prev = [], None, None
    for y in sorted(set(years)):
        if start is None:
            start = prev = y
        elif y == prev + 1:
            prev = y
        else:
            runs.append(f"{start}~{prev}" if prev > start else str(start))
            start = prev = y
    if start is not None:
        runs.append(f"{start}~{prev}" if prev > start else str(start))
    return runs


def backtest(months: list) -> dict:
    gs = nq.gap_series(months)
    rows = []
    for i, g in enumerate(gs):
        if g is None or g["m"] < SINCE:
            continue
        close = months[i]["close"]
        fwd = dd = None
        if i + HORIZON < len(months):
            fwd = (months[i + HORIZON]["close"] / close - 1) * 100
            dd = (min(x["low"] for x in months[i + 1:i + 1 + HORIZON]) / close - 1) * 100
        rows.append({"m": g["m"], "g": g["g"], "fwd": fwd, "dd": dd})

    def avg(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 1) if xs else None

    def dd_pct(rs):
        rs = [r for r in rs if r["dd"] is not None]
        return round(sum(1 for r in rs if r["dd"] <= DD) / len(rs) * 100, 1) if rs else None

    band = [r for r in rows if nq.CAUTION <= r["g"] < nq.WARN]
    warn = [r for r in rows if r["g"] >= nq.WARN]
    return {
        "since_year": int(SINCE[:4]),
        "months_total": len(rows),
        "months_over_caution": sum(1 for r in rows if r["g"] >= nq.CAUTION),
        "caution_band": {"months": len(band), "fwd12_n": sum(1 for r in band if r["fwd"] is not None),
                         "fwd12_avg_pct": avg(r["fwd"] for r in band)},
        "all_fwd12_avg_pct": avg(r["fwd"] for r in rows),
        "warn": {"months": len(warn), "dd20_n": sum(1 for r in warn if r["dd"] is not None),
                 "dd20_pct": dd_pct(warn), "periods": _year_runs([int(r["m"][:4]) for r in warn])},
        "all_dd20_pct": dd_pct(rows),
    }


def main():
    months = nq.monthly(nq.fetch_daily())
    out = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "symbol": nq.SYMBOL,
        "data_through": months[-1]["last_date"],
        "method": ("월봉 고점 ÷ 월말 종가 60개월 평균 − 1. 12개월 뒤 수익률은 월말 종가 기준, "
                   "−20% 하락은 다음 12개월 월 저가 최솟값 기준. 진행 중인 달 포함."),
        **backtest(months),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
