# 중간선거 해 비교(2018 vs 2026) 수집 — S&P 500·나스닥·10년물 일봉과 연준 기준금리로 data/midterm_2018.json을 쓴다
"""
종목 홈 장기 신호 줄과 /stocks/midterm-2018/ 상세 페이지의 원천(2026-11-15 사용자 결정, 시안 docs/prototypes/2026-11-15-midterm-2018.html).
숫자는 전부 실측이다(§0) — 야후 일봉(nasdaq_overheat.fetch_daily)과 FRED 연준 목표 범위 상단(DFEDTARU).

기준은 직전 미국장 종가다(session_label.prev_us_session). 그 날짜의 S&P 500 일봉이 없으면 파일을 쓰지 않는다 —
하루 밀린 봉을 쓰지 않는다(§45). 2027년이 끝나면(비교할 2019년이 끝나면) 더 쓰지 않는다.

  python3 scripts/midterm_compare.py --date 2026-11-16     # KST 날짜 → 직전 미국장(11/13) 기준
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nasdaq_overheat as nq  # noqa: E402
from session_label import prev_us_session  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "midterm_2018.json"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU"
Y0, Y1 = 2018, 2026          # 비교하는 두 중간선거 해(같은 대통령의 첫 중간선거)
LAST_DAY = "2027-12-31"      # 2019년에 해당하는 2027년이 끝나면 비교를 멈춘다


def fetch_daily(symbol: str) -> list:
    """야후 일봉 [(날짜, 고가, 저가, 종가)] — 1950년부터. nasdaq_overheat.fetch_daily는 period1=0(1970년)부터라
    1950~1966년 중간선거가 빠진다."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(symbol)}"
           "?period1=-631152000&period2=4102444800&interval=1d")
    r = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=nq.UA), timeout=60).read())
    res = r["chart"]["result"][0]
    off = res["meta"].get("gmtoffset", 0)
    q = res["indicators"]["quote"][0]
    out = []
    for t, h, lo, c in zip(res["timestamp"], q["high"], q["low"], q["close"]):
        if None in (h, lo, c):
            continue
        out.append((datetime.utcfromtimestamp(t + off).strftime("%Y-%m-%d"), float(h), float(lo), float(c)))
    return out


def ytd_path(daily: list, year: int, until: str = "9999") -> list:
    """year-1년 마지막 종가 대비 등락 % — [일(1월 1일=0), %, 날짜] 두 해치(year·year+1), until까지."""
    base = [c for d, c in daily if d[:4] == str(year - 1)]
    if not base:
        return []
    b, d0 = base[-1], date(year, 1, 1)
    return [[(date.fromisoformat(d) - d0).days, round((c / b - 1) * 100, 2), d]
            for d, c in daily if str(year) <= d[:4] <= str(year + 1) and d <= until]


def at_or_before(rows: list, d: str):
    """[(날짜, 값)] 오래된→최신에서 d 이하 마지막 행. 없으면 None."""
    out = None
    for r in rows:
        if r[0] <= d:
            out = r
        else:
            break
    return out


def corr(xs: list, ys: list) -> float | None:
    n = min(len(xs), len(ys))
    if n < 20:
        return None
    xs, ys = xs[:n], ys[:n]
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sx = sum((a - mx) ** 2 for a in xs) ** .5
    sy = sum((b - my) ** 2 for b in ys) ** .5
    return round(sxy / (sx * sy), 2) if sx and sy else None


def drawdown(daily: list, year: str, d: str) -> float | None:
    """d 종가가 그해(1월~d) 최고 종가보다 몇 % 아래인지."""
    xs = [c for x, c in daily if x[:4] == year and x <= d]
    return round((xs[-1] / max(xs) - 1) * 100, 1) if xs else None


def midterm_day(y: int) -> date:
    """11월 첫 월요일 다음 화요일."""
    n1 = date(y, 11, 1)
    return n1 + timedelta(days=(0 - n1.weekday()) % 7 + 1)


def midterm_stats(daily: list, until: str) -> tuple:
    """1950년부터 끝난 중간선거마다 선거일 종가 → 12개월 뒤 종가 %. 그리고 아무 날 12개월 뒤 기준선(오른 비율·평균)."""
    rows = []
    for y in range(1950, 2100, 4):
        ed = midterm_day(y)
        end = ed.replace(year=y + 1)
        if end.isoformat() > until:
            break
        p0 = at_or_before(daily, ed.isoformat())
        p1 = at_or_before(daily, end.isoformat())
        if p0 and p1:
            rows.append([y, round((p1[1] / p0[1] - 1) * 100, 1)])
    s = [(d, c) for d, c in daily if d >= "1950-01-01"]
    fwd = [(s[i + 252][1] / s[i][1] - 1) * 100 for i in range(len(s) - 252)]
    base = {"up": round(sum(f > 0 for f in fwd) / len(fwd) * 100, 1), "avg": round(sum(fwd) / len(fwd), 1)} if fwd else {}
    return rows, base


def year_ret(daily: list, y: int) -> float | None:
    a = [c for d, c in daily if d[:4] == str(y - 1)]
    b = [c for d, c in daily if d[:4] == str(y)]
    return round((b[-1] / a[-1] - 1) * 100, 1) if a and b else None


