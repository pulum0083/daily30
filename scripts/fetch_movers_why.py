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


_HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}


def _num(s) -> float:
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def parse_naver_realtime(data: dict, vol_avg20: float) -> dict | None:
    """네이버 polling 응답 → {code,name,change_pct,volume,surge}. 데이터 없으면 None."""
    datas = data.get("datas") or []
    if not datas:
        return None
    d = datas[0]
    vol = _num(d.get("accumulatedTradingVolume"))
    return {
        "code": d.get("itemCode", ""),
        "name": d.get("stockName", ""),
        "change_pct": _num(d.get("fluctuationsRatio")),
        "volume": vol,
        "surge": (vol / vol_avg20) if vol_avg20 else 0.0,
    }


def _load_universe() -> list[dict]:
    """stocks.json(41종목)에서 code·name 유니버스를 읽는다."""
    return json.loads((CONFIG_DIR / "stocks.json").read_text(encoding="utf-8"))


def _load_vol_avg20() -> dict:
    """스냅샷에서 종목별 vol_avg20을 읽는다(급증배수 계산용). 없으면 빈 dict."""
    if not SNAPSHOT_PATH.exists():
        return {}
    snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return {c: (v.get("vol_avg20") or 0) for c, v in (snap.get("stocks") or {}).items()}


def fetch_mover_rows() -> list[dict]:
    """유니버스 41종목의 네이버 실시간을 받아 무버 행 리스트를 만든다(네트워크)."""
    avg = _load_vol_avg20()
    rows = []
    for s in _load_universe():
        code = s["code"]
        url = f"https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
        try:
            req = urllib.request.Request(url, headers=_HDR)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            row = parse_naver_realtime(data, avg.get(code, 0))
            if row:
                rows.append(row)
        except Exception as e:
            print(f"[movers_why] {code} 실시간 실패: {e}")
    return rows


from fetch_news_live import _UP_WORDS, _DOWN_WORDS  # noqa: E402


def classify_tier(event: dict | None, change_pct: float) -> str:
    """방향 일치 게이트. event 없으면 none, 감성·헤드라인↔등락 일치면 why, 불일치면 related."""
    if not event:
        return "none"
    head = event.get("headline", "") or ""
    sent = event.get("sentiment", "neu")
    up = change_pct >= CHANGE_THRESHOLD
    down = change_pct <= -CHANGE_THRESHOLD
    if down and _UP_WORDS.search(head):
        return "related"
    if up and _DOWN_WORDS.search(head):
        return "related"
    if (sent == "pos" and up) or (sent == "neg" and down):
        return "why"
    return "related"
