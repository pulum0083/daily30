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
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

LATEST_FILE = {
    "kospi": "latest_kospi.json",
    "us": "latest_us.json",
    "kospi-close": "latest_kospi_close.json",
}

# 본문 스캔: 타입별 스칼라 필드(위반 시 차단) / 리스트 필드(원소 제거)
SCALAR_PROSE = {
    "kospi-close": ["market_summary", "why", "what", "so_what"],
    "kospi": [],
    "us": [],
}
# 헤드라인은 검사 제외
EXCLUDED_FIELDS = {"reason_title", "market_title"}

# 교정 임계치
PRICE_TOLERANCE = 0.05      # 종목 가격 ±5% 초과 이탈 시 교정
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


def validate_prose_against_picks(analysis: dict, btype: str,
                                  corrections: list, warnings: list, blocks: list) -> None:
    """픽 실측 데이터와 reasons·scenario·watchpoints 산문을 교차검증한다.

    불일치 문장/항목을 제거하고 corrections에 기록.
    kospi-close는 stock_picks가 없으므로 skip.
    """
    if btype == "kospi-close":
        return

    picks = analysis.get("stock_picks")
    if not isinstance(picks, list) or not picks:
        return

    # 픽 실측 테이블 구성 (enrich 완료 후 change_pct가 float로 채워져 있음)
    ticker_real: dict = {}
    name_real: dict = {}
    for p in picks:
        chg = p.get("change_pct")
        if not isinstance(chg, (int, float)):
            continue
        tk = (p.get("ticker") or "").strip().upper()
        nm = (p.get("name") or "").strip()
        if tk:
            ticker_real[tk] = float(chg)
        if nm:
            name_real[nm] = float(chg)
        # 이름에서 짧은 식별자 추출: "AVGO (브로드컴)" → "AVGO", "브로드컴"
        parts = re.split(r'[\s()/·]', nm)
        for part in parts:
            part = part.strip()
            if len(part) >= 2:
                name_real.setdefault(part, float(chg))

    def real_chg_for_text(text: str):
        """텍스트에 언급된 픽 티커/이름을 찾아 실측 change_pct 반환. 없으면 None."""
        t = strip_tags(text)
        for tk, chg in ticker_real.items():
            if tk in t:
                return chg
        for nm, chg in sorted(name_real.items(), key=lambda x: -len(x[0])):
            if nm in t:
                return chg
        return None

    # ── reasons 검증 ──────────────────────────────────────────────
    reasons = analysis.get("reasons")
    if isinstance(reasons, list):
        kept = []
        for item in reasons:
            real = real_chg_for_text(item)
            if real is None:
                kept.append(item)
                continue
            claims = _extract_change_claims(item)
            bad = [c for c in claims if is_contradicted(c, real)]
            if bad:
                corrections.append(
                    f"reasons 항목 제거 (실측 {real:+.2f}% vs 텍스트 {bad}): {item[:60]}"
                )
            else:
                kept.append(item)
        if len(kept) < REASONS_MIN:
            blocks.append(
                f"reasons가 {len(kept)}개로 과소 — prose 교정 후 부족 (최소 {REASONS_MIN})"
            )
        analysis["reasons"] = kept

    # ── 픽 scenario 검증 ──────────────────────────────────────────
    for pick in picks:
        scenario = pick.get("scenario") or ""
        if not scenario:
            continue
        chg = pick.get("change_pct")
        if not isinstance(chg, (int, float)):
            continue
        real = float(chg)
        sentences = _sentence_split(scenario)
        kept_sentences = []
        for sent in sentences:
            claims = _extract_change_claims(sent)
            bad = [c for c in claims if is_contradicted(c, real)]
            if bad:
                corrections.append(
                    f"픽 '{pick.get('name')}' scenario 문장 제거 "
                    f"(실측 {real:+.2f}% vs 텍스트 {bad}): {sent[:60]}"
                )
            else:
                kept_sentences.append(sent)
        new_scenario = _join_sentences(kept_sentences)
        if not new_scenario.strip():
            warnings.append(f"픽 '{pick.get('name')}' scenario 전체 제거됨 — 수동 확인 필요")
        pick["scenario"] = new_scenario

    # ── watchpoints 검증 ─────────────────────────────────────────
    if "watch_items" in analysis and "watchpoints" in analysis:
        warnings.append("watch_items와 watchpoints 키 동시 존재 — watchpoints는 미검증")
    watch_key = "watch_items" if "watch_items" in analysis else "watchpoints"
    watch = analysis.get(watch_key)
    if isinstance(watch, list):
        kept = []
        for item in watch:
            text = item.get("text") or item.get("label") or ""
            real = real_chg_for_text(text)
            if real is None:
                kept.append(item)
                continue
            claims = _extract_change_claims(text)
            bad = [c for c in claims if is_contradicted(c, real)]
            if bad:
                corrections.append(
                    f"watchpoint 항목 제거 (실측 {real:+.2f}% vs 텍스트 {bad}): "
                    f"{item.get('label', '')}"
                )
            else:
                kept.append(item)
        analysis[watch_key] = kept


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


