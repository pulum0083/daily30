# 뉴스 수집 모듈들이 함께 쓰는 경로·시간대·Gemini 키 읽기·빈 뉴스 형태

from __future__ import annotations
import json
import os
from pathlib import Path
import pytz


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


KST = pytz.timezone("Asia/Seoul")


# ─────────────────────────────────────────────────────────────────────────────
# Gemini API
# ─────────────────────────────────────────────────────────────────────────────

def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        config_file = BASE_DIR / "config.json"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                cfg = json.load(f)
            key = cfg.get("gemini", {}).get("api_key", "")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. "
            "Set the environment variable or add gemini.api_key to config.json"
        )
    return key


EMPTY_NEWS = {
    "key_indicators": [],
    "catalysts": [],
    "headlines": [],
    "market_sentiment": "neutral",
}
