# 쿨라매기 돌파 규칙을 S&P 500 일봉으로 근사한 백테스트 — 신호·체결·청산을 날짜순으로 재현해 R 배수로 잰다
import sys, numpy as np, pandas as pd
D = pd.read_pickle("kq_ohlc.pkl")
O, H, L, C = (D[k].drop(columns="^GSPC") for k in ("Open", "High", "Low", "Close"))
SPX = D["Close"]["^GSPC"]
ADR_MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
MKT = (sys.argv[2] if len(sys.argv) > 2 else "none")
STOP = (sys.argv[3] if len(sys.argv) > 3 else "lod")     # lod: 산 날 저가(낙관) / prev: 전날 저가, 산 날 깨면 손절(보수)
UNIV = (sys.argv[4] if len(sys.argv) > 4 else "setup")   # setup: 쿨라매기 조건 / base: 아무 종목 10일 고점 돌파
SLIP = 0.001  # 사고팔 때 0.1%씩 불리하게

r1, r3, r6 = C / C.shift(21) - 1, C / C.shift(63) - 1, C / C.shift(126) - 1
top = pd.concat([x.rank(axis=1, pct=True) for x in (r1, r3, r6)]).groupby(level=0).max() >= 0.98
run = C / C.rolling(126).min() - 1 >= 0.30           # 6달 안 저점에서 30% 넘게 오른 상태
s10, s20 = C.rolling(10).mean(), C.rolling(20).mean()
above = (C > s10) & (C > s20) & (s10 > s20)
rng10 = (H.rolling(10).max() - L.rolling(10).min()) / C
rngp = ((H.rolling(20).max() - L.rolling(20).min()) / C).shift(10)
tight = rng10 < 0.6 * rngp
hl = L.rolling(10).min() > L.rolling(20).min().shift(10)
pivot = H.rolling(10).max()
near = C / pivot - 1 > -0.08
adr = (H / L - 1).rolling(20).mean()
setup = top & run & above & tight & hl & near & (adr >= ADR_MIN)
if UNIV == "base":
    setup = (C > s10) & (adr >= ADR_MIN) & near & (C.notna())
if MKT == "ma50":
    ok = SPX > SPX.rolling(50).mean()
    setup = setup.mul(ok, axis=0).astype(bool)

idx = C.index
trades = []
for t in C.columns:
    o, h, l, c, sm, a, sg, pv = (x[t].values for x in (O, H, L, C, s10, adr, setup, pivot))
    i, n = 130, len(c)
    while i < n - 1:
        if not sg[i]:
            i += 1; continue
        P, ent = pv[i], None
        for j in range(i + 1, min(i + 6, n)):               # 신호 뒤 5거래일 안에 기준선을 뚫으면 산다
            if h[j] > P:
                ent = j; break
            if c[j] < sm[j]:                                # 그 전에 10일선을 깨면 셋업 무효
                break
        if ent is None:
            i += 1; continue
        j = ent
        px = max(P, o[j]) * (1 + SLIP); stop = l[j] if STOP == "lod" else l[j - 1]
        risk = px - stop
        if risk <= 0 or risk / px > a[i]:                   # 손절폭이 하루 평균 움직임보다 넓으면 넘긴다
            i = j + 1; continue
        # 청산: 5거래일 째 종가에 절반, 나머지는 손절을 본전으로 올리고 종가 < 10일선이면 판다
        res, half, k, st = 0.0, 1.0, j + 1, stop
        if STOP == "prev" and l[j] <= stop:                 # 산 날 손절선을 깼다 — 산 뒤에 깼다고 본다(불리한 가정)
            trades.append({"t": t, "d": idx[j], "out": idx[j], "R": -1 - SLIP * px / risk, "risk": risk / px,
                           "ret": -(risk / px) - SLIP, "hold": 0})
            i = j + 1; continue
        while k < n:
            if l[k] <= st:
                ex = min(o[k], st) * (1 - SLIP)
                res += half * (ex - px) / risk; half = 0; break
            if half == 1.0 and k - j >= 5:
                res += 0.5 * (c[k] * (1 - SLIP) - px) / risk; half = 0.5; st = max(st, px)
            elif half == 0.5 and c[k] < sm[k]:
                res += 0.5 * (c[k] * (1 - SLIP) - px) / risk; half = 0; break
            elif half == 1.0 and c[k] < sm[k] and k - j >= 1:
                res += (c[k] * (1 - SLIP) - px) / risk; half = 0; break
            k += 1
        if half:  # 데이터 끝 — 미청산은 빼고 센다
            i = k; continue
        trades.append({"t": t, "d": idx[j], "out": idx[min(k, n - 1)], "R": res, "risk": risk / px,
                       "ret": res * risk / px, "hold": k - j})
        i = k + 1
T = pd.DataFrame(trades)
T["w"] = np.minimum(0.005 / T.risk, 0.30)                  # 0.5% 위험, 한 종목 30% 한도
T["acct"] = T.w * T.ret
print(f"[{UNIV}·{STOP}] ADR≥{ADR_MIN:.0%} 시장거름={MKT}  매매 {len(T)}건 ({T.d.min().date()}~{T.d.max().date()})")
w = T.R > 0
print(f"  승률 {w.mean():.1%} · 평균 {T.R.mean():+.2f}R · 이긴 평균 {T.R[w].mean():+.2f}R · 진 평균 {T.R[~w].mean():+.2f}R")
print(f"  평균 손절폭 {T.risk.mean():.1%} · 평균 보유 {T.hold.mean():.1f}일 · 3R 넘은 비율 {(T.R>=3).mean():.1%} · 최대 {T.R.max():+.1f}R")
print(f"  매매당 평균 수익률 {T.ret.mean():+.2%} (중앙값 {T.ret.median():+.2%})")
T["y"] = T.d.dt.year
yr = T.groupby("y").acct.sum()
print(f"  계좌 기준 매매당 {T.acct.mean():+.3%} · 30% 한도에 걸린 매매 {(T.w>=0.30).mean():.0%} · 연 합계 중앙값 {yr.median():+.1%} (최악 {yr.min():+.1%} {yr.idxmin()})")
print("  계좌 연합계 " + " · ".join(f"{y}:{v:+.0%}" for y, v in yr.items()))
print("  연도별 " + " · ".join(f"{y}:{g.R.mean():+.2f}R/{len(g)}건" for y, g in T.groupby("y")))
T.to_pickle(f"kq_trades_{ADR_MIN}_{MKT}.pkl")
