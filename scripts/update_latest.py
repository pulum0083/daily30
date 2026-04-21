#!/usr/bin/env python3
"""
브리핑 생성 후 web/data/latest.json을 업데이트한다.
api/subscribe.mjs가 이 파일을 읽어 구독자에게 최신 브리핑을 발송한다.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DATA = BASE_DIR / "web" / "data"

WEB_BASE = "https://doubleshot.space"

TYPE_LABEL = {
    "kospi":  "🇰🇷 코스피 시초가 브리핑",
    "us":     "🇺🇸 미국 시장 브리핑",
    "weekly": "📋 주간 리포트",
}


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", str(text))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["kospi", "us", "weekly"], required=True)
    parser.add_argument("--date", default=None)
    args = parser.parse_args()

    kst       = pytz.timezone("Asia/Seoul")
    date_slug = args.date or datetime.now(kst).strftime("%Y-%m-%d")

    analysis_file = DATA_DIR / f"analysis_{args.type}.json"
    if not analysis_file.exists():
        print(f"[update_latest] {analysis_file} 없음 — 건너뜀", file=sys.stderr)
        sys.exit(0)

    with open(analysis_file, encoding="utf-8") as f:
        data = json.load(f)

    pred    = data.get("prediction", {})
    reasons = [strip_html(r) for r in data.get("reasons", [])[:3]]

    latest = {
        "date":       date_slug,
        "type":       args.type,
        "label":      TYPE_LABEL[args.type],
        "title":      strip_html(data.get("reason_title", "")),
        "direction":  pred.get("direction", ""),
        "up_pct":     pred.get("up_pct", 0),
        "confidence": pred.get("confidence", 0),
        "reasons":    reasons,
        "link":       f"{WEB_BASE}/briefings/{date_slug}/",
        "updated_at": datetime.now(kst).strftime("%Y-%m-%d %H:%M KST"),
    }

    WEB_DATA.mkdir(parents=True, exist_ok=True)
    out = WEB_DATA / "latest.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    print(f"[update_latest] ✓ {out} 업데이트 완료")


if __name__ == "__main__":
    main()
