# S&P 500 돌파 관찰 목록 — 쿨라매기 조건으로 고른 종목의 10일 최고가 돌파와 그 뒤 터틀 규칙 결과(미국 브리핑 섹션, 결정론·LLM 없음)
"""
미국 브리핑(21:15 KST = 미국 프리마켓)에 직전 정규장 종가 기준으로 싣는다(2026-11-16 사용자 결정, §88).
정의는 2026-11-15 백테스트(docs/plans/2026-11-15-turtle-review/hy_bt.py·hy_state.py)와 같다 — 바꾸면 그 성적이 이 화면의 근거가 아니게 된다.

조건(쿨라매기, 그날 종가로 판정)
  1·3·6달 상승률 중 하나가 S&P 500 상위 2% · 6달 저점에서 +30% 이상 · 종가 > 10일선 > 20일선 ·
  최근 10일 폭 < 그 전 20일 폭의 60% · 최근 10일 저점 > 그 전 20일 저점 · 10일 최고가에서 8% 안 ·
  하루 평균 움직임(ADR20) 3% 이상.
돌파: 조건을 채운 날(k)로부터 5거래일 안에 그날의 10일 최고가(기준선)를 처음 넘은 날. 산 가격 = max(기준선, 그날 시가).
  넘기 전에 종가가 10일선 아래로 내려가면 그 조건은 무효다. 같은 종목은 앞 돌파가 끝나기 전엔 새 돌파로 세지 않는다
  (2026-11-26 — 백테스트 hy_bt.py와 맞췄다. 그 전엔 이 둘이 없어 젠 디지털이 '진행 중'과 '오늘 돌파'에 함께 나왔다).
결과(터틀): 손절선 = 산 가격 − 2N(N = 20일 평균 실제 움직임, 전날 값), 추세 끝 = 20일 최저가 이탈(산 다음 날부터).
  돌파한 날 저가가 손절선 아래면 그날 손절로 본다(백테스트와 같은 불리한 가정).

출력: data/breakout_watch.json(gitignore — generate_html이 analysis에 넣어 스냅샷에 남는다, §45).
직전 정규장 봉이 없거나 종목이 450개 밑이면 파일을 쓰지 않고 실패한다 — 섹션만 빠진다(§0).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "breakout_watch.json"
MIN_VALID = 450
ADR_MIN = 0.03
LOOKBACK = 60        # 이 거래일 안에 돌파한 종목만 추적한다
WINDOW = 5           # 조건을 채운 날로부터 며칠 안의 돌파만 센다
SHOW_ENDED = 5       # 끝난 종목은 끝난 지 이 거래일까지만 결과 칸에 남긴다
MAX_WAIT = 6
MAX_TRACK = 10


def indicators(O, H, L, C):
    """hy_bt.py(sp500)와 같은 정의. 입력은 날짜 × 종목 DataFrame."""
    import numpy as np
    import pandas as pd
    r1, r3, r6 = C / C.shift(21) - 1, C / C.shift(63) - 1, C / C.shift(126) - 1
    rk = {"1달": r1.rank(axis=1, pct=True), "3달": r3.rank(axis=1, pct=True), "6달": r6.rank(axis=1, pct=True)}
    top = pd.concat(rk.values()).groupby(level=0).max() >= 0.98
    run = C / C.rolling(126).min() - 1 >= 0.30
    s10, s20 = C.rolling(10).mean(), C.rolling(20).mean()
    above = (C > s10) & (C > s20) & (s10 > s20)
    tight = (H.rolling(10).max() - L.rolling(10).min()) / C < 0.6 * ((H.rolling(20).max() - L.rolling(20).min()) / C).shift(10)
    hl = L.rolling(10).min() > L.rolling(20).min().shift(10)
    pv10 = H.rolling(10).max()
    near = C / pv10 - 1 > -0.08
    adr = (H / L - 1).rolling(20).mean()
    tr = np.maximum(H - L, np.maximum((H - C.shift()).abs(), (L - C.shift()).abs()))
    N = tr.ewm(alpha=1 / 20, adjust=False).mean()
    lo20 = L.rolling(20).min().shift(1)
    kq = top & run & above & tight & hl & near & C.notna() & (adr >= ADR_MIN)
    return {"kq": kq, "pv10": pv10, "N": N, "lo20": lo20, "s10": s10, "rk": rk, "ret": {"1달": r1, "3달": r3, "6달": r6}}


def find_breakouts(kq, H, pv10, start: int, end: int, C=None, s10=None) -> list:
    """start~end 거래일 사이 돌파 후보 [(종목, 돌파일 i, 조건일 k)] — 기준선을 처음 넘은 날.
    C·s10을 주면 넘기 전(k+1~i-1)에 종가가 10일선 아래로 내려간 조건은 무효로 본다(백테스트와 같다).
    같은 종목이 앞 돌파 중에 또 넘는 건 compute()가 거른다."""
    out = []
    for t in kq.columns:
        q, h, p = kq[t].to_numpy(), H[t].to_numpy(), pv10[t].to_numpy()
        c = C[t].to_numpy() if C is not None and s10 is not None else None
        m = s10[t].to_numpy() if c is not None else None
        for i in range(start, end + 1):
            for k in range(max(i - WINDOW, 0), i):
                if not (q[k] and h[i] > p[k]) or (h[k + 1:i] > p[k]).any():
                    continue
                if c is not None and (c[k + 1:i] < m[k + 1:i]).any():
                    continue
                out.append((t, i, k))
                break
    return out


def pending(kq, H, C, pv10, s10, I: int, live: set, free_from: dict) -> dict:
    """다음 거래일(I+1)에 돌파로 셀 수 있는 종목 {종목: 조건일 k} — find_breakouts가 I+1에서 보는 조건일 그대로다.
    k는 I−WINDOW+1~I, 그 뒤 I까지 기준선(그날 10일 최고가)을 넘지 않았고 종가가 10일선 아래로 내려가지 않았어야 한다.
    조건일이 여럿이면 기준선이 가장 낮은 날(그 선을 넘는 순간 돌파로 센다). 2026-11-28 — 그 전엔 오늘 조건만 봐서
    며칠 전 조건으로 돌파한 종목이 전날 '기다리는 중'에 없었다(지난 200거래일 돌파 후보 326건 중 23건)."""
    out = {}
    for t in kq.columns:
        if t in live:
            continue
        q, h, p, c = kq[t].to_numpy(), H[t].to_numpy(), pv10[t].to_numpy(), C[t].to_numpy()
        m = s10[t].to_numpy() if s10 is not None else None
        ks = [k for k in range(max(I - WINDOW + 1, 0), I + 1)
              if q[k] and k >= free_from.get(t, -1) and not (h[k + 1:I + 1] > p[k]).any()
              and (m is None or not (c[k + 1:I + 1] < m[k + 1:I + 1]).any())]
        if ks:
            out[t] = min(ks, key=lambda k: p[k])
    return out


def why(ind, H, L, C, t: str, k: int) -> dict:
    """고른 이유 — 가장 센 기간 상승률·상위 %, 최근 10일 폭과 그 전 20일 폭."""
    import math
    rk = {b: ind["rk"][b][t].iloc[k] for b in ind["rk"]}
    best = max(rk, key=lambda b: rk[b] if not math.isnan(rk[b]) else -1)
    c = C[t].iloc[k]
    w10 = (H[t].iloc[k - 9:k + 1].max() - L[t].iloc[k - 9:k + 1].min()) / c * 100
    w20 = (H[t].iloc[k - 29:k - 9].max() - L[t].iloc[k - 29:k - 9].min()) / c * 100
    return {"best": best, "ret": round(float(ind["ret"][best][t].iloc[k]) * 100), "top": max(round((1 - rk[best]) * 100, 1), 0.1),
            "w10": round(float(w10), 1), "w20": round(float(w20), 1)}


def compute(O, H, L, C, session: date) -> dict | None:
    """직전 정규장(session)까지의 일봉으로 오늘 돌파·기다림·결과를 만든다. 그날 봉이 없거나 종목이 모자라면 None."""
    import pandas as pd
    ts = pd.Timestamp(session)
    keep = [d <= ts for d in C.index]
    O, H, L, C = O[keep], H[keep], L[keep], C[keep]
    if not len(C) or C.index[-1] != ts or int(C.iloc[-1].notna().sum()) < MIN_VALID:
        return None
    ind = indicators(O, H, L, C)
    kq, pv10, N, lo20 = ind["kq"], ind["pv10"], ind["N"], ind["lo20"]
    I = len(C) - 1
    days = [d.date().isoformat() for d in C.index]
    today, track, live = [], [], set()
    free_from = {}       # 종목별로 새 돌파를 셀 수 있는 첫 조건일 — 앞 돌파가 끝난 다음 날부터(진행 중이면 없음)
    for t, i, k in sorted(find_breakouts(kq, H, pv10, max(I - 2 * LOOKBACK, 0), I, C, ind.get("s10")), key=lambda x: (x[0], x[1])):
        if t in live or k < free_from.get(t, -1):
            continue
        piv, n = float(pv10[t].iloc[k]), float(N[t].iloc[i - 1])
        ent = max(piv, float(O[t].iloc[i]))
        stop = ent - 2 * n
        state, ex_i, ex = "live", None, None
        for j in range(i, I + 1):
            lo = float(L[t].iloc[j])
            if lo <= stop:
                state, ex_i, ex = "stop", j, (min(float(O[t].iloc[j]), stop) if j > i else stop)
                break
            if j > i and lo < float(lo20[t].iloc[j]):
                state, ex_i, ex = "exit", j, min(float(O[t].iloc[j]), float(lo20[t].iloc[j]))
                break
        if ex_i is not None:
            free_from[t] = ex_i + 1
        if i == I and state == "live":
            c = float(C[t].iloc[I])
            today.append({"t": t, "close": round(c, 2), "chg": round((c / float(C[t].iloc[I - 1]) - 1) * 100, 2),
                          "pivot": round(piv, 2), "open": round(float(O[t].iloc[I]), 2),
                          "entry": round(ent, 2), "stop": round(stop, 2), "why": why(ind, H, L, C, t, k)})
            live.add(t)
            continue
        if state == "live":
            live.add(t)
        elif I - ex_i > SHOW_ENDED:
            continue
        if i < I - LOOKBACK:     # 앞쪽은 겹침을 가리려고만 훑었다 — 결과 칸엔 최근 LOOKBACK 거래일 돌파만
            continue
        cur = ex if ex is not None else float(C[t].iloc[I])
        track.append({"t": t, "from": days[i], "state": state, "days": (ex_i if ex_i is not None else I) - i,
                      "pct": round((cur / ent - 1) * 100, 1)})
    wait = []
    for t, k in pending(kq, H, C, pv10, ind.get("s10"), I, live, free_from).items():
        c, piv, n = float(C[t].iloc[I]), float(pv10[t].iloc[k]), float(N[t].iloc[I])
        wait.append({"t": t, "close": round(c, 2), "pivot": round(piv, 2), "stop": round(piv - 2 * n, 2),
                     "to_pivot": round((piv / c - 1) * 100, 1), "since": days[k], "why": why(ind, H, L, C, t, k)})
    wait.sort(key=lambda r: r["to_pivot"])
    track.sort(key=lambda r: r["from"], reverse=True)
    return {"asof": days[I], "n": int(C.iloc[-1].notna().sum()), "today": today, "wait": wait, "track": track}


def order_by_cap(result: dict, caps: dict) -> dict:
    """세 목록을 시가총액 큰 순으로(2026-11-16 사용자 결정) 세우고 개수를 자른다. 시총을 못 읽은 종목은 뒤로, 그 안에선 원래 순서."""
    key = lambda r: -(caps.get(r["t"]) or 0)
    for k in ("today", "wait", "track"):
        for r in result[k]:
            r["cap"] = caps.get(r["t"])
        result[k].sort(key=key)
    result["wait_more"] = max(len(result["wait"]) - MAX_WAIT, 0)
    result["wait"] = result["wait"][:MAX_WAIT]
    result["track"] = result["track"][:MAX_TRACK]
    return result


def fetch_caps(tickers: list) -> dict:
    """시가총액(달러) — 야후 fast_info. 못 읽으면 빠진다(sp500_ma200.add_caps와 같은 원천)."""
    import yfinance as yf

    def cap(t):
        try:
            return float(yf.Ticker(t).fast_info["marketCap"])
        except Exception:
            return None
    with ThreadPoolExecutor(8) as ex:
        return {t: c for t, c in zip(tickers, ex.map(cap, tickers)) if c}


def add_names(result: dict, names: dict) -> None:
    """보여줄 종목만 한글 이름을 붙인다(네이버). 못 읽으면 영문 회사명."""
    from fetch_data import _naver_us_basic
    rows = result["today"] + result["wait"] + result["track"]
    tickers = sorted({r["t"] for r in rows})

    def ko(t):
        try:
            d = _naver_us_basic(t.replace("-", "."))
            return (d or {}).get("stockName") or None
        except Exception:
            return None
    with ThreadPoolExecutor(6) as ex:
        got = dict(zip(tickers, ex.map(ko, tickers)))
    for r in rows:
        r["name"] = got.get(r["t"]) or names.get(r["t"], r["t"])


def download(yf, tickers: list):
    """분할·배당 반영 일봉 OHLC 15개월 — 통째로 빈 종목은 한 번 더 받는다(sp500_ma200.download와 같은 이유)."""
    raw = yf.download(tickers, period="15mo", interval="1d", auto_adjust=True, progress=False, threads=True)
    O, H, L, C = (raw[k] for k in ("Open", "High", "Low", "Close"))
    miss = [t for t in tickers if t not in C.columns or C[t].isna().all()]
    if miss:
        print(f"[breakout_watch] 빈 종목 {len(miss)}개 다시 받기: {', '.join(miss[:10])}", file=sys.stderr)
        try:
            again = yf.download(miss, period="15mo", interval="1d", auto_adjust=True, progress=False, threads=False)
            for t in miss:
                for frame, key in ((O, "Open"), (H, "High"), (L, "Low"), (C, "Close")):
                    col = again[key]
                    s = col[t] if hasattr(col, "columns") and t in col.columns else (col if len(miss) == 1 else None)
                    if s is not None and not s.isna().all():
                        frame[t] = s
        except Exception as e:
            print(f"[breakout_watch] 다시 받기 실패({e})", file=sys.stderr)
    return O, H, L, C


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="브리핑 날짜(KST, 기본 오늘)")
    args = ap.parse_args()
    import yfinance as yf
    from session_label import prev_us_session
    from sp500_ma200 import fetch_constituents

    brief = date.fromisoformat(args.date) if args.date else datetime.now(KST).date()
    session = prev_us_session(brief)
    items = fetch_constituents()
    if len(items) < MIN_VALID:
        print(f"[breakout_watch] 구성 종목 {len(items)}개 — 중단", file=sys.stderr)
        return 1
    names = {t: n for t, n, _ in items}
    O, H, L, C = download(yf, list(names))
    result = compute(O, H, L, C, session)
    if result is None:
        last = C.index[-1].date() if len(C) else None
        print(f"[breakout_watch] 계산 불가(직전 정규장 {session}, 마지막 봉 {last}) — 파일을 쓰지 않는다", file=sys.stderr)
        return 1
    order_by_cap(result, fetch_caps(sorted({r["t"] for k in ("today", "wait", "track") for r in result[k]})))
    add_names(result, names)
    result["date"] = brief.isoformat()
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[breakout_watch] {result['asof']} 돌파 {[r['t'] for r in result['today']]} · 기다림 "
          f"{[r['t'] for r in result['wait']]}(+{result['wait_more']}) · 결과 {len(result['track'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
