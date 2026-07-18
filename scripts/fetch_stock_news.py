# 종목별 관련 뉴스를 RSS로 수집해 요약·썸네일을 붙여 위젯용 JSON을 만드는 스크립트
import html
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "web" / "data" / "stock-news.json"
STOCKS = {"005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차"}
MAX_ITEMS = 5
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
RSS_URL = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"

_TAG = re.compile(r"<[^>]+>")
_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_FIELD = {
    "title": re.compile(r"<title>(.*?)</title>", re.S),
    "url": re.compile(r"<link>(.*?)</link>", re.S),
    "pubDate": re.compile(r"<pubDate>(.*?)</pubDate>", re.S),
    "source": re.compile(r"<source[^>]*>(.*?)</source>", re.S),
}
_OG_IMAGE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
    re.I,
)


# 승격 대상으로 인정할 언론사명 최대 길이 — 이보다 길면 제목 일부로 보고 건드리지 않는다.
_MAX_SOURCE_LEN = 20


# 뉴스가 아닌 UGC 플랫폼 출처 — 언론사가 아니라 플랫폼만 제외한다.
_UGC_SOURCES = {
    "네이버블로그", "naverblog", "blog.naver.com",
    "네이버포스트", "naverpost", "post.naver.com",
    "네이버카페", "navercafe", "cafe.naver.com",
    "다음카페", "daumcafe", "cafe.daum.net",
    "티스토리", "tistory", "tistory.com",
    "브런치", "brunch", "brunch.co.kr",
    "벨로그", "velog", "velog.io",
}


def _strip_tags(text):
    # 태그를 먼저 지운 뒤 엔티티를 복원한다 — 순서가 반대면 &lt;script&gt;가 진짜 태그가 된다.
    return html.unescape(_TAG.sub("", text).strip()).strip()


def _is_ugc_source(source):
    # 부분 일치는 쓰지 않는다 — "OO포스트" 같은 실제 언론사를 잘못 걸러낼 수 있다.
    return source.replace(" ", "").lower() in _UGC_SOURCES


def _is_domain_like(source):
    # 공백 없이 점을 포함하거나 전부 로마자면 도메인·영문 표기로 본다.
    if not source or " " in source:
        return False
    return "." in source or source.isascii()


def _clean_title(title, source):
    # 구글 뉴스는 제목 끝에 " - 언론사"를 붙이고, 같은 이름이 두 번 붙는 경우도 있다.
    if source:
        suffix = " - " + source
        while title.endswith(suffix):
            title = title[: -len(suffix)].strip()

    # source가 도메인·로마자면 제목에 남은 한글 언론사명을 출처로 승격한다.
    if _is_domain_like(source):
        head, sep, tail = title.rpartition(" - ")
        candidate = tail.strip()
        if sep and candidate and len(candidate) <= _MAX_SOURCE_LEN \
                and not any(c.isdigit() for c in candidate):
            return head.strip(), candidate

    return title, source


def _fetch(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_rss(xml):
    items = []
    for block in _ITEM.findall(xml):
        fields = {}
        for name, pattern in _FIELD.items():
            m = pattern.search(block)
            fields[name] = m.group(1).strip() if m else ""

        pub_date = fields["pubDate"]
        time_label = ""
        published = ""
        if pub_date:
            try:
                dt = parsedate_to_datetime(pub_date).astimezone(KST)
                # 경과 시간이 아니라 KST 달력 날짜로 비교한다 — 어제 23:50은 "어제"다.
                days = (datetime.now(KST).date() - dt.date()).days
                if days == 0:
                    time_label = dt.strftime("%H:%M")
                elif days == 1:
                    time_label = "어제"
                else:
                    time_label = f"{dt.month}/{dt.day}"
                published = dt.isoformat()
            except (TypeError, ValueError):
                time_label = ""
                published = ""

        title, source = _clean_title(
            _strip_tags(fields["title"]), _strip_tags(fields["source"])
        )
        # 최신 5건을 자르기 전에 걸러야 빈 자리가 다음 기사로 채워진다.
        if _is_ugc_source(source):
            continue
        items.append({
            "title": title,
            "url": fields["url"],
            "time": time_label,
            "published": published,
            "source": source,
        })

    # 구글 뉴스 피드 순서는 발행 시각순이 아니다 — 실제 발행 시각으로 다시 정렬한다.
    return _sort_by_published(items)


def _sort_by_published(items):
    # 발행 시각을 못 읽은 항목은 순위를 매길 수 없으므로 버리지 않고 맨 뒤로 보낸다.
    return sorted(
        items,
        key=lambda i: (bool(i.get("published")), i.get("published") or ""),
        reverse=True,
    )


def merge(old, new):
    old_by_url = {o["url"]: o for o in old}
    merged = []
    todo = []
    # 피드 순서가 아니라 실제 발행 시각 기준 최신 5건을 고른다.
    for item in _sort_by_published(new)[:MAX_ITEMS]:
        prev = old_by_url.get(item["url"])
        if prev and prev.get("summary"):
            merged.append({
                "url": item["url"],
                "title": item["title"],
                "time": item["time"],
                "published": item.get("published", ""),
                "source": item["source"],
                "summary": prev["summary"],
                "thumb": prev.get("thumb"),
            })
        else:
            merged.append({
                "url": item["url"],
                "title": item["title"],
                "time": item["time"],
                "published": item.get("published", ""),
                "source": item["source"],
                "summary": "",
                "thumb": None,
            })
            todo.append(item)
    return merged, todo


def extract_og_image(html):
    m = _OG_IMAGE.search(html)
    if not m:
        return None
    return m.group(1) or m.group(2)
