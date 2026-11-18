# 코스피 아침 브리핑 섹션 컨텍스트 — 요약 카드·어제 예측·이슈 점검·예측 근거·전일 수급

import json
import re
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from briefing_data import read_dated_payload
from prediction_basis import OPEN as BASIS_OPEN
from html_common import BASE_DIR, DATA_DIR, _DOWS, _market_data_is_for, load_json
from sections_close import _split_comfort_line, build_flow_context, build_keynum_context, build_qa_context, build_scenario_context, build_signal_context, build_why_what_so_context


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
                    ("ewy_resid", "EWY(코스피 반영분 제외)"), ("vix", "VIX"), ("ai_ah", "AI 반도체 시간외")]


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


def build_ib_korea_views(target_date: str = None) -> dict:
    """외국계 IB 코멘트 섹션 컨텍스트 빌더 (코스피 전용).

    url이 없는 항목은 표시하지 않는다(원본 링크 이동 보장). 데이터 없으면 빈 리스트 →
    템플릿에서 섹션 자체 생략. 날짜가 브리핑 날짜와 다르면 쓰지 않는다 — 국내 이슈와 같은 검사(§14,
    2026-10-26 추가: 이전 실행의 잔존 파일이 다른 날짜 브리핑에 실릴 수 있었다).
    """
    payload = read_dated_payload(BASE_DIR / "data" / "ib_korea_views.json", target_date)
    if payload is None:
        return {"ib_korea_views": []}
    views = [v for v in (payload.get("views") or []) if isinstance(v, dict) and v.get("url")]
    return {"ib_korea_views": views}


def build_domestic_issues(target_date: str = None) -> dict:
    """국내 이슈 섹션 컨텍스트 빌더 (코스피 아침 전용).

    url 없는 항목은 제외한다(원본 링크 이동 보장). 데이터가 없거나 날짜가 다르면
    빈 리스트 → 템플릿에서 섹션 자체 생략(운영 규칙 0 — 없으면 지어내지 않는다).
    날짜 검증은 이전 실행의 잔존 파일이 다른 날짜 브리핑을 오염시키는 것을 막는다(§14와 동일 패턴).

    `time_abs`는 절대 시각('10/22 21:44')이다 — 발행 뒤 굳는 정적 페이지라 '3시간 전' 같은
    상대 라벨은 읽는 시각에 따라 틀린다(§20·§24에서 세 번 재발한 패턴).
    """
    payload = read_dated_payload(BASE_DIR / "data" / "domestic_issues.json", target_date)
    if payload is None:
        return {"domestic_issues": [], "domestic_window_label": ""}

    items = []
    for it in payload.get("issues") or []:
        if not isinstance(it, dict) or not it.get("url"):
            continue
        items.append({**it, "time_abs": _abs_time_label(it.get("published_at"))})
    return {
        "domestic_issues": items,
        "domestic_window_label": (payload.get("window") or {}).get("label", ""),
        "domestic_card_title": _domestic_card_title((payload.get("window") or {}).get("from", "")),
    }
