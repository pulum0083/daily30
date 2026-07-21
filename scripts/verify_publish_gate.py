# 발행 전 SEO 메타·JSON-LD·sitemap 게이트 — STOCKS_SERVICE_RULES §9 검증 기준을 코드로 강제한다
"""2026-07-21: 종목 상세 46개가 description·canonical·OG·JSON-LD를 하나도 갖지 않은 채
발행되고 있었다. §9 발행 전 검증 기준 4번이 문서상 체크리스트로만 존재해 아무도 못 잡았다.

두 겹으로 막는다.

1. **쓰기 시점 차단** — `gate_write()`가 위반한 HTML은 파일로 쓰지 않는다. 직전 정상본이 남으므로
   깨진 페이지가 발행되는 일 자체가 없다(운영 규칙 0: 구식이지만 정상 > 최신이지만 깨짐).
2. **CI 실패** — 이 파일을 직접 실행하면 발행본 전수를 감사하고 위반 시 exit 1.
   `.github/workflows/ci.yml`이 push·PR마다 돌린다.

일간 잡의 종목 페이지 생성 스텝은 `continue-on-error: true`를 유지한다(§21 — 종목 서비스
작업이 마감 브리핑 발행을 막지 않는다). 게이트가 걸려도 로그와 CI 양쪽에 흔적이 남는다.
"""

import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
CONFIG_DIR = Path(__file__).resolve().parent / "config"
SITE_BASE = "https://doubleshot.space"

MIN_DESC_LEN = 20  # 이보다 짧으면 검색 결과에 쓸모없는 스니펫이라 누락으로 본다


def _head(html: str) -> str:
    return html.split("</head>")[0]


def _meta(head: str, attr: str, value: str):
    """<meta {attr}="{value}" content="..."> 의 content를 반환. 없으면 None."""
    m = re.search(
        r'<meta\s+[^>]*%s=["\']%s["\'][^>]*content=["\']([^"\']*)["\']' % (attr, re.escape(value)),
        head,
        re.I,
    )
    return m.group(1) if m else None


def check_html(html: str, url: str) -> list:
    """페이지 1개의 발행 적격성을 검사해 위반 목록을 반환한다. 빈 리스트면 통과."""
    errs = []
    head = _head(html)

    title = re.search(r"<title>(.*?)</title>", head, re.S)
    if not title or not title.group(1).strip():
        errs.append("<title> 없음/빈 값")

    desc = _meta(head, "name", "description")
    if not desc:
        errs.append("meta description 없음")
    elif len(desc) < MIN_DESC_LEN:
        errs.append(f"meta description 너무 짧음({len(desc)}자)")

    if not _meta(head, "name", "robots"):
        errs.append("meta robots 없음")

    canon = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']', head, re.I)
    if not canon:
        errs.append("link canonical 없음")
    elif canon.group(1) != url:
        errs.append(f"canonical 불일치: {canon.group(1)} != {url}")

    og_url = _meta(head, "property", "og:url")
    if not og_url:
        errs.append("og:url 없음")
    elif og_url != url:
        errs.append(f"og:url 불일치: {og_url} != {url}")

    if not _meta(head, "property", "og:title"):
        errs.append("og:title 없음")
    og_desc = _meta(head, "property", "og:description")
    if not og_desc or len(og_desc) < MIN_DESC_LEN:
        errs.append("og:description 없음/너무 짧음")
    og_img = _meta(head, "property", "og:image")
    if not og_img or not og_img.startswith("https://"):
        errs.append("og:image 없음/절대 URL 아님")
    if not _meta(head, "name", "twitter:card"):
        errs.append("twitter:card 없음")

    # JSON-LD — 파싱조차 안 되는 블록은 구글이 통째로 버린다. 있는 척만 하는 상태를 막는다.
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', head, re.S)
    if not blocks:
        errs.append("JSON-LD 없음")
    types = []
    for i, b in enumerate(blocks):
        try:
            obj = json.loads(b.replace("<\\/", "</"))
        except json.JSONDecodeError as e:
            errs.append(f"JSON-LD[{i}] 파싱 실패: {e}")
            continue
        if not obj.get("@type"):
            errs.append(f"JSON-LD[{i}] @type 없음")
        types.append(obj.get("@type"))
    if blocks and "BreadcrumbList" not in types:
        errs.append("BreadcrumbList JSON-LD 없음")

    # §9 검증 기준 3번 — /v2/ 경로는 완전 삭제됨(SERVICE_RULES §3)
    if "/v2/" in html:
        errs.append("/v2/ 경로 발견")

    return errs


def gate_write(out_path: Path, html: str, url: str) -> list:
    """게이트를 통과한 HTML만 파일로 쓴다.

    위반 시 **쓰지 않고** 위반 목록을 반환한다 — 직전 정상본이 그대로 남는다.
    호출부는 반환값이 비어 있지 않으면 그 페이지를 실패로 집계하고, 실행 끝에 exit 1 해야 한다.
    """
    errs = check_html(html, url)
    if errs:
        print(f"::error::[발행 게이트] {url} 차단 — {'; '.join(errs)}", file=sys.stderr)
        return errs
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return []


# ── 발행본 전수 감사 (CI · 수동 점검용) ─────────────────────────────────────


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def published_pages() -> list:
    """감사 대상 (경로, URL) 목록. 생성기가 만드는 페이지만 본다 — 수기 페이지는 대상 밖."""
    pages = []
    for s in _load(CONFIG_DIR / "stocks.json"):
        p = WEB_DIR / "stocks" / s["code"] / "index.html"
        if p.exists():
            pages.append((p, f"{SITE_BASE}/stocks/{s['code']}/"))
    for s in _load(CONFIG_DIR / "us_stocks.json"):
        tk = s["ticker"].lower()
        p = WEB_DIR / "stocks" / "us" / tk / "index.html"
        if p.exists():
            pages.append((p, f"{SITE_BASE}/stocks/us/{tk}/"))
    universe = CONFIG_DIR / "stock_universe.json"
    if universe.exists():
        for key in _load(universe).get("sectors", {}):
            p = WEB_DIR / "stocks" / "sector" / key / "index.html"
            if p.exists():
                pages.append((p, f"{SITE_BASE}/stocks/sector/{key}/"))
    return pages


def check_sitemap(urls) -> list:
    """생성된 페이지가 sitemap.xml에 전부 들어갔는지 검사한다.

    섹터 8개가 생성만 되고 sitemap에 빠져 색인 경로 자체가 없던 사고(2026-07-21)를 고정한다.
    """
    sm = WEB_DIR / "sitemap.xml"
    if not sm.exists():
        return ["sitemap.xml 없음"]
    locs = set(re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8")))
    return [f"sitemap 누락: {u}" for u in urls if u not in locs]


def audit() -> int:
    pages = published_pages()
    if not pages:
        print("::error::[발행 게이트] 감사 대상 페이지가 0건 — 생성이 통째로 실패했는지 확인할 것")
        return 1

    violations = 0
    for path, url in pages:
        errs = check_html(path.read_text(encoding="utf-8"), url)
        if errs:
            violations += 1
            print(f"::error file={path.relative_to(BASE_DIR)}::{url} — {'; '.join(errs)}")

    for err in check_sitemap([u for _, u in pages]):
        violations += 1
        print(f"::error::{err}")

    if violations:
        print(f"\n❌ 발행 게이트 위반 {violations}건 / 검사 {len(pages)}페이지")
        return 1
    print(f"✅ 발행 게이트 통과 — {len(pages)}페이지 (메타 5종·JSON-LD·canonical·sitemap)")
    return 0


if __name__ == "__main__":
    sys.exit(audit())
