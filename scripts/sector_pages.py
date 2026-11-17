# 섹터 정적 페이지(/stocks/sector/{key}/) 8종 작성기

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from scripts.verify_publish_gate import gate_write
except ImportError:
    from verify_publish_gate import gate_write
from html_common import CONFIG_DIR, CSS_PATH, GATE_BLOCKED, JS_PATH, SITE_BASE, WEB_DIR, _breadcrumb, _jsonld, load_json, make_env


def _fmt_krw(v: float) -> str:
    """정수 원화 천 단위 콤마 포맷."""
    return f"{int(v):,}"


def _fmt_pct(v: float) -> str:
    """부호 포함 등락률 포맷."""
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


def _pct_cls(v: float) -> str:
    if v > 0:
        return "up"
    elif v < 0:
        return "down"
    return "flat"


_SECTOR_EMOJI = {
    "semicon": "🔬", "battery": "🔋", "auto": "🚗", "defense": "🛡️",
    "ship": "🚢", "bio": "🧬", "finance": "🏦", "power": "⚡",
}

# 섹터 페이지 본문 카피는 scripts/config/sector_copy.json에 있다.
# 2026-09-02에 파이썬 리터럴 딕셔너리에서 분리했다 — 소스에 긴 한국어 산문을 박아두면
# 수정할 때마다 코드를 건드려야 하고, 그대로 방치되기 쉽다(§20).
_SECTOR_COPY_PATH = CONFIG_DIR / "sector_copy.json"


def _sector_copy(key: str) -> dict:
    """섹터별 본문 카피. 파일·키가 없으면 빈 dict → 해당 문단이 렌더되지 않는다(§0)."""
    if not _SECTOR_COPY_PATH.exists():
        print(f"[generate_html] ⚠️ {_SECTOR_COPY_PATH.name} 없음 — 섹터 본문 생략", file=sys.stderr)
        return {}
    entry = load_json(_SECTOR_COPY_PATH).get(key)
    return entry if isinstance(entry, dict) else {}


def build_sector_pages():
    """stock_universe.json + stocks-snapshot.json → 섹터별 정적 페이지 8개 생성.

    종목 상세 페이지는 없다(2026-10-26 제거) — 종목 카드는 링크하지 않는다.
    """
    universe_path = CONFIG_DIR / "stock_universe.json"
    snapshot_path = WEB_DIR / "data" / "stocks-snapshot.json"
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snap_stocks = snapshot.get("stocks", {})
    snapshot_date = snapshot.get("generated_at", "")[:10]

    env = make_env()
    tpl = env.get_template("pages/stock_sector.html")

    all_sectors = [
        {"key": k, "label": v["label"], "emoji": _SECTOR_EMOJI.get(k, "")}
        for k, v in universe["sectors"].items()
    ]

    for key, sector in universe["sectors"].items():
        stocks = []
        for s in sector["stocks"]:
            code = s["code"]
            measured = snap_stocks.get(code)
            if not measured:
                continue
            stocks.append({
                "code": code,
                "name": s["name"],
                "close": measured["close"],
                "close_fmt": _fmt_krw(measured["close"]),
                "change_pct": measured["change_pct"],
                "pct_fmt": _fmt_pct(measured["change_pct"]),
                "pct_cls": _pct_cls(measured["change_pct"]),
                "wk52_high": measured["wk52_high"],
                "wk52_low": measured["wk52_low"],
                "wk52_high_fmt": _fmt_krw(measured["wk52_high"]),
                "wk52_low_fmt": _fmt_krw(measured["wk52_low"]),
                "spark20": measured.get("spark20", []),
                "foreign_rate": measured.get("foreign_rate"),
            })

        # 등락률 높은 순 정렬 (None은 맨 뒤) — 섹터에서 지금 뭐가 움직이는지 우선 노출
        stocks.sort(key=lambda s: (s["change_pct"] is None, -(s["change_pct"] or 0)))

        pcts = [s["change_pct"] for s in stocks if s["change_pct"] is not None]
        avg_pct = sum(pcts) / len(pcts) if pcts else 0
        breadth = {
            "up": sum(1 for p in pcts if p > 0),
            "down": sum(1 for p in pcts if p < 0),
            "flat": sum(1 for p in pcts if p == 0),
            "total": len(pcts),
        }

        # description·og:title은 템플릿의 og_desc/og_title 블록이 정본이다(base.html이 재사용).
        # 여기서는 그 블록이 만들지 못하는 canonical·JSON-LD만 넘긴다.
        html = tpl.render(
            sector_label=sector["label"],
            sector_key=key,
            canonical_url=f"{SITE_BASE}/stocks/sector/{key}/",
            seo_jsonld=[_jsonld(_breadcrumb([
                ("홈", "/stocks/"), ("종목", "/stocks/"),
                (sector["label"], f"/stocks/sector/{key}/"),
            ]))],
            sector_emoji=_SECTOR_EMOJI.get(key, ""),
            sector_copy=_sector_copy(key),
            stocks=stocks,
            avg_pct=avg_pct,
            avg_pct_fmt=_fmt_pct(avg_pct),
            avg_cls=_pct_cls(avg_pct),
            breadth=breadth,
            snapshot_date=snapshot_date,
            all_sectors=all_sectors,
            css_path=CSS_PATH,
            js_path=JS_PATH,
        )
        out_file = WEB_DIR / "stocks" / "sector" / key / "index.html"
        url = f"{SITE_BASE}/stocks/sector/{key}/"
        if gate_write(out_file, html, url):
            GATE_BLOCKED.append(url)
            continue
        print(f"섹터 페이지 {key} → {out_file}")
