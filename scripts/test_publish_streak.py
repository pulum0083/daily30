#!/usr/bin/env python3
# check_accuracy.compute_publish_streak — 거래일 기준 연속 발행 계산 테스트
"""주말·공휴일이 끊김으로 오판되지 않는지, 실제 미발행만 끊김으로 세는지 검증한다.

기준 달력: 2026-07-17(금)은 제헌절 공휴일, 07-18·19는 주말, 05-25도 공휴일.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from check_accuracy import compute_publish_streak
from holiday_check import check_kospi_open
from datetime import date


def mk(dates, type_="kospi"):
    return [{"date": d, "type": type_} for d in dates]


def test_empty():
    assert compute_publish_streak([]) == {"days": 0, "from": None, "to": None}


def test_weekend_is_not_a_break():
    """금(07-24) → 월(07-20) 사이 주말(25·26은 미래, 18·19는 주말)은 끊김이 아니다."""
    r = compute_publish_streak(mk(["2026-07-20", "2026-07-21", "2026-07-22",
                                   "2026-07-23", "2026-07-24"]))
    assert r["days"] == 5, r
    assert r["from"] == "2026-07-20"
    assert r["to"] == "2026-07-24"


def test_holiday_is_not_a_break():
    """07-17(제헌절)을 건너뛰어도 07-16과 07-20이 이어진다."""
    assert not check_kospi_open(date(2026, 7, 17)), "전제 확인: 07-17은 공휴일"
    r = compute_publish_streak(mk(["2026-07-16", "2026-07-20", "2026-07-21"]))
    assert r["days"] == 3, r
    assert r["from"] == "2026-07-16"


def test_missing_trading_day_breaks():
    """07-21(화)이 빠지면 그 앞은 세지 않는다 — 스트릭은 07-22부터."""
    r = compute_publish_streak(mk(["2026-07-20", "2026-07-22", "2026-07-23"]))
    assert r["days"] == 2, r
    assert r["from"] == "2026-07-22"
    assert r["to"] == "2026-07-23"


def test_us_entries_are_ignored():
    """US는 채점 탈퇴 — 스트릭은 kospi 발행만 센다."""
    rows = mk(["2026-07-23", "2026-07-24"]) + mk(["2026-07-20", "2026-07-21"], "us")
    r = compute_publish_streak(rows)
    assert r["days"] == 2, r
    assert r["from"] == "2026-07-23"


def test_real_data_matches_manual_count():
    """실제 briefings.json에서 계산한 값이 드리프트 없는 불변식을 만족한다.

    이전에는 `days == 68`·`to == "2026-07-24"`를 하드코딩해, 브리핑이 하루 더 발행될
    때마다 테스트가 깨졌다(§20의 "상대 값을 저장하지 말라"와 같은 계열의 실수 — 매일
    자라는 데이터에 고정 기댓값을 박은 것). 날짜가 지나도 유효한 불변식으로 바꾼다.
    """
    import json
    p = Path(__file__).parent.parent / "data" / "briefings.json"
    rows = json.load(open(p, encoding="utf-8"))["briefings"]
    r = compute_publish_streak(rows)

    latest_kospi = max(
        b["date"] for b in rows
        if (b.get("type") or "kospi") == "kospi" and b.get("date")
    )
    assert r["from"] == "2026-04-15", r      # 스트릭 시작점은 고정 (끊기면 바뀐다)
    assert r["to"] == latest_kospi, r        # 끝은 항상 최신 kospi 발행일
    assert r["days"] >= 68, r                # 단조 증가 — 줄었다면 계산 회귀


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as e:
            fails += 1
            print(f"  ✗ {name}: {e}")
    print("FAIL" if fails else "모두 통과")
    sys.exit(1 if fails else 0)
