# 시장 추세판 시안용 — ETF 14개의 터틀 55/20 상태(추세 여부·며칠째·청산선·돌파선·최근 바뀐 날)를 JSON으로 뽑는다
import json, pandas as pd, numpy as np
D = pd.read_pickle("tt_etf.pkl"); H, L, C = D["High"], D["Low"], D["Close"]
MK = [("EWY","한국"),("SMH","반도체"),("QQQ","나스닥100"),("SPY","S&P 500"),("IWM","러셀2000"),("EWJ","일본"),("FXI","중국"),("EEM","신흥국"),
      ("GLD","금"),("SLV","은"),("USO","원유"),("TLT","미 장기채"),("UUP","달러"),("FXY","엔")]
out = []
for t, k in MK:
    h, l, c = H[t].dropna(), L[t].dropna(), C[t].dropna()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    N = tr.ewm(alpha=1 / 20, adjust=False).mean()
    hi55, lo20 = h.rolling(55).max().shift(1), l.rolling(20).min().shift(1)
    on, start, ev = False, None, []
    for d in c.index[-400:]:
        if not on and h[d] > hi55[d]: on, start = True, d; ev.append(("in", d))
        elif on and l[d] < lo20[d]: on = False; ev.append(("out", d))
    last = c.index[-1]
    nh, nl = h.iloc[-55:].max(), l.iloc[-20:].min()   # 내일 기준 돌파선·청산선
    r = {"t": t, "k": k, "on": on, "n_pct": round(N.iloc[-1] / c.iloc[-1] * 100, 1),
         "to_brk": round((nh / c.iloc[-1] - 1) * 100, 1), "to_exit": round((c.iloc[-1] / nl - 1) * 100, 1),
         "days": int((c.index > start).sum()) + 1 if on else None,
         "gain": round((c.iloc[-1] / c[start] - 1) * 100, 1) if on else None,
         "last_ev": ev[-1][0] if ev else None, "last_d": ev[-1][1].strftime("%m/%d") if ev else None,
         "ev_age": int((c.index > ev[-1][1]).sum()) if ev else None}
    out.append(r)
json.dump({"asof": str(C.index[-1].date()), "rows": out}, open("tt_state.json", "w"), ensure_ascii=False, indent=1)
for r in out: print(r)
