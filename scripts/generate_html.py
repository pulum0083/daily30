#!/usr/bin/env python3
# config-driven 섹션 조립으로 브리핑 HTML을 생성하는 조립기
"""브리핑 HTML 조립기.

call_claude.py가 다음 시그니처로 호출한다:
  generate_html.py --type {kospi|us|kospi-close} --data-file <latest_*.json> --date YYYY-MM-DD

analysis_{type}.json(Claude 분석) + data-file(시장 데이터)을 읽어
config/{internal}.json 선언에 따라 섹션 템플릿을 조립하고
web/briefings/{date}/{internal}/index.html 로 출력한다.

데이터가 없는 섹션은 조립 템플릿의 {% if %} 가드로 자동 생략된다(하이브리드).
"""

import argparse
import html
import json
import math
import os
import re
import sys
from datetime import datetime, date, timezone
from pathlib import Path

import pytz
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from og_card import make_card
from prediction_basis import OPEN as BASIS_OPEN, stats_rows, legacy_kospi_rows, outcome_pct

try:
    from scripts.verify_publish_gate import gate_write, check_sitemap
except ImportError:
    from verify_publish_gate import gate_write, check_sitemap

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
QUOTE_TODAY_FILE = DATA_DIR / "quote_today.json"
BRIEFINGS_DIR = WEB_DIR / "briefings"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
CONFIG_DIR = Path(__file__).resolve().parent / "config"

# 정적 에셋 캐시 무효화용 버전 — style.css/main.js 변경 시 이 값을 올리면 브라우저가 새 파일을 받는다.
ASSET_VER = "20261029a"
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


# 마감 수급 7일 흐름용 누적 저장 (벌크 7일 API가 막혀 있어 매일 단일일 수급을 쌓아 시계열 생성)
SUPPLY_HISTORY_FILE = DATA_DIR / "supply_history.json"
SUPPLY_KEYS = ("foreign", "institution", "individual")


def _load_supply_history() -> dict:
    try:
        return load_json(SUPPLY_HISTORY_FILE)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_supply_history_web(hist: dict) -> None:
    """수급 히스토리를 web/data/로 미러링한다 — 종목 대시보드 수급 행의 '10일 추이' 패널이 fetch한다.
    data/ 는 웹 루트 밖이라 브라우저에서 직접 읽을 수 없다. 이 파일의 소유 워크플로우는
    kospi-briefing 하나뿐이므로 다른 잡과 커밋이 겹치지 않는다(SERVICE_RULES §18)."""
    if not hist:
        return
    out = WEB_DIR / "data" / "supply-history.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")


def update_supply_history(date: str, inv: dict) -> dict:
    """당일 시장 수급(외국인/기관/개인 순매수)을 날짜별로 멱등 upsert하고 전체를 반환한다(억원 단위)."""
    rec = {}
    for key in SUPPLY_KEYS:
        d = inv.get(key)
        if isinstance(d, dict) and d.get("net") is not None:
            rec[key] = round(d["net"] / 100)  # 백만원 → 억원
    hist = _load_supply_history()
    if not rec:
        return hist
    hist[date] = rec
    hist = {k: hist[k] for k in sorted(hist)[-30:]}  # 최근 30일만 보관
    SUPPLY_HISTORY_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")
    write_supply_history_web(hist)
    return hist


def supply_flow(hist: dict, key: str, upto: str) -> list:
    """key 투자자의 최근 7거래일(upto 날짜 이하) 순매수 시계열(오래된→오늘, 억원)."""
    dates = sorted(d for d in hist if d <= upto)[-7:]
    return [hist[d].get(key, 0) for d in dates]


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


# ── 섹션 컨텍스트 빌더 ─────────────────────────────────────────────────────────
# 이슈 카드 title·body에서 새어든 수치(등락률·가격·지수 레벨)를 제거하는 최종 방어선.
# 운영 규칙 0: 이슈 카드에는 실측이 없으므로 어떤 숫자도 표시하지 않는다(티커는 별도 필드라 무관).
_ISSUE_NUM_PATTERNS = [
    re.compile(r"[-+]?\d[\d,.]*\s*%"),          # 등락률: -4%, +2.3%
    re.compile(r"\$\s?\d[\d,.]*"),               # 가격: $168, $ 168.5
    re.compile(r"\b\d{1,3}(?:,\d{3})+\b"),       # 콤마 그룹 지수 레벨: 5,431
]


def _strip_issue_numbers(text: str) -> str:
    if not text:
        return ""
    out = text
    for pat in _ISSUE_NUM_PATTERNS:
        out = pat.sub("", out)
    # 숫자 제거로 생긴 이중 공백·공백앞 구두점 정리
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.·])", r"\1", out)
    return out.strip()


def _prev_us_session_label(target_date: str) -> str:
    """섹션 제목의 '간밤' 표기. 월요일·휴일 다음날은 직전 미국장이 어제가 아니므로
    '지난 금요일'처럼 실제 세션을 가리킨다 (2026-07-27 실사고)."""
    try:
        from datetime import date as _d
        from session_label import us_session_label
        y, m, dd = (int(x) for x in target_date.split("-"))
        return us_session_label(_d(y, m, dd))
    except Exception:
        return "간밤"


def build_us_issue_results(analysis: dict, target_date: str = "") -> dict:
    """직전 미국장 이슈 채점 결과 → 코스피 아침 브리핑 '이렇게 끝났어요' 섹션.

    **스냅샷이 1순위다.** 결과를 analysis에 주입해 두면 generate_html이 analysis를 통째로
    analysis_snapshot.json에 저장하므로, 나중에 재생성할 때 §2 규칙대로 스냅샷이 먼저 쓰이고
    그 시점 시세를 다시 조회하지 않는다 — 별도 저장 장치가 필요 없다.

    데이터 파일을 쓸 때는 세션 날짜를 대조한다. 다른 실행이 남긴 파일이 엉뚱한 날짜 브리핑을
    오염시키는 것을 막는다(§14와 같은 처방). 결과가 없으면 빈 리스트 — 섹션이 통째로 생략된다.
    """
    label = _prev_us_session_label(target_date) if target_date else "간밤"
    results = analysis.get("us_issue_results")
    if not isinstance(results, dict):
        results = _read_us_issue_results(target_date)
        if results is not None:
            analysis["us_issue_results"] = results   # 스냅샷에 함께 저장된다
    cards = (results or {}).get("cards") or []
    return {
        "us_issue_cards": [c for c in cards if isinstance(c, dict)],
        "us_issue_label": (results or {}).get("session_label") or label,
        "us_issue_session": (results or {}).get("us_session_date", ""),
    }


def _read_us_issue_results(target_date: str):
    """data/us_issue_results.json 을 읽되 대상 세션이 맞을 때만 돌려준다."""
    path = DATA_DIR / "us_issue_results.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[generate_html] us_issue_results 파싱 실패: {e}")
        return None
    if not target_date:
        return data
    try:
        from datetime import date as _d
        from session_label import us_session_to_score
        y, m, dd = (int(x) for x in target_date.split("-"))
        expected = us_session_to_score(_d(y, m, dd))
    except Exception:
        return data
    got = data.get("us_session_date")
    if expected is None:
        # 미국 휴장으로 새 세션이 없는 날 — 직전 세션은 어제 이미 채점했다.
        # 채점 스텝이 실패해 어제 결과 파일이 남아 있어도 여기서 막는다.
        print("[generate_html] 새로 채점할 미국 세션이 없어 이슈 결과 섹션을 생략합니다.")
        return None
    if got != str(expected):
        print(f"[generate_html] ⚠️ us_issue_results 세션 불일치({got} ≠ {expected}) — 섹션 생략")
        return None
    return data


_DOWS = ["월", "화", "수", "목", "금", "토", "일"]
# 이슈 점검 카드의 국내 관련 종목 — 제목 키워드 규칙(사용자 결정 2026-10-26). AI 판단이 아니라서 '관련 종목'으로 표기한다.
ISSUE_RELATED_KR = [
    (re.compile(r"반도체|메모리|HBM|D램|낸드"), [("005930", "삼성전자"), ("000660", "SK하이닉스")]),
]


def _prev_label(prev_date: str, target_date: str) -> str:
    """'어제 예측' 칩의 날짜 표현. 어제가 아니면 '어제'라고 쓰지 않는다(§24)."""
    p = datetime.strptime(prev_date, "%Y-%m-%d").date()
    t = datetime.strptime(target_date, "%Y-%m-%d").date()
    gap = (t - p).days
    if gap == 1:
        return "어제"
    if gap <= 3 and p.weekday() == 4 and t.weekday() == 0:
        return "지난 금요일"
    return f"{p.month}/{p.day}({_DOWS[p.weekday()]})"


def build_prev_prediction(analysis: dict, target_date: str, gap_fn=None) -> dict:
    """요약 카드의 '어제 예측' 칩 — 직전 코스피 예측이 시초가에서 맞았는지.

    07:25엔 전날 예측이 아직 채점 전이다(정확도 체크는 다음 거래일 09:10). 그래서 채점 기록이 없으면
    전날 시초가 갭을 지수 일봉으로 직접 구해 같은 규칙으로 채점한다(마감 배지와 같은 방식).
    그것도 못 구하면 칩을 뺀다 — 더 오래된 결과로 대신하지 않는다(§16).
    결과는 analysis에 넣어 스냅샷에 함께 저장한다(재생성해도 바뀌지 않게).
    """
    saved = analysis.get("prev_prediction_result")
    if isinstance(saved, dict) and saved.get("date"):
        res = saved
    else:
        bpath = DATA_DIR / "briefings.json"
        if not bpath.exists():
            return {}
        rows = load_json(bpath).get("briefings", [])
        prev = [b for b in rows if b.get("type") == "kospi" and b.get("date", "") < target_date]
        if not prev:
            return {}
        last = max(prev, key=lambda b: b["date"])   # 가장 최근 항목만 — 채점 여부 무관(§16)
        if last.get("basis") != BASIS_OPEN:
            return {}                               # 종가 기준 옛 예측은 시초가 칩으로 말할 수 없다
        predicted = last.get("predicted_direction", "")
        gap = last.get("actual_open_pct") if last.get("is_correct") is not None else None
        if not isinstance(gap, (int, float)):
            if gap_fn is None:
                from check_accuracy import get_kospi_open_gap as gap_fn
            g = gap_fn(last["date"])
            gap = g[2] if g else None
        if not isinstance(gap, (int, float)):
            return {}
        from check_accuracy import classify_direction_correct
        res = {
            "date": last["date"],
            "direction": predicted,
            "ok": bool(classify_direction_correct(predicted, gap)),
            "open_pct": round(gap, 2),
        }
        analysis["prev_prediction_result"] = res     # 스냅샷에 함께 저장된다
    return {"prev_pred": {
        "label": _prev_label(res["date"], target_date),
        "dir_word": (res.get("direction") or "").replace(" 우위", ""),
        "ok": bool(res.get("ok")),
        "open_pct": res.get("open_pct"),
    }}


def build_hero(analysis: dict, target_date: str) -> dict:
    """30초 요약 카드 머리·확률 표기. 중립이면 위로 열릴 확률을 그대로 보여준다."""
    pred = analysis.get("prediction") or {}
    d = datetime.strptime(target_date, "%Y-%m-%d")
    direction = pred.get("direction", "")
    neutral = "상승" not in direction and "하락" not in direction
    return {
        "hero_date_label": f"{d.month}월 {d.day}일({_DOWS[d.weekday()]})",
        "hero_prob_caption": "위로 열릴 확률" if neutral else "",
        "hero_prob": pred.get("up_pct", 50) if neutral else None,
    }


_PRIOR_SIG_NAMES = [("sox", "SOX"), ("nasdaq", "나스닥"), ("nq", "나스닥 선물"),
                    ("ewy_resid", "EWY(코스피 반영분 제외)"), ("vix", "VIX")]


def _market_data_is_for(market_data: dict, target_date: str) -> bool:
    """시장 데이터가 이 브리핑 날짜에 수집된 것인지 — 다른 날 파일로 스냅샷을 채우지 않는다(§14)."""
    return bool(target_date) and str((market_data or {}).get("generated_at") or "")[:10] == target_date


def build_prior_signals(analysis: dict, market_data: dict, target_date: str) -> dict:
    """요약 카드의 '예측 근거 신호' 한 줄 — 방향을 정하는 prior 신호 실측(§57·§63).

    예측에 실제로 쓰는 leading_signal.compute_prior()로 계산하고 analysis에 넣어 스냅샷에 남긴다.
    시장 데이터가 이 날짜 것이 아니면 만들지 않는다(재생성 때 다른 날 값이 들어가지 않게).
    """
    saved = analysis.get("prior_signals")
    if not isinstance(saved, dict):
        if not _market_data_is_for(market_data, target_date):
            return {}
        try:
            from leading_signal import compute_prior
            sig = compute_prior(market_data).get("signals") or {}
        except Exception as e:
            print(f"[generate_html] 예측 근거 신호 계산 실패: {e}")
            return {}
        saved = {k: sig.get(k) for k, _ in _PRIOR_SIG_NAMES if isinstance(sig.get(k), (int, float))}
        if not saved:
            return {}
        analysis["prior_signals"] = saved      # 스냅샷에 함께 저장된다
    rows = [{"name": name, "pct": saved[k]} for k, name in _PRIOR_SIG_NAMES if isinstance(saved.get(k), (int, float))]
    return {"prior_sig": rows} if rows else {}


def build_prev_supply(analysis: dict, market_data: dict, target_date: str) -> dict:
    """이슈 점검의 '국내 · 실측' 카드 — 직전 거래일 정규장 마감(15:31~15:40) 투자자별 순매수(§51·§56).

    표시 순서는 개인 → 기관 → 외국인(§10). 단위는 억원. analysis에 넣어 스냅샷에 남긴다.
    """
    saved = analysis.get("prev_supply")
    if not isinstance(saved, dict):
        it = (market_data or {}).get("investor_trading") or {}
        if not _market_data_is_for(market_data, target_date) or not it.get("date"):
            return {}
        try:
            saved = {"date": str(it["date"]),
                     **{k: round(float(it[k]["net"]) / 100) for k in ("individual", "institution", "foreign")}}
        except (KeyError, TypeError, ValueError):
            return {}
        if str(saved["date"]) >= target_date.replace("-", ""):
            return {}                            # 아침 브리핑은 전 거래일 값만 — 오늘 장중 값이 아니다
        analysis["prev_supply"] = saved
    d = str(saved["date"])
    rows = [{"name": n, "eok": saved.get(k)} for k, n in (("individual", "개인"), ("institution", "기관"), ("foreign", "외국인"))
            if isinstance(saved.get(k), (int, float))]
    if len(rows) < 3:
        return {}
    return {"prev_supply": {"label": f"{int(d[4:6])}월 {int(d[6:8])}일", "rows": rows}}


def _issue_title(title: str) -> str:
    """'메타 실적 — 반응은 극과 극'에서 대시 뒤 부제를 뗀다. 남는 게 짧으면 원문(§45 retitle과 같은 기준)."""
    head = re.sub(r"\s*—.*$", "", title or "").strip()
    return head if len(head) >= 6 else (title or "")


def build_issue_check(us_cards: list) -> dict:
    """오늘의 이슈 점검 — 간밤 미국 카드(us_issue_results 실측)를 화면용으로 펼친다.
    숫자는 실측 그대로, 판정·코스피 영향은 붙이지 않는다(§45, 사용자 결정 2026-10-26)."""
    out = []
    for i, c in enumerate(us_cards or [], 1):
        title = c.get("title", "")
        sides = [s for s in (c.get("sides") or []) if isinstance(s, dict)]
        related = []
        for pat, stocks in ISSUE_RELATED_KR:
            if pat.search(title):
                for code, name in stocks:
                    related.append({"name": name})            # 종목 상세 페이지가 없어 이름만(2026-10-26)
                break
        # 쪽(side)별로 칩을 묶는다 — 문장(check_line)은 한쪽만 말해서, 다른 쪽 종목 칩이 설명 없이 붙어 있었다(2026-10-26)
        groups = []
        for s in sides:
            marks = [m for m in (s.get("marks") or []) if isinstance(m.get("pct"), (int, float))]
            if marks:
                groups.append({"label": s.get("label", ""), "marks": marks})
        if len(groups) < 2:                       # 한쪽뿐이면 라벨이 문장과 겹친다
            for g in groups:
                g["label"] = ""
        out.append({
            "title": _issue_title(title),
            "check_line": c.get("check_line", ""),
            "groups": groups,
            "proxy": next((s.get("proxy") for s in sides if s.get("proxy")), None),
            "duplicate_of": c.get("duplicate_of"),
            "related": related,
        })
    return {"ic_us_cards": out}


def _abs_time_label(published_at: str) -> str:
    """'2026-10-22 21:44' → '10/22 21:44'. 발행 뒤 굳는 정적 페이지라 상대 시각('3시간 전')을 쓰지 않는다(§20)."""
    try:
        d = datetime.strptime((published_at or "")[:16], "%Y-%m-%d %H:%M")
        return f"{d.month}/{d.day} {d:%H:%M}"
    except ValueError:
        return ""


def _domestic_card_title(window_from: str) -> str:
    """국내 뉴스 카드 제목 — '어제'가 아니라 수집 창의 실제 날짜로 쓴다(§24)."""
    try:
        d = datetime.strptime(window_from[:10], "%Y-%m-%d")
        return f"{d.month}월 {d.day}일 장 마감 이후 국내 소식"
    except (TypeError, ValueError):
        return "국내 소식"


MA5_BACKTEST_PATH = CONFIG_DIR / "monthly_ma5_backtest.json"


