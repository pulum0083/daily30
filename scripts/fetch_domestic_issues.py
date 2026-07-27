#!/usr/bin/env python3
# 코스피 아침 브리핑용 국내 이슈를 Google News RSS로 실수집하고 Gemini로 선별·요약하는 스크립트
"""국내 이슈 수집 (코스피 아침 브리핑 전용).

아침 브리핑의 검색 지시가 미국발에 쏠려 국내 소재가 0건으로 나오는 문제를 해결한다
(2026-07-27 진단: key_indicators 5건·catalysts 2건이 전부 미국발).

**구조 — §10에서 검증된 "RSS 실수집 → Gemini는 선별·요약만" 2단계 파이프라인:**

1. 한국어 Google News RSS로 국내 트랙(정책·금통위·수출입·공시·수급) 기사를 실수집한다.
2. 각 후보의 **실제 발행일시를 원문 페이지에서 재검증**한다 — Google News RSS의 `pubDate`는
   옛 기사를 재크롤링하며 현재 시각으로 다시 찍는 경우가 있어 신뢰하지 않는다(§10 방지 룰).
3. 검증된 기사만 Gemini에 넘겨 **선별·요약만** 시킨다. 날짜·URL·출처는 RSS 실데이터라
   Gemini가 생성할 수 없다.

수집 창은 **직전 코스피 마감 이후부터 지금까지** — 월요일이면 금요일 15:30부터 주말 전체다.
대상이 없으면 `issues: []`로 저장하고 섹션은 생략된다(운영 규칙 0 — 없으면 지어내지 않는다).

출력: data/domestic_issues.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytz

sys.path.insert(0, str(Path(__file__).parent))

from fetch_ib_korea_views import _HDR, _resolve_gnews_url, _verify_real_published_at

KST = pytz.timezone("Asia/Seoul")
ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "domestic_issues.json"

_GN_KR = "https://news.google.com/rss/search?hl=ko&gl=KR&ceid=KR:ko&q="

MAX_ITEMS = 4          # 화면에 싣는 최대 이슈 수
MAX_CANDIDATES = 24    # Gemini에 넘기기 전 후보 상한 (발행일 검증 비용 통제)
MAX_VERIFY = 12        # 원문 발행일 검증을 시도할 최대 건수

# 국내 트랙 — 아침 브리핑에 실릴 만한 소재군. 쿼리당 상위 몇 건만 본다.
QUERIES = [
    "금융통화위원회 기준금리 결정",
    "코스피 외국인 기관 수급",
    "정부 증시 정책 발표",
    "수출 통계 반도체",
    "코스피 상장사 공시 수주 계약",
    "한국은행 경제 전망",
    "코스닥 개인 투자자 순매수",
]


def _parse_rss_datetime(raw: str) -> datetime | None:
    """RSS pubDate → KST datetime. 실패 시 None."""
    try:
        return parsedate_to_datetime(raw).astimezone(KST)
    except Exception:
        return None


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s{2,}", " ", text).strip()


def collect_window(today) -> tuple[datetime, str]:
    """수집 창 시작 시각(직전 코스피 마감)과 사람이 읽는 라벨을 만든다."""
    try:
        from session_label import prev_kospi_session
        prev = prev_kospi_session(today)
    except Exception as e:
        print(f"[domestic] session_label 사용 불가, 24시간 창 사용: {e}", file=sys.stderr)
        prev = None
    if not prev:
        start = KST.localize(datetime.combine(today, datetime.min.time())) - timedelta(days=1)
        return start, "최근 24시간"
    # 직전 코스피 마감(15:30 KST) 이후
    start = KST.localize(datetime.combine(prev, datetime.min.time())).replace(hour=15, minute=30)
    return start, f"{prev} 코스피 마감 이후"


def fetch_candidates(start: datetime, now: datetime) -> list[dict]:
    """RSS로 후보 기사를 모은다. 이 단계의 pubDate는 정렬용일 뿐 채택 근거가 아니다."""
    seen_titles, cands = set(), []
    for q in QUERIES:
        try:
            req = urllib.request.Request(_GN_KR + urllib.parse.quote(q), headers=_HDR)
            with urllib.request.urlopen(req, timeout=12) as r:
                root = ET.fromstring(r.read())
        except Exception as e:
            print(f"[domestic] RSS 실패 ({q}): {e}", file=sys.stderr)
            continue
        for item in list(root.iter("item"))[:6]:
            title = _clean(item.findtext("title") or "")
            if not title or title in seen_titles:
                continue
            pub = _parse_rss_datetime(item.findtext("pubDate") or "")
            if not pub or not (start <= pub <= now + timedelta(hours=1)):
                continue
            src_el = item.find("source")
            seen_titles.add(title)
            cands.append({
                "title": title,
                "desc": _clean(item.findtext("description") or "")[:200],
                "link": (item.findtext("link") or "").strip(),
                "source": (src_el.text or "").strip() if src_el is not None else "",
                "rss_pub": pub,
                "query": q,
            })
    cands.sort(key=lambda c: c["rss_pub"], reverse=True)
    return cands[:MAX_CANDIDATES]


def verify_candidates(cands: list[dict], start: datetime, now: datetime) -> list[dict]:
    """원문 URL을 리졸브해 **실제 발행일시**가 수집 창 안인지 재검증한다.

    §10 방지 룰: Google News RSS의 pubDate는 재크롤링으로 현재 시각이 다시 찍힐 수 있어
    최종 판정에 쓰지 않는다. 실제 발행일 추출에 실패하면 그 후보는 **버린다**(표시하지 않는다).
    """
    out = []
    for c in cands[:MAX_VERIFY]:
        url = _resolve_gnews_url(c["link"]) if c["link"] else ""
        if not url:
            continue
        real = _verify_real_published_at(url)
        if not real:
            print(f"[domestic] 발행일 검증 불가 → 제외: {c['title'][:40]}", file=sys.stderr)
            continue
        real_kst = real.astimezone(KST)
        if not (start <= real_kst <= now + timedelta(hours=1)):
            print(f"[domestic] 창 밖({real_kst:%m-%d %H:%M}) → 제외: {c['title'][:40]}",
                  file=sys.stderr)
            continue
        out.append({**c, "url": url, "published_at": real_kst.strftime("%Y-%m-%d %H:%M")})
        if len(out) >= MAX_ITEMS * 2:
            break
    return out


_SUMMARY_PROMPT = """\
아래는 {window_label} 국내에서 실제로 발행된 경제·증시 기사 목록이다.
오늘({today}) 코스피 개장(09:00)에 영향을 줄 만한 국내 이슈를 최대 {n}건 골라 요약해줘.

