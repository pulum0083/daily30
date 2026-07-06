#!/usr/bin/env python3
"""텔레그램 발송 전, 상세 브리핑 페이지가 실제로 배포되어 열리는지 확인한다.

GitHub Pages 배포(peaceiris/actions-gh-pages) 직후에도 CDN 반영까지 수십 초~
수 분 지연될 수 있어, 배포 스텝이 끝났다고 곧바로 페이지가 열린다는 보장이 없다.
이 스크립트는 페이지가 실제로 열릴 때까지(200 OK) 재시도한다 — 시간/횟수
제한으로 포기하지 않는다. 잘못된 조기 포기로 텔레그램 발송이 스킵되는 것을
막기 위함(2026-07-06: 10회 시도 제한 때문에 정상 배포된 페이지를 못 잡아
발송이 누락된 사고). 워크플로우 잡 자체의 타임아웃이 최종 안전망 역할을 한다.
"""

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pytz

BASE_DIR = Path(__file__).parent.parent

URL_MAP = {
    "kospi": "kospi",
    "us": "us",
    "kospi-close": "close",
}

RETRY_INTERVAL_SEC = 10


def get_web_base_url() -> str:
    base = os.environ.get("WEB_BASE_URL")
    if base:
        return base.rstrip("/")
    return "https://pulum0083.github.io/daily30"


def build_url(briefing_type: str) -> str:
    date_slug = datetime.now(pytz.timezone("Asia/Seoul")).strftime("%Y-%m-%d")
    slug = URL_MAP.get(briefing_type)
    if not slug:
        raise ValueError(f"알 수 없는 브리핑 타입: {briefing_type}")
    return f"{get_web_base_url()}/briefings/{date_slug}/{slug}/"


def is_live(url: str) -> bool:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError:
        return False
    except urllib.error.URLError:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=list(URL_MAP.keys()))
    args = parser.parse_args()

    url = build_url(args.type)
    print(f"상세 페이지 라이브 확인: {url}")

    attempt = 0
    while True:
        attempt += 1
        if is_live(url):
            print(f"✅ 확인 완료 (시도 {attempt})")
            sys.exit(0)
        print(f"⏳ 아직 미반영 (시도 {attempt}) — {RETRY_INTERVAL_SEC}초 후 재시도")
        time.sleep(RETRY_INTERVAL_SEC)


if __name__ == "__main__":
    main()