MA5_MARKETS = {
    # 코스피 아침(§61) — 허브 46종목·KRX 공식 종가
    "kr": {"key": "monthly_ma5", "file": "monthly_ma5.json", "bt": None,   # None = MA5_BACKTEST_PATH(호출 시점 값)
           "scope": "코스피200", "source": "KRX 공식 종가", "modal": "ma5m-modal"},
    # 미국(§67) — 미국 후보 대형주·정규장 종가. AI 종목 픽(진입·목표·손절)을 대체한다
    "us": {"key": "monthly_ma5_us", "file": "monthly_ma5_us.json", "bt": CONFIG_DIR / "monthly_ma5_us_backtest.json",
           "scope": "미국 대형주 후보", "source": "미국 정규장 종가", "modal": "ma5m-us-modal"},
}


def _ma5_price(v, market: str) -> str:
    return f"${v:,.2f}" if market == "us" else f"{v:,.0f}원"


def build_monthly_ma5(analysis: dict, target_date: str = "", market: str = "kr") -> dict:
    """월봉 5개월선 안착 종목 코너(sections/monthly_ma5.html) — 코스피 아침·미국 브리핑 공용.

    us_issue_results와 같은 구조다 — 스냅샷이 1순위고, 데이터 파일은 브리핑 날짜와 같을 때만 쓴다(§14·§45).
    조건 충족 종목이 없으면 섹션을 통째로 뺀다. 하단 '1년 뒤 오른 비율' 문장의 출처인 백테스트 파일이
    없어도 뺀다 — 그 문장 없이 종목만 보이면 '오른다'로 읽힌다(사용자 결정 2026-10-25).
    """
    cfg = MA5_MARKETS[market]
    data = analysis.get(cfg["key"])
    if not isinstance(data, dict):
        data = _read_monthly_ma5(target_date, cfg["file"])
        if data is not None:
            data = _drop_ma5_repeats(data, target_date, market)
            analysis[cfg["key"]] = data   # 스냅샷에 함께 저장된다 — 걸러낸 뒤라 재생성해도 같은 목록이다
    items = [x for x in ((data or {}).get("items") or []) if isinstance(x, dict) and x.get("strip")]
    stats = _ma5_backtest_stats(cfg["bt"])
    if not items or not stats:
        return {"ma5m_items": []}
    view = []
    for x in items:
        cells = []
        for c in x["strip"]:
            gap = c.get("gap_pct")
            tip = (f"{c.get('label', '')} {'현재' if c.get('cur') else '월말'} 종가 {_ma5_price(c['close'], market)}"
                   + (f" · 5개월선 {_ma5_price(c['ma5'], market)}" if c.get("ma5") else ""))
            cells.append({**c, "cls": "up" if (gap or 0) > 0 else "dn", "tip": tip,
                          "h": round(min(abs(gap or 0), 20) / 20 * 100)})
        nd = str(x.get("now_date") or "")
        view.append({**x, "cells": cells, "n": len(cells),
                     "now_label": f"{int(nd[4:6])}/{int(nd[6:8])}" if len(nd) == 8 else "",
                     "now_price": _ma5_price(x["now_close"], market),
                     "has_cur": bool(cells and cells[-1].get("cur")),
                     "last_label": f"{int(str(x['last_complete'])[4:])}월"})
    return {"ma5m_items": view, "ma5m_stats": {**stats, "scope": cfg["scope"], "source": cfg["source"]},
            "ma5m_modal": cfg["modal"]}


def _ma5_shown_this_month(target_date: str, market: str) -> set:
    """같은 달에 이미 발행된 브리핑(그 날짜 전)의 월봉 5개월선 코너에 나온 종목 코드.

    발행본 스냅샷이 원본이다(§4·§45) — 로컬 데이터 파일이 아니라 실제로 구독자에게 나간 목록을 센다.
    """
    if not target_date or len(target_date) < 7:
        return set()
    cfg = MA5_MARKETS[market]
    btype = "kospi" if market == "kr" else "us"
    seen = set()
    for snap in sorted(BRIEFINGS_DIR.glob(f"{target_date[:7]}-*/{btype}/analysis_snapshot.json")):
        if snap.parent.parent.name >= target_date:
            continue
        try:
            d = json.loads(snap.read_text(encoding="utf-8")).get(cfg["key"]) or {}
        except Exception:
            continue
        seen |= {x.get("code") for x in (d.get("items") or []) if isinstance(x, dict) and x.get("code")}
    return seen


def _drop_ma5_repeats(data: dict, target_date: str, market: str) -> dict:
    """한 번 실은 종목은 그 달에 다시 싣지 않는다(사용자 결정 2026-10-27) — 브리핑·텔레그램 공통.

    조건은 월봉 기준이라 한 달 내내 같은 종목이 매일 나왔다. 다음 달에도 조건을 채우면 다시 나온다.
    뺀 종목 이름은 기록으로 `repeat_hidden`에 남긴다. 실을 종목이 없으면 브리핑·텔레그램·첫 화면 모두 섹션째 빠진다.
    """
    seen = _ma5_shown_this_month(target_date, market)
    items = data.get("items") or []
    keep = [x for x in items if not (isinstance(x, dict) and x.get("code") in seen)]
    if len(keep) == len(items):
        return data
    hidden = [x.get("name") or x.get("code") for x in items if isinstance(x, dict) and x.get("code") in seen]
    print(f"[generate_html] 월봉 5개월선 — 이번 달에 이미 실은 종목 제외: {', '.join(hidden)}")
    return {**data, "items": keep, "repeat_hidden": hidden}


def _read_monthly_ma5(target_date: str, filename: str = "monthly_ma5.json"):
    """data/{filename} 을 읽되 브리핑 날짜가 같을 때만 돌려준다."""
    path = DATA_DIR / filename
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[generate_html] {filename} 파싱 실패: {e}")
        return None
    if target_date and data.get("date") != target_date:
        print(f"[generate_html] ⚠️ {filename} 날짜 불일치({data.get('date')} ≠ {target_date}) — 섹션 생략")
        return None
    return data


def _ma5_backtest_stats(path=None):
    """백테스트 설정 파일의 12개월 수치. 없거나 깨졌으면 None."""
    try:
        bt = json.loads((path or MA5_BACKTEST_PATH).read_text(encoding="utf-8"))
        h = bt["horizons"]["12"]
        y0, y1 = (int(v) for v in bt["years_label"].split("~"))
        return {"win_pct": h["signal"]["win_pct"], "base_win_pct": h["base"]["win_pct"],
                "n": h["signal"]["n"], "years": y1 - y0 + 1, "years_label": bt["years_label"],
                "universe": bt.get("universe", "")}
    except Exception as e:
        print(f"[generate_html] 월봉 5개월선 백테스트 수치 없음({e}) — 섹션 생략")
        return None


_PM_FUTURES = [("sp500_fut", "S&P500 선물"), ("nasdaq_fut", "나스닥 선물"), ("dow_fut", "다우 선물")]
_PM_STOCKS = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]


def _pct_of(d):
    """수집 데이터의 등락률 — get_ticker_full은 change_pct, 사이드바 선물(NQ)은 chg."""
    if not isinstance(d, dict):
        return None
    v = d.get("change_pct", d.get("chg"))
    return float(v) if isinstance(v, (int, float)) else None


def build_premarket_strip(analysis: dict, market_data: dict, target_date: str, gen_time: str = "") -> dict:
    """미국 브리핑 맨 위 '프리마켓 실측' 띠 — 지수선물 3종 + 빅테크 6종의 발행 시점 실체결가 등락(§0 ①·§26).

    fetch_data가 연장시간 체결로 잡은 값을 그대로 쓴다. analysis에 넣어 스냅샷에 남기고, 시장 데이터가
    이 날짜 것이 아니면 만들지 않는다. 값이 하나도 없으면 띠를 뺀다.
    """
    saved = analysis.get("premarket")
    if not isinstance(saved, dict):
        if not _market_data_is_for(market_data, target_date):
            return {}
        fut = (market_data or {}).get("futures") or {}
        big = (market_data or {}).get("bigtech") or {}
        saved = {
            "asof": gen_time,
            "futures": [{"name": n, "pct": _pct_of(fut.get(k))} for k, n in _PM_FUTURES if _pct_of(fut.get(k)) is not None],
            "stocks": [{"name": t, "pct": _pct_of(big.get(t))} for t in _PM_STOCKS if _pct_of(big.get(t)) is not None],
        }
        if not saved["futures"] and not saved["stocks"]:
            return {}
        analysis["premarket"] = saved          # 스냅샷에 함께 저장된다
    if not saved.get("futures") and not saved.get("stocks"):
        return {}
    return {"premarket": saved}


NASDAQ_BACKTEST_PATH = CONFIG_DIR / "nasdaq_overheat_backtest.json"
_NQ_BADGE = {"ok": "✓ 정상", "caution": "⚠️ 주의", "warn": "🚨 경고"}
_NQ_W, _NQ_H, _NQ_PADR, _NQ_PADT, _NQ_PADB = 640, 190, 8, 10, 22   # 그래프 SVG 좌표(프로토타입과 같다)


def build_nasdaq_check(analysis: dict, target_date: str = "") -> dict:
    """미국 브리핑 '나스닥 체크' 섹션 + 텔레그램 경고 블록의 공통 컨텍스트(§65).

    월봉 5개월선 코너와 같은 구조다 — 스냅샷이 1순위고, 데이터 파일은 브리핑 날짜와 같을 때만 쓴다(§14·§45).
    데이터가 없거나 하단 설명의 출처인 백테스트 파일이 없으면 빈 dict → 섹션·텔레그램 블록 모두 생략.
    텔레그램(call_claude._nasdaq_telegram_lines)도 이 함수로 읽어 페이지와 숫자가 어긋나지 않는다.
    """
    import nasdaq_overheat as nq
    data = analysis.get("nasdaq_overheat")
    if not isinstance(data, dict):
        data = _read_nasdaq_overheat(target_date)
        if data is not None:
            # 스냅샷에 함께 저장된다. 1990년부터의 긴 시계열(history)은 상세 페이지 전용이라 뺀다 —
            # 브리핑마다 수십 KB가 쌓인다(/stocks/nasdaq-check/, 2026-10-28).
            data = {k: v for k, v in data.items() if k != "history"}
            analysis["nasdaq_overheat"] = data
    if not data or not isinstance(data.get("gap_pct"), (int, float)):
        return {}
    try:
        bt = json.loads(NASDAQ_BACKTEST_PATH.read_text(encoding="utf-8"))
        bt["caution_band"]["fwd12_avg_pct"], bt["warn"]["dd20_pct"]          # 필수 키 확인
    except Exception as e:
        print(f"[generate_html] 나스닥 체크 백테스트 수치 없음({e}) — 섹션 생략")
        return {}
    gap = float(data["gap_pct"])
    level = nq.level_of(gap)                     # 저장된 level이 아니라 같은 판정 함수로 다시 정한다
    if level == "ok":
        # 정상 구간엔 섹션을 숨긴다 — 매일 같은 '정상'이 반복돼 뜻이 없었다(2026-10-26 사용자 결정).
        # 데이터는 위에서 analysis에 이미 넣었으므로 스냅샷·종목 홈 구조 신호에는 그대로 남는다.
        return {}
    month = str(data.get("month") or "")
    month_label = ("이번 달" if target_date and month == target_date[:7]
                   else (f"{int(month[5:7])}월" if len(month) == 7 else "이번 달"))
    return {"nq": {
        "gap": gap, "level": level, "badge": _NQ_BADGE[level],
        "high": data.get("high"), "ma60": data.get("ma60"),
        "streak": int(data.get("streak") or 0) if level != "ok" else 0,
        "pin": max(0.0, min(gap, 100.0)), "month_label": month_label,
        "chart": _nasdaq_chart(data.get("series") or [], data.get("peak"), nq.CAUTION, nq.WARN),
        "bt": bt, "caution": nq.CAUTION, "warn": nq.WARN,
    }}


def _nasdaq_chart(series: list, peak, caution: float, warn: float) -> dict:
    """2014년 이후 월별 위치 그래프 — SVG는 선·면·기준선만, 글자·점은 HTML로 겹친다(모바일에서 SVG가 가로로 눌려
    글자가 찌그러졌다). 좌표는 HTML용 퍼센트(top)·calc(left)로 같이 돌려준다."""
    pts = [s for s in series if isinstance(s, dict) and isinstance(s.get("g"), (int, float))]
    if len(pts) < 2:
        return {}
    W, H = _NQ_W, _NQ_H
    def Y(v):
        v = min(max(v, 0), 100)
        return _NQ_PADT + (H - _NQ_PADT - _NQ_PADB) * (1 - v / 100)
    xs = [i * (W - _NQ_PADR) / (len(pts) - 1) for i in range(len(pts))]
    line = " ".join(f"{x:.1f},{Y(p['g']):.1f}" for x, p in zip(xs, pts))
    left = lambda x: f"calc(34px + (100% - 34px) * {x / W:.4f})"
    top = lambda v: f"{Y(v) / H * 100:.2f}%"
    pi = max(range(len(pts)), key=lambda i: pts[i]["g"])
    pk = peak if isinstance(peak, dict) and peak.get("m") else pts[pi]
    return {
        "w": W, "h": H, "x1": W - _NQ_PADR, "line": line,
        "area": f"{xs[0]:.1f},{Y(0):.1f} {line} {xs[-1]:.1f},{Y(0):.1f}",
        "y100": f"{Y(100):.1f}", "y_warn": f"{Y(warn):.1f}", "y_caution": f"{Y(caution):.1f}",
        "h_warn": f"{Y(warn) - Y(100):.1f}", "h_caution": f"{Y(caution) - Y(warn):.1f}",
        "dot": {"left": left(xs[-1]), "top": top(pts[-1]["g"])},
        "peak_dot": {"left": left(xs[pi]), "top": top(pts[pi]["g"])},
        "axes": [{"v": int(v), "top": top(v)} for v in (warn, caution, 0)],
        "years": [{"y": p["m"][:4], "left": left(x)} for x, p in zip(xs, pts)
                  if p["m"].endswith("-01") and int(p["m"][:4]) % 2 == 0],
        "from_year": pts[0]["m"][:4],
        "peak_label": f"{int(pk['m'][:4])}년 {int(pk['m'][5:7])}월 {pk['g']:.0f}%",
    }


def _read_nasdaq_overheat(target_date: str):
    """data/nasdaq_overheat.json 을 읽되 브리핑 날짜가 같을 때만 돌려준다."""
    path = DATA_DIR / "nasdaq_overheat.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[generate_html] nasdaq_overheat 파싱 실패: {e}")
        return None
    if target_date and data.get("date") != target_date:
        print(f"[generate_html] ⚠️ nasdaq_overheat 날짜 불일치({data.get('date')} ≠ {target_date}) — 섹션 생략")
        return None
    return data


NASDAQ_PAGE_URL = f"{SITE_BASE}/stocks/nasdaq-check/"
_NQP_W, _NQP_H = 1000, 300        # 상세 페이지 그래프 SVG 좌표 — 늘려 그리고 글자·점은 HTML로 겹친다(_nasdaq_chart와 같은 방식)
_NQP_LOG_TICKS = (500, 1000, 2000, 5000, 10000, 20000, 50000)


def _nqp_years(hist: list) -> list:
    """5년마다 연도 눈금(1월 위치)."""
    n = len(hist)
    return [{"y": h["m"][:4], "left": f"{i / (n - 1) * 100:.2f}%"}
            for i, h in enumerate(hist) if h["m"].endswith("-01") and int(h["m"][:4]) % 5 == 0]


def _nqp_gap_chart(hist: list, caution: float, warn: float) -> dict:
    """① 월별 이격률(월봉 고점 ÷ 60개월선 − 1). 주의·경고 구간을 칠하고 0·기준선을 긋는다."""
    W, H = _NQP_W, _NQP_H
    gs = [h["g"] for h in hist]
    lo = min(-50.0, math.floor(min(gs) / 50) * 50)
    hi = max(100.0, math.ceil(max(gs) / 50) * 50)
    Y = lambda v: (hi - v) / (hi - lo) * H
    xs = [i * W / (len(hist) - 1) for i in range(len(hist))]
    line = " ".join(f"{x:.1f},{Y(g):.1f}" for x, g in zip(xs, gs))
    top = lambda v: f"{Y(v) / H * 100:.2f}%"
    pi = max(range(len(gs)), key=lambda i: gs[i])
    return {
        "w": W, "h": H, "line": line, "lo": lo, "hi": hi,   # 짚기 말풍선이 같은 눈금으로 점을 찍는다
        "area": f"0,{Y(0):.1f} {line} {W},{Y(0):.1f}",
        "y_hi": f"{Y(hi):.1f}", "y_warn": f"{Y(warn):.1f}", "y_caution": f"{Y(caution):.1f}", "y0": f"{Y(0):.1f}",
        "h_warn": f"{Y(warn) - Y(hi):.1f}", "h_caution": f"{Y(caution) - Y(warn):.1f}",
        "axes": [{"v": f"{int(v)}%", "top": top(v)} for v in range(int(lo), int(hi) + 1, 50)],
        "th": [{"v": f"{int(caution)} 주의", "top": top(caution), "cls": "caution"},
               {"v": f"{int(warn)} 경고", "top": top(warn), "cls": "warn"}],
        "dot": {"left": "100%", "top": top(gs[-1])},
        "peak": {"left": f"{xs[pi] / W * 100:.2f}%", "top": top(gs[pi]),
                 "label": f"{int(hist[pi]['m'][:4])}년 {int(hist[pi]['m'][5:7])}월 {gs[pi]:+.0f}%"},
        "years": _nqp_years(hist),
    }


