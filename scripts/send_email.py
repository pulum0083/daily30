#!/usr/bin/env python3
"""
브리핑 요약을 이메일로 발송한다 (Resend API).

사용법:
  python3 scripts/send_email.py --type kospi
  python3 scripts/send_email.py --type us
  python3 scripts/send_email.py --type weekly
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

RECIPIENT  = "pulum0083@gmail.com"
WEB_BASE   = "https://daily30-ecru.vercel.app"

TYPE_META = {
    "kospi":  {"label": "🇰🇷 코스피 시초가 브리핑", "emoji": "📈"},
    "us":     {"label": "🇺🇸 미국 시장 브리핑",     "emoji": "🌐"},
    "weekly": {"label": "📋 주간 리포트",            "emoji": "📊"},
}


def load_api_key() -> str:
    key = os.environ.get("RESEND_API_KEY")
    if key:
        return key
    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            cfg = json.load(f)
        key = cfg.get("resend", {}).get("api_key", "")
        if key:
            return key
    raise RuntimeError("RESEND_API_KEY를 찾을 수 없습니다.")


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", str(text))


def build_email(briefing_type: str, date_slug: str) -> tuple[str, str]:
    """(subject, html_body) 반환"""
    kst       = pytz.timezone("Asia/Seoul")
    today_str = datetime.now(kst).strftime("%Y.%m.%d")
    meta      = TYPE_META[briefing_type]
    slug      = 'ko' if briefing_type == 'kospi' else briefing_type
    link      = f"{WEB_BASE}/briefings/{slug}/{date_slug}/"

    # ── 분석 JSON 읽기 ──
    analysis_file = DATA_DIR / f"analysis_{briefing_type}.json"
    if not analysis_file.exists():
        subject = f"{meta['emoji']} {meta['label']} | {today_str}"
        body    = f'<p>브리핑이 생성되었습니다.</p><p><a href="{link}">전체 보기 →</a></p>'
        return subject, wrap_html(subject, body, link)

    with open(analysis_file, encoding="utf-8") as f:
        data = json.load(f)

    reason_title = strip_html(data.get("reason_title", ""))
    pred         = data.get("prediction", {})
    direction    = pred.get("direction", "")
    up_pct       = pred.get("up_pct", "")
    confidence   = pred.get("confidence", "")
    reasons      = data.get("reasons", [])

    # 제목: reason_title 사용
    subject = f"{meta['emoji']} {reason_title}" if reason_title else f"{meta['emoji']} {meta['label']} | {today_str}"

    # 본문 블록
    lines = []
    lines.append(f"<b>{meta['label']}</b> | {today_str}")
    lines.append("")

    if direction:
        lines.append(f"📊 예측: <b>{direction}</b> ({up_pct}%)")
        lines.append(f"신뢰도: {confidence}%")
        lines.append("")

    if reason_title:
        lines.append(f"💬 <b>{reason_title}</b>")
        lines.append("")

    if reasons:
        lines.append("핵심 시그널:")
        for r in reasons[:3]:
            lines.append(f"• {strip_html(r)}")

    body_text = "\n".join(lines)
    return subject, wrap_html(subject, body_text, link)


def wrap_html(title: str, body_text: str, link: str) -> str:
    rows = ""
    for line in body_text.split("\n"):
        if line == "":
            rows += "<tr><td style='padding:4px 0'></td></tr>"
        else:
            rows += f"<tr><td style='font-size:14px;line-height:1.7;color:#333'>{line}</td></tr>"

    return f"""
    <div style="font-family:'Apple SD Gothic Neo',sans-serif;max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e5e5;border-radius:12px;overflow:hidden">
      <div style="background:linear-gradient(135deg,#006EFF,#7C3AED);padding:24px 28px">
        <div style="color:rgba(255,255,255,.7);font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px">Daily30' · AI 투자 브리핑</div>
        <div style="color:#fff;font-size:20px;font-weight:800;line-height:1.3">{title}</div>
      </div>
      <div style="padding:24px 28px">
        <table style="width:100%;border-collapse:collapse">{rows}</table>
      </div>
      <div style="padding:16px 28px;border-top:1px solid #f0f0f0;background:#fafafa">
        <a href="{link}" style="display:inline-block;background:#006EFF;color:#fff;text-decoration:none;font-size:14px;font-weight:700;padding:12px 24px;border-radius:8px">전체 브리핑 보기 →</a>
      </div>
      <div style="padding:16px 28px;font-size:11px;color:#aaa">
        Daily30' · 개인 투자 비서 · 언제든 구독 해지 가능
      </div>
    </div>
    """


def send_email(api_key: str, subject: str, html: str) -> dict:
    payload = json.dumps({
        "from":    "Daily30' <onboarding@resend.dev>",
        "to":      [RECIPIENT],
        "subject": subject,
        "html":    html,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            "User-Agent":    "daily30-briefing/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise RuntimeError(f"Resend API 오류 ({e.code}): {body}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["kospi", "us", "weekly"], required=True)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (기본: 오늘 KST)")
    args = parser.parse_args()

    kst       = pytz.timezone("Asia/Seoul")
    date_slug = args.date or datetime.now(kst).strftime("%Y-%m-%d")

    try:
        api_key = load_api_key()
    except RuntimeError as e:
        print(f"[send_email] {e}", file=sys.stderr)
        sys.exit(1)

    subject, html = build_email(args.type, date_slug)

    try:
        result = send_email(api_key, subject, html)
        print(f"[send_email] ✓ 발송 완료 → {RECIPIENT} (id={result.get('id', '?')})")
        print(f"[send_email]   제목: {subject}")
    except RuntimeError as e:
        print(f"[send_email] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
