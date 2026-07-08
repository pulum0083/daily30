#!/usr/bin/env python3
# 외국계 증권사·글로벌 IB의 한국 시장·대형주 코멘트를 Google News RSS로 수집·요약하는 스크립트
"""
Usage:
    python3 scripts/fetch_ib_korea_views.py

출력: data/ib_korea_views.json
  - Google News 한국어 RSS에서 화이트리스트 IB × 코스피/대형주 쿼리로 최근 24시간 기사만 수집
  - 제목/요약에 화이트리스트 IB명이 실제로 박혀 있어야 채택 (귀속 불가하면 버림)
  - IB당 1건, 최대 3건 (동일 IB는 가장 최근 1건)
  - batchexecute로 발행사 원문 URL 리졸브 → 실패 시 Google News 링크 폴백
  - Gemini는 제목+요약 기반 스탠스 요약(해요체)·bull/bear/neu 분류만 수행 (날짜·URL·출처 생성 불가)
  - 대상 없으면 빈 배열 저장 (섹션 생략, 파이프라인 보호)
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
KST = timezone(timedelta(hours=9))

MAX_ITEMS = 3

# 화이트리스트 IB — aliases 중 하나라도 제목/요약에 있으면 채택. 리스트 순서대로 first-match.
HOUSES = [
    {"name": "골드만삭스",   "initials": "GS",   "aliases": ["골드만삭스", "골드만"]},
    {"name": "모건스탠리",   "initials": "MS",   "aliases": ["모건스탠리", "모간스탠리"]},
    {"name": "JP모건",      "initials": "JPM",  "aliases": ["jp모건", "jp모간", "제이피모건", "jp 모건"]},
    {"name": "UBS",         "initials": "UBS",  "aliases": ["ubs"]},
    {"name": "씨티",         "initials": "Citi", "aliases": ["씨티그룹", "씨티"]},
    {"name": "노무라",       "initials": "NOM",  "aliases": ["노무라"]},
    {"name": "맥쿼리",       "initials": "MQ",   "aliases": ["맥쿼리"]},
    {"name": "HSBC",        "initials": "HSBC", "aliases": ["hsbc"]},
    {"name": "CLSA",        "initials": "CLSA", "aliases": ["clsa"]},
    {"name": "번스타인",     "initials": "BST",  "aliases": ["번스타인"]},
    {"name": "BofA",        "initials": "BofA", "aliases": ["뱅크오브아메리카", "bofa", "메릴린치"]},
    {"name": "바클레이스",   "initials": "BARC", "aliases": ["바클레이스", "바클레이즈"]},
]

VALID_SENTIMENTS = {"bull", "bear", "neu"}
_SENT_MAP = {"bullish": "bull", "bearish": "bear", "neutral": "neu"}


def _match_house(text: str) -> dict | None:
    """제목/요약 text에 화이트리스트 IB alias가 있으면 해당 하우스 dict 반환, 없으면 None."""
    low = text.lower()
    for h in HOUSES:
        if any(a in low for a in h["aliases"]):
            return h
    return None


def _within_24h(dt: datetime, now: datetime) -> bool:
    """dt가 now 기준 최근 24시간 이내(과거 방향)이고 미래가 아니면 True."""
    if dt > now:
        return False
    return (now - dt) <= timedelta(hours=24)


def _time_label(dt: datetime, now: datetime) -> str:
    """오늘(KST)이면 '오늘 HH:MM', 어제면 '어제 HH:MM', 그 밖이면 'M/D HH:MM'."""
    d0 = now.astimezone(KST).date()
    d = dt.astimezone(KST).date()
    hm = dt.astimezone(KST).strftime("%H:%M")
    if d == d0:
        return f"오늘 {hm}"
    if (d0 - d).days == 1:
        return f"어제 {hm}"
    return f"{d.month}/{d.day} {hm}"


def _normalize_sentiment(s: str) -> str:
    low = str(s).strip().lower()
    if low in _SENT_MAP:
        return _SENT_MAP[low]
    return low if low in VALID_SENTIMENTS else "neu"


def _dedup_by_house(cands: list[dict], max_items: int = MAX_ITEMS) -> list[dict]:
    """동일 하우스는 published_at 최신 1건만 유지, 최신순 정렬 후 max_items건 반환."""
    seen: dict[str, dict] = {}
    for c in cands:
        name = c["house"]
        if name not in seen or c["published_at"] > seen[name]["published_at"]:
            seen[name] = c
    ordered = sorted(seen.values(), key=lambda c: c["published_at"], reverse=True)
    return ordered[:max_items]


if __name__ == "__main__":
    from fetch_ib_korea_views import main  # noqa
    main()