[규칙]
- **목록에 있는 기사만 사용한다.** 목록에 없는 사건을 추가하지 않는다.
- 각 항목의 `idx`는 아래 목록의 번호를 그대로 쓴다. 없는 번호를 만들지 않는다.
- `summary`는 1~2문장, **해요체**로 끝낸다(예: "~했어요", "~로 보여요").
- **제목·요약에 실제로 있는 수치만 쓴다.** 지수 레벨·등락률·목표가를 추측해 쓰지 않는다.
- 미국·해외 단독 소재는 제외한다(국내 정책·수급·기업·지표 중심).
- 서로 같은 사건의 중복 보도는 하나로 합친다.
- 고를 만한 게 없으면 빈 배열 []을 반환한다. 억지로 채우지 않는다.

[기사 목록]
{articles}

출력 형식 (JSON만, 다른 텍스트 없이):
{{"issues": [{{"idx": 0, "title": "짧은 제목", "summary": "해요체 1~2문장"}}]}}
"""


def summarize(items: list[dict], window_label: str, today: str) -> list[dict]:
    """Gemini는 선별·요약만 한다 — 날짜·URL·출처는 RSS 실데이터를 그대로 쓴다."""
    if not items:
        return []
    try:
        from google import genai
        from google.genai import types
        from fetch_news import get_gemini_api_key
    except ImportError as e:
        print(f"[domestic] Gemini 사용 불가: {e}", file=sys.stderr)
        return []

    listing = "\n".join(
        f"{i}. [{it['published_at']}] {it['title']} — {it['desc'][:120]}"
        for i, it in enumerate(items)
    )
    prompt = _SUMMARY_PROMPT.format(
        window_label=window_label, today=today, n=MAX_ITEMS, articles=listing
    )
    try:
        client = genai.Client(api_key=get_gemini_api_key())
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=900),
        )
        raw = (resp.text or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        picked = json.loads(m.group(0))["issues"] if m else []
    except Exception as e:
        print(f"[domestic] Gemini 요약 실패: {e}", file=sys.stderr)
        return []

    out = []
    for p in picked[:MAX_ITEMS]:
        idx = p.get("idx")
        if not isinstance(idx, int) or not (0 <= idx < len(items)):
            print(f"[domestic] 잘못된 idx {idx} → 제외", file=sys.stderr)
            continue
        src = items[idx]
        out.append({
            "title": (p.get("title") or src["title"])[:80],
            "summary": (p.get("summary") or "").strip(),
            "source": src["source"],
            "url": src["url"],
            "published_at": src["published_at"],
        })
    return out


_STOP_RE = re.compile(r"[^가-힣A-Za-z0-9]+")


def _key_tokens(text: str) -> set:
    """제목에서 비교용 토큰 집합을 만든다(조사·기호 제거는 하지 않고 2글자 이상만)."""
    return {t for t in _STOP_RE.split(text or "") if len(t) >= 2}


def _norm(text: str) -> str:
    """따옴표·구두점을 제거한 비교용 문자열 (토큰 경계 흔들림에 강하다)."""
    return _STOP_RE.sub("", text or "")


def dedupe_issues(issues: list[dict], threshold: float = 0.25,
                  seq_threshold: float = 0.5) -> list[dict]:
    """같은 사건의 중복 보도를 제거한다.

    2026-07-27 실사고: "한은 8월 기준금리 인상" 한 사건을 서로 다른 매체가 낸 기사 3건이
    그대로 3개 이슈로 실렸다. 프롬프트로 "중복은 합쳐라"라고 지시해도 지켜지지 않아
    결정론 게이트를 최종 방어선으로 둔다(§22·§24 교훈).
    제목 토큰의 자카드 유사도가 threshold 이상이면 뒤에 온 항목을 버린다(앞선 항목이 더 최신).

    **두 신호를 OR로 본다** — 토큰 자카드만으로는 취약하다. 실측에서 같은 사건인데도
    따옴표 위치가 바뀌며 "성장에"/"성장"으로 토큰이 갈려 유사도가 0.20까지 떨어졌다.
    구두점을 제거한 문자열 유사도(SequenceMatcher)를 함께 보면 이 경계 흔들림에 강하다.

    임계값은 실사고 데이터에서 역산했다. 낮게 잡은 대가로 표현이 비슷한 별개 사건이
    합쳐질 수 있으나(예: "정부 반도체 지원 대책" vs "정부 배터리 지원 대책"),
    **중복 3건을 그대로 싣는 것보다 1건 덜 싣는 쪽이 낫다.**
    """
    from difflib import SequenceMatcher

    out = []
    for it in issues:
        title = it.get("title", "")
        toks, norm = _key_tokens(title), _norm(title)
        dup = False
        for kept in out:
            kt = kept.get("title", "")
            k, knorm = _key_tokens(kt), _norm(kt)
            jac = len(toks & k) / len(toks | k) if (toks and k) else 0.0
            seq = SequenceMatcher(None, norm, knorm).ratio() if (norm and knorm) else 0.0
            if jac >= threshold or seq >= seq_threshold:
                print(f"[domestic] 중복 제거(자카드 {jac:.2f} / 문자열 {seq:.2f}): {title[:40]}",
                      file=sys.stderr)
                dup = True
                break
        if not dup:
            out.append(it)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="코스피 아침 브리핑용 국내 이슈 수집")
    ap.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    args = ap.parse_args()

    now = datetime.now(KST)
    today = now.date()
    start, window_label = collect_window(today)
    print(f"[domestic] 수집 창: {start:%Y-%m-%d %H:%M} ~ {now:%Y-%m-%d %H:%M} ({window_label})")

    cands = fetch_candidates(start, now)
    print(f"[domestic] RSS 후보 {len(cands)}건")
    verified = verify_candidates(cands, start, now)
    print(f"[domestic] 발행일 검증 통과 {len(verified)}건")
    issues = dedupe_issues(summarize(verified, window_label, today.isoformat()))
    print(f"[domestic] 최종 채택 {len(issues)}건")

    payload = {
        "date": today.isoformat(),
        "window": {"from": start.strftime("%Y-%m-%d %H:%M"), "label": window_label},
        "issues": issues,
        "generated_at": now.isoformat(),
    }
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[domestic] Saved → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