# ── 종목 후보(실측) 수집·매칭 ──────────────────────────────────────────────────
def collect_candidates(latest, btype):
    """latest_*.json에서 {name/ticker → {price, change_pct}} 매칭용 리스트를 모은다."""
    out = []
    keys = ["kospi_candidates"] if btype == "kospi" else (["us_candidates"] if btype == "us" else [])
    for k in keys:
        out.extend(latest.get(k, []) or [])
    # 섹터 대표 종목 (kospi 모닝)
    for sec in (latest.get("sector_stocks") or {}).values():
        out.extend(sec.get("stocks", []) or [])
    return out


def match_candidate(pick, candidates):
    """pick.name/ticker가 후보의 name/ticker를 포함하면 매칭(실측 dict 반환)."""
    name = pick.get("name", "") or ""
    tk = pick.get("ticker", "") or ""
    for c in candidates:
        cn, ct = c.get("name", "") or "", c.get("ticker", "") or ""
        if (cn and (cn in name or cn == tk)) or (ct and (ct in name or ct == tk)):
            if c.get("price") is not None:
                return c
    return None


def _fmt_chg(v):
    return f"{'+' if v >= 0 else ''}{v:.2f}%"


# ── 픽 종목 실측 주입 (yfinance 직접 fetch) ───────────────────────────────────
# Claude는 후보 풀과 무관하게 종목을 자유 선택하므로, 사전 수집된 candidate가
# 대부분 비어 있다. 픽된 종목의 ticker를 직접 fetch해 price·change·MA·sparkline을
# 실측으로 덮어쓰고, generate_html이 읽는 candidate 리스트에도 주입한다.

def _resolve_ticker(pick, btype):
    """pick → 조회용 식별자. 해석 불가 시 빈 문자열.

    - us: 영문 티커(예: NVDA) — yfinance용.
    - kospi: 6자리 종목코드(예: 005930) — 네이버 일봉용. .KS/.KQ 접미사는 붙이지
      않는다. yfinance에 .KS를 붙이면 KOSDAQ 종목이 유령 데이터(하루 stale·오价)를
      반환해 잘못된 가격이 주입되기 때문. 네이버는 코드만으로 시장을 정확히 식별한다.
    """
    tk = (pick.get("ticker") or "").strip()
    name = pick.get("name") or ""
    if btype == "us":
        sym = tk or (name.split("(")[0].strip().split()[0] if name else "")
        # 미국 티커: 영문 대문자 1~5자
        return sym if re.fullmatch(r"[A-Z]{1,5}", sym or "") else ""
    # kospi / kospi-close: 6자리 종목코드 (접미사 없음)
    code = (tk.split(".")[0] if tk else "").strip()
    return code if code.isdigit() and len(code) == 6 else ""


def _inject_candidate(cands, clean_ticker, name, data):
    """generate_html sparkline 매칭용 candidate 항목을 주입/갱신한다."""
    entry = {
        "ticker": clean_ticker,
        "name": name,
        "price": data["price"],
        "change_pct": data["change_pct"],
        "ma20_dist_pct": data.get("ma20_dist_pct"),
        "ma200_dist_pct": data.get("ma200_dist_pct"),
        "sparkline": data.get("sparkline", []),
        "ma20_sparkline": data.get("ma20_sparkline", []),
        "ma200_sparkline": data.get("ma200_sparkline", []),
    }
    for i, c in enumerate(cands):
        if c.get("ticker") == clean_ticker or c.get("name") == name:
            cands[i] = entry
            return
    cands.append(entry)