def _nqp_level_chart(hist: list) -> dict:
    """② 나스닥 월봉 고점과 60개월선 — 1990년 ~400에서 2만 7천대까지라 로그 눈금으로 그린다."""
    W, H = _NQP_W, _NQP_H
    vals = [v for h in hist for v in (h["h"], h["ma"]) if v and v > 0]
    lo = min(vals) * 0.85
    hi = max(vals) * 1.12
    llo, lhi = math.log10(lo), math.log10(hi)
    Y = lambda v: (lhi - math.log10(v)) / (lhi - llo) * H
    xs = [i * W / (len(hist) - 1) for i in range(len(hist))]
    pts = lambda key: " ".join(f"{x:.1f},{Y(h[key]):.1f}" for x, h in zip(xs, hist))
    return {
        "w": W, "h": H, "high": pts("h"), "ma": pts("ma"), "llo": round(llo, 6), "lhi": round(lhi, 6),
        "axes": [{"v": f"{t:,}", "top": f"{Y(t) / H * 100:.2f}%"} for t in _NQP_LOG_TICKS if lo <= t <= hi],
        "years": _nqp_years(hist),
    }


def build_nasdaq_page(data: dict, bt: dict, target_date: str) -> dict:
    """/stocks/nasdaq-check/ 상세 페이지 컨텍스트. 숫자는 전부 수집 파일·백테스트 파일 그대로다(§0)."""
    import nasdaq_overheat as nq
    hist = [h for h in (data.get("history") or [])
            if isinstance(h, dict) and all(isinstance(h.get(k), (int, float)) for k in ("g", "h", "c", "ma"))]
    if len(hist) < 24 or not isinstance(data.get("gap_pct"), (int, float)):
        return {}
    gap = float(data["gap_pct"])
    level = nq.level_of(gap)
    month = str(data.get("month") or "")
    month_label = f"{int(month[:4])}년 {int(month[5:7])}월" if len(month) == 7 else "이번 달"
    last = str(data.get("last_date") or "")
    asof = f"{int(last[5:7])}월 {int(last[8:10])}일" if len(last) == 10 else ""
    brief = BRIEFINGS_DIR / target_date / "us" / "index.html"
    return {
        "nq": {
            "gap": gap, "level": level, "badge": _NQ_BADGE[level],
            "high": data.get("high"), "ma60": data.get("ma60"),
            "streak": int(data.get("streak") or 0), "pin": max(0.0, min(gap, 100.0)),
            "month_label": month_label, "asof": asof, "date": target_date,
            "caution": nq.CAUTION, "warn": nq.WARN, "bt": bt,
            "from_year": hist[0]["m"][:4],
            "gap_chart": _nqp_gap_chart(hist, nq.CAUTION, nq.WARN),
            "level_chart": _nqp_level_chart(hist),
            # 짚었을 때 띄울 월별 값 — [월, 이격률, 고점, 종가, 60개월선]
            "points": [[h["m"], h["g"], h["h"], h["c"], h["ma"]] for h in hist],
            "brief_url": f"/briefings/{target_date}/us/" if brief.exists() else "",
        },
        "canonical_url": NASDAQ_PAGE_URL,
        "seo_jsonld": [_jsonld(_breadcrumb([("홈", "/stocks/"), ("종목", "/stocks/"),
                                            ("나스닥 체크", "/stocks/nasdaq-check/")]))],
        "css_path": CSS_PATH, "js_path": JS_PATH,
    }


def write_nasdaq_page(target_date: str) -> bool:
    """그날 수집한 data/nasdaq_overheat.json으로 상세 페이지를 쓴다. 날짜가 다르거나 데이터·백테스트가
    없으면 쓰지 않는다 — 직전 페이지가 그대로 남는다(§14·§20)."""
    data = _read_nasdaq_overheat(target_date)
    if not data:
        return False
    try:
        bt = json.loads(NASDAQ_BACKTEST_PATH.read_text(encoding="utf-8"))
        bt["caution_band"]["fwd12_avg_pct"], bt["warn"]["dd20_pct"]
    except Exception as e:
        print(f"[generate_html] 나스닥 체크 상세 페이지 생략 — 백테스트 수치 없음({e})")
        return False
    ctx = build_nasdaq_page(data, bt, target_date)
    if not ctx:
        print("[generate_html] 나스닥 체크 상세 페이지 생략 — 1990년부터의 시계열(history)이 없음")
        return False
    html_out = make_env().get_template("pages/nasdaq_check.html").render(**ctx)
    out = WEB_DIR / "stocks" / "nasdaq-check" / "index.html"
    if gate_write(out, html_out, NASDAQ_PAGE_URL):
        GATE_BLOCKED.append(NASDAQ_PAGE_URL)
        return False
    print(f"[generate_html] 나스닥 체크 상세 페이지 → {out}")
    return True


def build_issues(analysis: dict) -> dict:
    """analysis.issues → 렌더용 이슈 리스트. title 없는 항목 제외, title·body 숫자 가드 적용."""
    issues = []
    for it in (analysis.get("issues") or []):
        title = _strip_issue_numbers(it.get("title", ""))
        if not title:
            continue
        entry = {"title": title, "body": _strip_issue_numbers(it.get("body", ""))}
        for side in ("down", "up"):
            s = it.get(side)
            if isinstance(s, dict) and (s.get("label") or s.get("tickers")):
                entry[side] = {"label": s.get("label", ""), "tickers": list(s.get("tickers") or [])}
        issues.append(entry)
    return {"issues": issues}


def build_us_tone(market_data: dict) -> dict:
    """leading_signal.compute_prior_us() 방향(실측 프리마켓·SOX·VIX 기반)을
    '오늘의 관점' 배경색 CSS 클래스로 매핑한다. 숫자·점수는 절대 반환하지 않는다 —
    코스피 dir_cls와 동일한 방식으로 색만 동기화하되 채점 대상은 아니다."""
    from leading_signal import compute_prior_us
    prior = compute_prior_us(market_data)
    dir_map = {"상승": "up", "하락": "dn", "중립": "neutral"}
    return {"dir_cls": dir_map.get(prior["direction"], "neutral")}


def _fmt_signed(value: float, decimals: int) -> tuple:
    """부호 있는 퍼센트 문자열을 만들되, 표시 자릿수로 반올림한 값을 그대로 분류에도 써서
    문자열과 up/dn 판정이 항상 일치하게 한다.

    round()가 -0.0을 만들 수 있고(예: round(-0.04, 1) == -0.0), -0.0은 파이썬에서
    0과 같다고 비교되면서도(-0.0 >= 0 은 True) 문자열 포맷은 부호를 그대로 찍어
    "-0.00%" 처럼 보인다 — 반올림 전 원값으로 up/dn을 판정하면 화면엔 0.00%인데
    파란색(dn)이 뜨는 모순이 생긴다. round() 이후 값이 0이면 +0.0으로 정규화해
    문자열도 부호도 항상 같은 값에서 나오게 한다."""
    v = round(value, decimals)
    if v == 0:
        v = 0.0
    return v, f"{v:+.{decimals}f}"


def build_overnight_bridge(market_data: dict) -> dict:
    """fetch_data.fetch_overnight_bridge()가 만든 원시 수치를 표시 문자열로 변환한다(§20).

    출력은 write_overnight_bridge_json()이 web/data/overnight-bridge.json으로 발행하고
    /stocks/ 홈 클라이언트가 렌더한다 — 브리핑 페이지에는 넣지 않는다(2026-08-03 배치 변경).

    market_data["overnight_bridge"]는 섹터별 행 리스트({sector, us_label, us_change,
    kr_label, kr_change, gap_pp, kr_session_date}) 또는 None(섹션 생략)이다.
    None이거나 키가 없으면(또는 빈 리스트면) 소비처가 섹션을 건너뛸 수 있도록 빈 리스트를 돌려준다 —
    fetch 단계가 이미 데이터 없음을 판정했으므로 여기서 다시 채워 넣지 않는다(§0).

    이 섹션은 선택 섹션이다 — 행 하나가 깨져 있다고 07:25 브리핑 전체를 죽이면 안 된다
    (§0 부칙). market_data는 latest_kospi.json에서 오는데, §23/§28 정정 절차로 사람이
    직접 손으로 고치는 파일이라 필드가 null이거나 타입이 틀린 실제 실패 모드가 있다.
    build_us_issue_results가 컨테이너가 아니라 항목 단위로 isinstance(dict) 가드를 거는 것과
    같은 방식으로, 행 하나가 dict가 아니거나 숫자 필드가 숫자가 아니거나(None·문자열 등)
    거래일이 없으면 그 행만 건너뛴다 — 자리표시자를 채워 넣지 않는다(§0, 없으면 지어내지
    않고 비운다). 건너뛴 행은 stderr에 로그를 남긴다 — 이 데이터가 수동 편집 파일에서
    오므로, 조용히 넘어가면 §20류 사고(낡거나 깨진 값이 계속 진짜처럼 보이는 것)처럼
    편집 실수가 몇 번이고 재현돼도 아무도 못 알아챈다.

    kr_session_date는 모든 행에서 동일한 값이라 행마다 반복하지 않고 최상위 키
    overnight_bridge_date로 한 번만 올린다 — 소비처가 "N일 한국 마감 vs 간밤 미국장" 같은
    섹션 헤더 라벨을 한 곳에서만 채우면 되고(§24 상대 시간 라벨 금지 규칙과 동일하게
    렌더 시점에 실제 날짜를 명시), 행마다 같은 문자열을 반복해 소비처에서 매번 [0]을
    꺼내 쓰게 만들지 않기 위함이다. fetch_data.py가 단일 루프 안 로컬 변수 하나에서
    모든 행의 날짜를 채우므로 정상 상태에선 항상 하나로 일치하지만(구조적 보장), 그
    보장이 깨진 경우(수동 편집 등)엔 첫 값을 유지하고 불일치를 stderr에 남긴다 — 조용히
    마지막 값으로 덮어써 엉뚱한 날짜를 모든 행에 붙이는 것보다, 실패를 눈에 띄게 하는
    쪽을 택한다. 날짜 없는 행은 그 행 자체를 건너뛰므로, 표시되는 행이 하나라도 있으면
    overnight_bridge_date는 항상 비어 있지 않다 — 날짜 없이 행만 떠 있는 상태(§24 위반)를
    구조적으로 방지한다.
    """
    rows = market_data.get("overnight_bridge")
    empty = {"overnight_bridge": [], "overnight_bridge_date": ""}
    if not isinstance(rows, list) or not rows:
        return empty

    out = []
    session_date = ""
    for r in rows:
        if not isinstance(r, dict):
            print("[generate_html] overnight_bridge: 행이 dict가 아니라 건너뜀.", file=sys.stderr)
            continue

        # 진단 로그용 이름. sector가 문자열이 아니면(NaN 등) 그대로 찍어도 오해만 부르므로
        # "?"로 대체한다 — float("nan")은 truthy라 `or "?"` 만으로는 걸러지지 않는다.
        raw_sector = r.get("sector")
        sector = raw_sector if isinstance(raw_sector, str) and raw_sector else "?"

        # 라벨 3종은 그대로 JSON에 실려 나가는 값이라 숫자 필드와 같은 강도로 검사한다.
        # 이름을 못 붙이는 행은 화면에 설명할 수단이 없으므로 자리표시자를 채우지 않고
        # 행 자체를 건너뛴다(§0 — 없으면 비우고 지어내지 않는다). 특히 라벨에 NaN·Infinity가
        # 들어오면 json.dumps가 예외 없이 맨몸 NaN 리터럴을 써서 파일 전체가 유효하지 않은
        # JSON이 되고, 클라이언트의 JSON.parse가 통째로 실패해 /stocks/ 블록이 죽는다 —
        # 숫자 필드의 "+nan%p" 표시 불일치보다 훨씬 단단한 고장이라 같은 자리에서 막는다.
        labels = {}
        bad_label = False
        for key in ("sector", "us_label", "kr_label"):
            val = r.get(key)
            if not isinstance(val, str) or not val:
                print(
                    f"[generate_html] overnight_bridge: {sector} 행의 {key} 값({val!r})이 "
                    "비어 있지 않은 문자열이 아니라 행을 건너뜀.",
                    file=sys.stderr,
                )
                bad_label = True
                break
            labels[key] = val
        if bad_label:
            continue

        nums = {}
        malformed = False
        for key in ("us_change", "kr_change", "gap_pp"):
            val = r.get(key, 0.0)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                print(
                    f"[generate_html] overnight_bridge: {sector} 행의 {key} 값({val!r})이 "
                    "숫자가 아니라 행을 건너뜀.",
                    file=sys.stderr,
                )
                malformed = True
                break
            if not math.isfinite(val):
                # NaN·Infinity도 float이라 위 타입 검사를 통과한다. 그대로 두면
                # NaN은 "+nan%p"·gap_cls="" 로 렌더돼 문자열과 분류가 어긋나고
                # (이 함수가 지키기로 한 불변식 위반), Infinity는 "+inf%"가 그대로 나간다.
                # 파이썬 표준 json이 NaN·Infinity 리터럴을 그대로 읽고 쓰므로
                # §23/§28 수동 정정으로 latest_kospi.json을 손으로 고치다 실제로 섞일 수 있다.
                print(
                    f"[generate_html] overnight_bridge: {sector} 행의 {key} 값({val!r})이 "
                    "유한한 숫자가 아니라 행을 건너뜀.",
                    file=sys.stderr,
                )
                malformed = True
                break
            nums[key] = float(val)
        if malformed:
            continue

        row_date = r.get("kr_session_date")
        if not isinstance(row_date, str) or not row_date:
            print(
                f"[generate_html] overnight_bridge: {sector} 행에 kr_session_date가 없어 건너뜀.",
                file=sys.stderr,
            )
            continue

        if not session_date:
            session_date = row_date
        elif row_date != session_date:
            print(
                f"[generate_html] overnight_bridge: 행 간 kr_session_date 불일치"
                f"({session_date!r} vs {row_date!r}) — 먼저 나온 값을 유지.",
                file=sys.stderr,
            )

        us_r, us_num = _fmt_signed(nums["us_change"], 2)
        kr_r, kr_num = _fmt_signed(nums["kr_change"], 2)
        gap_r, gap_num = _fmt_signed(nums["gap_pp"], 1)

        out.append({
            "sector": labels["sector"],
            "us_label": labels["us_label"],
            "kr_label": labels["kr_label"],
            "us_change_fmt": f"{us_num}%",
            "kr_change_fmt": f"{kr_num}%",
            "us_cls": "up" if us_r >= 0 else "dn",
            "kr_cls": "up" if kr_r >= 0 else "dn",
            "gap_fmt": f"{gap_num}%p",
            "gap_cls": "up" if gap_r > 0 else ("dn" if gap_r < 0 else ""),
            "gap_word": "선반영" if gap_r > 0 else ("미반영" if gap_r < 0 else "동조"),
        })

    if not out:
        return empty

    return {"overnight_bridge": out, "overnight_bridge_date": session_date}


def build_prediction(analysis: dict, index_name: str, pred_title: str, gen_time: str) -> dict:
    pred = analysis.get("prediction", {})
    up_pct = pred.get("up_pct", 50)
    down_pct = pred.get("down_pct", 100 - up_pct)
    direction = pred.get("direction", "중립")
    confidence = pred.get("confidence", 70)
    is_up = "상승" in direction
    dir_cls = "up" if is_up else ("dn" if "하락" in direction else "neutral")
    band_color = "#E03131" if is_up else "#2775ED"
    dots = max(1, min(5, round(confidence / 20)))
    conf_label = "강함" if confidence >= 80 else ("보통" if confidence >= 60 else "약함")
    basis = pred.get("basis")
    if basis == BASIS_OPEN and index_name.upper().startswith("KOSPI"):
        pred_title = "KOSPI 시초가 방향 예측"
    return {
        "pred_title": pred_title,
        "pred_basis": basis,          # "open"이면 시초가 기준(§57). 옛 스냅샷엔 없다 → 템플릿이 옛 문구를 쓴다
        "direction": direction,
        "dir_cls": dir_cls,
        "dir_arrow": "↑" if is_up else ("↓" if "하락" in direction else "→"),
        "dir_word": "상승" if is_up else "하락",
        "up_pct": up_pct,
        "down_pct": down_pct,
        "readout_pct": up_pct if is_up else down_pct,
        "band_left": max(0, min(86, (up_pct if is_up else up_pct) - 7)),
        "band_width": 14,
        "band_color": band_color,
        "confidence": confidence,
        "confidence_dots": dots,
        "confidence_label": conf_label,
        "generated_time": gen_time,
    }


def build_scenario_context(analysis: dict) -> dict:
    """시나리오 분기 형식용 컨텍스트. analysis_format == 'scenario' 일 때 사용."""
    return {
        "sc_summary": analysis.get("sc_summary", ""),
        "sc_left_label": analysis.get("sc_left_label", "하락 근거"),
        "sc_right_label": analysis.get("sc_right_label", "반등 가능성"),
        "sc_left_items": analysis.get("sc_left_items", [])[:3],
        "sc_right_items": analysis.get("sc_right_items", [])[:3],
        "sc_footer": analysis.get("sc_footer", ""),
    }


def build_why_what_so_context(analysis: dict) -> dict:
    """WHY/WHAT/SO WHAT 형식용 컨텍스트. analysis_format == 'why_what_so' 일 때 사용."""
    b_rows = []
    for label, key, sw in [("WHY", "why", False), ("WHAT", "what", False), ("SO?", "so_what", True)]:
        if analysis.get(key):
            b_rows.append({"label": label, "text": analysis[key], "so_what": sw})
    return {
        "reason_lead": analysis.get("reason_lead", ""),
        "b_rows": b_rows,
    }


def build_qa_context(analysis: dict) -> dict:
    """Q&A 문답 형식용 컨텍스트. analysis_format == 'qa' 일 때 사용."""
    items = []
    for it in analysis.get("qa_items", [])[:3]:
        if it.get("q") and it.get("a"):
            items.append({"q": it["q"], "a": it["a"]})
    return {"qa_items": items}


