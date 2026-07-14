#!/usr/bin/env python3
"""텔레그램 발송 전, 상세 브리핑 페이지가 실제로 배포되어 열리는지 확인한다.

실제 서비스 URL(doubleshot.space, Vercel)이 열릴 때까지 재시도한다.
배포 스텝이 끝났다고 곧바로 페이지가 열린다는 보장이 없어(CDN 반영 지연) 몇 차례
재시도는 필요하지만(2026-07-06: 10회 시도 제한 때문에 정상 배포된 페이지를 못 잡아
발송이 누락된 사고), 무제한 재시도는 반대로 "영원히 안 뜨는 페이지"를 못 걸러낸다
(2026-07-14: GitHub Pages 자체가 저장소에서 비활성화된 채로 이 스크립트가 gh-pages
URL을 무한 재시도해 잡이 멈추고 텔레그램이 끝내 발송되지 않은 사고 — 이후 확인
대상을 실제 서비스 URL로 바꾸고 상한을 둠). 상한 초과 시 조용히 넘어가지 않고
실패(exit 1)한다 — 무음 스킵보다 명시적 실패가 낫다.
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
MAX_ATTEMPTS = 60  # 10초 간격 60회 = 최대 10분


def get_web_base_url() -> str:
    base = os.environ.get("WEB_BASE_URL")
    if base:
        return base.rstrip("/")
    return "https://doubleshot.space"


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

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if is_live(url):
            print(f"✅ 확인 완료 (시도 {attempt})")
            sys.exit(0)
        if attempt < MAX_ATTEMPTS:
            print(f"⏳ 아직 미반영 (시도 {attempt}/{MAX_ATTEMPTS}) — {RETRY_INTERVAL_SEC}초 후 재시도")
            time.sleep(RETRY_INTERVAL_SEC)

    print(f"❌ {MAX_ATTEMPTS}회 시도 후에도 페이지가 열리지 않음 — 배포 실패로 간주하고 중단", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
