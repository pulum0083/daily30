#!/usr/bin/env python3
"""
Gemini Flash 기반 뉴스 요약 스크립트 (3순위: Gemini Worker).

흐름:
  1. Google News RSS에서 시장 관련 뉴스 헤드라인 수집 (무료, API 키 불필요)
  2. Gemini 1.5 Flash로 핵심 지표 5개 + 헤드라인 3개로 압축
  3. data/news_summary_{type}.json 저장

call_claude.py가 이 요약본만 Claude에 전달하므로, 원문 뉴스의 방대한 토큰을 Claude가 처리하지 않아도 됩니다.

Usage:
    python3 scripts/fetch_news.py --type kospi
    python3 scripts/fetch_news.py --type us
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError

import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")

# ─────────────────────────────────────────────────────────────────────────────
# RSS 뉴스 소스 설정
# ─────────────────────────────────────────────────────────────────────────────

def _rss(q: str, hl: str = "en", gl: str = "US", ceid: str = "US:en") -> str:
    return f"https://news.google.com/rss/search?q={quote(q)}&hl={hl}&gl={gl}&ceid={ceid}"

KOSPI_RSS_FEEDS = [
    _rss("KOSPI stock market", "en", "US", "US:en"),
    _rss("Korea stock NASDAQ semiconductor", "en", "US", "US:en"),
    _rss("Korean stock market today", "en", "US", "US:en"),
    _rss("코스피 증시", "ko", "KR", "KR:ko"),
]

US_RSS_FEEDS = [
    _rss("NASDAQ S&P500 stock market"),
    _rss("Federal Reserve interest rate economy"),
    _rss("US stock market today earnings"),
    _rss("NVDA AAPL MSFT semiconductor"),
]

KOSPI_GEMINI_PROMPT = """\
아래 뉴스 헤드라인들을 분석하여, 오늘 코스피 시초가 예측에 필요한 핵심 정보만 추출해줘.

출력 형식 (JSON만, 다른 텍스트 없이):
{
  "key_indicators": [
    "핵심 지표 또는 이슈 1 (수치 포함, 한 문장)",
    "핵심 지표 또는 이슈 2",
    "핵심 지표 또는 이슈 3",
    "핵심 지표 또는 이슈 4",
    "핵심 지표 또는 이슈 5"
  ],
  "headlines": [
    "코스피 방향에 영향을 줄 헤드라인 1",
    "헤드라인 2",
    "헤드라인 3"
  ],
  "market_sentiment": "bullish" | "bearish" | "neutral"
}

뉴스 데이터:
"""

US_GEMINI_PROMPT = """\
아래 뉴스 헤드라인들을 분석하여, 오늘 미국 증시(S&P500/NASDAQ) 개장 방향 예측에 필요한 핵심 정보만 추출해줘.

출력 형식 (JSON만, 다른 텍스트 없이):
{
  "key_indicators": [
    "핵심 지표 또는 이슈 1 (수치 포함, 한 문장)",
    "핵심 지표 또는 이슈 2",
    "핵심 지표 또는 이슈 3",
    "핵심 지표 또는 이슈 4",
    "핵심 지표 또는 이슈 5"
  ],
  "headlines": [
    "미국 증시 방향에 영향을 줄 헤드라인 1",
    "헤드라인 2",
    "헤드라인 3"
  ],
  "market_sentiment": "bullish" | "bearish" | "neutral"
}

