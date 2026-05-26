#!/usr/bin/env python3
"""
Market holiday checker for KOSPI and US markets.
Uses pandas_market_calendars if available, otherwise falls back to a hardcoded list.
Exit code 0 = market is open, Exit code 1 = market is closed/holiday.
"""

import argparse
import sys
from datetime import date, datetime, timedelta
import pytz

KST = pytz.timezone("Asia/Seoul")
US_EASTERN = pytz.timezone("America/New_York")


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Saturday, 6=Sunday


def check_with_pandas_calendars(market: str, check_date: date) -> bool:
    """Returns True if market is OPEN on check_date."""
    try:
        import pandas_market_calendars as mcal

        cal_name = "XKRX" if market == "kospi" else "NYSE"
        cal = mcal.get_calendar(cal_name)
        schedule = cal.schedule(
            start_date=check_date.strftime("%Y-%m-%d"),
            end_date=check_date.strftime("%Y-%m-%d"),
        )
        return not schedule.empty
    except Exception:
        return None  # Fallback to hardcoded list


def check_kospi_open(check_date: date) -> bool:
    """Returns True if KOSPI is open on check_date."""
    if is_weekend(check_date):
        return False

    # 하드코딩 목록을 먼저 확인 (manual override — pandas보다 우선)
    korean_holidays_2025 = {
        date(2025, 1, 1),   # 신정
        date(2025, 1, 27),  # 설날 임시공휴일
        date(2025, 1, 28),  # 설날 연휴
        date(2025, 1, 29),  # 설날
        date(2025, 1, 30),  # 설날 연휴
        date(2025, 3, 3),   # 대체공휴일 (삼일절 3/1 토요일)
        date(2025, 5, 5),   # 어린이날 + 부처님오신날 (겹침)
        date(2025, 5, 6),   # 대체공휴일 (부처님오신날)
        date(2025, 6, 3),   # 21대 대통령선거 임시공휴일
        date(2025, 6, 6),   # 현충일
        date(2025, 8, 15),  # 광복절
        date(2025, 10, 3),  # 개천절
        date(2025, 10, 6),  # 추석
        date(2025, 10, 7),  # 추석 연휴
        date(2025, 10, 8),  # 대체공휴일 (추석 연휴 10/5 일요일)
        date(2025, 10, 9),  # 한글날
        date(2025, 12, 25), # 성탄절
        date(2025, 12, 31), # KRX 연말 휴장
    }
    korean_holidays_2026 = {
        date(2026, 1, 1),   # 신정
        date(2026, 2, 16),  # 설날 연휴
        date(2026, 2, 17),  # 설날
        date(2026, 2, 18),  # 설날 연휴
        date(2026, 3, 2),   # 대체공휴일 (삼일절 3/1 일요일)
        date(2026, 5, 1),   # 근로자의 날
        date(2026, 5, 5),   # 어린이날
        date(2026, 5, 25),  # 대체공휴일 (부처님오신날 5/24 일요일)
        date(2026, 6, 3),   # 지방선거일 임시공휴일
        date(2026, 7, 17),  # 제헌절 (18년 만에 공휴일 부활)
        date(2026, 8, 17),  # 대체공휴일 (광복절 8/15 토요일)
        date(2026, 9, 24),  # 추석 연휴
        date(2026, 9, 25),  # 추석
        date(2026, 9, 26),  # 추석 연휴
        date(2026, 10, 5),  # 대체공휴일 (개천절 10/3 토요일)
        date(2026, 10, 9),  # 한글날
        date(2026, 12, 25), # 성탄절
        date(2026, 12, 31), # KRX 연말 휴장
    }
    all_holidays = korean_holidays_2025 | korean_holidays_2026
    if check_date in all_holidays:
        return False

    result = check_with_pandas_calendars("kospi", check_date)
    if result is not None:
        return result

    return True


def check_us_open(check_date: date) -> bool:
    """Returns True if NYSE/NASDAQ is open on check_date."""
    if is_weekend(check_date):
        return False

    result = check_with_pandas_calendars("us", check_date)
    if result is not None:
        return result

    # Hardcoded US market holidays 2025-2026 (fallback)
    us_holidays_2025 = {
        date(2025, 1, 1),   # New Year's Day
        date(2025, 1, 20),  # MLK Day
        date(2025, 2, 17),  # Presidents Day
        date(2025, 4, 18),  # Good Friday
        date(2025, 5, 26),  # Memorial Day
        date(2025, 6, 19),  # Juneteenth
        date(2025, 7, 4),   # Independence Day
        date(2025, 9, 1),   # Labor Day
        date(2025, 11, 27), # Thanksgiving
        date(2025, 12, 25), # Christmas
    }
    us_holidays_2026 = {
        date(2026, 1, 1),   # New Year's Day
        date(2026, 1, 19),  # MLK Day
        date(2026, 2, 16),  # Presidents Day
        date(2026, 4, 3),   # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),   # Independence Day (observed)
        date(2026, 9, 7),   # Labor Day
        date(2026, 11, 26), # Thanksgiving
        date(2026, 12, 25), # Christmas
    }
    all_holidays = us_holidays_2025 | us_holidays_2026
    return check_date not in all_holidays


def was_kospi_only_closed_previous_session(today: date) -> bool:
    """직전 KOSPI 거래일과 오늘 사이에 다른 시장(미국·아시아)이 1번 이상 추가로 거래됐는지 판정.

    True면 'post-holiday catch-up' 컨텍스트가 필요한 날.
    매주 월요일(주말 갭만 있는 경우)은 False로 떨어지고,
    한국이 평일에 단독 휴장한 다음 거래일에는 True가 된다.
    """
    # 직전 KOSPI 거래일을 찾는다
    prev_kospi = today
    while True:
        prev_kospi -= timedelta(days=1)
        if check_kospi_open(prev_kospi):
            break

    # 그 사이의 추가 거래일 카운트 — 평일(아시아 시장 대부분 거래) 또는 미국 거래일
    extra_sessions = 0
    d = prev_kospi + timedelta(days=1)
    while d < today:
        if (not is_weekend(d)) or check_us_open(d):
            extra_sessions += 1
        d += timedelta(days=1)

    return extra_sessions >= 1


def main():
    parser = argparse.ArgumentParser(description="Check if market is open today")
    parser.add_argument("--market", choices=["kospi", "us"], required=True)
    parser.add_argument(
        "--date",
        default=None,
        help="Date to check (YYYY-MM-DD). Defaults to today KST.",
    )
    args = parser.parse_args()

    if args.date:
        check_date = date.fromisoformat(args.date)
    else:
        check_date = datetime.now(KST).date()

    if args.market == "kospi":
        is_open = check_kospi_open(check_date)
    else:
        is_open = check_us_open(check_date)

    status = "OPEN" if is_open else "CLOSED"
    print(f"[holiday_check] {args.market.upper()} on {check_date}: {status}")

    # Exit code 0 = open, 1 = closed
    sys.exit(0 if is_open else 1)


if __name__ == "__main__":
    main()