def _closes_to_realdata(closes, ndigits):
    """일봉 종가 리스트(오래된→최신)로 실측 dict를 만든다.
    '전일 등락률' = close[-1] vs close[-2] (실시간 장중가 아님).
    """
    if len(closes) < 2:
        return {"error": "insufficient data"}
    price, prev = closes[-1], closes[-2]
    r = (lambda v: round(v, ndigits))
    out = {
        "price": r(price),
        "change_pct": round((price - prev) / prev * 100, 4),
        "sparkline": [r(x) for x in closes[-20:]],
    }

    def _ma_series(window):
        # 마지막 20개 지점의 이동평균(데이터 부족 시 윈도우 clamp)
        return [sum(closes[max(0, i - window + 1):i + 1]) / len(closes[max(0, i - window + 1):i + 1])
                for i in range(len(closes) - 20, len(closes))]

    if len(closes) >= 20:
        ma20 = _ma_series(20)
        out["ma20_dist_pct"] = round((price - ma20[-1]) / ma20[-1] * 100, 2)
        out["ma20_sparkline"] = [r(v) for v in ma20]
    if len(closes) >= 200:
        ma200 = _ma_series(200)
        out["ma200_dist_pct"] = round((price - ma200[-1]) / ma200[-1] * 100, 2)
        out["ma200_sparkline"] = [r(v) for v in ma200]
    return out


def _closes_from_toss_candles(candles: list, ndigits: int) -> dict:
    """Toss 캔들 리스트(오래된→최신)에서 실측 dict를 만든다."""
    closes = [float(c["closePrice"]) for c in candles if c.get("closePrice")]
    result = _closes_to_realdata(closes, ndigits)
    # vol_mult: 최신 거래량 / 직전 20일 평균 (tradingVolume 필드가 있을 때만)
    volumes = [float(c["tradingVolume"]) for c in candles if c.get("tradingVolume")]
    if len(volumes) >= 2:
        avg20 = sum(volumes[max(0, len(volumes) - 21):-1]) / min(20, len(volumes) - 1)
        if avg20 > 0:
            result["vol_mult"] = round(volumes[-1] / avg20, 1)
    return result


def _fetch_us_realdata(ticker):
    """미국 종목 실측. Toss 캔들 우선, 실패 시 yfinance 폴백."""
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
                return _closes_from_toss_candles(candles, ndigits=4)
        except Exception:
            pass

    # 2) yfinance 폴백
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="300d").dropna(subset=["Close"])
        closes = [float(x) for x in hist["Close"].tolist()]
        return _closes_to_realdata(closes, ndigits=4)
    except Exception as e:
        return {"error": str(e)}


