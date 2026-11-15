# 쿨라매기 종목 고르기 + 터틀 매매 규칙을 섞은 방식 일봉 백테스트 — 섞은 방식·터틀만·쿨라매기 조건만·아무 날 비교
"""
고르기(쿨라매기): 1·3·6달 상승률 중 하나가 상위 2% · 6달 저점 대비 +30% · 종가 > 10일선 > 20일선 ·
  최근 10일 폭 < 앞 20일 폭의 60% · 저점 높아짐 · 10일 고점에서 8% 안 · 하루 평균 움직임 ADR 이상.
매매(터틀, 전부 일봉): 신호 뒤 5거래일 안 기준선(10일 고점) 돌파에 산다(시가가 위면 시가) ·
  손절 = 산 가격 − 2N(N = 20일 평균 실제 움직임) · 청산 = 20일 최저가 이탈 또는 종가 < 10일선(변형) ·
  산 날 저가가 손절선 아래면 손절된 것으로 본다(불리한 가정). 한 단위만(추가 매수 없음). 체결 손해 0.1%씩.
R = 손익 ÷ 2N(한 번 손절에 잃는 돈).

  python3 hy_bt.py sp500|growth
"""
import sys
import numpy as np
import pandas as pd

SRC = sys.argv[1]
SLIP = 0.001
if SRC == "sp500":
    D = pd.read_pickle("kq_ohlc.pkl")
    O, H, L, C = (D[k].drop(columns="^GSPC") for k in ("Open", "High", "Low", "Close"))
    liq = C.notna()
    ADRMIN = 0.03
else:
    D = pd.read_pickle("kq_g_daily.pkl")
    D = D.loc[:, ~D.columns.duplicated()]
    O, H, L, C, V = (D[k] for k in ("Open", "High", "Low", "Close", "Volume"))
    liq = (C >= 5) & ((C * V).rolling(20).mean() >= 2e7)
    ADRMIN = 0.04

Cl = C.where(liq)
r1, r3, r6 = Cl / Cl.shift(21) - 1, Cl / Cl.shift(63) - 1, Cl / Cl.shift(126) - 1
top = pd.concat([x.rank(axis=1, pct=True) for x in (r1, r3, r6)]).groupby(level=0).max() >= 0.98
run = C / C.rolling(126).min() - 1 >= 0.30
s10, s20 = C.rolling(10).mean(), C.rolling(20).mean()
above = (C > s10) & (C > s20) & (s10 > s20)
tight = (H.rolling(10).max() - L.rolling(10).min()) / C < 0.6 * ((H.rolling(20).max() - L.rolling(20).min()) / C).shift(10)
hl = L.rolling(10).min() > L.rolling(20).min().shift(10)
pv10 = H.rolling(10).max()
near = C / pv10 - 1 > -0.08
adr = (H / L - 1).rolling(20).mean()
TR = np.maximum(H - L, np.maximum((H - C.shift()).abs(), (L - C.shift()).abs()))
N = TR.ewm(alpha=1 / 20, adjust=False).mean()
hi55 = H.rolling(55).max().shift(1)
lo20 = L.rolling(20).min().shift(1)
base = liq & (adr >= ADRMIN)
kq = top & run & above & tight & hl & near & base
rng = np.random.default_rng(3)

MODES = {
    "섞은 방식(쿨라매기 고르기 + 터틀 매매, 20일 최저가 청산)": ("kq", "lo20"),
    "섞은 방식(쿨라매기 고르기 + 터틀 손절, 10일선 청산)": ("kq", "ma10"),
    "터틀만(55일 돌파, 20일 최저가 청산)": ("t55", "lo20"),
    "아무 날(같은 매매 규칙)": ("rand", "lo20"),
}


def sim(sig_kind, exit_kind):
    out = []
    p_rand = float(kq.values.mean()) * 3
    for t in C.columns:
        o, h, l, c = (x[t].values for x in (O, H, L, C))
        n_, sm, l20, h55, pv, ok = N[t].values, s10[t].values, lo20[t].values, hi55[t].values, pv10[t].values, base[t].values
        sig = kq[t].values
        n = len(c)
        i = 130
        while i < n - 1:
            ent = None
            if sig_kind == "kq":
                if sig[i]:
                    for j in range(i + 1, min(i + 6, n)):
                        if h[j] > pv[i]:
                            ent = (j, max(pv[i], o[j])); break
                        if c[j] < sm[j]:
                            break
            elif sig_kind == "t55":
                if ok[i] and not np.isnan(h55[i]) and h[i] > h55[i]:
                    ent = (i, max(h55[i], o[i]))
            else:
                if ok[i] and rng.random() < p_rand:
                    ent = (i, o[i])
            if not ent or np.isnan(n_[ent[0] - 1]):
                i += 1; continue
            j, px = ent
            nn = n_[j - 1]
            px *= (1 + SLIP)
            stop = px - 2 * nn
            if l[j] <= stop:                       # 산 날 손절선을 깼다 — 불리하게 손절로 본다
                out.append((t, j, -1 - SLIP * px / (2 * nn), 0)); i = j + 1; continue
            k, ex = j + 1, None
            while k < n:
                if l[k] <= stop:
                    ex = min(o[k], stop); break
                if exit_kind == "lo20" and l[k] < l20[k]:
                    ex = min(o[k], l20[k]); break
                if exit_kind == "ma10" and c[k] < sm[k]:
                    ex = c[k]; break
                k += 1
            if ex is None:
                break
            ex *= (1 - SLIP)
            out.append((t, j, (ex - px) / (2 * nn), k - j))
            i = k + 1
    T = pd.DataFrame(out, columns=["t", "j", "R", "hold"])
    T["d"] = C.index[T.j]
    return T


print(f"[{SRC}] {C.index[0].date()} ~ {C.index[-1].date()} · 종목 {C.shape[1]} · 하루 움직임 {ADRMIN:.0%} 이상")
for name, (sk, ek) in MODES.items():
    T = sim(sk, ek)
    w = T.R > 0
    top5 = T.R[T.R < T.R.quantile(.95)].mean()
    T["y"] = T.d.dt.year
    yr = " · ".join(f"{y}:{g.R.mean():+.2f}" for y, g in T.groupby("y"))
    print(f"  {name}\n    {len(T)}번 · 이긴 비율 {w.mean():.0%} · 한 번 평균 {T.R.mean():+.2f}R (중앙값 {T.R.median():+.2f}) · "
          f"이긴 평균 {T.R[w].mean():+.2f}R · 진 평균 {T.R[~w].mean():+.2f}R · 상위5% 빼면 {top5:+.2f}R · 보유 중앙값 {T.hold.median():.0f}일\n    해마다 {yr}")
