# 터틀 규칙 시험용 — 여러 시장을 대표하는 ETF 일봉(분할·배당 반영)을 받아 저장
import yfinance as yf
T = ["SPY","QQQ","IWM","EFA","EEM","EWY","EWJ","FXI","TLT","IEF","GLD","SLV","USO","UNG","DBA","DBC","UUP","FXE","FXY","XLE","XLK","SMH"]
d = yf.download(T, start="2000-01-01", interval="1d", auto_adjust=True, progress=False, threads=True)
d[["Open","High","Low","Close"]].to_pickle("tt_etf.pkl")
print(d["Close"].apply(lambda s: s.first_valid_index().date()).to_string())
