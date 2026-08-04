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
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# 전송 재시도 — 2026-08-05 07:32 코스피 브리핑이 read timeout 한 번에 미발송된 사고 대응.
# 워크플로우의 텔레그램 스텝은 continue-on-error라 실패해도 잡이 초록색으로 끝나므로,
# 일시적 네트워크 요동은 여기서 흡수해야 한다.
SEND_MAX_ATTEMPTS = 3
SEND_TIMEOUT_SEC = 30      # 15초는 응답이 느릴 뿐인 요청까지 잘랐다 — 여유를 둔다
SEND_BACKOFF_SEC = 3       # 시도 간 대기: 3s → 9s


def load_credentials(lang: str = "ko") -> tuple[str, str]:
    """Return (bot_token, chat_id).

    For lang='en', reads TELEGRAM_CHAT_ID_EN (env) or telegram.chat_id_en (config.json).
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if lang == "en":
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN_EN") or bot_token
        chat_id = os.environ.get("TELEGRAM_CHAT_ID_EN", "")
        if not bot_token or not chat_id:
            config_file = BASE_DIR / "config.json"
            if config_file.exists():
                with open(config_file, encoding="utf-8") as f:
                    cfg = json.load(f)
                if not chat_id:
                    chat_id = cfg.get("telegram", {}).get("chat_id_en", "")
                if not bot_token:
                    bot_token = (
                        cfg.get("telegram", {}).get("bot_token_en", "")
                        or cfg.get("telegram", {}).get("bot_token", "")
                    )
        if not chat_id:
            raise RuntimeError(
                "English Telegram channel not configured.\n"
                "Set env var TELEGRAM_CHAT_ID_EN, "
                "or add telegram.chat_id_en to config.json."
            )
        if not bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set.")
        return bot_token, chat_id

    # Korean channel (default)
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
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
        # 링크 프리뷰를 켜되 썸네일 없는 '텍스트 카드'로 표시한다. 브리핑 페이지는 og:image를
        # 내보내지 않으므로(generate_html no_og_image) 텔레그램이 도메인·제목·설명만 그린다.
        # prefer_small_media는 혹시 다른 이미지가 잡혀도 크게 뜨지 않게 하는 안전장치.
        "link_preview_options": json.dumps({"is_disabled": False, "prefer_small_media": True}),
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")

    # 재시도는 중복 발송 위험을 감수한다. read timeout은 "요청이 도달하지 못했다"와
    # "도달했는데 응답만 못 읽었다"를 구분할 수 없고, sendMessage에는 멱등키가 없다.
    # 미발송(구독자가 브리핑을 아예 못 받음)이 중복보다 훨씬 해로우므로 재시도를 택한다.
    last_err = None
    for attempt in range(1, SEND_MAX_ATTEMPTS + 1):
        req = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=SEND_TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            # 4xx는 토큰·chat_id·본문 오류라 재시도해도 결과가 같다 — 즉시 포기.
            if e.code < 500:
                raise RuntimeError(f"HTTP {e.code}: {body}") from e
            last_err = RuntimeError(f"HTTP {e.code}: {body}")
        except Exception as e:  # 타임아웃·연결 끊김 등 일시적 네트워크 오류
            last_err = RuntimeError(str(e))

        if attempt < SEND_MAX_ATTEMPTS:
            wait = SEND_BACKOFF_SEC * (3 ** (attempt - 1))
            print(
                f"[send_telegram] 전송 실패 ({attempt}/{SEND_MAX_ATTEMPTS}): {last_err} "
                f"— {wait}초 후 재시도",
                file=sys.stderr,
            )
            time.sleep(wait)

    raise RuntimeError(f"{SEND_MAX_ATTEMPTS}회 시도 모두 실패: {last_err}")


def send_admin_alert(message: str) -> None:
    """전송 실패를 관리자 텔레그램으로 알린다. 키 미설정이면 조용히 건너뜀.

    브리핑 전송 스텝은 continue-on-error라 실패해도 잡이 success로 끝난다 —
    이 알림이 없으면 로그를 직접 열기 전까지 미발송을 알 방법이 없다.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if not token or not chat_id:
        print("[send_telegram] 관리자 알림 키 미설정 — 알림 건너뜀", file=sys.stderr)
        return
    try:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=10)
        print("[send_telegram] 관리자 알림 발송 완료", file=sys.stderr)
    except Exception as e:
        # 알림 실패가 원래 오류를 가리면 안 된다.
        print(f"[send_telegram] 관리자 알림 실패: {e}", file=sys.stderr)


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
        labels = {"kospi": "🇰🇷 코스피", "us": "🇺🇸 미국 시장", "weekly": "📋 주간 리포트", "kospi-close": "🇰🇷 코스피 마감"}
        label = labels.get(briefing_type, "📊 브리핑")
        url_map = {"kospi": f"{date_slug}/kospi", "us": f"{date_slug}/us", "kospi-close": f"{date_slug}/close"}
        path = url_map.get(briefing_type, f"weekly/{date_slug}")
        return (
            f"{label} 브리핑 | {today}\n\n"
            f"브리핑이 생성되었습니다.\n\n"
            f"🔗 상세 분석 → {web_url}/briefings/{path}/"
        )

    with open(analysis_file, encoding="utf-8") as f:
        data = json.load(f)

    pred = data.get("prediction", {})
    direction = pred.get("direction", "알 수 없음")
    up_pct = pred.get("up_pct", "?")
    down_pct = pred.get("down_pct", "?")
    confidence = pred.get("confidence", "?")
    reason_title = data.get("reason_title", "")
    reasons = data.get("reasons", [])

    import re
    def strip_html(text):
        return re.sub(r"<[^>]+>", "", str(text))

    # 방향에 맞는 확률 표기: 상승 우위 → up_pct, 하락 우위 → down_pct
    dir_pct = down_pct if "하락" in str(direction) else up_pct
    dir_emoji = "📈" if "상승" in str(direction) else ("📉" if "하락" in str(direction) else "📊")
    divider = "─" * 20

    if briefing_type == "kospi":
        header = f"🇰🇷 코스피 예측 브리핑 | {today}"
        pred_line = f"{dir_emoji} 예측: <b>{direction} ({dir_pct}%)</b>\n신뢰도: <b>{confidence}%</b>"
        link = f"{web_url}/briefings/{date_slug}/kospi/"
    elif briefing_type == "us":
        header = f"🇺🇸 미국 시장 브리핑 | {today}"
        pred_line = f"{dir_emoji} 예측: <b>{direction} ({dir_pct}%)</b>\n신뢰도: <b>{confidence}%</b>"
        link = f"{web_url}/briefings/{date_slug}/us/"
    elif briefing_type == "kospi-close":
        header = f"🇰🇷 코스피 마감 브리핑 | {today}"
        pred_line = f"{dir_emoji} {direction}" if direction else ""
        link = f"{web_url}/briefings/{date_slug}/close/"
    else:
        header = f"📋 주간 리포트 | {today}"
        pred_line = ""
        link = f"{web_url}/briefings/weekly/{date_slug}/"

    parts = [header, divider, pred_line] if pred_line else [header]
    if reason_title:
        parts += [divider, f"💬 {strip_html(reason_title)}"]
    if reasons:
        parts += ["", "핵심 시그널:"]
        parts += [f"• {strip_html(r)}" for r in reasons[:3]]
    parts += [divider, f"🔗 상세 분석 → {link}"]

    return "\n".join(parts)