def fred_upper() -> list:
    """연준 목표 범위 상단 [(날짜, %)] 오래된→최신. 실패하면 빈 목록(그 칸만 빠진다)."""
    text = ""
    try:
        req = urllib.request.Request(FRED_URL, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=15).read().decode()
    except Exception as e:
        # 파이썬 urllib이 FRED에 붙지 못하는 경로가 있다(로컬 실측: curl 0.3초, urllib 시간 초과) — curl로 한 번 더
        try:
            text = subprocess.run(["curl", "-s", "--max-time", "30", FRED_URL], capture_output=True, text=True, check=True).stdout
        except Exception as e2:
            print(f"[midterm] FRED 조회 실패({e} / {e2}) — 기준금리 칸을 뺀다", file=sys.stderr)
            return []
    out = []
    for line in text.splitlines()[1:]:
        d, _, v = line.partition(",")
        try:
            out.append((d, float(v)))
        except ValueError:
            continue
    return out


def rate_changes(fed: list, start: str, end: str) -> list:
    """start~end 사이 상단이 바뀐 결정 [결정일, 새 값, +1|−1]. FRED는 FOMC 결정 다음 날 값이 바뀌므로 하루 빼 결정일로 둔다
    (2019-08-01 → 7/31 인하, 2026-09-17 → 9/16 인상)."""
    out, prev = [], None
    for d, v in fed:
        if prev is not None and v != prev:
            dec = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
            if dec > end:
                break
            if dec >= start:
                out.append([dec, v, 1 if v > prev else -1])
        prev = v
    return out


def build(spx: list, ixic: list, tnx: list, fed: list, session: str) -> dict | None:
    spx = [(d, c) for d, _h, _l, c in spx if d <= session]
    if not spx or spx[-1][0] != session:
        print(f"[midterm] S&P 500 {session} 종가 없음(마지막 {spx[-1][0] if spx else '-'}) — 쓰지 않는다", file=sys.stderr)
        return None
    ixic = [(d, c) for d, _h, _l, c in ixic if d <= session]
    tnx = [(d, c) for d, _h, _l, c in tnx if d <= session]
    a, b = ytd_path(spx, Y0), ytd_path(spx, Y1, session)
    if len(b) < 20:
        return None
    same_d = session.replace(str(int(session[:4])), str(int(session[:4]) - (Y1 - Y0)), 1)
    same = at_or_before([(p[2], p[1]) for p in a], same_d)
    da, db = [p[1] for p in a], [p[1] for p in b]
    out = {
        "asof": session, "years": [Y0, Y1], "a": a, "b": b,
        "same": {"date": same[0], "pct": same[1]} if same else None,
        "corr": corr(da, db),
        "corr_daily": corr([y - x for x, y in zip(da, da[1:])], [y - x for x, y in zip(db, db[1:])]),
        "dd": {"a": drawdown(spx, same[0][:4], same[0]) if same else None, "b": drawdown(spx, session[:4], session)},
        "low_a": None, "tnx": {}, "fed": {}, "ret": {},
    }
    a0 = [(d, c) for d, c in spx if d[:4] == str(Y0)]
    lo = min(a0, key=lambda r: r[1])
    out["low_a"] = {"date": lo[0], "pct": next(p[1] for p in a if p[2] == lo[0]),
                    "dd": round((lo[1] / max(c for _d, c in a0) - 1) * 100, 1)}
    if same:
        ta, tb = at_or_before(tnx, same[0]), at_or_before(tnx, session)
        if ta and tb:
            out["tnx"] = {"a": round(ta[1], 2), "b": round(tb[1], 2)}
    if fed and same:
        ua, ub = at_or_before(fed, same[0]), at_or_before(fed, session)
        if ua and ub:
            out["fed"] = {"a": ua[1], "b": ub[1],
                          "a_moves": rate_changes(fed, f"{Y0}-01-01", same[0]),
                          "b_moves": rate_changes(fed, f"{Y1}-01-01", session),
                          "after_a": rate_changes(fed, same[0], f"{Y0 + 1}-12-31")}
    for k, s in (("spx", spx), ("ixic", ixic)):
        out["ret"][k] = {str(y): year_ret(s, y) for y in (Y0, Y0 + 1)}
    out["midterms"], out["base"] = midterm_stats(spx, session)
    # 진행 중인 중간선거(선거일이 지났고 12개월이 안 찬 것) — 선거일 종가 → 지금. 확정 통계(평균·오른 횟수)에는 넣지 않는다.
    ed = midterm_day(Y1).isoformat()
    p0 = at_or_before(spx, ed)
    if p0 and p0[0] == ed and session > ed:
        out["midterm_live"] = {"y": Y1, "from": ed, "pct": round((spx[-1][1] / p0[1] - 1) * 100, 1),
                               "days": sum(1 for d, _c in spx if ed < d <= session)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="KST 날짜(YYYY-MM-DD). 직전 미국장 종가를 쓴다")
    args = ap.parse_args()
    kst = date.fromisoformat(args.date) if args.date else date.today()
    sess = prev_us_session(kst)
    if sess is None:
        return 1
    session = sess.isoformat()
    if session > LAST_DAY:
        print(f"[midterm] {LAST_DAY} 이후 — 비교를 멈춘다")
        return 0
    data = build(fetch_daily("^GSPC"), nq.fetch_daily("^IXIC"), nq.fetch_daily("^TNX"), fred_upper(), session)
    if not data:
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[midterm] {session} · {Y1} {data['b'][-1][1]:+.2f}% · {Y0} 같은 날 "
          f"{data['same']['pct'] if data['same'] else '-'}% · 상관 {data['corr']} · 중간선거 {len(data['midterms'])}번")
    return 0


if __name__ == "__main__":
    sys.exit(main())
