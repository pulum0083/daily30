#!/usr/bin/env python3
# Gemini Google Search grounding으로 최신 시장 뉴스를 수집·요약하는 스크립트

"""
흐름:
  Gemini 2.5 Flash (google_search grounding) → 그 시점 Google 검색 기반 최신 뉴스 수집·요약
  → data/news_summary_{type}.json 저장

Usage:
    python3 scripts/fetch_news.py --type kospi
    python3 scripts/fetch_news.py --type us
    python3 scripts/fetch_news.py --type kospi-close
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")


# ─────────────────────────────────────────────────────────────────────────────
# Gemini API
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
# 브리핑 타입별 검색·요약 프롬프트
# ─────────────────────────────────────────────────────────────────────────────

KOSPI_PROMPT = """\
오늘({today}) 한국 코스피 시장 예측에 필요한 최신 뉴스를 Google Search로 검색해 분석해줘.

검색할 내용:
- 어제(현지 시각) 미국 나스닥·S&P500 등락 원인과 수치
- 오늘 코스피 개장에 영향을 줄 외국인 수급·ETF 자금 흐름
- 오늘 예정된 주요 경제 지표 또는 이벤트 (FOMC, CPI 등)
- 반도체·기술주 관련 최신 이슈 (NVDA, TSMC 등)
- 원유·환율 최신 동향

[key_indicators 작성 규칙]
- 반드시 실제 수치(%, 금액)를 포함한다
- 오늘 코스피에 직접 영향을 줄 이슈만 포함한다
- 포함 금지: YTD 수익률, 연간 상승률, 애널리스트 중장기 전망

출력 형식 (JSON만, 다른 텍스트 없이):
{{
  "key_indicators": [
    "어제 미국 증시 관련 구체적 이슈 (수치 포함)",
    "외국인 수급·ETF 관련 이슈",
    "오늘 예정된 경제 지표 또는 이벤트",
    "반도체·기술주 이슈",
    "원유·환율 동향"
  ],
  "headlines": [
    "오늘 코스피 방향에 직접 영향을 줄 헤드라인 1",
    "헤드라인 2",
    "헤드라인 3"
  ],
  "market_sentiment": "bullish or bearish or neutral"
}}
"""

KOSPI_CLOSE_PROMPT = """\
오늘({today}) 한국 코스피 마감 시황 분석에 필요한 최신 뉴스를 Google Search로 검색해 분석해줘.

검색할 내용:
- 오늘 코스피 마감 지수와 주요 등락 원인
- 오늘 외국인·기관 수급 동향
- 오늘 장중 급등락 섹터 및 종목 원인
- 오늘 발표된 경제 지표·정책·규제 이슈

[key_indicators 작성 규칙]
- 오늘 장중 실제 발생한 이슈만 포함한다
- 반드시 수치(%, 금액)를 포함한다
- 포함 금지: 중장기 전망, 애널리스트 목표가, 연간 수익률

출력 형식 (JSON만, 다른 텍스트 없이):
{{
  "key_indicators": [
    "오늘 코스피 등락 관련 핵심 이슈 (수치 포함)",
    "섹터별 이슈 (반도체·바이오·2차전지 등)",
    "외국인·기관 수급 관련 뉴스",
    "정책·규제·실적 이슈"
  ],
  "headlines": [
    "오늘 코스피 마감 관련 헤드라인 1",
    "헤드라인 2",
    "헤드라인 3"
  ],
  "market_sentiment": "bullish or bearish or neutral"
}}
"""

US_PROMPT = """\
오늘({today}) 미국 증시(S&P500/NASDAQ) 예측에 필요한 최신 뉴스를 Google Search로 검색해 분석해줘.

검색할 내용:
- 현재 S&P500·나스닥 선물 방향과 수치
- 오늘 발표된 경제 지표 결과 (CPI, NFP, FOMC 등)
- 빅테크·반도체 주요 이슈 (NVDA, AAPL, MSFT, AMD 등)
- 연준 발언·금리 동향
- 아시아·유럽 증시 흐름

[key_indicators 작성 규칙]
- 오늘 또는 어제 실제 발생한 이슈, 현재 선물 방향만 포함한다
- 반드시 수치(%, 금액, bp)를 포함한다
- 포함 금지: YTD 수익률, 연간 상승률, 애널리스트 중장기 전망

출력 형식 (JSON만, 다른 텍스트 없이):
{{
  "key_indicators": [
    "오늘 선물·프리마켓 관련 구체적 이슈 (수치 포함)",
    "발표된 경제 지표 결과 또는 연준 이슈",
    "빅테크·반도체 이슈 (수치 포함)",
    "금리·VIX·달러 관련 이슈",
    "아시아·유럽 증시 흐름"
  ],
  "headlines": [
    "미국 증시 방향에 영향을 줄 헤드라인 1",
    "헤드라인 2",
    "헤드라인 3"
  ],
  "market_sentiment": "bullish or bearish or neutral"
}}
"""

PROMPT_MAP = {
    "kospi": KOSPI_PROMPT,
    "kospi-close": KOSPI_CLOSE_PROMPT,
    "us": US_PROMPT,
}


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Google Search grounding으로 뉴스 수집·요약
# ─────────────────────────────────────────────────────────────────────────────

def fetch_and_summarize(briefing_type: str) -> dict:
    """Gemini Google Search grounding으로 최신 뉴스를 검색·요약해 dict로 반환한다."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    client = genai.Client(api_key=get_gemini_api_key())
    today = datetime.now(KST).strftime("%Y-%m-%d")
    prompt = PROMPT_MAP[briefing_type].format(today=today)

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.3,
            max_output_tokens=1024,
        ),
    )
    raw = response.text.strip()

    # JSON 블록 추출 (마크다운 펜스·전후 텍스트 제거)
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    # { ... } 블록만 추출
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)

    return json.loads(raw)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gemini Google Search grounding으로 시장 뉴스 수집·요약")
    parser.add_argument("--type", choices=["kospi", "kospi-close", "us"], required=True)
    args = parser.parse_args()

    print(f"[fetch_news] Fetching news via Gemini Google Search grounding (type={args.type})")

    try:
        summary = fetch_and_summarize(args.type)
        print(
            f"[fetch_news] OK: {len(summary.get('key_indicators', []))} indicators, "
            f"{len(summary.get('headlines', []))} headlines"
        )
    except Exception as e:
        print(f"[fetch_news] ERROR: {e}", file=sys.stderr)
        summary = {
            "key_indicators": [],
            "headlines": [],
            "market_sentiment": "neutral",
            "error": str(e),
        }

    summary["generated_at"] = datetime.now(KST).isoformat()
    out_path = DATA_DIR / f"news_summary_{args.type}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[fetch_news] Saved → {out_path}")


if __name__ == "__main__":
    main()
