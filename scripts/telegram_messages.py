# 브리핑 텔레그램 메시지 조립 — 코스피 아침·미국·코스피 마감, 월봉 5개월선·S&P 200일선·나스닥 체크 줄

from __future__ import annotations
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sp500_ma200 import EVENT_LINE as SP500_TG_LINE, EVENT_JUMP as SP500_TG_JUMP, event_of as _sp500_event  # noqa: E402,F401 — 판정은 한 곳(§30)
from claude_common import DATA_DIR, load_config


def get_web_base_url() -> str:
    web_base = os.environ.get("WEB_BASE_URL", "")
    if not web_base:
        cfg = load_config()
        web_base = cfg.get("web", {}).get("base_url", "https://pulum0083.github.io/daily30")
    return web_base.rstrip("/")


def _today_kospi_prediction(date_str: str) -> dict | None:
    """오늘(date_str) 날짜의 kospi 예측 항목을 briefings.json에서 찾는다. 없으면 None.

    §16 방지 룰(SERVICE_RULES.md): 오늘 항목이 없으면 절대 다른 날짜로 대체하지 않는다 —
    호출부는 반드시 배지 자체를 생략해야 한다."""
    bpath = DATA_DIR / "briefings.json"
    if not bpath.exists():
        return None
    try:
        rows = json.load(open(bpath, encoding="utf-8")).get("briefings", [])
    except Exception:
        return None
    return next((b for b in rows if b.get("type") == "kospi" and b.get("date") == date_str), None)


def _cumulative_kospi_accuracy(before_date: str) -> "tuple[int, int] | None":
    """before_date 이전(오늘 미포함)까지 채점 완료된 kospi 예측의 (적중건, 전체건). 없으면 None."""
    bpath = DATA_DIR / "briefings.json"
    if not bpath.exists():
        return None
    try:
        rows = json.load(open(bpath, encoding="utf-8")).get("briefings", [])
    except Exception:
        return None
    from prediction_basis import stats_rows
    scored = [b for b in stats_rows(rows)
              if b.get("type") == "kospi"
              and str(b.get("date", "")) < before_date
              and b.get("is_correct") is not None]
    if not scored:
        return None
    hit = sum(1 for b in scored if b.get("is_correct"))
    return hit, len(scored)


def _ma5_telegram_lines(analysis: dict, date_str: str) -> list:
    """월봉 5개월선 안착 종목 블록 — 페이지에 그 섹션이 보일 때만 같은 데이터로 싣는다(§61·§62).

    텔레그램은 HTML 생성보다 먼저 만들어져 analysis에 아직 monthly_ma5가 없을 수 있다. 그래서 페이지와 같은
    generate_html.build_monthly_ma5()로 읽는다 — 날짜 대조·백테스트 파일 없음 처리까지 페이지와 똑같다.
    백테스트 설명 줄은 싣지 않는다 — 한 줄로는 뜻이 전달되지 않아 페이지의 '근거와 면책 고지'에만 둔다(사용자 결정 2026-10-26).
    백테스트 파일이 없으면 페이지가 섹션을 빼므로 여기서도 같은 조건으로 뺀다.
    """
    import generate_html
    ctx = generate_html.build_monthly_ma5(dict(analysis), date_str)
    items, st = ctx.get("ma5m_items") or [], ctx.get("ma5m_stats")
    if not items or not st:
        return []
    out = ["", "📊 월봉 5개월선 안착 종목"]
    for x in items[:3]:
        # 한 줄이 구분선 폭(20칸)에 들어가게 짧게 쓴다 — 괄호만 다음 줄로 넘어가던 것을 막는다(2026-10-27).
        gap = (f"이격 {x['now_gap_pct']:+.1f}%" if x.get("has_cur")
               else f"{x['last_label']} 말 이격 {x['month_end_gap_pct']:+.1f}%")
        out.append(f"• {x['name']} {x['streak']}개월째 · {gap}")
    if len(items) > 3:
        out.append(f"• 외 {len(items) - 3}종목")
    return out