뉴스 데이터:
"""


# ─────────────────────────────────────────────────────────────────────────────
# Gemini API 설정
# ─────────────────────────────────────────────────────────────────────────────

def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        config_file = BASE_DIR / "config.json"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                cfg = json.load(f)
            key = cfg.get("gemini", {}).get("api_key", "")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. "
            "Set the environment variable or add gemini.api_key to config.json"
        )
    return key


# ─────────────────────────────────────────────────────────────────────────────
# RSS 파싱 (표준 라이브러리만 사용)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_rss_headlines(feed_url: str, max_items: int = 8) -> list[str]:
    """Google News RSS에서 헤드라인 목록을 반환한다."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; DailyB/1.0)"
    }
    try:
        req = Request(feed_url, headers=headers)
        with urlopen(req, timeout=10) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        channel = root.find("channel")
        if channel is None:
            return []
        items = channel.findall("item")[:max_items]
        headlines = []
        for item in items:
            title = item.findtext("title", "").strip()
            desc = item.findtext("description", "").strip()
            # desc may contain HTML; strip tags naively
            desc_clean = ""
            if desc:
                import re
                desc_clean = re.sub(r"<[^>]+>", "", desc)[:120]
            if title:
                line = title
                if desc_clean:
                    line += f" — {desc_clean}"
                headlines.append(line)
        return headlines
    except (URLError, ET.ParseError, Exception) as e:
        print(f"[fetch_news] RSS fetch failed ({feed_url[:60]}...): {e}", file=sys.stderr)
        return []


def collect_news(briefing_type: str) -> str:
    """모든 RSS 피드에서 헤드라인을 수집하여 하나의 텍스트로 반환한다."""
    feeds = KOSPI_RSS_FEEDS if briefing_type == "kospi" else US_RSS_FEEDS
    all_headlines = []
    seen = set()

    for feed_url in feeds:
        for headline in fetch_rss_headlines(feed_url, max_items=6):
            # 중복 제거 (제목 앞 30자 기준)
            key = headline[:30]
            if key not in seen:
                seen.add(key)
                all_headlines.append(headline)

    if not all_headlines:
        return ""

    return "\n".join(f"- {h}" for h in all_headlines[:20])


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Flash 요약 (google-generativeai SDK)
# ─────────────────────────────────────────────────────────────────────────────

def summarize_with_gemini(news_text: str, briefing_type: str) -> dict:
    """Gemini 2.0 Flash로 뉴스 텍스트를 요약하여 JSON 딕셔너리를 반환한다."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "google-genai not installed. "
            "Run: pip install google-genai"
        )

    client = genai.Client(api_key=get_gemini_api_key())

    prompt_prefix = KOSPI_GEMINI_PROMPT if briefing_type == "kospi" else US_GEMINI_PROMPT
    full_prompt = prompt_prefix + "\n" + news_text

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=full_prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=512,
        ),
    )
    raw = response.text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    return json.loads(raw)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch & summarize market news via Gemini Flash")
    parser.add_argument("--type", choices=["kospi", "us"], required=True)
    args = parser.parse_args()

    print(f"[fetch_news] Collecting news for type={args.type}")

    # 1. RSS 수집
    news_text = collect_news(args.type)
    if not news_text:
        print("[fetch_news] WARNING: No news collected. Saving empty summary.", file=sys.stderr)
        summary = {"key_indicators": [], "headlines": [], "market_sentiment": "neutral"}
    else:
        print(f"[fetch_news] Collected {news_text.count(chr(10)) + 1} headlines")

        # 2. Gemini 요약
        try:
            summary = summarize_with_gemini(news_text, args.type)
            print(f"[fetch_news] Gemini summary: {len(summary.get('key_indicators', []))} indicators, "
                  f"{len(summary.get('headlines', []))} headlines")
        except Exception as e:
            print(f"[fetch_news] ERROR: Gemini summarization failed: {e}", file=sys.stderr)
            # 실패해도 원본 헤드라인 일부를 fallback으로 사용
            raw_headlines = [line.lstrip("- ") for line in news_text.split("\n")[:5] if line.strip()]
            summary = {
                "key_indicators": raw_headlines[:3],
                "headlines": raw_headlines[:3],
                "market_sentiment": "neutral",
                "error": str(e),
            }

    # 3. 타임스탬프 추가 후 저장
    summary["generated_at"] = datetime.now(KST).isoformat()
    out_path = DATA_DIR / f"news_summary_{args.type}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[fetch_news] Saved → {out_path}")


if __name__ == "__main__":
    main()
