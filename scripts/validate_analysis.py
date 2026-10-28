#!/usr/bin/env python3
# Claude 분석 결과(analysis_*.json)의 수치·본문을 실측·규칙으로 검증·교정하는 발행 게이트
"""
call_claude → [validate_analysis] → generate_html 사이에서 동작.

- 교정 가능: analysis_*.json 제자리 교정 후 저장 (exit 0)
- 치명적/교정 불가: exit 1 + 관리자 텔레그램 알림 (발행 중단)

설계: docs/superpowers/specs/2026-06-02-analysis-validation-gate-design.md
"""
import argparse
import copy
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import scripts.superlative_subject as _ss
except ImportError:
    import superlative_subject as _ss

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

LATEST_FILE = {
    "kospi": "latest_kospi.json",
    "us": "latest_us.json",
    "kospi-close": "latest_kospi_close.json",
}

# 본문 스캔 대상 스칼라 필드. 위반 시 **차단하지 않고** 금지 문장만 제거하고 발행을 잇는다
# (2026-06-04 aa0e4eb3 — 한 문장 때문에 브리핑 전체를 막는 게 과했다).
# 전체가 금지 패턴이면 필드를 비우고 warning만 남기므로, 이 필드를 렌더하는 템플릿은
# 빈 값 가드가 있어야 한다(close_reason.html·why_what_so.html 참고).
# 리스트 필드는 위반 원소만 제거된다.
SCALAR_PROSE = {
    "kospi-close": ["dek", "market_summary", "why", "what", "so_what"],
    "kospi": [],
    "us": [],
}
# 헤드라인은 검사 제외
EXCLUDED_FIELDS = {"reason_title", "market_title"}

FX_MIN, FX_MAX = 1000, 2000  # 원/달러 환율 정상 범위
INDEX_PCT_MAX = 30.0         # 지수 일간 등락률 절대값 상한
REASONS_MIN = 2             # 교정 후 남아야 할 최소 reasons 수

# ── 패턴 ──────────────────────────────────────────────────────────────────────
# 숫자+경 (뒤에 한글 음절이 없을 때만 — '경기/경제/경우' 오탐 방지)
GYEONG_RE = re.compile(r"\d[\d,]*\s*경(?![가-힣])")
HWANYUL_CTX_RE = re.compile(r"(환율|원\s*/\s*달러|원달러)")
WON_NUM_RE = re.compile(r"([\d,]+)\s*원")
INDEX_CTX_RE = re.compile(r"(코스피|코스닥)")
PCT_NUM_RE = re.compile(r"([+-][\d.]+)\s*%")


