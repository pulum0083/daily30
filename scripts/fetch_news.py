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
- **주도주 기업 이벤트**: 코스피 대형주(삼성전자·SK하이닉스·현대차 등)의 상장·ADR·M&A·지분매각·신사업 진출·대형 수주·설비투자·실적 발표
- **[임시 2026-07-12 추가, 테마 소멸 시 제거]** SK하이닉스 ADR 미국 상장 이후 한국 증시(특히 SK하이닉스 본주) 반응·수급 대응 — 이번 주 핵심 테마이므로 명시 검색
- **인과 촉매**: 특정 섹터/주도주 등락의 '원인'이 된 사건 — 특히 미국 빅테크 전략 뉴스(클라우드·자체 칩 설계·감산·투자)가 한국 반도체·2차전지에 미치는 파급(read-through)
- **AI 모델 개발사 이슈(비상장이지만 핵심 촉매)**: OpenAI·Anthropic의 신모델 출시, 대형 칩·HBM·클라우드 계약, 대규모 투자·펀딩 — 이런 AI 인프라 수요 신호가 SK하이닉스·삼성전자 HBM·반도체 투자심리에 미치는 파급

[key_indicators 작성 규칙]
- 반드시 실제 수치(%, 금액)를 포함한다
- 오늘 코스피에 직접 영향을 줄 이슈만 포함한다
- 포함 금지: YTD 수익률, 연간 상승률, 애널리스트 중장기 전망

[catalysts 작성 규칙]
- 오늘 코스피 주도주·섹터를 움직일 '사건' 중심 뉴스만 담는다 (지수 등락률 나열이 아님)
- 각 항목은 "무슨 사건 → 어느 종목·섹터에 왜 영향" 형태의 한 문장. 실제로 검색된 사건만 담고, 없으면 빈 배열 []
- 예: "메타, 자체 AI 추론 칩 설계 확대 발표 → 기존 메모리 수요 둔화 우려로 한국 반도체 투자심리 위축"

