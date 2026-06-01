#!/usr/bin/env python3
"""
브리핑 요약을 이메일로 발송한다 (Resend API).

- 관리자(RECIPIENT) 항상 포함
- RESEND_AUDIENCE_ID 설정 시 Resend Contacts에서 구독자 목록 조회 후 함께 발송

사용법:
  python3 scripts/send_email.py --type kospi
  python3 scripts/send_email.py --type us
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

RECIPIENTS = ["pulum0083@gmail.com"]
WEB_BASE   = "https://doubleshot.space"


def notify_admin_email(subject: str, body: str) -> None:
    """운영자(pulum0083@gmail.com)에게 오류 알림 이메일 발송. 실패해도 조용히 넘어감."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        config_file = BASE_DIR / "config.json"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                cfg = json.load(f)
            api_key = cfg.get("resend", {}).get("api_key", "")
    if not api_key:
        return
    try:
        payload = json.dumps({
            "from": "noreply@doubleshot.space",
            "to": ["pulum0083@gmail.com"],
            "subject": subject,
            "html": f"<pre style='font-family:sans-serif'>{body}</pre>",
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

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


def get_subscribers(api_key: str, audience_id: str) -> list[str]:
    """Resend Contacts API에서 구독 중인 이메일 목록 조회"""
    req = urllib.request.Request(
        f"https://api.resend.com/audiences/{audience_id}/contacts",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            emails = [c["email"] for c in data.get("data", []) if not c.get("unsubscribed")]
            print(f"[send_email] 구독자 {len(emails)}명 조회 완료")
            return emails
    except Exception as e:
        print(f"[send_email] Contacts 조회 실패: {e}", file=sys.stderr)
        notify_admin_email(
            "[Double-Shot] 구독자 목록 조회 실패",
            f"Resend Contacts API 오류로 구독자에게 이메일이 발송되지 않았어요.\n오류: {e}",
        )
        return []


def build_email(briefing_type: str, date_slug: str) -> tuple[str, str]:
    """(subject, html_body) 반환"""
    kst       = pytz.timezone("Asia/Seoul")
    today_str = datetime.now(kst).strftime("%Y.%m.%d")
    meta      = TYPE_META[briefing_type]
    link      = f"{WEB_BASE}/briefings/{date_slug}/"

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

    subject = f"{meta['emoji']} {reason_title}" if reason_title else f"{meta['emoji']} {meta['label']} | {today_str}"

    rows = ""
    rows += f"<tr><td style='font-size:13px;color:#888888;padding-bottom:12px;font-family:Arial,sans-serif;'>{meta['label']} | {today_str}</td></tr>"

    if direction:
        rows += f"<tr><td style='padding:4px 0;font-family:Arial,sans-serif;'><span style='font-size:14px;font-weight:700;color:#333333;'>&#128202; 예측: {direction} ({up_pct}%)</span><br/><span style='font-size:13px;color:#888888;'>신뢰도: {confidence}%</span></td></tr>"
        rows += "<tr><td style='padding:4px 0;'></td></tr>"

    if reason_title:
        rows += f"<tr><td style='font-family:Arial,sans-serif;font-size:14px;font-weight:700;color:#333333;padding:4px 0;'>💬 {reason_title}</td></tr>"
        rows += "<tr><td style='padding:4px 0;'></td></tr>"

    if reasons:
        rows += "<tr><td style='font-family:Arial,sans-serif;font-size:13px;color:#555555;padding:4px 0;font-weight:700;'>핵심 시그널:</td></tr>"
        for r in reasons[:3]:
            rows += f"<tr><td style='font-family:Arial,sans-serif;font-size:13px;line-height:1.8;color:#444444;padding:3px 0;'>&#8226; {strip_html(r)}</td></tr>"

    return subject, wrap_html(subject, rows, link)


def wrap_html(title: str, rows_html: str, link: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ko" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="UTF-8"/>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Double-Shot 브리핑</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f5f5;">
  <tr><td align="center" style="padding:24px 16px;">
    <table width="560" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;background:#ffffff;border:1px solid #e5e5e5;">
      <tr>
        <td bgcolor="#006EFF" style="padding:24px 28px;background:#006EFF;">
          <p style="margin:0 0 8px 0;font-family:Arial,sans-serif;font-size:11px;font-weight:700;color:rgba(255,255,255,0.8);letter-spacing:1px;">Double-Shot &#183; AI 투자 브리핑</p>
          <p style="margin:0;font-family:Arial,sans-serif;font-size:18px;font-weight:800;color:#ffffff;line-height:1.4;">{title}</p>
        </td>
      </tr>
      <tr>
        <td style="padding:20px 28px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            {rows_html}
          </table>
        </td>
      </tr>
      <tr>
        <td style="padding:16px 28px;border-top:1px solid #f0f0f0;background:#fafafa;">
          <a href="{link}" style="display:inline-block;background:#006EFF;color:#ffffff;text-decoration:none;font-family:Arial,sans-serif;font-size:14px;font-weight:700;padding:12px 24px;">전체 브리핑 보기 &#x2192;</a>
        </td>
      </tr>
      <tr>
        <td style="padding:14px 28px;font-family:Arial,sans-serif;font-size:11px;color:#bbbbbb;">
          Double-Shot &#183; AI 투자 브리핑 서비스
        </td>
      </tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""


def send_emails_batch(api_key: str, recipients: list[str], subject: str, html: str) -> int:
    """Resend batch API로 여러 수신자에게 개별 발송. 성공 건수 반환."""
    messages = [
        {
            "from":    "Double-Shot <noreply@doubleshot.space>",
            "to":      [r],
            "subject": subject,
            "html":    html,
            "headers": {
                "List-Unsubscribe": "<mailto:unsubscribe@doubleshot.space?subject=unsubscribe>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        }
        for r in recipients
    ]

    success = 0
    # Resend batch 최대 100개
    for i in range(0, len(messages), 100):
        batch = messages[i:i+100]
        payload = json.dumps(batch).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails/batch",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
                "User-Agent":    "daily30-briefing/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                success += len(result.get("data", []))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            if e.code == 429:
                notify_admin_email(
                    "[Double-Shot] 이메일 발송 한도 초과",
                    "Resend 무료 플랜 일일/월간 한도에 도달했어요.\n→ Resend 대시보드에서 플랜 업그레이드를 확인해 주세요.",
                )
            elif e.code in (401, 403):
                notify_admin_email(
                    f"[Double-Shot] 이메일 발송 실패 ({e.code})",
                    "RESEND_API_KEY가 유효하지 않거나 권한이 없어요.\n→ GitHub Secrets의 RESEND_API_KEY를 확인해 주세요.",
                )
            raise RuntimeError(f"Resend batch API 오류 ({e.code}): {body}")

    return success


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

    # 수신자 목록: 관리자 + Resend Contacts 구독자
    audience_id = os.environ.get("RESEND_AUDIENCE_ID")
    subscribers = get_subscribers(api_key, audience_id) if audience_id else []

    # 관리자는 항상 포함, 중복 제거
    recipients = list(dict.fromkeys(RECIPIENTS + subscribers))
    print(f"[send_email] 총 수신자 {len(recipients)}명 (관리자 1 + 구독자 {len(subscribers)})")

    try:
        sent = send_emails_batch(api_key, recipients, subject, html)
        print(f"[send_email] ✓ 발송 완료 → {sent}/{len(recipients)}명")
        print(f"[send_email]   제목: {subject}")
        if sent < len(recipients):
            notify_admin_email(
                "[Double-Shot] 이메일 일부 발송 실패",
                f"{sent}/{len(recipients)}명에게만 전송됐어요.\n→ Resend 대시보드 로그를 확인해 주세요.",
            )
    except RuntimeError as e:
        print(f"[send_email] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
