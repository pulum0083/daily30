# 뉴스 실적 게이트 — 오래된 실적·이미 발표된 실적의 예고 기사 제외(주어 종목 기준)

from __future__ import annotations
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from news_common import KST
from news_gate_history import _GENERIC_UPPER, _norm_for_match
from news_gate_grounding import _item_text


_EARNINGS_KEYWORDS = ("실적", "어닝", "earnings", "eps", "매출", "순이익",
                      "가이던스", "guidance", "분기", "컨퍼런스콜", "실적 발표")


def _is_earnings_catalyst(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in _EARNINGS_KEYWORDS)


def _parse_tickers(ticker_field) -> list:
    """catalyst의 ticker 필드(문자열/리스트)에서 유효 티커(1~5자 라틴)만 추출."""
    if isinstance(ticker_field, list):
        raw = " ".join(str(x) for x in ticker_field)
    else:
        raw = str(ticker_field or "")
    return [t for t in re.findall(r"[A-Za-z]{1,5}", raw.upper())
            if t not in _GENERIC_UPPER]


_earnings_age_cache: dict = {}

# 야후 실적 기록은 발표 직후 며칠 동안 이번 발표를 싣지 않는다(2026-11-18 실사고: 엔비디아가 11/17 장 마감 뒤
# 실적을 냈는데 기록의 마지막 발표는 8/26 — '84일 전 실적'으로 판정돼, 찾았더라도 진짜 기사가 지워졌을 것이다).
# 같은 시각 야후 일정(calendar)은 다음 발표일을 11/18로 적고 있었다. 기록이 한 분기 가까이 묵었는데 일정상
# 발표일이 오늘 언저리면 '야후가 아직 못 실은 것'으로 보고 방금 발표로 친다. 41일 지난 마이크론(§31)처럼
# 다음 발표가 한참 뒤인 진짜 옛 실적은 그대로 걸러진다.
_VENDOR_LAG_MIN_AGE = 60          # 기록상 직전 발표가 이보다 오래돼야 '기록이 밀렸을 수 있다'로 본다
_CAL_NEAR_BEFORE, _CAL_NEAR_AFTER = 3, 1   # 일정상 발표일이 오늘 기준 [-3일, +1일] 안이면 방금 발표로 본다


def _vendor_lag_age(age, calendar_dates, today: date):
    """기록 나이(age)를 일정(calendar_dates)으로 보정한다. 보정하면 0(방금 발표), 아니면 age 그대로."""
    if age is not None and age < _VENDOR_LAG_MIN_AGE:
        return age
    for d in calendar_dates or []:
        if -_CAL_NEAR_AFTER <= (today - d).days <= _CAL_NEAR_BEFORE:
            return 0
    return age


def _calendar_earnings_dates(ticker: str) -> list:
    """야후 일정(calendar)의 'Earnings Date' — 실패하면 빈 목록."""
    try:
        import yfinance as yf
        raw = (yf.Ticker(ticker).calendar or {}).get("Earnings Date") or []
        return [d if isinstance(d, date) and not isinstance(d, datetime) else d.date() for d in raw]
    except Exception as e:
        print(f"[fetch_news] 실적 일정 조회 실패({ticker}): {e}", file=sys.stderr)
        return []


def _days_since_last_earnings(ticker: str, today: date):
    """yfinance로 ticker의 '가장 최근 과거 실적 발표일'을 조회해 today와의 일수 차를 반환.
    조회 실패·데이터 없음이면 None(검증 불가 → 상위 로직이 '유지'로 판단).
    기록이 묵었는데 일정상 발표가 오늘 언저리면 0을 돌려준다(_vendor_lag_age)."""
    if ticker in _earnings_age_cache:
        return _earnings_age_cache[ticker]
    age = None
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).get_earnings_dates(limit=12)
        if df is not None and not df.empty:
            past = [d.date() for d in df.index if getattr(d, "tzinfo", None) and d.date() <= today]
            if past:
                age = (today - max(past)).days
    except Exception as e:
        print(f"[fetch_news] 어닝일 조회 실패({ticker}): {e}", file=sys.stderr)
    if age is None or age >= _VENDOR_LAG_MIN_AGE:
        fixed = _vendor_lag_age(age, _calendar_earnings_dates(ticker), today)
        if fixed != age:
            print(f"[fetch_news] {ticker} 실적 기록이 밀림(직전 {age}일 전) — 일정상 발표가 오늘 언저리라 방금 발표로 본다",
                  file=sys.stderr)
            age = fixed
    _earnings_age_cache[ticker] = age
    return age


