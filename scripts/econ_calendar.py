# 경제 캘린더 수집 — 이벤트를 발표 시각(KST)으로 끝남·예정으로 나눈다

from __future__ import annotations
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from market_common import KST


def _bucket_calendar_events(events: list, kst_now: datetime) -> dict:
    """고영향 이벤트를 추려 **발행 시각 기준 시제**(status)를 붙여 분류한다.

    날짜만 비교하면 그날 새벽에 이미 끝난 이벤트(예: 03:00 KST FOMC)가
    21:15 KST 미국 브리핑에서도 "오늘 예정"으로 남는다 — 2026-07-30 실사고.
    소스(ff_calendar_thisweek.json)는 `actual`을 **절대 채우지 않으므로**
    "actual이 비었으면 미발표"라는 판정은 쓸 수 없다. 시각 비교가 유일한 근거다.

    status: "released"(이미 발표됨) | "upcoming"(아직 안 나옴)
    """
    KEY_COUNTRIES = {"USD", "CNY", "KRW", "JPY", "EUR"}
    today_kst = kst_now.strftime("%Y-%m-%d")

    today_events, upcoming_events = [], []
    for ev in events:
        if ev.get("impact") != "High" or ev.get("country") not in KEY_COUNTRIES:
            continue
        try:
            dt_kst = datetime.fromisoformat(ev.get("date", "")).astimezone(KST)
        except Exception:
            continue  # 시제를 판정할 수 없는 이벤트는 버린다

        item = {
            "title":    ev.get("title", ""),
            "country":  ev.get("country", ""),
            "impact":   ev.get("impact", ""),
            "date_kst": dt_kst.strftime("%Y-%m-%d %H:%M KST"),
            "date_kst_date": dt_kst.strftime("%Y-%m-%d"),
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
            "actual":   ev.get("actual", ""),
            "status":   "released" if dt_kst <= kst_now else "upcoming",
        }

        if item["date_kst_date"] == today_kst:
            today_events.append(item)
        elif item["date_kst_date"] > today_kst:
            upcoming_events.append(item)

    return {"today": today_events, "upcoming": upcoming_events[:10]}


def fetch_economic_calendar() -> dict:
    """ForexFactory 주간 경제 캘린더에서 고영향 이벤트를 가져온다 (무료, API 키 불필요).

    Returns:
        {
          "today": [...],    # 오늘 KST 기준 고영향 이벤트 (각 항목에 status)
          "upcoming": [...], # 향후 5일 고영향 이벤트 (최대 10개)
        }
    """
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 DailyB/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read().decode("utf-8"))

        out = _bucket_calendar_events(events, datetime.now(KST))
        released = sum(1 for e in out["today"] if e["status"] == "released")
        print(f"[fetch_data] Economic calendar: today={len(out['today'])} "
              f"(released={released}), upcoming={len(out['upcoming'])}")
        return out

    except Exception as e:
        print(f"[fetch_data] Economic calendar error: {e}", file=sys.stderr)
        return {"today": [], "upcoming": []}
