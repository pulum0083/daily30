# 뉴스 실측 대조 게이트 — 방향·최상급·지수 레벨이 실측과 반대인 항목, 오래된 촉매 제외

from __future__ import annotations
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import superlative_subject as _ss
from news_gate_grounding import _item_text


# 문자열형 catalyst 맨 앞의 [YYYY-MM-DD] 발생일 접두사 (하위호환 파싱용)
_DATE_PREFIX_RE = re.compile(r"^\s*\[(\d{4})-(\d{2})-(\d{2})\]\s*")


def _parse_iso_date(s: str):
    """'YYYY-MM-DD' → date, 파싱 불가 시 None."""
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# 방향 주장 어휘 — 대상 키워드 근처에 이 표현이 있으면 그 방향을 주장한 것으로 본다.
_UP_WORDS = r"(?:급등|상승|강세|오르|올라|뛰|치솟|반등|돌파|회복|상승세)"
_DOWN_WORDS = r"(?:급락|하락|약세|내리|떨어|밀리|빠지|폭락|급감|하락세|후퇴)"

# 실측 대조 대상 — 키워드 → 실측 스냅샷 키
# 지수는 2026-07-29 실사고로 추가됐다(§28): "나스닥 사상 최고치 경신"(실측 -0.22%)·
# "S&P500 5,500선 돌파"(실측 ~7,4xx)가 방향·레벨 무검증으로 통과했다.
# 긴 이름을 먼저 둬야 "필라델피아 반도체"가 부분 매칭으로 갈리지 않는다.
_REALITY_SUBJECTS = {
    "유가": "oil",
    "국제유가": "oil",
    "WTI": "oil",
    "브렌트": "oil",
    "필라델피아 반도체지수": "sox",
    "필라델피아 반도체": "sox",
    "나스닥": "nasdaq",
    "S&P500": "sp500",
    "S&P 500": "sp500",
    "다우존스": "dow",
    "다우": "dow",
}

# 지수 실측 조회 심볼 (change_pct·현재 레벨을 함께 본다)
_INDEX_SYMBOLS = {"nasdaq": "^IXIC", "sp500": "^GSPC", "dow": "^DJI", "sox": "^SOX"}

# "사상 최고치 경신"처럼 **수치가 없는 정성 최상급 주장**. 등락률 게이트(§22·§24)는
# 인접 숫자가 있어야 발화하므로 이런 주장에 구조적으로 눈이 먼다 — 별도로 잡는다.
_HIGH_SUPERLATIVE_RE = _ss.HIGH_RE
_LOW_SUPERLATIVE_RE = _ss.LOW_RE

# "5,500선"·"5500 포인트"·"5,500 돌파" 형태의 지수 레벨 표기 (3~5자리)
_INDEX_LEVEL_RE = re.compile(r"(\d{1,2}[,]?\d{3})\s*(?:선|포인트|p\b|돌파|회복|안착)")
# "배럴당 78달러" 형태 — 유가는 자릿수가 짧아 위 지수 패턴에 안 걸린다
_PRICE_LEVEL_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*달러")


def _claim_direction(text: str, subject: str) -> str | None:
    """text가 subject에 대해 주장하는 방향("up"/"down")을 뽑는다. 없으면 None.

    subject 등장 위치 기준 앞뒤 25자 안에서만 방향어를 찾는다 — 문장 전체를 훑으면
    "유가 하락으로 항공주 상승"처럼 서로 다른 대상의 방향어가 교차 매칭된다.
    """
    if not text or subject not in text:
        return None
    for m in re.finditer(re.escape(subject), text):
        win = text[max(0, m.start() - 25): m.end() + 25]
        up = re.search(_UP_WORDS, win)
        down = re.search(_DOWN_WORDS, win)
        if up and not down:
            return "up"
        if down and not up:
            return "down"
    return None