# 뉴스 텍스트에 한글/영문 사명으로만 언급된 회사를 티커로 resolve — Gemini 문자열 catalyst엔
# ticker 필드가 없어 어닝 캘린더 검증이 건너뛰어지던 구멍을 막는다(2026-07-22 '엔비디아 실적 발표'
# 실사고: NVIDIA는 7월 하순에 실적이 없는데 Gemini가 오늘 촉매로 소환, ticker 필드가 없어 통과).
# yfinance 어닝 조회가 신뢰 가능한 미국 대형주만 등록(국내주는 .KS 어닝이 불안정 → 미등록=fail-open).
_NAME_TO_TICKER = {
    "엔비디아": "NVDA", "nvidia": "NVDA",
    "애플": "AAPL",
    "마이크로소프트": "MSFT",
    "아마존": "AMZN",
    "메타": "META",
    "알파벳": "GOOGL", "구글": "GOOGL",
    "테슬라": "TSLA",
    "마이크론": "MU", "micron": "MU",
    "브로드컴": "AVGO",
    "인텔": "INTC",
    "퀄컴": "QCOM",
    "넷플릭스": "NFLX",
    "오라클": "ORCL",
    "세일즈포스": "CRM",
    "어도비": "ADBE",
    "asml": "ASML",
    "tsmc": "TSM", "대만반도체": "TSM",
    "제이피모건": "JPM", "jp모건": "JPM", "jpmorgan": "JPM",
    "골드만삭스": "GS",
    "모건스탠리": "MS",
    "뱅크오브아메리카": "BAC",
    "씨티그룹": "C",
    "웰스파고": "WFC",
    "블랙록": "BLK",
}
_NAME_TO_TICKER_NORM = {_norm_for_match(k): v for k, v in _NAME_TO_TICKER.items()}


def _resolve_company_tickers(text: str) -> list:
    """뉴스 텍스트에 언급된 (매핑된) 회사명을 티커 리스트로 변환. 등장 회사만, 중복 제거."""
    t = _norm_for_match(text)
    out = []
    for name_norm, ticker in _NAME_TO_TICKER_NORM.items():
        if name_norm and name_norm in t and ticker not in out:
            out.append(ticker)
    return out


# 프롬프트가 요구하는 catalyst 형식이 "사건 → 영향"이므로, 화살표 왼쪽이 사건의 주어다.
_ARROW_RE = re.compile(r"\s*(?:→|->|⇒|=>)\s*")
_PAREN_TICKER_RE = re.compile(r"\(([A-Z]{1,5})(?:[,\s]|\))")


def _earnings_subject_tickers(text: str, ticker_field="") -> list:
    """실적 주장의 **주어** 티커만 뽑는다.

    2026-08-04 실사고: "마이크론(MU)의 3분기 실적 예상치 상회 → 프리마켓에서 반도체
    관련주(AMD, QCOM) 강세"의 ticker 필드가 "MU,AMD,QCOM"이었는데, 마침 **AMD가 그날
    실적을 발표**해 "여러 티커 중 하나라도 최근이면 유지" 규칙에 걸렸다. 그래서 41일 전
    (2026-06-24)에 발표된 마이크론 실적이 '오늘의 촉매'로 통과했다. 같은 날조가
    headlines(순수 문자열, ticker 필드 없음)에서는 MU만 잡혀 정상 제외됐다 —
    **ticker 필드에 영향 종목까지 섞여 들어온 것이 게이트를 무력화한 것**이다.

    ticker 필드는 사건 주체와 영향 종목을 구분하지 않으므로 주어 판정에 쓸 수 없다.
    화살표가 없어 주어를 특정할 수 없으면 기존 동작(전체 티커)으로 fail-open한다.
    """
    if _ARROW_RE.search(text or ""):
        cause = _ARROW_RE.split(text, 1)[0]
        # 산문에서는 티커가 괄호 안에 온다. 맨 문자열 스캔은 "JP모건"의 "JP"처럼
        # 사명 앞머리를 티커로 오인하므로 쓰지 않는다.
        paren = [t for t in _PAREN_TICKER_RE.findall(cause) if t not in _GENERIC_UPPER]
        subj = list(dict.fromkeys(paren + _resolve_company_tickers(cause)))
        if subj:
            return subj
    return list(dict.fromkeys(_parse_tickers(ticker_field) + _resolve_company_tickers(text)))


