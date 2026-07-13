#!/usr/bin/env python3
# 외국계 증권사·글로벌 IB의 한국 시장·대형주 코멘트를 Google News RSS로 수집·요약하는 스크립트
"""
Usage:
    python3 scripts/fetch_ib_korea_views.py

출력: data/ib_korea_views.json
  - Google News 한국어 RSS에서 화이트리스트 IB × 코스피/대형주 쿼리로 24시간 이내 pubDate 기사만 1차 수집
  - 제목/요약에 화이트리스트 IB명이 실제로 박혀 있어야 채택 (귀속 불가하면 버림)
  - RSS pubDate는 재크롤링으로 조작될 수 있어 신뢰하지 않는다 — batchexecute로 원문 URL을 리졸브한 뒤
    원문 페이지의 실제 발행일시(JSON-LD/meta, MSN은 콘텐츠 API)를 다시 조회해 그 값이 24시간 이내인지로
    최종 판정한다(_select_verified_candidates). 실제 발행일 추출 실패 시 후보를 버린다.
  - IB당 1건, 최대 3건 (동일 IB는 pubDate 최신순으로 시도해 검증 통과하는 첫 후보)
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


def _get_kospi_ref() -> float | None:
    """yfinance ^KS11 직전 종가 반환. 실패 시 None."""
    try:
        import yfinance as yf
        hist = yf.Ticker("^KS11").history(period="3d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"[ib_views] 코스피 기준 레벨 조회 실패: {e}", file=sys.stderr)
        return None


_KOSPI_MAN_PAT = re.compile(r"(\d{1,2})\s*만\s*(\d{0,4})")
_KOSPI_PLAIN_PAT = re.compile(r"(\d{3,5})\s*(?:선|포인트)")
# 콤마 표기·접미사 없는 숫자("15,000 간다", "15000 가능") — 만/선/포인트 패턴이 놓치는 케이스 보강.
# 예측·전망 동사가 바로 뒤에 와야 매칭(임의의 4~5자리 숫자를 다 지수로 오인하지 않도록 범위 제한).
_KOSPI_FORECAST_PAT = re.compile(r"(\d{1,2},\d{3}|\d{3,5})\s*(?:까지|간다|가능|돌파|도달|넘본다|넘어선다)")


def _extract_index_levels(text: str) -> list:
    """텍스트에서 '1만2000선', '8700포인트', '15,000 간다', '15000 가능' 등
    코스피 지수 레벨 언급을 숫자로 추출."""
    levels = []
    for m in _KOSPI_MAN_PAT.finditer(text):
        rest = m.group(2)
        levels.append(int(m.group(1)) * 10000 + (int(rest) if rest else 0))
    for m in _KOSPI_PLAIN_PAT.finditer(text):
        levels.append(float(m.group(1)))
    for m in _KOSPI_FORECAST_PAT.finditer(text):
        levels.append(float(m.group(1).replace(",", "")))
    return levels


def _is_stale_index_level(text: str, ref: float) -> bool:
    """언급된 지수 레벨이 실제 코스피(ref) 대비 ±30%를 벗어나면 True (구글 뉴스가 재노출한 옛 기사로 판단).

    Google News RSS의 pubDate는 원 기사 발행일이 아니라 재크롤링/재노출 시각을 반영하는 경우가 있어,
    24시간 필터를 통과해도 실제로는 지수 레벨이 몇 달~몇 년 전 수준인 옛 기사가 섞여 들어올 수 있다.
    """
    for lvl in _extract_index_levels(text):
        if lvl < ref * 0.7 or lvl > ref * 1.3:
            return True
    return False


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


def _fetch_rss_candidates(now: datetime, kospi_ref: float | None) -> list[dict]:
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
            if kospi_ref and _is_stale_index_level(title + " " + desc, kospi_ref):
                print(f"[ib_views] SKIP(지수 레벨 이상 — 옛 기사 재노출 추정): {title[:50]}", file=sys.stderr)
                continue
            seen_titles.add(title)
            cands.append({
                "house": house["name"], "initials": house["initials"],
                "title": title, "desc": desc, "source": source,
                "link": link, "published_at": pub,
            })
    return cands


_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"


def _extract_resolved_url(raw: str) -> str | None:
    """batchexecute 응답 원문(garturlres 포함)에서 실제 원문 URL을 복원한다.

    Google이 내부 JSON 문자열을 한 번 더 JSON으로 감싸 이스케이프하기 때문에, 쿼리스트링에
    =·& 같은 특수문자가 있으면 \\u003d·\\u0026 형태로 이중 이스케이프된다. 단순히 '역슬래시가
    아닌 문자'만 매칭하는 정규식은 이 이스케이프 시퀀스의 첫 역슬래시에서 멈춰버려 URL이
    쿼리스트링 시작 지점(예: '?no', '?apiversion')에서 잘린다. \\uXXXX를 실제 문자로 복원한
    뒤 반환해 이 잘림을 막는다.
    """
    if "garturlres" not in raw:
        return None
    seg = raw.split("garturlres", 1)[1]
    m = re.search(r'"(https?://.*?)\\*"', seg)
    if not m:
        return None
    url = m.group(1)
    url = re.sub(r"\\+u([0-9a-fA-F]{4})", lambda mm: chr(int(mm.group(1), 16)), url)
    return url.replace("\\/", "/")


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
        return _extract_resolved_url(raw) or link
    except Exception:
        return link


# ─────────────────────────────────────────────────────────────────────────────
# 실제 발행일시 검증 — Google News RSS pubDate는 재크롤링/재노출 시각을 반영할 수 있어
# 신뢰하지 않는다(2026-07-13·2026-07-14 두 차례 실사고로 확인됨). 원문 페이지의 구조화
# 데이터(JSON-LD datePublished, article:published_time 등)에서 실제 발행일시를 다시 조회해
# 그 값으로만 24시간 이내 여부를 최종 판정한다. 추출 실패 시 신뢰할 수 없는 것으로 간주해
# 후보를 버린다(데이터 정합성 > 완전성).
# ─────────────────────────────────────────────────────────────────────────────

_JSONLD_DATE_PAT = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_META_DATE_PAT = re.compile(
    r'<meta[^>]+(?:property|name|itemprop)=["\']'
    r'(?:article:published_time|og:published_time|datePublished)["\']'
    r'[^>]*content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_MSN_ARTICLE_ID_PAT = re.compile(r"/ar-([A-Za-z0-9]+)")


def _parse_iso_datetime(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_real_published_at(html: str) -> datetime | None:
    """기사 페이지 HTML에서 실제 발행일시(JSON-LD datePublished 또는 meta published_time)를
    추출한다. 구조화 데이터가 없으면 None(신뢰 불가 — 상위에서 후보를 드롭)."""
    for pat in (_JSONLD_DATE_PAT, _META_DATE_PAT):
        m = pat.search(html)
        if m:
            dt = _parse_iso_datetime(m.group(1))
            if dt:
                return dt
    return None


def _fetch_msn_published_at(url: str) -> datetime | None:
    """MSN은 기사 정적 HTML이 클라이언트 렌더링(SPA)이라 meta 태그가 없다.
    MSN 콘텐츠 API(assets.msn.com)로 실제 발행일시(publishedDateTime)를 직접 조회한다."""
    m = _MSN_ARTICLE_ID_PAT.search(url)
    if not m:
        return None
    try:
        api_url = f"https://assets.msn.com/content/view/v2/Detail/ko-kr/{m.group(1)}"
        req = urllib.request.Request(api_url, headers=_HDR)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        raw = data.get("publishedDateTime")
        return _parse_iso_datetime(raw) if raw else None
    except Exception as e:
        print(f"[ib_views] MSN 발행일 조회 실패: {e}", file=sys.stderr)
        return None


def _verify_real_published_at(url: str) -> datetime | None:
    """기사 원문 URL의 실제 발행일시를 조회한다. MSN은 전용 API, 그 외는 페이지 메타데이터.
    조회 실패(추출 불가·네트워크 오류) 시 None."""
    if "msn.com" in url:
        return _fetch_msn_published_at(url)
    try:
        req = urllib.request.Request(url, headers=_HDR)
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"[ib_views] 원문 페이지 조회 실패: {e}", file=sys.stderr)
        return None
    return _parse_real_published_at(html)


def _select_verified_candidates(cands: list[dict], now: datetime, max_items: int = MAX_ITEMS) -> list[dict]:
    """하우스별로 RSS pubDate 최신순으로 시도하며, 원문 URL을 리졸브해 실제 발행일시가
    24시간 이내로 검증되는 첫 후보만 채택한다. 검증 불가·24시간 초과 후보는 다음 후보로 넘어간다.
    (RSS pubDate는 재노출로 조작될 수 있어 최종 판정 근거로 쓰지 않는다.)"""
    by_house: dict[str, list[dict]] = {}
    for c in cands:
        by_house.setdefault(c["house"], []).append(c)
    selected: list[dict] = []
    for items in by_house.values():
        items.sort(key=lambda c: c["published_at"], reverse=True)
        for c in items:
            resolved_url = _resolve_gnews_url(c["link"])
            real_dt = _verify_real_published_at(resolved_url)
            if real_dt is None:
                print(f"[ib_views] SKIP(실발행일 확인 불가): {c['title'][:40]}", file=sys.stderr)
                continue
            real_dt_kst = real_dt.astimezone(KST)
            if not _within_24h(real_dt_kst, now):
                print(f"[ib_views] SKIP(실발행일 24h 초과 — {real_dt_kst.isoformat()}): {c['title'][:40]}", file=sys.stderr)
                continue
            selected.append({**c, "resolved_url": resolved_url, "real_published_at": real_dt_kst})
            break
    selected.sort(key=lambda c: c["real_published_at"], reverse=True)
    return selected[:max_items]


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
    kospi_ref = _get_kospi_ref()
    if kospi_ref:
        print(f"[ib_views] 코스피 기준 레벨 {kospi_ref:.0f}", file=sys.stderr)
    cands = _select_verified_candidates(_fetch_rss_candidates(now, kospi_ref), now)
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
            "url": c["resolved_url"],
            "published_at": c["real_published_at"].isoformat(),
            "time_label": _time_label(c["real_published_at"], now),
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
