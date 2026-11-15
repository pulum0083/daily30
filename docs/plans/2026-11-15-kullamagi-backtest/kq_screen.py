# 쿨라매기 조건 스크리너 — 검토용(2026-11-15), 지금 시점 후보 수를 센다
# 쿨라매기 돌파 조건(일봉으로 잴 수 있는 부분)을 S&P 500에 돌려 보는 검토용 스크리너
import json, sys
import yfinance as yf, pandas as pd, numpy as np
items = json.load(open(sys.argv[1]))["items"]
tick = [i[0] for i in items]
tick = [t.replace(".", "-") for t in tick]
raw = yf.download(tick, period="1y", interval="1d", auto_adjust=True, progress=False, threads=True)
C, H, L = raw["Close"], raw["High"], raw["Low"]
last = C.index[-1]
rows = []
for t in tick:
    c, h, l = C[t].dropna(), H[t].dropna(), L[t].dropna()
    if len(c) < 130: continue
    r = {"t": t, "r1": c.iloc[-1]/c.iloc[-22]-1, "r3": c.iloc[-1]/c.iloc[-64]-1, "r6": c.iloc[-1]/c.iloc[-127]-1}
    w = c.iloc[-127:]
    r["run"] = max((w.iloc[i:] .max()/w.iloc[i]-1) for i in range(0, len(w)-5, 3))  # 6달 안 최대 상승폭
    r["sma10"], r["sma20"] = c.iloc[-10:].mean(), c.iloc[-20:].mean()
    r["above"] = c.iloc[-1] > r["sma10"] and c.iloc[-1] > r["sma20"] and r["sma10"] > r["sma20"]
    rng = lambda a, b: (h.iloc[a:b].max() - l.iloc[a:b].min()) / c.iloc[b-1]
    r["tight"] = rng(-10, None if False else len(h)) < 0.6 * rng(-30, -10) if True else False
    r["hl"] = l.iloc[-10:].min() > l.iloc[-30:-10].min()
    r["pivot"] = h.iloc[-15:].max(); r["dist"] = c.iloc[-1]/r["pivot"]-1
    r["adr"] = ((h/l-1).iloc[-20:].mean())
    r["close"] = c.iloc[-1]
    rows.append(r)
df = pd.DataFrame(rows)
for k in ("r1","r3","r6"): df[k+"p"] = df[k].rank(pct=True)
df["top"] = (df[["r1p","r3p","r6p"]].max(axis=1) >= 0.98)
print("기준일", last.date(), "종목", len(df))
print("1단계(상위 2% & 6달 안 +30%↑):", int((df.top & (df.run>=0.3)).sum()))
s2 = df[df.top & (df.run>=0.3) & df.above]
print("+10·20일선 위:", len(s2))
s3 = s2[s2.tight & s2.hl & (s2.dist > -0.08)]
print("+좁아지는 쉼(최근 10일 폭 < 앞 20일 폭의 60%, 저점 높아짐, 고점 8% 안):", len(s3))
pd.set_option("display.width", 200)
cols = ["t","close","r1","r3","r6","run","tight","hl","dist","pivot","adr"]
print(df[df.top & (df.run>=0.3)][cols].sort_values("r3", ascending=False).round(3).to_string(index=False))