def _drop_stale_earnings(catalysts: list, today: date, max_age_days: int = 2,
                         age_fn=None) -> list:
    """실적형 catalyst 중, 티커의 실제 최근 발표일이 max_age_days를 초과한 것을 제외.

    - 실적형이 아니면(거시·지정학·제품 등) 검증하지 않고 유지.
    - 티커가 없거나 조회 실패면 검증 불가 → 유지(과잉 제외 방지, 교차일 게이트가 백스톱).
    - 여러 티커 중 하나라도 최근(≤max_age_days) 발표면 신선한 실적으로 보고 유지.
    catalysts 항목은 {date,text,ticker} dict 또는 문자열. 반환 shape는 입력과 동일."""
    age_fn = age_fn or _days_since_last_earnings
    kept = []
    for c in catalysts:
        text = _item_text(c)
        ticker_field = c.get("ticker", "") if isinstance(c, dict) else ""
        if not _is_earnings_catalyst(text):
            kept.append(c)
            continue
        # 사건의 **주어** 티커만 검증한다 — 영향 종목(방관자)이 마침 오늘 실적을 냈다는
        # 이유로 몇 주 된 실적 주장이 통과하던 구멍을 막는다(2026-08-04 실사고).
        tickers = _earnings_subject_tickers(text, ticker_field)
        if not tickers:
            kept.append(c)  # 검증 불가 → 유지
            continue
        ages = [a for a in (age_fn(t, today) for t in tickers) if a is not None]
        if not ages:
            kept.append(c)  # 전부 조회 실패 → 유지
            continue
        if min(ages) > max_age_days:
            print(f"[fetch_news] stale 실적 제외(최근 발표 {min(ages)}일 전 > {max_age_days}): {text}",
                  file=sys.stderr)
        else:
            kept.append(c)
    return kept


# 발표 전 시점의 표현 — "곧 나온다"고 말하는 문장. '전망'·'기대'는 결과 기사에도 흔해
# ("가이던스 전망 상향") 넣지 않는다.
_PREVIEW_RE = re.compile(
    r"임박|앞두고|앞둔|앞서|발표\s*예정|예정된|예정이|발표\s*전|발표를\s*기다|대기"
    r"|ahead of|preview|to report|will report|set to report|expected to report|before .{0,20}earnings",
    re.IGNORECASE,
)

_release_cache: dict = {}


def _last_earnings_release(ticker: str, now: datetime):
    """ticker의 가장 최근 실적 발표 **시각**(tz-aware) 중 now 이전인 것. 실패·없음이면 None.

    날짜가 아니라 시각으로 본다 — 미국 실적은 장 마감 뒤(16:00 ET = 다음 날 05:00 KST)에
    나오므로, 날짜로 비교하면 KST 기준 '오늘 새벽'에 나온 실적을 하루 어긋나게 판정한다(§29).
    """
    if ticker in _release_cache:
        return _release_cache[ticker]
    out = None
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).get_earnings_dates(limit=8)
        if df is not None and not df.empty:
            past = [d.to_pydatetime() for d in df.index
                    if getattr(d, "tzinfo", None) and d.to_pydatetime() <= now]
            if past:
                out = max(past)
    except Exception as e:
        print(f"[fetch_news] 실적 발표 시각 조회 실패({ticker}): {e}", file=sys.stderr)
    _release_cache[ticker] = out
    return out


def _drop_preview_after_release(items: list, now: datetime, window_days: int = 7,
                                release_fn=None) -> list:
    """이미 발표된 실적을 '발표 임박·앞두고'로 쓴 항목을 뺀다.

    2026-10-01 실사고: 마이크론 실적은 05:00 KST에 나왔는데 21:17 미국 브리핑이 00:00에
    발행된 예고 기사("마이크론 실적 발표 임박")를 골라 '오늘의 분수령'으로 서술했다.
    기사 자체는 쓰인 시점엔 맞았지만 브리핑 시점엔 이미 지난 일이다. stale 게이트
    (`_drop_stale_earnings`)는 오래된 실적을 오늘 일로 쓰는 것만 막아 이 경우를 못 잡는다.

    판정: 실적형 + 예고형 표현 + 주어 종목의 최근 발표 시각이 now 이전이고 window_days 안.
    창을 두는 이유 — 직전 발표가 석 달 전이면 그 예고는 다음 분기 실적 이야기라 맞을 수 있다.
    발표 시각을 못 읽으면 판단하지 않는다(fail-open). 반환 shape는 입력과 같다.
    """
    release_fn = release_fn or _last_earnings_release
    kept = []
    for it in items:
        text = _item_text(it)
        # RSS 경로는 LLM이 다시 쓴 문장에서 '임박'이 빠질 수 있어 원문 기사 제목도 함께 본다.
        article = it.get("article") if isinstance(it, dict) else None
        blob = f"{text} {(article or {}).get('title', '')}"
        if not (_is_earnings_catalyst(blob) and _PREVIEW_RE.search(blob)):
            kept.append(it)
            continue
        ticker_field = it.get("ticker", "") if isinstance(it, dict) else ""
        released = []
        for t in _earnings_subject_tickers(text, ticker_field) or _resolve_company_tickers(blob):
            r = release_fn(t, now)
            if r is not None and timedelta(0) <= now - r <= timedelta(days=window_days):
                released.append(f"{t} {r.astimezone(KST):%m-%d %H:%M} KST")
        if released:
            print(f"[fetch_news] 이미 발표된 실적의 예고 기사 제외({', '.join(released)}): {text[:80]}",
                  file=sys.stderr)
        else:
            kept.append(it)
    return kept
