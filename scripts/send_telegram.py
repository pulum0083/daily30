#!/usr/bin/env python3
"""
Send briefing summary to Telegram.

인증 우선순위:
  1. 환경 변수  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  (GitHub Actions / CI)
  2. config.json  (로컬 실행)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


def load_credentials() -> tuple[str, str]:
    """Return (bot_token, chat_id) — env vars first, then config.json."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        return bot_token, chat_id

    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            cfg = json.load(f)
        try:
            return cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"]
        except KeyError:
            pass

    raise RuntimeError(
        "Telegram credentials not found.\n"
        "Set env vars TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, "
        "or fill config.json."
    )


def get_web_base_url() -> str:
    base = os.environ.get("WEB_BASE_URL")
    if base:
        return base.rstrip("/")

    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("web", {}).get("base_url", "").rstrip("/")

    return "https://pulum0083.github.io/daily30"


def send_message(bot_token: str, chat_id: str, text: str) -> dict:
    """Send a Telegram message via Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def build_fallback_message(briefing_type: str) -> str:
    """analysis_kospi/us/weekly.json 에서 텔레그램 메시지를 자동 생성한다."""
    from datetime import datetime
    import pytz

    web_url = get_web_base_url()
    today = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y.%m.%d")
    date_slug = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d")

    analysis_file = DATA_DIR / f"analysis_{briefing_type}.json"
    if not analysis_file.exists():
        # 마지막 수단: 단순 알림만
        labels = {"kospi": "🇰🇷 코스피", "us": "🇺🇸 미국 시장", "weekly": "📋 주간 리포트"}
        label = labels.get(briefing_type, "📊 브리핑")
        return (
            f"{label} 브리핑 | {today}\n\n"
            f"브리핑이 생성되었습니다.\n\n"
            f"🔗 상세 분석 → {web_url}/briefings/{'ko' if briefing_type == 'kospi' else briefing_type}/{date_slug}/"
        )

    with open(analysis_file, encoding="utf-8") as f:
        data = json.load(f)

    pred = data.get("prediction", {})
    direction = pred.get("direction", "알 수 없음")
    up_pct = pred.get("up_pct", "?")
    confidence = pred.get("confidence", "?")
    reason_title = data.get("reason_title", "")
    reasons = data.get("reasons", [])

    # HTML 태그 제거 (텔레그램 plain text용)
    import re
    def strip_html(text):
        return re.sub(r"<[^>]+>", "", str(text))

    if briefing_type == "kospi":
        header = f"🇰🇷 코스피 시초가 브리핑 | {today}"
        pred_line = f"📊 예측: {direction} ({up_pct}%)\n신뢰도: {confidence}%"
        link = f"{web_url}/briefings/ko/{date_slug}/"
    elif briefing_type == "us":
        header = f"🇺🇸 미국 시장 브리핑 | {today}"
        pred_line = f"📊 예측: {direction} ({up_pct}%)\n신뢰도: {confidence}%"
        link = f"{web_url}/briefings/us/{date_slug}/"
    else:
        header = f"📋 주간 리포트 | {today}"
        pred_line = ""
        link = f"{web_url}/briefings/weekly/{date_slug}/"

    bullet_lines = "\n".join(
        f"• {strip_html(r)}" for r in reasons[:3]
    )

    parts = [header, "", pred_line] if pred_line else [header]
    if reason_title:
        parts += ["", f"〔{strip_html(reason_title)}〕"]
    if bullet_lines:
        parts += ["", bullet_lines]
    parts += ["", f"🔗 상세 분석 → {link}"]

    return "\n".join(parts)


def already_sent_today(briefing_type: str) -> bool:
    """Return True if a message was already sent today (KST) for this type."""
    from datetime import datetime
    import pytz
    today = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    flag_file = DATA_DIR / f"telegram_sent_{briefing_type}_{today}.flag"
    return flag_file.exists()


def mark_sent_today(briefing_type: str) -> None:
    from datetime import datetime
    import pytz
    today = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    flag_file = DATA_DIR / f"telegram_sent_{briefing_type}_{today}.flag"
    flag_file.touch()


def main():
    parser = argparse.ArgumentParser(description="Send briefing to Telegram")
    parser.add_argument("--type", choices=["kospi", "us", "weekly"], required=True)
    parser.add_argument(
        "--message",
        type=str,
        default=None,
        help="Message text. If omitted, reads data/telegram_message_{type}.txt",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Send even if already sent today",
    )
    args = parser.parse_args()

    # 하루 1회 발송 제한 — 중복 실행 방지
    if not args.force and already_sent_today(args.type):
        print(f"[send_telegram] ⚠️  Already sent today (type={args.type}). Skipping. Use --force to override.")
        return

    try:
        bot_token, chat_id = load_credentials()
    except RuntimeError as e:
        print(f"[send_telegram] {e}", file=sys.stderr)
        sys.exit(1)

    if args.message:
        message_text = args.message
    else:
        msg_file = DATA_DIR / f"telegram_message_{args.type}.txt"
        if msg_file.exists():
            with open(msg_file, encoding="utf-8") as f:
                message_text = f.read()
        else:
            # txt 파일 없으면 analysis JSON에서 자동 생성 (fallback)
            print(f"[send_telegram] Message file not found, trying fallback from JSON...", file=sys.stderr)
            message_text = build_fallback_message(args.type)

    # Replace placeholder URL if present
    web_url = get_web_base_url()
    message_text = message_text.replace("{web.base_url}", web_url)

    try:
        result = send_message(bot_token, chat_id, message_text)
        if result.get("ok"):
            mark_sent_today(args.type)
            print(f"[send_telegram] ✓ Sent (type={args.type})")
        else:
            print(f"[send_telegram] Telegram API error: {result}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[send_telegram] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
