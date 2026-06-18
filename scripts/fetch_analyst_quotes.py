#!/usr/bin/env python3
# Gemini google_search로 월가 애널리스트 12명의 최근 발언을 수집·분류하는 스크립트
"""
Usage:
    python3 scripts/fetch_analyst_quotes.py

출력: data/analyst_quotes.json
  - 48시간 이내 실발언만 수집 (없으면 빈 배열)
  - 최대 4명, published_at 기준 최신순 정렬
  - sentiment: bull | bear | neu (Gemini 자동 분류)
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import dateutil.parser
import pytz

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")

ANALYSTS = [
    {"name": "Tom Lee",               "affiliation": "Fundstrat",               "initials": "TL"},
    {"name": "Ed Yardeni",            "affiliation": "Yardeni Research",         "initials": "EY"},
    {"name": "Dan Ives",              "affiliation": "Wedbush",                  "initials": "DI"},
    {"name": "Mike Wilson",           "affiliation": "Morgan Stanley",           "initials": "MW"},
    {"name": "Savita Subramanian",    "affiliation": "Bank of America",          "initials": "SS"},
    {"name": "Bill Ackman",           "affiliation": "Pershing Square",          "initials": "BA"},
    {"name": "Stan Druckenmiller",    "affiliation": "Duquesne Family Office",   "initials": "SD"},
    {"name": "Mohamed El-Erian",      "affiliation": "Allianz",                  "initials": "ME"},
    {"name": "Jeff Gundlach",         "affiliation": "DoubleLine Capital",       "initials": "JG"},
    {"name": "Ray Dalio",             "affiliation": "Bridgewater Associates",   "initials": "RD"},
    {"name": "Cathie Wood",           "affiliation": "ARK Invest",               "initials": "CW"},
    {"name": "Michael Burry",         "affiliation": "Scion Asset Management",   "initials": "MB"},
]

MAX_QUOTES = 4

VALID_SENTIMENTS = {"bull", "bear", "neu"}
REQUIRED_FIELDS = {"name", "quote", "source", "published_at", "time_label", "sentiment"}


def _is_valid_quote(q) -> bool:
    if not isinstance(q, dict):
        return False
    return all(q.get(f) for f in REQUIRED_FIELDS)


def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        config_file = BASE_DIR / "config.json"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                cfg = json.load(f)
            key = cfg.get("gemini", {}).get("api_key", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return key


def build_prompt(now_kst: datetime) -> str:
    now_str = now_kst.strftime("%Y-%m-%d %H:%M KST")
    cutoff_str = "48시간 이내 (기준: " + now_str + ")"
    analyst_list = "\n".join(
        f'- {a["name"]} ({a["affiliation"]})'
        for a in ANALYSTS
    )
    return f"""\
현재 시각은 {now_str}입니다.

아래 월가 애널리스트·투자자 12명 각각에 대해 Google Search로 최근 발언을 검색해 주세요.
수집 기준: {cutoff_str} 이내에 실제 인터뷰·기사·SNS에서 한 발언만 포함.

대상 인물:
{analyst_list}

각 인물에 대해:
1. 최근 {cutoff_str} 이내 시장 전망 관련 발언이 있는지 검색
2. 있으면: 실제 발언 내용(한국어 번역), 출처, 발언 일시 추출
3. 없으면: 해당 인물을 결과에서 완전히 제외

⚠️ 매우 중요: 검색 결과에 실제로 존재하는 발언만 포함하세요.
발언이 검색되지 않으면 해당 인물을 results 배열에서 제외하세요.
발언 내용을 추측·생성·요약하지 마세요. 검색된 원문 기반 번역만 허용합니다.

sentiment 분류 기준:
- "bull": 시장 상승 전망, 매수 추천, 낙관적 견해
- "bear": 시장 하락 전망, 매도 추천, 비관적 견해
- "neu": 중립, 조건부, 혼조

time_label 형식: 발언이 오늘(KST 기준)이면 "오늘 HH:MM", 어제면 "어제 HH:MM"

출력 형식 (JSON 배열만, 다른 텍스트 없이):
[
  {{
    "name": "인물 이름 (영문, 원래 표기)",
    "affiliation": "소속 기관",
    "initials": "이니셜 2자",
    "quote": "한국어 번역 발언 (원문 기반, 2-4문장)",
    "source": "출처 매체명",
    "url": "반드시 빈 문자열 \"\" — URL은 검색 메타데이터에서 자동 주입됩니다",
    "published_at": "ISO 8601 datetime (KST, 예: 2026-06-06T23:14:00+09:00)",
    "time_label": "어제 23:14",
    "sentiment": "bull"
  }}
]