def _superlative_claim_wrong(text: str, subject: str, snap: dict) -> str | None:
    """subject에 대한 '사상 최고/최저' 류 주장이 실측과 어긋나면 사유 문자열, 아니면 None.

    2026-07-29 실사고(§28): "나스닥이 사상 최고치를 경신"이 그대로 발행됐는데 실측은
    **-0.22% 하락 마감**이었고 최근 고점 대비로도 한참 아래였다. 이 주장엔 숫자가 하나도
    없어서 등락률 게이트(§22·§24)가 구조적으로 발화할 수 없었다 — 그래서 별도 게이트다.

    판정: 최고 주장인데 (그날 하락했거나 | 최근 고점의 99% 미만) → 틀림. 최저는 대칭.
    52주 고·저를 못 구했으면 등락 방향만으로 판정한다(fail-open 우선).
    """
    if subject not in text:
        return None
    # 최상급마다 같은 문장 안의 주어를 하나만 정한다(§59) — 앞뒤 25자 창은 문장 경계를 넘어
    # "국채금리는 … 최고치를 기록했어요. 이 금리 부담이 다우를…"을 다우의 주장으로 오판했다.
    kinds = {k for n, k in _ss.attributed_superlatives(text, list(_REALITY_SUBJECTS.items()))
             if n == subject}
    chg, level = snap.get("change_pct"), snap.get("level")
    if "high" in kinds:
        if chg is not None and chg < 0:
            return f"'최고' 주장이나 실측 {chg:+.2f}% 하락"
        hi = snap.get("high_52w")
        if level is not None and hi and level < hi * 0.99:
            return f"'최고' 주장이나 실측 {level:,.0f} < 52주 고점 {hi:,.0f}"
    if "low" in kinds:
        if chg is not None and chg > 0:
            return f"'최저' 주장이나 실측 {chg:+.2f}% 상승"
        lo = snap.get("low_52w")
        if level is not None and lo and level > lo * 1.01:
            return f"'최저' 주장이나 실측 {level:,.0f} > 52주 저점 {lo:,.0f}"
    return None


def _level_claim_wrong(text: str, subject: str, snap: dict, tol: float = 0.15) -> str | None:
    """subject 근처에 적힌 지수 레벨이 실측과 tol(기본 ±15%)를 넘게 어긋나면 사유, 아니면 None.

    2026-07-29 실사고(§28): "S&P 500 지수는 0.3% 상승한 5,500선을 돌파" — **등락률은 맞고
    레벨만 틀린** 형태라 방향 게이트를 그대로 통과했다(실측 ~7,4xx, -26%). 학습 시점의
    옛 지수 레벨을 그대로 뱉는 그라운딩 실패의 전형이라, 레벨을 따로 대조한다.
    """
    level = snap.get("level")
    if level is None or subject not in text:
        return None
    # 유가는 자릿수가 짧아(78달러) 지수 패턴에 안 걸리므로 달러 표기도 함께 본다
    pats = (_INDEX_LEVEL_RE, _PRICE_LEVEL_RE) if level < 1000 else (_INDEX_LEVEL_RE,)
    for m in re.finditer(re.escape(subject), text):
        win = text[m.start(): m.end() + 30]
        for pat in pats:
            for lm in pat.finditer(win):
                claimed = float(lm.group(1).replace(",", ""))
                if abs(claimed / level - 1) > tol:
                    return f"레벨 {claimed:,.1f} vs 실측 {level:,.1f}"
    return None


def _drop_reality_contradictions(items: list, real: dict) -> list:
    """실측 시장데이터와 어긋나는 주장을 담은 항목을 제거한다.

    검사 3종 — ① 방향 반대 ② 정성 최상급(사상 최고/최저) 모순 ③ 지수 레벨 이탈.

    2026-07-27 실사고: 미국 브리핑 재수집분이 "국제유가 80달러 돌파 → 에너지 관련주 상승세"·
    "중동 긴장 완화 속 국제유가 상승세 지속"을 냈는데, 실측은 **WTI -6.05%·브렌트 -6.67%**로
    정반대였다(CVX -2.9%, XOM -3.3%). 익명 플레이스홀더 게이트(§25)는 실명이 있어 통과시키고,
    어닝 게이트(§22)는 실적 서사가 아니라 통과시키며, validate_analysis는 call_claude
    **이후**라 이미 서사가 만들어진 뒤다. 그래서 수집 단계에서 잘라낸다.

    2026-07-29 실사고(§28)로 ②③이 추가됐다 — ①만으로는 "나스닥 사상 최고치 경신"(숫자 없음)과
    "S&P500 5,500선 돌파"(방향은 맞고 레벨만 틀림)를 둘 다 놓친다.

    real이 비었거나 값이 없으면 판단하지 않는다(fail-open) — 정상 항목 오제거를 막는다.
    """
    out = []
    for it in items or []:
        text = _item_text(it)
        reason = None
        for subject, key in _REALITY_SUBJECTS.items():
            snap = real.get(key)
            if not snap:
                continue
            # 하위호환: 예전 스냅샷은 등락률 float 하나였다(§27) — dict로 승격해서 받는다
            if isinstance(snap, (int, float)):
                snap = {"change_pct": float(snap), "level": None}
            chg = snap.get("change_pct")
            if chg is not None:
                claimed = _claim_direction(text, subject)
                if claimed and claimed != ("up" if chg > 0 else "down"):
                    reason = f"{subject} 방향 모순(실측 {chg:+.2f}%, 주장 {claimed})"
            reason = reason or _superlative_claim_wrong(text, subject, snap)
            reason = reason or _level_claim_wrong(text, subject, snap)
            if reason:
                print(f"[fetch_news] 실측 모순 제거({subject}: {reason}): {text[:60]}",
                      file=sys.stderr)
                break
        if not reason:
            out.append(it)
    return out


