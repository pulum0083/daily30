# RSS 우선 뉴스 수집 — 기사 모으기·발행일 확인·LLM 선별·출처 붙이기

from __future__ import annotations
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import news_sources as ns
from session_label import prev_us_session
from news_common import EMPTY_NEWS, KST, get_gemini_api_key
from news_gate_history import _drop_prev_run_echoes, _load_prev_catalysts
from news_gate_earnings import _drop_preview_after_release, _parse_tickers, _resolve_company_tickers
from news_gate_grounding import _drop_placeholder_entities


def _dedupe_articles(articles: list) -> list:
    """같은 사건을 다룬 여러 기사를 대표 1건으로 묶는다.

    대표는 **가장 이른 발행 기사**(pub_time 최소). `source_count`는 보도 매체 수 —
    신뢰도 신호로 참고할 수는 있지만 "사실 여부" 판정에 쓰지 않는다(통신사 기사를 그대로
    받아쓴 기사도 매체 수만 늘린다).
    """
    groups: list[list[dict]] = []
    for a in articles:
        placed = False
        for g in groups:
            if ns.is_dup_title(a["title"], g[0]["title"]):
                g.append(a)
                placed = True
                break
        if not placed:
            groups.append([a])
    out = []
    for g in groups:
        rep = min(g, key=lambda a: a.get("pub_time", "99:99"))
        rep = dict(rep)
        rep["source_count"] = len(g)
        out.append(rep)
    return out


def _articles_prompt_block(articles: list, with_date: bool = False) -> str:
    """기사 목록을 1부터 번호를 매겨 프롬프트에 넣을 텍스트로 만든다.
    with_date면 발행 시각 앞에 날짜(MM-DD)를 붙인다 — 창이 하루를 넘는 코스피 아침용."""
    if not articles:
        return ""
    lines = []
    for i, a in enumerate(articles, start=1):
        when = f"{a.get('date', '')[5:]} {a.get('pub_time', '')}".strip() if with_date else a.get('pub_time', '')
        lines.append(f"{i}. [{when}] {a['title']} ({a.get('source', '')})")
        if a.get("desc"):
            lines.append(f"   {a['desc']}")
    return "\n".join(lines)


_PCT_RE = re.compile(r"\d+(?:\.\d+)?%")


def _article_blob(article: dict) -> str:
    return f"{article.get('title', '')} {article.get('desc', '')}"


def _unsourced_claim(text: str, ticker_field, article: dict) -> str | None:
    """text·ticker가 주장하는 수치·기업이 그 기사(article)에 실제로 있는지 확인한다.

    없으면 사유 문자열을 반환(있으면 None). 검증 대상은 두 가지뿐이다 — ① 텍스트에 등장하는
    퍼센트 수치가 기사 본문에 문자 그대로 있는가 ② 텍스트·ticker가 가리키는 기업이 기사에
    등장하는가. §31 사고(마이크론)는 기사 목록에 그 사건 자체가 없었으므로, 텍스트가 목록
    밖의 기업·수치를 끌어오면 이 시점에 걸러진다.
    """
    blob = _article_blob(article)
    for pct in _PCT_RE.findall(text or ""):
        if pct not in blob:
            return f"기사에 없는 수치({pct})"

    tickers = list(dict.fromkeys(_parse_tickers(ticker_field) + _resolve_company_tickers(text)))
    blob_tickers = set(_parse_tickers(blob) + _resolve_company_tickers(blob))
    for t in tickers:
        if t not in blob_tickers and t not in blob.upper():
            return f"기사에 없는 기업/티커({t})"
    return None


def _resolve_selection(selection: list, articles: list) -> list:
    """LLM이 고른 {idx, text, ticker} 목록을 실제 기사와 대조해 검증된 항목만 남긴다.

    idx는 1부터 시작하는 _articles_prompt_block의 번호와 같다. 범위 밖·누락이면 그 자체로
    검증 불가이므로 버린다. 살아남은 항목에는 원본 기사(article)와 그 기사의 실제 발행
    날짜(date)를 붙인다 — 날짜는 기사에서만 오므로 LLM이 날짜를 위조할 수 없다.
    """
    out = []
    for sel in selection or []:
        idx = sel.get("idx") if isinstance(sel, dict) else None
        if not isinstance(idx, int) or not (1 <= idx <= len(articles)):
            print(f"[fetch_news] RSS 선택 범위 밖 idx 제거: {sel}", file=sys.stderr)
            continue
        article = articles[idx - 1]
        text = str(sel.get("text") or "").strip()
        if not text:
            continue
        reason = _unsourced_claim(text, sel.get("ticker", ""), article)
        if reason:
            print(f"[fetch_news] RSS 미검증 주장 제거({reason}): {text[:60]}", file=sys.stderr)
            continue
        out.append({
            "date": article.get("date", ""),
            "text": text,
            "ticker": str(sel.get("ticker") or ""),
            "article": article,
        })
    return out


