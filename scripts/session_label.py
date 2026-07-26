#!/usr/bin/env python3
# 브리핑 문구의 '간밤' 표현을 직전 실제 거래일 기준으로 계산·교정하는 유틸.
"""
코스피 아침 브리핑은 "간밤 미국 시장"을 전제로 쓰여 있다. 하지만 **월요일**이나
**휴일 다음날**에는 직전 미국장이 지난 금요일(혹은 그 이전)이라 '간밤'이 사실과 다르다.
(2026-07-27 실사고: 월요일 브리핑이 지난 금요일 미국장을 "간밤"으로 서술.)

`us_session_label(date)` — 그날 브리핑이 참조하는 직전 미국장을 가리키는 한국어 표현.
  · 직전 미국장이 바로 어제면 "간밤"
  · 아니면 "지난 금요일"처럼 요일로, 8일 이상 벌어지면 "직전 미국장(7/17)"

`fix_overnight_wording(text, date)` — 본문의 '간밤/어젯밤/밤사이'를 위 라벨로 치환.
LLM 프롬프트로만 막으면 새는 표현이라 발행 직전 결정론적 게이트로 한 번 더 잡는다.
"""

from __future__ import annotations

import sys
from datetime import date as _date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from holiday_check import check_kospi_open, check_us_open  # noqa: E402

_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 브리핑 본문에서 '간밤'과 같은 뜻으로 쓰이는 표현들
_OVERNIGHT_WORDS = ("간밤에", "간밤", "어젯밤", "지난밤", "밤사이")


def prev_us_session(d: _date) -> _date | None:
    """d(KST 브리핑 날짜) 이전의 가장 최근 미국장 개장일."""
    for back in range(1, 15):
        cand = d - timedelta(days=back)
        if check_us_open(cand):
            return cand
    return None


def prev_kospi_session(d: _date) -> _date | None:
    """d 이전의 가장 최근 코스피 개장일."""
    for back in range(1, 15):
        cand = d - timedelta(days=back)
        if check_kospi_open(cand):
            return cand
    return None


def _label_for(d: _date, prev: _date | None, same_night: str) -> str:
    if prev is None:
        return "직전 미국장"
    gap = (d - prev).days
    if gap <= 1:
        return same_night
    if gap <= 7:
        return f"지난 {_WEEKDAY_KO[prev.weekday()]}요일"
    return f"직전 미국장({prev.month}/{prev.day})"


def us_session_label(d: _date) -> str:
    """직전 미국장을 가리키는 표현. 어제면 '간밤', 아니면 '지난 금요일' 등."""
    return _label_for(d, prev_us_session(d), "간밤")


def is_overnight_us(d: _date) -> bool:
    """직전 미국장이 실제로 '간밤'인지 여부."""
    return us_session_label(d) == "간밤"


def fix_overnight_wording(text: str, d: _date) -> str:
    """'간밤' 계열 표현을 그날 실제 라벨로 치환. 간밤이 맞는 날이면 원문 그대로."""
    if not text or is_overnight_us(d):
        return text
    label = us_session_label(d)
    for word in _OVERNIGHT_WORDS:
        text = text.replace(word, label)
    return text


if __name__ == "__main__":
    from datetime import datetime
    import pytz

    today = datetime.now(pytz.timezone("Asia/Seoul")).date()
    print(f"{today} → 직전 미국장 {prev_us_session(today)} / 라벨 '{us_session_label(today)}'")
    print(f"{today} → 직전 코스피장 {prev_kospi_session(today)}")
