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

    return "https://bejewelled-toffee-87de55.netlify.app"


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
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Send briefing to Telegram")
    parser.add_argument("--type", choices=["kospi", "us", "weekly"], required=True)
    parser.add_argument(
        "--message",
        type=str,
        default=None,
        help="Message text. If omitted, reads data/telegram_message_{type}.txt",
    )
    args = parser.parse_args()

    try:
        bot_token, chat_id = load_credentials()
    except RuntimeError as e:
        print(f"[send_telegram] {e}", file=sys.stderr)
        sys.exit(1)

    if args.message:
        message_text = args.message
    else:
        msg_file = DATA_DIR / f"telegram_message_{args.type}.txt"
        if not msg_file.exists():
            print(f"[send_telegram] Message file not found: {msg_file}", file=sys.stderr)
            sys.exit(1)
        with open(msg_file, encoding="utf-8") as f:
            message_text = f.read()

    # Replace placeholder URL if present
    web_url = get_web_base_url()
    message_text = message_text.replace("{web.base_url}", web_url)

    try:
        result = send_message(bot_token, chat_id, message_text)
        if result.get("ok"):
            print(f"[send_telegram] ✓ Sent (type={args.type})")
        else:
            print(f"[send_telegram] Telegram API error: {result}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[send_telegram] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
