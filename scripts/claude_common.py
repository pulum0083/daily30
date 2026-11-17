# call_claude와 나눈 모듈이 함께 쓰는 경로·시간대·설정 읽기

from __future__ import annotations
import json
from pathlib import Path
import pytz


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
GURU_QUOTES_FILE = DATA_DIR / "guru_quotes.json"
QUOTE_TODAY_FILE = DATA_DIR / "quote_today.json"
KST = pytz.timezone("Asia/Seoul")


def load_config() -> dict:
    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            return json.load(f)
    return {}
