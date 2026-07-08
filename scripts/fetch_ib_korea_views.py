#!/usr/bin/env python3
# 외국계 증권사·글로벌 IB의 한국 시장·대형주 코멘트를 Google News RSS로 수집·요약하는 스크립트
"""
Usage:
    python3 scripts/fetch_ib_korea_views.py

출력: data/ib_korea_views.json
  - Google News 한국어 RSS에서 화이트리스트 IB × 코스피/대형주 쿼리로 최근 24시간 기사만 수집
  - 제목/요약에 화이트리스트 IB명이 실제로 박혀 있어야 채택 (귀속 불가하면 버림)
  - IB당 1건, 최대 3건 (동일 IB는 가장 최근 1건)
  - batchexecute로 발행사 원문 URL 리졸브 → 실패 시 Google News 링크 폴백
  - Gemini는 제목+요약 기반 스탠스 요약(해요체)·bull/bear/neu 분류만 수행 (날짜·URL·출처 생성 불가)
  - 대상 없으면 빈 배열 저장 (섹션 생략, 파이프라인 보호)
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
KST = timezone(timedelta(hours=9))

MAX_ITEMS = 3

# 화이트리스트 IB — aliases 중 하나라도 제목/요약에 있으면 채택. 리스트 순서대로 first-match.
HOUSES = [
    {"name": "골드만삭스",   "initials": "GS",   "aliases": ["골드만삭스", "골드만"]},
    {"name": "모건스탠리",   "initials": "MS",   "aliases": ["모건스탠리", "모간스탠리"]},
    {"name": "JP모건",      "initials": "JPM",  "aliases": ["jp모건", "jp모간", "제이피모건", "jp 모건"]},
    {"name": "UBS",         "initials": "UBS",  "aliases": ["ubs"]},
    {"name": "씨티",         "initials": "Citi", "aliases": ["씨티그룹", "씨티"]},
    {"name": "노무라",       "initials": "NOM",  "aliases": ["노무라"]},
    {"name": "맥쿼리",       "initials": "MQ",   "aliases": ["맥쿼리"]},
    {"name": "HSBC",        "initials": "HSBC", "aliases": ["hsbc"]},
    {"name": "CLSA",        "initials": "CLSA", "aliases": ["clsa"]},
    {"name": "번스타인",     "initials": "BST",  "aliases": ["번스타인"]},
    {"name": "BofA",        "initials": "BofA", "aliases": ["뱅크오브아메리카", "bofa", "메릴린치"]},
    {"name": "바클레이스",   "initials": "BARC", "aliases": ["바클레이스", "바클레이즈"]},
]

VALID_SENTIMENTS = {"bull", "bear", "neu"}
_SENT_MAP = {"bullish": "bull", "bearish": "bear", "neutral": "neu"}


def _match_house(text: str) -> dict | None:
    """제목/요약 text에 화이트리스트 IB alias가 있으면 해당 하우스 dict 반환, 없으면 None."""
    low = text.lower()
    for h in HOUSES:
        if any(a in low for a in h["aliases"]):
            return h
    return None


def _within_24h(dt: datetime, now: datetime) -> bool:
    """dt가 now 기준 최근 24시간 이내(과거 방향)이고 미래가 아니면 True."""
    if dt > now:
        return False
    return (now - dt) <= timedelta(hours=24)


def _time_label(dt: datetime, now: datetime) -> str:
    """오늘(KST)이면 '오늘 HH:MM', 어제면 '어제 HH:MM', 그 밖이면 'M/D HH:MM'."""
    d0 = now.astimezone(KST).date()
    d = dt.astimezone(KST).date()
    hm = dt.astimezone(KST).strftime("%H:%M")
    if d == d0:
        return f"오늘 {hm}"
    if (d0 - d).days == 1:
        return f"어제 {hm}"
    return f"{d.month}/{d.day} {hm}"


def _normalize_sentiment(s: str) -> str:
    low = str(s).strip().lower()
    if low in _SENT_MAP:
        return _SENT_MAP[low]
    return low if low in VALID_SENTIMENTS else "neu"


def _dedup_by_house(cands: list[dict], max_items: int = MAX_ITEMS) -> list[dict]:
    """동일 하우스는 published_at 최신 1건만 유지, 최신순 정렬 후 max_items건 반환."""
    seen: dict[str, dict] = {}
    for c in cands:
        name = c["house"]
        if name not in seen or c["published_at"] > seen[name]["published_at"]:
            seen[name] = c
    ordered = sorted(seen.values(), key=lambda c: c["published_at"], reverse=True)
    return ordered[:max_items]


_GN_KR = "https://news.google.com/rss/search?hl=ko&gl=KR&ceid=KR:ko&q="
_HDR = {"User-Agent": "Mozilla/5.0"}

# 화이트리스트 IB × 한국 시장·대형주 조합 쿼리. 커버리지 확보용으로 넉넉히.
_QUERIES = [
    "외국계 증권사 코스피",
    "골드만삭스 삼성전자", "골드만삭스 코스피",
    "모건스탠리 SK하이닉스", "모건스탠리 코스피",
    "JP모건 코스피", "JP모건 한국 증시",
    "UBS 코스피", "노무라 한국 증시", "씨티 코스피",
    "맥쿼리 삼성전자", "HSBC 한국 증시", "CLSA 코스피",
]


def _clean_title(title: str) -> str:
    """Google News RSS 제목 끝 '- 출처명' 제거."""
    title = re.sub(r"\s*-\s*[^-]{1,30}$", "", title.strip())
    return re.sub(r"\s{2,}", " ", title).strip()


def _fetch_rss_candidates(now: datetime) -> list[dict]:
    """쿼리 세트로 RSS를 돌며 24h 이내·IB 귀속 가능한 후보를 수집한다.

    각 후보: {house, initials, title, desc, source, link, published_at(datetime)}
    """
    seen_titles: set[str] = set()
    cands: list[dict] = []
    for q in _QUERIES:
        url = _GN_KR + urllib.parse.quote(q)
        try:
            req = urllib.request.Request(url, headers=_HDR)
            with urllib.request.urlopen(req, timeout=12) as r:
                root = ET.fromstring(r.read())
        except Exception as e:
            print(f"[ib_views] RSS 실패 ({q}): {e}", file=sys.stderr)
            continue
        for item in root.iter("item"):
            title = _clean_title((item.findtext("title") or "").strip())
            desc = re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip()[:200]
            link = (item.findtext("link") or "").strip()
            src_el = item.find("source")
            source = (src_el.text or "").strip() if src_el is not None else ""
            try:
                pub = parsedate_to_datetime((item.findtext("pubDate") or "")).astimezone(KST)
            except Exception:
                continue
            if not title or title in seen_titles:
                continue
            if not _within_24h(pub, now):
                continue
            house = _match_house(title + " " + desc)
            if house is None:
                continue
            seen_titles.add(title)
            cands.append({
                "house": house["name"], "initials": house["initials"],
                "title": title, "desc": desc, "source": source,
                "link": link, "published_at": pub,
            })
    return cands


_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"


def _resolve_gnews_url(link: str) -> str:
    """Google News 기사 링크를 발행사 원문 URL로 리졸브한다. 실패 시 원래 link 반환."""
    if "/rss/articles/" not in link:
        return link
    try:
        art = link.split("/articles/")[1].split("?")[0]
        req = urllib.request.Request(link, headers=_HDR)
        with urllib.request.urlopen(req, timeout=12) as r:
            page = r.read().decode("utf-8", "ignore")
        sig = re.search(r'data-n-a-sg="([^"]+)"', page)
        ts = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sig and ts):
            return link
        inner = (
            '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
            'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
            f'"{art}",{ts.group(1)},"{sig.group(1)}"]'
        )
        payload = [[["Fbv4je", inner, None, "generic"]]]
        body = "f.req=" + urllib.parse.quote(json.dumps(payload))
        req2 = urllib.request.Request(
            _BATCH_URL, data=body.encode(),
            headers={**_HDR, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        with urllib.request.urlopen(req2, timeout=12) as r:
            raw = r.read().decode("utf-8", "ignore")
        seg = raw.split("garturlres")[1] if "garturlres" in raw else raw
        m = re.search(r'(https?://[^\\"]+)', seg)
        return m.group(1) if m else link
    except (urllib.error.URLError, TimeoutError, OSError, IndexError):
        return link


sys.path.insert(0, str(BASE_DIR / "scripts"))
from fetch_news_live import get_gemini_api_key  # noqa: E402


_SUMMARY_PROMPT = """다음은 외국계 증권사(글로벌 IB)의 한국 시장·종목 관련 견해를 다룬 국내 기사입니다.
이 IB가 어떤 스탠스를 밝혔는지 1~2문장 한국어로 요약하고, 감성을 분류하세요.