def build_signal_context(analysis: dict) -> dict:
    """신호등 스코어보드 형식용 컨텍스트. analysis_format == 'signal' 일 때 사용."""
    items = []
    for it in analysis.get("sig_items", [])[:5]:
        lvl = it.get("level", "neu")
        if lvl not in ("up", "neu", "down"):
            lvl = "neu"
        if it.get("label") and it.get("desc"):
            items.append({"level": lvl, "label": it["label"], "desc": it["desc"]})
    tone = analysis.get("sig_tone", "neu")
    if tone not in ("up", "neu", "down"):
        tone = "neu"
    return {
        "sig_verdict": analysis.get("sig_verdict", ""),
        "sig_tone": tone,
        "sig_items": items,
    }


def build_flow_context(analysis: dict) -> dict:
    """인과 흐름 체인 형식용 컨텍스트. analysis_format == 'flow' 일 때 사용."""
    steps = []
    for it in analysis.get("flow_steps", [])[:4]:
        d = it.get("dir", "neu")
        if d not in ("up", "neu", "down"):
            d = "neu"
        if it.get("title") and it.get("text"):
            steps.append({
                "stage": it.get("stage", ""),
                "dir": d,
                "title": it["title"],
                "text": it["text"],
            })
    return {"flow_lead": analysis.get("flow_lead", ""), "flow_steps": steps}


def build_keynum_context(analysis: dict) -> dict:
    """핵심 숫자 카드 형식용 컨텍스트. analysis_format == 'keynum' 일 때 사용."""
    cards = []
    for it in analysis.get("num_cards", [])[:4]:
        d = it.get("dir", "neu")
        if d not in ("up", "neu", "down"):
            d = "neu"
        if it.get("label") and it.get("value"):
            cards.append({
                "label": it["label"],
                "value": it["value"],
                "dir": d,
                "caption": it.get("caption", ""),
            })
    return {"num_cards": cards, "num_take": analysis.get("num_take", "")}