def _attach_verified_sources(catalysts: list, log_prefix: str = "fetch_news") -> list:
    """각 항목의 Google News 링크를 원문 URL로 리졸브하고 실제 발행일시를 재확인한다.

    확인 실패(리졸브 실패·구조화 데이터 없음)면 그 항목을 버린다 — RSS pubDate만으로는
    신뢰하지 않는다는 §Google News 재크롤링 원칙(2026-07-13·14 실사고)을 그대로 적용한다.
    검증에 성공한 항목만 실제 출처 URL·발행일시를 달고 살아남는다.
    """
    out = []
    for c in catalysts:
        article = c.get("article") or {}
        if article.get("verified_url"):            # 선별 전에 이미 확인한 기사(_verify_articles)
            url, published = article["verified_url"], article["verified_published"]
        else:
            link = article.get("link", "")
            url = ns.resolve_gnews_url(link) if link else ""
            published = ns.verify_real_published_at(url, log_prefix=log_prefix) if url else None
            if published and not _is_recent(published):
                published = None
        if not url or not published:
            print(f"[fetch_news] RSS 발행일 검증 실패 — 항목 제외: {c.get('text', '')[:60]}",
                  file=sys.stderr)
            continue
        out.append({
            "date": c["date"], "text": c["text"], "ticker": c.get("ticker", ""),
            "url": url, "source": article.get("source", ""),
            "published_at": published.isoformat(),
        })
    return out


# 미국 브리핑 RSS 쿼리 — §19 우선순위(실적·프리마켓 반응·매크로)를 따른다.
_US_RSS_QUERIES = [
    ("뉴욕증시 나스닥", "kr"), ("미국 증시 반도체", "kr"), ("월가 실적 발표", "kr"),
    ("나스닥 프리마켓", "kr"),
    ("Wall Street stocks premarket", "en"), ("US stock market earnings", "en"),
    # 기업 뉴스(실적·가이던스·급등락 종목) — 시황 요약만 잡히던 것을 보완한다(§19, 2026-11-09)
    ("premarket movers stocks", "en"), ("stocks making biggest moves premarket", "en"),
    ("shares earnings beat guidance", "en"), ("미국 실적 발표 주가 급등락", "kr"),
]
# AI 산업 큰 사건 — AI 기업의 상장·대형 투자·공급 계약. 실적·시황 검색어로는 잡히지 않는다
# (2026-11-18 밤 앤트로픽 공모가 83달러·940억 달러 IPO 기사가 수십 건 나왔는데 다음 날 아침 수집이 하나도 못 가져왔다).
# 두 브리핑에 함께 붙인다. 지켜볼 회사가 바뀌면 여기만 고친다.
_AI_EVENT_QUERIES = [
    ("앤트로픽", "kr"), ("오픈AI", "kr"), ("AI 상장 공모", "kr"), ("AI 데이터센터 투자 계약", "kr"),
    ("Anthropic", "en"), ("OpenAI", "en"), ("AI IPO", "en"),
]
_US_RSS_QUERIES += _AI_EVENT_QUERIES
# 코스피 아침(07:25) — 직전 코스피 장 마감 뒤 밤사이 미국에서 나온 기사. 장 마감 뒤 실적·시간외 반응을
# 꼭 잡도록 '실적'·'시간외'·'after hours' 검색어를 둔다(2026-11-18: 06:20 엔비디아 실적을 07:27 수집이 놓쳤다).
_KOSPI_RSS_QUERIES = [
    ("뉴욕증시 마감", "kr"), ("미국 증시 반도체", "kr"), ("실적 발표 시간외 주가", "kr"),
    ("시간외 거래 급등", "kr"), ("코스피 전망 개장", "kr"), ("오늘 증시 전망", "kr"),
    ("stocks after hours earnings", "en"), ("after-hours movers", "en"),
    ("shares earnings beat guidance", "en"), ("Wall Street close stocks", "en"),
] + _AI_EVENT_QUERIES
KOSPI_RSS_SINCE_HOUR = 16   # 직전 코스피 거래일 16:00 KST 이후 기사(정규장 15:30 마감 뒤)
RSS_SELECT_MAX = 7          # 선별 상한 — 2026-11-09 전엔 4였고 검증에서 빠져 하루 0~3건만 남았다
RECENT_HOURS = 30           # 실제 발행일이 이보다 오래된 기사는 쓰지 않는다(구글 재크롤링 옛 기사 차단)