def _fetch_reality_snapshot() -> dict:
    """실측 대조에 쓸 시장 스냅샷. 조회 실패 항목은 None으로 두어 fail-open한다.

    각 키는 {"change_pct":…, "level":…, "high_52w":…, "low_52w":…} 형태다(없는 값은 None).
    """
    real: dict = {}
    try:
        import yfinance as yf
    except Exception as e:                                     # pragma: no cover
        print(f"[fetch_news] yfinance 없음 — 실측 대조 생략: {e}", file=sys.stderr)
        return real

    def _snap(symbol: str, with_52w: bool) -> dict | None:
        h = yf.Ticker(symbol).history(period="1y" if with_52w else "7d")["Close"].dropna()
        if len(h) < 2:
            return None
        last, prev = float(h.iloc[-1]), float(h.iloc[-2])
        s = {"change_pct": round((last / prev - 1) * 100, 2), "level": last,
             "high_52w": None, "low_52w": None}
        if with_52w:
            s["high_52w"], s["low_52w"] = float(h.max()), float(h.min())
        return s

    for key, symbol in [("oil", "CL=F"), *_INDEX_SYMBOLS.items()]:
        try:
            snap = _snap(symbol, with_52w=(key != "oil"))
            if snap:
                real[key] = snap
        except Exception as e:
            print(f"[fetch_news] {key}({symbol}) 실측 조회 실패(대조 생략): {e}", file=sys.stderr)
    return real


def _catalyst_cutoff(briefing_type: str, today: date) -> date:
    """브리핑 타입별 catalyst 허용 시작일(이 날짜 이상만 채택).

    기본은 어제(today-1)다. **코스피 아침 브리핑만 직전 미국장까지 창을 넓힌다** —
    월요일 07:25에 직전 미국장은 지난 금요일이라, 어제(일요일) 기준으로 자르면
    그 브리핑이 실제로 다뤄야 할 금요일 미국장 사건이 통째로 잘려나간다(§24 세션 갭).
    평일에는 직전 미국장 = 어제라 기존 동작과 같다.
    """
    default = today - timedelta(days=1)
    if briefing_type != "kospi":
        return default
    try:
        from session_label import prev_us_session
        prev_us = prev_us_session(today)
    except Exception as e:
        print(f"[fetch_news] session_label 사용 불가, 기본 cutoff 사용: {e}", file=sys.stderr)
        return default
    return min(default, prev_us) if prev_us else default


def _filter_stale_catalysts(catalysts: list, today: date, cutoff: date = None) -> list:
    """catalyst별 발생일을 읽어 오늘/어제(today-1)보다 오래된 사건은 버리고, 남긴 항목은
    순수 문자열(사건 → 영향)로 반환한다. 다운스트림(call_claude)은 문자열 리스트를 기대한다.

    항목 형태 2가지를 모두 받는다:
      · {"date": "YYYY-MM-DD", "text": "사건 → 영향"}  ← US 프롬프트가 요구하는 구조화 형태
      · "사건 → 영향"  또는  "[YYYY-MM-DD] 사건 → 영향"  ← 문자열/인라인 접두사(하위호환)

    2026-07-15~20 실사고: 7/15 발표된 ASML 2분기 실적이 사흘 넘게 '오늘 프리마켓 촉매'로
    재등장했다(_load_prev_catalysts 소프트 중복 방지만으론 못 막음). 이 함수가 하드 게이트다.
    날짜 미상 항목은 버리지 않는다 — 유가·지정학 등 날짜 태그 없이 오는 거시 촉매를 보호한다.
    완전성보다 정합성이 우선이되, '날짜 미상'과 '오래됨'은 구분한다.

    cutoff를 명시하면 그 날짜 이상만 채택한다(코스피 월요일의 주말 공백 — `_catalyst_cutoff`)."""
    if cutoff is None:
        cutoff = today - timedelta(days=1)
    kept, dropped = [], []
    for c in catalysts:
        if isinstance(c, dict):
            text = _item_text(c)
            if not text:
                continue
            ev = _parse_iso_date(c.get("date") or c.get("event_date") or "")
        elif isinstance(c, str):
            m = _DATE_PREFIX_RE.match(c)
            text = _DATE_PREFIX_RE.sub("", c).strip() if m else c.strip()
            ev = _parse_iso_date(f"{m.group(1)}-{m.group(2)}-{m.group(3)}") if m else None
        else:
            continue
        if ev is not None and ev < cutoff:
            dropped.append((text, ev.isoformat()))
        else:
            kept.append(text)  # 최신이거나 날짜 미상 → 유지
    for txt, ev in dropped:
        print(f"[fetch_news] stale catalyst 제외({ev}): {txt}", file=sys.stderr)
    return kept
