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


import re  # noqa: E402
import urllib.parse  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402
from fetch_news_live import _UP_WORDS, _DOWN_WORDS  # noqa: E402
from fetch_news_live import _GN_KR, _clean_title, _parse_rss_datetime, get_gemini_api_key  # noqa: E402


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


_SENT_PROMPT = """종목 "{name}"의 오늘 기사 목록입니다. 주가에 가장 영향이 큰 기사 1건을 골라,
요약 1문장과 감성을 분류하세요. 사실만, 추측·생성 금지.

[기사 목록]
{lst}

[출력 — JSON만, 마크다운 없이]
{{"idx": 0, "summary": "한 문장 요약", "sentiment": "pos|neg|neu"}}
"""


def _fetch_stock_articles(name: str, today: str, max_items: int = 8) -> list[dict]:
    """종목명 Google News RSS에서 오늘 기사 + link(url)까지 수집한다."""
    url = _GN_KR + urllib.parse.quote(f"{name} 주가")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print(f"[movers_why] {name} RSS 실패: {e}")
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        pub_date, pub_time = _parse_rss_datetime(item.findtext("pubDate") or "")
        if not title or pub_date != today:
            continue
        src_el = item.find("source")
        out.append({
            "headline": _clean_title(title),
            "time": pub_time or "09:00",
            "url": (item.findtext("link") or "").strip(),
            "source": (src_el.text or "").strip() if src_el is not None else "",
        })
        if len(out) >= max_items:
            break
    return out


def _infer_sentiment(headline: str) -> str:
    """헤드라인 방향어로 감성 판정 (Gemini 폴백용). 하락어 우선."""
    if _DOWN_WORDS.search(headline):
        return "neg"
    if _UP_WORDS.search(headline):
        return "pos"
    return "neu"


def _fallback_event(a: dict) -> dict:
    """Gemini 실패 시: 당일 기사 헤드라인 그대로 + 정규식 감성. 실데이터만 사용."""
    return {
        "time": a["time"], "headline": a["headline"], "url": a["url"],
        "source": a["source"], "summary": a["headline"],
        "sentiment": _infer_sentiment(a["headline"]),
    }


def _gemini_pick(name: str, articles: list[dict]) -> dict:
    """기사 목록 중 Gemini가 1건 선별·요약·감성. 실패 시 첫 기사 헤드라인 폴백."""
    from google import genai
    from google.genai import types
    lst = "\n".join(f'{i}. "{a["headline"]}" ({a["source"]})' for i, a in enumerate(articles))
    prompt = _SENT_PROMPT.format(name=name, lst=lst)
    try:
        client = genai.Client(api_key=get_gemini_api_key())
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=200),
        )
        raw = (resp.text or "").strip()
        mt = re.search(r"\{[\s\S]*\}", raw)
        parsed = json.loads(mt.group(0)) if mt else {}
    except Exception as e:
        print(f"[movers_why] {name} Gemini 실패 → 헤드라인 폴백: {e}")
        return _fallback_event(articles[0])
    idx = parsed.get("idx")
    if not isinstance(idx, int) or not (0 <= idx < len(articles)):
        return _fallback_event(articles[0])
    a = articles[idx]
    sent = parsed.get("sentiment", "neu")
    if sent not in ("pos", "neg", "neu"):
        sent = "neu"
    summary = (parsed.get("summary") or "").strip() or a["headline"]
    return {
        "time": a["time"], "headline": a["headline"], "url": a["url"],
        "source": a["source"], "summary": summary,
        "sentiment": sent,
    }


def pick_event(name: str, today: str) -> dict | None:
    """종목 기사 중 Gemini가 1건 선별·요약·감성. 기사 0건이면 None."""
    articles = _fetch_stock_articles(name, today)
    if not articles:
        return None
    return _gemini_pick(name, articles)


def pick_events(name: str, today: str, change_pct: float, max_n: int = 2) -> list[dict]:
    """핀용 이벤트를 최대 max_n건 선별. 1순위는 Gemini 요약, 그다음은 남은 기사 헤드라인 폴백.
    tier 'why'(빨강) 우선 정렬. 실데이터만 사용 — 기사가 부족하면 그만큼만(억지로 채우지 않음)."""
    articles = _fetch_stock_articles(name, today)
    if not articles:
        return []
    primary = _gemini_pick(name, articles)
    cand = [primary]
    seen = {primary["headline"]}
    for a in articles:
        if a["headline"] in seen:
            continue
        cand.append(_fallback_event(a))
        seen.add(a["headline"])
    # tier 부여 후 'none' 제거 → 빨강(why) 우선 정렬 → 상위 max_n.
    scored = [(ev, classify_tier(ev, change_pct)) for ev in cand]
    scored = [(ev, t) for ev, t in scored if t != "none"]
    scored.sort(key=lambda x: 0 if x[1] == "why" else 1)
    return [{
        "time": ev["time"], "headline": ev["headline"], "url": ev["url"],
        "source": ev["source"], "why": _why_line(ev, t), "tier": t,
        "sentiment": ev["sentiment"],
    } for ev, t in scored[:max_n]]


def _why_line(event: dict, tier: str) -> str:
    summ = event.get("summary") or event.get("headline")
    if tier == "why":
        return summ
    return f"{summ} (개별 인과 단정 안 함)"


LEADER_CODES = ["005930", "000660", "005380"]  # 주도주(삼성전자·SK하이닉스·현대차)


def build_payload(today: str) -> dict:
    """주도주 3종에 대해 뉴스·게이트 → 산출물 dict. 무버 전체 선별은 유지(데이터 보존)."""
    all_rows = fetch_mover_rows()
    row_by_code = {r["code"]: r for r in all_rows}
    stocks = []
    for code in LEADER_CODES:
        r = row_by_code.get(code)
        if not r:
            continue
        events = pick_events(r["name"], today, r["change_pct"])
        stocks.append({
            "code": r["code"], "name": r["name"],
            "changePct": round(r["change_pct"], 2),
            "surge": round(r.get("surge") or 0, 2),
            "events": events,
        })
    return {"generated_at": datetime.now(KST).isoformat(), "date": today, "stocks": stocks}


def main():
    today = datetime.now(KST).strftime("%Y-%m-%d")
    payload = build_payload(today)
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    dated = WEB_DATA / f"movers-why-{today}.json"
    live = WEB_DATA / "movers-why-live.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    dated.write_text(text, encoding="utf-8")
    live.write_text(text, encoding="utf-8")
    n_pinned = sum(1 for s in payload["stocks"] if s["events"])
    print(f"[movers_why] {len(payload['stocks'])} movers, {n_pinned} with news → {dated.name}")


if __name__ == "__main__":
    main()