발언이 하나도 없으면 빈 배열 [] 를 반환하세요.
"""


def fetch_analyst_quotes() -> list:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    client = genai.Client(api_key=get_gemini_api_key())
    now_kst = datetime.now(KST)
    prompt = build_prompt(now_kst)

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )

    if not response.text:
        finish = getattr(response.candidates[0], "finish_reason", "UNKNOWN") if response.candidates else "NO_CANDIDATES"
        raise RuntimeError(f"Gemini returned empty response (finish_reason={finish})")

    raw = response.text.strip()

    # JSON 블록 추출 (마크다운 펜스 제거)
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        raw = m.group(0)

    quotes = json.loads(raw)
    if not isinstance(quotes, list):
        return []

    # grounding_metadata에서 실제 URL 추출 (Gemini가 실제로 참조한 검색 결과)
    grounding_urls: list[dict] = []
    try:
        gm = response.candidates[0].grounding_metadata
        for chunk in (gm.grounding_chunks or []):
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                grounding_urls.append({"uri": web.uri, "title": getattr(web, "title", "")})
    except Exception:
        pass

    # 각 발언에 grounding URL 매핑: 애널리스트 이름이 title에 포함된 URL 우선
    def _find_url(q: dict) -> str:
        name_lower = q.get("name", "").lower()
        source_lower = q.get("source", "").lower()
        # 1순위: title에 이름 포함
        for g in grounding_urls:
            if name_lower.split()[-1] in g["title"].lower():
                return g["uri"]
        # 2순위: title에 source 포함
        for g in grounding_urls:
            if any(w in g["title"].lower() for w in source_lower.split() if len(w) > 3):
                return g["uri"]
        return ""

    for q in quotes:
        q["url"] = _find_url(q)

    # initials 보정: ANALYSTS 정의 기준으로 덮어쓰기
    initials_map = {a["name"]: a["initials"] for a in ANALYSTS}
    for q in quotes:
        q["initials"] = initials_map.get(q.get("name", ""), q.get("initials", "??"))

    # sentiment 정규화: e.g. "bullish"→"bull", "bearish"→"bear", "neutral"→"neu"
    _sent_map = {"bullish": "bull", "bearish": "bear", "neutral": "neu"}
    for q in quotes:
        s = str(q.get("sentiment", "")).lower()
        q["sentiment"] = _sent_map.get(s, s) if s in _sent_map else (s if s in VALID_SENTIMENTS else "neu")

    # 중복 제거: 동일 애널리스트의 가장 최근 발언만 유지
    seen = {}
    for q in quotes:
        name = q.get("name", "")
        try:
            dt = dateutil.parser.parse(q.get("published_at", "2000-01-01T00:00:00+09:00"))
        except Exception:
            dt = datetime(2000, 1, 1, tzinfo=KST)
        if name not in seen or dt > seen[name][0]:
            seen[name] = (dt, q)
    quotes = [v for _, v in seen.values()]

    # 필수 필드 검증 필터
    quotes = [q for q in quotes if _is_valid_quote(q)]

    # published_at 기준 최신순 정렬 후 MAX_QUOTES 보존
    def sort_key(q):
        try:
            return dateutil.parser.parse(q.get("published_at", "2000-01-01T00:00:00+09:00"))
        except Exception:
            return datetime(2000, 1, 1, tzinfo=KST)

    quotes.sort(key=sort_key, reverse=True)
    return quotes[:MAX_QUOTES]


def main():
    print("[fetch_analyst_quotes] 월가 애널리스트 발언 수집 시작")
    out_path = DATA_DIR / "analyst_quotes.json"

    try:
        quotes = fetch_analyst_quotes()
        print(f"[fetch_analyst_quotes] 수집 완료: {len(quotes)}명")
    except Exception as e:
        print(f"[fetch_analyst_quotes] ERROR: {e}", file=sys.stderr)
        # 실패 시 빈 배열 저장 (섹션 생략)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)
        print(f"[fetch_analyst_quotes] 빈 배열 저장 → {out_path}")
        sys.exit(0)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(quotes, f, ensure_ascii=False, indent=2)
    print(f"[fetch_analyst_quotes] 저장 완료 → {out_path}")


if __name__ == "__main__":
    main()
