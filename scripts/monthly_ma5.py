# 월봉 5개월선 3개월 안착 종목 스크리닝 — 코스피 아침 브리핑 '월봉 5개월선 안착 종목' 코너(결정론, LLM 없음)
"""
조건(사용자 결정 2026-10-25, docs/plans/2026-10-25-monthly-ma5-corner/plan.md):
  ① 완성된 월봉 기준 월말 종가가 5개월 이동평균선 위에서 3개월 이상 연속 마감
  ② 진행 중인 이번 달 종가도 5개월선 위 — 이미 깨진 종목은 뺀다
     (완성 월봉만 보면 10월에 5개월선을 깬 금융주 5종목이 '안착'으로 나왔다)
대상은 종목 시그널 허브 46종목. 9/14 이후 월말 종가는 공식 종가 저장소로 교정해야 하는데(§48)
그 저장소가 이 46종목만 쌓기 때문이다.

외국인 보유율 3개월 변화는 **정보로만** 싣는다. 2011~2025 백테스트에서 이 값은 결과를 가르지 못했다.
같은 백테스트에서 조건 충족 뒤 12개월 상승 비율은 기준선과 차이가 없었다 — 화면 문구는 '조건 충족'까지만 쓴다.

출력: data/monthly_ma5.json(gitignore — generate_html이 analysis에 주입해 스냅샷에 흡수된다, §45와 같은 구조)
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kr_official_closes as kr  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "scripts" / "config" / "stock_universe.json"
OUT_PATH = ROOT / "data" / "monthly_ma5.json"

MA_MONTHS = 5        # 이동평균 개월 수
MIN_STREAK = 3       # 안착으로 보는 최소 연속 개월
STRIP_MONTHS = 12    # 화면 스트립에 그릴 완성 월 수
FETCH_DAYS = 640     # 12개월 스트립 + 5개월선 계산에 필요한 약 17개월 + 여유


def month_end_series(rows):
    """일봉 행(오래된→최신) → 달마다 마지막 거래일 행 [{m, date, close, fr}]. 종가 없는 행은 건너뛴다."""
    by_m = {}
    for r in rows or []:
        d = str(r.get("localDate") or "")
        c = r.get("closePrice")
        if len(d) != 8 or not c:
            continue
        by_m[d[:6]] = {"m": d[:6], "date": d, "close": float(c), "fr": r.get("foreignRetentionRate")}
    return [by_m[k] for k in sorted(by_m)]


def annotate(ms):
    """완성 월 리스트에 5개월선(ma5)·선 위 여부(above)·연속 개수(streak)를 붙인다."""
    for i, x in enumerate(ms):
        x["ma5"] = mean(m["close"] for m in ms[i - MA_MONTHS + 1:i + 1]) if i >= MA_MONTHS - 1 else None
        x["above"] = x["ma5"] is not None and x["close"] > x["ma5"]
        x["streak"] = (ms[i - 1]["streak"] + 1 if i else 1) if x["above"] else 0
    return ms


def _month_label(m):
    return f"{int(m[4:])}월"


def _last_trading_day(yyyymm):
    """그 달의 마지막 코스피 거래일(YYYYMMDD)."""
    from holiday_check import check_kospi_open
    y, mo = int(yyyymm[:4]), int(yyyymm[4:])
    d = (date(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1))
    for _ in range(15):
        if check_kospi_open(d):
            break
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def screen_one(rows, today, last_trading_day=_last_trading_day):
    """한 종목 판정. 판단할 수 없으면 None(사유는 stderr).

    today(date): 브리핑 기준일. 그 날이 속한 달보다 앞선 달이 '완성 월'이다.
    """
    ms = month_end_series(rows)
    cur_m = today.strftime("%Y%m")
    done = annotate([m for m in ms if m["m"] < cur_m])
    cur = next((m for m in ms if m["m"] == cur_m), None)
    if len(done) < MA_MONTHS or done[-1]["ma5"] is None:
        return None
    # 애프터장 이후(9/14~) 봉은 공식 종가가 없으면 빠진다. 월말 봉이 빠지면 그 달의 '월말 종가'가
    # 조용히 다른 날 종가로 바뀌므로, 화면에 쓰는 달의 월말 날짜를 실제 마지막 거래일과 대조한다.
    # 남은 행의 날짜가 아니라 '달'로 대조한다 — 9/30 봉이 빠지면 9월의 마지막 행이 9/10이 되어
    # 날짜 기준 검사(9/14 이후만)를 그대로 빠져나간다(테스트로 확인).
    for m in done[-STRIP_MONTHS:]:
        if m["m"] >= kr.AFTERMARKET_START[:6] and m["date"] != last_trading_day(m["m"]):
            print(f"[monthly_ma5] {m['m']} 월말 봉 누락({m['date']}) — 판단하지 않는다", file=sys.stderr)
            return None

    last = done[-1]
    cur_ma5 = mean([m["close"] for m in done[-(MA_MONTHS - 1):]] + [cur["close"]]) if cur else None
    cur_above = None if cur is None else cur["close"] > cur_ma5
    passed = last["streak"] >= MIN_STREAK and cur_above is not False

    fr_chg = None
    base = done[-1 - MIN_STREAK] if len(done) > MIN_STREAK else None
    if base and last["fr"] is not None and base["fr"] is not None:
        fr_chg = round(last["fr"] - base["fr"], 2)

    strip = []
    shown = done[-STRIP_MONTHS:]
    run_from = len(shown) - last["streak"]
    for i, m in enumerate(shown):
        strip.append({"m": m["m"], "label": _month_label(m["m"]), "close": m["close"], "ma5": round(m["ma5"], 2) if m["ma5"] else None,
                      "gap_pct": round((m["close"] / m["ma5"] - 1) * 100, 2) if m["ma5"] else None,
                      "run": i >= run_from, "cur": False})
    if cur:
        strip.append({"m": cur["m"], "label": "이번 달", "close": cur["close"], "ma5": round(cur_ma5, 2),
                      "gap_pct": round((cur["close"] / cur_ma5 - 1) * 100, 2), "run": False, "cur": True})

    run = shown[run_from:] if last["streak"] else []
    latest = cur or last
    return {
        "passed": passed,
        "streak": last["streak"],
        "run_label": (f"{_month_label(run[0]['m'])}~{_month_label(run[-1]['m'])}" if len(run) > 1
                      else (_month_label(run[0]["m"]) if run else "")),
        "last_complete": last["m"],
        "month_end_close": last["close"],
        "month_end_ma5": round(last["ma5"], 2),
        "month_end_gap_pct": round((last["close"] / last["ma5"] - 1) * 100, 2),
        "now_date": latest["date"],
        "now_close": latest["close"],
        "now_gap_pct": strip[-1]["gap_pct"],
        "mtd_pct": round((cur["close"] / last["close"] - 1) * 100, 2) if cur else None,
        "fr_now": last["fr"],
        "fr_chg_3m": fr_chg,
        "strip": strip,
    }


def _pin_date():
    raw = os.environ.get("DS_PIN_SESSION_DATE", "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        print(f"[monthly_ma5] DS_PIN_SESSION_DATE 형식 오류: {raw!r} — 무시", file=sys.stderr)
        return None


def load_universe(path=UNIVERSE_PATH):
    u = json.loads(Path(path).read_text(encoding="utf-8"))
    out, seen = [], set()
    for sec in u.get("sectors", {}).values():
        for s in sec.get("stocks", []):
            if s.get("code") and s["code"] not in seen:
                seen.add(s["code"])
                out.append((s["code"], s.get("name") or s["code"]))
    return out


def run(now=None, fetch_rows=None, universe=None, last_trading_day=_last_trading_day):
    """허브 종목 전체를 판정해 결과 dict를 돌려준다. 조회에 전부 실패하면 None."""
    now = now or datetime.now(KST)
    pin = _pin_date()
    today = pin or now.date()
    fetch_rows = fetch_rows or (lambda code: kr.official_day_rows(code, now=now, days=FETCH_DAYS))
    universe = universe if universe is not None else load_universe()
    items, failed, screened = [], [], 0
    for code, name in universe:
        rows = fetch_rows(code)
        if pin:
            rows = [r for r in rows if str(r.get("localDate") or "") < pin.strftime("%Y%m%d")]
        if not rows:
            failed.append(code)
            continue
        res = screen_one(rows, today, last_trading_day)
        if res is None:
            failed.append(code)
            continue
        screened += 1
        if res["passed"]:
            items.append({"code": code, "name": name, **res})
    if universe and not screened:
        return None
    items.sort(key=lambda x: (-x["streak"], -x["now_gap_pct"]))
    return {
        "date": today.isoformat(),
        "generated_at": now.isoformat(),
        "universe": len(universe),
        "screened": screened,
        "failed": failed,
        "items": items,
    }


def main():
    result = run()
    if result is None:
        print("[monthly_ma5] 46종목 전부 판정 실패 — 파일을 쓰지 않는다(섹션 생략)", file=sys.stderr)
        sys.exit(1)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    names = ", ".join(f"{x['name']}({x['streak']}개월)" for x in result["items"]) or "없음"
    print(f"[monthly_ma5] {result['date']} 판정 {result['screened']}/{result['universe']} · 조건 충족: {names}")
    if result["failed"]:
        print(f"[monthly_ma5] 판정 못 한 종목 {len(result['failed'])}개: {result['failed']}", file=sys.stderr)


if __name__ == "__main__":
    main()
