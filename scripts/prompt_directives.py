# 그날 데이터로 만드는 프롬프트 지시문 — 세션 라벨·지수 위치·현직 인물·날짜별 일지·이벤트 시제·KST 날짜

from __future__ import annotations
import json
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_common import BASE_DIR


def _investor_to_eok(it: dict) -> dict:
    """investor_trading.net(백만원)을 프롬프트용 억원으로 바꾼 사본. 원본은 그대로 둔다(supply_history·화면이 백만원을 쓴다).

    2026-11-10 실사고 — 코스피 아침 프롬프트가 백만원 그대로 받아, 모델이 100으로 나눈 숫자에 '백만원'을 붙여
    "외국인 6,895백만원 순매도"(실제 6,895억원)가 나갔다. 마감 브리핑과 같은 단위(억원)로 맞춘다.
    """
    import copy
    out = copy.deepcopy(it or {})
    for actor in ("foreign", "institution", "individual"):
        if isinstance(out.get(actor), dict) and isinstance(out[actor].get("net"), (int, float)):
            out[actor]["net"] = round(out[actor]["net"] / 100)
    if out:
        out["_unit"] = "억원"
    return out


def _us_news_session_directive(date_str: str, news_summary: dict | None) -> str:
    """미국 브리핑 — 뉴스가 다루는 세션을 못박는다.

    미국 브리핑은 프리마켓(21:15 KST)에 나가는데 RSS로 모은 기사는 **직전 정규장 마감**을
    다룬다. 그 등락을 "지금·프리마켓"으로 옮겨 쓰면 §26 재발이다(직전 정규장 종가를
    프리마켓 실체결가인 양 실은 사고).

    세션 날짜는 fetch_news가 계산해 `news_session`으로 넘긴 값만 쓴다 — 여기서 다시
    계산하면 판정이 두 곳에 생긴다(§30).
    """
    session = (news_summary or {}).get("news_session") or {}
    prev = session.get("date")
    if not prev:
        return ""
    return (
        f"## 뉴스 세션 기준 (중요)\n"
        f"이 브리핑은 {date_str} **미국 프리마켓** 시간에 발행된다. 함께 제공된 뉴스"
        f"(catalysts·catalyst_sources)는 모두 **직전 정규장({prev}) 마감**을 다룬 기사다.\n"
        f"- 뉴스에서 온 등락·수치는 **\"직전 정규장에서\"**로 서술한다. "
        f"**\"지금·현재·프리마켓에서\"라고 쓰지 않는다.**\n"
        f"- 프리마켓 현재 상태는 뉴스가 아니라 **시장 데이터 실측**에서만 가져온다.\n"
        f"- 개별 종목의 지금 등락은 `us_candidates`의 `change_pct`(발행 시점 프리마켓 체결가)다. 어제 밀린 종목이 지금"
        f" 오르고 있으면 \"눌리고 있어요\"라고 쓰지 않는다 — 발행 전 검증이 그 문장을 실측으로 바꾼다.\n\n"
    )


def _session_label_directive(date_str: str, briefing_type: str,
                             news_summary: dict | None = None) -> str:
    """'간밤' 표기 지시문 — 월요일·휴일 다음날은 직전 미국장이 어제가 아니다.

    2026-07-27 실사고: 월요일 브리핑이 지난 금요일(7/24) 미국장을 "간밤"으로 서술.
    프롬프트만으로는 새므로 validate_analysis.fix_overnight_labels가 발행 직전 한 번 더 잡는다.

    미국 브리핑은 성격이 다르다 — '간밤'이 아니라 '뉴스가 어느 세션 것인가'가 쟁점이라
    별도 지시문으로 갈라 처리한다.
    """
    if briefing_type == "us":
        return _us_news_session_directive(date_str, news_summary)
    if briefing_type != "kospi":
        return ""
    try:
        from datetime import date as _d
        from session_label import prev_us_session, us_session_label
        y, m, dd = (int(x) for x in date_str.split("-"))
        today = _d(y, m, dd)
        prev = prev_us_session(today)
        label = us_session_label(today)
    except Exception:
        return ""
    if label == "간밤":
        return ""
    return (
        f"## 직전 미국장 표기 (중요)\n"
        f"오늘({date_str})이 참조하는 직전 미국장은 **{prev} ({label})**이다. "
        f"어젯밤 미국장은 열리지 않았으므로 **'간밤'·'어젯밤'·'밤사이'라고 쓰지 말고 "
        f"'{label}'로 쓴다.** 국내 직전 거래일도 같은 날이다.\n\n"
    )


