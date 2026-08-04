# Google News RSS 수집·원문 URL 리졸브·실제 발행일 검증을 공유하는 뉴스 수집 공용 모듈
#
# 이 모듈이 생긴 이유 (SERVICE_RULES §30·§31):
#   같은 판정 로직을 여러 스크립트가 각자 구현하면 한쪽만 고쳐진 채 나머지가 몇 주씩
#   방치된다. 실제로 fetch_news_live.py와 fetch_ib_korea_views.py는 _clean_title·
#   _resolve_gnews_url·_extract_resolved_url을 각각 들고 있었고 문서화 수준이 갈라져 있었다.
#   앞으로 뉴스 수집기(fetch_news.py 포함)는 여기 있는 것을 쓴다.
#
# 핵심 원칙 — **날짜·URL은 실데이터에서만 나온다.** RSS pubDate조차 신뢰하지 않고
# 원문 페이지의 구조화 데이터로 재확인한다(2026-07-13·07-14 두 차례 실사고).

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))

HDR = {"User-Agent": "Mozilla/5.0"}
BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
GN_KR = "https://news.google.com/rss/search?hl=ko&gl=KR&ceid=KR:ko&q="
GN_EN = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="


def gnews_url(query: str, lang: str = "kr") -> str:
    """검색어로 Google News RSS URL을 만든다."""
    return (GN_KR if lang == "kr" else GN_EN) + urllib.parse.quote(query)


# ── RSS 파싱 ─────────────────────────────────────────────────────────────────

def parse_rss_datetime(date_str: str) -> tuple[str | None, str | None]:
    """RSS pubDate → (YYYY-MM-DD, HH:MM) KST. 실패 시 (None, None)."""
    if not date_str:
        return None, None
    try:
        dt = parsedate_to_datetime(date_str.strip()).astimezone(KST)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except Exception:
        return None, None


def clean_title(title: str, strip_brackets: bool = False) -> str:
    """Google News RSS 제목 끝 '- 출처명'을 제거한다.

    strip_brackets=True면 [단독]·(종합) 같은 괄호 태그도 함께 지운다.
    두 소비처의 기존 동작이 실제로 달랐어서 파라미터로 남긴다 — 임의로 통일하지 않는다.
    """
    title = re.sub(r"\s*-\s*[^-]{1,30}$", "", title.strip())
    if strip_brackets:
        title = re.sub(r"\[.*?\]", "", title)
        title = re.sub(r"\(.*?\)", "", title)
    return re.sub(r"\s{2,}", " ", title).strip()


def fetch_rss(url: str, today: str, max_items: int = 15,
              strip_brackets: bool = True, log_prefix: str = "news_sources") -> list[dict]:
    """RSS URL에서 오늘 날짜(KST) 기사만 수집한다. pub_time(HH:MM) 포함.

    ⚠️ 여기서 쓰는 pubDate는 **수집 후보를 고르는 용도**일 뿐이다. 채택 판정에는
    verify_real_published_at()으로 원문 실제 발행일을 다시 확인해야 한다 —
    Google이 오래된 기사를 재크롤링하며 pubDate를 현재 시각으로 다시 찍는 사례가 있다.
    """
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=12) as r:
            xml_bytes = r.read()
        root = ET.fromstring(xml_bytes)
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            desc = (item.findtext("description") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date, pub_time = parse_rss_datetime(item.findtext("pubDate") or "")
            source_el = item.find("source")
            source = (source_el.text or "").strip() if source_el is not None else ""

            if not title or pub_date != today:
                continue

            desc = re.sub(r"<[^>]+>", "", desc)[:180].strip()
            items.append({
                "title": clean_title(title, strip_brackets),
                "date": pub_date,
                "pub_time": pub_time or "00:00",
                "source": source,
                "desc": desc,
                "link": link,
            })
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"[{log_prefix}] RSS 수집 실패 ({url[:70]}): {e}")
        return []


# ── Google News 링크 → 발행사 원문 URL ────────────────────────────────────────