GURU_QUOTES_FILE = DATA_DIR / "guru_quotes.json"
QUOTE_TODAY_FILE = DATA_DIR / "quote_today.json"
SENT_LOG_FILE = DATA_DIR / "telegram_sent_log.json"


def pick_quote() -> str:
    """오늘 코스피 브리핑이 뽑아둔 quote_today.json을 우선 쓰고,
    없거나 날짜가 오늘이 아니면 guru_quotes.json에서 랜덤으로 뽑는다.
    (웹·텔레그램이 같은 날 다른 명언을 보여주지 않도록 동기화 — kospi 타입만 quote_today.json을 씀)"""
    import random
    import pytz
    from datetime import datetime

    if QUOTE_TODAY_FILE.exists():
        try:
            with open(QUOTE_TODAY_FILE, encoding="utf-8") as f:
                today_quote = json.load(f)
            today_str = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d")
            if (
                isinstance(today_quote, dict)
                and today_quote.get("date") == today_str
                and today_quote.get("quote")
                and today_quote.get("author")
            ):
                return f"\n\n━━━━━━━━━━━━━━━━━━━━\n💡 <i>\"{today_quote['quote']}\"</i>\n— {today_quote['author']}"
        except (json.JSONDecodeError, OSError):
            pass

    if not GURU_QUOTES_FILE.exists():
        return ""
    try:
        with open(GURU_QUOTES_FILE, encoding="utf-8") as f:
            quotes = json.load(f)
    except (json.JSONDecodeError, OSError):
        return ""
    if not isinstance(quotes, list) or not quotes:
        return ""
    item = random.choice(quotes)
    if not isinstance(item, dict) or not item.get("quote") or not item.get("author"):
        return ""
    return f"\n\n━━━━━━━━━━━━━━━━━━━━\n💡 <i>\"{item['quote']}\"</i>\n— {item['author']}"


