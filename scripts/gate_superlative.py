# 지수 최상급 주장(사상 최고 등) 실측 대조와 예측 확률을 선행 신호 범위로 당기는 게이트

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import scripts.superlative_subject as _ss
except ImportError:
    import superlative_subject as _ss
from gate_text import strip_tags
from gate_prose import _INDEX_NAME_SYMBOL


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


def clamp_us_prediction_to_prior(analysis: dict, prior: dict, corrections: list) -> None:
    """미국 up_pct를 S&P 선물 구간표 ±10%p 안으로 당기고 방향은 뒤집지 못하게 한다. 구간표 값이 없으면 두고 넘어간다."""
    from leading_signal import clamp_us_up_pct
    pred = analysis.get("prediction")
    if not isinstance(pred, dict) or (prior or {}).get("up_pct") is None:
        return
    up = pred.get("up_pct")
    fixed = clamp_us_up_pct(up, prior["up_pct"])
    if fixed is None or fixed == up:
        return
    pred["up_pct"], pred["down_pct"] = fixed, 100 - fixed
    corrections.append(f"미국 up_pct {up}% → {fixed}% (S&P 선물 구간표 {prior['up_pct']}% ±10%p 밖)")


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
