# 뉴스 반복 게이트 — 직전 실행 에코·전날 장 리캡 제외와 촉매 기록 읽고 쓰기

from __future__ import annotations
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from news_common import DATA_DIR
from news_gate_reality import _parse_iso_date
from news_gate_grounding import _item_text


def _load_prev_catalysts(briefing_type: str, max_items: int = 6) -> list:
    """직전 실행이 저장한 data/news_summary_{type}.json의 catalysts·headlines를 읽는다.

    이 파일은 매 실행마다 덮어써지므로, 오늘 실행이 덮어쓰기 전 시점엔 어제(직전) 실행분이
    그대로 남아 있다 — 이 시점에 읽어 "이미 다룬 주제" 목록으로 프롬프트에 주입한다.
    2026-07-15~17 실사고: ASML·모건스탠리 실적 촉매가 프롬프트의 예시 문장과 겹치는 데다
    이 중복 방지 장치가 없어 사흘 연속 같은 이슈가 "오늘의 이슈"로 재포장됐다.
    파일 없음·파싱 실패 시 빈 리스트를 반환해 중복 방지 없이 정상 진행한다(수집 자체를 막지 않음)."""
    path = DATA_DIR / f"news_summary_{briefing_type}.json"
    if not path.exists():
        return []
    try:
        prev = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    items = (prev.get("catalysts") or []) + (prev.get("headlines") or [])
    return items[:max_items]


# 고유 식별력이 없는 범용 대문자 토큰 — 엔티티로 치지 않는다(AI·CPI 등은 매일 등장)
_GENERIC_UPPER = {
    "AI", "CPI", "PPI", "WTI", "VIX", "EPS", "GDP", "FOMC", "ETF", "IPO", "US",
    "USD", "SP", "NASDAQ", "DOW", "Q", "KPI", "M", "ADR", "HBM", "DRAM", "SOX",
    "GPU", "CPU", "CEO", "CFO", "M&A", "S", "P", "PCE", "NFP", "BOJ", "ECB",
}


def _norm_for_match(s: str) -> str:
    """한글·영숫자만 남기고 소문자로 붙인다(조사·구두점·공백 제거)."""
    return re.sub(r"[^0-9a-z가-힣]", "", (s or "").lower())


def _char_ngrams(s: str, n: int = 3) -> set:
    s = _norm_for_match(s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _distinctive_entities(text: str) -> set:
    """티커·영문 사명 등 고유 식별 토큰(2자 이상 라틴). 범용어(_GENERIC_UPPER)는 제외."""
    return {t for t in re.findall(r"[A-Za-z]{2,}", (text or "").upper())
            if t not in _GENERIC_UPPER}


def _is_cross_day_recap(text: str, stale_texts: list) -> bool:
    """text가 2일 이상 전 catalyst(stale_texts) 중 하나의 재탕이면 True.

    판정: 어떤 stale와 (유사도 ≥ 0.40) 이거나 (공유 고유엔티티 존재 AND 유사도 ≥ 0.15).
    실측(2026-07 ASML 변형)으로 튜닝 — 같은 사건 재탕은 잡고, 같은 엔티티라도 다른 뉴스는 유지."""
    g = _char_ngrams(text)
    ents = _distinctive_entities(text)
    for s in stale_texts:
        sim = _jaccard(g, _char_ngrams(s))
        if sim >= 0.40 or (ents & _distinctive_entities(s) and sim >= 0.15):
            return True
    return False


def _drop_prev_run_echoes(items: list, prev_texts: list) -> list:
    """직전 실행 결과(중복 방지용으로 프롬프트에 주입한 목록)를 그대로 되뱉은 항목을 제거한다.

    2026-08-04 재현 확인: `_load_prev_catalysts`가 "이미 다룬 주제"로 넣어준 목록을
    Gemini가 **오늘의 catalysts로 그대로 복사**해 돌려줬다. 심지어 각 항목 끝에
    "(참고: 직전 브리핑에서 언급된 내용으로…)"라고 스스로 주석까지 달았다.
    즉 중복 방지 장치가 오히려 **날조를 매일 되살리는 급식기**로 작동하고 있었다 —
    어제 실린 거짓이 오늘 프롬프트에 들어가 오늘 다시 실린다(§28 '프롬프트의 임시 항목'과 같은 계열).

    판정은 교차일 recap과 같은 유사도(문자 3-gram + 공유 고유엔티티)를 쓴다.
    prev_texts가 비어 있으면 아무것도 하지 않는다.
    """
    prev = [t for t in (_item_text(p) for p in (prev_texts or [])) if t]
    if not prev:
        return items
    kept = []
    for it in items or []:
        text = _item_text(it)
        if _SELF_LABELED_ECHO_RE.search(text) or _is_cross_day_recap(text, prev):
            print(f"[fetch_news] 직전 실행 에코 제거: {text[:70]}", file=sys.stderr)
            continue
        kept.append(it)
    return kept


# 모델이 스스로 "직전 브리핑에서 언급된 내용"이라 밝힌 흔적 — 그건 오늘의 뉴스가 아니다.
_SELF_LABELED_ECHO_RE = re.compile(
    r"(직전|이전|앞선|지난)\s*브리핑에서\s*(언급|다룬|다뤄진|소개)"
)


def _drop_cross_day_recaps(catalysts: list, stale_texts: list) -> list:
    """catalysts에서 stale_texts(2일+ 전)와 실질 중복인 항목을 하드 제외한다."""
    if not stale_texts:
        return catalysts
    kept = []
    for c in catalysts:
        if _is_cross_day_recap(c, stale_texts):
            print(f"[fetch_news] 교차일 recap 제외: {c}", file=sys.stderr)
        else:
            kept.append(c)
    return kept


def _history_path(briefing_type: str) -> Path:
    return DATA_DIR / f"catalyst_history_{briefing_type}.json"


def _load_stale_catalysts(briefing_type: str, today: date, min_age_days: int = 2) -> list:
    """catalyst_history_{type}.json에서 (today - min_age_days) 이전 날짜의 catalyst를 모아 반환.

    '오늘/어제'는 정상(신선)이므로 제외하고, 이틀 이상 전에 등장했던 것만 recap 판정 대상으로 쓴다."""
    path = _history_path(briefing_type)
    if not path.exists():
        return []
    try:
        hist = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    cutoff = today - timedelta(days=min_age_days)
    stale = []
    for entry in hist:
        d = _parse_iso_date(entry.get("date", ""))
        if d is not None and d <= cutoff:
            stale.extend(entry.get("catalysts", []))
    return stale


def _append_catalyst_history(briefing_type: str, today: date, catalysts: list,
                             keep_days: int = 5) -> None:
    """오늘 발행한 catalyst(문자열 리스트)를 히스토리에 기록하고 최근 keep_days개 날짜만 유지."""
    path = _history_path(briefing_type)
    hist = []
    if path.exists():
        try:
            hist = json.load(open(path, encoding="utf-8"))
        except Exception:
            hist = []
    today_str = today.isoformat()
    hist = [e for e in hist if e.get("date") != today_str]  # 같은 날 재실행 시 갱신
    hist.append({"date": today_str, "catalysts": list(catalysts)})
    hist.sort(key=lambda e: e.get("date", ""))
    hist = hist[-keep_days:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
