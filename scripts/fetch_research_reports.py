#!/usr/bin/env python3
# 네이버 금융 리서치(시황정보)에서 당일 국내 증권사 시황 리포트를 수집·요약하는 스크립트
"""
Usage:
    python3 scripts/fetch_research_reports.py

출력: data/research_reports.json
  - 당일(KST) 발행된 "국내 시황" 리포트만 (미국/글로벌/전일자 제목 제외)
  - 증권사당 1건, 최대 3건
  - Gemini 요약(해요체 1~2문장, 지수·등락률 등 숫자 절대 금지) — 숫자 잔존 시 해당 건 폐기
  - 대상 리포트가 없으면 빈 배열 (섹션 자체 생략, 파이프라인 보호)
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pytz

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
KST = pytz.timezone("Asia/Seoul")

sys.path.insert(0, str(BASE_DIR / "scripts"))
from fetch_news_live import get_gemini_api_key  # noqa: E402

_HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}
LIST_URL = "https://finance.naver.com/research/market_info_list.naver"
READ_URL = "https://finance.naver.com/research/market_info_read.naver?nid={nid}&page=1"

_KW = re.compile(r"코스피|KOSPI|국내|마감|증시|시장|마켓|전략", re.I)
_EXCL = re.compile(r"미국|글로벌|Global|Carbon|해외", re.I)
_NUM_LEAK = re.compile(r"\d+\.?\d*\s*%|\d{3,4}\.?\d*\s*p\b|\d,\d{3}")
MAX_REPORTS = 3


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=_HDR)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return resp.read().decode("euc-kr", errors="ignore")


def _list_today(today: str) -> list[dict]:
    """당일 국내 시황 리포트 후보를 증권사당 1건, 최대 MAX_REPORTS건 반환한다."""
    try:
        html = _get(LIST_URL)
    except Exception as e:
        print(f"[research_reports] list fetch failed: {e}", file=sys.stderr)
        return []
    rows = re.findall(
        r'market_info_read\.naver\?nid=(\d+)[^"]*"[^>]*>([^<]+)</a>.*?'
        r'<td[^>]*>\s*([^<]+?)\s*</td>.*?(\d{2}\.\d{2}\.\d{2})',
        html, re.DOTALL,
    )
    import html as _html
    today_short = today[2:].replace("-", ".")  # "2026-07-02" -> "26.07.02"
    _, today_mm, today_dd = (int(x) for x in today.split("-"))
    _ymd_pat = re.compile(r"(\d{2})\.(\d{2})\.(\d{2})")
    _md_pat = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)")
    seen_firm, picks = set(), []
    for nid, title, firm, date in rows:
        if date != today_short:
            continue
        title = _html.unescape(title.strip())
        firm = firm.strip()
        if not _KW.search(title) or _EXCL.search(title):
            continue
        # 제목에 박힌 날짜(YY.MM.DD 또는 M/D 표기)가 당일과 다르면(전일자 내용 재게시) 제외
        stale = False
        for mm, dd in [m.groups()[1:] for m in _ymd_pat.finditer(title)]:
            if (int(mm), int(dd)) != (today_mm, today_dd):
                stale = True
        for mm, dd in [m.groups() for m in _md_pat.finditer(title)]:
            if (int(mm), int(dd)) != (today_mm, today_dd):
                stale = True
        if stale:
            continue
        if firm in seen_firm:
            continue
        seen_firm.add(firm)
        picks.append({"nid": nid, "title": title, "firm": firm})
        if len(picks) >= MAX_REPORTS:
            break
    return picks


def _body_text(nid: str) -> str:
    try:
        html = _get(READ_URL.format(nid=nid))
    except Exception as e:
        print(f"[research_reports] {nid} body fetch failed: {e}", file=sys.stderr)
        return ""
    i = html.find("view_cnt")
    if i < 0:
        return ""
    import html as _html
    chunk = re.sub(r"<[^>]+>", " ", html[i:i + 2500])
    return re.sub(r"\s+", " ", _html.unescape(chunk)).strip()


_PROMPT = """다음은 증권사 시황 리포트 본문입니다. 개인 투자자용으로 1~2문장 한국어 요약을 만드세요.

규칙:
- 지수 레벨·등락률·목표가 등 숫자는 절대 쓰지 마세요(원인·맥락만 서술).
- 리포트에 없는 내용을 생성하지 마세요.
- 반드시 해요체(예: ~했어요, ~보였어요)로 끝내세요. '~다', '~습니다'체 금지.

[본문]
{body}

[출력: 요약문만, 다른 텍스트 없이]"""


def _summarize(body: str) -> str | None:
    from google import genai
    from google.genai import types
    try:
        client = genai.Client(api_key=get_gemini_api_key())
        resp = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=_PROMPT.format(body=body[:1300]),
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=200),
        )
        summary = (resp.text or "").strip()
    except Exception as e:
        print(f"[research_reports] Gemini 요약 실패: {e}", file=sys.stderr)
        return None
    if not summary or _NUM_LEAK.search(summary):
        return None
    return summary


def build_payload(today: str) -> list[dict]:
    out = []
    for cand in _list_today(today):
        body = _body_text(cand["nid"])
        if not body:
            continue
        summary = _summarize(body)
        if not summary:
            print(f"[research_reports] SKIP(숫자 잔존/요약 실패): {cand['title']}", file=sys.stderr)
            continue
        out.append({
            "firm": cand["firm"],
            "title": cand["title"],
            "summary": summary,
            "url": READ_URL.format(nid=cand["nid"]),
        })
    return out


def main():
    today = datetime.now(KST).strftime("%Y-%m-%d")
    reports = build_payload(today)
    payload = {"generated_at": datetime.now(KST).isoformat(), "date": today, "reports": reports}
    out_path = DATA_DIR / "research_reports.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[research_reports] {len(reports)}건 저장 → {out_path}")


if __name__ == "__main__":
    main()
