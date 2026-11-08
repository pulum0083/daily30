# 주간 장기 리포트 — 한 주의 지수 등락과 장기 지표(코스피 체크·나스닥 체크·S&P 500 200일선·월봉 5개월선)를 모아 /weekly/{금요일}/을 쓴다
"""
토요일 아침(미국 금요일 장 마감 뒤) 한 번 만들고 고치지 않는다. 모은 값은 web/weekly/{금요일}/data.json에 함께 남기고,
다시 그릴 땐 그 파일만 읽는다(브리핑 analysis_snapshot과 같은 원칙, §2) — 나중에 다시 돌려도 그 주의 숫자가 바뀌지 않는다.

깨끗한 체크아웃에서 돈다(.github/workflows/weekly-report.yml) — gitignore된 data/*.json에 기대지 않는다.
  · 코스피 종가: 네이버 지수 일봉(build_home_summary.fetch_kospi_days)
  · 미국 지수·나스닥 체크·코스피 체크: 야후 일봉(nasdaq_overheat.fetch_daily)
  · S&P 500 200일선 비율: sp500_ma200.py를 이 자리에서 돌려 금요일 세션까지 누적 기록에 넣는다
  · 월봉 5개월선: 그 주 브리핑 스냅샷(커밋됨) · 섹터 주간 등락: home-summary.json(커밋됨, 날짜가 맞을 때만)
문장·헤드라인은 longterm_pages.weekly_context가 정해진 틀로 만든다(LLM 없음, §0).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kospi_check as kc  # noqa: E402
import nasdaq_overheat as nq  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
WEEKLY = ROOT / "web" / "weekly"
BRIEFINGS = ROOT / "web" / "briefings"
US_IDX = (("^GSPC", "S&P500"), ("^IXIC", "나스닥"), ("^DJI", "다우"), ("^SOX", "반도체"))


def week_of(today: date) -> date:
    """today 이전(당일 제외)의 가장 최근 금요일 — 토요일 실행이면 어제."""
    d = today - timedelta(days=1)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


def series_for_week(rows: list, monday: str, end: str) -> list:
    """[(날짜, 종가)] 오래된→최신 → [직전 주 마지막 종가, 이번 주 날짜들...]. 직전 종가가 없으면 []."""
    before = [r for r in rows if r[0] < monday]
    inside = [r for r in rows if monday <= r[0] <= end]
    if not before or not inside:
        return []
    return [list(before[-1])] + [list(r) for r in inside]


def ma200_gap(rows: list, d: str):
    """d까지의 종가로 200일 평균 대비 거리(%). 200일이 안 되면 None."""
    cs = [c for x, c in rows if x <= d]
    if len(cs) < 200:
        return None
    return round((cs[-1] / (sum(cs[-200:]) / 200) - 1) * 100, 2)


def _names(snap: dict, key: str) -> list:
    m = snap.get(key) or {}
    return [i.get("name") for i in (m.get("items") or []) if i.get("name")] + list(m.get("repeat_hidden") or [])


def ma5_lists(kind: str, key: str, monday: str, end: str, session_of) -> dict:
    """그 주 브리핑 스냅샷에서 월봉 5개월선 안착 종목(마지막 날 기준)과 그 주에 빠진 종목.
    한 달에 한 번만 싣는 규칙(§61) 때문에 이미 실린 종목은 repeat_hidden에 이름만 남는다 — 연속 개월은 그달 앞 스냅샷에서 찾는다."""
    snaps = []
    d = date.fromisoformat(monday)
    while d.isoformat() <= end:
        p = BRIEFINGS / d.isoformat() / kind / "analysis_snapshot.json"
        if p.exists():
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(s.get(key), dict):
                    snaps.append((d.isoformat(), s))
            except ValueError:
                pass
        d += timedelta(days=1)
    if not snaps:
        return {}
    month = snaps[-1][0][:7]
    snaps = [x for x in snaps if x[0][:7] == month]
    streak = {}
    for p in sorted(BRIEFINGS.glob(f"{month}-*/{kind}/analysis_snapshot.json")):
        try:
            for i in (json.loads(p.read_text(encoding="utf-8")).get(key) or {}).get("items") or []:
                if i.get("name") and i.get("streak"):
                    streak[i["name"]] = i["streak"]
        except ValueError:
            continue
    last = _names(snaps[-1][1], key)
    dropped = []
    for n in _names(snaps[0][1], key):
        if n in last:
            continue
        gone = next((dd for dd, s in snaps if n not in _names(s, key)), None)
        dropped.append({"name": n, "when": session_of(date.fromisoformat(gone)).isoformat() if gone else ""})
    return {"items": [{"name": n, "streak": streak.get(n)} for n in last], "dropped": dropped}


def collect(end: date) -> dict:
    """네트워크로 그 주 값을 모은다. 코스피 종가를 못 받으면 None."""
    from build_home_summary import fetch_kospi_days, OUT as HOME_SUMMARY
    from session_label import prev_kospi_session, prev_us_session
    monday = (end - timedelta(days=4)).isoformat()
    e = end.isoformat()
    prev_end = (end - timedelta(days=7)).isoformat()

    ks_rows = [(r["date"], r["close"]) for r in fetch_kospi_days(e)]
    ks = series_for_week(ks_rows, monday, e)
    if not ks:
        print("[weekly] 코스피 종가 없음 — 중단", file=sys.stderr)
        return None
    kr_last, kr_prev = ks[-1][0], ks[0][0]
    idx = {"KS": ks}
    us_daily, ma = {}, {}
    for sym, name in US_IDX:
        daily = nq.fetch_daily(sym)
        rows = [(d, c) for d, _h, _l, c in daily if d <= e]
        us_daily[sym] = daily
        s = series_for_week(rows, monday, e)
        if s:
            idx[sym] = [[d, round(c, 2)] for d, c in s]
            ma[name] = [ma200_gap(rows, s[-1][0]), ma200_gap(rows, s[0][0])]
    us_last = (idx.get("^GSPC") or [[e]])[-1][0]
    us_prev = (idx.get("^GSPC") or [[prev_end]])[0][0]

    ks_daily = nq.fetch_daily(kc.SYMBOL)
    now_c = kc.compute(ks_daily, kr_last, ks[-1][1])
    prev_c = kc.compute(ks_daily, kr_prev, ks[0][1])
    kcd = {"now": now_c and now_c["gap_pct"], "prev": prev_c and prev_c["gap_pct"],
           "year_max": now_c and now_c.get("year_max"), "prev_max": now_c and now_c.get("prev_max")}

    def nqat(d):
        c = nq.compute(nq.monthly([r for r in us_daily["^IXIC"] if r[0] <= d]))
        return {k: c[k] for k in ("gap_pct", "month", "high", "level")} if c else {}
    nqn, nqp = nqat(us_last), nqat(us_prev)
    nqd = {"now": {"gap": nqn.get("gap_pct"), **nqn}, "prev": {"gap": nqp.get("gap_pct"), **nqp}}

    # S&P 500 — 금요일 세션을 누적 기록에 넣는다(토요일 날짜로 돌리면 직전 미국장 = 금요일)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "sp500_ma200.py"), "--date",
                    (end + timedelta(days=1)).isoformat()], check=False)
    spd = {}
    try:
        hist = json.loads((ROOT / "data" / "sp500_breadth_history.json").read_text(encoding="utf-8"))["rows"]
        now_r = [r for r in hist if r[0] <= us_last]
        prev_r = [r for r in hist if r[0] <= us_prev]
        if now_r and now_r[-1][0] == us_last and prev_r:
            pcts = sorted(r[1] for r in now_r)
            n = len(pcts)
            med = pcts[n // 2] if n % 2 else (pcts[n // 2 - 1] + pcts[n // 2]) / 2
            spd = {"now": now_r[-1][:2], "prev": prev_r[-1][:2], "median_all": round(med, 1),
                   "from_label": f"{int(now_r[0][0][:4])}년 {int(now_r[0][0][5:7])}월"}
            cur = json.loads((ROOT / "data" / "sp500_ma200.json").read_text(encoding="utf-8"))
            if cur.get("asof") == us_last and cur.get("sectors"):
                spd["sectors"] = [[k, a / t * 100] for k, (a, t) in cur["sectors"].items()]
    except (OSError, ValueError, KeyError) as ex:
        print(f"[weekly] S&P 500 200일선 기록 없음({ex}) — 그 카드만 빠진다", file=sys.stderr)

    sectors_week = []
    try:
        hs = json.loads(HOME_SUMMARY.read_text(encoding="utf-8"))
        if hs.get("date") == kr_last:
            sectors_week = hs.get("sectors_week") or []
    except (OSError, ValueError):
        pass

    return {
        "end": e, "monday": monday, "prev_end": prev_end, "kr_last": kr_last, "us_last": us_last,
        "idx": idx, "kc": kcd, "nq": nqd, "spx": spd, "ma200": ma,
        "ma5": {"kr": ma5_lists("kospi", "monthly_ma5", monday, e, prev_kospi_session),
                "us": ma5_lists("us", "monthly_ma5_us", monday, e, prev_us_session)},
        "sectors_week": sectors_week,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
    }


def render(end: str) -> bool:
    """web/weekly/{end}/data.json으로 그 주 페이지와 목록 페이지를 쓴다."""
    import generate_html as gh
    import longterm_pages as lp
    d = json.loads((WEEKLY / end / "data.json").read_text(encoding="utf-8"))
    prev = (date.fromisoformat(end) - timedelta(days=7)).isoformat()
    ctx = lp.weekly_context(d, f"/weekly/{prev}/" if (WEEKLY / prev / "index.html").exists() else "")
    if not ctx:
        print("[weekly] 렌더할 값이 없음", file=sys.stderr)
        return False
    url = f"{gh.SITE_BASE}/weekly/{end}/"
    ctx.update({"canonical_url": url, "css_path": gh.CSS_PATH, "js_path": gh.JS_PATH,
                "seo_jsonld": [gh._jsonld(gh._breadcrumb([("홈", "/stocks/"), ("주간 장기 리포트", "/weekly/"),
                                                         (ctx["wk"]["tag"].split(" · ")[0], f"/weekly/{end}/")]))]})
    env = gh.make_env()
    if gh.gate_write(WEEKLY / end / "index.html", env.get_template("pages/weekly_report.html").render(**ctx), url):
        return False
    write_index()
    gh.write_sitemap_xml()
    print(f"[weekly] {end} 주간 장기 리포트 → web/weekly/{end}/index.html")
    return True


def write_index() -> None:
    """/weekly/ 목록 — 디스크에 커밋된 주간 리포트(data.json)에서 만든다. 최신이 위."""
    import generate_html as gh
    import longterm_pages as lp
    items = []
    for p in sorted(WEEKLY.glob("*/data.json"), reverse=True):
        try:
            c = lp.weekly_context(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, KeyError):
            continue
        if c and (p.parent / "index.html").exists():
            items.append({"url": f"/weekly/{p.parent.name}/", "tag": c["wk"]["tag"], "head": c["wk"]["head"], "sub": c["wk"]["sub"]})
    url = f"{gh.SITE_BASE}/weekly/"
    ctx = {"items": items, "canonical_url": url, "css_path": gh.CSS_PATH, "js_path": gh.JS_PATH,
           "seo_jsonld": [gh._jsonld(gh._breadcrumb([("홈", "/stocks/"), ("주간 장기 리포트", "/weekly/")]))]}
    gh.gate_write(WEEKLY / "index.html", gh.make_env().get_template("pages/weekly_index.html").render(**ctx), url)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-end", help="그 주 금요일(YYYY-MM-DD). 없으면 오늘(KST) 이전 가장 최근 금요일")
    ap.add_argument("--force", action="store_true", help="이미 있는 주도 다시 모은다(기본은 건너뜀 — 발행본을 고치지 않는다)")
    ap.add_argument("--render-only", action="store_true", help="모으지 않고 저장된 data.json으로 다시 그린다")
    args = ap.parse_args()
    end = date.fromisoformat(args.week_end) if args.week_end else week_of(datetime.now(KST).date())
    out = WEEKLY / end.isoformat()
    if args.render_only:
        return 0 if render(end.isoformat()) else 1
    if (out / "index.html").exists() and not args.force:
        print(f"[weekly] {end} 리포트가 이미 있어요 — 건너뜀")
        return 0
    d = collect(end)
    if not d:
        return 1
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0 if render(end.isoformat()) else 1


if __name__ == "__main__":
    sys.exit(main())