def _index_position_directive(analysis_data: dict | None) -> str:
    """주요 지수가 52주 고·저 대비 어디에 있는지를 프롬프트에 명시한다.

    등락률만 보면 "+0.32% 상승"에서 "사상 최고 수준을 다시 확인했다"로 넘어가는 비약을
    막을 근거가 모델에게 없다. 2026-08-24·2026-08-26 코스피 아침 브리핑이 둘 다 이
    비약을 저질렀고(실측 S&P500은 52주 고점 대비 -1.6%), §28 게이트가 스칼라 산문에서
    잡아 **발행을 통째로 차단**했다 — 그날 브리핑이 아예 안 나갔다.

    게이트는 최종 방어선이라 그대로 두고(자동 교정이 불가능한 산문은 차단이 맞다),
    애초에 모델이 그 주장을 안 하도록 실측 위치를 미리 준다. 임계 1%는 게이트의
    `snap["level"] < snap["high_52w"] * 0.99` 와 같은 값이다 — 두 곳이 어긋나면
    프롬프트가 허용한 표현을 게이트가 막는 모순이 생기므로 함께 바꾼다.
    """
    idx = (analysis_data or {}).get("index_52w") or {}
    rows = []
    for label, d in idx.items():
        if not isinstance(d, dict):
            continue
        price, hi, lo = d.get("price"), d.get("high_52w"), d.get("low_52w")
        if not (price and hi and lo):
            continue
        from_hi = d.get("pct_from_52w_high")
        if from_hi is None:
            from_hi = (price - hi) / hi * 100
        near_high = price >= hi * 0.99
        near_low = price <= lo * 1.01
        verdict = ("52주 고점권 — 최고 표현 가능" if near_high
                   else "52주 저점권 — 최저 표현 가능" if near_low
                   else "고점도 저점도 아님 — 최상급 표현 금지")
        rows.append(f"- {label}: 현재 {price:,.2f} / 52주 고점 {hi:,.2f} "
                    f"({from_hi:+.2f}%) / 52주 저점 {lo:,.2f} → {verdict}")
    if not rows:
        return ""

    return (
        "## 지수 최상급 표현 규칙 (반드시 지킬 것)\n\n"
        "'사상 최고'·'최고치 경신'·'신고가'·'역대 최고' 같은 표현은 그 지수가 **52주 고점의 "
        "99% 이상**일 때만 쓴다. '사상 최저'·'신저가'도 52주 저점의 101% 이하일 때만 쓴다.\n"
        "그날 올랐다는 사실만으로 최고 표현을 쓰지 않는다 — 상승과 신고가는 다른 주장이다.\n\n"
        + "\n".join(rows) +
        "\n\n위 실측이 '최상급 표현 금지'인 지수에 최고·최저 표현을 쓰면 발행 검증에서 "
        "차단돼 브리핑이 아예 나가지 못한다. 대신 '상승 마감'·'고점권에서 버티는 중'처럼 "
        "실측이 뒷받침하는 표현을 쓴다.\n\n"
    )


