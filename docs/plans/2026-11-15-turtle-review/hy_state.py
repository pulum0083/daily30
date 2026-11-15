# 섞은 방식 관찰 목록 시안용 — S&P 500 지정일 종가 기준 돌파·대기·진행 중 종목과 사다리 값, 고른 이유를 JSON으로
import sys, json, io, contextlib, runpy
import numpy as np, pandas as pd
ASOF = sys.argv[1]
sys.argv = ["hy_bt.py", "sp500"]
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path("hy_bt.py", run_name="lib")
C, H, L, O, kq, pv10, N, lo20, s10, r1, r3, r6 = (g[k] for k in ("C", "H", "L", "O", "kq", "pv10", "N", "lo20", "s10", "r1", "r3", "r6"))
meta = {i[0].replace(".", "-"): i[1] for i in json.load(open("sp500_constituents.json"))["items"]}
idx = C.index
I = idx.get_loc(pd.Timestamp(ASOF))
rk = {k: x.rank(axis=1, pct=True) for k, x in (("1달", r1), ("3달", r3), ("6달", r6))}

def breakouts_upto(i_end, start):
    """start~i_end 사이 돌파(처음 넘은 날), 같은 종목은 10거래일 안에 다시 세지 않는다."""
    out, last = [], {}
    for i in range(start, i_end + 1):
        for t in C.columns:
            for k in range(i - 5, i):
                if kq[t].iloc[k] and H[t].iloc[i] > pv10[t].iloc[k] and not (H[t].iloc[k + 1:i] > pv10[t].iloc[k]).any():
                    if t in last and i - last[t] <= 10:
                        break
                    last[t] = i
                    p = pv10[t].iloc[k]; ent = max(p, O[t].iloc[i]); n = N[t].iloc[i - 1]
                    out.append({"t": t, "i": i, "k": k, "entry": ent, "n": n, "stop": ent - 2 * n})
                    break
    return out

def why(t, k):
    best = max(rk, key=lambda x: rk[x][t].iloc[k] if not np.isnan(rk[x][t].iloc[k]) else 0)
    ret = {"1달": r1, "3달": r3, "6달": r6}[best][t].iloc[k] * 100
    pct_top = (1 - rk[best][t].iloc[k]) * 100
    w10 = (H[t].iloc[k - 9:k + 1].max() - L[t].iloc[k - 9:k + 1].min()) / C[t].iloc[k] * 100
    w20 = (H[t].iloc[k - 29:k - 9].max() - L[t].iloc[k - 29:k - 9].min()) / C[t].iloc[k] * 100
    return {"best": best, "ret": round(ret, 0), "top": max(round(pct_top, 1), 0.1), "w10": round(w10, 1), "w20": round(w20, 1)}

bs = breakouts_upto(I, I - 60)
today = [b for b in bs if b["i"] == I]
# 진행 중·최근 끝남 — 2N 손절·20일 최저가 청산으로 asof까지
track = []
for b in bs:
    if b["i"] == I:
        continue
    t, ent, stop = b["t"], b["entry"], b["stop"]
    st, ex_i, ex = "진행 중", None, None
    for j in range(b["i"], I + 1):
        lo = L[t].iloc[j]
        if lo <= stop: ex_i, ex, st = j, min(O[t].iloc[j], stop) if j > b["i"] else stop, "손절"; break
        if j > b["i"] and lo < lo20[t].iloc[j]: ex_i, ex, st = j, min(O[t].iloc[j], lo20[t].iloc[j]), "20일 최저가"; break
    cur = ex if ex is not None else C[t].iloc[I]
    R = (cur - ent) / (2 * b["n"])
    if st == "진행 중" or I - ex_i <= 5:
        track.append({"t": t, "name": meta.get(t, t), "from": str(idx[b["i"]].date()), "days": (ex_i or I) - b["i"],
                      "state": st, "R": round(R, 2), "pct": round((cur / ent - 1) * 100, 1)})
def card(t, k, ent=None, n=None, stop=None):
    c = C[t].iloc[I]; p = pv10[t].iloc[k]; nn = n if n is not None else N[t].iloc[I]
    e = ent if ent is not None else p
    st = stop if stop is not None else e - 2 * nn
    return {"t": t, "name": meta.get(t, t), "close": round(c, 2), "chg": round((c / C[t].iloc[I - 1] - 1) * 100, 2),
            "pivot": round(p, 2), "entry": round(e, 2), "stop": round(st, 2), "stop_pct": round((st / e - 1) * 100, 1),
            "lo20": round(L[t].iloc[I - 19:I + 1].min(), 2), "npct": round(nn / c * 100, 1),
            "to_pivot": round((p / c - 1) * 100, 1), "why": why(t, k)}
out = {"asof": ASOF,
       "today": [card(b["t"], b["k"], b["entry"], b["n"], b["stop"]) for b in today],
       "wait": [card(t, I) for t in C.columns if kq[t].iloc[I] and t not in {b["t"] for b in today}],
       "track": sorted(track, key=lambda x: x["from"], reverse=True)}
json.dump(out, open(f"hy_{ASOF}.json", "w"), ensure_ascii=False, indent=1)
print(ASOF, "돌파", [c["t"] for c in out["today"]], "대기", [c["t"] for c in out["wait"]])
for x in out["track"]: print("  ", x)
for c in out["today"] + out["wait"]: print("  ", c["t"], c["close"], c["pivot"], c["stop"], c["lo20"], c["npct"], c["why"])
