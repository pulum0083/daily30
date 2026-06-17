# 이슈 브리핑 수집 스크립트 — RSS 기반 2단계 파이프라인
# 1단계: 네이버 증권 RSS + Google News RSS 로 오늘 날짜 기사 수집 (날짜·제목 실데이터)
# 2단계: Gemini 로 선별만 (google_search 미사용 → 날짜 세탁 원천 차단)

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).parent.parent
OUT_PATH = REPO_ROOT / "web" / "data" / "kospi-news-live.json"
MAX_HISTORY = 6


# ── 시간대 판별 ──────────────────────────────────────────────────────────────

def get_slot(hour: int, minute: int) -> str:
    """KST 시·분을 받아 구간 문자열을 반환한다.

    MARKET      09:00~15:30  장중 실시간
    POST_MARKET 16:35~21:29  마감 후 + 미국 프리마켓
    US_MARKET   21:30~01:00  미국 시장
    """
    total = hour * 60 + minute
    if 540 <= total <= 930:
        return "MARKET"
    if 995 <= total < 1290:
        return "POST_MARKET"
    if total >= 1290 or total <= 60:
        return "US_MARKET"
    return "MARKET"


# ── RSS 수집 ─────────────────────────────────────────────────────────────────

def _parse_rss_date(date_str: str) -> str | None:
    """RSS pubDate → YYYY-MM-DD (KST). 실패 시 None."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str.strip())
        return dt.astimezone(KST).strftime("%Y-%m-%d")
    except Exception:
        return None


def _clean_title(title: str) -> str:
    """Google News RSS 제목 끝 '- 출처명' 제거 + 괄호 태그 제거."""
    title = re.sub(r"\s*-\s*[^-]{1,30}$", "", title.strip())
    title = re.sub(r"\[.*?\]", "", title)
    title = re.sub(r"\(.*?\)", "", title)
    return re.sub(r"\s{2,}", " ", title).strip()


def _fetch_rss(url: str, today: str, max_items: int = 15) -> list[dict]:
    """RSS URL에서 오늘 날짜(KST) 기사만 수집한다."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            xml_bytes = r.read()
        root = ET.fromstring(xml_bytes)
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub_date = _parse_rss_date(item.findtext("pubDate") or "")
            source_el = item.find("source")
            source = (source_el.text or "").strip() if source_el is not None else ""

            if not title or pub_date != today:
                continue

            desc = re.sub(r"<[^>]+>", "", desc)[:180].strip()
            items.append({
                "title": _clean_title(title),
                "date": pub_date,
                "source": source,
                "desc": desc,
            })
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"[fetch_news_live] RSS 수집 실패 ({url[:70]}): {e}")
        return []


_GN_KR = "https://news.google.com/rss/search?hl=ko&gl=KR&ceid=KR:ko&q="
_GN_EN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="


def fetch_articles(slot: str, today: str) -> list[dict]:
    """슬롯별로 Google News RSS에서 오늘 날짜 기사를 수집·합친다."""
    if slot == "MARKET":
        queries_kr = ["코스피 주식", "코스피 수급 외국인"]
        queries_en = []
    elif slot == "POST_MARKET":
        queries_kr = ["코스피 마감", "뉴욕증시 프리마켓"]
        queries_en = []
    else:  # US_MARKET
        queries_kr = ["나스닥 뉴욕증시"]
        queries_en = ["S&P 500 nasdaq stock market"]

    sources = (
        [_GN_KR + urllib.parse.quote(q) for q in queries_kr]
        + [_GN_EN + urllib.parse.quote(q) for q in queries_en]
    )

    articles: list[dict] = []
    seen: set[str] = set()
    for url in sources:
        for item in _fetch_rss(url, today):
            if item["title"] not in seen:
                seen.add(item["title"])
                articles.append(item)

    return articles


# ── Gemini 선별 (google_search 미사용) ───────────────────────────────────────

_SLOT_DESC = {
    "MARKET":      "장중 코스피",
    "POST_MARKET": "장 마감 후·미국 프리마켓",
    "US_MARKET":   "미국 장중",
}

