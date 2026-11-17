# 브리핑 페이지의 제목·설명·구조화 데이터(SEO 머리)와 공유 카드 태그 정리

import html
import re
from datetime import datetime, date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prediction_basis import OPEN as BASIS_OPEN
from html_common import BRIEFING_LABELS, KST, SITE_BASE, _breadcrumb, _jsonld
from sections_shared import build_prediction


# ── 렌더 ──────────────────────────────────────────────────────────────────────
# 브리핑 <title>·description(2026-10-27). 검색에 나오는 줄이라 사람들이 찾는 말(검색어)을 앞에,
# 그날 헤드라인을 뒤에 둔다. 새 발행(render_briefing)과 발행본 일괄 교체(backfill_briefing_heads)가
# 같은 함수를 쓴다 — 두 곳이 어긋나지 않게.
SEO_TITLE_PREFIX = {"close": "코스피 마감 시황", "us": "미국 증시 전망"}
# 검색 결과에 보이는 한글 이름 — 영문 "Double-Shot"만 있으면 "더블샷"으로 찾는 사람에게 걸리지 않는다(2026-11-13).
BRAND_KO = "더블샷"


def _plain_text(s) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip() if isinstance(s, str) else ""


def briefing_head(analysis: dict, btype: str, target_date: str) -> dict:
    """{"title", "description"} — HTML에 그대로 넣을 수 있게 이스케이프한 값."""
    analysis = analysis or {}
    dt = date.fromisoformat(target_date)
    day = f"{dt.month}월 {dt.day}일"
    if btype == "kospi":
        # 시초가 기준(§57)이 아닌 옛 예측은 '시초가'라고 쓰지 않는다
        is_open = (analysis.get("prediction") or {}).get("basis") == BASIS_OPEN
        prefix = "코스피 시초가 예측" if is_open else "코스피 방향 예측"
    else:
        prefix = SEO_TITLE_PREFIX[btype]
    tv = analysis.get("todays_view") or {}
    headline = next((t for t in map(_plain_text, (tv.get("view_title"), analysis.get("reason_title"),
                                                  analysis.get("market_title"))) if t), "")
    dek = next((t for t in map(_plain_text, (tv.get("dek"), analysis.get("dek"),
                                             analysis.get("sc_summary"))) if t), "")
    title = f"{prefix} {day} | {headline} | {BRAND_KO}" if headline else f"{prefix} {day} | {BRAND_KO}"
    parts = []
    if btype == "kospi" and analysis.get("prediction"):
        p = build_prediction(analysis, "KOSPI", "KOSPI 당일 방향 예측", "")
        parts.append(f"{p['pred_title']}: {p['direction']} {p['readout_pct']}% · 신뢰도 {p['confidence']}%")
    parts.append(dek or headline or f"{target_date} {BRIEFING_LABELS[btype]} 브리핑")
    return {"title": html.escape(title), "description": html.escape(". ".join(parts)),
            "headline": headline, "prefix": f"{prefix} {day}"}


def _iso_kst(generated_at: str, target_date: str) -> str:
    """발행 시각을 시간대가 붙은 ISO로. 못 읽으면 그 날짜 자정 KST."""
    try:
        dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = KST.localize(dt)
        return dt.isoformat(timespec="seconds")
    except Exception:
        return f"{target_date}T00:00:00+09:00"


def briefing_jsonld(head: dict, btype: str, target_date: str, generated_at: str, canonical_url: str) -> list:
    """브리핑 구조화 데이터 — 기사(NewsArticle)·경로(BreadcrumbList). 숫자는 넣지 않는다(제목·시각·주소만).
    image는 맨 끝에 둔다 — 공유 카드를 못 만들면 strip_og_image가 이 항목도 지운다."""
    published = _iso_kst(generated_at, target_date)
    article = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": (head.get("headline") or head.get("prefix") or "")[:110],
        "alternativeHeadline": head.get("prefix", ""),
        "datePublished": published, "dateModified": published,
        "inLanguage": "ko-KR",
        "mainEntityOfPage": canonical_url,
        "author": {"@type": "Organization", "name": BRAND_KO, "alternateName": "Double-Shot", "url": f"{SITE_BASE}/about/"},
        "publisher": {"@type": "Organization", "name": BRAND_KO, "alternateName": "Double-Shot",
                      "logo": {"@type": "ImageObject", "url": f"{SITE_BASE}/icons/icon-512.png"}},
        "image": f"{canonical_url}og.png",
    }
    crumb = _breadcrumb([("홈", "/stocks/"), ("브리핑", "/briefings/"),
                         (head.get("prefix") or BRIEFING_LABELS.get(btype, ""), None)])
    return [_jsonld(article), _jsonld(crumb)]


def strip_og_image(html: str) -> str:
    """공유 카드를 못 만든 페이지에서 og:image·twitter:image를 지운다 — 없는 이미지를 가리키지 않게."""
    html = re.sub(r'<meta (?:property="og:image"|name="twitter:image") content="[^"]*">\n?', "", html)
    html = re.sub(r',"image":"[^"]*og\.png"', "", html)   # 구조화 데이터의 공유 카드 주소도 지운다
    return html.replace('<meta name="twitter:card" content="summary_large_image">',
                        '<meta name="twitter:card" content="summary">')