def _split_comfort_line(text: str) -> str:
    """comfort_line을 문장 단위(.!?)로 쪼개 <br>로 줄바꿈한다."""
    text = (text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    return "<br>".join(p for p in parts if p)


def _load_quote_today(target_date: str) -> dict:
    """quote_today.json이 이 브리핑 날짜와 일치할 때만 {quote, author}를 반환한다.
    call_claude.py의 render_outputs()가 코스피 타입일 때만 이 파일을 쓴다."""
    if not QUOTE_TODAY_FILE.exists():
        return {}
    try:
        q = load_json(QUOTE_TODAY_FILE)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(q, dict):
        return {}
    if q.get("date") != target_date or not q.get("quote") or not q.get("author"):
        return {}
    return {"quote": q["quote"], "author": q["author"]}


def build_reasons(analysis: dict, target_date: str = "") -> dict:
    direction = analysis.get("prediction", {}).get("direction", "")
    fallback = {
        "상승 우위": "왜 오를까? — 오늘의 상승 시그널",
        "하락 우위": "왜 내릴까? — 오늘의 하락 시그널",
    }.get(direction, "오를까 내릴까? — 오늘의 핵심 변수")
    fmt = analysis.get("analysis_format", "why_what_so")
    ctx = {
        "analysis_format": fmt,
        "reason_title": analysis.get("reason_title") or fallback,
        "comfort_line": _split_comfort_line(analysis.get("comfort_line", "")),
        # 이렇게 보는 이유 — 예측 방향의 핵심 동인 3개(넘버링). 형식과 무관하게 항상 표시.
        "key_drivers": analysis.get("key_drivers") or [],
    }
    # 직전 미국장 이슈의 실측 채점 결과. 카드가 없으면 템플릿에서 자동 생략.
    ctx.update(build_us_issue_results(analysis, target_date))
    if fmt == "split":
        pass  # split은 오늘의 관점 본문이 todays_view.recap/outlook — 별도 형식 컨텍스트 불필요
    elif fmt == "scenario":
        ctx.update(build_scenario_context(analysis))
    elif fmt == "why_what_so":
        ctx.update(build_why_what_so_context(analysis))
    elif fmt == "qa":
        ctx.update(build_qa_context(analysis))
    elif fmt == "signal":
        ctx.update(build_signal_context(analysis))
    elif fmt == "flow":
        ctx.update(build_flow_context(analysis))
    elif fmt == "keynum":
        ctx.update(build_keynum_context(analysis))
    return ctx


def _chg_cell(chg) -> dict:
    """등락률 셀의 표시 문자열과 색상 클래스.

    세 상태를 구분한다 — 모름(None) / 보합(정확히 0) / 상승·하락.
    예전엔 `>= 0`으로 뭉뚱그려 0.00%가 ▲·상승색(빨강)으로 나갔다. 방향성이 핵심인
    화면에서 '안 움직임'과 '올랐음'이 같은 모습이면 안 된다.
    """
    if chg is None:
        return {"chg": "", "chg_cls": "unknown"}
    if chg == 0:
        return {"chg": "— 0.00%", "chg_cls": "flat"}
    return {
        "chg": f"{'▲' if chg > 0 else '▼'} {chg:+.2f}%",
        "chg_cls": "up" if chg > 0 else "down",
    }


def build_market_items(market_data: dict, internal_type: str, gen_time: str) -> list:
    """시장 지표 사이드바 — VIX와 공포·탐욕 지수 두 항목만 표시한다.

    2026-08-31에 나스닥·필라델피아 반도체·나스닥100 선물 행을 화면에서 뺐다(수집은 유지 —
    분석 프롬프트와 다른 위젯이 계속 소비한다). 이 패널은 '지수 시세'가 아니라 '투자 심리'를
    보여주는 자리다. 데이터가 없으면 그 행을 그리지 않는다(§0 — 없으면 비운다).
    """
    if internal_type not in ("kospi", "us"):
        return []
    mdj = dict(market_data.get("market_data_js", {}))
    if "vix" not in mdj and market_data.get("vix"):
        mdj["vix"] = market_data["vix"]
    items = []

    # VIX — S&P500 30일 내재변동성
    vix = mdj.get("vix")
    if isinstance(vix, dict) and vix.get("price") is not None:
        p = vix["price"]
        lvls = [(15, "안정", "calm"), (20, "보통", "normal"), (30, "경계", "elevated"),
                (40, "불안", "high"), (10 ** 9, "극단", "high")]
        _, lbl, cls = next(x for x in lvls if p < x[0])
        cp = vix.get("change_pct", 0)
        items.append({
            "name": "VIX 공포지수", "info_modal": "vix-modal",
            "val": f"{p:.2f}",
            "chg": f"{'+' if cp >= 0 else ''}{cp:.2f}%",
            "chg_cls": "up" if cp >= 0 else "down",
            "badge": lbl, "badge_cls": cls,
        })
    return items


def build_fng_dial(market_data: dict, internal_type: str) -> dict:
    """공포·탐욕 지수 반원 다이얼. 데이터가 없거나 낡았으면 빈 dict → 섹션 생략(§0).

    아치 좌표는 반지름 82 · 중심 (100,100)의 고정값이라 템플릿에 상수로 두고,
    여기서는 바늘 각도만 계산한다. 0점=왼쪽(-90°), 100점=오른쪽(+90°)이므로
    각도 = (점수 - 50) × 1.8.
    """
    if internal_type not in ("kospi", "us"):
        return {}
    mdj = market_data.get("market_data_js", {})
    fng = mdj.get("fng")
    if not isinstance(fng, dict) or not _fng_is_fresh(fng):
        return {}
    score = fng["score"]
    label, cls = _fng_label(score, fng.get("rating"))
    prev = fng.get("prev_close")
    sub = ""
    if isinstance(prev, (int, float)):
        # 0~100 점수라 등락'률'이 아니라 포인트 차이로 보여준다.
        d = score - prev
        # 표시상 0.0p가 되는 구간은 아예 비운다 — '보합'이라는 틀린 주장을 막기 위함(§0).
        # CNN은 미국 정규장이 열리기 전에 이미 직전 종가를 previous_close로 넘기는데,
        # 새 세션 값은 아직 없어 score와 previous_close가 **완전히 같아진다**. 미국 브리핑은
        # 21:15 KST(= 프리마켓)에 나가므로 이 구간에 정확히 걸리고, 비우지 않으면 매일
        # '+0.0p'가 찍힌다(2026-08-31 확인). 소수 13자리가 우연히 일치할 일은 없으므로
        # 이 조건은 사실상 '아직 갱신 안 됨'만 잡는다.
        if abs(d) >= 0.05:
            sub = f"전일 {prev:.1f} · {'+' if d >= 0 else ''}{d:.1f}p"
    return {
        "score": f"{score:.0f}",
        "needle_deg": round((max(0.0, min(100.0, score)) - 50) * 1.8, 2),
        "state": label,
        "state_cls": cls,
        "sub": sub,
    }


# CNN 등급 → 한국어 라벨. 뱃지 색은 기존 vix-badge 팔레트를 재사용한다 —
# 공포·탐욕은 양쪽 끝이 모두 위험 구간이라 극단을 red(high), 그 안쪽을 yellow(elevated),
# 중립을 green(calm)으로 둔다.
_FNG_RATING_KO = {
    "extreme fear":  ("극단적 공포", "high"),
    "fear":          ("공포", "elevated"),
    "neutral":       ("중립", "calm"),
    "greed":         ("탐욕", "elevated"),
    "extreme greed": ("극단적 탐욕", "high"),
}


def _fng_label(score: float, rating) -> tuple:
    """CNN이 준 등급을 우선 쓰고, 없거나 모르는 값이면 점수 구간으로 되돌린다."""
    hit = _FNG_RATING_KO.get((rating or "").strip().lower())
    if hit:
        return hit
    for upper, key in ((25, "extreme fear"), (45, "fear"), (55, "neutral"), (75, "greed")):
        if score < upper:
            return _FNG_RATING_KO[key]
    return _FNG_RATING_KO["extreme greed"]


def _fng_is_fresh(fng: dict, max_age_days: int = 5, now=None) -> bool:
    """수집이 조용히 죽었을 때 낡은 값을 계속 보여주지 않기 위한 신선도 게이트(§20).

    CNN은 미국 정규장 기준으로 갱신되므로 주말·연휴엔 며칠 묵는 게 정상이다.
    3일 연휴 + 주말을 감안해 5일까지 허용하고, 그보다 오래되면 행을 그리지 않는다.
    """
    if not isinstance(fng.get("score"), (int, float)):
        return False
    asof = fng.get("asof")
    if not asof:
        print("[generate_html] ⚠️ 공포·탐욕 지수에 수집 시각이 없어 표시하지 않습니다.", file=sys.stderr)
        return False
    try:
        ts = datetime.fromisoformat(str(asof).replace("Z", "+00:00"))
    except ValueError:
        print(f"[generate_html] ⚠️ 공포·탐욕 지수 시각 파싱 실패: {asof}", file=sys.stderr)
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ref = now or datetime.now(timezone.utc)
    age_days = (ref - ts).total_seconds() / 86400.0
    if age_days > max_age_days:
        print(f"[generate_html] ⚠️ 공포·탐욕 지수가 {age_days:.1f}일 지났습니다 — 표시 생략.",
              file=sys.stderr)
        return False
    return True


def _shares_label(n) -> str:
    """주 수 → '66.9만주'·'2억 2,320만주'·'9,800주'(부호 없음)."""
    n = abs(int(n))
    if n >= 100_000_000:
        eok, man = divmod(n, 100_000_000)
        return f"{eok}억 {man // 10_000:,}만주" if man >= 10_000 else f"{eok}억주"
    if n >= 10_000:
        return f"{n / 10_000:,.1f}만주"
    return f"{n:,}주"


def build_close_vs(vs: dict) -> dict:
    """/api/intraday?vs=close 요약 → '어제와 비교' 한 줄 + 사이드바 섹터 막대(종목 홈 마감 카드와 같은 값)."""
    out = {}
    k, vol, amp = vs.get("kospi") or {}, vs.get("vol") or {}, vs.get("amp") or {}
    num = lambda x: isinstance(x, (int, float))
    rel = vs.get("prev_rel") or "어제"
    cells = []
    if num(k.get("t")):
        cells.append({"lbl": "코스피", "val": f"{k['t']:+.2f}%", "cls": "up" if k["t"] > 0 else "dn" if k["t"] < 0 else "",
                      "sub": f"{rel} {k['y']:+.2f}%" if num(k.get("y")) else ""})
    if num(vol.get("diff")):
        cells.append({"lbl": "거래량", "val": f"{vol['diff']:+.1f}%", "cls": "",
                      "sub": _shares_label(vol["t"] * 1000) if num(vol.get("t")) else ""})
    if num(amp.get("t")):
        cells.append({"lbl": "진폭", "val": f"{amp['t']:.2f}%", "cls": "",
                      "sub": f"{rel} {amp['y']:.2f}%" if num(amp.get("y")) else ""})
    if cells:
        pd = str(vs.get("prev_date") or "")
        out["vs_line"] = {"title": vs.get("verdict") or "", "tone": vs.get("tone") or "", "cells": cells,
                          "basis": (f"{int(pd[5:7])}/{int(pd[8:10])} vs " if len(pd) == 10 else "")
                                   + f"{int(vs['today'][5:7])}/{int(vs['today'][8:10])} · 15:30 확정"}
    secs = [x for x in vs.get("sectors") or [] if num(x.get("t"))]
    if secs:
        secs.sort(key=lambda x: -x["t"])
        mx = max(abs(x["t"]) for x in secs) or 1
        out["sector_bars"] = [{
            "name": x.get("label", ""), "pct": f"{x['t']:+.2f}%", "cls": "up" if x["t"] >= 0 else "dn",
            "w": round(abs(x["t"]) / mx * 50, 1), "neg": x["t"] < 0,
            "move": (f"▲{x['move']}" if x["move"] > 0 else f"▼{-x['move']}") if num(x.get("move")) and x["move"] else "",
            "partial": x.get("n") if num(x.get("n")) and x["n"] < 3 else None,
        } for x in secs]
    return out


def build_close_leaders(rows: list) -> list:
    """주도주 3종목 마감 — 공식 종가·등락·외국인 5일 순매수(주). 종가가 없는 종목은 빠져 있다."""
    out = []
    for r in rows:
        if not isinstance(r.get("close"), (int, float)) or not isinstance(r.get("change_pct"), (int, float)):
            continue
        cp = r["change_pct"]
        f5 = r.get("frgn5") or {}
        row = {"name": r.get("name", ""), "close": f"{int(r['close']):,}",
               "chg": f"{'▲' if cp > 0 else '▼' if cp < 0 else ''} {cp:+.2f}%".strip(),
               "cls": "up" if cp > 0 else "dn" if cp < 0 else ""}
        if isinstance(f5.get("sum"), (int, float)):
            row["frgn5"] = ("+" if f5["sum"] > 0 else "−" if f5["sum"] < 0 else "") + _shares_label(f5["sum"])
            row["frgn5_cls"] = "up" if f5["sum"] > 0 else "dn" if f5["sum"] < 0 else ""
            fr, to = str(f5.get("from", "")), str(f5.get("to", ""))
            if len(fr) == 8 and len(to) == 8:
                row["frgn5_range"] = f"{int(fr[4:6])}/{int(fr[6:])}~{int(to[4:6])}/{int(to[6:])}"
        out.append(row)
    return out


def build_close_sections(analysis: dict, market: dict, index_name: str, target_date: str) -> dict:
    """마감 전용 섹션 컨텍스트 (있는 데이터만)."""
    ctx = {}
    indices = market.get("indices", {})
    kospi = indices.get("kospi", {})
    intraday = market.get("intraday", {})

    # close_hero
    prices = intraday.get("prices", [])
    if prices and kospi:
        cp = kospi.get("change_pct", 0)
        ca = kospi.get("change_abs", 0)
        up = cp >= 0
        price = kospi.get("price", 0)
        ta = market.get("trade_amount", {})
        subs = []
        for name, key in [("KOSDAQ", "kosdaq"), ("원/달러", "usdkrw")]:
            d = indices.get(key)
            if isinstance(d, dict) and d.get("price") is not None:
                scp = d.get("change_pct")
                subs.append({
                    "name": name,
                    "val": f"{d['price']:,.2f}",
                    # 등락률을 모르면(None) 셀을 비운다 — 0.00%로 채우면 '보합'이라는
                    # 틀린 주장이 된다. 진짜 보합은 화살표 없이 중립색으로 구분한다.
                    **_chg_cell(scp),
                })
        ctx.update({
            "index_name": index_name,
            "close_val": f"{price:,.2f}",
            "close_chg": f"{'▲' if up else '▼'} {abs(ca):.2f} ({cp:+.2f}%)",
            "close_chg_cls": "up" if up else "down",
            "vol_label": "코스피 거래대금",
            "vol_val": ta.get("formatted") or "—",
            "intraday_prices": prices,
            "prev_close": round(price - ca, 2),
            "intraday_axis": ["09:00", "10:30", "12:00", "13:30", "15:20"],
            "sub_indices": subs,
        })

    # close_reason 섹션
    if analysis.get("market_title") or analysis.get("reason_title"):
        fmt = analysis.get("analysis_format", "why_what_so")
        ctx["analysis_format"] = fmt
        ctx["reason_title"] = analysis.get("market_title") or analysis.get("reason_title", "")
        ctx["close_dek"] = analysis.get("dek", "")   # 타이틀 아래 서브 한 문장 — 텔레그램과 같은 필드(§62)
        ctx["comfort_line"] = _split_comfort_line(analysis.get("comfort_line", ""))
        if fmt == "brief":   # 세 줄 요약(원인·주도·다음) — 2026-10-29부터 마감 고정 형식
            ctx["brief_lines"] = [{"k": str(it.get("k", "")), "text": str(it.get("text", ""))}
                                  for it in (analysis.get("brief_lines") or [])
                                  if isinstance(it, dict) and it.get("text")]
        elif fmt == "scenario":
            ctx.update(build_scenario_context(analysis))
        elif fmt == "qa":
            ctx.update(build_qa_context(analysis))
        elif fmt == "signal":
            ctx.update(build_signal_context(analysis))
        else:  # why_what_so (옛 발행본)
            ctx["reason_lead"] = analysis.get("market_summary", "")
            b_rows = []
            for label, key, sw in [("WHY", "why", False), ("WHAT", "what", False), ("SO?", "so_what", True)]:
                if analysis.get(key):
                    b_rows.append({"label": label, "text": analysis[key], "so_what": sw})
            ctx["b_rows"] = b_rows

    # close_breadth (market_breadth 있을 때만)
    mb = market.get("market_breadth", {})
    if mb:
        rows = []
        if any(k in mb for k in ("up", "down", "unchanged")):
            rows.append({"label": "등락", "cells": [
                {"lbl": "상승", "val": mb.get("up", 0), "cls": "up"},
                {"lbl": "하락", "val": mb.get("down", 0), "cls": "down"},
                {"lbl": "보합", "val": mb.get("unchanged", 0), "cls": "neutral"},
            ]})
        # 신고가·신저가는 원천이 없어 0으로 채워진 값이었다 — 그리지 않는다(2026-10-28, §0). 옛 데이터 파일의 0도 무시한다.
        if any(k in mb for k in ("upper_limit", "lower_limit")):
            rows.append({"label": "특이 종목", "cells": [
                {"lbl": "상한가", "val": mb.get("upper_limit", 0), "cls": "up"},
                {"lbl": "하한가", "val": mb.get("lower_limit", 0), "cls": "down"},
            ]})
        if rows:
            ctx["breadth_rows"] = rows

    # 어제와 비교 · 섹터별 오늘 등락 · 주도주 3종목(2026-10-29) — 수집일이 브리핑 날짜와 같을 때만(§14)
    vs = market.get("vs_close") or {}
    if vs.get("today") == target_date:
        ctx.update(build_close_vs(vs))
    if str(market.get("generated_at", ""))[:10] == target_date:
        leaders = build_close_leaders(market.get("leaders") or [])
        if leaders:
            ctx["leaders"] = leaders

    # close_sector
    sectors = market.get("sectors", [])
    if sectors:
        ctx["sectors"] = [{
            "name": s.get("name", ""),
            "pct": f"{s.get('change_pct', 0):+.1f}%",
            "cls": "up" if s.get("change_pct", 0) >= 0 else "dn",
        } for s in sectors[:8]]
        if sectors[0].get("basis"):
            ctx["sector_basis"] = sectors[0]["basis"]   # 16시 뒤 대표 3종목 공식 종가로 채운 날(2026-10-28)

    # close_supply (수급) — fetch_investor_trading 구조: {player: {"net": 백만원}}
    inv = market.get("investor_trading", {})
    if isinstance(inv, dict) and inv:
        hist = update_supply_history(target_date, inv)
        cells = []
        for label, key in [("외국인", "foreign"), ("기관", "institution"), ("개인", "individual")]:
            d = inv.get(key)
            if not isinstance(d, dict) or d.get("net") is None:
                continue
            eok = round(d["net"] / 100)  # 백만원 → 억원
            up = eok >= 0
            cells.append({
                "label": label,
                "amt": f"{eok:+,}억",
                "amt_cls": "up" if up else "down",
                "sub": "순매수" if up else "순매도",
                "flow": supply_flow(hist, key, target_date),  # 최근 7일 흐름(누적)
            })
        if cells:
            ctx["supply_cells"] = cells

    # 3일 수급 흐름 (supply_history.json → 투자자별 3일 트렌드)
    supply_hist_path = DATA_DIR / "supply_history.json"
    supply_hist = load_json(supply_hist_path) if supply_hist_path.exists() else {}
    if supply_hist:
        sorted_dates = sorted(supply_hist.keys(), reverse=True)[:3]  # 최신순
        sorted_dates_asc = list(reversed(sorted_dates))              # 오래된→최신

        investor_defs = [
            ("foreign",     "frgn",  "외국인"),
            ("institution", "inst",  "기관"),
            ("individual",  "indiv", "개인"),
        ]

        def _sflow_summary(vals):
            signs = [v >= 0 for v in vals]
            d = lambda pos: "순매수" if pos else "순매도"
            if all(signs):
                trend = ", 규모 감소 중" if vals[-1] < vals[-2] else (", 규모 확대 중" if vals[-1] > vals[-2] else "")
                return f"{len(vals)}일 연속 순매수{trend}"
            elif not any(signs):
                trend = ", 오늘 규모 축소" if abs(vals[-1]) < abs(vals[-2]) else (", 규모 확대 중" if abs(vals[-1]) > abs(vals[-2]) else "")
                return f"{len(vals)}일 연속 순매도{trend}"
            elif signs[-1] != signs[-2]:
                return f"어제 {d(signs[-2])}, 오늘 {d(signs[-1])} 전환"
            else:
                return f"혼조세"

        # 투자자별 최대 절대값으로 각자 스케일 정규화 (표시는 최신순)
        flow_rows = []
        for key, cls, label in investor_defs:
            vals_asc = [supply_hist[d].get(key, 0) for d in sorted_dates_asc]
            max_abs = max(abs(v) for v in vals_asc) or 1
            days = []
            for d, val in zip(sorted_dates, [supply_hist[d].get(key, 0) for d in sorted_dates]):
                mm_dd = d[5:]
                sign = "+" if val >= 0 else "−"
                days.append({
                    "date": mm_dd,
                    "width": max(4, round(abs(val) / max_abs * 88)),
                    "dn": val < 0,
                    "amt": f"{sign}{abs(val):,}억",
                })
            flow_rows.append({"investor": label, "cls": cls, "days": days,
                               "summary": _sflow_summary(vals_asc)})
        ctx["supply_flow_rows"] = flow_rows

    # close_dpick — 당일 데이터가 있을 때만 (없으면 섹션 자체 미표시)
    dpick_raw = market.get("dpick", [])
    if dpick_raw:
        dpick_rows = []
        for p in dpick_raw:
            chg = p.get("change_pct", 0)
            row = {
                "name": p.get("name", ""),
                "code": p.get("code", ""),
                "mult": p.get("trade_mult", 0),
                "vol":  f"{p.get('trade_value_eok', 0):,}억",
                "chg":  f"{'▲' if chg >= 0 else '▼'} {abs(chg):.2f}%",
                "chg_cls": "up" if chg > 0 else "down" if chg < 0 else "",
            }
            # 옛 데이터(수급 조건이 있던 시절)에 외국인·기관 금액이 있으면 그대로 보인다. 지금 수집분엔 없다(2026-10-28).
            frgn, inst = p.get("frgn_eok"), p.get("inst_eok")
            if isinstance(frgn, (int, float)) and isinstance(inst, (int, float)):
                total = frgn + inst or 1
                row["segs"] = [
                    {"cls": "frgn", "width": max(4, round(frgn / total * 80)), "label": f"외국인 {frgn:,}억"},
                    {"cls": "inst", "width": max(4, round(inst / total * 80)), "label": f"기관 {inst:,}억"},
                ]
            dpick_rows.append(row)
        ctx["dpick_rows"] = dpick_rows

    # close_research — 오늘 증권가 시황 (data/research_reports.json). Gemini 요약이지만
    # 생성 시 숫자(지수·등락률) 잔존을 이미 걸러낸 원문 요약만 담고 있다.
    research_path = BASE_DIR / "data" / "research_reports.json"
    if research_path.exists():
        try:
            research_raw = json.loads(research_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            research_raw = {}
        if research_raw.get("date") == target_date:
            research_rows = [
                {"firm": r.get("firm", ""), "title": r.get("title", ""),
                 "summary": r.get("summary", ""), "url": r.get("url", "")}
                for r in research_raw.get("reports", [])
                if r.get("summary")
            ]
            if research_rows:
                ctx["research_rows"] = research_rows

    return ctx


def build_analyst_quotes(data: dict) -> dict:
    """월가 애널리스트 발언 섹션 컨텍스트 빌더.

    url(grounding에서 리졸브된 원본 기사 링크)이 없는 항목은 표시하지 않는다.
    구글 검색 폴백 링크는 실제 발언 근거를 확인할 수 없다는 뜻이라, 검증 안 된
    멘트를 노출하는 셈이 된다 — 차라리 그 항목만 조용히 제외한다(섹션 자체는
    나머지 검증된 발언이 있으면 유지).
    """
    quotes_path = BASE_DIR / "data" / "analyst_quotes.json"
    if quotes_path.exists():
        with open(quotes_path, encoding="utf-8") as f:
            raw_quotes = json.load(f)
    else:
        raw_quotes = []
    analyst_quotes = []
    for q in raw_quotes:
        if not q.get("url"):
            continue
        q["search_url"] = q["url"]
        analyst_quotes.append(q)
    return {"analyst_quotes": analyst_quotes}


def build_ib_korea_views(target_date: str = None) -> dict:
    """외국계 IB 코멘트 섹션 컨텍스트 빌더 (코스피 전용).

    url이 없는 항목은 표시하지 않는다(원본 링크 이동 보장). 데이터 없으면 빈 리스트 →
    템플릿에서 섹션 자체 생략. 날짜가 브리핑 날짜와 다르면 쓰지 않는다 — 국내 이슈와 같은 검사(§14,
    2026-10-26 추가: 이전 실행의 잔존 파일이 다른 날짜 브리핑에 실릴 수 있었다).
    """
    views_path = BASE_DIR / "data" / "ib_korea_views.json"
    if not views_path.exists():
        return {"ib_korea_views": []}
    with open(views_path, encoding="utf-8") as f:
        payload = json.load(f)
    if target_date and payload.get("date") != target_date:
        print(f"[generate_html] ib_korea_views 날짜 불일치({payload.get('date')} != {target_date}) → 카드 생략")
        return {"ib_korea_views": []}
    views = [v for v in payload.get("views", []) if v.get("url")]
    return {"ib_korea_views": views}


def build_domestic_issues(target_date: str = None) -> dict:
    """국내 이슈 섹션 컨텍스트 빌더 (코스피 아침 전용).

    url 없는 항목은 제외한다(원본 링크 이동 보장). 데이터가 없거나 날짜가 다르면
    빈 리스트 → 템플릿에서 섹션 자체 생략(운영 규칙 0 — 없으면 지어내지 않는다).
    날짜 검증은 이전 실행의 잔존 파일이 다른 날짜 브리핑을 오염시키는 것을 막는다(§14와 동일 패턴).

    `time_abs`는 절대 시각('10/22 21:44')이다 — 발행 뒤 굳는 정적 페이지라 '3시간 전' 같은
    상대 라벨은 읽는 시각에 따라 틀린다(§20·§24에서 세 번 재발한 패턴).
    """
    path = BASE_DIR / "data" / "domestic_issues.json"
    if not path.exists():
        return {"domestic_issues": [], "domestic_window_label": ""}
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"[generate_html] domestic_issues 읽기 실패: {e}")
        return {"domestic_issues": [], "domestic_window_label": ""}

    if target_date and payload.get("date") != target_date:
        print(f"[generate_html] domestic_issues 날짜 불일치"
              f"({payload.get('date')} != {target_date}) → 섹션 생략")
        return {"domestic_issues": [], "domestic_window_label": ""}

    items = []
    for it in payload.get("issues", []):
        if not it.get("url"):
            continue
        items.append({**it, "time_abs": _abs_time_label(it.get("published_at"))})
    return {
        "domestic_issues": items,
        "domestic_window_label": (payload.get("window") or {}).get("label", ""),
        "domestic_card_title": _domestic_card_title((payload.get("window") or {}).get("from", "")),
    }


def build_accuracy(internal_type: str) -> dict:
    bpath = DATA_DIR / "briefings.json"
    if not bpath.exists():
        return {}
    # 코스피는 시초가 기준 기록만 센다(§57). 표본 5건 미만이면 상자를 그리지 않는다 —
    # 전환 직후 "1건 중 1건 100%"처럼 뜻 없는 숫자를 내보내지 않는다.
    data = stats_rows(load_json(bpath).get("briefings", []))
    src = SRC_TYPE.get(internal_type, internal_type)
    typed = [b for b in data if b.get("type") in (internal_type, src) and b.get("is_correct") is not None]
    if not typed or (internal_type == "kospi" and len(typed) < 5):
        return {}
    r30, r7 = typed[-30:], typed[-7:]

    def pct(lst):
        return round(sum(1 for b in lst if b["is_correct"]) / len(lst) * 100) if lst else 0

    hit = sum(1 for b in r30 if b["is_correct"])
    miss = len(r30) - hit
    pending = sum(1 for b in data if b.get("type") in (internal_type, src) and b.get("is_correct") is None)
    total = max(hit + miss + pending, 1)
    return {
        "acc_7d_pct": pct(r7), "acc_30d_pct": pct(r30),
        "hit": hit, "miss": miss, "pending": pending,
        "hit_pct": round(hit / total * 100), "miss_pct": round(miss / total * 100),
        "pending_pct": round(pending / total * 100),
    }


def _baseline_pct(rows: list) -> int:
    """구간 내 실제 상승일 비율(%). '매일 상승이라고만 답하는 예측기'의 적중률이다.

    우리 적중률과 반드시 같은 표본이어야 비교가 성립하므로, 미채점 항목은
    여기서도 직접 걸러낸다(호출자 필터링에 의존하지 않는다).
    상승 판정은 채점 로직(check_accuracy)이 기록한 actual_direction을 그대로 쓴다."""
    scored = [b for b in rows if b.get("is_correct") is not None]
    if not scored:
        return 0
    up = sum(1 for b in scored if b.get("actual_direction") == "상승")
    return round(up / len(scored) * 100)


def _edge_cls(edge: int) -> str:
    """우위 폭(%p) → 게이지 채움 색. ±10%p를 경계로 둔다.

    최근 15건 기준 1건이 6.7%p라 한 자릿수 차이는 표본 노이즈다. 경계를 0에 두면
    +3%p 같은 사실상 무차이를 초록으로 칠해 없는 우위를 주장하게 된다."""
    if edge >= 10:
        return "good"
    if edge <= -10:
        return "bad"
    return "flat"


def _legacy_close_summary(all_rows: list, internal_type: str) -> dict:
    """전환 이전 종가 기준 코스피 기록의 건수·적중률. 코스피가 아니거나 기록이 없으면 빈 dict."""
    if internal_type != "kospi":
        return {}
    legacy = [b for b in legacy_kospi_rows(all_rows) if b.get("is_correct") is not None]
    if not legacy:
        return {}
    hit = sum(1 for b in legacy if b["is_correct"])
    return {"sc_legacy_count": len(legacy), "sc_legacy_pct": round(hit / len(legacy) * 100),
            "sc_legacy_until": max(b["date"] for b in legacy)}


def build_scorecard(internal_type: str) -> dict:
    """예측 성적표(카드+더보기 모달) 컨텍스트. briefings.json의 실측 채점값(is_correct)만 사용.
    월별 적중률·최근 결과는 모두 실데이터 집계 — 사후 '복기 사유' 서술은 저장돼 있지 않으므로
    생성하지 않고 사실(예측→실제)만 표시한다(데이터 정합성 철칙)."""
    bpath = DATA_DIR / "briefings.json"
    if not bpath.exists():
        return {}
    all_rows = load_json(bpath).get("briefings", [])
    rows = stats_rows(all_rows)               # 코스피는 시초가 기준 기록만(§57)
    src = SRC_TYPE.get(internal_type, internal_type)
    typed = [b for b in rows if b.get("type") in (internal_type, src)]
    scored = [b for b in typed if b.get("is_correct") is not None]
    if len(scored) < 5:                       # 표본이 너무 적으면 카드 생략
        return {}

    def pct(lst):
        return round(sum(1 for b in lst if b["is_correct"]) / len(lst) * 100) if lst else 0

    def cls(p):                               # accuracy.html의 acc_cls와 동일 규칙
        return "good" if p >= 70 else ("mid" if p >= 50 else "bad")

    r15 = scored[-15:]
    r15_pct = pct(r15)
    cum_pct = pct(scored)
    r15_base = _baseline_pct(r15)
    cum_base = _baseline_pct(scored)
    # 우위는 원본 실수 차이가 아니라 화면에 뜬 반올림값끼리의 차이로 구한다 —
    # 사용자가 73 − 53을 암산했을 때 표시된 +20%p와 어긋나면 안 된다.
    r15_edge = r15_pct - r15_base
    cum_edge = cum_pct - cum_base
    hits = [b for b in scored if b["is_correct"]]
    hit_avg = (sum(abs(outcome_pct(b) or 0) for b in hits) / len(hits)) if hits else 0

    # 최근 30건 기준 적중/오류/미결 막대
    r30 = scored[-30:]
    hit30 = sum(1 for b in r30 if b["is_correct"])
    miss30 = len(r30) - hit30
    pending = sum(1 for b in typed if b.get("is_correct") is None)
    total = max(hit30 + miss30 + pending, 1)

    # 월별 적중률 (최근 5개월) — 같은 달 기준선을 함께 실어 진 달이 드러나게 한다
    from collections import defaultdict
    mon = defaultdict(list)
    for b in scored:
        mon[b["date"][:7]].append(b)
    monthly = []
    for mkey in sorted(mon)[-5:]:
        rows_m = mon[mkey]
        p = pct(rows_m)
        monthly.append({
            "label": f"{int(mkey[5:7])}월",
            "pct": p,
            "cls": cls(p),
            "base_pct": _baseline_pct(rows_m),
        })

    # 최근 결과 (맞은 날·틀린 날 그대로, 사실만)
    dows = ["월", "화", "수", "목", "금", "토", "일"]
    recent = []
    for b in reversed(scored[-6:]):
        try:
            dt = datetime.strptime(b["date"], "%Y-%m-%d")
            dlabel = f"{dt.month}/{dt.day} ({dows[dt.weekday()]})"
        except Exception:
            dlabel = b.get("date", "")
        d = b.get("predicted_direction", "")
        pred_word = "상승 예측" if "상승" in d else ("하락 예측" if "하락" in d else "중립 예측")
        chg = outcome_pct(b)
        chg_str = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "—"
        recent.append({
            "date_label": dlabel,
            "pred_word": pred_word,
            "actual": chg_str,
            "ok": bool(b["is_correct"]),
        })

    return {
        # 채점이 15건이 되기 전엔 '최근 15건'이 누적과 같은 표본이라 숨긴다(2026-10-26 — 9건인데 '최근 15건'으로 표시됐다)
        "sc_show_recent15": len(scored) >= 15,
        "sc_recent15_pct": r15_pct,
        "sc_recent15_cls": cls(r15_pct),
        "sc_cum_pct": cum_pct,
        "sc_cum_cls": cls(cum_pct),
        "sc_cum_count": len(scored),
        # 전환 이전 종가 기준 기록 — 통계엔 안 넣고 모달에 사실만 적는다(§57)
        **_legacy_close_summary(all_rows, internal_type),
        # 기준선 = 매일 '상승'이라고만 답했을 때의 적중률
        "sc_recent15_base": r15_base,
        "sc_recent15_edge": r15_edge,
        "sc_recent15_gcls": _edge_cls(r15_edge),
        "sc_cum_base": cum_base,
        "sc_cum_edge": cum_edge,
        "sc_cum_gcls": _edge_cls(cum_edge),
        "sc_hit_avg": f"{hit_avg:.1f}%",
        "sc_hit": hit30, "sc_miss": miss30, "sc_pending": pending,
        "sc_hit_pct": round(hit30 / total * 100),
        "sc_miss_pct": round(miss30 / total * 100),
        "sc_pending_pct": round(pending / total * 100),
        "sc_monthly": monthly,
        "sc_recent": recent,
    }


# ── 인접 브리핑 + 목록 ─────────────────────────────────────────────────────────
def existing_dates(internal_type: str) -> list:
    if not BRIEFINGS_DIR.exists():
        return []
    return sorted(d.name for d in BRIEFINGS_DIR.iterdir()
                  if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}$", d.name)
                  and (d / internal_type / "index.html").exists())


