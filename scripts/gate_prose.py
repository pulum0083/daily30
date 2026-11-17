# 본문 수치 게이트 — 픽 밖 종목·복기/관전 문장·key_drivers의 등락률을 실측과 대조, 간밤·현직 인물 표기 교정

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_text import _NON_TICKER, _PROSE_FETCH_ALIAS, _US_TICKER_RE, _direction_contradicts, _extract_change_claims, _join_sentences, _sentence_split, _walk_strings, strip_tags
from gate_realdata import _fetch_kospi_realdata, _fetch_us_realdata


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