def _fetch_kospi_realdata(code):
    """한국 종목 실측 (6자리 코드). Toss 캔들 우선, 실패 시 네이버 폴백."""
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
            candles = tc.get_candles(code, interval="1d", count=300)
            if candles:
                return _closes_from_toss_candles(candles, ndigits=2)
        except Exception:
            pass

    # 2) 네이버 일봉 폴백
    import urllib.request
    from datetime import datetime, timedelta
    try:
        end = datetime.now().strftime("%Y%m%d") + "0000"
        start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d") + "0000"
        url = (f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
               f"?startDateTime={start}&endDateTime={end}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read())
        closes = [float(rw["closePrice"]) for rw in rows if rw.get("closePrice")]
        return _closes_to_realdata(closes, ndigits=2)
    except Exception as e:
        return {"error": str(e)}


def _fetch_pick_realdata(ticker, is_us):
    """픽 종목 실측 fetch. 미국·한국 모두 Toss 우선, 폴백 포함."""
    return _fetch_us_realdata(ticker) if is_us else _fetch_kospi_realdata(ticker)


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


def enrich_picks_with_realdata(analysis, latest, btype, corrections, warnings):
    """픽된 종목의 실측 데이터를 fetch해 analysis·latest(candidate)에 주입한다.
    Returns: latest가 변경됐는지(bool).
    """
    picks = analysis.get("stock_picks")
    if not isinstance(picks, list) or not picks:
        return False
    if btype not in ("kospi", "us"):
        return False

    is_us = btype == "us"
    cand_key = "us_candidates" if is_us else "kospi_candidates"
    cands = latest.setdefault(cand_key, [])
    changed = False

    for p in picks:
        tk = _resolve_ticker(p, btype)
        if not tk:
            warnings.append(f"종목 '{p.get('name')}' 티커 해석 실패 — 실측 주입 생략")
            continue
        data = _fetch_pick_realdata(tk, is_us)
        if "error" in data or data.get("price") is None:
            warnings.append(f"종목 '{p.get('name')}'({tk}) 실측 fetch 실패: {data.get('error', 'no price')}")
            continue

        price, chg = data["price"], data["change_pct"]
        old_chg = p.get("change")
        p["price"] = f"${price:,.2f}" if is_us else f"{int(round(price)):,}원"
        p["change"] = _fmt_chg(chg)
        p["change_cls"] = "up" if chg >= 0 else "down"
        if data.get("ma200_dist_pct") is not None:
            p["ma200_dist_pct"] = data["ma200_dist_pct"]
        if data.get("ma20_dist_pct") is not None:
            p["ma20_dist_pct"] = data["ma20_dist_pct"]
        if data.get("vol_mult") is not None:
            p["vol_mult"] = data["vol_mult"]

        _inject_candidate(cands, tk, p.get("name", ""), data)
        changed = True
        corrections.append(
            f"종목 '{p.get('name')}'({tk}) 실측 주입: change {old_chg} → {p['change']}, price {p['price']}"
        )

    return changed


def correct_pick_price(pick, gt, corrections, is_us=False):
    """pick 가격이 실측과 ±5% 초과 이탈하면 price·change·entry/target/stop를 교정.

    is_us는 btype에서 직접 전달받는다. Claude 원본 가격 문자열('$' 유무)로
    판정하면 '$' 없는 미국 가격 형식("130달러" 등)에서 오판할 수 있다.
    """
    cur = parse_price(pick.get("price"))
    gt_price = gt.get("price")
    if cur is None or not gt_price or cur <= 0:
        return
    if abs(cur - gt_price) / gt_price <= PRICE_TOLERANCE:
        return

    new_price = f"${gt_price:,.2f}" if is_us else f"{int(round(gt_price)):,}원"
    ratio = gt_price / cur

    old = pick.get("price")
    pick["price"] = new_price
    chg = gt.get("change_pct")
    if chg is not None:
        pick["change"] = _fmt_chg(chg)
        pick["change_cls"] = "up" if chg >= 0 else "down"

    # 진입/목표/손절: 같은 비율로 스케일 (파싱 가능할 때만)
    for fld in ("entry", "target", "stop"):
        raw = pick.get(fld)
        v = parse_price(raw)
        if v is not None and isinstance(raw, str):
            scaled = v * ratio
            pick[fld] = f"${scaled:,.2f}" if is_us else f"{int(round(scaled)):,}원"

    corrections.append(f"종목 '{pick.get('name')}' 가격 교정: {old} → {new_price} (실측 대비 교차검증)")


def forbidden_in_pick(pick):
    """stock_pick의 서술형 본문(scenario·action_guide)에서 금지 패턴 탐지."""
    bad = []
    for fld in ("scenario", "action_guide"):
        bad.extend(find_forbidden(pick.get(fld)))
    return bad


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


# ── 검증 본체 ─────────────────────────────────────────────────────────────────
def validate(analysis, latest, btype):
    """analysis를 검증·교정한다.

    Returns dict: {analysis(교정본), corrections[], warnings[], blocks[]}
    blocks 비어있지 않으면 발행 차단.
    """
    a = copy.deepcopy(analysis)
    corrections, warnings, blocks = [], [], []

    # 1) 구조 필드 — 예측형 브리핑(kospi/us)만. 마감(kospi-close)은 예측 필드가 없는 시황 요약이라 제외.
    if btype in ("kospi", "us"):
        pred = a.get("prediction") or {}
        up = pred.get("up_pct")
        if not isinstance(up, (int, float)) or isinstance(up, bool) or not (0 <= up <= 100):
            blocks.append(f"prediction.up_pct 비정상: {up!r}")
        if not pred.get("direction"):
            blocks.append("prediction.direction 누락")

    # 2) 계층 1 + stock_picks 본문
    picks = a.get("stock_picks")
    is_us = btype == "us"
    if isinstance(picks, list) and picks:
        cands = collect_candidates(latest, btype)
        kept = []
        for p in picks:
            bad = forbidden_in_pick(p)
            if bad:
                corrections.append(f"종목 '{p.get('name')}' 제거: {bad}")
                continue
            gt = match_candidate(p, cands)
            if gt:
                correct_pick_price(p, gt, corrections, is_us=is_us)
            else:
                warnings.append(f"종목 '{p.get('name')}' 실측 매칭 실패 — 가격 교차검증 생략")
            kept.append(p)
        if not kept:
            blocks.append("stock_picks 전부 제거됨 (브리핑 빈약)")
        a["stock_picks"] = kept

    # 2-b) 산문 교차검증 — 픽 실측 vs reasons·scenario·watchpoints
    if btype in ("kospi", "us"):
        validate_prose_against_picks(a, btype, corrections, warnings, blocks)

    # 2-c) 산문 교차검증 — 픽 외 개별 종목 방향 모순 (us 전용)
    if btype == "us":
        validate_prose_nonpick_stocks(a, btype, corrections, warnings)

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
def send_admin_alert(message):
    """차단 시 관리자 텔레그램으로 알림. 키 미설정이면 조용히 건너뜀(차단은 유지)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if not token or not chat_id:
        print("[validate] 관리자 알림 키 미설정 — 알림 건너뜀 (차단은 유지)", file=sys.stderr)
        return
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat_id, "text": message, "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=10)
        print("[validate] 관리자 알림 발송 완료", file=sys.stderr)
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

    # 0) 픽 종목 실측 주입 (yfinance 직접 fetch — 깨진/빈약한 candidate 풀 우회)
    pre_corrections, pre_warnings = [], []
    latest_changed = enrich_picks_with_realdata(
        analysis, latest, btype, pre_corrections, pre_warnings
    )
    if latest_changed and latest_path.exists():
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(latest, f, ensure_ascii=False, indent=2)
        print(f"[validate] ✓ candidate 실측 주입 후 저장 → {latest_path}")

    result = validate(analysis, latest, btype)

    # 4-b) 선행신호 prior 오버라이드 (kospi 전용) — strong prior가 LLM 방향과 정반대면 재생성
    if btype == "kospi":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from leading_signal import compute_prior, prior_contradicts_direction
        prior = compute_prior(latest)
        llm_dir = (result["analysis"].get("prediction") or {}).get("direction", "")
        if prior_contradicts_direction(prior, llm_dir):
            print(f"[validate] 🧭 선행신호 오버라이드: LLM '{llm_dir}' ↔ strong prior '{prior['direction']}' "
                  f"(score {prior['score']}) — {prior['direction']}로 재생성", file=sys.stderr)
            regen = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "call_claude.py"),
                 "--type", "kospi", "--no-html", "--force-direction", prior["direction"]],
            )
            if regen.returncode == 0:
                analysis = load_json(analysis_path)
                result = validate(analysis, latest, btype)
                send_admin_alert(
                    f"🧭 <b>kospi</b> 방향 오버라이드\n"
                    f"LLM: {llm_dir} → prior: {prior['direction']} (강도 strong, score {prior['score']})\n"
                    f"SOX {prior['signals'].get('sox')} / EWY {prior['signals'].get('ewy')} / VIX {prior['signals'].get('vix')}"
                )
            else:
                send_admin_alert(f"⚠️ kospi 방향 오버라이드 재생성 실패(rc={regen.returncode}) — LLM 방향 {llm_dir} 유지 발행")

    result["corrections"] = pre_corrections + result["corrections"]
    result["warnings"] = pre_warnings + result["warnings"]

    for w in result["warnings"]:
        print(f"[validate] ⚠️  {w}")
    for c in result["corrections"]:
        print(f"[validate] 🔧 교정: {c}")

    if result["blocks"]:
        summary = "\n".join(f"  • {b}" for b in result["blocks"])
        print(f"[validate] 🚫 발행 차단 — 치명적 오류:\n{summary}", file=sys.stderr)
        send_admin_alert(
            f"🚫 <b>{btype}</b> 브리핑 발행 차단\n"
            + "\n".join(f"• {b}" for b in result["blocks"])
        )
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