def parse_price(s):
    """'53,600원' / '$53.60' / 53600 → float. 파싱 불가 시 None."""
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    m = re.search(r"[-+]?[\d,]*\.?\d+", s.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def strip_tags(text):
    """<b> 등 HTML 태그 제거 (패턴 스캔 시 태그 경계로 인한 누락 방지)."""
    return re.sub(r"<[^>]+>", "", text or "")


def find_forbidden(text):
    """본문 문자열에서 금지 패턴을 찾아 사유 리스트를 반환한다 (없으면 빈 리스트)."""
    if not isinstance(text, str) or not text:
        return []
    t = strip_tags(text)
    reasons = []

    if GYEONG_RE.search(t):
        reasons.append("금지 단위 '경'(시총/금액)")

    # 환율: 환율 키워드 인근(뒤 20자) 원-숫자가 정상 범위 밖
    for m in HWANYUL_CTX_RE.finditer(t):
        win = t[m.end():m.end() + 20]
        wn = WON_NUM_RE.search(win)
        if wn:
            val = parse_price(wn.group(1))
            if val is not None and not (FX_MIN <= val <= FX_MAX):
                reasons.append(f"환율 범위 이탈({val:.0f}원)")
            break

    # 지수 등락률: 코스피/코스닥 인근(앞뒤 25자) % 절대값 30 초과
    for m in INDEX_CTX_RE.finditer(t):
        win = t[max(0, m.start() - 25):m.end() + 25]
        for pm in PCT_NUM_RE.finditer(win):
            val = parse_price(pm.group(1))
            if val is not None and abs(val) > INDEX_PCT_MAX:
                reasons.append(f"지수 등락률 비정상({val:+.1f}%)")
        if reasons and reasons[-1].startswith("지수"):
            break

    return reasons


def is_contradicted(stated_pct: float, real_pct: float) -> bool:
    """산문에 기재된 % 수치가 실측 change_pct와 충돌하는지 판정.

    조건: diff > 5%p AND (실측 < 0.5% OR 배수 >= 5배 OR 부호 반전)
    """
    diff = abs(stated_pct - real_pct)
    if diff <= 5.0:
        return False
    if abs(real_pct) < 0.5:
        return True
    # 방향 반전 (부호가 다르고 diff > 5%p) → 차단
    if stated_pct * real_pct < 0:
        return True
    return abs(stated_pct / real_pct) >= 5.0


# change claim 컨텍스트 키워드 — 일간 변동률을 서술하는 문장에서만 % 추출
_CHANGE_CTX_RE = re.compile(
    r'(?:'
    r'전일\s*[+-]?\d'           # "전일 +X%"
    r'|단\s*하루에'              # "단 하루에 +X%"
    r'|하루\s*만에'              # "하루 만에 +X%"
    r'|[+-]?\d[\d.]*\s*%\s*(?:폭등|급등|폭락|급락|상승|하락|올랐|떨어|빠졌|내려앉|주저앉)'  # "+X% 폭등"
    r'|(?:폭등|급등|폭락|급락|상승|하락|내려앉|주저앉)\s*[+-]?\d'  # "폭등 +X%"
    r')'
)
_PCT_RE = re.compile(r'([+-]?\d+\.?\d*)\s*%')


def _extract_change_claims(text: str) -> list:
    """산문 텍스트에서 '일간 변동률'을 서술하는 % 수치만 추출한다.
    MA 대비, 목표 수익률, 손절 % 등은 제외.
    """
    if not isinstance(text, str):
        return []
    t = strip_tags(text)
    # 수집된 (% 수치 위치, 값) 쌍을 모은 뒤 위치 중복 제거
    # % 기호의 위치로 중복을 감지 (같은 % 기호를 여러 패턴이 지칭하는 경우 제거)
    seen_pct_positions = set()
    results = []
    for m in _CHANGE_CTX_RE.finditer(t):
        window = t[m.start(): m.end() + 30]
        for pm in _PCT_RE.finditer(window):
            # % 기호의 절대 위치 (pm.group()의 끝 위치 = % 기호)
            pct_char_pos = m.start() + pm.end() - 1
            if pct_char_pos in seen_pct_positions:
                continue
            seen_pct_positions.add(pct_char_pos)
            try:
                results.append(float(pm.group(1)))
            except ValueError:
                pass
    return results


# ── 픽 외 종목 산문 검증 ────────────────────────────────────────────────────────

# ETF·지수·약어 등 티커처럼 보이지만 개별 종목이 아닌 단어 제외 목록
# 단, 실측 조회 가능한 지수/ETF(DRAM·SOX·VIX·EWY·GLD·SPY·QQQ·IWM·XLK·XLF·
# SOXX·SOXL·TQQQ)는 제외하지 않고 산문 방향 검증 대상으로 둔다.
# (SOX→^SOX, VIX→^VIX는 _PROSE_FETCH_ALIAS로 매핑). 환각 방향 표현을 잡기 위함.
_NON_TICKER = frozenset({
    "USD", "ETF", "GDP", "CPI", "NFP", "DXY", "PCE",
    "ISM", "PMI", "FED", "ECB", "BOJ", "AI", "US", "NQ", "SP",
    "FOMC", "WTI", "DAX", "JPY", "KRW", "EUR",
    "NYSE", "KRX", "KST", "MA", "MA20", "MA200",
    "LLM", "API", "IPO", "CEO", "CFO", "REIT", "FY", "EPS", "PE",
})

# 산문 약칭 → 실측 조회용 심볼 (지수는 yfinance용 ^ 접두 필요)
_PROSE_FETCH_ALIAS = {"SOX": "^SOX", "VIX": "^VIX"}

# ASCII 문자 경계로 추출 — "SOX가"·"NVDA는"처럼 한국어 조사가 붙어도 인식
# (\b만으로는 X↔가 사이에 워드 경계가 없어 누락됨)
_US_TICKER_RE = re.compile(r"(?<![A-Za-z])([A-Z]{2,5})(?![A-Za-z])")

# 방향 단어: 상승/하락 문맥 감지
_UP_WORDS_RE = re.compile(r"(올랐|상승|급등|폭등|강세|반등|오르며|오른|올라|강하게)")
_DOWN_WORDS_RE = re.compile(r"(내렸|하락|급락|폭락|약세|빠졌|떨어|내리며|내린|내려앉|주저앉|하락세|폭락|폭등)")


def _sentence_split(text: str) -> list:
    """텍스트를 문장 단위로 분리. HTML 태그 경계 고려."""
    return [s.strip() for s in re.split(r"(?<=[.。!?])\s*", text) if s.strip()]


def _join_sentences(sentences: list) -> str:
    """분리된 문장 리스트를 하나의 문자열로 합친다."""
    return " ".join(s for s in sentences if s.strip())


def _direction_contradicts(sentence: str, real_chg: float) -> bool:
    """문장의 방향 표현(정성·정량)이 실측 change_pct와 모순인지 확인."""
    plain = strip_tags(sentence)
    # 정량 % 수치 모순
    claims = _extract_change_claims(plain)
    if any(is_contradicted(c, real_chg) for c in claims):
        return True
    # 정성 방향 모순: 텍스트 상승인데 실측 하락(-1% 미만), 또는 반대
    has_up = bool(_UP_WORDS_RE.search(plain))
    has_dn = bool(_DOWN_WORDS_RE.search(plain))
    if has_up and not has_dn and real_chg <= -1.0:
        return True
    if has_dn and not has_up and real_chg >= 1.0:
        return True
    return False


def validate_prose_nonpick_stocks(analysis: dict, btype: str,
                                   corrections: list, warnings: list) -> None:
    """픽에 없는 개별 종목이 산문(reasons·scenario)에 언급될 때,
    방향 표현이 실측과 모순이면 해당 문장을 제거한다.

    현재 미국(us) 브리핑만 지원 — 한국 종목명 추출은 사전 필요.
    """
    if btype != "us":
        return

    # 이미 검증된 픽 티커 집합 (재조회 방지)
    pick_tickers: set = set()
    for p in (analysis.get("stock_picks") or []):
        tk = (p.get("ticker") or "").strip().upper()
        if tk:
            pick_tickers.add(tk)

    # 모든 산문에서 티커 후보 수집 (중복 제거)
    candidate_tickers: set = set()
    all_prose = list(analysis.get("reasons") or []) + [
        p.get("scenario", "") for p in (analysis.get("stock_picks") or [])
        if p.get("scenario")
    ]
    for text in all_prose:
        for m in _US_TICKER_RE.finditer(strip_tags(text)):
            tk = m.group(1)
            if tk not in _NON_TICKER and tk not in pick_tickers:
                candidate_tickers.add(tk)

    if not candidate_tickers:
        return

    # 각 티커 실측 fetch (캐시)
    realdata_cache: dict = {}
    for tk in candidate_tickers:
        data = _fetch_us_realdata(_PROSE_FETCH_ALIAS.get(tk, tk))
        if "error" not in data and data.get("change_pct") is not None:
            realdata_cache[tk] = data["change_pct"]

    if not realdata_cache:
        return

    def _tickers_in_text(text: str) -> list:
        plain = strip_tags(text)
        return [m.group(1) for m in _US_TICKER_RE.finditer(plain)
                if m.group(1) in realdata_cache]

    # ── reasons 문장 단위 교정 ────────────────────────────────────────────────
    if isinstance(analysis.get("reasons"), list):
        kept = []
        for item in analysis["reasons"]:
            tickers_in_item = _tickers_in_text(item)
            if not tickers_in_item:
                kept.append(item)
                continue
            # 항목 내 모순 티커 존재 여부 확인
            bad_tickers = [tk for tk in tickers_in_item
                           if _direction_contradicts(item, realdata_cache[tk])]
            if bad_tickers:
                corrections.append(
                    f"reasons 항목 제거 (비픽 종목 방향 모순 {bad_tickers}): {item[:60]}"
                )
            else:
                kept.append(item)
        analysis["reasons"] = kept

    # ── 픽 scenario 문장 단위 교정 ───────────────────────────────────────────
    for pick in (analysis.get("stock_picks") or []):
        sc = pick.get("scenario") or ""
        if not sc:
            continue
        tickers_in_sc = _tickers_in_text(sc)
        if not tickers_in_sc:
            continue
        sentences = _sentence_split(sc)
        kept_sents = []
        for sent in sentences:
            bad = [tk for tk in _tickers_in_text(sent)
                   if _direction_contradicts(sent, realdata_cache[tk])]
            if bad:
                corrections.append(
                    f"픽 '{pick.get('name')}' scenario 문장 제거 "
                    f"(비픽 종목 방향 모순 {bad}): {sent[:60]}"
                )
            else:
                kept_sents.append(sent)
        pick["scenario"] = _join_sentences(kept_sents)


def validate_todays_view_recap(analysis: dict, btype: str,
                               corrections: list, warnings: list) -> None:
    """오늘의 관점 recap 항목 중, codes로 명시된 종목의 방향 서술이
    실측과 모순이면 해당 항목을 제거한다. (한국 종목: 코드로 직접 실측)"""
    if btype != "kospi":
        return
    tv = analysis.get("todays_view") or {}
    recap = tv.get("recap")
    if not isinstance(recap, list):
        return
    real: dict = {}
    seen: set = set()
    for item in recap:
        for code in (item.get("codes") or []):
            if code in seen:
                continue
            seen.add(code)
            d = _fetch_kospi_realdata(code)
            if "error" not in d and d.get("change_pct") is not None:
                real[code] = d["change_pct"]
            else:
                warnings.append(f"todays_view.recap 종목 '{code}' 실측 실패 — 방향 교차검증 생략")
    kept = []
    for item in recap:
        codes = [c for c in (item.get("codes") or []) if c in real]
        bad = [c for c in codes if _direction_contradicts(item.get("text", ""), real[c])]
        if bad:
            corrections.append(f"todays_view.recap 항목 제거 (종목 방향 모순 {bad}): {item.get('text','')[:50]}")
        else:
            kept.append(item)
    tv["recap"] = kept


def validate_todays_view_outlook(analysis: dict, btype: str,
                                 corrections: list, warnings: list) -> None:
    """오늘의 관점 outlook 중 사실 주장(tag=='event')은 source가 있어야 유지한다.
    source가 없는 event는 근거 없는 일정 주장(할루시네이션 위험)이므로 제거.
    tag=='watch'(정성 관전)는 소스 없이 유지."""
    if btype != "kospi":
        return
    tv = analysis.get("todays_view") or {}
    outlook = tv.get("outlook")
    if not isinstance(outlook, list):
        return
    kept = []
    for o in outlook:
        if o.get("tag") == "event" and not (o.get("source") or "").strip():
            corrections.append(f"todays_view.outlook event 제거 (근거 소스 없음): {o.get('text','')[:50]}")
            continue
        kept.append(o)
    tv["outlook"] = kept


def _us_figure_stale(text: str, real_chg: float, tol: float = 2.0) -> bool:
    """key_drivers 산문에 인용된 US 지수/ETF 일간 변동률이 실측과 tol%p 넘게 벌어지면 True.

    is_contradicted(5%p·5배·부호반전)는 '인접 세션 stale'(어제·그제처럼 실제로 존재하는
    옆 세션 값을 그대로 인용한 경우)을 못 잡는다. 예: EWY '+6.18%'(전 세션 값) vs 실측 '+1.72%'
    → diff 4.46%p로 is_contradicted 임계 미만이라 통과. SOX·EWY change_pct는 fetch_data와
    게이트가 같은 일봉 소스로 계산해 같은 세션이면 소수점까지 일치하므로, 정밀 데이터 인용에
    한해 더 타이트한 임계치(기본 2%p)를 별도 적용해 세션 어긋남을 잡는다."""
    for c in _extract_change_claims(strip_tags(text)):
        if abs(c - real_chg) > tol:
            return True
    return False


# 산문에 한글·기호로 등장하는 미국 지수명 → 실측 조회 심볼.
# _US_TICKER_RE는 ASCII 티커만 잡아서 "나스닥"·"S&P500"이 무검증으로 통과했다
# (2026-07-27 실사고: 실제 S&P500 +0.05%인데 "-0.05% 조정 마감"으로 발행).
# 긴 이름부터 매칭해야 "나스닥100 선물"이 "나스닥"으로 오인식되지 않는다.
_INDEX_NAME_SYMBOL = [
    ("필라델피아 반도체지수", "^SOX"),
    ("필라델피아 반도체", "^SOX"),
    ("필라델피아반도체", "^SOX"),
    ("나스닥100", None),   # 선물 — 일봉 실측과 기준이 달라 검증 대상에서 제외
    ("나스닥", "^IXIC"),
    ("S&P500", "^GSPC"),
    ("S&P 500", "^GSPC"),
    ("다우존스", "^DJI"),
    ("다우", "^DJI"),
]

# 지수명 바로 뒤(최대 12자 이내)에 붙은 등락률만 그 지수의 주장으로 본다.
# 문자열 전체를 훑으면 "나스닥 -0.64%, S&P500 +0.05%"처럼 여러 지수가 한 문장에 있을 때
# 서로의 수치와 교차 비교돼 정상 항목을 오제거한다.
_PCT_NEAR_RE = r"[^%]{0,12}?([+-]?\d+(?:\.\d+)?)\s*%"


def _index_figures(text: str) -> dict:
    """산문에서 '지수명 + 인접 등락률'을 뽑아 {심볼: 주장 등락률}로 돌려준다."""
    plain = strip_tags(text)
    # 검증 제외 이름(나스닥100 선물 등)을 먼저 마스킹한다.
    # 안 하면 짧은 별칭('나스닥')이 "나스닥100 선물 +1.17%"를 잡아 엉뚱한 지수로 오인식한다.
    for name, symbol in _INDEX_NAME_SYMBOL:
        if symbol is None:
            plain = plain.replace(name, "○" * len(name))

    out: dict = {}
    for name, symbol in _INDEX_NAME_SYMBOL:
        if symbol is None or symbol in out:
            continue
        m = re.search(re.escape(name) + _PCT_NEAR_RE, plain)
        if m:
            out[symbol] = float(m.group(1))
            # 매칭 구간을 지워 짧은 별칭(다우존스→다우)이 같은 수치를 다시 잡지 않게 한다
            plain = plain[:m.start()] + "○" * (m.end() - m.start()) + plain[m.end():]
    return out


def _index_figure_wrong(claimed: float, real: float) -> bool:
    """지수 등락률 주장이 실측과 어긋나는지. 부호 반전 또는 2%p 초과 차이."""
    if claimed * real < 0 and abs(claimed - real) > 0.02:
        return True   # 부호 반전 (0.00 근처 노이즈는 제외)
    return abs(claimed - real) > 2.0


def validate_key_drivers(analysis: dict, btype: str,
                         corrections: list, warnings: list) -> None:
    """이렇게 보는 이유(key_drivers) 항목의 종목·지수 서술이 실측과 모순이면 항목을 제거한다.

    - 한국 종목: codes로 명시된 코드를 직접 실측해 방향 교차검증 (recap과 동일 로직).
    - 미국 지수/ETF(SOX·EWY·NVDA 등): codes가 비어도 본문 티커를 추출해 실측 재조회한 뒤,
      방향 모순 또는 정량 stale(_us_figure_stale)이면 제거. codes 없는 US 서사가 무검증으로
      통과하던 구멍을 막는다 (2026-07-22 stale·날조 US 서사 실사고)."""
    if btype != "kospi":
        return
    drivers = analysis.get("key_drivers")
    if not isinstance(drivers, list):
        return

    # ── 한국 종목 실측 (codes 명시) ──────────────────────────────────────────
    kr_real: dict = {}
    seen: set = set()
    for item in drivers:
        if not isinstance(item, dict):
            continue
        for code in (item.get("codes") or []):
            if code in seen:
                continue
            seen.add(code)
            d = _fetch_kospi_realdata(code)
            if "error" not in d and d.get("change_pct") is not None:
                kr_real[code] = d["change_pct"]
            else:
                warnings.append(f"key_drivers 종목 '{code}' 실측 실패 — 방향 교차검증 생략")

    # ── 미국 지수/ETF 실측 (codes 없이 본문 티커 추출) ────────────────────────
    us_real: dict = {}
    for item in drivers:
        if not isinstance(item, dict):
            continue
        for m in _US_TICKER_RE.finditer(strip_tags(item.get("text", ""))):
            tk = m.group(1)
            if tk in _NON_TICKER or tk in us_real:
                continue
            d = _fetch_us_realdata(_PROSE_FETCH_ALIAS.get(tk, tk))
            if "error" not in d and d.get("change_pct") is not None:
                us_real[tk] = d["change_pct"]
            # fetch 실패 시 조용히 생략(fail-open) — 깨진 실측으로 정상 항목을 오제거하지 않는다

    # ── 한글·기호 지수명(나스닥·S&P500 등) 실측 ─────────────────────────────────
    idx_real: dict = {}
    for item in drivers:
        if not isinstance(item, dict):
            continue
        for symbol in _index_figures(item.get("text", "")):
            if symbol in idx_real:
                continue
            d = _fetch_us_realdata(symbol)
            if "error" not in d and d.get("change_pct") is not None:
                idx_real[symbol] = d["change_pct"]

    kept = []
    for item in drivers:
        if not isinstance(item, dict):
            continue
        text = item.get("text", "")
        bad = [c for c in (item.get("codes") or []) if c in kr_real
               and _direction_contradicts(text, kr_real[c])]
        for m in _US_TICKER_RE.finditer(strip_tags(text)):
            tk = m.group(1)
            if tk in us_real and (_direction_contradicts(text, us_real[tk])
                                  or _us_figure_stale(text, us_real[tk])):
                bad.append(tk)
        for symbol, claimed in _index_figures(text).items():
            if symbol in idx_real and _index_figure_wrong(claimed, idx_real[symbol]):
                bad.append(f"{symbol}({claimed:+.2f}% vs 실측 {idx_real[symbol]:+.2f}%)")
        if bad:
            corrections.append(f"key_drivers 항목 제거 (방향·수치 모순 {bad}): {text[:50]}")
        else:
            kept.append(item)
    if len(kept) < len(drivers):
        warnings.append(f"key_drivers {len(drivers)}→{len(kept)}개 (모순 항목 제거)")
    analysis["key_drivers"] = kept


# ── 종목 후보(실측) 수집·매칭 ──────────────────────────────────────────────────
def _walk_strings(obj, fn) -> int:
    """dict/list를 재귀 순회하며 모든 문자열에 fn을 적용한다. 바뀐 개수를 반환."""
    n = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                new = fn(v)
                if new != v:
                    obj[k] = new
                    n += 1
            else:
                n += _walk_strings(v, fn)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                new = fn(v)
                if new != v:
                    obj[i] = new
                    n += 1
            else:
                n += _walk_strings(v, fn)
    return n


def fix_overnight_labels(analysis, btype, corrections):
    """'간밤' 표기 교정 — 월요일·휴일 다음날은 직전 미국장이 어제가 아니다.

    2026-07-27 실사고: 월요일 코스피 브리핑이 지난 금요일(7/24) 미국장을 "간밤"으로 서술.
    프롬프트 지시만으로는 새는 표현이라(§22 교훈) 발행 직전 결정론적으로 치환한다.
    """
    if btype != "kospi":
        return
    try:
        from datetime import datetime as _dt
        import pytz
        from session_label import fix_overnight_wording, is_overnight_us, us_session_label
    except Exception as e:
        print(f"[validate] 간밤 표기 검사 생략: {e}", file=sys.stderr)
        return

    today = _dt.now(pytz.timezone("Asia/Seoul")).date()
    if is_overnight_us(today):
        return  # 직전 미국장이 실제로 간밤 — 교정 불필요
    label = us_session_label(today)
    n = _walk_strings(analysis, lambda s: fix_overnight_wording(s, today))
    if n:
        corrections.append(f"'간밤' 표기 {n}건 → '{label}' 교정 (직전 미국장이 어제가 아님)")


# 역할을 가리키는 표현 뒤에서만 전임자 이름을 현직으로 바꾼다 — '파월 전 의장'처럼 전임자를 일부러 쓴 문장은 두고,
# 파월은 2028년까지 이사로 남아 이름 자체를 지우면 안 된다(§64).
_ROLE_SUFFIX = r"(\s*(?:연준\s*)?의장|의?\s*(?:발언|기자회견|회견|입|톤|메시지|연설|코멘트))"


def fix_officeholder_names(analysis, corrections, warnings, table=None):
    """현직 인물 교정 — 모델이 학습 시점 인물(예: 파월)을 현직 역할로 쓴 표현을 현직 이름으로 바꾼다.

    2026-10-26 코스피 '개장 후 볼 것'이 "파월 발언 톤"이라고 썼다. 실제 의장은 2026-05-22부터 워시다(§29에서도 같은 오류).
    역할 표현이 붙지 않은 전임자 이름은 바꾸지 않고 경고만 남긴다(전임자를 일부러 쓴 문장일 수 있다).
    """
    import re as _re
    if table is None:
        try:
            table = json.loads((Path(__file__).parent / "config" / "officeholders.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"[validate] 현직 인물 표 읽기 실패: {e}", file=sys.stderr)
            return
    for key, o in table.items():
        if key.startswith("_") or not isinstance(o, dict):
            continue
        for old in o.get("former") or []:
            pat = _re.compile(_re.escape(old) + _ROLE_SUFFIX)
            n = _walk_strings(analysis, lambda t, pat=pat, new=o["name"]: pat.sub(lambda m: new + m.group(1), t))
            if n:
                corrections.append(f"{o['role']} 이름 {n}건 '{old}' → '{o['name']}' 교정 (현직: {o['full_name']})")
            left = []
            _walk_strings(analysis, lambda t, old=old: (left.append(t) if old in t else None) or t)
            if left:
                warnings.append(f"전임 {o['role']} '{old}' 언급이 남아 있어요(역할 표현 없음 — 확인 필요): {left[0][:60]}")


# ── 픽 종목 실측 주입 (yfinance 직접 fetch) ───────────────────────────────────
# Claude는 후보 풀과 무관하게 종목을 자유 선택하므로, 사전 수집된 candidate가
# 대부분 비어 있다. 픽된 종목의 ticker를 직접 fetch해 price·change·MA·sparkline을
# 실측으로 덮어쓰고, generate_html이 읽는 candidate 리스트에도 주입한다.


def _closes_to_realdata(closes, ndigits, live_price=None):
    """일봉 종가 리스트(오래된→최신)로 실측 dict를 만든다.

    기본(live_price=None): '전일 등락률' = close[-1] vs close[-2] (실시간 장중가 아님).
    코스피 아침 브리핑처럼 **직전 완료 세션**이 기준인 경로가 이 동작을 쓴다.

    live_price 지정 시: 발행 시점의 실체결가(프리마켓·장중)를 현재가로 삼고
    **직전 정규장 종가(close[-1])를 기준가**로 등락률을 낸다. 미국 브리핑은
    21:15 KST = 프리마켓 한복판에 발행되므로 이 경로를 쓴다 — close[-1] vs close[-2]를
    쓰면 "지금"이 아니라 직전 세션의 등락이 실린다(2026-07-27 실사고, 운영 규칙 0).
    """
    if len(closes) < 2:
        return {"error": "insufficient data"}
    price, prev = closes[-1], closes[-2]
    if live_price:
        price, prev = float(live_price), closes[-1]
    r = (lambda v: round(v, ndigits))
    spark = closes[-20:] if not live_price else (closes[-19:] + [float(live_price)])
    out = {
        "price": r(price),
        "change_pct": round((price - prev) / prev * 100, 4),
        "sparkline": [r(x) for x in spark],
    }

    def _ma_series(window):
        # 마지막 20개 지점의 이동평균(데이터 부족 시 윈도우 clamp)
        return [sum(closes[max(0, i - window + 1):i + 1]) / len(closes[max(0, i - window + 1):i + 1])
                for i in range(len(closes) - 20, len(closes))]

    if len(closes) >= 20:
        ma20 = _ma_series(20)
        out["ma20_dist_pct"] = round((price - ma20[-1]) / ma20[-1] * 100, 2)
        out["ma20_sparkline"] = [r(v) for v in ma20]
        # 이격률뿐 아니라 **절대 수준**도 낸다 — 픽 카드가 손절 기준선을 실측으로 보여주고,
        # LLM이 "20일선 이탈 시"라고 쓴 손절가를 이 값으로 검증하기 위함(2026-09-02).
        out["ma20_level"] = r(ma20[-1])
    if len(closes) >= 200:
        ma200 = _ma_series(200)
        out["ma200_dist_pct"] = round((price - ma200[-1]) / ma200[-1] * 100, 2)
        out["ma200_level"] = r(ma200[-1])
        out["ma200_sparkline"] = [r(v) for v in ma200]
    return out


def _closes_from_toss_candles(candles: list, ndigits: int, live_price=None) -> dict:
    """Toss 캔들 리스트(오래된→최신)에서 실측 dict를 만든다."""
    closes = [float(c["closePrice"]) for c in candles if c.get("closePrice")]
    result = _closes_to_realdata(closes, ndigits, live_price=live_price)
    # vol_mult: 최신 거래량 / 직전 20일 평균 (tradingVolume 필드가 있을 때만)
    volumes = [float(c["tradingVolume"]) for c in candles if c.get("tradingVolume")]
    if len(volumes) >= 2:
        avg20 = sum(volumes[max(0, len(volumes) - 21):-1]) / min(20, len(volumes) - 1)
        if avg20 > 0:
            result["vol_mult"] = round(volumes[-1] / avg20, 1)
    return result


def _us_live_price(ticker):
    """발행 시점의 미국 종목 실체결가(프리마켓·장중 포함). 실패 시 None.

    yfinance fast_info는 연장시간대를 반영하지 않으므로 prepost intraday를 함께 본다
    (`fetch_data._extended_hours_price` 참조 — 2026-07-27 실사고).
    """
    try:
        try:
            from scripts.fetch_data import _get_realtime_price
        except ImportError:
            from fetch_data import _get_realtime_price
        rt = _get_realtime_price(ticker)
        return float(rt[0]) if rt and rt[0] else None
    except Exception:
        return None


def _fetch_us_realdata(ticker, live=False):
    """미국 종목 실측. Toss 캔들 우선, 실패 시 yfinance 폴백.

    live=True면 발행 시점 실체결가(프리마켓 포함)를 현재가로, 직전 정규장 종가를
    기준가로 삼는다. 미국 브리핑은 프리마켓 한복판에 나가므로 이 경로를 쓴다.
    """
    live_price = _us_live_price(ticker) if live else None

    # 1) 토스 API
    try:
        import scripts.toss_client as tc
    except ImportError:
        try:
            import toss_client as tc
        except ImportError:
            tc = None
    if tc:
        try:
            candles = tc.get_candles(ticker, interval="1d", count=300)
            if candles:
                return _closes_from_toss_candles(candles, ndigits=4, live_price=live_price)
        except Exception:
            pass

    # 2) yfinance 폴백
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="300d").dropna(subset=["Close"])
        closes = [float(x) for x in hist["Close"].tolist()]
        return _closes_to_realdata(closes, ndigits=4, live_price=live_price)
    except Exception as e:
        return {"error": str(e)}


def _pin_session_date():
    """DS_PIN_SESSION_DATE(KST)가 있으면 date, 없으면 None.

    코스피 아침 브리핑을 장 시작 후 수동 재생성할 때, 픽 실측이 **오늘 장중 값**으로
    주입되는 것을 막는다. 07:25 발행 시점엔 한국장이 닫혀 있어 §0가 "직전 완료 세션
    종가 대비"를 기준으로 삼는데, 09시 이후 재실행하면 토스·네이버 모두 당일 진행 중인
    (미완성) 일봉을 최신 캔들로 돌려주기 때문이다 — 실측 확인 결과 오늘 캔들의 거래량이
    전일의 1/6 수준이었다(장 초반 부분 데이터).
    """
    from datetime import datetime as _dt
    raw = os.environ.get("DS_PIN_SESSION_DATE", "").strip()
    if not raw:
        return None
    try:
        return _dt.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        print(f"[validate] DS_PIN_SESSION_DATE 형식 오류: {raw!r} — 무시", file=sys.stderr)
        return None


def _drop_rows_at_pin(rows, date_of):
    """pin 날짜 이후(당일 포함) 행 제거. pin이 없으면 그대로."""
    pin = _pin_session_date()
    if pin is None or not rows:
        return rows
    kept = []
    for r in rows:
        d = date_of(r)
        if d is None or d < pin:
            kept.append(r)
    if len(kept) < len(rows):
        print(f"[validate] pin {pin} — 당일 캔들 {len(rows) - len(kept)}건 제외", file=sys.stderr)
    return kept


def _toss_candle_date(c):
    from datetime import datetime as _dt
    try:
        return _dt.fromisoformat(str(c.get("timestamp"))).date()
    except Exception:
        return None


def _naver_row_date(r):
    from datetime import datetime as _dt
    try:
        return _dt.strptime(str(r.get("localDate"))[:8], "%Y%m%d").date()
    except Exception:
        return None


def _fetch_kospi_realdata(code):
    """한국 종목 실측 (6자리 코드). 정규장 공식 종가 일봉(kr_official_closes) 기준.

    토스 일봉은 쓰지 않는다 — 2026-09-14 대조에서 5종목 30거래일 중 26~29일이 KRX 공식 종가와
    달랐고(최대 8.27%, 넥스트레이드·시간외 체결이 섞인 값으로 보임) 거래소·세션을 고르는 옵션도 없다.
    §37에 미해결로 남았던 "토스·네이버 최대 4% 차이"의 원인이다(§48).
    """
    try:
        try:
            from scripts import kr_official_closes as koc
        except ImportError:
            import kr_official_closes as koc
        rows = _drop_rows_at_pin(koc.official_day_rows(code), _naver_row_date)
        closes = [float(rw["closePrice"]) for rw in rows if rw.get("closePrice")]
        return _closes_to_realdata(closes, ndigits=2)
    except Exception as e:
        return {"error": str(e)}


# ── 정성 최상급 주장 게이트 (2026-07-29 실사고 §28) ─────────────────────────────
# "나스닥이 사상 최고치를 경신"처럼 **숫자가 하나도 없는** 주장은 등락률 게이트
# (_index_figure_wrong·_us_figure_stale)가 구조적으로 발화할 수 없다 — 인접 수치가 있어야
# 비교가 성립하기 때문이다. 실제로 그날 나스닥은 -0.22% 하락 마감이었고, 같은 페이지
# 사이드바(실측)에 -0.22%가 찍혀 있는데도 본문만 "사상 최고"로 나갔다.
_SUPERLATIVE_HIGH_RE = _ss.HIGH_RE
_SUPERLATIVE_LOW_RE = _ss.LOW_RE
# 최상급 주장은 이 리스트 필드에서 발견되면 항목을 제거하고, 그 밖(스칼라 산문)에서
# 발견되면 발행을 차단한다 — 산문은 자동 수정이 불가능하고, 틀린 전제 위에 쓰인 글이라
# 문장 하나만 지워도 나머지 서사가 그대로 남기 때문이다.
_SUPERLATIVE_LIST_FIELDS = (
    "key_drivers", "watch_items", "telegram_signals", "reasons", "issues",
)


def _index_extremes(symbol):
    """지수 실측 스냅샷 {level, change_pct, high_52w, low_52w}. 실패 시 None(fail-open)."""
    closes = []
    try:
        import scripts.toss_client as tc
    except ImportError:
        try:
            import toss_client as tc
        except ImportError:
            tc = None
    if tc:
        try:
            candles = tc.get_candles(symbol, interval="1d", count=300)
            closes = [float(c["closePrice"]) for c in candles or [] if c.get("closePrice")]
        except Exception:
            closes = []
    if len(closes) < 2:
        try:
            import yfinance as yf
            hist = yf.Ticker(symbol).history(period="1y").dropna(subset=["Close"])
            closes = [float(x) for x in hist["Close"].tolist()]
        except Exception as e:
            print(f"[validate] {symbol} 실측 조회 실패(최상급 대조 생략): {e}", file=sys.stderr)
            return None
    if len(closes) < 2:
        return None
    return {
        "level": closes[-1],
        "change_pct": round((closes[-1] / closes[-2] - 1) * 100, 2),
        "high_52w": max(closes),
        "low_52w": min(closes),
    }


def find_superlative_violations(text, idx_real):
    """text의 '지수명 + 사상 최고/최저' 주장 중 실측과 어긋나는 것들의 사유 목록.

    최상급 표현마다 같은 문장 안의 주어를 하나만 정한다(superlative_subject, §59).
    앞뒤 25자 창으로 판정하던 때는 문장 경계를 넘어 "국채금리는 … 최고치를 기록했어요.
    이 금리 부담이 다우를 끌어내렸어요"를 다우의 주장으로 오판해 발행을 막았다.
    """
    plain = strip_tags(text or "")
    hits = []
    sym_of = dict(_INDEX_NAME_SYMBOL)
    for name, kind in _ss.attributed_superlatives(plain, _INDEX_NAME_SYMBOL):
        snap = idx_real.get(sym_of.get(name))
        if not snap:
            continue
        if kind == "high":
            if snap["change_pct"] < 0:
                hits.append(f"{name} '최고' 주장이나 실측 {snap['change_pct']:+.2f}% 하락")
            elif snap["level"] < snap["high_52w"] * 0.99:
                hits.append(f"{name} '최고' 주장이나 실측 {snap['level']:,.0f} "
                            f"< 52주 고점 {snap['high_52w']:,.0f}")
        else:
            if snap["change_pct"] > 0:
                hits.append(f"{name} '최저' 주장이나 실측 {snap['change_pct']:+.2f}% 상승")
            elif snap["level"] > snap["low_52w"] * 1.01:
                hits.append(f"{name} '최저' 주장이나 실측 {snap['level']:,.0f} "
                            f"> 52주 저점 {snap['low_52w']:,.0f}")
    return hits


def _superlative_texts(obj):
    """dict/list를 재귀 순회하며 최상급 표현이 든 문자열만 모은다(실측 조회 전 사전 필터)."""
    found = []
    if isinstance(obj, str):
        if _SUPERLATIVE_HIGH_RE.search(obj) or _SUPERLATIVE_LOW_RE.search(obj):
            found.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            found += _superlative_texts(v)
    elif isinstance(obj, list):
        for v in obj:
            found += _superlative_texts(v)
    return found


def clamp_prediction_to_prior(analysis: dict, prior: dict, corrections: list) -> None:
    """prediction.up_pct를 prior 확률 ±10%p 안으로 당기고 down_pct를 맞춘다. 고치면 corrections에 적는다.

    AI 방향이 prior가 가리키는 방향과 다르면(재생성 실패로 남은 경우) 손대지 않는다 —
    '하락 우위'라고 쓰고 상승 확률 60%를 붙이면 한 화면에서 방향과 숫자가 어긋난다.
    """
    from leading_signal import clamp_up_pct, direction_breaks_prior
    pred = analysis.get("prediction")
    if not isinstance(pred, dict) or (prior or {}).get("up_pct") is None:
        return
    if direction_breaks_prior(prior, pred.get("direction", "")):
        return
    up = pred.get("up_pct")
    fixed = clamp_up_pct(up, prior["up_pct"])
    if fixed is None or fixed == up:
        return
    pred["up_pct"], pred["down_pct"] = fixed, 100 - fixed
    corrections.append(f"up_pct {up}% → {fixed}% (prior 시초가 상승 확률 {prior['up_pct']}% ±10%p 밖)")


def validate_index_superlatives(analysis, corrections, warnings, blocks):
    """지수의 '사상 최고/최저' 주장을 실측과 대조해 리스트 항목은 제거, 산문은 발행 차단.

    최상급 표현이 아예 없으면 네트워크 조회 없이 즉시 반환한다(대부분의 날).
    실측 조회 실패 시엔 판단하지 않는다(fail-open) — 정상 항목 오제거·오차단을 막는다.
    """
    texts = _superlative_texts(analysis)
    if not texts:
        return
    symbols = {sym for name, sym in _INDEX_NAME_SYMBOL
               if sym and any(name in strip_tags(t) for t in texts)}
    if not symbols:
        return
    idx_real = {}
    for sym in symbols:
        snap = _index_extremes(sym)
        if snap:
            idx_real[sym] = snap
    if not idx_real:
        warnings.append("지수 최상급 주장 발견했으나 실측 조회 실패 — 대조 생략")
        return

    # 1) 리스트 필드는 위반 항목만 제거
    for fld in _SUPERLATIVE_LIST_FIELDS:
        items = analysis.get(fld)
        if not isinstance(items, list):
            continue
        kept = []
        for it in items:
            blob = json.dumps(it, ensure_ascii=False) if not isinstance(it, str) else it
            # 필드별로 따로 본다 — JSON으로 이어붙이면 제목의 지수명과 본문의 최상급이
            # 문장 경계 없이 붙어 주어가 엉킨다(§59)
            hits = [h for t in _superlative_texts(it)
                    for h in find_superlative_violations(t, idx_real)]
            if hits:
                corrections.append(f"{fld} 항목 제거 (실측 모순 {hits}): {strip_tags(blob)[:60]}")
            else:
                kept.append(it)
        analysis[fld] = kept

    # 2) 남은 곳(스칼라 산문 등)에 위반이 있으면 차단 — 산문은 자동 교정이 불가능하다
    for t in _superlative_texts(analysis):
        hits = find_superlative_violations(t, idx_real)
        if hits:
            blocks.append(f"지수 최상급 주장이 실측과 모순 ({hits}): {strip_tags(t)[:80]}")


# ── 이미 끝난 경제 이벤트의 예고형 서술 (2026-07-30 실사고 §29) ──────────────
# 03:00 KST FOMC가 07:25 코스피·21:15 미국 브리핑에서 모두 "예정"으로 나갔다.
# 캘린더 소스가 actual을 안 채워 모델에겐 모든 이벤트가 미발표로 보였던 게 원인이고,
# 이 게이트는 프롬프트 지시가 새더라도 발행 직전에 잡는 최종 방어선이다.
_PREVIEW_TENSE_RE = re.compile(
    r"(예정|앞두고|앞둔|대기|유력|기다리|나올\s*것|발표를\s*앞|관망)"
)
# 제목에서 뽑아낼 한글 본문용 키워드 — 대문자 약어는 한국어 기사에 그대로 쓰인다.
_EVENT_ACRONYM_RE = re.compile(r"\b([A-Z]{3,5})\b")

def _collect_strings(obj):
    """dict/list를 재귀 순회하며 문자열만 모은다.

    ⚠️ 치환용 `_walk_strings(obj, fn)`(§24)과 이름이 겹치면 그쪽을 덮어써서
    '간밤' 표기 교정이 TypeError로 죽는다(2026-08-03 실사고). 이름을 되돌리지 말 것.
    """
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _collect_strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _collect_strings(v)]
    return []


def _event_keywords(calendar):
    """캘린더에서 (이미 끝난 이벤트 키워드, 아직 안 온 이벤트 키워드)를 뽑는다."""
    released, upcoming = set(), set()
    for e in ((calendar or {}).get("today") or []):
        if not isinstance(e, dict):
            continue
        bucket = released if e.get("status") == "released" else upcoming
        bucket.update(_EVENT_ACRONYM_RE.findall(e.get("title", "")))
    return released - upcoming, upcoming


def find_event_tense_violations(text, released_kws, upcoming_kws):
    """이미 끝난 이벤트를 예고형으로 서술한 **문장**을 찾는다.

    문장 단위로 판정한다 — 실제 사고 문장("오늘 새벽 FOMC 결정 + 파월 기자회견 …
    기준금리 동결이 유력하지만")은 이벤트명과 예고 표현이 수십 자 떨어져 있어
    좁은 문자 창으로는 잡히지 않았다. 반대로 본문 전체를 한 덩어리로 보면
    "FOMC는 동결했어요. 실적 발표가 예정된 종목을 봐요"처럼 무관한 예고까지 걸린다.

    아직 안 온 이벤트 키워드가 같은 문장에 있으면 그쪽에 걸린 예고로 보고 넘어간다
    (예: "FOMC 결과가 나온 뒤 PCE 발표가 예정돼 있어요").
    """
    if not text or not released_kws:
        return []
    hits = []
    for sent in _SENT_SPLIT.split(strip_tags(text)):
        if any(u in sent for u in upcoming_kws):
            continue
        kw = next((k for k in released_kws if k in sent), None)
        if not kw:
            continue
        hit = _PREVIEW_TENSE_RE.search(sent)
        if hit:
            hits.append(f"{kw}…{hit.group(1)}")
    return hits


def validate_event_tense(analysis, calendar, corrections, warnings, blocks):
    """끝난 이벤트의 예고형 서술을 리스트 항목은 제거, 스칼라 산문은 발행 차단.

    끝난 이벤트가 없는 날(대부분)에는 즉시 반환한다. 네트워크 조회가 없어 비용이 없다.
    """
    released, upcoming = _event_keywords(calendar)
    if not released:
        return

    for fld in _SUPERLATIVE_LIST_FIELDS:
        items = analysis.get(fld)
        if not isinstance(items, list):
            continue
        kept = []
        for it in items:
            blob = it if isinstance(it, str) else json.dumps(it, ensure_ascii=False)
            hits = find_event_tense_violations(blob, released, upcoming)
            if hits:
                corrections.append(f"{fld} 항목 제거 (끝난 이벤트를 예고형 서술 {hits}): "
                                   f"{strip_tags(blob)[:60]}")
            else:
                kept.append(it)
        analysis[fld] = kept

    # 리스트 필드를 뺀 나머지를 **재귀로** 훑는다 — todays_view.outlook처럼 중첩된
    # 산문에 실제 사고 문장이 들어 있었다. 산문은 자동 교정이 불가능하므로 차단한다.
    rest = {k: v for k, v in analysis.items() if k not in _SUPERLATIVE_LIST_FIELDS}
    for val in _collect_strings(rest):
        hits = find_event_tense_violations(val, released, upcoming)
        if hits:
            blocks.append(f"이미 끝난 경제 이벤트를 예고형으로 서술 ({hits}): {strip_tags(val)[:80]}")


def fix_event_day_words(analysis, calendar, corrections) -> int:
    """미국 이벤트를 가리키는 '오늘/내일 새벽·밤'을 실제 KST 날짜로 고친다(2026-10-28 실사고).

    "오늘 새벽 FOMC 결과 발표가 예정돼 있어요"(07:25 발행, 실제 10/29 03:00 KST) → "내일 새벽 …".
    프롬프트 지시(call_claude._event_when_directive)가 새더라도 발행 직전에 결정론으로 잡는다.
    계산은 event_when 한 곳이다(§30).
    """
    try:
        from datetime import datetime as _dt
        import pytz
        from event_when import fix_day_words, us_events
    except Exception as e:
        print(f"[validate] 이벤트 시각 표기 검사 생략: {e}", file=sys.stderr)
        return 0
    evs = us_events(calendar)
    if not evs:
        return 0
    today = _dt.now(pytz.timezone("Asia/Seoul")).date()
    n = _walk_strings(analysis, lambda t: fix_day_words(t, evs, today))
    if n:
        corrections.append(f"미국 이벤트 시각 표기 {n}건을 한국 시간 기준(오늘/내일)으로 교정")
    return n


# 프리장·시간외에 거래되지 않는 '지수' — 이 시간대엔 값이 갱신되지 않는다.
# 뒤에 '선물'이 붙으면 제외한다(지수 선물은 연장시간대에도 거래된다).
_NO_PREMARKET_INDEX = (
    r"(?:SOX|반도체\s*(?:관련\s*)?지수|필라델피아\s*반도체|나스닥|S&P\s*500|S&P500|다우|코스피|코스닥)"
    r"(?!\s*(?:\d+\s*)?선물)"
)
_SESSION_WORDS = r"(?:프리마켓|프리장|시간\s*외|장\s*전)"
# 한국어 문장 종결 기준 분할 (…요. / …다. / ? / ! / 줄바꿈)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def find_session_mislabels(issues) -> list:
    """프리장에 거래되지 않는 지수를 '프리마켓에서'로 서술한 항목을 찾는다.

    2026-07-27 재생성 중 실제 재발: 모델이 SOX 금요일 종가(-4.25%)를 보고
    "반도체지수(SOX)는 프리마켓에서 눌리고 있어요"라고 썼다. SOX는 지수라 프리장에
    갱신되지 않으므로 그 수치는 직전 정규장 값이고, 실제 프리마켓 반도체주는 반등 중이라
    서사가 정반대였다(§26과 같은 계열 — 발행 시각과 데이터 기준의 불일치).

    **문장 단위로 판정한다** — 본문 전체를 훑으면 "SOX는 금요일 밀렸어요. 다만 오늘
    프리마켓에서는 AMD가 올랐어요"처럼 정상적으로 세션을 구분한 서술까지 걸린다.
    """
    bad = []
    for it in issues or []:
        # 제목과 본문은 **따로** 본다 — 이어붙이면 제목의 세션 표현이 본문 첫 문장과
        # 한 덩어리가 돼, 세션을 올바로 구분한 서술까지 걸린다.
        fields = ([str(it.get(k, "")) for k in ("title", "body")]
                  if isinstance(it, dict) else [str(it)])
        hit = None
        for field in fields:
            for sent in _SENT_SPLIT.split(field):
                if not re.search(_SESSION_WORDS, sent):
                    continue
                m = re.search(_NO_PREMARKET_INDEX, sent)
                if m:
                    hit = {"subject": m.group(0).strip(), "sentence": sent.strip()}
                    break
            if hit:
                break
        if hit:
            bad.append(hit)
    return bad


_PREMARKET_PHRASE = re.compile(r"(?:프리마켓|프리장)(?=에서|에도|에|은|는|$|\s)")
_PREMARKET_DROP = re.compile(r"(?:프리마켓|프리장)(?:에서도|에서는|에서|에도|에는|에)?\s*")
_ISSUE_BODY_MAX_SENT = 1


def trim_issue_bodies(analysis, corrections, max_sent=_ISSUE_BODY_MAX_SENT) -> int:
    """미국 이슈 본문을 첫 문장만 남긴다 — 설명이 길다는 지적(2026-10-26). 프롬프트(1문장·70자 안팎)만으로는 새서
    발행 전에 한 번 더 자른다. 문장을 고쳐 쓰지 않고 모델이 쓴 앞 문장을 그대로 남긴다."""
    n = 0
    for it in analysis.get("issues") or []:
        if not isinstance(it, dict) or not isinstance(it.get("body"), str):
            continue
        sents = [x for x in re.split(r"(?<=[.!?])\s+", it["body"].strip()) if x]
        if len(sents) > max_sent:
            it["body"] = " ".join(sents[:max_sent])
            n += 1
    if n:
        corrections.append(f"이슈 본문 {n}건을 첫 {max_sent}문장으로 줄임")
    return n


def fix_session_mislabels(analysis, corrections) -> int:
    """프리장에 거래되지 않는 지수를 '프리마켓에서'로 쓴 절을 '직전 정규장에서'로 고친다(미국 브리핑, §65 보강).

    2026-10-23 발행본: "프리마켓에서 반도체(SOX)가 크게 밀려요"(이슈 제목)·"프리마켓에서도 SOX가 큰 폭으로
    눌려 있어요"(dek). SOX −6.72%는 10/22 정규장 값이다 — 7/27(§27)과 같은 오류가 경고만 남기고 발행됐다.
    지수와 '프리마켓'이 **같은 절**(쉼표 사이)에 있을 때만 고친다. "SOX는 정규장에서 밀렸고, 프리마켓에서
    AMD는 올랐어요"처럼 세션을 나눈 문장은 둔다. '시간 외'·'장 전'은 뜻이 넓어 고치지 않는다(경고만 남는다).
    """
    def fix_text(text, said=False):
        out_sents = []
        for sent in re.split(r"(?<=[.!?])(\s+)", text):
            clauses = sent.split(",")
            for i, cl in enumerate(clauses):
                if re.search(_NO_PREMARKET_INDEX, cl) and _PREMARKET_PHRASE.search(cl):
                    if said or "직전 정규장" in ",".join(clauses[:i]):
                        # 같은 문장 앞에서 이미 '직전 정규장'을 말했다 — 또 쓰면 "직전 정규장에서 …, 직전 정규장에서도 …"처럼
                        # 어색하게 반복된다(2026-10-26 사용자 지적). 세션 표현을 조사째 지운다.
                        clauses[i] = _PREMARKET_DROP.sub("", cl)
                    else:
                        clauses[i] = _PREMARKET_PHRASE.sub("직전 정규장", cl)
            out_sents.append(",".join(clauses))
        return "".join(out_sents)

    n = 0
    pairs = [(it, "title", "body") for it in analysis.get("issues") or [] if isinstance(it, dict)]
    tv = analysis.get("todays_view")
    if isinstance(tv, dict):
        pairs.append((tv, "view_title", "dek"))
    for obj, head, body in pairs:
        said = False
        for k in (head, body):
            v = obj.get(k)
            if not isinstance(v, str):
                continue
            new = fix_text(v, said=said)        # 제목에서 이미 '직전 정규장'이라 했으면 본문에선 되풀이하지 않는다
            if new != v:
                obj[k] = new
                n += 1
            said = said or "직전 정규장" in new
    if n:
        corrections.append(f"세션 오표기 {n}건 교정 — 프리장에 거래되지 않는 지수의 '프리마켓' → '직전 정규장'")
    return n


def limit_data_issues(analysis, corrections, max_data=1) -> int:
    """미국 이슈 중 시장 데이터만으로 만든 이슈(kind == "data")를 하루 max_data개까지만 남긴다(사용자 결정 2026-10-26).

    10/23 미국 브리핑은 이슈 5개 중 2개(금리·VIX, S&P500 20일선 이탈)가 뉴스 사건이 아니라 기술적 위치였다.
    kind가 없는 이슈는 판단하지 않는다(fail-open — 옛 프롬프트 출력·kind 누락).
    """
    issues = analysis.get("issues")
    if not isinstance(issues, list):
        return 0
    kept, seen, dropped = [], 0, []
    for it in issues:
        if isinstance(it, dict) and it.get("kind") == "data":
            seen += 1
            if seen > max_data:
                dropped.append(it.get("title", ""))
                continue
        kept.append(it)
    if dropped:
        analysis["issues"] = kept
        corrections.append(f"데이터형 이슈 {len(dropped)}건 제외(하루 {max_data}개까지): " + " / ".join(t[:30] for t in dropped))
    return len(dropped)


def _fetch_kospi_index_levels():
    """코스피 지수 실측 + 핵심 레벨(지지/저항) 산출.

    네이버 일봉 차트(`/api/kospi-live`와 동일 출처)에서 최근 5거래일 고가/저가를
    뽑아 저항=최근 5일 고가, 지지=최근 5일 저가로 계산한다. 두 값 모두 당일 종가를
    항상 사이에 두므로 현재가가 밴드를 벗어나지 않는다.

    Returns {"price","support","resistance"} or {"error":...}.
    """
    import urllib.request
    from datetime import datetime, timedelta
    try:
        end = datetime.now().strftime("%Y%m%d") + "0000"
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d") + "0000"
        url = (f"https://api.stock.naver.com/chart/domestic/index/KOSPI/day"
               f"?startDateTime={start}&endDateTime={end}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read())
        recent = rows[-5:]
        highs = [float(r["highPrice"]) for r in recent if r.get("highPrice")]
        lows = [float(r["lowPrice"]) for r in recent if r.get("lowPrice")]
        closes = [float(r["closePrice"]) for r in recent if r.get("closePrice")]
        if not highs or not lows or not closes:
            return {"error": "코스피 일봉 행 없음"}
        return {
            "price": closes[-1],
            "support": round(min(lows) / 10) * 10,
            "resistance": round(max(highs) / 10) * 10,
        }
    except Exception as e:
        return {"error": str(e)}


def inject_kospi_index_levels(analysis, corrections, warnings):
    """코스피 '핵심 레벨' watch_item의 지지/저항 num을 실측 지수 기반으로 덮어쓴다.

    LLM은 실제 코스피 지수를 입력받지 못해 학습 기억(현실 지수)으로 levels를
    채우므로, 발행 전 실측값으로 교정한다. (SERVICE_RULES 0번 원칙)
    """
    watch_key = "watch_items" if "watch_items" in analysis else "watchpoints"
    watch = analysis.get(watch_key)
    if not isinstance(watch, list):
        return
    target = next(
        (it for it in watch
         if isinstance(it, dict) and isinstance(it.get("levels"), list) and it["levels"]),
        None,
    )
    if target is None:
        return
    idx = _fetch_kospi_index_levels()
    if "error" in idx:
        warnings.append(f"코스피 핵심 레벨 실측 실패 — LLM 값 유지: {idx['error']}")
        return
    fmt = lambda n: f"{int(round(n)):,}"
    old = {lv.get("label"): lv.get("num") for lv in target["levels"]}
    for lv in target["levels"]:
        if lv.get("cls") == "dn" or lv.get("label") == "지지":
            lv.update(label="지지", num=fmt(idx["support"]), cls="dn")
        elif lv.get("cls") == "up" or lv.get("label") == "저항":
            lv.update(label="저항", num=fmt(idx["resistance"]), cls="up")
    corrections.append(
        f"코스피 핵심 레벨 실측 주입 (지지 {old.get('지지')}→{fmt(idx['support'])}, "
        f"저항 {old.get('저항')}→{fmt(idx['resistance'])}; 현재 지수 {fmt(idx['price'])})"
    )


def _filter_list_prose(items, label, corrections):
    """리스트형 본문 원소 중 금지 패턴이 있는 것을 제거하고, 남은 리스트를 반환."""
    if not isinstance(items, list):
        return items, 0
    kept, removed = [], 0
    for it in items:
        text = it if isinstance(it, str) else (it.get("text", "") if isinstance(it, dict) else "")
        bad = find_forbidden(text)
        if bad:
            corrections.append(f"{label} 원소 제거: {bad}")
            removed += 1
            continue
        kept.append(it)
    return kept, removed


# ── 수급 수치 스케일 크로스체크 (kospi-close) ────────────────────────────────
def _extract_eok_values(text):
    """본문에서 억원 수치를 추출한다. '6조 5,941억' → 65941, '659억' → 659."""
    t = strip_tags(text or "")
    values = set()
    # N조 M억
    for m in re.finditer(r"([\d,]+)\s*조\s*([\d,]+)\s*억", t):
        jo  = int(m.group(1).replace(",", ""))
        eok = int(m.group(2).replace(",", ""))
        values.add(jo * 10000 + eok)
    # N억 (앞 6자 안에 '조'가 없을 때만)
    for m in re.finditer(r"([\d,]+)\s*억", t):
        ctx = t[max(0, m.start() - 6):m.start()]
        if "조" not in ctx:
            values.add(int(m.group(1).replace(",", "")))
    return values


def _check_supply_scale(analysis, latest, warnings):
    """마감 브리핑 분석 본문의 수급 수치 스케일을 크로스체크한다.

    investor_trading.net(백만원 → 억원 변환값)과 본문 언급 수치를 비교.
    실제 값의 1/100 수준이 언급되고 실제 값은 언급되지 않으면 WARN.
    """
    it = latest.get("investor_trading", {})
    if not it:
        return

    actuals = {}  # actor → 실제 억원(절대값)
    for actor in ("foreign", "institution", "individual"):
        net = (it.get(actor) or {}).get("net")
        if net is not None:
            eok = abs(round(net / 100))
            if eok >= 100:   # 100억 미만은 검사 실익 없음
                actuals[actor] = eok

    if not actuals:
        return

    # 분석 본문 전체에서 억원 숫자 추출
    prose = " ".join(
        analysis.get(f, "") or ""
        for f in ("market_summary", "why", "what", "so_what")
    )
    mentioned = _extract_eok_values(prose)
    if not mentioned:
        return

    LABEL = {"foreign": "외국인", "institution": "기관", "individual": "개인"}

    for actor, actual in actuals.items():
        wrong_scale = actual // 100  # 100배 축소된 잘못된 값

        # 잘못된 스케일(±40%) 언급 & 올바른 스케일(±40%) 미언급
        near_wrong   = any(abs(v - wrong_scale) / wrong_scale <= 0.4 for v in mentioned)
        near_correct = any(abs(v - actual)      / actual       <= 0.4 for v in mentioned)

        if near_wrong and not near_correct:
            fmt_actual = (
                f"{actual // 10000}조 {actual % 10000:,}억"
                if actual >= 10000 else f"{actual:,}억"
            )
            fmt_wrong = f"{wrong_scale:,}억"
            warnings.append(
                f"수급 스케일 불일치 ({LABEL[actor]}): 본문에 {fmt_wrong} 언급, "
                f"실제 {fmt_actual} — 단위 100배 오류 의심"
            )


# ── 형식↔본문 불일치 ──────────────────────────────────────────────────────────
# 각 형식의 '근거 섹션 본문'이 담기는 필드. 하나라도 차 있으면 섹션이 렌더된다.
# generate_html.build_*_context()가 실제로 읽는 키와 1:1로 맞춘다 — 한쪽만 바뀌면 이 게이트가
# 조용히 헛돈다. 형식을 추가할 땐 여기에도 등록할 것(test_registry_covers_every_rotation_format).
FORMAT_BODY_FIELDS = {
    "split": (),                                   # 형식별 필드 없음 — todays_view의 recap/outlook이 본문
    "scenario": ("sc_left_items", "sc_right_items", "sc_summary"),
    "why_what_so": ("why", "what", "so_what"),
    "qa": ("qa_items",),
    "signal": ("sig_items",),
    "flow": ("flow_steps",),
    "keynum": ("num_cards",),
}
FORMAT_FALLBACK = "split"


_TITLE_PCT_RE = re.compile(r"\d+(?:\.\d+)?(?=\s*%)")


_AMOUNT_NO_COMMA_RE = re.compile(r"(?<![\d,.])(\d{4,})(?=\s*(?:억|조|만|원))")


def fix_amount_commas(analysis, corrections):
    """제목·보조 문장의 금액(억·조·만·원 앞 네 자리 이상 숫자)에 쉼표를 넣는다 (전 타입, 2026-10-27).

    제목은 "6047억", 보조 문장은 "6,047억원"처럼 한 메시지 안에서 표기가 갈렸다. 숫자는 바꾸지 않고 표기만 맞춘다.
    "5500선"·"2026년"처럼 금액 단위가 아닌 숫자는 건드리지 않는다.
    """
    def fix(text):
        return _AMOUNT_NO_COMMA_RE.sub(lambda m: f"{int(m.group(1)):,}", text)

    targets = [(analysis, k) for k in ("reason_title", "market_title", "dek")]
    tv = analysis.get("todays_view")
    if isinstance(tv, dict):
        targets += [(tv, "view_title"), (tv, "dek")]
    for obj, key in targets:
        val = obj.get(key)
        if isinstance(val, str):
            new = fix(val)
            if new != val:
                obj[key] = new
                corrections.append(f"금액 쉼표 — {key}: {val[:40]} → {new[:40]}")


def fix_view_title_figures(analysis, btype, corrections):
    """헤드라인(todays_view.view_title)의 등락률이 검증된 본문에 없으면 헤드라인을 근거 문장으로 바꾼다 (kospi).

    헤드라인은 웹 페이지 맨 위·아카이브·텔레그램 첫 줄에 그대로 나가는데, 숫자 게이트는 key_drivers·recap에만 있다.
    그래서 헤드라인의 % 숫자는 게이트를 통과한 key_drivers·recap에 같은 숫자로 있어야 한다(부호는 보지 않는다 —
    "-6.72% 급락"과 "6.72% 밀렸다"는 같은 주장이다). 없으면 key_drivers[0]의 굵은 첫 문장으로 바꾼다(§0).
    호출 시점은 validate_key_drivers 이후 — 제거된 항목의 숫자를 근거로 삼지 않는다.
    """
    if btype != "kospi":
        return
    tv = analysis.get("todays_view")
    if not isinstance(tv, dict) or not isinstance(tv.get("view_title"), str):
        return
    title = tv["view_title"]
    figs = set(_TITLE_PCT_RE.findall(strip_tags(title)))
    if not figs:
        return
    kd = [k for k in (analysis.get("key_drivers") or []) if isinstance(k, dict)]
    evidence = " ".join(strip_tags(x.get("text", "")) for x in kd + list(tv.get("recap") or []) if isinstance(x, dict))
    missing = sorted(figs - set(_TITLE_PCT_RE.findall(evidence)))
    if not missing:
        return
    lead = ""
    if kd:
        m = re.search(r"<b>(.*?)</b>", kd[0].get("text", ""))
        lead = strip_tags(m.group(1) if m else kd[0].get("text", "")).strip()
    if lead and not (set(_TITLE_PCT_RE.findall(lead)) - set(_TITLE_PCT_RE.findall(evidence))):
        tv["view_title"] = lead
        corrections.append(f"view_title 교체 (근거에 없는 숫자 {missing}): {strip_tags(title)[:50]} → {lead[:50]}")
    else:
        corrections.append(f"view_title의 근거 없는 숫자 {missing} — 대체할 근거 문장이 없어 숫자만 지움: {strip_tags(title)[:50]}")
        tv["view_title"] = re.sub(r"\s*[+\-−]?\d+(?:\.\d+)?\s*%", "", title).strip()


def fix_format_payload_mismatch(analysis, corrections, warnings, blocks):
    """찍힌 analysis_format의 본문이 비었으면 내용에 맞는 형식으로 내려앉힌다.

    call_claude가 형식을 랜덤 추첨해 프롬프트로 지시한 뒤, 응답 내용과 무관하게
    `analysis["analysis_format"] = chosen_format`으로 덮어쓴다. 모델이 지시한 형식의 필드를
    내놓지 않으면 generate_html이 그 형식 템플릿을 골라 **빈 껍데기**를 렌더한다.

    2026-08-13 실사고: keynum으로 찍혔으나 num_cards가 없어 `<div class="keynum-grid"></div>`가
    그대로 발행됐다. 게다가 todays_view의 recap/outlook은 split일 때만 렌더되므로, 모델이
    만들어둔 복기·관전 2단까지 함께 사라져 근거 본문이 통째로 빈 채 나갔다.

    내용이 온전한데 포장만 어긋난 것이므로 발행을 막지 않고 split으로 내려앉힌다 — §0은
    "짧거나 섹션이 비는 것은 감수하되 틀린 것은 감수하지 않는다"이고, 여기서 틀린 것은 없다.
    다만 내려앉힐 내용조차 없으면 빈 브리핑이 나가므로 그때는 발행을 막는다.
    """
    fmt = analysis.get("analysis_format")
    if not fmt:
        return
    fields = FORMAT_BODY_FIELDS.get(fmt)
    if fields is None:
        warnings.append(
            f"analysis_format '{fmt}'가 FORMAT_BODY_FIELDS에 미등록 — 빈 섹션 검사를 건너뛴다. "
            "형식을 추가했다면 이 표에도 등록할 것")
        return
    if not fields or any(analysis.get(f) for f in fields):
        return

    # split으로 내려앉혔을 때 실제로 보여줄 본문이 남는가.
    tv = analysis.get("todays_view") or {}
    has_core = bool(tv.get("recap") or tv.get("outlook") or analysis.get("key_drivers"))
    if not has_core:
        blocks.append(
            f"analysis_format '{fmt}'의 본문({'/'.join(fields)})이 비었고 "
            "todays_view·key_drivers도 없어 근거 섹션이 통째로 빈다 — 빈 브리핑 발행 차단")
        return

    analysis["analysis_format"] = FORMAT_FALLBACK
    corrections.append(
        f"analysis_format '{fmt}' → '{FORMAT_FALLBACK}': "
        f"'{fmt}' 본문({'/'.join(fields)})이 비어 빈 섹션이 렌더될 상황 — "
        "모델이 실제로 만든 todays_view 본문으로 렌더한다")


# ── 검증 본체 ─────────────────────────────────────────────────────────────────
def validate(analysis, latest, btype):
    """analysis를 검증·교정한다.

    Returns dict: {analysis(교정본), corrections[], warnings[], blocks[]}
    blocks 비어있지 않으면 발행 차단.
    """
    a = copy.deepcopy(analysis)
    corrections, warnings, blocks = [], [], []

    # 1) 구조 필드 — 예측형 브리핑(kospi)만. 마감(kospi-close)은 예측 필드가 없는 시황 요약이라 제외.
    #    us는 이슈 중심 구조로 재정의되며 prediction 필드가 없어졌으므로(예측 정확도 채점 탈퇴) 제외.
    if btype == "kospi":
        pred = a.get("prediction") or {}
        up = pred.get("up_pct")
        if not isinstance(up, (int, float)) or isinstance(up, bool) or not (0 <= up <= 100):
            blocks.append(f"prediction.up_pct 비정상: {up!r}")
        if not pred.get("direction"):
            blocks.append("prediction.direction 누락")

    # 1-a) 형식↔본문 불일치 — 빈 껍데기 섹션 발행 차단. 다른 교정보다 먼저 형식을 확정해야
    #      이후 단계가 실제로 렌더될 필드를 대상으로 검사한다.
    fix_format_payload_mismatch(a, corrections, warnings, blocks)

    # 1-b) 위로 한 줄 — 순수 정서적 문구만 허용. 숫자·%·종목 티커가 섞이면 통째로 제거.
    cl = a.get("comfort_line")
    if isinstance(cl, str) and cl.strip():
        if re.search(r"\d|%|[A-Z]{2,5}\b", strip_tags(cl)):
            warnings.append(f"comfort_line 제거 (숫자·티커 포함): {cl!r}")
            a["comfort_line"] = ""

    # 2-c) 산문 교차검증 — 픽 외 개별 종목 방향 모순 (us 전용)
    if btype == "us":
        validate_prose_nonpick_stocks(a, btype, corrections, warnings)

    # 2-d) 오늘의 관점 검증 (kospi 전용)
    validate_todays_view_recap(a, btype, corrections, warnings)
    validate_todays_view_outlook(a, btype, corrections, warnings)
    validate_key_drivers(a, btype, corrections, warnings)
    fix_view_title_figures(a, btype, corrections)

    # 2-d-2) 이슈 세션 오표기 — 프리장 미거래 지수를 '프리마켓에서'로 서술 (us 전용)
    if btype == "us":
        fix_session_mislabels(a, corrections)      # 같은 절에 지수+프리마켓이면 교정, 남는 건 아래에서 경고
        limit_data_issues(a, corrections)          # 시장 데이터형 이슈는 하루 1개까지
        trim_issue_bodies(a, corrections)          # 이슈 본문은 한 문장
        for hit in find_session_mislabels(a.get("issues")):
            warnings.append(
                f"세션 오표기 의심 — {hit['subject']}는 프리장에 거래되지 않는다"
                f"(그 수치는 직전 정규장 값): {hit['sentence'][:80]}"
            )

    # 2-d-3) 지수 '사상 최고/최저' 정성 주장 실측 대조 (전 타입)
    validate_index_superlatives(a, corrections, warnings, blocks)

    # 2-d-2) 이미 끝난 경제 이벤트를 예고형으로 쓴 서술 차단 (§29)
    validate_event_tense(a, (latest or {}).get("economic_calendar"), corrections, warnings, blocks)
    fix_event_day_words(a, (latest or {}).get("economic_calendar"), corrections)   # '오늘 새벽 FOMC' → 실제 KST 날짜

    # 2-e) '간밤' 표기 교정 — 월요일·휴일 다음날 (kospi 전용)
    fix_overnight_labels(a, btype, corrections)

    # 2-f) 현직 인물 교정 — 전임 연준 의장 이름을 현직 역할로 쓴 표현 (전 타입, §64)
    fix_officeholder_names(a, corrections, warnings)

    # 2-g) 제목·보조 문장 금액 쉼표 (전 타입)
    fix_amount_commas(a, corrections)

    # 3) 계층 2 — 리스트형 본문
    if isinstance(a.get("reasons"), list):
        kept, _ = _filter_list_prose(a["reasons"], "reasons", corrections)
        a["reasons"] = kept
        if len(kept) < REASONS_MIN:
            blocks.append(f"reasons가 {len(kept)}개로 과소 (최소 {REASONS_MIN})")
    if isinstance(a.get("watch_items"), list):
        a["watch_items"], _ = _filter_list_prose(a["watch_items"], "watch_items", corrections)
    if btype == "kospi":
        inject_kospi_index_levels(a, corrections, warnings)
    sf = a.get("sector_focus")
    if isinstance(sf, dict):
        if isinstance(sf.get("paragraphs"), list):
            kept, _ = _filter_list_prose(sf["paragraphs"], "sector_focus.paragraphs", corrections)
            sf["paragraphs"] = kept
            if not kept:
                blocks.append("sector_focus.paragraphs 전부 제거됨")
        # signal 필드: 30자 이내 한 문장 — 금지 패턴 감지 시 경고만(필수 필드라 제거 불가)
        if isinstance(sf.get("signal"), str):
            bad = find_forbidden(sf["signal"])
            if bad:
                warnings.append(f"sector_focus.signal 금지 패턴 감지 (수동 확인 필요): {bad}")

    # sector_semicon (us 전용) — paragraphs·signal 검증
    ss = a.get("sector_semicon")
    if isinstance(ss, dict):
        if isinstance(ss.get("paragraphs"), list):
            kept, _ = _filter_list_prose(ss["paragraphs"], "sector_semicon.paragraphs", corrections)
            ss["paragraphs"] = kept
        if isinstance(ss.get("signal"), str):
            bad = find_forbidden(ss["signal"])
            if bad:
                warnings.append(f"sector_semicon.signal 금지 패턴 감지 (수동 확인 필요): {bad}")

    # 3-b) telegram_signals — 텔레그램 직송 문자열이므로 모든 타입에서 검증
    if isinstance(a.get("telegram_signals"), list):
        a["telegram_signals"], _ = _filter_list_prose(
            a["telegram_signals"], "telegram_signals", corrections
        )

    # 4) 계층 2 — 스칼라 본문 (금지 문장 제거 후 계속 발행)
    for fld in SCALAR_PROSE.get(btype, []):
        if fld in EXCLUDED_FIELDS:
            continue
        text = a.get(fld)
        if not isinstance(text, str) or not text:
            continue
        bad = find_forbidden(text)
        if not bad:
            continue
        # 금지 패턴을 포함한 문장만 제거
        import re as _re
        sentences = _re.split(r'(?<=[.!?요])\s+', text)
        kept = [s for s in sentences if not find_forbidden(s)]
        if kept:
            a[fld] = " ".join(kept)
            corrections.append(f"본문 '{fld}' 금지 문장 제거: {bad}")
        else:
            # 전체가 금지 패턴인 경우 필드 삭제
            a[fld] = ""
            warnings.append(f"본문 '{fld}' 전체 제거 (금지 패턴 {bad})")

    # 5) 수급 수치 스케일 크로스체크 (kospi-close only)
    if btype == "kospi-close":
        _check_supply_scale(a, latest, warnings)

    return {"analysis": a, "corrections": corrections, "warnings": warnings, "blocks": blocks}


# ── 관리자 알림 ───────────────────────────────────────────────────────────────
def build_block_alert(btype, blocks):
    """차단 알림 메시지. 인용하는 블록 텍스트는 브리핑 산문(<b> 태그·부등호 포함)이라
    반드시 이스케이프한다 — 안 하면 parse_mode=HTML이 400을 뱉고, 하필 가장 알아야 할
    차단 상황에서만 알림이 사라진다(2026-08-24 실사고)."""
    body = "\n".join(f"• {html.escape(str(b))}" for b in blocks)
    return f"🚫 <b>{html.escape(btype)}</b> 브리핑 발행 차단\n{body}"


def send_admin_alert(message):
    """차단 시 관리자 텔레그램으로 알림. 키 미설정이면 조용히 건너뜀(차단은 유지).

    **HTML 실패 시 평문으로 한 번 더 보낸다.** 이 알림의 본문에는 모델이 쓴 산문이
    그대로 들어가는데, 그 산문에 <b> 같은 태그가 섞이고 길이 제한으로 잘리면
    parse_mode=HTML이 400을 뱉는다 — 실제로 2026-08-24·08-26 발행 차단 알림이 둘 다
    이 이유로 실패했고, 그래서 "브리핑이 안 나갔다"는 사실을 아무도 몰랐다.
    가장 중요한 알림이 자기 서식 때문에 죽는 구조라 서식을 포기하더라도 반드시 보낸다.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if not token or not chat_id:
        print("[validate] 관리자 알림 키 미설정 — 알림 건너뜀 (차단은 유지)", file=sys.stderr)
        return

    def _post(text, parse_mode):
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=urllib.parse.urlencode(payload).encode())
        urllib.request.urlopen(req, timeout=10)

    try:
        _post(message, "HTML")
        print("[validate] 관리자 알림 발송 완료", file=sys.stderr)
        return
    except Exception as e:
        detail = ""
        try:                          # HTTPError면 텔레그램이 사유를 본문에 준다
            detail = f" — {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception:
            pass
        print(f"[validate] 관리자 알림 HTML 실패({e}){detail} — 평문으로 재시도",
              file=sys.stderr)

    try:
        _post(strip_tags(message), None)
        print("[validate] 관리자 알림 발송 완료(평문)", file=sys.stderr)
    except Exception as e:
        print(f"[validate] 관리자 알림 실패: {e}", file=sys.stderr)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="분석 결과 검증·교정 게이트")
    parser.add_argument("--type", choices=["kospi", "us", "kospi-close"], required=True)
    args = parser.parse_args()
    btype = args.type

    analysis_path = DATA_DIR / f"analysis_{btype}.json"
    latest_path = DATA_DIR / LATEST_FILE[btype]

    if not analysis_path.exists():
        print(f"[validate] {analysis_path} 없음 — 검증 건너뜀", file=sys.stderr)
        return 0
    analysis = load_json(analysis_path)
    latest = load_json(latest_path) if latest_path.exists() else {}

    result = validate(analysis, latest, btype)

    # 4-b) 선행신호 prior 오버라이드 (kospi 전용) — strong prior가 LLM 방향과 정반대면 재생성
    if btype == "kospi":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from leading_signal import (compute_prior, prior_contradicts_direction,
                                    direction_breaks_prior, prior_side)
        prior = compute_prior(latest)
        llm_dir = (result["analysis"].get("prediction") or {}).get("direction", "")
        # prior 확률이 한쪽(55%↑/45%↓)을 가리키는데 AI 방향이 다르면 그 방향으로 다시 쓰게 한다(§57).
        # strong prior와 정반대인 경우(옛 조건)는 이 조건에 포함되지만, 확률을 못 낸 날을 위해 함께 둔다.
        forced_dir = prior_side(prior) or prior["direction"]
        if direction_breaks_prior(prior, llm_dir) or prior_contradicts_direction(prior, llm_dir):
            print(f"[validate] 🧭 선행신호 오버라이드: LLM '{llm_dir}' ↔ prior '{forced_dir}' "
                  f"(시초가 상승 확률 {prior.get('up_pct')}%, score {prior['score']}) — {forced_dir}로 재생성", file=sys.stderr)
            try:
                regen = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve().parent / "call_claude.py"),
                     "--type", "kospi", "--no-html", "--force-direction", forced_dir],
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                send_admin_alert("⚠️ kospi 방향 오버라이드 재생성 타임아웃(5분) — LLM 방향 유지 발행")
                regen = None
            if regen and regen.returncode == 0:
                analysis = load_json(analysis_path)
                result = validate(analysis, latest, btype)
                new_dir = (result["analysis"].get("prediction") or {}).get("direction", "")
                if forced_dir not in new_dir:
                    send_admin_alert(f"⚠️ kospi 방향 오버라이드 재생성 뒤에도 방향이 '{new_dir}' — prior {forced_dir}와 다른 채 발행")
                send_admin_alert(
                    f"🧭 <b>kospi</b> 방향 오버라이드\n"
                    f"LLM: {llm_dir} → prior: {forced_dir} (시초가 상승 확률 {prior.get('up_pct')}%, 강도 {prior['strength']}, score {prior['score']})\n"
                    f"SOX {prior['signals'].get('sox')} / EWY {prior['signals'].get('ewy')} / VIX {prior['signals'].get('vix')}"
                )
            elif regen is not None:
                send_admin_alert(f"⚠️ kospi 방향 오버라이드 재생성 실패(rc={regen.returncode}) — LLM 방향 {llm_dir} 유지 발행")

    # 4-c) up_pct를 prior 확률 ±10%p 안으로 당긴다(kospi 전용, §57). 방향 재생성이 실패해 AI 방향이 남았으면
    #      숫자만 고치지 않는다 — 방향과 확률이 서로 어긋난 채 나가느니 AI 원본을 그대로 두고 관리자에게 알린다(위 알림).
    if btype == "kospi":
        clamp_prediction_to_prior(result["analysis"], prior, result["corrections"])

    for w in result["warnings"]:
        print(f"[validate] ⚠️  {w}")
    for c in result["corrections"]:
        print(f"[validate] 🔧 교정: {c}")

    if result["blocks"]:
        summary = "\n".join(f"  • {b}" for b in result["blocks"])
        print(f"[validate] 🚫 발행 차단 — 치명적 오류:\n{summary}", file=sys.stderr)
        send_admin_alert(build_block_alert(btype, result["blocks"]))
        return 1

    # 교정본 저장 (교정 사항이 있을 때만 덮어씀)
    if result["corrections"]:
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(result["analysis"], f, ensure_ascii=False, indent=2)
        print(f"[validate] ✓ {len(result['corrections'])}건 교정 후 저장 → {analysis_path}")
    else:
        print("[validate] ✓ 검증 통과 — 교정 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
