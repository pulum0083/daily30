# 장중 코스피 핵심 이슈를 Gemini Google Search로 수집해 kospi-news-live.json을 갱신하는 스크립트
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).parent.parent
OUT_PATH = REPO_ROOT / "web" / "data" / "kospi-news-live.json"
MAX_HISTORY = 6

PROMPT = """
지금 {today} {time} KST 기준, 코스피 장중 투자자가 가장 주목해야 할 이슈 2개를 골라주세요.

[선택 범위 — 아래 두 카테고리에서 각 1개씩]
1. 시장 전체: 코스피·코스닥 지수 흐름, 외국인·기관 수급, 환율, 글로벌 이슈
2. 주요 종목: 삼성전자·SK하이닉스·현대차·셀트리온·카카오·NAVER·KB금융·포스코 등 대형주, 또는 오늘 5% 이상 급등락 중인 종목

[타이틀 규칙]
- 각 15자 이내, 현재 일어나고 있는 일을 짧고 강하게
- "지속", "흐름", "동향" 같은 밋밋한 단어 금지
- 구체적 숫자·행위자 포함 (예: "삼전 5% 급락", "외국인 20일째 매도", "원화 1545 돌파")
- 시장 감정 표현 허용 (질주, 급락, 흔들, 버팀, 폭발 등)

[요약 규칙]
- 각 40자 이내, 해요체(~있어요, ~이에요, ~해요)
- 투자자 시각 — "왜 지금 이게 중요한지"를 한 줄로
- 원인 → 결과 구조 (예: "OO 때문에 XX가 흔들리고 있어요")

아래 JSON 형식만 출력하세요 (마크다운·추가 텍스트 없이):
{{
  "market": {{"title": "시장 이슈 제목", "summary": "한 줄 요약"}},
  "stock":  {{"title": "종목 이슈 제목", "summary": "한 줄 요약"}}
}}
"""


def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        cfg = REPO_ROOT / "config.json"
        if cfg.exists():
            with open(cfg, encoding="utf-8") as f:
                config = json.load(f)
            key = config.get("gemini", {}).get("api_key", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found in env or config.json")
    return key


def fetch_latest_issue(today: str, time_str: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=get_gemini_api_key())
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=PROMPT.format(today=today, time=time_str),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.7,
            max_output_tokens=400,
        ),
    )
    raw = response.text
    if not raw:
        raise RuntimeError("Gemini가 빈 응답을 반환했습니다 (response.text is None or empty)")
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    parsed = json.loads(raw)
    # 구버전 단일 포맷 호환 — market/stock 키가 없으면 market으로 래핑
    if "market" not in parsed and "title" in parsed:
        parsed = {"market": parsed, "stock": None}
    return parsed


def main() -> None:
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    print(f"[fetch_news_live] {today} {time_str} KST — Gemini 이슈 수집 시작")

    try:
        latest = fetch_latest_issue(today, time_str)
    except Exception as e:
        print(f"[fetch_news_live] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # 기존 latest를 history 맨 앞에 추가 (날짜가 같은 경우에만 history 이어받음)
    history: list = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if existing.get("date") == today:
                prev = existing.get("latest")
                if prev:
                    # market 키가 있는 새 포맷 또는 구 포맷 모두 history에 보존
                    entry = {"time": existing.get("updated_at", "")}
                    if "market" in prev:
                        entry.update(prev)
                    elif prev.get("title") and prev.get("title") != "오늘의 이슈 준비 중":
                        entry["market"] = prev
                    if entry.get("market"):
                        history = [entry]
                history += existing.get("history", [])
                history = history[:MAX_HISTORY]
        except Exception:
            pass

    data = {"date": today, "updated_at": time_str, "latest": latest, "history": history}
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_news_live] Saved → {OUT_PATH}")


if __name__ == "__main__":
    main()
