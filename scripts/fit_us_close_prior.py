# S&P 선물 등락 구간별 S&P500 상승 마감 비율을 재서 scripts/config/us_close_prior.json을 만든다(미국 브리핑 확률의 출처)
"""21:15 KST 시점 ES 선물 등락(직전 일봉 종가 대비)을 구간으로 나눠, 그날 S&P500이 전일보다 높게 끝난 비율을 잰다.
야후 1시간봉 조회 한계(730일) 안에서만 계산한다. 다시 맞출 때: python3 scripts/fit_us_close_prior.py
"""
import bisect
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

KST = timezone(timedelta(hours=9))
ET = ZoneInfo("America/New_York")
OUT = Path(__file__).resolve().parent / "config" / "us_close_prior.json"
EDGES = [-0.5, -0.2, 0.0, 0.2, 0.5]
SPLIT = "2025-12-01"     # 앞뒤 구간이 비슷한지 보려고 나눠서도 기록한다


def _chart(symbol, rng, interval):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{symbol.replace('^', '%5E').replace('=', '%3D')}?range={rng}&interval={interval}&includePrePost=true")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    r = json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]
    return [(t, c) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]


def build_rows(es_hourly, es_daily, sp_daily) -> list:
    """(ES 등락 %, S&P 전일 대비 %) 행. es_hourly는 (ts, close), 일봉 둘은 (date, close) 오름차순."""
    ts = [t for t, _ in es_hourly]
    es_days = [d for d, _ in es_daily]
    rows = []
    for (prev_d, prev_c), (d, c) in zip(sp_daily, sp_daily[1:]):
        pub = datetime(d.year, d.month, d.day, 21, 15, tzinfo=KST).timestamp()
        i = bisect.bisect_right(ts, pub - 3600) - 1           # 21:15 전에 끝난 마지막 1시간봉
        j = bisect.bisect_left(es_days, d) - 1                # d 이전 마지막 ES 일봉 — 라이브의 전일 종가와 같다
        if i < 0 or j < 0 or pub - ts[i] > 3 * 3600:
            continue
        rows.append({"d": str(d), "es": (es_hourly[i][1] / es_daily[j][1] - 1) * 100, "sp": (c / prev_c - 1) * 100})
    return rows


def bands(rows: list) -> list:
    lows = [None] + EDGES
    highs = EDGES + [None]
    out = []
    for lo, hi in zip(lows, highs):
        z = [r for r in rows if (lo is None or r["es"] >= lo) and (hi is None or r["es"] < hi)]
        up = sum(1 for r in z if r["sp"] > 0)
        out.append({"lo": lo, "hi": hi, "days": len(z), "up_pct": round(up / len(z) * 100) if z else None})
    return out


def main():
    def by_date(rows):
        return [(datetime.fromtimestamp(t, ET).date(), c) for t, c in rows]
    es_h = _chart("ES=F", "730d", "1h")
    es_d = by_date(_chart("ES=F", "3y", "1d"))
    sp_d = by_date(_chart("^GSPC", "3y", "1d"))
    rows = build_rows(es_h, es_d, sp_d)
    first = rows[0]["d"]
    hit = sum(1 for r in rows if (r["es"] >= 0) == (r["sp"] > 0))
    out = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "symbol": "ES=F → ^GSPC",
        "method": "21:15 KST 직전 ES 1시간봉 ÷ 직전 ES 일봉 종가 − 1을 구간으로 나눠 그날 S&P500 상승 마감 비율을 잰다.",
        "data_from": first, "data_through": rows[-1]["d"], "days": len(rows),
        "direction_hit_pct": round(hit / len(rows) * 100, 1),
        "bands": bands(rows),
        "bands_early": bands([r for r in rows if r["d"] < SPLIT]),
        "bands_late": bands([r for r in rows if r["d"] >= SPLIT]),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
