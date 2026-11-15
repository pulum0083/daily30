# 종목 터틀 시안용 — S&P 500 지정일 종가 기준 '새로 시작(55일 돌파)·이어감·추세 끝' 종목과 N·손절선·청산선·한 단위 크기를 JSON으로
import json, sys, pandas as pd, numpy as np, yfinance as yf
from concurrent.futures import ThreadPoolExecutor
ASOF = sys.argv[1]
D = pd.read_pickle("kq_ohlc.pkl").loc[:ASOF]
O, H, L, C = (D[k].drop(columns="^GSPC") for k in ("Open", "High", "Low", "Close"))
meta = {i[0].replace(".", "-"): (i[1], i[2]) for i in json.load(open("sp500_constituents.json"))["items"]}
TR = np.maximum(H - L, np.maximum((H - C.shift()).abs(), (L - C.shift()).abs()))
N = TR.ewm(alpha=1 / 20, adjust=False).mean()
hi55, lo20 = H.rolling(55).max().shift(1), L.rolling(20).min().shift(1)
b, e = H > hi55, L < lo20
st = pd.DataFrame(np.nan, index=H.index, columns=H.columns); st[b] = 1; st[e & ~b] = 0; st = st.ffill().fillna(0)
d = C.index[-1]; npct = N.loc[d] / C.loc[d] * 100; ok = npct >= 1.0          # 하루 움직임 1% 미만(인수합병으로 묶인 종목 등)은 뺀다
fresh = b.loc[d] & (st.iloc[-2] == 0) & ok
cont = b.loc[d] & (st.iloc[-2] == 1) & ok
ended = e.loc[d] & (st.iloc[-2] == 1) & ok
capf = json.load(open("tts_caps.json")) if __import__("os").path.exists("tts_caps.json") else {}
need = [t for t in list(fresh[fresh].index) + list(cont[cont].index) + list(ended[ended].index) if t not in capf]
def cap(t):
    try: return float(yf.Ticker(t).fast_info["marketCap"])
    except Exception: return None
with ThreadPoolExecutor(8) as ex: capf.update(dict(zip(need, ex.map(cap, need))))
json.dump(capf, open("tts_caps.json", "w"))
kn = lambda t: meta.get(t, (t, ""))[0]
def chg(t): return round((C[t].iloc[-1] / C[t].iloc[-2] - 1) * 100, 2)
def start_of(t):  # 추세가 시작된 날 = 마지막으로 상태가 0→1로 바뀐 날
    s = st[t]; ch = s[(s == 1) & (s.shift(1) == 0)]; return ch.index.max() if len(ch) else None
new = []
for t in fresh[fresh].index:
    n, line = N[t].loc[d], hi55[t].loc[d]; ent = max(line, O[t].loc[d])
    new.append({"t": t, "name": kn(t), "sec": meta.get(t, ("", ""))[1], "cap": capf.get(t), "close": round(C[t].loc[d], 2), "chg": chg(t),
                "entry": round(ent, 2), "npct": round(npct[t], 1), "stop": round(ent - 2 * n, 2), "stop_pct": round(-2 * n / ent * 100, 1),
                "lo20": round(L[t].iloc[-20:].min(), 2), "lo20_pct": round((L[t].iloc[-20:].min() / ent - 1) * 100, 1),
                "unit": round(min(100 / npct[t], 100)), "adds": [round(ent + k * 0.5 * n, 2) for k in (1, 2, 3)],
                "quiet": int((C.index > (b[t].iloc[:-1][b[t].iloc[:-1]].index.max() if b[t].iloc[:-1].any() else C.index[0])).sum()) - 1})
ends = []
for t in ended[ended].index:
    s0 = start_of(t)
    ends.append({"t": t, "name": kn(t), "cap": capf.get(t), "close": round(C[t].loc[d], 2), "lo20": round(lo20[t].loc[d], 2),
                 "days": int((C.index > s0).sum()) if s0 is not None else None, "since": round((C[t].loc[d] / C[t].loc[s0] - 1) * 100, 1) if s0 is not None else None})
conts = [{"t": t, "name": kn(t), "cap": capf.get(t)} for t in cont[cont].index]
for x in (new, ends, conts): x.sort(key=lambda r: -(r["cap"] or 0))
out = {"asof": str(d.date()), "n_trend": int((st.iloc[-1] == 1).sum()), "n_all": int(C.loc[d].notna().sum()), "new": new, "ended": ends, "cont": conts}
json.dump(out, open(f"tts_{ASOF}.json", "w"), ensure_ascii=False, indent=1)
print(ASOF, "새로", len(new), "이어감", len(conts), "끝", len(ends), "추세 중", out["n_trend"])
for r in new: print(" ", r["t"], r["name"], f'{(r["cap"] or 0)/1e9:.0f}B', r["npct"], r["entry"], r["stop"], r["lo20"], r["unit"], "쉼", r["quiet"])
for r in ends: print("  끝", r["t"], r["name"], r["days"], r["since"])
