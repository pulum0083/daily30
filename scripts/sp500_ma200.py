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
ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "sp500_ma200.json"
LIST_PATH = ROOT / "data" / "sp500_constituents.json"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
MA_DAYS = 200
HOT_PCT = 40.0          # 과열 기준(사용자 결정 2026-11-08)
MIN_LIST = 480          # 위키 목록이 이보다 짧으면 표가 바뀐 것으로 보고 저장본을 쓴다
MIN_VALID = 450         # 200일선을 계산한 종목이 이보다 적으면 수집 실패로 본다
BREADTH_DAYS = 60

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
    breadth = []
    for i in range(max(0, len(gap) - BREADTH_DAYS), len(gap)):
        g = gap.iloc[i][valid].dropna()
        if len(g) >= MIN_VALID:
            breadth.append([gap.index[i].strftime("%Y-%m-%d"), round(float((g > 0).mean() * 100), 1)])
    above = sum(1 for t in valid if last[t] > 0)
    prev_above = sum(1 for t in valid if prev[t] > 0)
    return {
        "asof": session.isoformat(), "prev": df.index[-2].strftime("%Y-%m-%d"),
        "n": len(valid), "above": above,
        "above_pct": round(above / len(valid) * 100, 1), "above_pct_prev": round(prev_above / len(valid) * 100, 1),
        "breadth": breadth, "below": below, "up": up, "hot": hot,
    }


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="브리핑 날짜(KST, 기본 오늘)")
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
    raw = yf.download(list(names), period="15mo", interval="1d", auto_adjust=True,
                      progress=False, threads=True)["Close"]
    result = compute(raw, names, session)
    if result is None:
        last = raw.index[-1].date() if len(raw) else None
        print(f"[sp500_ma200] 계산 불가(직전 정규장 {session}, 마지막 봉 {last}) — 파일을 쓰지 않는다", file=sys.stderr)
        return 1
    add_caps(result)
    result["date"] = brief.isoformat()
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[sp500_ma200] {session} 200일선 위 {result['above_pct']}% ({result['n']}개) · 아래로 {len(result['below'])}"
          f" · 위로 {len(result['up'])} · 과열 {len(result['hot'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
