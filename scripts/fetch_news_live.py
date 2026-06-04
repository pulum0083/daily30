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
지금 {today} {time} KST 기준, 코스피 장중에 가장 큰 영향을 주는 핵심 이슈 1개를 알려주세요.

아래 JSON 형식만 출력하세요 (마크다운·추가 텍스트 없이):
{{
  "title": "이슈 제목 (15자 이내)",
  "summary": "한 줄 요약 (40자 이내)"
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
            temperature=0.3,
            max_output_tokens=256,
        ),
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    return json.loads(raw)


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

    # 기존 latest를 history 맨 앞에 추가
    history: list = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            prev = existing.get("latest")
            if prev and prev.get("title") and prev.get("title") != "오늘의 이슈 준비 중":
                history = [{"time": existing.get("updated_at", ""), **prev}]
            history += existing.get("history", [])
            history = history[:MAX_HISTORY]
        except Exception:
            pass

    data = {"updated_at": time_str, "latest": latest, "history": history}
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_news_live] Saved → {OUT_PATH}")


if __name__ == "__main__":
    main()