_RSS_SELECT_PROMPT = """아래는 오늘({today}) 실제로 수집된 미국 시장 관련 기사 목록이다(번호·발행시각·매체·요약 포함).
이 목록에 있는 사건 중, 오늘 미국 증시 브리핑에 담을 만큼 중요한 것을 최대 {max_n}개 골라라.
지수 등락을 요약한 시황 기사보다 **기업의 실적·가이던스·경영진 발언·급등락 이유** 같은 구체적인 사건을 먼저 고른다.
**AI 산업 큰 사건**(앤트로픽·오픈AI 같은 AI 기업의 상장·대형 투자·공급 계약)도 시황 기사보다 먼저 고른다 —
AI 투자 심리를 움직여 반도체·AI 인프라 종목으로 이어진다.
같은 시황을 다룬 기사는 하나만 고른다.

[기사 목록]
{articles}

[출력 규칙]
- 반드시 목록의 번호(idx)를 참조한다. 목록에 없는 사건·기업·수치를 새로 만들지 않는다.
- text는 "사건 → 영향" 한 문장. 숫자를 쓸 때는 **목록에 있는 숫자만** 그대로 옮겨 쓴다.
- ticker는 그 사건의 주체 기업 미국 티커. 거시·지정학이면 빈 문자열.
- 목록은 최신 발행순이다. 같은 사건을 다룬 기사가 여럿이면 **가장 최근 기사** 하나만 고른다 — 영어·한국어로
  언어가 달라도 같은 회사의 같은 일이면 같은 사건이다(2026-11-19: 앤트로픽 상장 기사 세 건을 따로 골랐다).
- 실적·지표처럼 이미 발표된 사건은 결과 기사를 고른다. 발표 전에 쓰인 예고 기사("임박"·"앞두고"·"Ahead of")를
  골라 아직 안 나온 일처럼 쓰지 않는다 — 그 사이에 결과가 나왔을 수 있다.
- 중요한 기사가 없으면 selection을 빈 배열로 둔다. 억지로 채우지 않는다.

출력 형식 (JSON만):
{{"selection": [{{"idx": 1, "text": "사건 → 영향", "ticker": "MU"}}]}}"""


_KOSPI_RSS_SELECT_PROMPT = """아래는 오늘({today}) 코스피 개장 전(07:25)에 실제로 수집된 기사 목록이다(번호·발행시각·매체·요약 포함).
직전 코스피 장 마감 뒤부터 지금까지 나온 기사다. 이 중 오늘 코스피 개장에 영향을 줄 사건을 최대 {max_n}개 골라라.
**미국 장 마감 뒤에 나온 기업 실적·가이던스와 그에 따른 시간외 주가 반응**을 가장 먼저 고른다 — 특히 엔비디아 같은
AI 반도체·인프라 기업 실적은 삼성전자·SK하이닉스와 직결된다. 그다음 **AI 산업 큰 사건**(앤트로픽·오픈AI 같은
AI 기업의 상장·대형 투자·공급 계약 — AI 투자 심리와 HBM 수요 기대로 이어진다), 미국 증시 마감 원인, 국내 개장 변수 순이다.
같은 사건을 다룬 기사는 하나만 고른다.

[기사 목록]
{articles}

[출력 규칙]
- 반드시 목록의 번호(idx)를 참조한다. 목록에 없는 사건·기업·수치를 새로 만들지 않는다.
- text는 "사건 → 영향" 한 문장. 숫자를 쓸 때는 **목록에 있는 숫자만** 그대로 옮겨 쓴다.
- ticker는 그 사건의 주체 기업 미국 티커. 국내 기업·거시·지정학이면 빈 문자열.
- 목록은 최신 발행순이다. 같은 사건을 다룬 기사가 여럿이면 **가장 최근 기사** 하나만 고른다 — 영어·한국어로
  언어가 달라도 같은 회사의 같은 일이면 같은 사건이다(2026-11-19: 앤트로픽 상장 기사 세 건을 따로 골랐다).
- 실적처럼 이미 발표된 사건은 결과 기사를 고른다. 발표 전에 쓰인 예고 기사("앞두고"·"임박"·"Ahead of")를
  골라 아직 안 나온 일처럼 쓰지 않는다 — 그 사이에 결과가 나왔을 수 있다.
- 중요한 기사가 없으면 selection을 빈 배열로 둔다. 억지로 채우지 않는다.

출력 형식 (JSON만):
{{"selection": [{{"idx": 1, "text": "사건 → 영향", "ticker": "NVDA"}}]}}"""