def _sp500_lines(analysis: dict, date_str: str) -> list:
    """S&P 500 200일선 체크 — 비율 한 줄 + 무슨 일인지 한 줄 + 아래로 넘은 종목 + 과열 종목(§81).

    특별한 날에만 싣는다 — 200일선 위 비율이 50%를 넘나들었거나 하루에 5%p 넘게 움직인 날(2026-11-09 사용자 결정,
    그 전엔 매일 나갔다). 전날 비율이 없으면 판단할 수 없어 싣지 않는다.
    페이지와 같은 generate_html.read_sp500_ma200()으로 읽는다(날짜 대조까지 같다). 값이 없으면 블록째 뺀다.
    종목은 시가총액 순 앞 3개만 쓰고 나머지는 '외 N개'로 묶는다 — 말풍선 폭(21칸)에 한 줄로 들어간다.
    """
    import generate_html
    d = generate_html.read_sp500_ma200(dict(analysis), date_str)
    if not d or not isinstance(d.get("above_pct"), (int, float)) or not isinstance(d.get("above_pct_prev"), (int, float)):
        return []
    event = _sp500_event(d["above_pct"], d["above_pct_prev"])
    if not event:
        return []
    out = ["", f"📏 S&P 500 200일선 위 {d['above_pct']:.1f}% (전날 {d['above_pct_prev']:.1f}%)", event]

    def names(rows):
        s = "·".join(r["t"] for r in rows[:3])
        return s + (f" 외 {len(rows) - 3}개" if len(rows) > 3 else "")
    if d.get("below"):
        out.append(f"이탈 {names(d['below'])}")
    if d.get("hot"):
        out.append(f"과열 {names(d['hot'])}")
    return out


def _nasdaq_change_lines(analysis: dict, date_str: str) -> list:
    """나스닥 체크는 주의(60)·경고(70)에 처음 닿은 날과 전달 고점을 처음 넘은 날의 미국 브리핑에만 싣는다(2026-11-03 사용자 결정).

    판정은 모두 월봉 고점으로 한다 — 60개월선은 종가를 따라 매일 소수점이 움직여 값으로 보면 거의 매일 바뀐다.
    직전 세션 데이터가 아니면 싣지 않는다 — 수집이 밀린 날 어제 일을 또 보내게 된다.
    """
    from datetime import date
    import generate_html as gh
    import nasdaq_overheat as nq
    from session_label import prev_us_session
    data = analysis.get("nasdaq_overheat") or gh._read_nasdaq_overheat(date_str)
    if not data or not data.get("high_changed") or not isinstance(data.get("gap_pct"), (int, float)):
        return []
    prev_session = prev_us_session(date.fromisoformat(date_str))
    if not prev_session or data.get("last_date") != prev_session.isoformat():
        return []
    gap, month, level = float(data["gap_pct"]), str(data.get("month") or ""), nq.level_of(float(data["gap_pct"]))
    high, prev_high, pm_high, ma60 = (data.get(k) for k in ("high", "prev_high", "prev_month_high", "ma60"))
    before = nq.level_of((prev_high / ma60 - 1) * 100) if isinstance(prev_high, (int, float)) and ma60 else "ok"
    rank = {"ok": 0, "caution": 1, "warn": 2}
    crossed = rank[level] > rank[before]
    broke = (isinstance(pm_high, (int, float)) and isinstance(high, (int, float)) and high > pm_high
             and (not isinstance(prev_high, (int, float)) or prev_high <= pm_high))
    if not crossed and not broke:
        return []
    icon, word = {"ok": ("📊", "✓ 정상"), "caution": ("⚠️", "주의"), "warn": ("🚨", "경고")}[level]
    y, m = int(month[:4]), int(month[5:7])
    last_m = 12 if m == 1 else m - 1
    reasons = []
    if crossed:
        reasons.append(f"{word} 기준 {nq.WARN if level == 'warn' else nq.CAUTION:.0f}%를 넘었어요.")
    if broke:
        reasons.append(f"{last_m}월 고점({pm_high:,.0f})을 넘었어요.")
    lines = ["", f"{icon} 나스닥 체크 {m}월 {gap:+.1f}% · {word}", " ".join(reasons)]
    if level == "warn":
        try:
            bt = json.loads(gh.NASDAQ_BACKTEST_PATH.read_text(encoding="utf-8"))
            lines.append(f"※ 과거 {nq.WARN:.0f}% 넘은 달 뒤 12개월 안에 -20% 넘게 빠진 경우가 "
                         f"{bt['warn']['dd20_pct']:.0f}%였어요(전체 {bt['all_dd20_pct']:.0f}%).")
        except (OSError, ValueError, KeyError) as e:
            print(f"[call_claude] 나스닥 경고 통계 생략: {e}", file=sys.stderr)
    return lines


