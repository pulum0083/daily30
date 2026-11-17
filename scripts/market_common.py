# 시장 데이터 수집 모듈들이 함께 쓰는 경로·시간대

from __future__ import annotations
from pathlib import Path
import pytz


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


KST = pytz.timezone("Asia/Seoul")
UTC = pytz.utc
