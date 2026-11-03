# 하이퍼리퀴드 24시간 선물의 전날 15:30 대비 등락을 기록한다 — 코스피 시초가 예측에 넣을지 판단할 자료(예측에는 쓰지 않음)
"""코스피 아침 잡에서 돌고 data/hl_signals.json을 쓴다. call_claude가 briefings.json 예측 행의 `hl`로 옮긴다.
비교는 scripts/hl_shadow_report.py. 20~30거래일 뒤 지금 계산값보다 꾸준히 나을 때만 공식에 넣는다(2026-11-03 결정).
"""
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from session_label import prev_kospi_session  # noqa: E402

KST = timezone(timedelta(hours=9))
OUT = Path(__file__).resolve().parent.parent / "data" / "hl_signals.json"
COINS = ("KR200", "SMSN", "SKHX", "EWY")
STALE_SEC = 3 * 3600      # 마지막 체결봉이 이보다 오래됐으면 '지금 값'으로 치지 않는다


def _candles(coin: str, start_ms: int, end_ms: int) -> list:
    body = json.dumps({"type": "candleSnapshot", "req": {"coin": f"xyz:{coin}", "interval": "15m",
                                                         "startTime": start_ms, "endTime": end_ms}}).encode()
    req = urllib.request.Request("https://api.hyperliquid.xyz/info", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=15))


def move_pct(candles: list, base_ts: float, now_ts: float):
    """base_ts에 끝난 15분봉 대비 가장 최근 봉 등락(%). 어느 쪽 봉이든 없거나 오래됐으면 None."""
    rows = sorted((c["t"] / 1000, float(c["c"])) for c in candles)
    base = [c for t, c in rows if t + 900 <= base_ts and base_ts - (t + 900) < STALE_SEC]
    now = [(t, c) for t, c in rows if t <= now_ts and now_ts - t < STALE_SEC]
    if not base or not now:
        return None
    return round((now[-1][1] / base[-1] - 1) * 100, 3)


def collect(today: date, now_ts: float, fetch=_candles) -> dict:
    prev = prev_kospi_session(today)
    if prev is None:
        return {}
    base_ts = datetime(prev.year, prev.month, prev.day, 15, 30, tzinfo=KST).timestamp()
    moves = {}
    for coin in COINS:
        try:
            v = move_pct(fetch(coin, int((base_ts - 3600) * 1000), int(now_ts * 1000)), base_ts, now_ts)
        except Exception as e:
            print(f"[hl_signals] {coin} 조회 실패: {e}", file=sys.stderr)
            continue
        if v is not None:
            moves[coin] = v
    return moves


def main():
    now = datetime.now(KST)
    moves = collect(now.date(), now.timestamp())
    OUT.write_text(json.dumps({"date": now.strftime("%Y-%m-%d"), "generated_at": now.isoformat(timespec="seconds"),
                               "moves": moves}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[hl_signals] {moves}")


if __name__ == "__main__":
    main()