def find_adjacent(internal_type: str, target: str) -> tuple:
    dirs = existing_dates(internal_type)
    if target not in dirs:
        # 아직 안 써졌으면 가상으로 끼워 계산
        dirs = sorted(set(dirs) | {target})
    idx = dirs.index(target)
    prev_url = f"/briefings/{dirs[idx-1]}/{internal_type}/" if idx > 0 else None
    next_url = f"/briefings/{dirs[idx+1]}/{internal_type}/" if idx < len(dirs) - 1 else None
    return prev_url, next_url


def build_list_context(target_date: str, active_type: str) -> dict:
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []
    today = datetime.now(KST).strftime("%Y-%m-%d")

    def norm_type(t):
        return TYPE_MAP.get(t, t)

    def cell_for(d: str, btype: str, today_card: bool) -> dict:
        new_path = BRIEFINGS_DIR / d / btype / "index.html"
        ready = new_path.exists()
        match = next((b for b in briefings if b.get("date") == d and norm_type(b.get("type")) == btype), None)
        base = {"type": btype, "label": BRIEFING_LABELS[btype]}
        if d == target_date and btype == active_type:
            base["state"] = "current"
        elif ready:
            base["state"] = "ready"
            base["url"] = f"/briefings/{d}/{btype}/"
        elif today_card:
            base["state"] = "pending"
            base["scheduled_time"] = SCHEDULED_TIMES[btype]
            return base
        else:
            base["state"] = "empty"
            return base
        # ready/current 공통 표시
        if match:
            direction = match.get("predicted_direction") or match.get("direction", "")
            if btype == "close":
                chg = match.get("actual_change_pct")
                base["pill_cls"] = "neutral"
                base["pill_text"] = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else ""
                base["title"] = f"KOSPI {chg:+.2f}%" if isinstance(chg, (int, float)) else "마감"
            else:
                up = "상승" in direction
                base["pill_cls"] = "up" if up else "dn"
                base["pill_text"] = ("▲" if up else "▼") if direction else ""
                base["title"] = direction or "—"
            base["time"] = fmt_time(match.get("generated_at", ""))
        else:
            base["title"] = "—"
            base["time"] = ""
        return base

    types = ["kospi", "close", "us"]
    today_card = {
        "date": today, "day_label": day_label(today, full=True),
        "slots": [cell_for(today, t, True) for t in types],
    }
    past_dates = sorted({b["date"] for b in briefings if b.get("date") and b["date"] != today}, reverse=True)[:20]
    past_rows, prev_month = [], None
    for d in past_dates:
        if not any((BRIEFINGS_DIR / d / t / "index.html").exists() for t in types):
            continue
        if len(past_rows) >= 10:
            break
        try:
            dt = date.fromisoformat(d)
        except ValueError:
            continue
        month = f"{dt.year}년 {dt.month}월"
        past_rows.append({
            "date": d, "date_short": d[5:], "day_label": day_label(d),
            "month_label": month, "show_month": month != prev_month,
            "cells": [cell_for(d, t, False) for t in types],
        })
        prev_month = month
    return {"today_card": today_card, "past_rows": past_rows}


# ── 렌더 ──────────────────────────────────────────────────────────────────────
# 브리핑 <title>·description(2026-10-27). 검색에 나오는 줄이라 사람들이 찾는 말(검색어)을 앞에,
# 그날 헤드라인을 뒤에 둔다. 새 발행(render_briefing)과 발행본 일괄 교체(backfill_briefing_heads)가
# 같은 함수를 쓴다 — 두 곳이 어긋나지 않게.
SEO_TITLE_PREFIX = {"close": "코스피 마감 시황", "us": "미국 증시 전망"}


def _plain_text(s) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip() if isinstance(s, str) else ""


def briefing_head(analysis: dict, btype: str, target_date: str) -> dict:
    """{"title", "description"} — HTML에 그대로 넣을 수 있게 이스케이프한 값."""
    analysis = analysis or {}
    dt = date.fromisoformat(target_date)
    day = f"{dt.month}월 {dt.day}일"
    if btype == "kospi":
        # 시초가 기준(§57)이 아닌 옛 예측은 '시초가'라고 쓰지 않는다
        is_open = (analysis.get("prediction") or {}).get("basis") == BASIS_OPEN
        prefix = "코스피 시초가 예측" if is_open else "코스피 방향 예측"
    else:
        prefix = SEO_TITLE_PREFIX[btype]
    tv = analysis.get("todays_view") or {}
    headline = next((t for t in map(_plain_text, (tv.get("view_title"), analysis.get("reason_title"),
                                                  analysis.get("market_title"))) if t), "")
    dek = next((t for t in map(_plain_text, (tv.get("dek"), analysis.get("dek"),
                                             analysis.get("sc_summary"))) if t), "")
    title = f"{prefix} {day} | {headline}" if headline else f"{prefix} {day} — Double-Shot"
    parts = []
    if btype == "kospi" and analysis.get("prediction"):
        p = build_prediction(analysis, "KOSPI", "KOSPI 당일 방향 예측", "")
        parts.append(f"{p['pred_title']}: {p['direction']} {p['readout_pct']}% · 신뢰도 {p['confidence']}%")
    parts.append(dek or headline or f"{target_date} {BRIEFING_LABELS[btype]} 브리핑")
    return {"title": html.escape(title), "description": html.escape(". ".join(parts))}


def render_briefing(internal_type: str, target_date: str, market_data: dict, force: bool = False) -> str:
    env = make_env()
    config = load_json(CONFIG_DIR / f"{internal_type}.json")
    src_type = SRC_TYPE[internal_type]
    # ── analysis 로드 우선순위 ──────────────────────────────────────────────────
    # 1순위: git에 커밋된 날짜별 snapshot (재생성 시 오염 방지)
    # 2순위: 임시 live 파일 — 반드시 날짜 검증 후 사용
    # --force 시 snapshot을 무시하고 항상 최신 analysis_{type}.json을 사용 (의도적 정정 재생성용)
    snapshot_path = BRIEFINGS_DIR / target_date / internal_type / "analysis_snapshot.json"
    analysis_path = DATA_DIR / f"analysis_{src_type}.json"

    if snapshot_path.exists() and not force:
        print(f"[generate_html] ⚠️ 기존 snapshot 사용 → {snapshot_path.relative_to(BASE_DIR)} "
              f"(새로 생성된 analysis_{src_type}.json은 무시됨. 의도적 정정이면 --force 사용)")
        analysis = load_json(snapshot_path)
    elif analysis_path.exists():
        analysis = load_json(analysis_path)
        analysis_date = (analysis.get("generated_at") or "")[:10]
        if analysis_date and analysis_date != target_date:
            raise RuntimeError(
                f"[generate_html] ⛔ 분석 날짜 불일치 — "
                f"analysis_{src_type}.json 생성일({analysis_date}) ≠ 대상 날짜({target_date}).\n"
                f"다른 워크플로우 실행으로 덮어써진 파일입니다. 오염된 예측 발행을 차단합니다.\n"
                f"해결: web/briefings/{target_date}/{internal_type}/analysis_snapshot.json 이 있으면 자동 사용됩니다."
            )
    else:
        analysis = {}

    generated_at = market_data.get("generated_at") or analysis.get("generated_at") or datetime.now(KST).isoformat()
    gen_time = fmt_time(generated_at)
    index_name = config["index_name"]
    prev_url, next_url = find_adjacent(internal_type, target_date)

    canonical_url = f"https://doubleshot.space/briefings/{target_date}/{internal_type}/"
    _issue_slot_map = {"kospi": "MARKET", "us": "US_MARKET"}
    ctx = {
        "date_str": target_date,
        "generated_at": generated_at,
        "generated_time": gen_time,
        "gnb_date": f"{target_date} KST {gen_time}",
        "index_name": index_name,
        "prev_url": prev_url, "next_url": next_url,
        "css_path": CSS_PATH, "js_path": JS_PATH,
        "canonical_url": canonical_url,
        "briefing_type": internal_type,
        "issue_slot": _issue_slot_map.get(internal_type, "MARKET"),
        **build_list_context(target_date, internal_type),
        **build_accuracy(internal_type),
        # 공유 카드(2026-10-27) — write_output이 같은 폴더에 og.png를 만든다. 못 만들면 태그를 지운다.
        # 텔레그램 메시지는 링크 미리보기를 끈다(send_telegram) — 이 카드는 카카오톡·X 공유용이다.
        "og_image": f"{canonical_url}og.png",
    }
    ctx["accuracy"] = bool(ctx.get("acc_30d_pct") is not None and (ctx.get("hit", 0) + ctx.get("miss", 0)) > 0)

    # 코스피 성적표 카드 — 사이드바 accuracy.html 대체(kospi 전용). 데이터 부족 시 빈 dict → 카드 생략.
    if internal_type == "kospi":
        ctx.update(build_scorecard(internal_type))
        ctx["scorecard"] = bool(ctx.get("sc_monthly"))

    if internal_type == "close":
        ctx.update(build_close_sections(analysis, market_data, index_name, target_date))
    elif internal_type == "us":
        # 미국 이슈 중심 브리핑 — 예측 대신 오늘의 관점 + 이슈 카드. 성적표 사이드바 없음.
        ctx.update(build_issues(analysis))
        ctx.update(build_us_tone(market_data))
        ctx.update(build_analyst_quotes(market_data))
        # AI 종목 픽(진입·목표·손절)은 2026-10-26 제거 — 코스피와 같은 월봉 5개월선 안착 코너(결정론, §67)
        ctx.update(build_monthly_ma5(analysis, target_date, "us"))
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["fng_dial"] = build_fng_dial(market_data, internal_type)
        ctx["todays_view"] = analysis.get("todays_view")
        ctx.update(build_nasdaq_check(analysis, target_date))   # 나스닥 체크(§65) — 이슈 아래
        ctx.update(build_premarket_strip(analysis, market_data, target_date, gen_time))   # 프리마켓 실측 띠 — 맨 위
        ctx["accuracy"] = False  # US 채점 탈퇴 — 성적표 사이드바 미표시
    else:
        ctx.update(build_prediction(analysis, index_name, config["pred_title"], gen_time))
        ctx["quote_today"] = _load_quote_today(target_date)
        ctx.update(build_reasons(analysis, target_date))
        ctx.update(build_analyst_quotes(market_data))
        # 상승 모멘텀 종목(LLM 픽)은 2026-10-25 제거 — 그 자리에 월봉 5개월선 안착 종목(결정론)을 둔다
        ctx.update(build_monthly_ma5(analysis, target_date))
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["fng_dial"] = build_fng_dial(market_data, internal_type)
        ctx["watch_items"] = analysis.get("watch_items") or analysis.get("watchpoints") or []
        ctx["todays_view"] = analysis.get("todays_view")
        ctx["format_in_view"] = True  # 코스피는 근거 형식을 '오늘의 관점' 안에서 렌더
        ctx.update(build_ib_korea_views(target_date))
        ctx.update(build_domestic_issues(target_date))
        # 3단 구조(2026-10-26) — 30초 요약 카드 + 오늘의 이슈 점검
        ctx.update(build_hero(analysis, target_date))
        ctx.update(build_prev_prediction(analysis, target_date))
        ctx.update(build_issue_check(ctx.get("us_issue_cards")))
        ctx.update(build_prior_signals(analysis, market_data, target_date))   # 예측 근거 신호 한 줄
        ctx.update(build_prev_supply(analysis, market_data, target_date))     # 전일 수급 카드
        uls = analysis.get("us_linked_story") or {}
        if uls.get("title"):
            ctx["us_linked_title"] = uls["title"]
            ctx["us_linked_paragraphs"] = uls.get("paragraphs", [])
            ctx["us_linked_stocks"] = uls.get("related_stocks", [])
        else:
            # us_linked_story가 없으면(또는 폴백) 섹터 리뷰를 렌더한다 — 날짜 시드 랜덤으로 택1됨
            sf = analysis.get("sector_focus") or {}
            if sf.get("signal") and sf.get("paragraphs"):
                ctx["sector_emoji"] = sf.get("emoji", "🏭")
                ctx["sector_name"] = sf.get("sector_name", "반도체")
                ctx["sector_signal"] = sf["signal"]
                ctx["sector_paragraphs"] = sf.get("paragraphs", [])

    head = briefing_head(analysis, internal_type, target_date)
    ctx["page_title"] = head["title"]
    ctx["og_description"] = head["description"]

    template = env.get_template(config["template"])
    return template.render(**ctx), analysis


def strip_og_image(html: str) -> str:
    """공유 카드를 못 만든 페이지에서 og:image·twitter:image를 지운다 — 없는 이미지를 가리키지 않게."""
    html = re.sub(r'<meta (?:property="og:image"|name="twitter:image") content="[^"]*">\n?', "", html)
    return html.replace('<meta name="twitter:card" content="summary_large_image">',
                        '<meta name="twitter:card" content="summary">')


