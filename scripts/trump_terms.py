# 트럼프 1기 vs 2기 비교 수집 — 취임 직전 종가를 0%로 두고 S&P 500·자산별·역대 임기를 data/trump_terms.json에 쓴다
"""
/stocks/trump-terms/ 상세 페이지와 종목 홈 '장기 신호' 넷째 줄의 원천(2026-11-21 사용자 결정,
시안 docs/prototypes/2026-11-21-trump-terms-page.html · -home-row.html C3안).
숫자는 전부 야후 일봉 종가다(§0). 기준은 직전 미국장 종가(session_label.prev_us_session)이고,
그 날짜의 S&P 500 일봉이 없으면 파일을 쓰지 않는다(§45). 금리는 넣지 않는다(사용자 결정 2026-11-21).

  python3 scripts/trump_terms.py --date 2026-11-21     # KST 날짜 → 직전 미국장(11/20) 기준
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import midterm_compare as mc  # noqa: E402
from session_label import prev_us_session  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "trump_terms.json"

# 자산별 표 — 미국 증시(us)와 코스피·달러·금·유가(kr) 두 표로 나눈다(사용자 결정 2026-11-21)
ASSETS = (
    ("^GSPC", "S&P 500", "us"), ("^IXIC", "나스닥", "us"), ("^DJI", "다우", "us"),
    ("^RUT", "러셀 2000(소형주)", "us"), ("^SOX", "필라델피아 반도체", "us"),
    ("^KS11", "코스피", "kr"), ("KRW=X", "원/달러 환율", "kr"), ("DX-Y.NYB", "달러 지수", "kr"),
    ("GC=F", "금", "kr"), ("CL=F", "WTI 유가", "kr"),
)

# 역대 대통령 임기 — 1월 20일 시작으로 맞춘다. 중간에 바뀐 임기(케네디·존슨, 닉슨·포드)는 한 칸.
PRESIDENTS = (
    (1953, "아이젠하워"), (1957, "아이젠하워 2"), (1961, "케네디·존슨"), (1965, "존슨"), (1969, "닉슨"),
    (1973, "닉슨·포드"), (1977, "카터"), (1981, "레이건"), (1985, "레이건 2"), (1989, "부시"),
    (1993, "클린턴"), (1997, "클린턴 2"), (2001, "부시 2"), (2005, "부시 2-2"), (2009, "오바마"),
    (2013, "오바마 2"), (2017, "트럼프 1기"), (2021, "바이든"), (2025, "트럼프 2기"),
)


def _before(rows: list, d: str):
    b = [r for r in rows if r[0] < d]
    return b[-1] if b else None


def _upto(rows: list, d: str):
    b = [r for r in rows if r[0] <= d]
    return b[-1] if b else None


def _pct(a, b) -> float:
    return round((a / b - 1) * 100, 1)


def asset_rows(series: dict, same_d: str, session: str) -> list:
    """자산마다 1기 같은 날 · 2기 지금 · 1기 4년 끝(취임 직전 거래일 종가 대비 %). 지금 값이 session이 아니면 그 자산을 뺀다."""
    (s1, e1), (s2, _e) = mc.TERMS
    out = []
    for sym, name, group in ASSETS:
        rows = [r for r in series.get(sym) or [] if r[0] <= session]
        b1, b2, a1, e = _before(rows, s1), _before(rows, s2), _upto(rows, same_d), _upto(rows, e1)
        if not (rows and b1 and b2 and a1 and e) or rows[-1][0] < (date.fromisoformat(session) - timedelta(days=4)).isoformat():
            print(f"[trump] {name} 값 없음 — 뺀다", file=sys.stderr)
            continue
        out.append({"k": name, "sym": sym, "group": group, "t1": _pct(a1[1], b1[1]),
                    "t2": _pct(rows[-1][1], b2[1]), "end1": _pct(e[1], b1[1]), "asof": rows[-1][0]})
    return out


def president_rows(spx: list, days: int, session: str) -> list:
    """역대 임기마다 취임 뒤 같은 날수의 S&P 500(취임 직전 거래일 종가 대비)과 4년 끝 값. 같은 날수에 닿지 않은 임기는 same=None."""
    out = []
    for y, name in PRESIDENTS:
        s, e = f"{y}-01-20", f"{y + 4}-01-19"
        p = mc.term_path(spx, s, min(e, session))
        at = [q for q in p if q[0] <= days]
        out.append({"y": y, "name": name,
                    "same": at[-1][1] if at and at[-1][0] >= days - 5 else None,
                    "end": p[-1][1] if p and e <= session else None})
    return out


def forward_after(spx: list, same_d: str) -> dict:
    """1기 같은 날 종가 기준으로 그 뒤 — 3개월 안 최저, 6개월·1년 뒤, 4년 끝."""
    _, e1 = mc.TERMS[0]
    b = _upto(spx, same_d)
    d0 = date.fromisoformat(same_d)
    win = [r for r in spx if same_d < r[0] <= (d0 + timedelta(days=92)).isoformat()]
    lo = min(win, key=lambda r: r[1]) if win else None
    at = lambda n: _upto(spx, (d0 + timedelta(days=n)).isoformat())
    m6, m12, end = at(182), at(365), _upto(spx, e1)
    return {"low3m": {"date": lo[0], "pct": _pct(lo[1], b[1])} if lo else None,
            "m6": {"date": m6[0], "pct": _pct(m6[1], b[1])}, "m12": {"date": m12[0], "pct": _pct(m12[1], b[1])},
            "end": {"date": end[0], "pct": _pct(end[1], b[1])}}


def build(series: dict, session: str) -> dict | None:
    spx = [r for r in series.get("^GSPC") or [] if r[0] <= session]
    if not spx or spx[-1][0] != session:
        print(f"[trump] S&P 500 {session} 종가 없음(마지막 {spx[-1][0] if spx else '-'}) — 쓰지 않는다", file=sys.stderr)
        return None
    terms = mc.build_terms(spx, session)
    if not terms or not terms.get("same"):
        return None
    return {"asof": session, **terms,
            "assets": asset_rows(series, terms["same"]["date"], session),
            "pres": president_rows(spx, terms["t2"][-1][0], session),
            "fwd": forward_after(spx, terms["same"]["date"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="KST 날짜(YYYY-MM-DD). 직전 미국장 종가를 쓴다")
    args = ap.parse_args()
    sess = prev_us_session(date.fromisoformat(args.date) if args.date else date.today())
    if sess is None:
        return 1
    session = sess.isoformat()
    series = {}
    for sym, _name, _g in ASSETS:
        try:
            series[sym] = [(d, c) for d, _h, _l, c in mc.fetch_daily(sym)]
        except Exception as e:
            print(f"[trump] {sym} 받기 실패({e})", file=sys.stderr)
    data = build(series, session)
    if not data:
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[trump] {session} · 취임 뒤 {data['t2'][-1][0]}일 2기 {data['t2'][-1][1]:+.2f}% · "
          f"1기 같은 날 {data['same']['pct']:+.2f}% · 자산 {len(data['assets'])}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
