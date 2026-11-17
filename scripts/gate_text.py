# 발행 게이트가 함께 쓰는 본문 검사 도우미 — 금지 패턴·수치 추출·문장 나누기·문자열 순회

import re


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