def save_telegram_message(briefing_type: str, date_str: str, analysis: dict) -> None:
    """analysis JSON → telegram_message_{type}.txt 생성 (매 실행마다 최신화)."""
    from send_telegram import link_line
    import re

    def strip_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", str(text))

    web_base = get_web_base_url()

    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y.%m.%d")

    pred = analysis.get("prediction", {})
    direction = pred.get("direction", "알 수 없음")
    up_pct = pred.get("up_pct", "?")
    down_pct = pred.get("down_pct", "?")
    confidence = pred.get("confidence", "?")
    reason_title = strip_html(analysis.get("reason_title", ""))

    # 방향에 맞는 확률 표기: 상승 우위 → up_pct, 하락 우위 → down_pct
    dir_pct   = down_pct if "하락" in str(direction) else up_pct
    dir_emoji = "📈" if "상승" in str(direction) else ("📉" if "하락" in str(direction) else "📊")


    if briefing_type == "us":
        # 미국: 큰 쪽 확률 → 헤드라인(🎯) → 오늘 밤 볼 것(👀, 첫 이슈 제목) — 코스피 형식과 맞춘다(2026-10-25).
        # 미국 예측엔 신뢰도가 없다. 두 문장 모두 웹 페이지 맨 위 헤드라인·첫 이슈 카드와 같은 필드다.
        header = f"🇺🇸 미국 시장 브리핑 | {date_display}"
        link   = f"{web_base}/briefings/{date_str}/us/"
        tv = analysis.get("todays_view") or {}
        view_title = strip_html(tv.get("view_title", ""))
        issue_titles = [strip_html(it.get("title", "")) for it in (analysis.get("issues") or []) if it.get("title")]
        lines = [header, ""]
        if isinstance(up_pct, int) and isinstance(down_pct, int):
            if up_pct == down_pct:
                lines += [f"📊 <b>중립 {up_pct}%</b>"]
            else:
                us_up = up_pct > down_pct
                lines += [f"{'📈' if us_up else '📉'} <b>{'상승' if us_up else '하락'} 우위 {max(up_pct, down_pct)}%</b>"]
        if view_title:
            lines += ["", f"🎯 <b>{view_title}</b>"]
        if issue_titles:
            lines += ["", "👀 오늘 밤 볼 것", issue_titles[0]]
        lines += _nasdaq_change_lines(analysis, date_str)
        lines += _sp500_lines(analysis, date_str)
        lines += ["", link_line("전체 이슈 점검", link)]
    else:
        # 코스피: 방향·확률 → 헤드라인(🎯) → 개장 후 볼 것(👀) 한 문장씩만(2026-10-25).
        # 두 문장 모두 웹 페이지 맨 위 헤드라인·'오늘 볼 것' 첫 줄과 같은 필드라 텔레그램과 페이지가 어긋나지 않는다.
        is_open = (analysis.get("prediction") or {}).get("basis") == "open"
        header = f"🇰🇷 코스피 {'시초가 예측' if is_open else '예측 브리핑'} | {date_display}"
        link   = f"{web_base}/briefings/{date_str}/kospi/"
        tv = analysis.get("todays_view") or {}
        headline = strip_html(tv.get("view_title", "")) or reason_title
        outlook = [o for o in (tv.get("outlook") or []) if isinstance(o, dict) and o.get("text")]

        lines = [header, "", f"{dir_emoji} <b>{direction} {dir_pct}%</b> (신뢰도 {confidence}%)"]
        if headline:
            lines += ["", f"🎯 <b>{headline}</b>"]
        if outlook:
            lines += ["", "👀 개장 후 볼 것", strip_html(outlook[0]["text"])]
        lines += _ma5_telegram_lines(analysis, date_str)
        lines += ["", link_line("전체 근거·이슈 점검", link)]

    msg = "\n".join(lines)
    path = DATA_DIR / f"telegram_message_{briefing_type}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(msg)
    print(f"[call_claude] Telegram message saved → {path}")


