# 종목별 관련 뉴스를 RSS로 수집해 요약·썸네일을 붙여 위젯용 JSON을 만드는 스크립트
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


def _strip_tags(text):
    return _TAG.sub("", text).strip()


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
        if pub_date:
            try:
                dt = parsedate_to_datetime(pub_date).astimezone(KST)
                now = datetime.now(KST)
                time_label = dt.strftime("%H:%M") if dt.date() == now.date() else "어제"
            except (TypeError, ValueError):
                time_label = ""

        items.append({
            "title": _strip_tags(fields["title"]),
            "url": fields["url"],
            "time": time_label,
            "source": _strip_tags(fields["source"]),
        })
    return items


def merge(old, new):
    old_by_url = {o["url"]: o for o in old}
    merged = []
    todo = []
    for item in new[:MAX_ITEMS]:
        prev = old_by_url.get(item["url"])
        if prev and prev.get("summary"):
            merged.append({
                "url": item["url"],
                "title": item["title"],
                "time": item["time"],
                "source": item["source"],
                "summary": prev["summary"],
                "thumb": prev.get("thumb"),
            })
        else:
            merged.append({
                "url": item["url"],
                "title": item["title"],
                "time": item["time"],
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
