# 종목 유니버스의 실적 발표 예정일(기업 IR 공시)을 수집해 web/data/earnings-calendar.json 생성
"""
소스: https://m.stock.naver.com/api/stock/{code}/integration 의 irScheduleInfo

왜 네이버 IR인가 (yfinance 기각 사유 — docs/plans/2026-07-21-home-earnings-valuation):
  yfinance get_earnings_dates()는 인덱스가 America/New_York이라 KST로 옮기면 날짜가 밀린다.
  실측에서 삼성전자·SK하이닉스 모두 실제 IR 공시일보다 하루 이르게 나왔다.
  irScheduleDate는 기업 IR 공시 기반의 KST 네이티브 날짜라 변환 오차가 없다.

irScheduleDday(네이버가 주는 D-day)는 저장하지 않는다.
상대 시간 라벨은 저장 시점에만 맞고 이후 계속 틀린다(SERVICE_RULES §20에서 두 번 사고).
화면이 렌더 시점에 직접 계산한다.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
UNIVERSE = ROOT / "scripts" / "config" / "stock_universe.json"
OUT = ROOT / "web" / "data" / "earnings-calendar.json"

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://m.stock.naver.com/",
}
API = "https://m.stock.naver.com/api/stock/{code}/integration"
REQUEST_GAP = 0.12   # 네이버에 부담 주지 않도록 종목 사이 간격
HORIZON_DAYS = 60    # 이보다 먼 일정은 캘린더로 쓸모가 없다


def load_universe(path: Path = UNIVERSE) -> list[dict]:
    """섹터별로 나뉜 유니버스를 (code, name) 평면 목록으로 편다. 중복 코드는 한 번만."""
    data = json.loads(path.read_text(encoding="utf-8"))
    seen, out = set(), []
    for sector in data.get("sectors", {}).values():
        for s in sector.get("stocks", []):
            code = s.get("code")
            if code and code not in seen:
                seen.add(code)
                out.append({"code": code, "name": s.get("name", "")})
    return out


def fetch_ir_schedule(code: str) -> dict | None:
    """종목 하나의 IR 일정을 조회한다. 일정이 없으면 None."""
    req = urllib.request.Request(API.format(code=code), headers=UA)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    ir = data.get("irScheduleInfo") or {}
    date = ir.get("irScheduleDate")
    if not date:
        return None
    return {
        "code": code,
        "name": ir.get("stockName") or data.get("stockName") or "",
        "date": date,
        "title": (ir.get("title") or "").strip(),
    }


def is_upcoming(date_str: str, today: str, horizon: str) -> bool:
    """오늘(KST) 이후이고 지평선 안쪽인 일정만 캘린더에 남긴다.

    지난 일정은 캘린더가 아니고, 너무 먼 일정은 화면에서 노이즈다.
    날짜 형식이 깨진 항목은 통과시키지 않는다.
    """
    if not isinstance(date_str, str) or len(date_str) != 10:
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return False
    return today <= date_str <= horizon


def collect(stocks: list[dict], today: str, horizon: str, sleep: float = REQUEST_GAP) -> list[dict]:
    """유니버스를 돌며 예정 일정만 모아 날짜순으로 돌려준다.

    한 종목이 실패해도 나머지로 캘린더를 만든다 — 일정이 있는 종목이
    소수라 한 건의 네트워크 오류로 전체를 버리는 게 더 손해다.
    """
    events = []
    for s in stocks:
        try:
            ev = fetch_ir_schedule(s["code"])
        except Exception as e:
            print(f"⚠️ {s['name']}({s['code']}) IR 일정 조회 실패: {e}", file=sys.stderr)
            ev = None
        if ev and is_upcoming(ev["date"], today, horizon):
            if not ev["name"]:
                ev["name"] = s["name"]
            events.append(ev)
        if sleep:
            time.sleep(sleep)
    events.sort(key=lambda e: (e["date"], e["name"]))
    return events


def _write_atomic(path: Path, text: str) -> None:
    """같은 디렉터리 임시 파일에 쓴 뒤 교체한다.

    브라우저에 그대로 서빙되는 파일이라 절반만 쓰인 상태가 관측되면 안 된다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    horizon = (now + timedelta(days=HORIZON_DAYS)).strftime("%Y-%m-%d")

    stocks = load_universe()
    print(f"수집 중: {len(stocks)}개 종목 IR 일정 ({today} ~ {horizon})")
    events = collect(stocks, today, horizon)

    _write_atomic(
        OUT,
        json.dumps({"updated_at": today, "events": events}, ensure_ascii=False, indent=2),
    )
    print(f"✅ {OUT} 저장 완료 (예정 {len(events)}건)")
    for e in events[:10]:
        print(f"   {e['date']}  {e['name']}")


if __name__ == "__main__":
    main()