def extract_resolved_url(raw: str) -> str | None:
    """batchexecute 응답 원문(garturlres 포함)에서 실제 원문 URL을 복원한다.

    Google이 내부 JSON 문자열을 한 번 더 JSON으로 감싸 이스케이프하기 때문에, 쿼리스트링에
    =·& 같은 특수문자가 있으면 \\u003d·\\u0026 형태로 이중 이스케이프된다. 단순히 '역슬래시가
    아닌 문자'만 매칭하는 정규식은 이 이스케이프 시퀀스의 첫 역슬래시에서 멈춰버려 URL이
    쿼리스트링 시작 지점(예: '?no', '?apiversion')에서 잘린다. \\uXXXX를 실제 문자로 복원한
    뒤 반환해 이 잘림을 막는다(2026-07-14 수정 — 쿼리스트링 있는 URL로 반드시 재검증할 것).
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


def resolve_gnews_url(link: str) -> str:
    """Google News 기사 링크를 발행사 원문 URL로 리졸브한다. 실패 시 원래 link 반환."""
    if not link or "/rss/articles/" not in link:
        return link
    try:
        art = link.split("/articles/")[1].split("?")[0]
        req = urllib.request.Request(link, headers=HDR)
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
            BATCH_URL, data=body.encode(),
            headers={**HDR, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        with urllib.request.urlopen(req2, timeout=12) as r:
            raw = r.read().decode("utf-8", "ignore")
        return extract_resolved_url(raw) or link
    except Exception:
        return link


# ── 실제 발행일시 검증 ────────────────────────────────────────────────────────
# Google News RSS pubDate는 재크롤링/재노출 시각을 반영할 수 있어 신뢰하지 않는다
# (2026-07-13·2026-07-14 두 차례 실사고). 원문 페이지의 구조화 데이터에서 실제
# 발행일시를 다시 조회해 그 값으로만 최종 판정한다. 추출 실패 시 후보를 버린다
# (완전성보다 정합성 — 운영 규칙 0).

_JSONLD_DATE_PAT = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_META_DATE_PAT = re.compile(
    r'<meta[^>]+(?:property|name|itemprop)=["\']'
    r'(?:article:published_time|og:published_time|datePublished)["\']'
    r'[^>]*content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_MSN_ARTICLE_ID_PAT = re.compile(r"/ar-([A-Za-z0-9]+)")


def parse_iso_datetime(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_real_published_at(html: str) -> datetime | None:
    """기사 페이지 HTML에서 실제 발행일시(JSON-LD datePublished 또는 meta published_time)를
    추출한다. 구조화 데이터가 없으면 None(신뢰 불가 — 상위에서 후보를 드롭)."""
    for pat in (_JSONLD_DATE_PAT, _META_DATE_PAT):
        m = pat.search(html)
        if m:
            dt = parse_iso_datetime(m.group(1))
            if dt:
                return dt
    return None


def fetch_msn_published_at(url: str, log_prefix: str = "news_sources") -> datetime | None:
    """MSN은 기사 정적 HTML이 클라이언트 렌더링(SPA)이라 meta 태그가 없다.
    MSN 콘텐츠 API(assets.msn.com)로 실제 발행일시(publishedDateTime)를 직접 조회한다."""
    m = _MSN_ARTICLE_ID_PAT.search(url)
    if not m:
        return None
    try:
        api_url = f"https://assets.msn.com/content/view/v2/Detail/ko-kr/{m.group(1)}"
        req = urllib.request.Request(api_url, headers=HDR)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        raw = data.get("publishedDateTime")
        return parse_iso_datetime(raw) if raw else None
    except Exception as e:
        print(f"[{log_prefix}] MSN 발행일 조회 실패: {e}", file=sys.stderr)
        return None


def verify_real_published_at(url: str, log_prefix: str = "news_sources") -> datetime | None:
    """기사 원문 URL의 실제 발행일시를 조회한다. MSN은 전용 API, 그 외는 페이지 메타데이터.
    조회 실패(추출 불가·네트워크 오류) 시 None."""
    if "msn.com" in url:
        return fetch_msn_published_at(url, log_prefix)
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"[{log_prefix}] 원문 페이지 조회 실패: {e}", file=sys.stderr)
        return None
    return parse_real_published_at(html)


# ── 한국어 제목 중복 판정 ─────────────────────────────────────────────────────
# 어절만으로는 조사·어미 변형에 뚫린다("매도" vs "매도와", "외인" vs "외국인").
# 같은 사건을 다른 언론사가 다시 쓴 제목은 어절이 절반도 안 겹치는 일이 흔해서,
# 문자 2-gram을 함께 본다. 임계는 실제 중복/비중복 쌍을 측정해 정했다(§29).

STOPWORDS = {
    "이슈", "뉴스", "기자", "오늘", "어제", "지난", "이번", "관련", "대한", "따른",
    "코스피", "코스닥", "주가", "주식", "시장", "장중", "장세", "상승", "하락",
    "전환", "반등", "급등", "급락", "강세", "약세", "회복", "마감",
}
BIGRAM_THRESHOLD = 0.40


def title_kw(title: str) -> set:
    return set(re.findall(r"[가-힣A-Za-z]{2,}", title)) - STOPWORDS


def title_bigrams(title: str) -> set:
    """제목의 문자 2-gram 집합. 조사·어미 변형에 강하다."""
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", title)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def is_dup_title(a: str, b: str, threshold: float = 0.55) -> bool:
    """두 제목이 같은 이슈를 가리키는지 판정한다 — 어절 겹침 **또는** 문자 2-gram 겹침.

    어절 단위 비교만으로는 한국어 재작성을 못 잡는다. 2026-07-30 실사고의 두 쌍은
    "외인 대규모 매도" vs "외국인 대규모 매도와", "이틀째" vs "이틀 연속"처럼 조사·어미만
    달라 어절 겹침이 0.29·0.33에 그쳤다(임계 0.55 미달 → 통과). 같은 쌍의 문자 2-gram
    겹침은 0.48·0.68로, 서로 다른 이슈(0.00~0.27)와 뚜렷이 갈린다.
    """
    wa, wb = title_kw(a), title_kw(b)
    if wa and wb and len(wa & wb) / min(len(wa), len(wb)) >= threshold:
        return True
    ga, gb = title_bigrams(a), title_bigrams(b)
    return bool(ga and gb) and len(ga & gb) / min(len(ga), len(gb)) >= BIGRAM_THRESHOLD
