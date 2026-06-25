# "왜 움직였나" 엔진 — 무버 선별 + RSS·Gemini·방향게이트 → movers-why-{date}.json
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).parent.parent
WEB_DATA = REPO_ROOT / "web" / "data"
CONFIG_DIR = REPO_ROOT / "scripts" / "config"
SNAPSHOT_PATH = WEB_DATA / "stocks-snapshot.json"

MAX_MOVERS = 10
CHANGE_THRESHOLD = 2.0   # |등락률| %
SURGE_THRESHOLD = 1.5    # 거래량 / vol_avg20

# fetch_news_live 재사용 (수정 금지)
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def select_movers(rows: list[dict], max_n: int = MAX_MOVERS) -> list[dict]:
    """등락·거래량 무버 선별. |change|>=2 또는 surge>=1.5 충족분만, 절대등락 큰 순 max_n개."""
    cand = [r for r in rows
            if abs(r.get("change_pct") or 0) >= CHANGE_THRESHOLD
            or (r.get("surge") or 0) >= SURGE_THRESHOLD]
    cand.sort(key=lambda r: abs(r.get("change_pct") or 0), reverse=True)
    return cand[:max_n]
