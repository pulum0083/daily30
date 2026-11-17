# 시점·세션 게이트 — 끝난 이벤트의 예고형, 오늘/내일 표기, 프리마켓 지수, 미국 이슈 카드 실측 대조

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_text import _collect_strings, _walk_strings, strip_tags
from gate_superlative import _SUPERLATIVE_LIST_FIELDS


# ── 이미 끝난 경제 이벤트의 예고형 서술 (2026-07-30 실사고 §29) ──────────────
# 03:00 KST FOMC가 07:25 코스피·21:15 미국 브리핑에서 모두 "예정"으로 나갔다.
# 캘린더 소스가 actual을 안 채워 모델에겐 모든 이벤트가 미발표로 보였던 게 원인이고,
# 이 게이트는 프롬프트 지시가 새더라도 발행 직전에 잡는 최종 방어선이다.
_PREVIEW_TENSE_RE = re.compile(
    r"(예정|앞두고|앞둔|대기|유력|기다리|나올\s*것|발표를\s*앞|관망)"
)
# 제목에서 뽑아낼 한글 본문용 키워드 — 대문자 약어는 한국어 기사에 그대로 쓰인다.
_EVENT_ACRONYM_RE = re.compile(r"\b([A-Z]{3,5})\b")


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


_ISSUE_FALL_NOW = re.compile(r"(밀리|눌리|내리|빠지|떨어지|하락하|약세를? 보이)고 있|(눌려|밀려|빠져|떨어져) 있|(밀려|눌려|내려|빠져|떨어져)요")
_ISSUE_RISE_NOW = re.compile(r"(오르|뛰|상승하|반등하|강세를? 보이)고 있|(올라|뛰어) 있|(올라|뛰어)요")
_ISSUE_MIN_MOVE = 0.5       # 프리마켓 등락 중앙값이 이만큼은 벌어져야 반대라고 본다(%)


