# 종목별 관련 뉴스를 RSS로 수집해 요약·썸네일을 붙여 위젯용 JSON을 만드는 스크립트
import html
import json
import os
import re
import sys
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

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
)

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
# 도메인 표기 출처(v.daum.net 등)를 실제 언론사명으로 복구할 때 쓰는 og:site_name 패턴.
_OG_SITE_NAME = re.compile(
    r'<meta[^>]+property=["\']og:site_name["\'][^>]*content=["\']([^"\']+)["\']'
    r'|<meta[^>]+content=["\']([^"\']+)["\'][^>]*property=["\']og:site_name["\']',
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


def extract_og_site_name(html):
    m = _OG_SITE_NAME.search(html)
    if not m:
        return None
    return m.group(1) or m.group(2)


def get_gemini_api_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        cfg_path = ROOT / "config.json"
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                key = cfg.get("gemini", {}).get("api_key", "")
            except Exception:
                key = ""
    return key


def build_prompt(name, items):
    lines = "\n".join(
        f"{i + 1}. {it['title']} ({it.get('source', '')})"
        for i, it in enumerate(items)
    )
    return (
        f"다음은 '{name}' 관련 뉴스 제목 목록이에요. 각 제목을 투자자에게 보여줄 "
        "한 문장 요약으로 바꿔주세요.\n\n"
        f"[제목 목록]\n{lines}\n\n"
        "[작성 규칙]\n"
        "- 모든 문장을 반드시 해요체로 끝내요 (예: '~해요', '~이에요', '~보여요').\n"
        "- '~습니다', '~됩니다' 같은 합쇼체는 절대 쓰지 마세요.\n"
        "- 각 요약은 60자 이내로 작성해요.\n"
        "- 제목에 없는 숫자·날짜·목표가는 새로 만들지 마세요.\n"
        "- 제목과 같은 순서로, 제목 개수와 동일한 개수만큼 작성해요.\n\n"
        "[출력 형식]\n"
        '다른 설명 없이 JSON 배열만 출력해요. 예: ["요약1", "요약2"]'
    )


def summarize(name, items):
    # todo가 비어 있으면(대부분의 폴링) Gemini를 호출하지 않는다 — 비용 모델의 핵심.
    if not items:
        return []

    key = get_gemini_api_key()
    if not key:
        print("[fetch_stock_news] GEMINI_API_KEY 없음 — 요약 생략", file=sys.stderr)
        return []

    prompt = build_prompt(name, items)
    payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    url = GEMINI_URL.format(model=GEMINI_MODEL, key=key)
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            raise ValueError("응답에서 JSON 배열을 찾을 수 없음")
        arr = json.loads(m.group(0))
        return [str(s) for s in arr]
    except Exception as e:
        print(f"[fetch_stock_news] Gemini 요약 실패: {e}", file=sys.stderr)
        return []


def apply_summaries(merged, todo, summaries):
    # todo·summaries 개수가 어긋나도(짧게/길게 와도) zip이 짧은 쪽에 맞춰 멈추므로 안전하다.
    for item, summary in zip(todo, summaries):
        for m in merged:
            if m["url"] == item["url"]:
                m["summary"] = summary
                break


_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"


def _extract_resolved_gnews_url(raw):
    # batchexecute 응답(garturlres)에서 실제 원문 URL을 복원한다.
    # 쿼리스트링의 =·& 는 \uXXXX로 이중 이스케이프되므로 반드시 복원 후 반환한다.
    if "garturlres" not in raw:
        return None
    seg = raw.split("garturlres", 1)[1]
    m = re.search(r'"(https?://.*?)\\*"', seg)
    if not m:
        return None
    url = m.group(1)
    url = re.sub(r"\\+u([0-9a-fA-F]{4})", lambda mm: chr(int(mm.group(1), 16)), url)
    return url.replace("\\/", "/")


def _resolve_gnews_url(link):
    # 구글 뉴스 RSS의 <link>는 실제 기사 페이지가 아니라 구글 뉴스 인터스티셜 리다이렉트다.
    # 이 상태로 fetch하면 og:site_name이 항상 "Google News"로 나와 발행사명을 복구할 수 없다.
    # 실패 시 원래 link를 그대로 반환한다 — 호출부가 리다이렉트 페이지로 폴백해서 처리한다.
    if "/rss/articles/" not in link:
        return link
    try:
        art = link.split("/articles/")[1].split("?")[0]
        req = urllib.request.Request(link, headers=UA)
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
            headers={**UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        with urllib.request.urlopen(req2, timeout=12) as r:
            raw = r.read().decode("utf-8", "ignore")
        return _extract_resolved_gnews_url(raw) or link
    except Exception:
        return link


def enrich_new_items(merged, todo):
    by_url = {m["url"]: m for m in merged}
    for item in todo:
        m = by_url.get(item["url"])
        if not m:
            continue

        fetch_url = _resolve_gnews_url(item["url"])
        try:
            page = _fetch(fetch_url)
        except Exception as e:
            print(f"[fetch_stock_news] 기사 페이지 조회 실패 ({item['url']}): {e}", file=sys.stderr)
            continue

        m["thumb"] = extract_og_image(page)

        # 도메인처럼 보이는 출처만 복구한다 — 멀쩡한 한글 언론사명은 절대 덮어쓰지 않는다.
        if _is_domain_like(m["source"]):
            site_name = extract_og_site_name(page)
            # 리졸브 실패로 여전히 구글 뉴스 인터스티셜이면 site_name이 "Google News"로 나온다 —
            # 그건 발행사명이 아니므로 승격하지 않는다.
            if site_name and site_name != "Google News":
                m["source"] = site_name


def main():
    now = datetime.now(KST)

    prev_data = {}
    if OUT_JSON.exists():
        try:
            prev_data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[fetch_stock_news] 기존 데이터 로드 실패: {e}", file=sys.stderr)
    prev_stocks = prev_data.get("stocks", {})

    result_stocks = {}
    for code, name in STOCKS.items():
        prev_items = prev_stocks.get(code, [])
        try:
            xml = _fetch(RSS_URL.format(q=urllib.parse.quote(name)))
            new_items = parse_rss(xml)
        except Exception as e:
            # RSS 수집 실패 시 빈 목록으로 덮어쓰지 않는다 — 기존 데이터를 그대로 보존한다.
            print(f"[fetch_stock_news] {name} RSS 수집 실패, 기존 데이터 유지: {e}", file=sys.stderr)
            result_stocks[code] = prev_items
            continue

        merged, todo = merge(prev_items, new_items)
        enrich_new_items(merged, todo)
        summaries = summarize(name, todo)
        apply_summaries(merged, todo, summaries)
        result_stocks[code] = merged

        newly_summarized = min(len(todo), len(summaries))
        print(f"[fetch_stock_news] {name}: {len(merged)}건, 신규 요약 {newly_summarized}건")

    data = {"updated_at": now.isoformat(), "stocks": result_stocks}

    # 브라우저가 이 파일을 직접 fetch하므로 절반만 써진 상태를 절대 노출하지 않는다.
    tmp_path = OUT_JSON.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, OUT_JSON)
    print(f"[fetch_stock_news] Saved → {OUT_JSON}")


if __name__ == "__main__":
    main()
