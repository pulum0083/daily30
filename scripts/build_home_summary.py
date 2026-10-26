# 종목 시그널 첫 화면용 정적 요약 — 최근 코스피 시가·종가와 시초가 예측 채점(오늘 포함)을 web/data/home-summary.json으로 쓴다
"""
쓰는 곳(web/assets/home-hero.js):
  · 마감 카드의 '📝 아침 시초가 예측 → 시초가 x% ✓' — 오늘 채점은 정확도 잡(다음 거래일 09:10)보다 먼저 필요하다
  · 주말 카드의 이번 주 코스피 등락·일별 등락·이번 주 예측 성적
공개 JSON에 없는 값이라 마감 잡이 만든다. **이 파일의 주인은 kospi-close 잡 하나다(§18).**

채점 규칙은 check_accuracy와 같다 — 시가 ÷ 직전 종가(지수 일봉, §57), 같은 classify_direction_correct.
지수 일봉을 못 받으면 파일을 쓰지 않는다(직전 파일이 남아 있어도 화면이 날짜로 걸러 낸다).
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_accuracy import classify_direction_correct  # noqa: E402
from prediction_basis import is_open_basis  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "data" / "home-summary.json"
BRIEFINGS = ROOT / "data" / "briefings.json"
DAYS = 10            # 최근 거래일 수(주간 등락 계산에 직전 주 마지막 종가까지 필요)


def fetch_kospi_days(today: str) -> list:
    """네이버 지수 일봉 → [{date, open, close}] 오래된→최신. 실패하면 []."""
    t = datetime.strptime(today, "%Y-%m-%d")
    start = (t - timedelta(days=30)).strftime("%Y%m%d")
    url = ("https://api.stock.naver.com/chart/domestic/index/KOSPI/day"
           f"?startDateTime={start}0000&endDateTime={t.strftime('%Y%m%d')}2359")
    try:
        rows = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                                 timeout=15).read())
    except Exception as e:
        print(f"[home_summary] 지수 일봉 조회 실패: {e}", file=sys.stderr)
        return []
    out = []
    for r in sorted(rows, key=lambda r: r["localDate"]):
        try:
            d = r["localDate"]
            out.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "open": float(r["openPrice"]), "close": float(r["closePrice"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def build(today: str, days: list, records: list) -> dict | None:
    """순수 함수 — 일봉과 예측 기록으로 요약을 만든다. 일봉이 2개 미만이면 None."""
    days = [d for d in days if d["date"] <= today]
    if len(days) < 2:
        return None
    rows = []
    for i in range(1, len(days)):
        p, d = days[i - 1], days[i]
        rows.append({"date": d["date"], "close": round(d["close"], 2),
                     "pct": round((d["close"] / p["close"] - 1) * 100, 2),
                     "open_pct": round((d["open"] / p["close"] - 1) * 100, 2)})
    rows = rows[-DAYS:]
    gap = {r["date"]: r["open_pct"] for r in rows}
    scores = []
    for b in records:
        if b.get("type") != "kospi" or not is_open_basis(b) or b.get("date") not in gap:
            continue
        g = gap[b["date"]]
        pred = b.get("predicted_direction", "")
        scores.append({"date": b["date"], "direction": pred, "open_pct": g,
                       "ok": bool(classify_direction_correct(pred, g))})
    return {"date": today, "kospi_days": rows, "scores": sorted(scores, key=lambda s: s["date"])}


def main():
    today = datetime.now(KST).strftime("%Y-%m-%d")
    days = fetch_kospi_days(today)
    try:
        records = json.loads(BRIEFINGS.read_text(encoding="utf-8")).get("briefings", [])
    except (OSError, ValueError):
        records = []
    out = build(today, days, records)
    if out is None:
        print("[home_summary] 지수 일봉 부족 — 파일을 쓰지 않는다", file=sys.stderr)
        sys.exit(1)
    out["generated_at"] = datetime.now(KST).isoformat(timespec="seconds")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    last = out["scores"][-1] if out["scores"] else None
    print(f"[home_summary] {today} · 거래일 {len(out['kospi_days'])}개 · 채점 {len(out['scores'])}건"
          + (f" · 최근 {last['date']} {last['direction']} → 시초가 {last['open_pct']:+.2f}% {'✓' if last['ok'] else '✗'}" if last else ""))


if __name__ == "__main__":
    main()
