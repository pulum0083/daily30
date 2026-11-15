# 중간선거 비교 지표 검토 — 2018·2026 연초 대비 흐름, 2019 수익률, 1950년 이후 중간선거 뒤 12개월 수익률, 10년물 5% 돌파일
import yfinance as yf, pandas as pd, numpy as np
d = yf.download(["^GSPC", "^IXIC", "^DJI", "^TNX"], start="1949-12-01", interval="1d", auto_adjust=False, progress=False)["Close"]
def ytd(s, y):
    s = s.dropna(); base = s[s.index.year == y - 1].iloc[-1]; x = s[s.index.year == y]
    return (x / base - 1) * 100
for k in ("^GSPC", "^IXIC", "^DJI"):
    print(k, "2018", round(ytd(d[k], 2018).iloc[-1], 2), "2019", round(ytd(d[k], 2019).iloc[-1], 2),
          "2026 지금", round(ytd(d[k], 2026).iloc[-1], 2), "2026 고점", round(ytd(d[k], 2026).max(), 2), ytd(d[k], 2026).idxmax().date())
a, b = ytd(d["^GSPC"], 2018).values, ytd(d["^GSPC"], 2026).values
n = len(b); print("S&P 2026 거래일", n, "· 같은 거래일 수까지 상관", round(np.corrcoef(a[:n], b)[0, 1], 3),
                  "· 일간 등락 상관", round(np.corrcoef(np.diff(a[:n]), np.diff(b))[0, 1], 3))
a2, b2 = ytd(d["^IXIC"], 2018).values, ytd(d["^IXIC"], 2026).values
print("나스닥 상관", round(np.corrcoef(a2[:len(b2)], b2)[0, 1], 3))
s18 = ytd(d["^GSPC"], 2018); print("2018 S&P 저점", round(s18.min(), 2), s18.idxmin().date(), "· 11/6 선거일", round(s18.loc["2018-11-06"], 2))
s26 = ytd(d["^GSPC"], 2026); print("2026 S&P 11/3", round(s26.loc[:"2026-11-03"].iloc[-1], 2), "· 최근", s26.index[-1].date())
# 1950년 이후 중간선거일(11월 첫 월요일 다음 화요일) 종가 → 12개월 뒤
rows = []
s = d["^GSPC"].dropna()
for y in range(1950, 2026, 4):
    y += 2
    if y > 2022: break
    nov1 = pd.Timestamp(y, 11, 1); mon = nov1 + pd.Timedelta(days=(0 - nov1.weekday()) % 7); ed = mon + pd.Timedelta(days=1)
    p0 = s[:ed].iloc[-1]; p1 = s[:ed + pd.DateOffset(years=1)].iloc[-1]
    q4low = s[ed - pd.Timedelta(days=60): ed].min()
    rows.append((y, ed.date(), round((p1 / p0 - 1) * 100, 1)))
r = pd.DataFrame(rows, columns=["y", "election", "next12m"])
print(r.to_string(index=False)); print("중간선거 뒤 12개월: 오른 해", (r.next12m > 0).sum(), "/", len(r), "평균", round(r.next12m.mean(), 1), "중앙값", r.next12m.median())
# 아무 날 12개월 기준선(1950~)
ss = s[s.index >= "1950-01-01"]; fwd = (ss.shift(-252) / ss - 1).dropna() * 100
print("아무 날 12개월 뒤: 오른 비율", round((fwd > 0).mean() * 100, 1), "평균", round(fwd.mean(), 1))
t = d["^TNX"].dropna(); t26 = t[t.index.year == 2026]
print("10년물 2026 첫 5% 이상 종가", t26[t26 >= 5].index.min().date() if (t26 >= 5).any() else None, "최고", round(t26.max(), 2), t26.idxmax().date())
t18 = t[t.index.year == 2018]; print("10년물 2018 첫 3% 이상 종가", t18[t18 >= 3].index.min().date(), "최고", round(t18.max(), 2), t18.idxmax().date())
