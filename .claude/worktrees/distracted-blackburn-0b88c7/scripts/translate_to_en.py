#!/usr/bin/env python3
"""
Translate Korean analysis JSON to English using Claude API.

Reads data/analysis_{type}.json (Korean) and produces:
  - data/analysis_en_{type}.json   — English analysis JSON
  - data/telegram_message_en_{type}.txt — English Telegram message

Usage:
    python3 scripts/translate_to_en.py --type kospi [--date 2026-05-06]
    python3 scripts/translate_to_en.py --type us
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
KST = pytz.timezone("Asia/Seoul")

TRANSLATE_SYSTEM_PROMPT = """\
You are a professional financial translator specializing in Korean-to-English translation of stock market briefings.

Rules:
1. Translate all Korean text to natural, professional English.
2. Preserve all HTML tags exactly as-is (e.g., <b>+1.5%</b> stays <b>+1.5%</b>).
3. Preserve all numeric values, prices, percentages, and ticker symbols exactly.
4. Convert Korean direction labels: "상승 우위" → "Bullish", "하락 우위" → "Bearish", "중립" or "혼조" → "Neutral".
5. Translate "해요체" Korean into concise, natural English sentences (not literally).
6. Keep the same JSON structure and field names.
7. Output pure JSON only — no markdown fences, no extra text.
"""


def load_config() -> dict:
    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        cfg = load_config()
        key = cfg.get("anthropic", {}).get("api_key", "")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. "
            "Set the environment variable or add anthropic.api_key to config.json"
        )
    return key


def get_web_base_url() -> str:
    base = os.environ.get("WEB_BASE_URL", "")
    if base:
        return base.rstrip("/")
    cfg = load_config()
    return cfg.get("web", {}).get("base_url", "https://doubleshot.space").rstrip("/")


def load_korean_analysis(briefing_type: str) -> dict:
    path = DATA_DIR / f"analysis_{briefing_type}.json"
    if not path.exists():
        raise FileNotFoundError(f"Korean analysis not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_translation_request(analysis: dict, briefing_type: str) -> str:
    """Build the fields that need translation — skip numeric/structural fields."""
    translatable = {
        "prediction": {
            "direction": analysis.get("prediction", {}).get("direction", ""),
        },
        "reason_title": analysis.get("reason_title", ""),
        "reasons": analysis.get("reasons", []),
        "stock_picks": [
            {
                "name": p.get("name", ""),
                "signal": p.get("signal", ""),
                "scenario_tag": p.get("scenario_tag", ""),
                "scenario": p.get("scenario", ""),
                "action_guide": p.get("action_guide", ""),
            }
            for p in analysis.get("stock_picks", [])
        ],
    }

    if briefing_type == "us":
        translatable["premarket_highs"] = [
            {
                "name": h.get("name", ""),
                "reason": h.get("reason", ""),
            }
            for h in analysis.get("premarket_highs", [])
        ]

    return json.dumps(translatable, ensure_ascii=False, indent=2)


def merge_translation(original: dict, translated: dict, briefing_type: str) -> dict:
    """Merge translated text fields back into the full original JSON structure."""
    result = json.loads(json.dumps(original))  # deep copy

    # prediction.direction
    result["prediction"]["direction"] = (
        translated.get("prediction", {}).get("direction")
        or original["prediction"]["direction"]
    )

    # reason_title, reasons
    result["reason_title"] = translated.get("reason_title", original.get("reason_title", ""))
    result["reasons"] = translated.get("reasons", original.get("reasons", []))

    # stock_picks — merge text fields only, keep numeric fields from original
    orig_picks = original.get("stock_picks", [])
    trans_picks = translated.get("stock_picks", [])
    merged_picks = []
    for i, orig in enumerate(orig_picks):
        pick = dict(orig)
        if i < len(trans_picks):
            t = trans_picks[i]
            pick["name"] = t.get("name") or orig.get("name", "")
            pick["signal"] = t.get("signal") or orig.get("signal", "")
            pick["scenario_tag"] = t.get("scenario_tag") or orig.get("scenario_tag", "")
            pick["scenario"] = t.get("scenario") or orig.get("scenario", "")
            pick["action_guide"] = t.get("action_guide") or orig.get("action_guide", "")
        merged_picks.append(pick)
    result["stock_picks"] = merged_picks

    # premarket_highs (US only)
    if briefing_type == "us":
        orig_highs = original.get("premarket_highs", [])
        trans_highs = translated.get("premarket_highs", [])
        merged_highs = []
        for i, orig in enumerate(orig_highs):
            high = dict(orig)
            if i < len(trans_highs):
                t = trans_highs[i]
                high["name"] = t.get("name") or orig.get("name", "")
                high["reason"] = t.get("reason") or orig.get("reason", "")
            merged_highs.append(high)
        result["premarket_highs"] = merged_highs

    return result


def call_translate(analysis: dict, briefing_type: str) -> dict:
    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    payload = build_translation_request(analysis, briefing_type)
    user_msg = f"Translate the following Korean financial briefing JSON to English:\n\n{payload}"

    print(f"[translate_to_en] Calling Claude for translation (type={briefing_type})")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Haiku: fast + cheap for translation
        max_tokens=2048,
        system=TRANSLATE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    usage = response.usage
    print(f"[translate_to_en] Input: {usage.input_tokens}, Output: {usage.output_tokens} tokens")

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    return json.loads(raw)


def save_english_analysis(briefing_type: str, analysis_en: dict) -> None:
    path = DATA_DIR / f"analysis_en_{briefing_type}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(analysis_en, f, ensure_ascii=False, indent=2)
    print(f"[translate_to_en] Saved → {path}")


def build_en_telegram_message(briefing_type: str, date_str: str, analysis_en: dict) -> str:
    def strip_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", str(text))

    web_base = get_web_base_url()
    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y.%m.%d")

    pred = analysis_en.get("prediction", {})
    direction = pred.get("direction", "Unknown")
    up_pct = pred.get("up_pct", "?")
    confidence = pred.get("confidence", "?")
    reason_title = strip_html(analysis_en.get("reason_title", ""))
    reasons = analysis_en.get("reasons", [])

    dir_emoji = "📈" if direction == "Bullish" else ("📉" if direction == "Bearish" else "📊")
    divider = "─" * 20

    if briefing_type == "kospi":
        header = f"🇰🇷 KOSPI Opening Brief | {date_display}"
        link = f"{web_base}/briefings/ko/{date_str}/"
    else:
        header = f"🇺🇸 US Market Brief | {date_display}"
        link = f"{web_base}/briefings/us/{date_str}/"

    lines = [
        header,
        divider,
        f"{dir_emoji} Forecast: <b>{direction} ({up_pct}%)</b>",
        f"Confidence: <b>{confidence}%</b>",
    ]

    if reason_title:
        lines += [divider, f"💬 {reason_title}"]

    if reasons:
        lines += ["", "Key Signals:"]
        for r in reasons[:4]:
            lines.append(f"• {strip_html(r)}")

    lines += [divider, f"🔗 Full Analysis → {link}"]

    return "\n".join(lines)


def save_en_telegram_message(briefing_type: str, date_str: str, analysis_en: dict) -> None:
    msg = build_en_telegram_message(briefing_type, date_str, analysis_en)
    path = DATA_DIR / f"telegram_message_en_{briefing_type}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(msg)
    print(f"[translate_to_en] EN Telegram message saved → {path}")


def main():
    parser = argparse.ArgumentParser(description="Translate Korean analysis to English")
    parser.add_argument("--type", choices=["kospi", "us"], required=True)
    parser.add_argument("--date", default=None, help="Date string (YYYY-MM-DD)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(KST).strftime("%Y-%m-%d")

    try:
        analysis_ko = load_korean_analysis(args.type)
    except FileNotFoundError as e:
        print(f"[translate_to_en] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        translated_fields = call_translate(analysis_ko, args.type)
    except Exception as e:
        print(f"[translate_to_en] ERROR calling Claude: {e}", file=sys.stderr)
        sys.exit(1)

    analysis_en = merge_translation(analysis_ko, translated_fields, args.type)
    save_english_analysis(args.type, analysis_en)
    save_en_telegram_message(args.type, date_str, analysis_en)

    print(f"[translate_to_en] Done. direction={analysis_en.get('prediction', {}).get('direction')}")


if __name__ == "__main__":
    main()