_SELECT_PROMPT = """오늘 {today} {time} KST — {slot_desc} 시간대.
아래는 실제 RSS에서 수집한 오늘 날짜 기사 목록입니다.
이 중에서 투자자에게 가장 중요한 기사 2개를 선택해 주세요.

[기사 목록]
{article_list}

[선택 기준]
- market: 시장 전체 (코스피·코스닥 지수, 수급, 환율, 글로벌 이슈)
- stock: 특정 종목·섹터 이슈

{avoid_block}[출력 규칙]
- idx: 위 목록 번호 (0부터 시작)
- summary: 제목·설명을 토대로 투자자에게 핵심을 전달하는 1~2문장 (사실만, 추측 금지)
- 아래 JSON만 출력 (마크다운 없이):
{{"market": {{"idx": 0, "summary": "요약"}}, "stock": {{"idx": 1, "summary": "요약"}}}}
"""

_AVOID_TMPL = """[직전 이슈 중복 금지 — 완전히 다른 종목·주제 선택]
{items}

"""


def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        cfg = REPO_ROOT / "config.json"
        if cfg.exists():
            with open(cfg, encoding="utf-8") as f:
                key = json.load(f).get("gemini", {}).get("api_key", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found in env or config.json")
    return key


def _call_gemini_select(
    articles: list[dict],
    slot: str,
    today: str,
    time_str: str,
    avoid_titles: list | None = None,
) -> dict:
    """Gemini에게 기사 목록을 주고 인덱스 선별만 시킨다 (google_search 미사용)."""
    from google import genai
    from google.genai import types

    article_list = "\n".join(
        f"{i}. \"{a['title']}\""
        + (f"  ↳ {a['desc'][:80]}" if a.get("desc") else "")
        + (f" ({a['source']})" if a.get("source") else "")
        for i, a in enumerate(articles)
    )
    avoid_block = ""
    if avoid_titles:
        avoid_block = _AVOID_TMPL.format(items="\n".join(f"- {t}" for t in avoid_titles))

    prompt = _SELECT_PROMPT.format(
        today=today, time=time_str,
        slot_desc=_SLOT_DESC[slot],
        article_list=article_list,
        avoid_block=avoid_block,
    )

    client = genai.Client(api_key=get_gemini_api_key())
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=300),
    )
    raw = (response.text or "").strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    parsed = json.loads(raw)

    result = {}
    for key in ("market", "stock"):
        sel = parsed.get(key) or {}
        idx = sel.get("idx")
        if isinstance(idx, int) and 0 <= idx < len(articles):
            result[key] = {
                "title":   articles[idx]["title"],
                "summary": (sel.get("summary") or "").strip(),
                "pub_date": articles[idx]["date"],
                "source":  articles[idx].get("source", ""),
            }
        else:
            result[key] = None
    return result


# ── 사후 검증 (방향 모순·지수 레벨·큐레이션·중복) ───────────────────────────

_UP_WORDS   = re.compile(r"반등|상승|급등|오름|강세|올라|뛰어|돌파|신고가")
_DOWN_WORDS = re.compile(r"하락|급락|폭락|무너|붕괴|추락|약세|내려|곤두박")
_EXTREME_CRASH = re.compile(r"서킷브레이커|서킷 브레이커|붕괴")
_KOSPI_LEVEL_PAT = re.compile(r"(?:\d{1,2},)?(\d{3,4})[선포]")
_CURATION_PAT = re.compile(
    r"주목받은\s*주식|오늘의\s*추천|이번\s*주\s*주목|요일별\s*추천|"
    r"stocks?\s*to\s*watch|top\s*stocks?|best\s*stocks?|"
    r"(?:월|화|수|목|금|토|일)요일[^\n]{0,5}주목|주목할\s*주식|추천\s*종목\s*[0-9]",
    re.IGNORECASE,
)
_STOPWORDS = {
    "이슈", "뉴스", "기자", "오늘", "어제", "지난", "이번", "관련", "대한", "따른",
    "코스피", "코스닥", "주가", "주식", "시장", "장중", "장세", "상승", "하락",
    "전환", "반등", "급등", "급락", "강세", "약세", "회복", "마감",
}


