# 최근 2년 60분봉으로 '장 시작 60분 고점 + 기준선 돌파' 체결과 그 순간까지의 저가 손절을 재현하는 백테스트
import sys, numpy as np, pandas as pd, yfinance as yf
D = pd.read_pickle("kq_ohlc.pkl")
O, H, L, C = (D[k].drop(columns="^GSPC") for k in ("Open", "High", "Low", "Close"))
SPX = D["Close"]["^GSPC"]
UNIV = sys.argv[1] if len(sys.argv) > 1 else "setup"
SLIP = 0.001
r1, r3, r6 = C / C.shift(21) - 1, C / C.shift(63) - 1, C / C.shift(126) - 1
top = pd.concat([x.rank(axis=1, pct=True) for x in (r1, r3, r6)]).groupby(level=0).max() >= 0.98
run = C / C.rolling(126).min() - 1 >= 0.30
s10, s20 = C.rolling(10).mean(), C.rolling(20).mean()
above = (C > s10) & (C > s20) & (s10 > s20)
tight = (H.rolling(10).max() - L.rolling(10).min()) / C < 0.6 * ((H.rolling(20).max() - L.rolling(20).min()) / C).shift(10)
hl = L.rolling(10).min() > L.rolling(20).min().shift(10)
pivot = H.rolling(10).max(); near = C / pivot - 1 > -0.08
adr = (H / L - 1).rolling(20).mean()
mkt = SPX > SPX.rolling(50).mean()
setup = (top & run & above & tight & hl & near & (adr >= 0.03)) if UNIV == "setup" else ((C > s10) & near & (adr >= 0.03))
setup = setup.mul(mkt, axis=0).astype(bool)
start = pd.Timestamp("2024-12-02")
cand = [t for t in C.columns if setup.loc[start:, t].any()]
if UNIV == "base":
    import random; random.seed(1); cand = random.sample(cand, min(120, len(cand)))
try:
    HB = pd.read_pickle(f"kq_60m_{UNIV}.pkl")
except FileNotFoundError:
    HB = yf.download(cand, period="730d", interval="60m", auto_adjust=True, progress=False, threads=True, prepost=False)
    HB.to_pickle(f"kq_60m_{UNIV}.pkl")
HB.index = HB.index.tz_convert("America/New_York")
print(f"[{UNIV}] 후보 종목 {len(cand)} · 60분봉 {HB.index[0].date()}~{HB.index[-1].date()}")
idx = C.index; trades = []
for t in cand:
    if t not in HB["High"].columns: continue
    hh, hl_, ho, hc = HB["High"][t], HB["Low"][t], HB["Open"][t], HB["Close"][t]
    dkey = hh.index.normalize().tz_localize(None)
    o, h, l, c, sm, a, sg, pv = (x[t].values for x in (O, H, L, C, s10, adr, setup, pivot))
    n = len(c); i = idx.searchsorted(start)
    while i < n - 1:
        if not sg[i]: i += 1; continue
        P, done = pv[i], None
        for j in range(i + 1, min(i + 6, n)):
            if c[j] < sm[j] and h[j] <= P: break
            if h[j] <= P: continue
            m = dkey == idx[j]
            if m.sum() < 3: break
            bh, bl, bo = hh[m].values, hl_[m].values, ho[m].values
            trig = max(P, bh[0])                             # 첫 60분 고점과 기준선 둘 다 넘어야 산다
            lod = bl[0]
            for b in range(1, len(bh)):
                if bh[b] > trig:
                    px = max(trig, bo[b]) * (1 + SLIP)
                    for lo_case in ("opt", "pes"):
                        pass
                    done = (j, b, px, lod, bl[b], bh, bl, hc[m].values); break
                lod = min(lod, bl[b])
            break
        if not done: i += 1; continue
        j, b, px, lod, entlow, bh, bl, bc = done
        res = {}
        for case in ("opt", "pes"):
            # opt: 돌파 봉의 저가는 돌파 전에 찍혔다(손절선 = 그 저가) / pes: 돌파 뒤에 찍혔다(돌파 전 저가로 손절, 깨면 손절)
            stop = min(lod, entlow) if case == "opt" else lod
            risk = px - stop
            if risk <= 0 or risk / px > a[i]: res[case] = None; continue
            hit = (case == "pes" and entlow <= stop) or any(bl[b + 1:] <= stop)
            if hit:
                res[case] = (-1 - SLIP * px / risk, risk / px); continue
            R, half, k, st = 0.0, 1.0, j + 1, stop
            while k < n:
                if l[k] <= st: R += half * (min(o[k], st) * (1 - SLIP) - px) / risk; half = 0; break
                if half == 1.0 and k - j >= 5: R += 0.5 * (c[k] * (1 - SLIP) - px) / risk; half = 0.5; st = max(st, px)
                elif c[k] < sm[k] and (half == 0.5 or k - j >= 1): R += half * (c[k] * (1 - SLIP) - px) / risk; half = 0; break
                k += 1
            res[case] = None if half else (R, risk / px)
        if res["opt"] or res["pes"]:
            trades.append({"t": t, "d": idx[j], **{f"R_{k}": (v[0] if v else np.nan) for k, v in res.items()},
                           **{f"risk_{k}": (v[1] if v else np.nan) for k, v in res.items()}})
        i = j + 1
T = pd.DataFrame(trades)
for k in ("opt", "pes"):
    R, rk = T[f"R_{k}"].dropna(), T[f"risk_{k}"].dropna()
    acct = (np.minimum(0.005 / rk, 0.30) * R * rk)
    print(f"  {'낙관' if k=='opt' else '보수'}: {len(R)}건 · 승률 {(R>0).mean():.1%} · 평균 {R.mean():+.2f}R (중앙값 {R.median():+.2f}) · 3R↑ {(R>=3).mean():.1%} · 손절폭 {rk.mean():.1%} · 계좌 매매당 {acct.mean():+.3%} · 2년 합 {acct.sum():+.0%}")
T.to_pickle(f"kq_h_trades_{UNIV}.pkl")