def write_output(html: str, internal_type: str, target_date: str, analysis=None):
    out_dir = BRIEFINGS_DIR / target_date / internal_type
    out_dir.mkdir(parents=True, exist_ok=True)
    card = make_card(analysis, internal_type, target_date)
    if card:
        (out_dir / "og.png").write_bytes(card)
    else:
        html = strip_og_image(html)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate_html] wrote {out_dir.relative_to(BASE_DIR)}/index.html")
    # analysis snapshot 저장 — git에 커밋되어 재생성 시 날짜 오염을 방지함
    if analysis:
        import json as _json
        snap_path = out_dir / "analysis_snapshot.json"
        snap_path.write_text(_json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[generate_html] snapshot → {snap_path.relative_to(BASE_DIR)}")


def find_latest_ready():
    """파일 수정 시간 기준 가장 최근 생성된 ready 브리핑 (internal_type, date) 반환. 없으면 None."""
    best = None  # (mtime, internal_type, date)
    for d_dir in BRIEFINGS_DIR.iterdir():
        d = d_dir.name
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', d):
            continue
        for it in DATA_FILE:
            html = d_dir / it / "index.html"
            if not html.exists():
                continue
            mtime = html.stat().st_mtime
            if best is None or mtime > best[0]:
                best = (mtime, it, d)
    return (best[1], best[2]) if best else None


def update_vercel_briefings_route(internal_type: str, target_date: str):
    """vercel.json의 /briefings/ 라우팅을 최신 브리핑으로 업데이트."""
    import re
    vercel_path = BASE_DIR / "vercel.json"
    content = vercel_path.read_text(encoding="utf-8")
    dest = f"/briefings/{target_date}/{internal_type}/index.html"
    pattern = r'("src": "\^/briefings/\?\$",\s*"dest": ")[^"]*(")'
    if not re.search(pattern, content):
        print(f"[generate_html] vercel.json /briefings/ 패턴 미일치, 건너뜀")
        return
    updated = re.sub(pattern, lambda m: m.group(1) + dest + m.group(2), content)
    if updated == content:
        print(f"[generate_html] vercel.json /briefings/ 이미 최신 ({dest})")
        return
    vercel_path.write_text(updated, encoding="utf-8")
    print(f"[generate_html] vercel.json /briefings/ → {dest}")


def _parse_close_price(html_path):
    """close 브리핑 HTML에서 KOSPI 종가 추출 (신규/레거시 포맷 모두 지원)."""
    try:
        html = html_path.read_text(encoding="utf-8")
        m = re.search(r'class="a-hero__idx-val">([0-9,]+(?:\.\d+)?)<', html)
        if not m:
            m = re.search(r'close-idx__name">KOSPI.*?close-idx__val">([0-9,]+(?:\.\d+)?)<', html, re.DOTALL)
        return m.group(1) if m else None
    except Exception:
        return None


def _bridge_target_is_today(target_date: str) -> bool:
    """밤사이 브리지 라이브 JSON을 지금 덮어써도 되는 날짜인지 판정한다.

    §2가 정한 과거 날짜 재생성(--date 2026-06-08 등)은 상시 절차인데, 그때 이 파일까지
    덮으면 6월 행이 라이브 파일에 실린다. 클라이언트 date 게이트가 걸러내므로 틀린 값이
    뜨지는 않지만, 다음 07:25까지 /stocks/에서 브리지가 조용히 사라지고 코스피 잡의
    git add web/ 이 그 퇴행을 커밋한다. 라이브 데이터 파일이 아카이브 재렌더의 부수
    효과가 되면 안 된다.
    """
    return target_date == datetime.now(KST).strftime("%Y-%m-%d")


def write_overnight_bridge_json(market_data: dict, target_date: str):
    """web/data/overnight-bridge.json 을 생성한다.

    밤사이 브리지는 브리핑 페이지가 아니라 종목 시그널 홈 `/stocks/`에서 07:30~09:00에만
    렌더한다(2026-08-03 배치 변경). `/stocks/index.html`은 손으로 쓴 정적 HTML이고 클라이언트
    JS가 web/data/*.json을 fetch하는 구조라, 표시용 행을 정적 JSON으로 발행한다.

    스키마:
      {
        "date": "YYYY-MM-DD",             # 이 데이터를 만든 코스피 브리핑의 발행일(KST)
        "generated_at": "ISO8601 +09:00",  # 생성 시각
        "kr_session_date": "YYYY-MM-DD",   # 비교 대상 한국 마감 세션의 실제 거래일
        "rows": [...]                      # build_overnight_bridge()가 구운 표시용 행
      }

    date는 클라이언트가 "이 파일이 오늘 것인가"를 판정하는 유일한 근거다. 어제 파일이
    그대로 남아 있어도 date가 오늘과 다르면 렌더하지 않는다 — 어제 갭을 오늘 갭으로
    보여주는 것이 이 기능이 드러내려던 §24 이중계상 사고 그 자체라, 완전성보다 정합성을
    택한다(§0). kr_session_date는 별도 필드로 둔다 — 발행일과 비교 대상 거래일은 다른
    날짜이고(월요일이면 3일 차이), 화면 머리말에는 상대어가 아니라 이 실제 날짜를
    적어야 한다(§24).

    표시 문자열은 파이썬에서 이미 다 구워 내보낸다. 클라이언트는 렌더만 하고
    `>= 0` / `> 0` 경계 판정을 JS로 다시 구현하지 않는다 — 그게 §30이 지적한 이중 구현이다.

    행이 없어도 파일은 항상 쓴다. 쓰지 않고 넘어가면 어제 파일이 어제 내용 그대로
    남아, 클라이언트 날짜 게이트가 유일한 방어선이 된다. 오늘 날짜 + 빈 rows로 덮어쓰면
    "오늘은 보여줄 것이 없다"가 파일 자체로 분명해진다(빈 상태 모호성 제거).
    """
    built = build_overnight_bridge(market_data)
    rows = built["overnight_bridge"]
    payload = {
        "date": target_date,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "kr_session_date": built["overnight_bridge_date"],
        "rows": rows,
    }

    # allow_nan=False — build_overnight_bridge가 이미 비유한 값을 걸러내지만, 그걸 뚫고
    # NaN·Infinity가 남아 있으면 기본 설정의 json.dumps는 예외 없이 맨몸 NaN 리터럴을 써서
    # 표준 JSON이 아닌 파일을 만든다(클라이언트 JSON.parse가 통째로 실패 → 블록 전체 사망).
    # 여기서 ValueError로 터뜨리면 호출부의 가드가 잡아 파일을 아예 건드리지 않는다 —
    # 직전 파일이 낡았을지언정 유효하고 date로 걸러지므로, 깨진 파일을 내보내는 것보다 낫다(§0).
    body = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)

    out_path = WEB_DIR / "data" / "overnight-bridge.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 브라우저가 이 파일을 직접 fetch하므로 절반만 써진 상태를 절대 노출하지 않는다
    # (fetch_stock_news.py의 선례와 동일한 이유).
    tmp_path = out_path.with_suffix(".json.tmp")
    tmp_path.write_text(body, encoding="utf-8")
    try:
        os.replace(tmp_path, out_path)
    except Exception:
        # 교체가 실패하면 tmp를 치우고 예외를 그대로 올린다. 남겨두면 코스피 잡의
        # git add web/ 이 찌꺼기 파일을 그대로 커밋한다.
        tmp_path.unlink(missing_ok=True)
        raise
    print(f"[generate_html] wrote web/data/overnight-bridge.json ({len(rows)}개 섹터)")


def write_briefings_list_json():
    """web/data/briefings-list.json 을 생성한다.

    브리핑 목록 today 카드를 JS가 동적으로 패치하는 데 사용한다.
    각 날짜별 kospi/close/us 슬롯 상태를 담는다.
    """
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []

    types = ["kospi", "close", "us"]

    # 최근 30일 분 날짜만 대상
    all_dates = sorted({b["date"] for b in briefings if b.get("date")}, reverse=True)[:30]
    today = datetime.now(KST).strftime("%Y-%m-%d")
    if today not in all_dates:
        all_dates = [today] + all_dates

    slots = {}
    for d in all_dates:
        day_slots = {}
        for btype in types:
            new_path = BRIEFINGS_DIR / d / btype / "index.html"
            ready = new_path.exists()
            match = next((b for b in briefings if b.get("date") == d and TYPE_MAP.get(b.get("type"), b.get("type")) == btype), None)

            if ready:
                entry = {"state": "ready", "url": f"/briefings/{d}/{btype}/"}
                # 브리핑 헤드라인(reason_title/market_title) — 스트립에서 실제 타이틀 표시용
                snap_path = BRIEFINGS_DIR / d / btype / "analysis_snapshot.json"
                if snap_path.exists():
                    snap = load_json(snap_path)
                    # US 브리핑은 reason_title/market_title이 없고 todays_view.view_title(오늘의 관점)이 헤드라인.
                    headline = (snap.get("reason_title") or snap.get("market_title")
                                or (snap.get("todays_view") or {}).get("view_title"))
                    if headline:
                        entry["headline"] = re.sub(r"<[^>]+>", "", str(headline)).strip()
                if btype == "close":
                    price = _parse_close_price(new_path)
                    entry["title"] = price or "마감"
                    entry["price"] = price or ""
                    entry["time"] = fmt_time(match.get("generated_at", "")) if match else ""
                elif match:
                    direction = match.get("predicted_direction") or match.get("direction", "")
                    up = "상승" in direction
                    entry["pill_cls"] = "up" if up else "dn"
                    entry["pill_text"] = ("▲" if up else "▼") if direction else ""
                    entry["title"] = direction or "—"
                    entry["time"] = fmt_time(match.get("generated_at", ""))
                else:
                    entry["title"] = "—"
                    entry["time"] = ""
            else:
                entry = {"state": "pending", "scheduled_time": SCHEDULED_TIMES.get(btype, "")}
            day_slots[btype] = entry
        slots[d] = day_slots

    out_path = WEB_DIR / "data" / "briefings-list.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"slots": slots}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[generate_html] wrote web/data/briefings-list.json")


# ─────────────────────────────────────────────────────────────────────────────
# 브리핑 아카이브 (/briefings/)
# ─────────────────────────────────────────────────────────────────────────────
# 2026-09-02 신설. 그 전까지 /briefings/ 는 briefings-list.json을 fetch해서
# 최신 브리핑으로 location.replace() 하는 1.7KB 리다이렉트 스텁이었다(본문 26자).
# 발행본이 80편 넘게 쌓였는데 **과거 브리핑을 훑어볼 경로가 사실상 없었고**,
# sitemap에는 그 스텁이 등재돼 크롤러에게 빈 페이지를 광고하고 있었다.
#
# ⚠️ 목록의 원본은 data/*.json이 아니라 **디스크에 커밋된 발행본**이다.
#    로컬 analysis 파일이 stale일 때 아카이브가 오염되는 것을 구조적으로 막는다(§23·§28).
# ⚠️ main.js patchBriefingList()는 `.bottom-list`를 찾아 최근 10일로 다시 그린다.
#    아카이브는 `.arch-list`를 쓰므로 그 대상이 아니다 — 클래스를 바꾸지 말 것.
# 하루 안에서도 **최신 발행이 위**로 온다 — 날짜가 최신순이므로 그래야 일관된다.
# 발행 시각: 코스피 예측 07:25 → 마감 16:25 → 미국 21:15 이므로 역순으로 나열한다.
# 이 순서가 곧 featured(맨 위 1편) 선정 순서이기도 하다 — 목록의 첫 항목이 featured다.
# ⚠️ build_list_context의 types(사이드바 3열 목록)와는 별개다. 그쪽은 가로 배치라 발행
#    순서대로 두는 게 자연스러우므로 함께 뒤집지 말 것.
ARCHIVE_TYPES = ["us", "close", "kospi"]


def _archive_headline(date_str: str, btype: str) -> str:
    """발행본의 헤드라인. 스냅샷 → meta description 순으로 찾고, 없으면 빈 문자열."""
    snap = BRIEFINGS_DIR / date_str / btype / "analysis_snapshot.json"
    if snap.exists():
        try:
            d = load_json(snap)
        except Exception:
            d = {}
        tv = d.get("todays_view") or {}
        for cand in (tv.get("view_title"), d.get("reason_title"), d.get("market_title")):
            if isinstance(cand, str) and cand.strip():
                return cand.strip()
    page = BRIEFINGS_DIR / date_str / btype / "index.html"
    if page.exists():
        m = re.search(r'<meta name="description" content="([^"]*)"', page.read_text(errors="ignore"))
        if m and m.group(1).strip():
            return html.unescape(m.group(1).strip())
    return ""


def _archive_dek(date_str: str, btype: str) -> str:
    """발행본의 서브타이틀(한 문단 요약). 없으면 빈 문자열 — 지어내지 않는다(§0).

    kospi·us는 `todays_view.dek`, close는 `dek`(2026-10-25~)·`sc_summary`가 같은 역할을 한다.
    맨 위 최신 1편에만 쓰이므로(그 아래는 제목만) 여기서만 읽는다.
    """
    snap = BRIEFINGS_DIR / date_str / btype / "analysis_snapshot.json"
    if not snap.exists():
        return ""
    try:
        d = load_json(snap)
    except Exception:
        return ""
    tv = d.get("todays_view") or {}
    for cand in (tv.get("dek"), d.get("dek"), d.get("sc_summary")):
        if isinstance(cand, str) and cand.strip():
            return cand.strip()
    return ""


def build_archive_context() -> dict:
    """발행된 브리핑을 디스크에서 훑어 월별 아카이브 목록을 만든다."""
    if not BRIEFINGS_DIR.exists():
        return {"months": [], "total": 0}
    dates = sorted(
        (p.name for p in BRIEFINGS_DIR.iterdir()
         if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)),
        reverse=True,
    )
    months, total, prev_month, featured_done = [], 0, None, False
    for d in dates:
        entries = []
        for t in ARCHIVE_TYPES:
            if not (BRIEFINGS_DIR / d / t / "index.html").exists():
                continue
            entry = {
                "label": BRIEFING_LABELS[t],
                "url": f"/briefings/{d}/{t}/",
                "headline": _archive_headline(d, t),
            }
            # 목록 맨 위 최신 1편만 서브타이틀까지 보여준다(2026-09-04). 나머지는 제목만 —
            # 전부 요약을 달면 목록이 길어져 훑어보기 어려워진다.
            if not featured_done:
                entry["dek"] = _archive_dek(d, t)
                entry["featured"] = True
                featured_done = True
            entries.append(entry)
        if not entries:
            continue
        total += len(entries)
        dt = date.fromisoformat(d)
        label = f"{dt.year}년 {dt.month}월"
        if label != prev_month:
            months.append({"label": label, "days": []})
            prev_month = label
        months[-1]["days"].append({
            "date": d, "date_short": f"{dt.month}월 {dt.day}일",
            "day_label": day_label(d),
            # ⚠️ 키 이름을 items로 두면 Jinja가 dict.items 메서드를 먼저 잡아 렌더가 깨진다.
            "briefings": entries,
        })
    return {"months": months, "total": total}


def write_briefings_index():
    """web/briefings/index.html — 정적 아카이브 목록을 생성한다."""
    ctx = build_archive_context()
    if not ctx["total"]:
        print("[generate_html] 아카이브: 발행본 없음 — index.html 생략", file=sys.stderr)
        return
    env = make_env()
    out = BRIEFINGS_DIR / "index.html"
    out.write_text(
        env.get_template("pages/briefings_index.html").render(
            canonical_url=f"{SITE_BASE}/briefings/", **ctx),
        encoding="utf-8")
    # 로그용 상대경로 — BASE_DIR 밖이면 relative_to가 예외를 던진다(테스트의 tmp_path 등).
    # 로그 한 줄 때문에 아카이브 생성이 죽으면 안 되므로 실패 시 절대경로로 떨어진다.
    try:
        shown = out.relative_to(BASE_DIR)
    except ValueError:
        shown = out
    print(f"[generate_html] 아카이브 갱신: {shown} "
          f"({ctx['total']}편 / {len(ctx['months'])}개월)")
    write_stocks_recent_briefings()
    write_briefings_rss()


# 브리핑 RSS(2026-10-27) — 네이버 서치어드바이저에 제출해 새 브리핑이 빨리 수집되게 한다.
# 아카이브와 같은 자리·같은 원본(디스크에 커밋된 발행본)으로 만든다. 제목·설명은 페이지 <head>와 같은 briefing_head.
# 파일은 BRIEFINGS_DIR 안에 둔다 — 테스트가 BRIEFINGS_DIR을 임시 폴더로 바꾸면 피드도 함께 따라간다.
RSS_ITEMS = 30


def _briefing_pub_date(date_str: str, btype: str, analysis: dict) -> str:
    """RFC 822 발행 시각. 스냅샷 generated_at, 없으면 정해진 발행 시각(SCHEDULED_TIMES)."""
    from email.utils import format_datetime
    try:
        dt = datetime.fromisoformat(analysis.get("generated_at") or "")
        if dt.tzinfo is None:
            dt = KST.localize(dt)
    except (TypeError, ValueError):
        h, m = SCHEDULED_TIMES[btype].split(":")
        dt = KST.localize(datetime.fromisoformat(date_str).replace(hour=int(h), minute=int(m)))
    return format_datetime(dt.astimezone(KST))


def write_briefings_rss(n: int = RSS_ITEMS) -> bool:
    """web/briefings/rss.xml — 최신 발행본 n편. 발행본이 없으면 쓰지 않는다."""
    if not BRIEFINGS_DIR.exists():
        return False
    dates = sorted((p.name for p in BRIEFINGS_DIR.iterdir()
                    if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)), reverse=True)
    items = []
    for d in dates:
        for t in ARCHIVE_TYPES:
            if len(items) >= n:
                break
            if not (BRIEFINGS_DIR / d / t / "index.html").exists():
                continue
            snap = BRIEFINGS_DIR / d / t / "analysis_snapshot.json"
            try:
                analysis = load_json(snap) if snap.exists() else {}
            except Exception:
                analysis = {}
            head = briefing_head(analysis, t, d)
            url = f"{SITE_BASE}/briefings/{d}/{t}/"
            items.append(
                f"    <item>\n      <title>{head['title']}</title>\n      <link>{url}</link>\n"
                f"      <guid isPermaLink=\"true\">{url}</guid>\n"
                f"      <pubDate>{_briefing_pub_date(d, t, analysis)}</pubDate>\n"
                f"      <description>{head['description']}</description>\n    </item>")
    if not items:
        return False
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n  <channel>\n'
           '    <title>Double-Shot AI 투자 브리핑</title>\n'
           f'    <link>{SITE_BASE}/briefings/</link>\n'
           f'    <atom:link href="{SITE_BASE}/briefings/rss.xml" rel="self" type="application/rss+xml"/>\n'
           '    <description>매일 아침 코스피 시초가 예측, 오후 코스피 마감 시황, 저녁 미국 증시 전망 브리핑</description>\n'
           '    <language>ko</language>\n'
           + "\n".join(items) + "\n  </channel>\n</rss>\n")
    (BRIEFINGS_DIR / "rss.xml").write_text(xml, encoding="utf-8")
    print(f"[generate_html] RSS 갱신: {len(items)}편")
    return True


# /stocks/ 맨 아래 '최근 브리핑' — 크롤러가 스크립트 없이 읽는 정적 목록(2026-10-27, §70).
# /stocks/index.html은 손으로 만든 정적 페이지라, 두 표시 사이만 다시 쓴다. 아카이브와 같은 자리에서
# 함께 갱신되므로 원본도 같다(디스크에 커밋된 발행본). 맨 위 1편만 요약을 붙인다 — 아카이브와 같은 규칙.
STOCKS_HOME_HTML = WEB_DIR / "stocks" / "index.html"
RECENT_START = "<!-- RECENT_BRIEFINGS:START -->"
RECENT_END = "<!-- RECENT_BRIEFINGS:END -->"
_WEEKDAYS = "월화수목금토일"


def build_recent_briefings(n: int = 6) -> list:
    """최신 발행본 n편 — 날짜 최신순, 하루 안에서는 미국 → 마감 → 코스피(ARCHIVE_TYPES)."""
    if not BRIEFINGS_DIR.exists():
        return []
    dates = sorted((p.name for p in BRIEFINGS_DIR.iterdir()
                    if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)), reverse=True)
    out = []
    for d in dates:
        for t in ARCHIVE_TYPES:
            if len(out) >= n:
                return out
            if not (BRIEFINGS_DIR / d / t / "index.html").exists():
                continue
            headline = re.sub(r"<[^>]+>", "", _archive_headline(d, t)).strip()
            if not headline:
                continue   # 제목 없는 편은 싣지 않는다 — 종류 이름만 남은 줄은 정보가 없다
            dt = date.fromisoformat(d)
            out.append({"url": f"/briefings/{d}/{t}/", "label": BRIEFING_LABELS[t],
                        "date": f"{dt.month}/{dt.day}({_WEEKDAYS[dt.weekday()]})",
                        "headline": headline, "dek": _archive_dek(d, t) if not out else ""})
    return out