def _get_market_reality():
    """삼성전자 현재가로 장중 방향을 추정한다. 실패 시 None."""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        import scripts.toss_client as tc
        prices = tc.get_prices(["005930"])
        if not prices:
            return None
        current = float(prices[0].get("lastPrice") or 0)
        if not current:
            return None
        today_str = datetime.now(KST).strftime("%Y-%m-%d")
        candles = tc.get_candles("005930", interval="1d", count=5)
        prev_closes = [
            float(c["closePrice"]) for c in candles
            if c.get("closePrice") and c.get("timestamp", "")[:10] != today_str
        ]
        if not prev_closes:
            return None
        change_pct = (current - prev_closes[-1]) / prev_closes[-1] * 100
        return {"change_pct": round(change_pct, 2)}
    except Exception as e:
        print(f"[fetch_news_live] market reality 조회 실패: {e}")
        return None


def _get_kospi_ref() -> float | None:
    """yfinance ^KS11 직전 종가 반환. 실패 시 None."""
    try:
        import yfinance as yf
        hist = yf.Ticker("^KS11").history(period="3d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"[fetch_news_live] 코스피 기준 레벨 조회 실패: {e}")
        return None


def _is_direction_conflict(result: dict, change_pct: float) -> bool:
    titles = " ".join([
        (result.get("market") or {}).get("title", ""),
        (result.get("stock") or {}).get("title", ""),
    ])
    if change_pct > 0.5 and _EXTREME_CRASH.search(titles):
        return True
    if change_pct <= -1.5 and _UP_WORDS.search(titles):
        return True
    if change_pct >= 1.5 and _DOWN_WORDS.search(titles):
        return True
    return False


def _is_wrong_index_level(result: dict, ref: float) -> list:
    bad = []
    for key in ("market", "stock"):
        title = (result.get(key) or {}).get("title", "")
        for m in _KOSPI_LEVEL_PAT.finditer(title):
            level = float(m.group(1).replace(",", ""))
            if level < ref * 0.7 or level > ref * 1.3:
                bad.append(f"{key}: {title} (언급={level:.0f}, 실제≈{ref:.0f})")
                break
    return bad


def _is_curation(result: dict) -> bool:
    stock_title = (result.get("stock") or {}).get("title", "")
    return bool(_CURATION_PAT.search(stock_title or ""))


def _title_kw(title: str) -> set:
    return set(re.findall(r"[가-힣A-Za-z]{2,}", title)) - _STOPWORDS


def _find_duplicate(result: dict, existing_titles: list, threshold: float = 0.55) -> list:
    new_titles = [
        (result.get("market") or {}).get("title", ""),
        (result.get("stock") or {}).get("title", ""),
    ]
    blocked = set()
    for nt in new_titles:
        if not nt:
            continue
        wa = _title_kw(nt)
        for et in existing_titles:
            wb = _title_kw(et)
            if wa and wb and len(wa & wb) / min(len(wa), len(wb)) >= threshold:
                blocked |= wa & wb
    return sorted(blocked)


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    slot = get_slot(now.hour, now.minute)

    print(f"[fetch_news_live] {today} {time_str} KST — 슬롯={slot} — RSS 수집 시작")

    # 1단계: RSS로 오늘 날짜 기사 수집
    articles = fetch_articles(slot, today)
    print(f"[fetch_news_live] 수집된 기사: {len(articles)}건")
    for a in articles:
        print(f"  [{a['source']}] {a['title']}")

    if len(articles) < 2:
        print("[fetch_news_live] 오늘 날짜 기사 부족 (2건 미만) — 발행 생략.", file=sys.stderr)
        sys.exit(0)

    # 오늘 이미 발행된 타이틀 목록 (중복 방지용)
    # seen_titles: history 수동 정리와 무관하게 오늘 발행된 모든 타이틀을 누적
    all_today_titles: list = []
    prev_seen_titles: list = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if existing.get("date") == today:
                # 1순위: seen_titles 필드 (수동 정리에도 유지됨)
                prev_seen_titles = existing.get("seen_titles", [])
                all_today_titles = list(prev_seen_titles)
                # 2순위: history 기반 보완 (seen_titles 미도입 구버전 대응)
                for h in [existing.get("latest", {})] + existing.get("history", []):
                    for key in ("market", "stock"):
                        t = (h.get(key) or {}).get("title", "")
                        if t and t not in all_today_titles:
                            all_today_titles.append(t)
        except Exception:
            pass

    # MARKET 슬롯: 실측 방향 + 코스피 레벨 조회
    market_reality = _get_market_reality() if slot == "MARKET" else None
    kospi_ref = _get_kospi_ref() if slot == "MARKET" else None
    if market_reality:
        print(f"[fetch_news_live] 삼성전자 {market_reality['change_pct']:+.1f}%")
    if kospi_ref:
        print(f"[fetch_news_live] 코스피 기준 {kospi_ref:.0f}")

    # 2단계: Gemini 선별 + 검증 루프
    result = None
    for attempt in range(4):
        avoid_titles = all_today_titles or None
        try:
            result = _call_gemini_select(articles, slot, today, time_str, avoid_titles)
        except Exception as e:
            print(f"[fetch_news_live] ERROR (시도 {attempt+1}): {e}", file=sys.stderr)
            if attempt == 3:
                sys.exit(1)
            continue

        if not result.get("market") or not result.get("stock"):
            print(f"[fetch_news_live] ⚠️ 선별 결과 불완전 (시도 {attempt+1}) — 재시도")
            continue

        if market_reality and _is_direction_conflict(result, market_reality["change_pct"]):
            titles = f"{result['market']['title']} / {result['stock']['title']}"
            print(f"[fetch_news_live] ⚠️ 방향 모순 (시도 {attempt+1}): {titles} — 재시도")
            continue

        if kospi_ref:
            wrong = _is_wrong_index_level(result, kospi_ref)
            if wrong:
                print(f"[fetch_news_live] ⚠️ 코스피 레벨 불일치 (시도 {attempt+1}): {wrong} — 재시도")
                continue

        if _is_curation(result):
            print(f"[fetch_news_live] ⚠️ 큐레이션 기사 (시도 {attempt+1}) — 재시도")
            continue

        if all_today_titles:
            dup = _find_duplicate(result, all_today_titles)
            if dup:
                print(f"[fetch_news_live] ⚠️ 중복 (시도 {attempt+1}): {dup} — 재시도")
                continue  # 항상 재시도 — 마지막 시도도 중복이면 for-else에서 발행 생략

        break
    else:
        print("[fetch_news_live] ❌ 4회 후에도 유효한 기사 없음. 발행 생략.", file=sys.stderr)
        sys.exit(0)

    # history 이어받기
    history: list = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if existing.get("date") == today:
                history = existing.get("history", [])
        except Exception:
            pass

    new_entry = {"time": time_str}
    new_entry.update(result)
    history = [new_entry] + history
    history = history[:MAX_HISTORY]

    # seen_titles 갱신: 오늘 발행된 타이틀 누적 (history 정리에도 유지)
    seen_titles = list(prev_seen_titles)
    for key in ("market", "stock"):
        t = (result.get(key) or {}).get("title", "")
        if t and t not in seen_titles:
            seen_titles.append(t)

    data = {
        "date": today,
        "updated_at": time_str,
        "slot": slot,
        "seen_titles": seen_titles,
        "latest": result,
        "history": history,
    }
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_news_live] Saved → {OUT_PATH}")

    archive_path = OUT_PATH.parent / f"kospi-news-{today}.json"
    archive_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_news_live] Archive → {archive_path.name}")


if __name__ == "__main__":
    main()
