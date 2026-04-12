#!/usr/bin/env python3
"""
Update Google Sheets with structured briefing data.
Reads from data/sheets_row_{type}.json and appends a row to the sheet.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"

KST = pytz.timezone("Asia/Seoul")

# Sheet tab names
SHEET_TABS = {
    "kospi": "코스피_브리핑",
    "us": "미국_브리핑",
    "weekly": "주간_리포트",
}

# Column headers per briefing type
HEADERS = {
    "kospi": [
        "날짜", "생성시각", "예측방향", "상승확률(%)", "신뢰도(%)",
        "SP500등락(%)", "NASDAQ등락(%)", "SOX등락(%)", "EWY등락(%)",
        "VIX", "DXY등락(%)", "WTI등락(%)", "원달러환율", "메모",
    ],
    "us": [
        "날짜", "생성시각", "예측방향", "상승확률(%)", "SP500예상하단(%)", "SP500예상상단(%)",
        "VIX", "DXY등락(%)", "10Y금리(%)", "WTI등락(%)", "공포탐욕지수", "오늘이벤트", "메모",
    ],
    "weekly": [
        "주간시작일", "주간종료일", "생성시각", "코스피등락(%)", "SP500등락(%)", "NASDAQ등락(%)",
        "핵심이벤트수", "최고리스크", "주목테마", "메모",
    ],
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError("config.json not found.")
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_or_create_sheet(spreadsheet, tab_name: str, headers: list):
    """Get existing worksheet or create new one with headers."""
    try:
        ws = spreadsheet.worksheet(tab_name)
        return ws
    except Exception:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
        ws.append_row(headers)
        return ws


def append_row(briefing_type: str, row_data: dict):
    """Append a row to the corresponding sheet tab."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print(
            "[update_sheets] gspread not installed. Run: pip install gspread google-auth",
            file=sys.stderr,
        )
        sys.exit(1)

    config = load_config()
    creds_file = BASE_DIR / config["google_sheets"]["credentials_file"]
    spreadsheet_id = config["google_sheets"]["spreadsheet_id"]

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(creds_file), scopes=scopes)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(spreadsheet_id)

    tab_name = SHEET_TABS[briefing_type]
    headers = HEADERS[briefing_type]
    ws = get_or_create_sheet(spreadsheet, tab_name, headers)

    # Build row in header order
    row = [row_data.get(h, "") for h in headers]
    ws.append_row(row, value_input_option="USER_ENTERED")
    print(f"[update_sheets] Row appended to '{tab_name}'")


def main():
    parser = argparse.ArgumentParser(description="Update Google Sheets with briefing data")
    parser.add_argument("--type", choices=["kospi", "us", "weekly"], required=True)
    args = parser.parse_args()

    row_file = DATA_DIR / f"sheets_row_{args.type}.json"
    if not row_file.exists():
        print(f"[update_sheets] Row file not found: {row_file}", file=sys.stderr)
        sys.exit(1)

    with open(row_file, encoding="utf-8") as f:
        row_data = json.load(f)

    try:
        append_row(args.type, row_data)
    except Exception as e:
        print(f"[update_sheets] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
