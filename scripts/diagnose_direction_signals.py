# 코스피 방향 예측의 선행신호 vs 모멘텀 적중률을 과거 데이터로 정량 진단하는 점검 스크립트
"""
점검 목적:
  코스피 D일 시초가 브리핑이 볼 수 있는 정보(= D 이전 마지막 미국장 종가)만으로
  '어느 신호가 다음날 코스피 방향을 잘 맞히는가'를 수치로 비교한다.

비교 규칙 (모두 부호만 본다):
  - EWY부호 / SOX부호 / VIX역부호 / 나스닥부호 / 결합 prior(가중)
  - 모멘텀: 전일 코스피 종가-종가 등락 부호 (현재 모델이 앵커링하는 기준)

시간 정렬:
  코스피[D] 아침은 D보다 '엄격히 이전'인 미국장 종가만 본다 → merge_asof(backward, exact=False).
  (미국장 종가 날짜 D는 코스피 D 마감 이후에 나오므로 사용 불가)
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leading_signal import SIGNAL_WEIGHTS

START = sys.argv[1] if len(sys.argv) > 1 else "2026-03-01"
END = sys.argv[2] if len(sys.argv) > 2 else None  # None = 오늘까지
DEADBAND = 0.3  # |등락률| < 0.3% 는 보합 노이즈 → 별도 집계

US_TICKERS = {
    "^IXIC": "nasdaq",
    "^GSPC": "sp500",
    "^SOX": "sox",
    "EWY": "ewy",
    "^VIX": "vix",
}


def pct(s):
    return s.pct_change() * 100


def main():
    kos = yf.download("^KS11", start=START, end=END, progress=False, auto_adjust=False)["Close"]
    if isinstance(kos, pd.DataFrame):
        kos = kos.squeeze("columns")
    kos = kos.dropna()
    kos_ret = pct(kos).dropna()
    kos_ret.name = "kospi"
    kos_df = kos_ret.to_frame()
    kos_df.index = pd.to_datetime(kos_df.index).tz_localize(None)
    # 모멘텀 = 전일(직전 코스피 거래일) 등락 부호
    kos_df["momentum_src"] = kos_df["kospi"].shift(1)

    us = yf.download(list(US_TICKERS), start=START, end=END, progress=False, auto_adjust=False)["Close"]
    us = us.rename(columns=US_TICKERS)
    us_ret = pct(us).dropna(how="all")
    us_ret.index = pd.to_datetime(us_ret.index).tz_localize(None)
    us_ret = us_ret.reset_index().rename(columns={"Date": "us_date", "index": "us_date"})
    us_ret.columns = ["us_date"] + list(us_ret.columns[1:])

    left = kos_df.reset_index().rename(columns={"Date": "kdate", "index": "kdate"})
    left.columns = ["kdate"] + list(left.columns[1:])

    # 코스피 D ↔ D보다 엄격히 이전인 마지막 미국 종가
    merged = pd.merge_asof(
        left.sort_values("kdate"),
        us_ret.sort_values("us_date"),
        left_on="kdate",
        right_on="us_date",
        direction="backward",
        allow_exact_matches=False,
    )
    merged = merged.dropna(subset=["kospi", "momentum_src", "ewy", "sox", "vix", "nasdaq"])

    # 결합 prior: leading_signal.SIGNAL_WEIGHTS 기준 (모듈과 동일 가중치)
    # 주의: 라이브 prior는 NQ선물(nq)을 포함하지만,
    # 백테스트는 yfinance로 과거 선물 정확 복원이 불가하므로 NQ 항은 제외한다.
    merged["prior_score"] = (
        SIGNAL_WEIGHTS["sox"] * merged["sox"]
        + SIGNAL_WEIGHTS["ewy"] * merged["ewy"]
        + SIGNAL_WEIGHTS["nasdaq"] * merged["nasdaq"]
        + SIGNAL_WEIGHTS["vix"] * merged["vix"]
    )

    truth = np.sign(merged["kospi"])
    rules = {
        "EWY부호":      np.sign(merged["ewy"]),
        "SOX부호":      np.sign(merged["sox"]),
        "VIX역부호":    -np.sign(merged["vix"]),
        "나스닥부호":   np.sign(merged["nasdaq"]),
        "결합prior":    np.sign(merged["prior_score"]),
        "모멘텀(전일)": np.sign(merged["momentum_src"]),
    }

    n = len(merged)
    print(f"\n표본: {n}거래일  ({merged['kdate'].min().date()} ~ {merged['kdate'].max().date()})\n")

    def hit(pred, mask=None):
        m = (pred == truth)
        if mask is not None:
            m = m[mask]
        return m.mean() * 100, m.sum(), len(m)

    print(f"{'규칙':<14}{'전체적중':>12}{'유의일(|D|≥0.3%)':>20}")
    big = merged["kospi"].abs() >= DEADBAND
    for name, pred in rules.items():
        a, ah, an = hit(pred)
        b, bh, bn = hit(pred, big)
        print(f"{name:<14}{a:>8.1f}% ({ah:>2}/{an:<2}){b:>12.1f}% ({bh:>2}/{bn:<2})")

    # 충돌 부분집합: 모멘텀과 EWY부호가 반대인 날 = 휩소/반전 후보
    conflict = np.sign(merged["momentum_src"]) != np.sign(merged["ewy"])
    cn = conflict.sum()
    print(f"\n── 충돌일(모멘텀≠EWY부호): {cn}일 — 여기서 V반등이 갈린다 ──")
    if cn:
        for name in ["EWY부호", "결합prior", "모멘텀(전일)"]:
            a, ah, an = hit(rules[name], conflict)
            print(f"  {name:<14}{a:>6.1f}% ({ah}/{an})")
        print("\n  충돌일 상세:")
        cd = merged[conflict][["kdate", "kospi", "momentum_src", "ewy", "sox", "vix"]]
        for _, r in cd.iterrows():
            mark = "↑" if r["kospi"] > 0 else "↓"
            ewy_ok = "EWY맞음" if np.sign(r["ewy"]) == np.sign(r["kospi"]) else "EWY틀림"
            print(f"   {r['kdate'].date()} 코스피{r['kospi']:+6.2f}{mark} | 전일{r['momentum_src']:+6.2f} EWY{r['ewy']:+6.2f} SOX{r['sox']:+6.2f} VIX{r['vix']:+6.2f} → {ewy_ok}")

    # 출시 게이트: 결합prior가 모멘텀을 5%p 이상 상회하면 PASS
    prior_hit, _, _ = hit(rules["결합prior"])
    mom_hit, _, _ = hit(rules["모멘텀(전일)"])
    verdict = "PASS" if prior_hit > mom_hit + 5 else "FAIL"
    print(f"\n[출시 게이트] 결합prior {prior_hit:.1f}% vs 모멘텀 {mom_hit:.1f}% → {verdict}")


if __name__ == "__main__":
    main()
