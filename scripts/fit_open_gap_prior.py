# 선행신호 prior를 코스피 시초가 갭 기준으로 재점검하는 진단 스크립트 (가중치·확률 환산·strong 규칙의 근거)
"""
무엇을 재나:
  코스피 D일 아침이 볼 수 있는 정보(= D보다 엄격히 이전의 마지막 미국장 종가)로
  'D일 시초가가 전일 종가보다 높게 열리는가'를 얼마나 맞히는지.

실행:  python3 scripts/fit_open_gap_prior.py            (네트워크 필요 — 네이버 지수 일봉 + 야후 차트 API)
       python3 scripts/fit_open_gap_prior.py --write    결과를 scripts/config/kospi_open_prior_backtest.json에도 쓴다
                                                        (방법론 페이지 /methodology/가 이 파일을 읽는다 — 숫자를 코드에 박지 않는다, §20)
결과는 leading_signal.py의 SIGNAL_WEIGHTS · PROB_A/B · P_STRONG_* 주석과 SERVICE_RULES §57에 적혀 있다.

한계:
  · 선물(NQ·ES)의 07:25 값은 과거를 되살릴 수 없어 백테스트에서 뺀다. 라이브 성적은 briefings.json의 signals로 따로 본다.
  · 야후 KRW=X 일봉은 마감 시각이 한국 개장과 겹쳐 실제 07:25 값보다 유리하게 잡힐 수 있다 — 그래도 예측력이 없었다.
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leading_signal import SIGNAL_WEIGHTS, DN_BAND, PROB_A, PROB_B, P_STRONG_UP, P_STRONG_DN

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "scripts" / "config" / "kospi_open_prior_backtest.json"

UA = {"User-Agent": "Mozilla/5.0"}
US = {"^IXIC": "nasdaq", "^SOX": "sox", "EWY": "ewy", "^VIX": "vix", "KRW=X": "usdkrw"}


def _get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())


def load_dataset(start="20231101") -> pd.DataFrame:
    rows = _get("https://api.stock.naver.com/chart/domestic/index/KOSPI/day"
                f"?startDateTime={start}0000&endDateTime=209912310000")
    k = pd.DataFrame(rows)
    k["kdate"] = pd.to_datetime(k["localDate"])
    k = k.sort_values("kdate")
    prev = k["closePrice"].shift(1)
    k["gap"] = (k["openPrice"] / prev - 1) * 100          # 채점 대상 — 시초가 갭
    k["kprev"] = ((k["closePrice"] / prev - 1) * 100).shift(1)   # 직전 코스피 세션 등락(EWY 잔차용)

    def yahoo(sym):
        d = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
                 "?range=3y&interval=1d")["chart"]["result"][0]
        ts = pd.to_datetime(d["timestamp"], unit="s") + pd.Timedelta(seconds=d["meta"]["gmtoffset"])
        return pd.Series(d["indicators"]["quote"][0]["close"], index=ts.normalize())

    cl = pd.DataFrame({name: yahoo(sym) for sym, name in US.items()})
    cl = cl[cl["sox"].notna()].ffill()                     # 미국 거래일만
    r = (cl.pct_change() * 100).reset_index()
    r.columns = ["us_date"] + list(r.columns[1:])
    m = pd.merge_asof(k[["kdate", "gap", "kprev"]].dropna(), r.sort_values("us_date"),
                      left_on="kdate", right_on="us_date", direction="backward", allow_exact_matches=False)
    m = m.dropna(subset=["gap", "sox", "ewy", "nasdaq", "vix"]).fillna({"usdkrw": 0}).reset_index(drop=True)
    m["ewy_resid"] = m["ewy"] - m["kprev"]
    return m


def score(m: pd.DataFrame, weights: dict) -> pd.Series:
    s = 0
    for key, w in weights.items():
        if key == "nq":            # 과거 07:25 선물값은 복원 불가 — 제외
            continue
        s = s + w * (m["ewy_resid"] if key == "ewy" else m[key])
    return s


def legacy_split(briefings: list, k: pd.DataFrame) -> dict:
    """종가 기준 시절(basis 없음) 코스피 예측을 시초가·종가·장중 방향으로 나눠 채점한다(§57 전환 근거).
    상승·하락 방향을 말한 날만 센다. 등락 0은 상승으로 본다(check_accuracy와 같은 규칙)."""
    day = {d.strftime("%Y-%m-%d"): (o, c, pc) for d, o, c, pc in
           zip(k["kdate"], k["openPrice"], k["closePrice"], k["closePrice"].shift(1))}
    hit = {"open": 0, "close": 0, "intraday": 0}
    dates = []
    for b in briefings:
        if b.get("type") != "kospi" or b.get("basis") == "open" or b.get("is_correct") is None:
            continue
        pd_ = b.get("predicted_direction") or ""
        side = 1 if "상승" in pd_ else -1 if "하락" in pd_ else 0
        v = day.get(b["date"])
        if not side or not v or not (v[2] > 0):
            continue
        o, c, pc = v
        dates.append(b["date"])
        hit["open"] += (o >= pc) == (side > 0)
        hit["close"] += (c >= pc) == (side > 0)
        hit["intraday"] += (c >= o) == (side > 0)
    n = len(dates)
    if not n:
        return {}
    return {"days": n, "from": min(dates), "to": max(dates),
            **{f"{key}_hit_pct": round(v / n * 100, 1) for key, v in hit.items()}}


def kospi_days(start="20260301") -> pd.DataFrame:
    rows = _get("https://api.stock.naver.com/chart/domestic/index/KOSPI/day"
                f"?startDateTime={start}0000&endDateTime=209912310000")
    k = pd.DataFrame(rows)
    k["kdate"] = pd.to_datetime(k["localDate"])
    return k.sort_values("kdate").reset_index(drop=True)


def main():
    write = "--write" in sys.argv[1:]
    m = load_dataset()
    y = np.sign(m["gap"])
    yr = m["kdate"].dt.year
    print(f"표본 {len(m)}거래일 ({m.kdate.min().date()} ~ {m.kdate.max().date()}) · 위로 열림 {(y > 0).mean() * 100:.1f}%\n")

    variants = {
        "현행 가중": SIGNAL_WEIGHTS,
        "원/달러 -0.8 포함(이전)": dict(SIGNAL_WEIGHTS, usdkrw=-0.8),
        "EWY 잔차 비중 1.0": dict(SIGNAL_WEIGHTS, ewy=1.0),
        "SOX만": {"sox": 1.0},
    }
    print(f"{'부호 적중률(%)':22s}{'전체':>8s}{'2024':>8s}{'2025':>8s}{'2026':>8s}")
    print(f"{'항상 상승':22s}{(y > 0).mean() * 100:8.1f}" + "".join(f"{(y[yr == v] > 0).mean() * 100:8.1f}" for v in (2024, 2025, 2026)))
    for name, w in variants.items():
        s = score(m, w)
        hit = (np.where(s > 0, 1, -1) == y)
        print(f"{name:22s}{hit.mean() * 100:8.1f}" + "".join(f"{hit[yr == v].mean() * 100:8.1f}" for v in (2024, 2025, 2026)))

    print("\n신호별 갭과의 상관 · 부호 적중")
    for c in ("sox", "nasdaq", "ewy", "ewy_resid", "vix", "usdkrw"):
        sgn = -1 if c in ("vix", "usdkrw") else 1
        print(f"  {c:10s} 상관 {m[c].corr(m.gap):+.2f}  부호 {((np.sign(m[c]) * sgn) == y).mean() * 100:.1f}%")

    s = score(m, SIGNAL_WEIGHTS)
    p = 1 / (1 + np.exp(-(PROB_A + PROB_B * s)))
    print(f"\n확률 환산(A={PROB_A}, B={PROB_B}) 보정 — 2026년")
    for lo, hi in ((0, .2), (.2, .35), (.35, .5), (.5, .65), (.65, .8), (.8, 1.01)):
        k = (yr == 2026) & (p >= lo) & (p < hi)
        if k.sum():
            print(f"  예측 {lo:.2f}~{hi:.2f}: {int(k.sum()):3d}일  평균 예측 {p[k].mean() * 100:3.0f}%  실제 {(y[k] > 0).mean() * 100:3.0f}%")

    pred = np.where(p >= .5, 1, -1)
    extreme = (p >= P_STRONG_UP) | (p <= P_STRONG_DN)
    agree = np.sign(m["sox"]) == np.sign(m["ewy_resid"])
    print("\nstrong 규칙 — 확률 극단 구간의 갭 방향 적중")
    for name, k in (("극단 전체", extreme), ("SOX·EWY잔차 같은 방향", extreme & agree), ("엇갈림", extreme & ~agree)):
        print(f"  {name:22s} {int(k.sum()):3d}일  {(pred[k] == y[k]).mean() * 100:.1f}%")

    dn = s < DN_BAND
    print(f"\n하락 판정(score < {DN_BAND}): {int(dn.sum())}일 중 실제 아래로 열림 {(y[dn] < 0).mean() * 100:.1f}%")

    briefings = json.loads((ROOT / "data" / "briefings.json").read_text(encoding="utf-8"))["briefings"]
    legacy = legacy_split(briefings, kospi_days())
    if legacy:
        print(f"\n종가 기준 시절 예측 {legacy['days']}일({legacy['from']}~{legacy['to']}) — "
              f"시초가 {legacy['open_hit_pct']}% · 종가 {legacy['close_hit_pct']}% · 장중 {legacy['intraday_hit_pct']}%")

    if write:
        hit = np.where(s > 0, 1, -1) == y
        y26 = yr == 2026
        calib = []
        for lo, hi in ((0, .2), (.8, 1.01)):
            k = y26 & (p >= lo) & (p < hi)
            if k.sum():
                calib.append({"lo": lo, "hi": min(hi, 1.0), "days": int(k.sum()),
                              "pred_pct": round(float(p[k].mean()) * 100), "actual_up_pct": round(float((y[k] > 0).mean()) * 100)})
        out = {
            "generated_at": pd.Timestamp.now(tz="Asia/Seoul").isoformat(timespec="seconds"),
            "method": "D일 아침 07:25에 볼 수 있는 직전 미국장 종가 신호(SOX·나스닥·EWY 잔차·VIX, 가중치는 leading_signal.py)로 "
                      "D일 코스피 시초가가 전일 종가보다 높게 열리는지 맞힌 비율. 07:25 선물값은 과거를 복원할 수 없어 뺐다.",
            "data_from": str(m.kdate.min().date()), "data_through": str(m.kdate.max().date()), "days": int(len(m)),
            "hit_pct": round(float(hit.mean()) * 100, 1), "base_up_pct": round(float((y > 0).mean()) * 100, 1),
            "y2026": {"days": int(y26.sum()), "hit_pct": round(float(hit[y26].mean()) * 100, 1),
                      "base_up_pct": round(float((y[y26] > 0).mean()) * 100, 1)},
            "usdkrw_sign_hit_pct": round(float(((np.sign(m["usdkrw"]) * -1) == y).mean()) * 100, 1),
            "calib_2026": calib,
            "legacy_split": legacy,
        }
        OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\n→ {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
