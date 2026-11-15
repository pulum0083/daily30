# 터틀 규칙(시스템1 20/10·직전 승리 건너뛰기, 시스템2 55/20, 2N 손절, ½N마다 최대 4단위) 일봉 백테스트
import sys, numpy as np, pandas as pd
SRC, SIDE = sys.argv[1], sys.argv[2]          # SRC: etf|sp500 · SIDE: long|both
RAND = len(sys.argv) > 3 and sys.argv[3] == "rand"   # 비교 기준: 돌파와 무관하게 아무 날에 산다(같은 확률로)
rng = np.random.default_rng(7)
D = pd.read_pickle("tt_etf.pkl" if SRC == "etf" else "kq_ohlc.pkl")
O, H, L, C = (D[k] for k in ("Open", "High", "Low", "Close"))
if SRC == "sp500":
    O, H, L, C = (x.drop(columns="^GSPC") for x in (O, H, L, C))
SLIP = 0.0005

def run(o, h, l, c, ent_n, ext_n, skip, direction, dates):
    n = len(c); tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    N = np.full(n, np.nan); N[20] = tr[:20].mean()
    for i in range(21, n): N[i] = (19 * N[i - 1] + tr[i - 1]) / 20
    sgn = 1 if direction == "L" else -1
    ph = pd.Series(h).rolling(ent_n).max().shift(1).values if sgn > 0 else -pd.Series(l).rolling(ent_n).min().shift(1).values
    pl = pd.Series(l).rolling(ext_n).min().shift(1).values if sgn > 0 else -pd.Series(h).rolling(ext_n).max().shift(1).values
    hh, ll, oo = (h, l, o) if sgn > 0 else (-l, -h, -o)       # 숏은 가격을 뒤집어 롱처럼 계산
    out, last_win, i = [], False, max(ent_n, 21)
    p_sig = np.nanmean(hh[ent_n:] > ph[ent_n:])
    while i < n - 1:
        sig = (rng.random() < p_sig) if RAND else (hh[i] > ph[i])
        if not sig or np.isnan(N[i - 1]) or np.isnan(ph[i]):
            i += 1; continue
        N0 = N[i - 1]; px0 = oo[i] if RAND else max(ph[i], oo[i])
        units = [px0 * (1 + SLIP)]; stop = px0 - 2 * N0; k = i; ex = None
        while k < n:
            if k > i:                                          # 산 날엔 더 사지 않는다(일봉으로 순서를 모른다)
                while len(units) < 4 and hh[k] >= px0 + 0.5 * N0 * len(units):   # ½N마다 한 단위
                    a = max(px0 + 0.5 * N0 * len(units), oo[k] if k > i else -1e18)
                    units.append(a * (1 + SLIP)); stop = a - 2 * N0
            if ll[k] <= stop: ex = min(oo[k], stop) if k > i else stop; break   # 산 날 2N 아래로 가면 손절(불리한 가정)
            if k > i and ll[k] <= pl[k]: ex = min(oo[k], pl[k]); break
            k += 1
        if ex is None: break
        ex *= (1 - SLIP)
        pnl = sum((ex - u) / N0 for u in units) * 1.0          # 계좌 %: 1N 움직임 = 1%
        taken = not (skip and last_win)
        if taken:
            out.append({"d": dates[i], "pnl": pnl, "R": pnl / 2, "units": len(units), "days": k - i})
        last_win = pnl > 0
        i = k + 1
    return out

rows = []
for t in C.columns:
    s = C[t].dropna()
    if len(s) < 300: continue
    ix = s.index; o, h, l, c = (x[t].reindex(ix).values for x in (O, H, L, C))
    for name, en, exn, sk in (("S1 20/10", 20, 10, True), ("S2 55/20", 55, 20, False)):
        for d in (["L"] if SIDE == "long" else ["L", "S"]):
            for r in run(o, h, l, c, en, exn, sk, d, ix):
                rows.append({"t": t, "sys": name, "dir": d, **r})
T = pd.DataFrame(rows); T["y"] = T.d.dt.year
for (sysn, d), g in T.groupby(["sys", "dir"]):
    w = g.pnl > 0
    print(f"[{SRC}{'·무작위' if RAND else ''}] {sysn} {'롱' if d=='L' else '숏'}: {len(g)}건 · 승률 {w.mean():.0%} · 평균 {g.R.mean():+.2f}R · 이긴 평균 {g.R[w].mean():+.2f}R · 진 평균 {g.R[~w].mean():+.2f}R · 상위5%빼면 {g.R[g.R<g.R.quantile(.95)].mean():+.2f}R")
    for a, b in ((2000, 2009), (2010, 2019), (2020, 2026)):
        x = g[(g.y >= a) & (g.y <= b)]
        if len(x): print(f"     {a}~{b}: {len(x)}건 평균 {x.R.mean():+.2f}R")
T.to_pickle(f"tt_trades_{SRC}_{SIDE}_{'rand' if RAND else 'sig'}.pkl")
