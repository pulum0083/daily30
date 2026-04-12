#!/usr/bin/env python3
"""
Market holiday checker for KOSPI and US markets.
Uses pandas_market_calendars if available, otherwise falls back to a hardcoded list.
Exit code 0 = market is open, Exit code 1 = market is closed/holiday.
"""

import argparse
import sys
from datetime import date, datetime
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

    result = check_with_pandas_calendars("kospi", check_date)
    if result is not None:
        return result

    # Hardcoded Korean public holidays 2025-2026 (fallback)
    korean_holidays_2025 = {
        date(2025, 1, 1),   # 신정
        date(2025, 1, 28),  # 설날 연휴
        date(2025, 1, 29),  # 설날
        date(2025, 1, 30),  # 설날 연휴
        date(2025, 3, 1),   # 삼일절
        date(2025, 5, 5),   # 어린이날
        date(2025, 5, 6),   # 대체공휴일
        date(2025, 6, 6),   # 현충일
        date(2025, 8, 15),  # 광복절
        date(2025, 10, 3),  # 개천절
        date(2025, 10, 5),  # 추석 연휴
        date(2025, 10, 6),  # 추석
        date(2025, 10, 7),  # 추석 연휴
        date(2025, 10, 9),  # 한글날
        date(2025, 12, 25), # 성탄절
        date(2025, 12, 31), # 연말 휴장
    }
    korean_holidays_2026 = {
        date(2026, 1, 1),   # 신정
        date(2026, 2, 16),  # 설날 연휴
        date(2026, 2, 17),  # 설날
        date(2026, 2, 18),  # 설날 연휴
        date(2026, 3, 1),   # 삼일절
        date(2026, 5, 5),   # 어린이날
        date(2026, 6, 6),   # 현충일
        date(2026, 8, 15),  # 광복절
        date(2026, 9, 24),  # 추석 연휴
        date(2026, 9, 25),  # 추석
        date(2026, 9, 26),  # 추석 연휴
        date(2026, 10, 3),  # 개천절
        date(2026, 10, 9),  # 한글날
        date(2026, 12, 25), # 성탄절
        date(2026, 12, 31), # 연말 휴장
    }
    all_holidays = korean_holidays_2025 | korean_holidays_2026
    return check_date not in all_holidays


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