def _load_sent_log() -> dict:
    if SENT_LOG_FILE.exists():
        with open(SENT_LOG_FILE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def _save_sent_log(log: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SENT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def already_sent_today(briefing_type: str, lang: str = "ko") -> bool:
    """Return True if a message was already sent today (KST) for this type/lang.

    telegram_sent_log.json에 날짜를 기록하여 git에 커밋 — GitHub Actions
    ephemeral 환경에서도 체크아웃 시 이전 발송 기록을 읽을 수 있다.
    """
    from datetime import datetime
    import pytz
    today = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    log = _load_sent_log()
    return log.get(briefing_type, {}).get(lang) == today


def mark_sent_today(briefing_type: str, lang: str = "ko") -> None:
    from datetime import datetime
    import pytz
    today = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    log = _load_sent_log()
    if briefing_type not in log:
        log[briefing_type] = {}
    log[briefing_type][lang] = today
    _save_sent_log(log)


def main():
    parser = argparse.ArgumentParser(description="Send briefing to Telegram")
    parser.add_argument("--type", choices=["kospi", "us", "weekly", "kospi-close"], required=True)
    parser.add_argument(
        "--lang", choices=["ko", "en"], default="ko",
        help="Language channel: 'ko' (default) or 'en' (TELEGRAM_CHAT_ID_EN)",
    )
    parser.add_argument(
        "--message",
        type=str,
        default=None,
        help="Message text. If omitted, reads data/telegram_message_{lang}_{type}.txt",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Send even if already sent today",
    )
    args = parser.parse_args()

    # 하루 1회 발송 제한 — 중복 실행 방지
    if not args.force and already_sent_today(args.type, args.lang):
        print(f"[send_telegram] ⚠️  Already sent today (type={args.type}, lang={args.lang}). Skipping. Use --force to override.")
        return

    try:
        bot_token, chat_id = load_credentials(args.lang)
    except RuntimeError as e:
        print(f"[send_telegram] {e}", file=sys.stderr)
        sys.exit(1)

    if args.message:
        message_text = args.message
    else:
        # kospi-close 전용 파일명 / EN / KO
        if args.type == "kospi-close":
            msg_file = DATA_DIR / "telegram_message_kospi_close.txt"
        elif args.lang == "en":
            msg_file = DATA_DIR / f"telegram_message_en_{args.type}.txt"
        else:
            msg_file = DATA_DIR / f"telegram_message_{args.type}.txt"

        if msg_file.exists():
            with open(msg_file, encoding="utf-8") as f:
                message_text = f.read()
        else:
            # txt 파일 없으면 analysis JSON에서 자동 생성 (fallback, KO only)
            print(f"[send_telegram] Message file not found, trying fallback from JSON...", file=sys.stderr)
            message_text = build_fallback_message(args.type)

    # Replace placeholder URL if present
    web_url = get_web_base_url()
    message_text = message_text.replace("{web.base_url}", web_url)

    # 일회성 공지 추가 (파일이 있으면 붙이고 삭제)
    notice_file = DATA_DIR / "telegram_notice_once.txt"
    if notice_file.exists():
        notice_text = notice_file.read_text(encoding="utf-8").strip()
        if notice_text:
            message_text = message_text.rstrip() + "\n\n" + notice_text
        notice_file.unlink()

    # 명언 추가
    message_text = message_text.rstrip() + pick_quote()

    # ── 날짜 유효성 검사: 오늘 날짜가 아닌 stale 메시지 발송 차단 ──
    if not args.force:
        import re
        import pytz
        today_str = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y.%m.%d")
        # 메시지 전체에서 날짜 패턴 추출 (예: 2026.04.27)
        date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", message_text)
        if date_match and date_match.group(1) != today_str:
            print(
                f"[send_telegram] ❌ Stale message detected: content date={date_match.group(1)}, today={today_str}. "
                f"Aborting to prevent sending outdated briefing. Use --force to override.",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        result = send_message(bot_token, chat_id, message_text)
        if result.get("ok"):
            mark_sent_today(args.type, args.lang)
            print(f"[send_telegram] ✓ Sent (type={args.type}, lang={args.lang})")
        else:
            print(f"[send_telegram] Telegram API error: {result}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[send_telegram] ERROR: {e}", file=sys.stderr)
        # 러너는 UTC라 date는 반드시 KST로 — 07:30 브리핑이 전날 날짜로 안내되는 것을 막는다.
        import pytz
        today_kst = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d")
        send_admin_alert(
            f"🚨 텔레그램 미발송 (type={args.type}, lang={args.lang})\n{e}\n"
            f"복구: gh workflow run telegram-resend.yml "
            f"-f briefing_type={args.type} -f date={today_kst}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