def save_closing_telegram_message(date_str: str, analysis: dict, market_data: dict) -> None:
    """KOSPI 마감 시황 텔레그램 메시지를 파일로 저장한다."""
    from send_telegram import link_line
    import re

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_accuracy import classify_direction_correct

    def strip_html(text):
        return re.sub(r"<[^>]+>", "", str(text))

    web_base = get_web_base_url()
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%Y.%m.%d")
    except Exception:
        date_display = date_str

    indices = market_data.get("indices", {})
    kospi  = indices.get("kospi", {})   # 종가 기준(전환 이전) 예측 채점에만 쓴다 — 지수 줄은 싣지 않는다(2026-10-27)

    # 타이틀은 market_title(brief·why_what_so) 또는 reason_title(옛 scenario·qa·signal) — 페이지와 같은 우선순위.
    title = strip_html(analysis.get("market_title") or analysis.get("reason_title") or "")
    dek   = strip_html(analysis.get("dek") or "")

    # 결과 배지: 오늘 아침 kospi 예측을 그 예측의 기준으로 즉석 채점. 오늘 예측이 없으면 배지 생략(§16).
    #  · 시초가 기준(§57) → 오늘 시가 갭으로 채점한다. 갭을 못 구하면 종가로 대신 채점하지 않고 배지를 뺀다.
    #  · 종가 기준(전환 이전 기록) → 오늘 종가 등락률.
    result_badge = ""
    today_pred = _today_kospi_prediction(date_str)
    kospi_chg = kospi.get("change_pct") if "error" not in kospi else None
    if today_pred:
        from prediction_basis import is_open_basis
        predicted = today_pred.get("predicted_direction", "")
        if is_open_basis(today_pred):
            from check_accuracy import get_kospi_open_gap
            gap = get_kospi_open_gap(date_str)
            actual, what = (gap[2] if gap else None), "시초가"
        else:
            actual, what = (kospi_chg if isinstance(kospi_chg, (int, float)) else None), "실제"
        if actual is not None:
            is_correct = classify_direction_correct(predicted, actual)
            mark = "✓" if is_correct else "✗"
            cum = _cumulative_kospi_accuracy(date_str)
            # 표본 5건 미만이면 누적 %를 붙이지 않는다 — 전환 직후 "1건 100%"는 뜻이 없다(§57)
            cum_txt = f" (누적 {round(cum[0] / cum[1] * 100)}%)" if (cum and cum[1] >= 5) else ""
            # 짧게 쓴다 — "→"에서 줄이 끊기던 것을 막는다(2026-10-27). "상승 우위" → "상승".
            short = str(predicted).replace(" 우위", "")
            result_badge = f"📝 아침 예측 {short} → {what} {actual:+.2f}% {mark}{cum_txt}"

    # 🎯 타이틀 → 서브 한 문장 → 아침 예측 채점(2026-10-27). 지수 수치 줄은 싣지 않는다 — 타이틀이 주인공이다.
    # 타이틀·서브는 웹 페이지 제목·서브와 같은 필드다. 타이틀과 서브 사이는 한 줄 띄운다(2026-10-30, 코스피 예측과 같은 간격).
    lines = [f"🇰🇷 코스피 마감 시황 | {date_display}", ""]
    if title:
        lines += [f"🎯 <b>{title}</b>"]
        if dek:
            lines += ["", dek]
    if result_badge:
        lines += ["", result_badge]
    lines += ["", link_line("수급·시장폭 상세", f"{web_base}/briefings/{date_str}/close/")]

    msg = "\n".join(lines)
    out = DATA_DIR / "telegram_message_kospi_close.txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write(msg)
    print(f"[call_claude] Closing telegram message saved → {out}")
