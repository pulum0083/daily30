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