def _officeholder_directive() -> str:
    """현직 인물(연준 의장 등)을 프롬프트에 못박는다 — 모델은 학습 시점 인물을 쓴다.

    2026-10-26 코스피 브리핑이 '파월 발언 톤'이라고 썼다(실제 의장은 2026-05-22부터 워시, §29에서도 같은 오류).
    발행 직전 validate_analysis.fix_officeholder_names()가 한 번 더 교정한다(프롬프트는 새기 때문이다).
    """
    try:
        table = json.loads((BASE_DIR / "scripts" / "config" / "officeholders.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    rows = []
    for key, o in table.items():
        if key.startswith("_") or not isinstance(o, dict):
            continue
        former = "·".join(o.get("former") or [])
        rows.append(f"- 현재 {o['role']}: **{o['full_name']}**({o['since']} 취임)"
                    + (f" — {former}는 현직이 아니다. {o.get('former_note', '')}" if former else ""))
    if not rows:
        return ""
    return ("## 현직 인물 (반드시 지킬 것)\n" + "\n".join(rows) +
            "\nFOMC 기자회견·의장 발언 등 그 자리의 역할을 쓸 때는 반드시 현직 이름을 쓴다.\n\n")


def _us_session_log_directive(date_str: str, analysis_data: dict | None) -> str:
    """최근 미국 세션 일지(날짜별 등락) — 사건을 실제로 일어난 날짜에 붙이게 한다.

    2026-10-26(월) 브리핑이 목요일(10/22) 메타 충격을 '지난 금요일 미 증시는 메타 우려로 흔들렸다'로 썼다
    (금요일 SOX +0.44%·DRAM +3.02% 반등). 직전 세션 일봉만 받던 모델에겐 날짜를 가를 근거가 없었다.
    """
    log = (analysis_data or {}).get("us_recent_sessions") or {}
    if not log:
        return ""
    try:
        from datetime import date as _d
        from session_label import prev_us_session, us_session_label
        y, m, dd = (int(x) for x in date_str.split("-"))
        today = _d(y, m, dd)
        prev, label = str(prev_us_session(today)), us_session_label(today)
    except Exception:
        prev, label = "", ""
    dows = "월화수목금토일"
    by_date = {}
    for name, rows in log.items():
        for r in rows or []:
            if isinstance(r, dict) and r.get("date") and isinstance(r.get("pct"), (int, float)):
                by_date.setdefault(r["date"], []).append(f"{name} {r['pct']:+.2f}%")
    if not by_date:
        return ""
    lines = []
    for ds in sorted(by_date, reverse=True):
        d = _d(*(int(x) for x in ds.split("-")))
        tag = f" ← 직전 미국장({label})" if ds == prev and label else ""
        lines.append(f"- {d.month}/{d.day}({dows[d.weekday()]}){tag}: " + ", ".join(by_date[ds]))
    return ("## 최근 미국 세션 일지 (사건 날짜 확인용)\n" + "\n".join(lines) +
            "\n뉴스의 사건(실적 충격·급락·반등)은 위 일지에서 **실제로 그 움직임이 있었던 날짜**로 쓴다. "
            "직전 미국장보다 앞선 날의 일을 직전 미국장의 일처럼 쓰지 않는다 — 그날을 '목요일'처럼 명시한다.\n\n")


def _calendar_tense_directive(analysis_data: dict | None) -> str:
    """이미 끝난 고영향 경제 이벤트를 예고형으로 쓰지 않도록 발행 시점 시제를 주입한다.

    코스피 아침(07:25)·미국(21:15) 브리핑은 그날 03:00 KST FOMC보다 뒤에 나가는데,
    캘린더 소스가 `actual`을 절대 채우지 않아 모델에겐 모든 이벤트가 "미발표"로 보였다
    (2026-07-30 실사고 — SERVICE_RULES §29). fetch_data가 시각을 비교해 붙인
    `status`가 유일한 근거이므로, 그 결과를 프롬프트에 명시적으로 넣는다.

    US 프롬프트에는 economic_calendar 설명 자체가 없었으므로 이 지시가 세 브리핑
    모두를 한 번에 덮는다.
    """
    cal = (analysis_data or {}).get("economic_calendar") or {}
    today = [e for e in (cal.get("today") or []) if isinstance(e, dict)]
    released = [e for e in today if e.get("status") == "released"]
    if not released:
        return ""

    def _fmt(e):
        return f"- {e.get('title', '')} ({e.get('date_kst', '')})"

    lines = [
        "## 경제 이벤트 시제 (반드시 지킬 것)",
        "",
        "아래 이벤트는 이 브리핑이 나가는 시점에 **이미 끝났다**. "
        "'예정'·'앞두고'·'대기'·'유력하지만'처럼 예고형으로 쓰지 말고 결과로 서술한다.",
        *[_fmt(e) for e in released],
        "",
        "결과 수치는 **뉴스 요약에 실제로 있을 때만** 쓴다. 없으면 발표됐다는 사실만 적거나 "
        "아예 언급하지 않는다 — 결과를 추정·생성하지 않는다.",
        "forecast는 시장 예상치일 뿐이므로 이미 끝난 이벤트에 결과처럼 쓰지 않는다.",
    ]

    upcoming = [e for e in today if e.get("status") == "upcoming"]
    if upcoming:
        lines += ["", "반면 아래는 아직 발표 전이므로 예고형으로 쓴다.",
                  *[_fmt(e) for e in upcoming]]

    return "\n".join(lines) + "\n\n"


def _event_when_directive(date_str: str, analysis_data: dict | None) -> str:
    """미국 경제 이벤트의 한국 시각을 '오늘/내일 새벽' 표기로 못박는다(2026-10-28 실사고).

    07:25 코스피 아침 브리핑이 FOMC 결과(10/29 03:00 KST)를 "오늘 새벽 … 예정"이라 썼다 —
    미국 날짜(ET) 기준 '오늘'이었다. 캘린더의 KST 시각을 브리핑 날짜와 비교한 표기를 그대로 주고,
    발행 직전 validate_analysis.fix_event_day_words()가 같은 계산(event_when)으로 한 번 더 고친다.
    사흘 안 미국 이벤트가 없으면 아무것도 넣지 않는다.
    """
    try:
        from event_when import is_minutes, minutes_meeting_month, us_events, when_label
        today = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return ""
    evs = [e for e in us_events((analysis_data or {}).get("economic_calendar"))
           if 0 <= (e["dt"].date() - today).days <= 2]
    if not evs:
        return ""
    lines = ["## 미국 이벤트 시각 (한국 시간 — 반드시 지킬 것)", "",
             "미국 이벤트는 아래 한국 시간 표기를 그대로 쓴다. 미국 날짜(ET)로 '오늘'이라 쓰지 않는다 — "
             "예를 들어 미국 시간 오늘 오후 2시 FOMC는 한국 시간 '내일 새벽 3시'다."]
    for e in evs:
        line = f"- {e['title']} ({e['date_kst']}) → '{when_label(e['date_kst'], today)}'"
        if is_minutes(e["title"]):   # 공개 달이 아니라 회의 달로 부른다(2026-11-18 실사고)
            line += (f" — {minutes_meeting_month(e['dt'])}월 회의 의사록이다(의사록은 회의 약 3주 뒤 공개). "
                     f"공개되는 달로 '{e['dt'].month}월 의사록'이라 쓰지 않는다")
        lines.append(line)
    return "\n".join(lines) + "\n\n"
