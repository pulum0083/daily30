# 나스닥·NYSE 상장 보통주 목록을 만들고 3년치 일봉을 나눠 받아 피클로 저장(성장주 확대 백테스트용)
import re, time, pandas as pd, yfinance as yf
a = pd.read_csv("nasdaqlisted.txt", sep="|")[:-1]
b = pd.read_csv("otherlisted.txt", sep="|")[:-1]
a = a[(a.ETF == "N") & (a["Test Issue"] == "N")][["Symbol", "Security Name"]]
b = b[(b.ETF == "N") & (b["Test Issue"] == "N") & b.Exchange.isin(["N", "A"])][["ACT Symbol", "Security Name"]].rename(columns={"ACT Symbol": "Symbol"})
u = pd.concat([a, b]).dropna()
bad = re.compile(r"warrant|unit|right|preferred|depositary|notes due|debenture|% |acquisition corp", re.I)
u = u[~u["Security Name"].str.contains(bad) & u.Symbol.str.fullmatch(r"[A-Z]{1,5}")]
syms = sorted(set(u.Symbol))
print("대상", len(syms))
parts = []
for k in range(0, len(syms), 400):
    ch = syms[k:k + 400]
    for tr in range(3):
        try:
            d = yf.download(ch, period="3y", interval="1d", auto_adjust=True, progress=False, threads=True)
            parts.append(d[["Open", "High", "Low", "Close", "Volume"]]); break
        except Exception as e:
            print("재시도", k, e); time.sleep(5)
    print(k, flush=True)
D = pd.concat(parts, axis=1)
spx = yf.download("^GSPC", period="3y", interval="1d", auto_adjust=True, progress=False)["Close"].squeeze()
D.to_pickle("kq_g_daily.pkl"); spx.to_pickle("kq_spx3y.pkl")
print(D["Close"].shape, D["Close"].notna().sum(axis=1).iloc[-1])
