# 국면 데이터 빌더 — Yahoo 일봉을 받아 market_regime_core로 계산하고 JSON을 굽는다.
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pytz

sys.path.insert(0, str(Path(__file__).parent))
from market_regime_core import WINDOW_DAYS  # noqa: E402

KST = pytz.timezone("Asia/Seoul")
CONFIG_PATH = Path(__file__).parent / "config" / "regime_baskets.json"
OUT_PATH = Path(__file__).parent.parent / "web" / "data" / "market-regime.json"
UA = {"User-Agent": "Mozilla/5.0"}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def fetch_daily_closes(ticker: str, rng: str = "2y") -> dict:
    """{'YYYY-MM-DD': close}. 실패 시 빈 dict — 호출부가 바스켓에서 제외한다."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={rng}&interval=1d")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read())
        r = data["chart"]["result"][0]
        ts = r["timestamp"]
        closes = r["indicators"]["quote"][0]["close"]
        return {datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"): c
                for t, c in zip(ts, closes) if c is not None}
    except Exception as e:
        print(f"[regime] {ticker} 수집 실패: {e}", file=sys.stderr)
        return {}


def fetch_all(cfg: dict, rng: str = "2y") -> dict:
    out = {}
    for b in cfg["baskets"]:
        for t in b["members"]:
            if t not in out:
                out[t] = fetch_daily_closes(t, rng)
    return out


def build(closes: dict, cfg: dict) -> dict:
    """오늘 시점 국면 산출물. 창은 마지막 WINDOW_DAYS 영업일."""
    from market_regime_core import basket_cum, daily_frames, resolve_regimes

    names = {b["key"]: b["name"] for b in cfg["baskets"]}
    order = [b["key"] for b in cfg["baskets"]]
    allowed = {b["key"] for b in cfg["baskets"] if b["scope"] == "global"}

    cal = sorted(closes["MSFT"])            # 기준 캘린더 = 미국 거래일 (모든 바스켓에서 MSFT를 빼면 KeyError)
    if len(cal) < WINDOW_DAYS + 1:
        raise RuntimeError(f"캘린더 부족: {len(cal)}일 < {WINDOW_DAYS + 1}일")

    # 국면 이력을 위해 최근 120일치도 같이 계산한다(regime_since 산출용)
    hist_n = min(120, len(cal) - WINDOW_DAYS)
    frames, spark_by_key, meta = [], {}, {}
    for i in range(len(cal) - hist_n, len(cal)):
        win = cal[i - WINDOW_DAYS:i + 1]
        cums = {}
        for b in cfg["baskets"]:
            cum, n = basket_cum(b["members"], closes, win)
            if cum:
                cums[b["key"]] = cum
                if i == len(cal) - 1:
                    spark_by_key[b["key"]] = [round(v, 1) for v in list(reversed(cum[::-5]))]
                    meta[b["key"]] = n
        frames.append(daily_frames(cums)[-1])

    res = resolve_regimes(frames, names, order, allowed)
    last, last_frame = res[-1], frames[-1]

    since = cal[len(cal) - hist_n]  # 폴백: 국면이 가용 이력 전체를 덮은 경우
    for i in range(len(res) - 1, 0, -1):
        if res[i]["regime_index"] != res[i - 1]["regime_index"]:
            since = cal[len(cal) - hist_n + i]
            break

    baskets = []
    for b in cfg["baskets"]:
        k = b["key"]
        if k not in last_frame:
            continue
        f = last_frame[k]
        baskets.append({"key": k, "name": b["name"], "scope": b["scope"],
                        "cum": f["cum"], "peak": f["peak"], "gap": f["gap"],
                        "is_high": f["is_high"], "spark": spark_by_key.get(k, []),
                        "members": b["members"], "n_used": meta.get(k, 0)})

    kr = {b["key"]: last_frame[b["key"]]["cum"]
          for b in cfg["baskets"] if b["scope"] == "korea" and b["key"] in last_frame}
    korea = None
    if "kr_semi" in kr and "kr_rest" in kr:
        korea = {"semi": kr["kr_semi"], "rest": kr["kr_rest"],
                 "gap": round(kr["kr_semi"] - kr["kr_rest"], 1)}

    out = {"generated_at": datetime.now(KST).isoformat(),
           "session_date": cal[-1],
           "window_days": WINDOW_DAYS,
           "state": last["state"], "headline": last["headline"],
           # 헤드라인을 만든 바로 그 히스테리시스 재료(§28 계열 사고 방지) — 프런트가
           # 카드를 고를 때 raw 단일일자 수치로 재도출하지 않고 이 키를 그대로 쓴다.
           "cooled_keys": last.get("cooled_keys", []),
           "rising_keys": last.get("rising_keys", []),
           "regime_since": since, "baskets": baskets}
    if korea:
        out["korea"] = korea
    return out


def main():
    cfg = load_config()
    closes = fetch_all(cfg)
    usable = {t: v for t, v in closes.items() if v}
    print(f"[regime] 수집 {len(usable)}/{len(closes)} 티커", file=sys.stderr)
    result = build(closes, cfg)
    if not result["headline"]:
        raise RuntimeError("헤드라인 생성 실패 — 판정과 재료가 어긋났다")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[regime] {result['state']} · \"{result['headline']}\" → {OUT_PATH}")


if __name__ == "__main__":
    main()