출력 형식 (JSON만, 다른 텍스트 없이):
{{
  "key_indicators": [
    "어제 미국 증시 관련 구체적 이슈 (수치 포함)",
    "외국인 수급·ETF 관련 이슈",
    "오늘 예정된 경제 지표 또는 이벤트",
    "반도체·기술주 이슈",
    "원유·환율 동향"
  ],
  "catalysts": [
    "주도주·섹터를 움직인 사건 → 영향 (실제 검색된 것만, 없으면 이 배열은 비운다)"
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
- **주도주 기업 이벤트**: 매그니피센트7(NVDA·AAPL·MSFT·GOOGL·AMZN·META·TSLA)·브로드컴(AVGO)·AMD·스페이스X(SPCX) 등 시총 상위 빅테크의 실적·가이던스·신제품·M&A·대형 계약·자사주·감원 등
- **[최우선] 오늘/어제 발표된 주요 기업 실적(어닝) — 어닝시즌에는 이것이 지수·섹터를 가장 크게 움직이는 촉매다**: 빅테크뿐 아니라 **금융주(모건스탠리·골드만삭스·JP모건·뱅크오브아메리카·블랙록·씨티 등 대형 은행·자산운용)**, 반도체(마이크론·TSMC·ASML), 헬스케어·소비재 등 **모든 섹터의 대형주 실적·가이던스·컨퍼런스콜 경영진 코멘트**를 반드시 검색한다. 오늘 실적을 발표하는 기업, 발표한 기업의 EPS·매출 서프라이즈/미스, 주가 반응(시간외 포함)을 함께 찾는다.
- **실적 read-through(연쇄 파급)**: 한 기업의 실적·발언이 **다른 종목·섹터를 움직인 경우**를 포착한다. (예: IBM 실적 콜의 AI 인프라 언급 → 메모리·데이터센터주 상승, 은행 실적의 대손충당·자본시장 코멘트 → 금융 섹터 전반, 마이크론 HBM 가이던스 → 반도체 장비주) 어느 기업의 무슨 실적/발언이 어느 종목·섹터를 왜 움직였는지 인과로 정리한다.
- **인과 촉매**: 특정 섹터/주도주 등락의 '원인'이 된 사건 — 신제품·전략 발표, 규제·소송, 공급망·감산 등이 어느 종목·섹터를 왜 움직였는지
- **AI 모델 개발사 이슈(비상장이지만 핵심 시장 촉매)**: OpenAI·Anthropic의 신모델 출시, 대형 칩·클라우드 계약, 펀딩·밸류, IPO 진행(S-1·상장 일정) — 엔비디아·브로드컴·MS·아마존·구글 등 상장 AI 인프라주에 미치는 파급

[key_indicators 작성 규칙]
- 오늘 또는 어제 실제 발생한 이슈, 현재 선물 방향만 포함한다
- 반드시 수치(%, 금액, bp)를 포함한다
- 포함 금지: YTD 수익률, 연간 상승률, 애널리스트 중장기 전망

[catalysts 작성 규칙]
- 오늘 미국 증시 주도주·섹터를 움직일 '사건' 중심 뉴스만 담는다 (지수 등락률 나열이 아님)
- 각 항목은 "무슨 사건 → 어느 종목·섹터에 왜 영향" 형태의 한 문장. 실제로 검색된 사건만 담고, 없으면 빈 배열 []
- **오늘/어제 발표된 주요 기업 실적(어닝)은 catalysts에 최우선으로 담는다** — 실적 서프라이즈·가이던스·경영진 발언이 해당 종목뿐 아니라 다른 종목·섹터로 파급된 경우(read-through)를 인과로 정리한다.
- 예: "엔비디아, 차세대 GPU 조기 양산 발표 → AI 반도체 수요 기대 확대로 필라델피아 반도체지수 강세"
- 예: "모건스탠리, 트레이딩 수익 서프라이즈로 실적 호조 → 골드만삭스·JP모건 등 대형 은행주 동반 강세"
- 예: "IBM 실적 콜, 고객사 AI 인프라 투자 확대 언급 → 마이크론·SK하이닉스 등 메모리·데이터센터주 상승"

출력 형식 (JSON만, 다른 텍스트 없이):
{{
  "key_indicators": [
    "오늘 선물·프리마켓 관련 구체적 이슈 (수치 포함)",
    "발표된 경제 지표 결과 또는 연준 이슈",
    "빅테크·반도체 이슈 (수치 포함)",
    "금리·VIX·달러 관련 이슈",
    "아시아·유럽 증시 흐름"
  ],
  "catalysts": [
    "주도주·섹터를 움직인 사건 → 영향 (실제 검색된 것만, 없으면 이 배열은 비운다)"
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
            max_output_tokens=1400,
        ),
    )
    if not response.text:
        finish = getattr(response.candidates[0], 'finish_reason', 'UNKNOWN') if response.candidates else 'NO_CANDIDATES'
        raise RuntimeError(f"Gemini returned empty response (finish_reason={finish})")
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

def _is_retryable_error(e: Exception) -> bool:
    msg = str(e).upper()
    return (
        "429" in msg or "RESOURCE_EXHAUSTED" in msg or "QUOTA" in msg
        or "503" in msg or "UNAVAILABLE" in msg or "SERVICE_UNAVAILABLE" in msg
    )


EMPTY_NEWS = {
    "key_indicators": [],
    "catalysts": [],
    "headlines": [],
    "market_sentiment": "neutral",
}


def main():
    parser = argparse.ArgumentParser(description="Gemini Google Search grounding으로 시장 뉴스 수집·요약")
    parser.add_argument("--type", choices=["kospi", "kospi-close", "us"], required=True)
    args = parser.parse_args()

    print(f"[fetch_news] Fetching news via Gemini Google Search grounding (type={args.type})")

    summary = None
    last_err = None
    for attempt in range(1, 4):
        try:
            summary = fetch_and_summarize(args.type)
            print(
                f"[fetch_news] OK (attempt {attempt}): "
                f"{len(summary.get('key_indicators', []))} indicators, "
                f"{len(summary.get('headlines', []))} headlines"
            )
            break
        except Exception as e:
            last_err = e
            if _is_retryable_error(e) and attempt < 3:
                import time
                wait = 45 * attempt
                print(f"[fetch_news] 일시 오류({attempt}/3) — {wait}s 후 재시도: {e}", file=sys.stderr)
                time.sleep(wait)
            else:
                break

    if summary is None:
        print(f"[fetch_news] ERROR: {last_err}", file=sys.stderr)
        # stale 파일이 남아 있으면 downstream이 구 데이터를 쓰지 않도록 삭제
        stale = DATA_DIR / f"news_summary_{args.type}.json"
        if stale.exists():
            stale.unlink()
            print(f"[fetch_news] stale 뉴스 파일 삭제: {stale}", file=sys.stderr)
        # Gemini 일시 장애 시 빈 뉴스로 파이프라인 계속 진행
        print("[fetch_news] WARN: 빈 뉴스로 계속 진행 (Gemini 일시 장애)", file=sys.stderr)
        summary = EMPTY_NEWS

    summary["generated_at"] = datetime.now(KST).isoformat()
    out_path = DATA_DIR / f"news_summary_{args.type}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[fetch_news] Saved → {out_path}")


if __name__ == "__main__":
    main()
