# 백테스트용 S&P 500 10년치 일봉(OHLC, 분할·배당 반영)과 ^GSPC를 받아 피클로 저장
import json, sys, yfinance as yf, pandas as pd
items = json.load(open(sys.argv[1]))["items"]
tick = [i[0].replace(".", "-") for i in items] + ["^GSPC"]
raw = yf.download(tick, period="11y", interval="1d", auto_adjust=True, progress=False, threads=True)
raw[["Open", "High", "Low", "Close", "Volume"]].to_pickle("kq_ohlc.pkl")
print(raw["Close"].shape, raw.index[0].date(), raw.index[-1].date())