def _premarket_opposite(side: dict, sign: int, changes: dict):
    """영향 종목 실측이 sign 쪽으로 움직였으면 [(티커, 등락)]을 큰 순으로, 아니면 None. 2종목 이상 잰 경우만 본다."""
    moved = [(t, changes[t]) for t in (side.get("tickers") or []) if isinstance(changes.get(t), (int, float))]
    if len(moved) < 2:
        return None
    opp = [(t, v) for t, v in moved if v * sign > 0]
    vals = sorted(v * sign for _, v in moved)
    if len(opp) * 3 < len(moved) * 2 or vals[len(vals) // 2] < _ISSUE_MIN_MOVE:
        return None
    return sorted(opp, key=lambda x: -abs(x[1]))


def fix_issue_premarket_contradictions(analysis, latest, corrections) -> int:
    """이슈가 지금 일처럼 쓴 방향이 프리마켓 실측과 반대면 고친다(미국 브리핑, 2026-11-03 실사고).

    11/3 "메모리·장비주 전반이 눌리고 있어요" — 21:16 실측은 MU +2.57%·AMD +2.31%·LRCX +3.12%였다. 어제 기사를 지금
    일처럼 옮긴 것이다. 본문은 실측만 담은 문장으로 바꾸고, 제목까지 그렇게 쓴 이슈는 뺀다. "밀렸어요"처럼 지난 일로
    쓴 문장은 어제 정규장 얘기일 수 있어 건드리지 않는다.
    """
    changes = {c.get("ticker"): c.get("change_pct") for c in (latest.get("us_candidates") or []) if isinstance(c, dict)}
    fixed = 0
    kept = []
    for it in analysis.get("issues") or []:
        if not isinstance(it, dict):
            kept.append(it)
            continue
        drop = False
        for key, sign, now_re, word in (("down", 1, _ISSUE_FALL_NOW, "오르고"), ("up", -1, _ISSUE_RISE_NOW, "내리고")):
            side = it.get(key)
            if not isinstance(side, dict):
                continue
            title, body = str(it.get("title") or ""), str(it.get("body") or "")
            if not (now_re.search(title) or now_re.search(body)):
                continue
            opp = _premarket_opposite(side, sign, changes)
            if not opp:
                continue
            fixed += 1
            if now_re.search(title):
                drop = True
                corrections.append(f"이슈 제거 — 제목이 프리마켓 실측과 반대: {title[:30]}")
                break
            shown = "·".join(f"{t} {v:+.1f}%" for t, v in opp[:3])
            it["body"] = f"발행 시점 프리마켓에선 {shown}로 {word} 있어요."
            corrections.append(f"이슈 본문 교정 — 프리마켓 실측과 반대: {title[:30]}")
            break
        if not drop:
            kept.append(it)
    if fixed:
        analysis["issues"] = kept
    return fixed


_ISSUE_ROSE_PAST = re.compile(r"올랐|웃었|뛰었|상승했|반등했|강세를? 보였")
_ISSUE_FELL_PAST = re.compile(r"내렸|눌렸|눌린|밀렸|밀린|빠졌|떨어졌|하락했|급락했|약세를? 보였")


def _prev_us_session_str(analysis) -> str:
    """이 브리핑이 말하는 직전 미국장 날짜(YYYY-MM-DD). 발행 시각을 못 읽으면 빈 값."""
    from datetime import date as _date
    from session_label import prev_us_session
    try:
        s = prev_us_session(_date.fromisoformat(str(analysis.get("generated_at") or "")[:10]))
    except ValueError:
        return ""
    return s.isoformat() if s else ""


def drop_stale_earnings_issues(analysis, corrections, age_fn=None, max_age_days=4) -> int:
    """미국 이슈 중 실적을 '지금 일'로 쓴 카드인데, 붙은 티커의 최근 실적 발표가 max_age_days보다 오래됐으면 뺀다.

    2026-11-10 실사고 — "맥도날드 실적 호조로 소비재 안도감 확산"이 실렸는데 맥도날드 실적은 11/4(6일 전)였다.
    수집 단계 게이트(fetch_news._drop_stale_earnings)는 회사 이름을 티커로 바꾸는 이름표(_NAME_TO_TICKER)에
    기대는데 맥도날드가 없어 검사 없이 통과했다. 이슈 카드는 언제나 ▲▼ 티커를 갖고 있으니 여기서 한 번 더 본다.
    - 실적·어닝·가이던스를 말하지 않는 카드, 발표 전 예고(앞두고·예정·임박 등)는 건드리지 않는다.
    - 티커 중 하나라도 최근 발표면 둔다(관대한 쪽 — 발행 직전 게이트의 오탐은 이슈 하나를 잃는다).
    - 발표일을 하나도 못 읽으면 판단하지 않는다(fail-open).
    max_age_days=4: 목요일 장 마감 뒤 발표 → 다음 월요일 브리핑까지가 4일이다.
    """
    from datetime import date as _date
    issues = analysis.get("issues")
    if not isinstance(issues, list) or not issues:
        return 0
    try:
        today = _date.fromisoformat(str(analysis.get("generated_at") or "")[:10])
    except ValueError:
        return 0
    import fetch_news as _fn
    age_fn = age_fn or _fn._days_since_last_earnings
    kept, dropped = [], []
    for it in issues:
        if not isinstance(it, dict):
            kept.append(it)
            continue
        blob = f"{it.get('title') or ''} {it.get('body') or it.get('text') or ''}"
        if not _fn._is_earnings_catalyst(blob) or _fn._PREVIEW_RE.search(blob):
            kept.append(it)
            continue
        tickers = []
        for side in ("up", "down"):
            sd = it.get(side)
            if isinstance(sd, dict):
                tickers += [t for t in (sd.get("tickers") or []) if isinstance(t, str) and re.fullmatch(r"[A-Z]{1,5}", t)]
        ages = [a for a in (age_fn(t, today) for t in dict.fromkeys(tickers)) if a is not None]
        if ages and min(ages) > max_age_days:
            dropped.append(f"{it.get('title')}({','.join(tickers)} 최근 발표 {min(ages)}일 전)")
            continue
        kept.append(it)
    if dropped:
        analysis["issues"] = kept
        corrections.append("오래된 실적을 지금 일로 쓴 이슈 제거: " + "; ".join(dropped))
    return len(dropped)


def fix_issue_side_tickers(analysis, latest, corrections, session_date) -> int:
    """지난 장 일로 쓴 이슈의 ▲▼ 칩에서 직전 정규장에 반대로 0.5% 넘게 움직인 종목을 뺀다(2026-11-05 실사고).

    11/5 1번 이슈가 CVX(−3.69%)·XOM(−4.62%)을 ▲에, AMD(+1.01%)·QCOM(+5.33%)을 ▼에 넣었다. 칩은 고칠 수 있지만
    문장은 고칠 수 없다 — "에너지가 웃었다" 같은 문장은 프롬프트의 us_sector_session 규칙이 막는다.
    """
    moved = {}
    for c in latest.get("us_candidates") or []:
        for s in (c.get("recent_sessions") or []) if isinstance(c, dict) else []:
            if s.get("date") == session_date and isinstance(s.get("pct"), (int, float)):
                moved[c.get("ticker")] = s["pct"]
    dropped = 0
    for it in analysis.get("issues") or []:
        if not isinstance(it, dict):
            continue
        text = f"{it.get('title') or ''} {it.get('body') or ''}"
        for key, sign, past in (("down", 1, _ISSUE_FELL_PAST), ("up", -1, _ISSUE_ROSE_PAST)):
            side = it.get(key)
            if not isinstance(side, dict) or not past.search(text):
                continue
            tickers = side.get("tickers") or []
            kept = [t for t in tickers if not (isinstance(moved.get(t), (int, float)) and moved[t] * sign >= _ISSUE_MIN_MOVE)]
            if len(kept) != len(tickers):
                dropped += len(tickers) - len(kept)
                corrections.append(f"이슈 칩 제외 — 직전 정규장 반대로 움직임: {sorted(set(tickers) - set(kept))}")
                side["tickers"] = kept
    return dropped


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
