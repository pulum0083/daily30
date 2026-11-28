# 브리핑·페이지 생성기가 함께 쓰는 경로·상수·Jinja 환경·날짜 표기 도우미

import json
from datetime import datetime, date
from pathlib import Path
import pytz
from jinja2 import Environment, FileSystemLoader


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
QUOTE_TODAY_FILE = DATA_DIR / "quote_today.json"
BRIEFINGS_DIR = WEB_DIR / "briefings"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
CONFIG_DIR = Path(__file__).resolve().parent / "config"

# 정적 에셋 캐시 무효화용 버전 — style.css/main.js 변경 시 이 값을 올리면 브라우저가 새 파일을 받는다.
ASSET_VER = "20261128"
CSS_PATH = f"/assets/style.css?v={ASSET_VER}"
JS_PATH = f"/assets/main.js?v={ASSET_VER}"
KST = pytz.timezone("Asia/Seoul")

# CLI type → 내부 type(URL·config·템플릿)
TYPE_MAP = {"kospi": "kospi", "us": "us", "kospi-close": "close", "close": "close"}
# 내부 type → analysis 파일명에 쓰는 source type
SRC_TYPE = {"kospi": "kospi", "us": "us", "close": "kospi-close"}
# 내부 type → 시장 데이터 파일명
DATA_FILE = {"kospi": "latest_kospi.json", "us": "latest_us.json", "close": "latest_kospi_close.json"}
BRIEFING_LABELS = {"kospi": "코스피 예측", "close": "코스피 마감", "us": "미국 시장"}
SCHEDULED_TIMES = {"kospi": "07:30", "close": "16:30", "us": "21:20"}
DAY_FULL = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
DAY_SHORT = ["월", "화", "수", "목", "금", "토", "일"]


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
    env.filters["tojson"] = lambda v: json.dumps(v, ensure_ascii=False)
    env.filters["acc_cls"] = lambda p: "good" if p >= 70 else ("mid" if p >= 50 else "bad")
    return env


# ─────────────────────────────────────────────────────────────────────────────
# SEO 메타 (2026-07-21 신설) — 종목·미국·섹터 상세 페이지의 head 메타를 한곳에서 만든다.
#
# 배경: 종목 상세 46개가 <title> 외에 description·canonical·OG·JSON-LD를 하나도 갖지
# 않은 채 발행되고 있었다(STOCKS_SERVICE_RULES §9 발행 게이트 4번 미이행). 검색 유입을
# 노린 영구 자산인데 정작 검색엔진에 제출되는 형태가 비어 있었다.
#
# ⚠️ make_env()가 autoescape=False라 meta content를 템플릿에서 그대로 찍으면 따옴표가
#    섞였을 때 속성이 깨진다. 반드시 여기서 이스케이프해 넘긴다.

SITE_BASE = "https://doubleshot.space"
OG_IMAGE_URL = f"{SITE_BASE}/assets/og-image.png"

# 하이퍼리퀴드 xyz dex에 상장돼 야간 추정가(/api/hl-night)를 받을 수 있는 한국 종목.
# api/hl-night.mjs 의 SYM2CODE 미러 — 거기에 심볼이 늘면 여기도 함께 늘린다.
# 여기 없는 종목은 야간 소스 자체가 없으므로 히어로 스트립을 아예 렌더하지 않는다(빈 자리 노출 금지).
HL_NIGHT_CODES = {"005930", "000660", "005380"}

# 발행 게이트(verify_publish_gate)에 걸려 파일로 쓰이지 않은 페이지 URL.
# 비어 있지 않으면 main()이 exit 1 한다 — 다만 그 페이지의 직전 정상본은 그대로 살아 있다.
GATE_BLOCKED = []


def _jsonld(obj) -> str:
    """JSON-LD 직렬화. 본문에 '</'가 들어가면 <script>가 조기 종료되므로 이스케이프한다."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _breadcrumb(items) -> dict:
    """items: [(name, path|None)] — 마지막 항목은 현재 페이지라 path가 없어도 된다."""
    elements = []
    for i, (name, path) in enumerate(items, start=1):
        el = {"@type": "ListItem", "position": i, "name": name}
        if path:
            el["item"] = f"{SITE_BASE}{path}"
        elements.append(el)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": elements}


def fmt_time(generated_at: str) -> str:
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = KST.localize(dt)
        return dt.astimezone(KST).strftime("%H:%M")
    except Exception:
        return "--:--"


def day_label(d: str, full: bool = False) -> str:
    try:
        wd = date.fromisoformat(d).weekday()
        return (DAY_FULL if full else DAY_SHORT)[wd]
    except Exception:
        return ""


_DOWS = ["월", "화", "수", "목", "금", "토", "일"]


def _market_data_is_for(market_data: dict, target_date: str) -> bool:
    """시장 데이터가 이 브리핑 날짜에 수집된 것인지 — 다른 날 파일로 스냅샷을 채우지 않는다(§14)."""
    return bool(target_date) and str((market_data or {}).get("generated_at") or "")[:10] == target_date


def _md(ymd: str) -> str:
    return f"{int(ymd[5:7])}/{int(ymd[8:10])}"


def _dow(ymd: str) -> str:
    return "월화수목금토일"[datetime.strptime(ymd, "%Y-%m-%d").weekday()]