규칙:
- 반드시 해요체(예: ~했어요, ~봤어요)로 끝내세요. '~다', '~습니다'체 금지.
- 제목·요약에 없는 내용을 생성하지 마세요. 목표가·지수 레벨 등 숫자는 제목·요약에 실제로
  있으면 그대로 써도 되지만, 없으면 절대 만들지 마세요.
- sentiment: 상승/비중확대/매수 견해면 "bull", 하락/비중축소/매도 견해면 "bear", 중립·혼조면 "neu".

[제목] {title}
[요약] {desc}

출력(JSON만, 다른 텍스트 없이):
{{"summary": "...", "sentiment": "bull"}}"""


def _summarize_and_classify(title: str, desc: str) -> dict | None:
    """제목+요약으로 스탠스 요약문·감성을 생성한다. 실패 시 None."""
    from google import genai
    from google.genai import types
    try:
        client = genai.Client(api_key=get_gemini_api_key())
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=_SUMMARY_PROMPT.format(title=title, desc=desc),
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=300),
        )
        raw = (resp.text or "").strip()
    except Exception as e:
        print(f"[ib_views] Gemini 요약 실패: {e}", file=sys.stderr)
        return None
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    summary = str(obj.get("summary", "")).strip()
    if not summary:
        return None
    return {"summary": summary, "sentiment": _normalize_sentiment(obj.get("sentiment", "neu"))}


def build_views(now: datetime) -> list[dict]:
    cands = _dedup_by_house(_fetch_rss_candidates(now))
    views: list[dict] = []
    for c in cands:
        sc = _summarize_and_classify(c["title"], c["desc"])
        if not sc:
            print(f"[ib_views] SKIP(요약 실패): {c['title'][:40]}", file=sys.stderr)
            continue
        views.append({
            "house": c["house"],
            "initials": c["initials"],
            "summary": sc["summary"],
            "source": c["source"],
            "url": _resolve_gnews_url(c["link"]),
            "published_at": c["published_at"].isoformat(),
            "time_label": _time_label(c["published_at"], now),
            "sentiment": sc["sentiment"],
        })
    return views


def main() -> None:
    now = datetime.now(KST)
    out_path = DATA_DIR / "ib_korea_views.json"
    try:
        views = build_views(now)
    except Exception as e:
        print(f"[ib_views] ERROR: {e}", file=sys.stderr)
        views = []
    payload = {"generated_at": now.isoformat(), "date": now.strftime("%Y-%m-%d"), "views": views}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ib_views] {len(views)}건 저장 → {out_path}")


if __name__ == "__main__":
    main()
