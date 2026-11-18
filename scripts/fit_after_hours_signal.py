# 미국 장 마감 뒤 AI 반도체 시간외 움직임이 다음 날 코스피 시초가를 더 잘 맞히게 하는지 재는 진단 스크립트(2026-11-18)
"""
무엇을 재나:
  D일 코스피 아침(07:25 KST)에 볼 수 있는 '직전 미국장 마감 뒤 시간외 움직임'(엔비디아·마이크론·브로드컴·TSMC·AMD 평균,
  SOXX)을 지금 prior(SOX·나스닥·EWY 잔차·VIX)에 더하면 시초가 방향 적중률이 오르는가.
  특히 빅테크·AI 인프라가 장 마감 뒤 실적을 낸 밤을 따로 본다(2026-11-18 엔비디아 실적 밤 예측 하락 57% → 시초가 +2.62%).

실행: python3 scripts/fit_after_hours_signal.py      (네트워크 필요 — 네이버 지수 일봉, 야후 1시간봉·실적 기록)
      python3 scripts/fit_after_hours_signal.py --write   결과를 scripts/config/after_hours_signal_backtest.json에도 쓴다
                                                          (방법론 페이지가 읽는다 — 숫자를 코드에 박지 않는다, §20)

시간외 값: 야후 1시간봉(prepost)에서 D일 16:00 ET 이후 시작해 07:25 KST 이전에 끝난 봉의 마지막 종가 ÷ D일 정규장 종가 − 1.
  1시간봉이라 07:25 직전 봉이 빠질 수 있다(겨울엔 17:00 ET까지, 여름엔 18:00 ET까지) — 그 뒤 움직임은 못 본다(보수적).
한계: 야후 1시간봉은 약 2년치만 준다. 지금 상장된 종목으로 잰다.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fit_open_gap_prior import load_dataset, score  # noqa: E402
from leading_signal import SIGNAL_WEIGHTS  # noqa: E402

from leading_signal import AH_TICKERS  # noqa: E402 — 라이브 계산과 같은 종목
EARN_TICKERS = ["NVDA", "MU", "AVGO", "TSM", "AMD", "ORCL", "MSFT", "GOOGL", "AMZN", "META", "AAPL", "DELL"]
ET = "America/New_York"


def after_hours_drift(sym: str, kdates: pd.Series, us_dates: pd.Series) -> pd.Series:
    h = yf.download(sym, period="730d", interval="1h", prepost=True, progress=False, auto_adjust=False)
    if h.empty:
        return pd.Series(np.nan, index=kdates.index)
    c = h["Close"]
    c = (c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c).dropna()
    c.index = c.index.tz_convert(ET)
    d = yf.Ticker(sym).history(period="3y", auto_adjust=False)["Close"]
    d.index = d.index.tz_convert(ET).normalize().tz_localize(None)
    first = c.index.min()
    out = []
    for kd, ud in zip(kdates, us_dates):
        ud = pd.Timestamp(ud).normalize()
        reg = d.get(ud)
        if reg is None or pd.isna(reg) or pd.Timestamp(ud.year, ud.month, ud.day, tz=ET) < first:   # 1시간봉이 없는 날은 자료 없음
            out.append(np.nan)
            continue
        cutoff = pd.Timestamp(kd.year, kd.month, kd.day, 7, 25, tz="Asia/Seoul").tz_convert(ET)
        start = pd.Timestamp(ud.year, ud.month, ud.day, 16, 0, tz=ET)
        bars = c[(c.index >= start) & (c.index + pd.Timedelta(hours=1) <= cutoff)]
        out.append((float(bars.iloc[-1]) / float(reg) - 1) * 100 if len(bars) else 0.0)
    return pd.Series(out, index=kdates.index)


def earnings_nights(us_dates: pd.Series) -> pd.Series:
    """D일(미국) 장 마감 뒤 실적을 낸 회사 목록(야후 실적 기록 — 과거는 기록이 있다)."""
    nights = {}
    for t in EARN_TICKERS:
        try:
            ed = yf.Ticker(t).get_earnings_dates(limit=16)
        except Exception:
            continue
        for ts in ed.index:
            ts = ts.tz_convert(ET)
            if ts.hour >= 16:      # 장 마감 뒤 발표만 — 장 전 발표는 그날 정규장에 이미 반영된다
                nights.setdefault(ts.normalize().tz_localize(None), []).append(t)
    return us_dates.map(lambda d: ",".join(nights.get(pd.Timestamp(d).normalize(), [])))


def hit(s, y):
    return float((np.where(s > 0, 1, -1) == y).mean() * 100)


def brier(s, y):
    """지금 확률식(leading_signal.PROB_A·PROB_B)으로 바꾼 상승 확률의 Brier 점수 — 낮을수록 잘 맞는다."""
    from leading_signal import PROB_A, PROB_B
    p = 1 / (1 + np.exp(-(PROB_A + PROB_B * np.asarray(s))))
    return float(np.mean((p - (np.asarray(y) > 0)) ** 2))


def main():
    m = load_dataset()
    for t in list(AH_TICKERS) + ["SOXX"]:
        m[f"ah_{t}"] = after_hours_drift(t, m["kdate"], m["us_date"])
    m["ai_ah"] = m[[f"ah_{t}" for t in AH_TICKERS]].mean(axis=1)
    m["earn"] = earnings_nights(m["us_date"])
    m = m.dropna(subset=["ai_ah"]).reset_index(drop=True)
    y = np.sign(m["gap"]).to_numpy()
    base = score(m, {k: v for k, v in SIGNAL_WEIGHTS.items() if k != "ai_ah"})   # 비교 기준 — 시간외를 넣기 전
    print(f"표본 {len(m)}거래일 ({m.kdate.min().date()} ~ {m.kdate.max().date()}) · 위로 열림 {(y > 0).mean() * 100:.1f}%")
    print(f"AI 반도체 시간외(평균)와 갭 상관 {m.ai_ah.corr(m.gap):+.2f} · SOXX 시간외 {m.ah_SOXX.corr(m.gap):+.2f} · 지금 점수 {base.corr(m.gap):+.2f}")
    print(f"시간외 부호 적중 {((np.sign(m.ai_ah) == y) & (m.ai_ah != 0)).sum() / (m.ai_ah != 0).sum() * 100:.1f}% "
          f"(움직임 있는 {(m.ai_ah != 0).sum()}일)\n")

    groups = {
        "전체": np.ones(len(m), bool),
        "실적 밤(빅테크·AI 장 마감 뒤 발표)": (m.earn != "").to_numpy(),
        "시간외 |평균| ≥ 1%": (m.ai_ah.abs() >= 1).to_numpy(),
        "시간외 |평균| ≥ 2%": (m.ai_ah.abs() >= 2).to_numpy(),
    }
    ws = (0, 0.5, 1.0, 1.5, 2.0, 3.0)
    print(f"{'구간':30s}{'일수':>5s}" + "".join(f"{'w=' + str(w):>8s}" for w in ws) + f"{'시간외만':>9s}")
    for name, k in groups.items():
        row = f"{name:30s}{int(k.sum()):5d}"
        for w in ws:
            row += f"{hit((base + w * m.ai_ah)[k], y[k]):8.1f}"
        row += f"{hit(m.ai_ah[k], y[k]):9.1f}"
        print(row)

    print(f"\nBrier(낮을수록 좋음) 전체 — 지금 {brier(base, y):.4f}" + "".join(f" · w={w} {brier(base + w * m.ai_ah, y):.4f}" for w in ws[1:]))
    k = (m.earn != "").to_numpy()
    print(f"Brier 실적 밤 — 지금 {brier(base[k], y[k]):.4f}" + "".join(f" · w={w} {brier((base + w * m.ai_ah)[k], y[k]):.4f}" for w in ws[1:]))

    # 시기를 나눈 검증 — 앞 절반으로 고른 가중을 뒤 절반에, 뒤로 고른 가중을 앞에
    half = len(m) // 2
    for name, (tr, te) in {"앞→뒤": (slice(0, half), slice(half, None)), "뒤→앞": (slice(half, None), slice(0, half))}.items():
        best = max(ws, key=lambda w: hit((base + w * m.ai_ah)[tr], y[tr]))
        print(f"\n{name}: 학습 구간 최적 w={best} — 검증 구간 지금 {hit(base[te], y[te]):.1f}% → 더하면 {hit((base + best * m.ai_ah)[te], y[te]):.1f}% "
              f"({len(y[te])}일, 실적 밤 {int((m.earn[te] != '').sum())}일: "
              f"{hit(base[te][(m.earn[te] != '').to_numpy()], y[te][(m.earn[te] != '').to_numpy()]):.1f}% → "
              f"{hit((base + best * m.ai_ah)[te][(m.earn[te] != '').to_numpy()], y[te][(m.earn[te] != '').to_numpy()]):.1f}%)")

    if "--write" in sys.argv[1:]:
        w = SIGNAL_WEIGHTS.get("ai_ah", 1.0)
        base_only = score(m, {k: v for k, v in SIGNAL_WEIGHTS.items() if k != "ai_ah"})
        withah = base_only + w * m.ai_ah
        k = (m.earn != "").to_numpy()
        big = (m.ai_ah.abs() >= 1).to_numpy()
        out = {
            "generated_at": pd.Timestamp.now(tz="Asia/Seoul").isoformat(timespec="seconds"),
            "method": "D일 07:25 KST까지의 AI 반도체(" + "·".join(AH_TICKERS) + ") 장 마감 뒤 시간외 평균 등락을 점수에 더했을 때 "
                      "D일 코스피 시초가 방향 적중률. 야후 1시간봉(약 2년치)이라 07:25 직전 1시간 안의 움직임은 빠질 수 있다.",
            "weight": w, "data_from": str(m.kdate.min().date()), "data_through": str(m.kdate.max().date()), "days": int(len(m)),
            "hit_without": round(hit(base_only, y), 1), "hit_with": round(hit(withah, y), 1),
            "earn_nights": int(k.sum()), "earn_without": round(hit(base_only[k], y[k]), 1), "earn_with": round(hit(withah[k], y[k]), 1),
            "big_move_days": int(big.sum()), "big_without": round(hit(base_only[big], y[big]), 1), "big_with": round(hit(withah[big], y[big]), 1),
        }
        p = Path(__file__).resolve().parent / "config" / "after_hours_signal_backtest.json"
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\n→ {p.relative_to(p.parents[2])}")

    print("\n실적 밤 목록(시간외 평균 · 지금 점수 · 실제 갭)")
    for _, r in m[m.earn != ""].iterrows():
        print(f"  {r.kdate.date()} {r.earn:22s} 시간외 {r.ai_ah:+5.2f}%  점수 {base[_]:+5.2f}  갭 {r.gap:+5.2f}%")


if __name__ == "__main__":
    main()
