#!/usr/bin/env python3
"""
Fear & Greed Index 패치 스크립트

코스피 브리핑이 08:30 KST에 생성될 때 alternative.me API는 아직
당일 데이터를 배포하지 않은 상태(09:00 KST 배포)라서 전일 값이 들어간다.
이 스크립트는 09:05 KST 이후 실행되어 당일 값으로 HTML을 패치한다.

대상 파일:
  - web/briefings/{date}-kospi.html
  - web/index.html (kospi 브리핑이 포함된 경우)
"""

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pytz

BASE_DIR = Path(__file__).parent.parent
WEB_DIR = BASE_DIR / "web"
KST = pytz.timezone("Asia/Seoul")


def fetch_fear_greed() -> dict:
    """alternative.me에서 최신 Fear & Greed 데이터를 가져온다."""
    url = "https://api.alternative.me/fng/?limit=365"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = json.loads(resp.read().decode())
    entries = raw.get("data", [])
    if not entries:
        raise ValueError("Fear & Greed API returned empty data")

    def val_at(idx):
        return int(entries[idx]["value"]) if idx < len(entries) else None

    return {
        "value":          val_at(0),
        "prev":           val_at(1),
        "1w":             val_at(7),
        "1m":             val_at(30),
        "1y":             val_at(364),
        "timestamp":      entries[0].get("timestamp"),
        "classification": entries[0].get("value_classification"),
    }


def is_today(fg: dict, date_str: str) -> bool:
    """API 데이터의 타임스탬프가 오늘(KST 기준)인지 확인."""
    ts = int(fg.get("timestamp", 0))
    api_date = datetime.fromtimestamp(ts, tz=KST).strftime("%Y-%m-%d")
    return api_date == date_str


def patch_html(html_path: Path, new_fg: dict) -> bool:
    """
    HTML 파일의 window.MARKET_DATA 안에 있는 fearGreed 블록을 교체한다.
    변경이 발생하면 True, 변경 없으면 False 반환.
    """
    content = html_path.read_text(encoding="utf-8")

    # window.MARKET_DATA = { ... }; 블록 추출
    pattern = r'(window\.MARKET_DATA\s*=\s*)(\{[\s\S]*?\});'
    match = re.search(pattern, content)
    if not match:
        print(f"[patch_fg] window.MARKET_DATA not found in {html_path.name}", file=sys.stderr)
        return False

    prefix = match.group(1)
    old_json_str = match.group(2)

    try:
        market_data = json.loads(old_json_str)
    except json.JSONDecodeError as e:
        print(f"[patch_fg] JSON parse error in {html_path.name}: {e}", file=sys.stderr)
        return False

    old_fg = market_data.get("fearGreed", {})
    if old_fg.get("value") == new_fg["value"] and old_fg.get("timestamp") == new_fg["timestamp"]:
        print(f"[patch_fg] {html_path.name}: fearGreed already up-to-date (value={new_fg['value']})")
        return False

    market_data["fearGreed"] = new_fg
    new_json_str = json.dumps(market_data, ensure_ascii=False, indent=2)
    new_content = content.replace(
        match.group(0),
        f"{prefix}{new_json_str};",
        1,
    )

    html_path.write_text(new_content, encoding="utf-8")
    print(
        f"[patch_fg] {html_path.name}: fearGreed 패치 완료 "
        f"({old_fg.get('value')} → {new_fg['value']}, {old_fg.get('timestamp')} → {new_fg['timestamp']})"
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="Fear & Greed Index HTML 패치")
    parser.add_argument(
        "--date",
        default=datetime.now(KST).strftime("%Y-%m-%d"),
        help="패치 대상 날짜 (YYYY-MM-DD, 기본값: 오늘 KST)",
    )
    args = parser.parse_args()
    date_str = args.date

    print(f"[patch_fg] 실행 날짜: {date_str}")

    # Fear & Greed 최신 데이터 수집
    try:
        fg = fetch_fear_greed()
    except Exception as e:
        print(f"[patch_fg] API 호출 실패: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[patch_fg] API 응답: value={fg['value']}, timestamp={fg['timestamp']}, class={fg['classification']}")

    # 오늘 데이터 여부 확인
    if not is_today(fg, date_str):
        api_date = datetime.fromtimestamp(int(fg["timestamp"]), tz=KST).strftime("%Y-%m-%d")
        print(f"[patch_fg] API 데이터가 아직 오늘({date_str}) 기준이 아님 (API 날짜: {api_date}) — 종료")
        sys.exit(0)

    patched_any = False

    # 1. 오늘 코스피 브리핑 HTML 패치
    briefing_path = WEB_DIR / "briefings" / f"{date_str}-kospi.html"
    if briefing_path.exists():
        patched_any |= patch_html(briefing_path, fg)
    else:
        print(f"[patch_fg] 브리핑 파일 없음: {briefing_path}", file=sys.stderr)

    # 2. index.html 패치 (오늘 코스피 내용이 들어있는 경우만)
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        # index.html이 오늘 코스피 브리핑을 담고 있는지 확인
        index_content = index_path.read_text(encoding="utf-8")
        if f"{date_str}-kospi" in index_content or f"{date_str} KST 08" in index_content:
            patched_any |= patch_html(index_path, fg)
        else:
            print(f"[patch_fg] index.html에 오늘 코스피 데이터 없음 — 건너뜀")

    if patched_any:
        print("[patch_fg] 패치 완료")
    else:
        print("[patch_fg] 변경 사항 없음")


if __name__ == "__main__":
    main()
