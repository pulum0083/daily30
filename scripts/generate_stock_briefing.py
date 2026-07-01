#!/usr/bin/env python3
# 삼성전자·SK하이닉스 종목별 이슈 타이틀을 생성해 Supabase에 저장하는 스크립트

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import pytz

try:
    from supabase import create_client
except ImportError:
    print("[briefing] ERROR: supabase-py 미설치. pip install supabase", file=sys.stderr)
    sys.exit(1)

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
KST = pytz.timezone("Asia/Seoul")
MAX_HISTORY = 6

STOCKS = [
    {
        "ticker": "005930",
        "name": "삼성전자",
        "focus": (
            "삼성전자 특화 이슈: HBM3E 엔비디아 퀄 진행 현황, 파운드리 사업 수주·기술 경쟁력, "
            "메모리(DRAM·NAND) 가격·점유율, 갤럭시·MX 사업부, 주주 환원(자사주·배당). "
            "SK하이닉스와 겹치는 공통 매크로는 가능한 한 제외하고 삼성전자 단독 이슈에 집중한다."
        ),
    },
    {
        "ticker": "000660",
        "name": "SK하이닉스",
        "focus": (
            "SK하이닉스 특화 이슈: HBM 공급량·가격·점유율(엔비디아·AMD·인텔 고객사 동향), "
            "HBM4 개발 일정, DRAM·eSSD 매출 전망, 설비 투자(CAPA 확장), 재무(부채·현금흐름). "
            "삼성전자와 겹치는 공통 매크로는 가능한 한 제외하고 SK하이닉스 단독 이슈에 집중한다."
        ),
    },
]

SYSTEM_PROMPT = """\
너는 한국 반도체 주식 전문 애널리스트다.
제공된 뉴스 요약과 시장 데이터를 바탕으로 특정 종목의 지금 이 시점 가장 중요한 이슈 제목을 작성한다.

## 출력 규칙

**[규칙 A] 핵심 이슈 1~2개를 훅 스타일로**
제목은 30자 이내. 구체적인 키워드와 주가에 미치는 방향을 함께 담는다.

**[규칙 B] 이모지 활용**
- 🚀 신고가·급등 모멘텀
- 💡 반도체·기술 이슈
- 🏭 생산·파운드리·CAPA
- 🤝 고객사·파트너십·계약
- 💰 실적·재무·주주환원
- 📉 리스크·하락 요인

## 출력 형식

순수 JSON만 출력. 마크다운 코드블록 없이.

{"title": "제목 (30자 이내)"}
"""


def get_supabase_client():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        cfg_path = BASE_DIR / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            url = url or cfg.get("supabase", {}).get("url", "")
            key = key or cfg.get("supabase", {}).get("service_role_key", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 없음")
    return create_client(url, key)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_user_content(stock: dict, datetime_str: str) -> str:
    news_kospi = load_json(DATA_DIR / "news_summary_kospi.json")
    news_us = load_json(DATA_DIR / "news_summary_us.json")
    latest = load_json(DATA_DIR / "latest_kospi.json")

    market_snapshot = {k: latest[k] for k in ("sox", "dram_etf", "vix", "fear_greed", "usd_krw") if k in latest}

    ticker_ys = stock["ticker"] + ".KS"
    stock_data = next(
        (c for c in latest.get("kospi_candidates", []) if c.get("ticker") == ticker_ys),
        {}
    )
    stock_data = {k: v for k, v in stock_data.items() if "sparkline" not in k}

    return "\n".join([
        f"현재 날짜·시각: {datetime_str}",
        f"종목: {stock['name']} ({stock['ticker']})",
        f"종목 특화 포커스: {stock['focus']}",
        "",
        f"종목 데이터:\n{json.dumps(stock_data, ensure_ascii=False, indent=2)}",
        "",
        f"시장 지표:\n{json.dumps(market_snapshot, ensure_ascii=False, indent=2)}",
        "",
        f"코스피 뉴스 요약:\n{json.dumps(news_kospi, ensure_ascii=False, indent=2)}",
        "",
        f"미국 뉴스 요약:\n{json.dumps(news_us, ensure_ascii=False, indent=2)}",
    ])


def call_claude(client: anthropic.Anthropic, stock: dict, datetime_str: str) -> dict:
    user_content = build_user_content(stock, datetime_str)
    print(f"[briefing] Calling Claude for {stock['name']} (~{len(user_content)//4} tokens)")

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=256,
        thinking={"type": "disabled"},
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    )

    usage = response.usage
    if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
        print(f"[briefing] Cache hit: {usage.cache_read_input_tokens} tokens")
    elif hasattr(usage, "cache_creation_input_tokens") and usage.cache_creation_input_tokens:
        print(f"[briefing] Cache write: {usage.cache_creation_input_tokens} tokens")
    print(f"[briefing] Output: {usage.output_tokens} tokens")

    if not response.content:
        raise RuntimeError(f"Claude returned empty content for {stock['name']}")
    text = response.content[0].text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


def insert_and_cleanup(sb, stock: dict, analysis: dict) -> None:
    new_title = analysis["title"]

    # 최신 타이틀과 동일하면 중복 저장 안 함
    latest = (
        sb.table("stock_briefings")
        .select("title")
        .eq("ticker", stock["ticker"])
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    if latest.data and latest.data[0]["title"] == new_title:
        print(f"[briefing] Skip: {stock['name']} — 이전 타이틀과 동일, 저장 건너뜀")
        return

    sb.table("stock_briefings").insert({
        "ticker": stock["ticker"],
        "title": new_title,
        "generated_at": datetime.now(KST).isoformat(),
    }).execute()

    # 최신 MAX_HISTORY개만 유지 — 초과분 삭제
    all_rows = (
        sb.table("stock_briefings")
        .select("generated_at")
        .eq("ticker", stock["ticker"])
        .order("generated_at", desc=True)
        .execute()
    )
    if len(all_rows.data) > MAX_HISTORY:
        cutoff = all_rows.data[MAX_HISTORY]["generated_at"]
        (
            sb.table("stock_briefings")
            .delete()
            .eq("ticker", stock["ticker"])
            .lte("generated_at", cutoff)
            .execute()
        )
        print(f"[briefing] Cleanup: {stock['name']} — {len(all_rows.data) - MAX_HISTORY}개 삭제")

    print(f"[briefing] Inserted {stock['name']} → {analysis['title']}")


def main():
    datetime_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        cfg_path = BASE_DIR / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            api_key = cfg.get("anthropic", {}).get("api_key", "")
    if not api_key:
        print("[briefing] ERROR: ANTHROPIC_API_KEY 없음", file=sys.stderr)
        sys.exit(1)

    claude = anthropic.Anthropic(
        api_key=api_key,
        default_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    )

    try:
        sb = get_supabase_client()
    except RuntimeError as e:
        print(f"[briefing] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    for stock in STOCKS:
        try:
            analysis = call_claude(claude, stock, datetime_str)
            insert_and_cleanup(sb, stock, analysis)
            print(f"[briefing] Done: {stock['name']} — {analysis['title']}")
        except Exception as e:
            print(f"[briefing] ERROR ({stock['name']}): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
