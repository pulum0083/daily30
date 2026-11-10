# S&P 500 200일선 체크 — 200일선 위 종목 비율, 200일선을 넘은 종목, 과열 종목(미국 브리핑 섹션, 결정론·LLM 없음)
"""
미국 브리핑(21:15 KST = 미국 프리마켓)에 직전 정규장 종가 기준으로 싣는다(2026-11-08 사용자 결정, 시안 A안·T3).

- 200일선: 최근 200거래일 정규장 종가(분할·배당 반영) 평균. 배당락 날의 가격 하락이 추세로 잡히지 않게 배당까지
  반영한다 — StockCharts 같은 '200일선 위 종목 비율' 지표와 같은 방식이다. 배당을 빼면 11/6 기준 비율이 58.8% → 55.9%로
  갈리고, 배당을 많이 주는 종목(유틸리티 등)이 선 아래로 잘못 잡힌다.
- 아래로·위로: 전 거래일엔 반대편에 있다가 직전 정규장 종가로 200일선을 넘은 종목.
- 과열: 200일선보다 40% 이상 높은 종목.

구성 종목은 위키피디아 S&P 500 목록을 읽어 data/sp500_constituents.json에 남긴다. 목록을 못 읽은 날은
그 파일을 쓴다 — 빈 목록으로 0건을 만들지 않는다(§47). 직전 정규장 봉이 없거나 종목이 450개 밑이면 파일을
쓰지 않고 실패한다 — 섹션·텔레그램 줄만 빠진다(§0).

출력: data/sp500_ma200.json(gitignore — generate_html이 analysis에 넣어 스냅샷에 남는다, §45)
     data/sp500_breadth_history.json(커밋) — 날마다 [날짜, 200일선 위 %, 종목 거리 중앙값 %, 과열 수, 20%↓ 수, 종목 수].
     상세 페이지(/stocks/sp500-200/)·주간 장기 리포트가 읽는다. 매일 최근 60거래일을 다시 계산해 덮어쓴다(upsert).
     2020-08 이전 날은 `--backfill`로 한 번 채웠다 — 그 구간은 지금 구성 종목으로 계산한 값이다(생존 편향, 페이지에 밝힌다).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "sp500_ma200.json"
LIST_PATH = ROOT / "data" / "sp500_constituents.json"
HISTORY_PATH = ROOT / "data" / "sp500_breadth_history.json"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
MA_DAYS = 200
HOT_PCT = 40.0          # 과열 기준(사용자 결정 2026-11-08)
MIN_LIST = 480          # 위키 목록이 이보다 짧으면 표가 바뀐 것으로 보고 저장본을 쓴다
MIN_VALID = 450         # 200일선을 계산한 종목이 이보다 적으면 수집 실패로 본다
BREADTH_DAYS = 60
DEEP_PCT = -20.0        # '20% 넘게 아래' — 상세 페이지 분포·지금 vs 보통
EVENT_LINE = 50.0       # 200일선 위 비율이 이 선을 넘나든 날
EVENT_JUMP = 5.0        # 하루에 이만큼(%p) 넘게 움직인 날 — 2025-01~2026-11 463거래일 중 두 조건을 합쳐 34일(한 달 1~2번)


def event_of(now: float, prev: float) -> str:
    """특별한 날인지 — 비율이 50%를 넘나들었거나 하루에 5%p 넘게 움직인 날만(2026-11-09 사용자 결정).
    브리핑 섹션과 텔레그램이 같은 판정을 쓴다. 해당하면 한 줄 설명, 아니면 ''."""
    crossed = (now < EVENT_LINE) != (prev < EVENT_LINE)
    diff = now - prev
    jump = abs(diff) >= EVENT_JUMP
    if crossed:
        where = "절반 아래로 내려왔어요" if now < EVENT_LINE else "다시 절반을 넘었어요"
        return (f"하루에 {abs(diff):.1f}%p {'빠지며' if diff < 0 else '오르며'} " + where + ".") if jump else where + "."
    if jump:
        return f"하루에 {abs(diff):.1f}%p {'빠졌어요' if diff < 0 else '올랐어요'}."
    return ""
BIN = 5                 # 분포 막대 하나의 폭(%p). -50 아래·+50 이상은 양 끝 칸에 모은다
BIN_LO, BIN_HI = -50, 50

SECTOR_KO = {
    "Information Technology": "기술", "Financials": "금융", "Consumer Discretionary": "경기소비재",
    "Consumer Staples": "필수소비재", "Utilities": "유틸리티", "Real Estate": "부동산", "Industrials": "산업재",
    "Health Care": "헬스케어", "Communication Services": "커뮤니케이션", "Energy": "에너지", "Materials": "소재",
}


def fetch_constituents() -> list:
    """[[티커, 회사명, 섹터(영문)], ...]. 위키 목록을 못 읽거나 짧으면 저장본."""
    try:
        import pandas as pd
        html = urllib.request.urlopen(urllib.request.Request(WIKI_URL, headers={"User-Agent": "Mozilla/5.0"}),
                                      timeout=20).read().decode()
        t = pd.read_html(io.StringIO(html))[0]
        items = [[str(s).replace(".", "-"), str(n), str(g)]
                 for s, n, g in zip(t["Symbol"], t["Security"], t["GICS Sector"])]
        if len(items) >= MIN_LIST:
            LIST_PATH.write_text(json.dumps({"updated": datetime.now(KST).strftime("%Y-%m-%d"), "items": items},
                                            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            return items
        print(f"[sp500_ma200] 위키 목록이 {len(items)}개뿐 — 저장본을 쓴다", file=sys.stderr)
    except Exception as e:
        print(f"[sp500_ma200] 위키 목록 조회 실패({e}) — 저장본을 쓴다", file=sys.stderr)
    try:
        return json.loads(LIST_PATH.read_text(encoding="utf-8"))["items"]
    except (OSError, ValueError, KeyError):
        return []


def compute(closes, names: dict, session: date) -> dict | None:
    """closes: 날짜 인덱스 × 티커 열의 정규장 종가 DataFrame. session: 직전 정규장 날짜.

    session 이후 행은 버리고, 마지막 행이 session이 아니면 None — 진행 중이거나 하루 밀린 봉을 쓰지 않는다(§45).
    names: {티커: (회사명, 섹터)}.
    """
    df = closes[[c for c in closes.columns if c in names]]
    df = df[[d.date() <= session for d in df.index]].dropna(how="all")
    if len(df) < MA_DAYS + 2 or df.index[-1].date() != session:
        return None
    ma = df.rolling(MA_DAYS, min_periods=MA_DAYS).mean()
    gap = (df / ma - 1) * 100
    last, prev = gap.iloc[-1], gap.iloc[-2]
    chg = (df.iloc[-1] / df.iloc[-2] - 1) * 100
    valid = [t for t in df.columns if last.notna()[t] and prev.notna()[t] and chg.notna()[t]]
    if len(valid) < MIN_VALID:
        return None

    def row(t):
        n, sec = names[t]
        return {"t": t, "n": n, "sec": SECTOR_KO.get(sec, sec), "chg": round(float(chg[t]), 2),
                "gap": round(float(last[t]), 2)}

    below = [row(t) for t in valid if last[t] < 0 < prev[t]]      # 전날 위 → 이날 아래
    up = [row(t) for t in valid if prev[t] < 0 < last[t]]         # 전날 아래 → 이날 위
    hot = sorted((row(t) for t in valid if last[t] >= HOT_PCT), key=lambda r: -r["gap"])
    rows = history_rows(gap[valid], max(0, len(gap) - BREADTH_DAYS))
    breadth = [[r[0], r[1]] for r in rows]
    lv = last[valid]
    sectors = {}
    for t in valid:
        s = sectors.setdefault(SECTOR_KO.get(names[t][1], names[t][1]), [0, 0])
        s[0] += int(lv[t] > 0)
        s[1] += 1
    above = sum(1 for t in valid if last[t] > 0)
    prev_above = sum(1 for t in valid if prev[t] > 0)
    return {
        "asof": session.isoformat(), "prev": df.index[-2].strftime("%Y-%m-%d"),
        "n": len(valid), "above": above,
        "above_pct": round(above / len(valid) * 100, 1), "above_pct_prev": round(prev_above / len(valid) * 100, 1),
        "breadth": breadth, "below": below, "up": up, "hot": hot,
        "history_rows": rows,
        # 상세 페이지 분포 — 반올림 전 값으로 센다(−0.04%가 '위'로 들어가면 위 비율과 어긋난다)
        "sectors": {k: v for k, v in sorted(sectors.items(), key=lambda kv: -kv[1][0] / kv[1][1])},
        "dist": dist_of([float(lv[t]) for t in valid]),
    }


def dist_of(gaps: list) -> dict:
    """종목별 200일선 거리 → 5%p 막대 개수와 구간 합계. bins: [[구간 시작 %, 개수]] — 첫 칸은 −50 아래, 마지막 칸은 +50 이상."""
    edges = list(range(BIN_LO, BIN_HI, BIN))
    bins = [[BIN_LO - BIN, sum(1 for g in gaps if g < BIN_LO)]]
    bins += [[a, sum(1 for g in gaps if a <= g < a + BIN)] for a in edges]
    bins += [[BIN_HI, sum(1 for g in gaps if g >= BIN_HI)]]
    s = sorted(gaps)
    n = len(s)
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {"bins": bins, "median": round(med, 2),
            "deep": sum(1 for g in gaps if g <= DEEP_PCT),
            "near": sum(1 for g in gaps if DEEP_PCT < g < -DEEP_PCT),
            "mid": sum(1 for g in gaps if -DEEP_PCT <= g < HOT_PCT),
            "hot": sum(1 for g in gaps if g >= HOT_PCT)}


def history_rows(gap, start: int) -> list:
    """gap(날짜 × 종목 거리 %)의 start행부터 날마다 [날짜, 200일선 위 %, 거리 중앙값, 과열 수, 20%↓ 수, 종목 수].
    200일선을 계산한 종목이 MIN_VALID보다 적은 날은 뺀다."""
    out = []
    for i in range(start, len(gap)):
        g = gap.iloc[i].dropna()
        if len(g) < MIN_VALID:
            continue
        out.append([gap.index[i].strftime("%Y-%m-%d"), round(float((g > 0).mean() * 100), 1), round(float(g.median()), 2),
                    int((g >= HOT_PCT).sum()), int((g <= DEEP_PCT).sum()), int(len(g))])
    return out


def upsert_history(rows: list, path: Path = None) -> list:
    """누적 기록에 rows를 날짜 기준으로 덮어쓰고(새 날은 추가) 날짜순으로 저장한다. 저장한 전체 기록을 돌려준다."""
    path = path or HISTORY_PATH
    try:
        cur = json.loads(path.read_text(encoding="utf-8")).get("rows", [])
    except (OSError, ValueError):
        cur = []
    by = {r[0]: r for r in cur}
    for r in rows:
        by[r[0]] = r
    merged = [by[k] for k in sorted(by)]
    path.write_text(json.dumps({"cols": ["date", "above_pct", "median_gap", "hot", "deep", "n"], "rows": merged},
                               separators=(",", ":")) + "\n", encoding="utf-8")
    return merged


def add_caps(result: dict) -> None:
    """아래로·위로 목록을 시가총액 순으로 — 이름이 알려진 종목이 앞에 온다. 시총을 못 읽은 종목은 뒤로."""
    import yfinance as yf
    rows = result["below"] + result["up"]

    def cap(t):
        try:
            return float(yf.Ticker(t).fast_info["marketCap"])
        except Exception:
            return None
    with ThreadPoolExecutor(8) as ex:
        caps = dict(zip([r["t"] for r in rows], ex.map(cap, [r["t"] for r in rows])))
    for k in ("below", "up"):
        for r in result[k]:
            r["cap"] = caps.get(r["t"])
        result[k].sort(key=lambda r: -(r["cap"] or 0))


def download(yf, tickers: list, period: str):
    """정규장 종가(분할·배당 반영)를 한 번에 받고, 통째로 빈 종목만 한 번 더 받는다.
    여러 스레드로 받으면 yfinance 캐시가 'database is locked'로 몇 종목을 놓친다(2026-11-09 주간 작업 HAS 1종목) —
    그대로 두면 그날 비율이 499종목 기준이 되고 누적 기록 최근 60일이 그 값으로 덮인다."""
    raw = yf.download(tickers, period=period, interval="1d", auto_adjust=True, progress=False, threads=True)["Close"]
    miss = [t for t in tickers if t not in raw.columns or raw[t].isna().all()]
    if miss:
        print(f"[sp500_ma200] 빈 종목 {len(miss)}개 다시 받기: {', '.join(miss[:10])}", file=sys.stderr)
        try:
            again = yf.download(miss, period=period, interval="1d", auto_adjust=True, progress=False, threads=False)["Close"]
            if not hasattr(again, "columns"):
                again = again.to_frame(miss[0])
            for t in miss:
                if t in again.columns and not again[t].isna().all():
                    raw[t] = again[t]
        except Exception as e:
            print(f"[sp500_ma200] 다시 받기 실패({e})", file=sys.stderr)
    return raw


def fill_session_close(yf, raw, session: date):
    """그날 일봉 종가가 비어 있으면 그날 5분봉의 마지막 종가로 채운다(2026-11-10).
    야후는 미국 장이 끝나고 몇 시간 동안 개별 종목의 그날 일봉 종가를 비워 둔다 — 11/10 07:25 KST(뉴욕 11/9 17:25)에
    11/9 일봉 종가가 503종목 모두 비어 있었고, 같은 때 5분봉 마지막 값은 장 마감 가격과 같았다(AAPL 350.69).
    정규장 마지막 봉(15:55)까지 와 있을 때만 채운다 — 장이 끝나기 전이면 그대로 둔다."""
    import pandas as pd
    ts = pd.Timestamp(session)
    have = int(raw.loc[ts].notna().sum()) if ts in raw.index else 0
    miss = [t for t in raw.columns if ts not in raw.index or pd.isna(raw.at[ts, t])]
    if not miss or have >= MIN_VALID:
        return raw
    try:
        intr = yf.download(miss, period="5d", interval="5m", auto_adjust=True, prepost=False, progress=False,
                           threads=True)["Close"]
    except Exception as e:
        print(f"[sp500_ma200] 5분봉 조회 실패({e}) — 그날 종가를 채우지 못함", file=sys.stderr)
        return raw
    if not hasattr(intr, "columns"):
        intr = intr.to_frame(miss[0])
    idx = intr.index.tz_convert(ET) if intr.index.tz is not None else intr.index
    day = intr[[d.date() == session for d in idx]]
    day_idx = [d for d in idx if d.date() == session]
    if not len(day) or max(d.hour * 60 + d.minute for d in day_idx) < 15 * 60 + 55:
        print(f"[sp500_ma200] {session} 5분봉이 장 마감까지 오지 않음 — 그날 종가를 채우지 않는다", file=sys.stderr)
        return raw
    last = day.ffill().iloc[-1]
    if ts not in raw.index:
        raw.loc[ts] = float("nan")
        raw = raw.sort_index()
    n = 0
    for t in miss:
        v = last.get(t)
        if v is not None and pd.notna(v):
            raw.at[ts, t] = float(v)
            n += 1
    print(f"[sp500_ma200] {session} 일봉 종가가 비어 있던 {len(miss)}종목 중 {n}종목을 5분봉 마지막 값으로 채움")
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="브리핑 날짜(KST, 기본 오늘)")
    ap.add_argument("--backfill", action="store_true", help="7년치 일봉으로 누적 기록(sp500_breadth_history.json)을 처음부터 채운다")
    args = ap.parse_args()
    import yfinance as yf
    from session_label import prev_us_session

    brief = date.fromisoformat(args.date) if args.date else datetime.now(KST).date()
    session = prev_us_session(brief)
    items = fetch_constituents()
    if len(items) < MIN_VALID:
        print(f"[sp500_ma200] 구성 종목 {len(items)}개 — 중단", file=sys.stderr)
        return 1
    names = {t: (n, s) for t, n, s in items}
    raw = download(yf, list(names), "7y" if args.backfill else "15mo")
    if not args.backfill:
        raw = fill_session_close(yf, raw, session)
    if args.backfill:
        df = raw[[d.date() <= session for d in raw.index]]
        gap = (df / df.rolling(MA_DAYS, min_periods=MA_DAYS).mean() - 1) * 100
        merged = upsert_history(history_rows(gap, 0))
        print(f"[sp500_ma200] 누적 기록 백필 — {len(merged)}일({merged[0][0]} ~ {merged[-1][0]})")
        return 0
    result = compute(raw, names, session)
    if result is None:
        last = raw.index[-1].date() if len(raw) else None
        print(f"[sp500_ma200] 계산 불가(직전 정규장 {session}, 마지막 봉 {last}) — 파일을 쓰지 않는다", file=sys.stderr)
        for ts in raw.index[-4:]:   # 어느 날짜에 종가가 몇 종목 있는지 — 원인을 짐작하지 않고 로그로 본다
            print(f"[sp500_ma200]   {ts} 종가 있는 종목 {int(raw.loc[ts].notna().sum())}/{raw.shape[1]}", file=sys.stderr)
        return 1
    add_caps(result)
    upsert_history(result.pop("history_rows"))
    result["date"] = brief.isoformat()
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[sp500_ma200] {session} 200일선 위 {result['above_pct']}% ({result['n']}개) · 아래로 {len(result['below'])}"
          f" · 위로 {len(result['up'])} · 과열 {len(result['hot'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