def _kospi_rss_since(today: date):
    """코스피 아침 RSS 창의 시작 — 직전 코스피 거래일 16:00 KST. 월요일이면 금요일 오후부터 주말까지 본다."""
    from session_label import prev_kospi_session
    prev = prev_kospi_session(today) or (today - timedelta(days=1))
    return KST.localize(datetime(prev.year, prev.month, prev.day, KOSPI_RSS_SINCE_HOUR))


def _us_news_session(today: date) -> dict | None:
    """미국 브리핑이 참조하는 뉴스 세션 — 직전 정규장.

    미국 브리핑은 21:15 KST(= 미국 프리마켓)에 나가고 RSS 수집은 오늘 KST 발행분만 담는다.
    그 기사들이 다룰 수 있는 최신 세션은 구조적으로 **직전 정규장 하나뿐**이라, 기사별로
    세션을 나누지 않고 하루치 라벨 하나만 계산한다(서머타임 경계 계산을 들여도 얻는 게
    없고 틀릴 여지만 는다 — 판단 근거는 계획 context-notes 2026-08-11).

    이 값이 없으면 call_claude는 세션 지시문을 만들지 않는다 — 근거 없는 지시를
    지어내지 않기 위해서다(§0).
    """
    prev = prev_us_session(today)
    if prev is None:
        return None
    return {"date": prev.isoformat(), "label": "직전 정규장"}


def _is_recent(published: datetime, now: datetime | None = None, hours: float = RECENT_HOURS) -> bool:
    """실제 발행일이 최근 hours(기본 RECENT_HOURS) 안인지. 시각 없는 값(주소 날짜)은 그날 정오 UTC로 들어온다.
    앞으로 12시간까지는 허용한다 — 시간대 표기가 없는 메타데이터·정오로 둔 주소 날짜의 오차."""
    now = now or datetime.now(KST)
    if published.tzinfo is None:
        published = KST.localize(published)
    age = now - published
    return timedelta(hours=-12) <= age <= timedelta(hours=hours)


def _verify_articles(articles: list, workers: int = 8, hours: float = RECENT_HOURS) -> list:
    """모은 기사 전부의 원문 주소·실제 발행일을 먼저 확인하고, 확인된 최근 기사만 남긴다.
    RSS pubDate는 믿지 않는다(§Google News 재크롤링 원칙). 확인 결과는 기사에 붙여 둔다 —
    _attach_verified_sources가 다시 조회하지 않는다."""
    from concurrent.futures import ThreadPoolExecutor

    def check(a):
        url = ns.resolve_gnews_url(a.get("link", "")) if a.get("link") else ""
        pub = ns.verify_real_published_at(url, log_prefix="fetch_news") if url else None
        return a, url, pub
    out, old, fail = [], 0, 0
    with ThreadPoolExecutor(workers) as ex:
        for a, url, pub in ex.map(check, articles):
            if not url or not pub:
                fail += 1
            elif not _is_recent(pub, hours=hours):
                old += 1
                print(f"[fetch_news] 실제 발행일이 오래된 기사 제외({pub.date()}): {a.get('title', '')[:50]}", file=sys.stderr)
            else:
                out.append({**a, "verified_url": url, "verified_published": pub})
    print(f"[fetch_news] 발행일 확인 — 모은 기사 {len(articles)}건 중 {len(out)}건 통과(확인 실패 {fail} · 오래됨 {old})")
    return out


