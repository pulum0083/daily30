# 미국 대형주 월봉 5개월선 3개월 안착 조건의 과거 성과 — 미국 코너 하단 '1년 뒤 오른 비율' 문장의 출처(재실행 가능)
"""
코스피 백테스트(backtest_monthly_ma5.py)와 같은 방법·기간·집계 함수를 미국 후보 목록에 쓴다(§20 — 숫자를 코드에 박지 않는다).
산출물 scripts/config/monthly_ma5_us_backtest.json 을 커밋하고 generate_html이 읽는다.
- 대상: 미국 후보 목록(fetch_data.US_CANDIDATES) 현재 종목 — 생존 편향이 있다. 기준선(같은 종목·기간의 모든 달)과의 차이로 본다.
- 비교 지수: S&P500(^GSPC) — 출력 키 beat_index_pct.
실행:  python3 scripts/backtest_monthly_ma5_us.py   (네트워크 필요 — 야후 일봉)
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest_monthly_ma5 as bk  # noqa: E402
import monthly_ma5 as mm  # noqa: E402
import monthly_ma5_us as mu  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
OUT = Path(__file__).resolve().parent / "config" / "monthly_ma5_us_backtest.json"
PERIOD = "period1=1230768000&period2=1790726400"   # 2009-01-01 ~ 2026-09-30 UTC


def _summ(rows, h):
    s = bk.summarize(rows, h)
    if s is not None:
        s["beat_index_pct"] = s.pop("beat_kospi_pct")
    return s


def main():
    tickers = [t for t, _ in mu.universe()]
    data = {t: mu.yahoo_day_rows(t, period=PERIOD) for t in tickers}
    idx = {m["m"]: m["close"] for m in mm.month_end_series(mu.yahoo_day_rows("^GSPC", period=PERIOD))}
    ims = sorted(idx)

    def fwd(series, i, h):
        j = i + h
        return None if j >= len(series) or series[j]["m"] > bk.RESULT_TO else series[j]["close"] / series[i]["close"] - 1

    def ifwd(m, h):
        if m not in idx:
            return None
        i = ims.index(m)
        return None if i + h >= len(ims) or ims[i + h] > bk.RESULT_TO else idx[ims[i + h]] / idx[m] - 1

    base, signal = [], []
    for t in tickers:
        ms = mm.annotate([m for m in mm.month_end_series(data.get(t)) if m["m"] <= bk.RESULT_TO])
        for i, x in enumerate(ms):
            if not (bk.SIGNAL_FROM <= x["m"] <= bk.SIGNAL_TO) or x["ma5"] is None:
                continue
            row = {"r": {h: fwd(ms, i, h) for h in bk.HORIZONS}, "k": {h: ifwd(x["m"], h) for h in bk.HORIZONS}}
            base.append(row)
            if x["streak"] == mm.MIN_STREAK:
                signal.append(row)
    if not base:
        print("[backtest_ma5_us] 데이터 없음 — 중단", file=sys.stderr)
        sys.exit(1)
    out = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "universe": f"미국 대형주 {len(tickers)}종목(현재 후보 목록)",
        "universe_n": len(tickers),
        "signal_period": f"{bk.SIGNAL_FROM[:4]}-{bk.SIGNAL_FROM[4:]}~{bk.SIGNAL_TO[:4]}-{bk.SIGNAL_TO[4:]}",
        "years_label": f"{bk.SIGNAL_FROM[:4]}~{int(bk.SIGNAL_TO[:4])}",
        "method": "3개월째 안착이 처음 완성된 달의 월말 종가 기준. 기준선은 같은 종목·기간의 모든 달. 비교 지수 S&P500. 생존 편향 있음.",
        "horizons": {str(h): {"signal": _summ(signal, h), "base": _summ(base, h)} for h in bk.HORIZONS},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    h12 = out["horizons"]["12"]
    print(f"[backtest_ma5_us] 신호 {h12['signal']['n']}건 · 12개월 상승 {h12['signal']['win_pct']}% "
          f"(기준선 {h12['base']['win_pct']}%) → {OUT}")


if __name__ == "__main__":
    main()