def render_recent_briefings(items: list) -> str:
    rows = []
    for i, it in enumerate(items):
        # 요약은 우리 분석 문장이라 <b> 강조만 살리고 나머지 태그는 지운다(아카이브는 그대로 |safe로 쓴다).
        dek = re.sub(r"<(?!/?b>)[^>]+>", "", it["dek"]) if it["dek"] else ""
        rows.append(
            f'      <li class="rb-item{" feat" if i == 0 else ""}"><a href="{it["url"]}">'
            f'<div class="rb-meta">{it["date"]} · {it["label"]}</div>'
            f'<div class="rb-h">{html.escape(it["headline"])}</div>'
            + (f'<div class="rb-d">{dek}</div>' if dek else "") + "</a></li>")
    return "\n".join(rows)


def write_stocks_recent_briefings(n: int = 6) -> bool:
    """/stocks/index.html의 표시 사이에 최근 브리핑 목록을 다시 쓴다. 표시가 없거나 발행본이 없으면 건드리지 않는다."""
    if not STOCKS_HOME_HTML.exists():
        return False
    page = STOCKS_HOME_HTML.read_text(encoding="utf-8")
    i, j = page.find(RECENT_START), page.find(RECENT_END)
    items = build_recent_briefings(n)
    if i < 0 or j < i or not items:
        print("[generate_html] /stocks/ 최근 브리핑: 표시 또는 발행본 없음 — 건너뜀", file=sys.stderr)
        return False
    new = page[:i + len(RECENT_START)] + "\n" + render_recent_briefings(items) + "\n      " + page[j:]
    if new != page:
        STOCKS_HOME_HTML.write_text(new, encoding="utf-8")
    print(f"[generate_html] /stocks/ 최근 브리핑 갱신: {len(items)}편")
    return True


def write_sitemap_xml():
    """web/sitemap.xml 을 생성한다. generate_html 실행마다 자동 갱신."""
    BASE = "https://doubleshot.space"
    today = datetime.now(KST).strftime("%Y-%m-%d")

    # ⚠️ `/` 는 vercel.json에서 `/stocks/`로 301 리다이렉트된다 — sitemap에 넣으면
    #    "리디렉션이 있는 페이지"로 색인에서 제외되고 신호만 흐려진다. 도착지를 직접 등재한다.
    # /about/·/legal/* 는 손으로 만든 정적 페이지라 자동 수집 대상이 아니었다.
    # 심사·신뢰도 판단 때 가장 먼저 찾는 페이지들이므로 명시적으로 넣는다(2026-09-02 추가).
    urls = [
        {"loc": f"{BASE}/stocks/",                       "changefreq": "daily",   "priority": "1.0"},
        {"loc": f"{BASE}/briefings/",                    "changefreq": "daily",   "priority": "0.9"},
        {"loc": f"{BASE}/stocks/income-designer/",       "changefreq": "monthly", "priority": "0.8"},
        {"loc": f"{BASE}/stocks/nasdaq-check/",          "changefreq": "daily",   "priority": "0.7"},
        {"loc": f"{BASE}/about/",                        "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/legal/disclaimer/",             "changefreq": "yearly",  "priority": "0.3"},
        {"loc": f"{BASE}/legal/privacy/",                "changefreq": "yearly",  "priority": "0.3"},
        {"loc": f"{BASE}/legal/terms/",                  "changefreq": "yearly",  "priority": "0.3"},
    ]

    # ready 상태인 브리핑 페이지만 포함
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []
    ready_dates = sorted({b["date"] for b in briefings if b.get("date")}, reverse=True)

    type_order = ["kospi", "close", "us"]
    for d in ready_dates:
        for btype in type_order:
            page = BRIEFINGS_DIR / d / btype / "index.html"
            if page.exists():
                lastmod = d if d <= today else today
                urls.append({
                    "loc": f"{BASE}/briefings/{d}/{btype}/",
                    "lastmod": lastmod,
                    "changefreq": "monthly",
                    "priority": "0.7",
                })

    # 생성된 섹터 페이지만 포함 (2026-07-21 추가 — 생성은 되는데 sitemap에 빠져 색인 경로가 없었다)
    universe_path = CONFIG_DIR / "stock_universe.json"
    if universe_path.exists():
        for key in load_json(universe_path).get("sectors", {}):
            if (WEB_DIR / "stocks" / "sector" / key / "index.html").exists():
                urls.append({
                    "loc": f"{BASE}/stocks/sector/{key}/",
                    "changefreq": "daily",
                    "priority": "0.7",
                })

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{u['loc']}</loc>")
        if "lastmod" in u:
            lines.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        lines.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        lines.append(f"    <priority>{u['priority']}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")

    out_path = WEB_DIR / "sitemap.xml"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[generate_html] wrote web/sitemap.xml ({len(urls)} urls)")


def patch_landing_hero(analysis: dict, target_date: str):
    """랜딩 페이지 Hero 위젯을 최신 코스피 분석으로 갱신한다 (코스피 브리핑 생성 시에만 호출).

    NOTE: 랜딩 hero는 고정 예시(2026-06-22 실측 브리핑)로 운영한다 — 자동 갱신 비활성화.
    sig_items 필드가 스키마에 없어 reasons가 항상 비던 문제도 있었음. 되살리려면 아래 return을 제거하고
    sig_items 대신 telegram_signals를 쓰도록 reason_lines를 수정해야 한다.
    """
    return
    landing = WEB_DIR / "landing.html"
    if not landing.exists():
        return

    prediction = analysis.get("prediction", {})
    direction = prediction.get("direction", "상승 우위")
    up_pct = prediction.get("up_pct", 50)
    sig_items = (analysis.get("sig_items") or [])[:5]
    reason_title = analysis.get("reason_title", "")

    arrow = "↑" if "상승" in direction else "↓"
    up_count = sum(1 for s in sig_items if s.get("level") == "up")
    total = len(sig_items)
    tone = "강세" if "상승" in direction else "약세"
    conf_text = f"{tone} 우위 · 신호 {total}개 중 {up_count}개가 상승"

    reason_lines = []
    for item in sig_items:
        label = item.get("label", "")
        desc = re.sub(r"<[^>]+>", "", item.get("desc", ""))
        level = item.get("level", "neu")
        tag_cls = "brief-tag risk" if level == "dn" else "brief-tag"
        reason_lines.append(
            f'          <div class="brief-reason">'
            f'<span class="{tag_cls}">{label}</span>'
            f"<span>{desc}</span></div>"
        )

    widget = (
        "<!-- HERO-WIDGET:START -->\n"
        '      <div class="live">\n'
        '        <div class="live-top">\n'
        f'          <div class="lab"><span class="live-dot"></span>{target_date} · 코스피 당일 예측</div>\n'
        f'          <div class="live-dir">{arrow} {direction} <span class="prob mono">{up_pct}% 상승</span></div>\n'
        f'          <div class="brief-head">{reason_title}</div>\n'
        f'          <div class="brief-sub">{conf_text}</div>\n'
        "        </div>\n"
        '        <div class="brief-reasons">\n'
        + "\n".join(reason_lines) + "\n"
        "        </div>\n"
        f'        <a class="brief-more" href="/briefings/{target_date}/kospi/">이 브리핑 전체 읽기 →</a>\n'
        "      </div>\n"
        "      <!-- HERO-WIDGET:END -->"
    )

    html = landing.read_text(encoding="utf-8")
    updated = re.sub(
        r"<!-- HERO-WIDGET:START -->.*?<!-- HERO-WIDGET:END -->",
        widget,
        html,
        flags=re.DOTALL,
    )
    if updated == html:
        print("[generate_html] landing.html hero 마커 없음, 패치 생략")
        return
    landing.write_text(updated, encoding="utf-8")
    print(f"[generate_html] landing.html hero → {target_date} 패치 완료")


def _fmt_krw(v: float) -> str:
    """정수 원화 천 단위 콤마 포맷."""
    return f"{int(v):,}"


def _fmt_pct(v: float) -> str:
    """부호 포함 등락률 포맷."""
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.2f}%"


def _pct_cls(v: float) -> str:
    if v > 0:
        return "up"
    elif v < 0:
        return "down"
    return "flat"


_SECTOR_EMOJI = {
    "semicon": "🔬", "battery": "🔋", "auto": "🚗", "defense": "🛡️",
    "ship": "🚢", "bio": "🧬", "finance": "🏦", "power": "⚡",
}

# 섹터 페이지 본문 카피는 scripts/config/sector_copy.json에 있다.
# 2026-09-02에 파이썬 리터럴 딕셔너리에서 분리했다 — 소스에 긴 한국어 산문을 박아두면
# 수정할 때마다 코드를 건드려야 하고, 그대로 방치되기 쉽다(§20).
_SECTOR_COPY_PATH = CONFIG_DIR / "sector_copy.json"


def _sector_copy(key: str) -> dict:
    """섹터별 본문 카피. 파일·키가 없으면 빈 dict → 해당 문단이 렌더되지 않는다(§0)."""
    if not _SECTOR_COPY_PATH.exists():
        print(f"[generate_html] ⚠️ {_SECTOR_COPY_PATH.name} 없음 — 섹터 본문 생략", file=sys.stderr)
        return {}
    entry = load_json(_SECTOR_COPY_PATH).get(key)
    return entry if isinstance(entry, dict) else {}


def build_sector_pages():
    """stock_universe.json + stocks-snapshot.json → 섹터별 정적 페이지 8개 생성.

    종목 상세 페이지는 없다(2026-10-26 제거) — 종목 카드는 링크하지 않는다.
    """
    universe_path = CONFIG_DIR / "stock_universe.json"
    snapshot_path = WEB_DIR / "data" / "stocks-snapshot.json"
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snap_stocks = snapshot.get("stocks", {})
    snapshot_date = snapshot.get("generated_at", "")[:10]

    env = make_env()
    tpl = env.get_template("pages/stock_sector.html")

    all_sectors = [
        {"key": k, "label": v["label"], "emoji": _SECTOR_EMOJI.get(k, "")}
        for k, v in universe["sectors"].items()
    ]

    for key, sector in universe["sectors"].items():
        stocks = []
        for s in sector["stocks"]:
            code = s["code"]
            measured = snap_stocks.get(code)
            if not measured:
                continue
            stocks.append({
                "code": code,
                "name": s["name"],
                "close": measured["close"],
                "close_fmt": _fmt_krw(measured["close"]),
                "change_pct": measured["change_pct"],
                "pct_fmt": _fmt_pct(measured["change_pct"]),
                "pct_cls": _pct_cls(measured["change_pct"]),
                "wk52_high": measured["wk52_high"],
                "wk52_low": measured["wk52_low"],
                "wk52_high_fmt": _fmt_krw(measured["wk52_high"]),
                "wk52_low_fmt": _fmt_krw(measured["wk52_low"]),
                "spark20": measured.get("spark20", []),
                "foreign_rate": measured.get("foreign_rate"),
            })

        # 등락률 높은 순 정렬 (None은 맨 뒤) — 섹터에서 지금 뭐가 움직이는지 우선 노출
        stocks.sort(key=lambda s: (s["change_pct"] is None, -(s["change_pct"] or 0)))

        pcts = [s["change_pct"] for s in stocks if s["change_pct"] is not None]
        avg_pct = sum(pcts) / len(pcts) if pcts else 0
        breadth = {
            "up": sum(1 for p in pcts if p > 0),
            "down": sum(1 for p in pcts if p < 0),
            "flat": sum(1 for p in pcts if p == 0),
            "total": len(pcts),
        }

        # description·og:title은 템플릿의 og_desc/og_title 블록이 정본이다(base.html이 재사용).
        # 여기서는 그 블록이 만들지 못하는 canonical·JSON-LD만 넘긴다.
        html = tpl.render(
            sector_label=sector["label"],
            sector_key=key,
            canonical_url=f"{SITE_BASE}/stocks/sector/{key}/",
            seo_jsonld=[_jsonld(_breadcrumb([
                ("홈", "/stocks/"), ("종목", "/stocks/"),
                (sector["label"], f"/stocks/sector/{key}/"),
            ]))],
            sector_emoji=_SECTOR_EMOJI.get(key, ""),
            sector_copy=_sector_copy(key),
            stocks=stocks,
            avg_pct=avg_pct,
            avg_pct_fmt=_fmt_pct(avg_pct),
            avg_cls=_pct_cls(avg_pct),
            breadth=breadth,
            snapshot_date=snapshot_date,
            all_sectors=all_sectors,
            css_path=CSS_PATH,
            js_path=JS_PATH,
        )
        out_file = WEB_DIR / "stocks" / "sector" / key / "index.html"
        url = f"{SITE_BASE}/stocks/sector/{key}/"
        if gate_write(out_file, html, url):
            GATE_BLOCKED.append(url)
            continue
        print(f"섹터 페이지 {key} → {out_file}")


def _finish_page_build(written_paths):
    """페이지 배치 생성 뒤 발행 게이트 결과를 종합한다. 위반이 있으면 exit 1.

    sitemap 포함 여부는 여기서만 검사할 수 있다 — write_sitemap_xml()이 '파일이 존재하는 페이지'만
    담기 때문에 쓰기 시점엔 아직 판정이 불가능하다.
    """
    problems = [f"메타 위반으로 발행 차단: {u}" for u in GATE_BLOCKED]
    problems += check_sitemap([f"{SITE_BASE}/{p[:-len('index.html')]}" for p in written_paths])
    if not problems:
        return
    for p in problems:
        print(f"::error::[발행 게이트] {p}", file=sys.stderr)
    print(f"\n❌ 발행 게이트 위반 {len(problems)}건 — 차단된 페이지는 직전 정상본이 유지됩니다",
          file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=list(TYPE_MAP.keys()))
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--data-file", dest="data_file", help="시장 데이터 JSON 경로")
    parser.add_argument("--write-list-only", action="store_true",
                        help="briefings-list.json 만 갱신하고 HTML 재생성 없이 종료")
    parser.add_argument("--sync-index", action="store_true",
                        help="index.html + briefings-list.json 재동기화만 하고 종료 (수동 브리핑 수정 후 사용)")
    parser.add_argument("--sectors", action="store_true",
                        help="섹터별 종목 페이지 8개 생성하고 종료")
    parser.add_argument("--nasdaq-page", dest="nasdaq_page", action="store_true",
                        help="--date 날짜의 data/nasdaq_overheat.json으로 /stocks/nasdaq-check/ 상세 페이지만 다시 쓴다")
    parser.add_argument("--force", action="store_true",
                        help="기존 analysis_snapshot.json을 무시하고 최신 analysis_{type}.json으로 강제 재생성 (의도적 정정용)")
    args = parser.parse_args()

    if args.sectors:
        build_sector_pages()
        write_sitemap_xml()   # 섹터 URL이 sitemap에 들어가야 게이트의 색인 경로 검사가 성립한다
        _finish_page_build([])
        return

    if args.nasdaq_page:
        if not args.date:
            parser.error("--nasdaq-page 는 --date 가 필요합니다")
        write_nasdaq_page(args.date)
        write_sitemap_xml()
        _finish_page_build([])
        return

    if args.write_list_only:
        write_briefings_list_json()
        write_briefings_index()
        write_sitemap_xml()
        return

    if args.sync_index:
        latest = find_latest_ready()
        if latest:
            update_vercel_briefings_route(latest[0], latest[1])
        write_briefings_list_json()
        write_briefings_index()
        write_sitemap_xml()
        return

    if not args.type or not args.date or not args.data_file:
        parser.error("--type, --date, --data-file 은 필수입니다 (--write-list-only / --sync-index 사용 시 제외)")

    internal_type = TYPE_MAP[args.type]
    data_path = Path(args.data_file)
    market_data = load_json(data_path) if data_path.exists() else {}

    html, analysis = render_briefing(internal_type, args.date, market_data, force=args.force)
    write_output(html, internal_type, args.date, analysis)
    if internal_type == "kospi":
        patch_landing_hero(analysis, args.date)
        # 밤사이 브리지는 /stocks/ 홈에서만 쓰는 부가 데이터다 — 여기서 예외가 새어나가
        # 07:25 브리핑 발행 자체가 죽으면 안 된다(§0 부칙). 실패하면 파일만 갱신되지
        # 않고(어제 파일이 남아도 클라이언트가 date로 걸러낸다) 브리핑은 그대로 나간다.
        #
        # 오늘 날짜일 때만 쓴다 — 근거는 _bridge_target_is_today() 참조.
        if not _bridge_target_is_today(args.date):
            print(f"[generate_html] overnight_bridge: 과거 날짜 재생성({args.date}) — "
                  "라이브 JSON은 건드리지 않음.", file=sys.stderr)
        else:
            try:
                write_overnight_bridge_json(market_data, args.date)
            except Exception as e:
                print(f"[generate_html] overnight_bridge JSON 생성 실패({type(e).__name__}: {e}) — 건너뜀.",
                      file=sys.stderr)
    if internal_type == "us":
        # 나스닥 체크 상세 페이지 — 부가 페이지라 실패해도 브리핑 발행은 계속한다(§0 부칙과 같은 판단).
        try:
            write_nasdaq_page(args.date)
        except Exception as e:
            print(f"[generate_html] 나스닥 체크 상세 페이지 생성 실패({type(e).__name__}: {e}) — 건너뜀.",
                  file=sys.stderr)
    update_vercel_briefings_route(internal_type, args.date)
    write_briefings_list_json()
    write_briefings_index()
    write_sitemap_xml()


if __name__ == "__main__":
    main()