def fetch_and_summarize_rss(briefing_type: str) -> dict:
    """RSS로 실제 기사를 먼저 모으고, LLM은 그 목록에서 고르고 요약만 한다.

    google_search 그라운딩과 달리 날짜·출처 URL이 기사에서 그대로 온다 — LLM이 위조할 수
    없다. 목록 밖 숫자·기업이 텍스트에 섞이면 _resolve_selection이 항목째 버린다(§31).
    미국 브리핑과 코스피 아침을 지원한다. 코스피 아침은 Gemini 검색 결과에 이 결과를 앞에 붙인다
    (fetch_news.merge_rss_catalysts — 2026-11-18: 06:20 엔비디아 실적을 Gemini 검색이 놓쳤다).
    """
    if briefing_type not in ("us", "kospi"):
        raise NotImplementedError(f"RSS 수집 경로는 us·kospi만 지원한다: {briefing_type}")

    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    if briefing_type == "kospi":
        queries, since = _KOSPI_RSS_QUERIES, _kospi_rss_since(now.date())
        hours = (now - since).total_seconds() / 3600 + 1
        select_prompt = _KOSPI_RSS_SELECT_PROMPT
    else:
        queries, since, hours, select_prompt = _US_RSS_QUERIES, None, RECENT_HOURS, _RSS_SELECT_PROMPT
    articles: list[dict] = []
    seen: set[str] = set()
    for q, lang in queries:
        for a in ns.fetch_rss(ns.gnews_url(q, lang), today, max_items=12, log_prefix="fetch_news", since=since):
            if a["title"] not in seen:
                seen.add(a["title"])
                articles.append(a)
    # 날짜를 넘는 창(코스피 아침)도 있으니 날짜+시각으로 정렬한다
    articles.sort(key=lambda a: (a.get("date", ""), a.get("pub_time", "99:99")))
    articles = _dedupe_articles(articles)
    # 발행일을 먼저 확인한다 — 고른 뒤에 확인하면 고른 기사의 절반 가까이가 버려졌다(2026-11-09 점검).
    articles = _verify_articles(articles, hours=hours)
    # 최신 기사를 앞에 둔다 — 오래된 순이면 새벽 예고 기사가 1번에 놓여 먼저 뽑힌다(2026-10-01).
    articles.sort(key=lambda a: (a.get("date", ""), a.get("pub_time", "")), reverse=True)

    if not articles:
        print("[fetch_news] RSS 수집·발행일 확인 후 0건 — 뉴스 없이 발행(§27)", file=sys.stderr)
        return dict(EMPTY_NEWS)

    from google import genai
    from google.genai import types
    # google_search는 v1beta만 받는다 — google-genai 3.0부터 기본값이 v1이라 명시한다(2026-11-13)
    client = genai.Client(api_key=get_gemini_api_key(),
                          http_options=types.HttpOptions(api_version="v1beta"))
    prompt = select_prompt.format(today=today, max_n=RSS_SELECT_MAX, articles=_articles_prompt_block(articles, with_date=briefing_type == "kospi"))
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite", contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=1600),
    )
    raw = (response.text or "").strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    m = re.search(r"\{[\s\S]*\}", raw)
    data = json.loads(m.group(0) if m else raw)

    resolved = _resolve_selection(data.get("selection"), articles)
    prev_items = _load_prev_catalysts(briefing_type)
    resolved = _drop_prev_run_echoes(resolved, prev_items)
    resolved = _drop_placeholder_entities(resolved)
    resolved = _drop_preview_after_release(resolved, datetime.now(KST))
    verified = _attach_verified_sources(resolved)

    out = {
        "key_indicators": [],
        "catalysts": [c["text"] for c in verified],
        "catalyst_sources": verified,   # 계획 3단계(출처 표시)에서 소비 — url·source·published_at
        "headlines": [],
        "market_sentiment": "neutral",
    }
    # 이 기사들이 다루는 세션을 계산해 함께 넘긴다. 모델이 published_at에서 스스로
    # 추론하게 두면 직전 정규장 값을 "지금 프리마켓"으로 쓰는 §26이 재발한다.
    session = _us_news_session(datetime.now(KST).date()) if briefing_type == "us" else None
    if session:
        out["news_session"] = session
    return out
