# 여러 브리핑이 함께 쓰는 섹션 컨텍스트 — 월봉 5개월선·예측 카드·시장 지표·성적표

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from briefing_data import read_dated_payload
from prediction_basis import OPEN as BASIS_OPEN, stats_rows, legacy_kospi_rows, outcome_pct
from html_common import BASE_DIR, BRIEFINGS_DIR, CONFIG_DIR, DATA_DIR, QUOTE_TODAY_FILE, SRC_TYPE, load_json


MA5_BACKTEST_PATH = CONFIG_DIR / "monthly_ma5_backtest.json"


MA5_MARKETS = {
    # 코스피 아침(§61) — 허브 46종목·KRX 공식 종가
    "kr": {"key": "monthly_ma5", "file": "monthly_ma5.json", "bt": None,   # None = MA5_BACKTEST_PATH(호출 시점 값)
           "scope": "코스피200", "source": "KRX 공식 종가", "modal": "ma5m-modal"},
    # 미국(§67) — 미국 후보 대형주·정규장 종가. AI 종목 픽(진입·목표·손절)을 대체한다
    "us": {"key": "monthly_ma5_us", "file": "monthly_ma5_us.json", "bt": CONFIG_DIR / "monthly_ma5_us_backtest.json",
           "scope": "미국 대형주 후보", "source": "미국 정규장 종가", "modal": "ma5m-us-modal"},
}


def _ma5_price(v, market: str) -> str:
    return f"${v:,.2f}" if market == "us" else f"{v:,.0f}원"


def build_monthly_ma5(analysis: dict, target_date: str = "", market: str = "kr") -> dict:
    """월봉 5개월선 안착 종목 코너(sections/monthly_ma5.html) — 코스피 아침·미국 브리핑 공용.

    us_issue_results와 같은 구조다 — 스냅샷이 1순위고, 데이터 파일은 브리핑 날짜와 같을 때만 쓴다(§14·§45).
    조건 충족 종목이 없으면 섹션을 통째로 뺀다. 하단 '1년 뒤 오른 비율' 문장의 출처인 백테스트 파일이
    없어도 뺀다 — 그 문장 없이 종목만 보이면 '오른다'로 읽힌다(사용자 결정 2026-10-25).
    """
    cfg = MA5_MARKETS[market]
    data = analysis.get(cfg["key"])
    if not isinstance(data, dict):
        data = _read_monthly_ma5(target_date, cfg["file"])
        if data is not None:
            data = _drop_ma5_repeats(data, target_date, market)
            analysis[cfg["key"]] = data   # 스냅샷에 함께 저장된다 — 걸러낸 뒤라 재생성해도 같은 목록이다
    items = [x for x in ((data or {}).get("items") or []) if isinstance(x, dict) and x.get("strip")]
    stats = _ma5_backtest_stats(cfg["bt"])
    if not items or not stats:
        return {"ma5m_items": []}
    view = []
    for x in items:
        cells = []
        for c in x["strip"]:
            gap = c.get("gap_pct")
            tip = (f"{c.get('label', '')} {'현재' if c.get('cur') else '월말'} 종가 {_ma5_price(c['close'], market)}"
                   + (f" · 5개월선 {_ma5_price(c['ma5'], market)}" if c.get("ma5") else ""))
            cells.append({**c, "cls": "up" if (gap or 0) > 0 else "dn", "tip": tip,
                          "h": round(min(abs(gap or 0), 20) / 20 * 100)})
        nd = str(x.get("now_date") or "")
        view.append({**x, "cells": cells, "n": len(cells),
                     "now_label": f"{int(nd[4:6])}/{int(nd[6:8])}" if len(nd) == 8 else "",
                     "now_price": _ma5_price(x["now_close"], market),
                     "has_cur": bool(cells and cells[-1].get("cur")),
                     "last_label": f"{int(str(x['last_complete'])[4:])}월"})
    return {"ma5m_items": view, "ma5m_stats": {**stats, "scope": cfg["scope"], "source": cfg["source"]},
            "ma5m_modal": cfg["modal"]}


def _ma5_shown_this_month(target_date: str, market: str) -> set:
    """같은 달에 이미 발행된 브리핑(그 날짜 전)의 월봉 5개월선 코너에 나온 종목 코드.

    발행본 스냅샷이 원본이다(§4·§45) — 로컬 데이터 파일이 아니라 실제로 구독자에게 나간 목록을 센다.
    """
    if not target_date or len(target_date) < 7:
        return set()
    cfg = MA5_MARKETS[market]
    btype = "kospi" if market == "kr" else "us"
    seen = set()
    for snap in sorted(BRIEFINGS_DIR.glob(f"{target_date[:7]}-*/{btype}/analysis_snapshot.json")):
        if snap.parent.parent.name >= target_date:
            continue
        try:
            d = json.loads(snap.read_text(encoding="utf-8")).get(cfg["key"]) or {}
        except Exception:
            continue
        seen |= {x.get("code") for x in (d.get("items") or []) if isinstance(x, dict) and x.get("code")}
    return seen


def _drop_ma5_repeats(data: dict, target_date: str, market: str) -> dict:
    """한 번 실은 종목은 그 달에 다시 싣지 않는다(사용자 결정 2026-10-27) — 브리핑·텔레그램 공통.

    조건은 월봉 기준이라 한 달 내내 같은 종목이 매일 나왔다. 다음 달에도 조건을 채우면 다시 나온다.
    뺀 종목 이름은 기록으로 `repeat_hidden`에 남긴다. 실을 종목이 없으면 브리핑·텔레그램·첫 화면 모두 섹션째 빠진다.
    """
    seen = _ma5_shown_this_month(target_date, market)
    items = data.get("items") or []
    keep = [x for x in items if not (isinstance(x, dict) and x.get("code") in seen)]
    if len(keep) == len(items):
        return data
    hidden = [x.get("name") or x.get("code") for x in items if isinstance(x, dict) and x.get("code") in seen]
    print(f"[generate_html] 월봉 5개월선 — 이번 달에 이미 실은 종목 제외: {', '.join(hidden)}")
    return {**data, "items": keep, "repeat_hidden": hidden}


def _read_monthly_ma5(target_date: str, filename: str = "monthly_ma5.json"):
    """data/{filename} 을 읽되 브리핑 날짜가 같을 때만 돌려준다."""
    return read_dated_payload(DATA_DIR / filename, target_date)


def _ma5_backtest_stats(path=None):
    """백테스트 설정 파일의 12개월 수치. 없거나 깨졌으면 None."""
    try:
        bt = json.loads((path or MA5_BACKTEST_PATH).read_text(encoding="utf-8"))
        h = bt["horizons"]["12"]
        y0, y1 = (int(v) for v in bt["years_label"].split("~"))
        return {"win_pct": h["signal"]["win_pct"], "base_win_pct": h["base"]["win_pct"],
                "n": h["signal"]["n"], "years": y1 - y0 + 1, "years_label": bt["years_label"],
                "universe": bt.get("universe", "")}
    except Exception as e:
        print(f"[generate_html] 월봉 5개월선 백테스트 수치 없음({e}) — 섹션 생략")
        return None


def build_prediction(analysis: dict, index_name: str, pred_title: str, gen_time: str) -> dict:
    pred = analysis.get("prediction", {})
    up_pct = pred.get("up_pct", 50)
    down_pct = pred.get("down_pct", 100 - up_pct)
    direction = pred.get("direction", "중립")
    confidence = pred.get("confidence", 70)
    is_up = "상승" in direction
    dir_cls = "up" if is_up else ("dn" if "하락" in direction else "neutral")
    band_color = "#E03131" if is_up else "#2775ED"
    dots = max(1, min(5, round(confidence / 20)))
    conf_label = "강함" if confidence >= 80 else ("보통" if confidence >= 60 else "약함")
    basis = pred.get("basis")
    if basis == BASIS_OPEN and index_name.upper().startswith("KOSPI"):
        pred_title = "KOSPI 시초가 방향 예측"
    return {
        "pred_title": pred_title,
        "pred_basis": basis,          # "open"이면 시초가 기준(§57). 옛 스냅샷엔 없다 → 템플릿이 옛 문구를 쓴다
        "direction": direction,
        "dir_cls": dir_cls,
        "dir_arrow": "↑" if is_up else ("↓" if "하락" in direction else "→"),
        "dir_word": "상승" if is_up else "하락",
        "up_pct": up_pct,
        "down_pct": down_pct,
        "readout_pct": up_pct if is_up else down_pct,
        "band_left": max(0, min(86, (up_pct if is_up else up_pct) - 7)),
        "band_width": 14,
        "band_color": band_color,
        "confidence": confidence,
        "confidence_dots": dots,
        "confidence_label": conf_label,
        "generated_time": gen_time,
    }


def _load_quote_today(target_date: str) -> dict:
    """quote_today.json이 이 브리핑 날짜와 일치할 때만 {quote, author}를 반환한다.
    call_claude.py의 render_outputs()가 코스피 타입일 때만 이 파일을 쓴다."""
    if not QUOTE_TODAY_FILE.exists():
        return {}
    try:
        q = load_json(QUOTE_TODAY_FILE)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(q, dict):
        return {}
    if q.get("date") != target_date or not q.get("quote") or not q.get("author"):
        return {}
    return {"quote": q["quote"], "author": q["author"]}


def _chg_cell(chg) -> dict:
    """등락률 셀의 표시 문자열과 색상 클래스.

    세 상태를 구분한다 — 모름(None) / 보합(정확히 0) / 상승·하락.
    예전엔 `>= 0`으로 뭉뚱그려 0.00%가 ▲·상승색(빨강)으로 나갔다. 방향성이 핵심인
    화면에서 '안 움직임'과 '올랐음'이 같은 모습이면 안 된다.
    """
    if chg is None:
        return {"chg": "", "chg_cls": "unknown"}
    if chg == 0:
        return {"chg": "— 0.00%", "chg_cls": "flat"}
    return {
        "chg": f"{'▲' if chg > 0 else '▼'} {chg:+.2f}%",
        "chg_cls": "up" if chg > 0 else "down",
    }


def build_market_items(market_data: dict, internal_type: str, gen_time: str) -> list:
    """시장 지표 사이드바 줄 — VIX와 미국 하이일드 스프레드(공포·탐욕은 위 다이얼).

    줄마다 큰 숫자·상태 뱃지·구간 막대·뜻 한 줄을 둔다(2026-11-23, 시안
    docs/prototypes/2026-11-23-market-indicators-hy.html). 데이터가 없으면 그 줄을 그리지 않는다(§0).
    """
    if internal_type not in ("kospi", "us"):
        return []
    mdj = dict(market_data.get("market_data_js", {}))
    if "vix" not in mdj and market_data.get("vix"):
        mdj["vix"] = market_data["vix"]
    items = []
    vix = _vix_item(mdj.get("vix"))
    if vix:
        items.append(vix)
    hy = _hy_item(mdj.get("hy"))
    if hy:
        items.append(hy)
    return items


def _prev_mark(prev, prev_pos, now_val, label: str) -> dict:
    """막대 위 '어제' 빈 점 — 다이얼처럼 어제 → 오늘을 잇는다. 어제 값이 없거나 같으면 뺀다."""
    if prev is None or prev_pos is None or abs(float(prev) - float(now_val)) < 0.005:
        return {"prev_pos": None, "prev_label": ""}
    return {"prev_pos": round(prev_pos, 1), "prev_label": label}


# 구간 막대 색 — 다이얼 아치와 같은 파스텔
_Z_G, _Z_G2, _Z_Y, _Z_R, _Z_R2 = "#86EFAC", "#D9F99D", "#FDE68A", "#FCA5A5", "#F87171"


def _vix_item(vix) -> dict:
    """VIX — S&P500 30일 내재변동성. 막대는 0~50, 15·20·30·40 경계."""
    if not isinstance(vix, dict) or not isinstance(vix.get("price"), (int, float)):
        return {}
    p = float(vix["price"])
    lvls = [(15, "안정", "g"), (20, "보통", "g"), (30, "경계", "y"), (40, "불안", "r"), (10 ** 9, "극단", "r")]
    _, lbl, cls = next(x for x in lvls if p < x[0])
    cp = vix.get("change_pct")
    prev = p / (1 + cp / 100) if isinstance(cp, (int, float)) and cp > -100 else None
    return {
        "key": "vix", "name": "VIX 공포지수", "info_modal": "vix-modal",
        "val": f"{p:.2f}",
        "chg": f"전일 {prev:.2f} · 하루 {'+' if cp >= 0 else '−'}{abs(cp):.1f}%" if prev is not None else "",
        "badge": lbl, "badge_cls": cls,
        "zone": [(30, _Z_G), (10, _Z_G2), (20, _Z_Y), (20, _Z_R), (20, _Z_R2)],
        "marker": round(max(0.0, min(50.0, p)) / 50 * 100, 1),
        "ticks": [(30, "15"), (40, "20"), (60, "30"), (80, "40")],
        **_prev_mark(prev, max(0.0, min(50.0, prev)) / 50 * 100 if prev is not None else None,
                     p, f"어제 {prev:.2f}" if prev is not None else ""),
        "mean": "S&amp;P 500이 앞으로 30일 얼마나 흔들릴지 옵션 값으로 잰 거예요. <b>30을 넘으면 불안 구간</b>이에요.",
        "when": "",
    }


HY_WARN_CHG = 0.50    # 10거래일 확대 경고(%p)
HY_STRONG_LEVEL = 5.0  # 이 수준 위에서 더 벌어지면 강한 경고(%p)


def hy_state(value: float, chg10: float) -> tuple:
    """(라벨, 색) — 10거래일 +0.50%p 이상 경고, 5%p 이상에서 계속 벌어지면 강한 경고."""
    if value >= HY_STRONG_LEVEL and chg10 > 0:
        return "강한 경고", "r"
    if chg10 >= HY_WARN_CHG:
        return "경고", "y"
    return "확대 없음", "g"


def _hy_is_fresh(hy: dict, max_age_days: int = 7, today=None) -> bool:
    """FRED는 하루 이틀 늦게 올린다 — 7일 넘게 멈추면 수집이 죽은 것으로 보고 뺀다(§20)."""
    try:
        d = datetime.strptime(str(hy.get("asof")), "%Y-%m-%d").date()
    except ValueError:
        return False
    ref = today or datetime.now(timezone(timedelta(hours=9))).date()
    if (ref - d).days > max_age_days:
        print(f"[generate_html] ⚠️ 하이일드 스프레드가 {(ref - d).days}일 지났습니다 — 표시 생략.", file=sys.stderr)
        return False
    return True


def _hy_item(hy) -> dict:
    if not isinstance(hy, dict) or not isinstance(hy.get("value"), (int, float)) \
            or not isinstance(hy.get("chg10"), (int, float)) or not _hy_is_fresh(hy):
        return {}
    v, c = float(hy["value"]), float(hy["chg10"])
    lbl, cls = hy_state(v, c)
    m, d = str(hy["asof"])[5:7], str(hy["asof"])[8:10]
    when = f"{int(m)}/{int(d)} 기준"
    if isinstance(hy.get("pct_above"), (int, float)):
        when += f" · 지난 3년 중 이보다 높았던 날 {hy['pct_above']:.0f}%"
    return {
        "key": "hy", "name": "하이일드 스프레드", "info_modal": "hy-modal",
        "val": f"{v:.2f}%",
        "chg": (f"전일 {hy['prev_value']:.2f}% · " if isinstance(hy.get("prev_value"), (int, float)) else "")
               + f"10거래일 {'+' if c >= 0 else '−'}{abs(c):.2f}%p",
        "badge": lbl, "badge_cls": cls,
        "zone": [(50, _Z_G), (50, _Z_Y)],
        "marker": round(max(0.0, min(1.0, c)) * 100, 1),
        "ticks": [(0, "0"), (50, "+0.50%p 경고"), (100, "+1.0")],
        **_prev_mark(hy.get("prev_chg10"),
                     max(0.0, min(1.0, float(hy["prev_chg10"]))) * 100
                     if isinstance(hy.get("prev_chg10"), (int, float)) else None,
                     c, (f"전일 {'+' if hy['prev_chg10'] >= 0 else '−'}{abs(hy['prev_chg10']):.2f}%p")
                     if isinstance(hy.get("prev_chg10"), (int, float)) else ""),
        "mean": "신용이 낮은 미국 기업이 국채보다 더 얹어 내는 이자예요. "
                "<b>10거래일에 0.5%p 넘게 벌어지면 돈줄이 마른다는 경고</b>예요.",
        "when": when,
    }


# 공포·탐욕 다이얼 — 얇은 아치 위에 어제 점(빈 원)과 오늘 점을 잇는 호(2026-11-23 다이얼 3안).
_DIAL_CX, _DIAL_CY, _DIAL_R = 110, 104, 82
_FNG_BANDS = [(0, 25, "#F87171"), (25, 45, "#FBBF24"), (45, 55, "#4ADE80"), (55, 75, "#FBBF24"), (75, 100, "#F87171")]


def _dial_pt(score: float, r: float) -> tuple:
    a = math.pi * (1 - score / 100)
    return (_DIAL_CX + r * math.cos(a), _DIAL_CY - r * math.sin(a))


def _dial_arc(s0: float, s1: float, r: float = _DIAL_R) -> str:
    """s0→s1 점수 구간의 호(작은 점수 → 큰 점수, 시계 방향)."""
    lo, hi = min(s0, s1), max(s0, s1)
    a, b = _dial_pt(lo, r), _dial_pt(hi, r)
    return f"M{a[0]:.1f} {a[1]:.1f} A{r} {r} 0 0 1 {b[0]:.1f} {b[1]:.1f}"


def _dial_move(s0: float, s1: float, r: float = _DIAL_R - 15) -> str:
    """어제(s0) → 오늘(s1) 화살표 호. 트랙 안쪽 반지름에 그려 점과 겹치지 않게 하고,
    끝(오늘 쪽)을 조금 줄여 화살촉이 점에 닿지 않게 한다."""
    trim = min(1.5, abs(s1 - s0) / 3)
    e = s1 - trim if s1 > s0 else s1 + trim
    a, b = _dial_pt(s0, r), _dial_pt(e, r)
    sweep = 1 if s1 > s0 else 0
    return f"M{a[0]:.1f} {a[1]:.1f} A{r} {r} 0 0 {sweep} {b[0]:.1f} {b[1]:.1f}"


def build_fng_dial(market_data: dict, internal_type: str) -> dict:
    """공포·탐욕 지수 반원 다이얼. 데이터가 없거나 낡았으면 빈 dict → 섹션 생략(§0).

    어제 점과 오늘 점을 아치 위에 찍고 그 사이를 호로 잇는다 — 하루 사이 어느 쪽으로
    움직였는지가 보인다. 어제 값이 없거나 사실상 같으면(아래) 오늘 점만 남긴다.
    """
    if internal_type not in ("kospi", "us"):
        return {}
    mdj = market_data.get("market_data_js", {})
    fng = mdj.get("fng")
    if not isinstance(fng, dict) or not _fng_is_fresh(fng):
        return {}
    score = float(fng["score"])
    label, cls = _fng_label(score, fng.get("rating"))
    prev = fng.get("prev_close")
    s = max(0.0, min(100.0, score))
    dial = {
        "score": f"{score:.0f}",
        "state": label,
        "state_cls": cls,
        "delta": "",
        "track": _dial_arc(0, 100),
        "bands": [{"d": _dial_arc(a, b), "color": c} for a, b, c in _FNG_BANDS],
        "ticks": [],
        "today": {"x": f"{_dial_pt(s, _DIAL_R)[0]:.1f}", "y": f"{_dial_pt(s, _DIAL_R)[1]:.1f}"},
        "prev": None,
    }
    for t in (25, 45, 55, 75):
        a, b = _dial_pt(t, _DIAL_R - 9), _dial_pt(t, _DIAL_R + 9)
        dial["ticks"].append({"x1": f"{a[0]:.1f}", "y1": f"{a[1]:.1f}", "x2": f"{b[0]:.1f}", "y2": f"{b[1]:.1f}"})
    if isinstance(prev, (int, float)):
        d = score - prev
        # 표시상 0.0p가 되는 구간은 아예 비운다 — '보합'이라는 틀린 주장을 막기 위함(§0).
        # CNN은 미국 정규장이 열리기 전에 이미 직전 종가를 previous_close로 넘기는데,
        # 새 세션 값은 아직 없어 score와 previous_close가 **완전히 같아진다**. 미국 브리핑은
        # 21:15 KST(= 프리마켓)에 나가므로 이 구간에 정확히 걸리고, 비우지 않으면 매일
        # '+0.0p'가 찍힌다(2026-08-31 확인).
        if abs(d) >= 0.05:
            ps = max(0.0, min(100.0, float(prev)))
            pp = _dial_pt(ps, _DIAL_R)
            lp = _dial_pt(ps, _DIAL_R + 12)
            dial["delta"] = f"{'+' if d >= 0 else '−'}{abs(d):.1f}p"
            dial["prev"] = {
                "x": f"{pp[0]:.1f}", "y": f"{pp[1]:.1f}",
                "move": _dial_move(ps, s),
                "lx": f"{lp[0]:.1f}", "ly": f"{lp[1] - 2:.1f}",
                "anchor": "end" if lp[0] < _DIAL_CX else "start",
                "label": f"어제 {prev:.1f}",
            }
    return dial


# CNN 등급 → 한국어 라벨. 뱃지 색은 기존 vix-badge 팔레트를 재사용한다 —
# 공포·탐욕은 양쪽 끝이 모두 위험 구간이라 극단을 red(high), 그 안쪽을 yellow(elevated),
# 중립을 green(calm)으로 둔다.
_FNG_RATING_KO = {
    "extreme fear":  ("극단적 공포", "high"),
    "fear":          ("공포", "elevated"),
    "neutral":       ("중립", "calm"),
    "greed":         ("탐욕", "elevated"),
    "extreme greed": ("극단적 탐욕", "high"),
}


def _fng_label(score: float, rating) -> tuple:
    """CNN이 준 등급을 우선 쓰고, 없거나 모르는 값이면 점수 구간으로 되돌린다."""
    hit = _FNG_RATING_KO.get((rating or "").strip().lower())
    if hit:
        return hit
    for upper, key in ((25, "extreme fear"), (45, "fear"), (55, "neutral"), (75, "greed")):
        if score < upper:
            return _FNG_RATING_KO[key]
    return _FNG_RATING_KO["extreme greed"]


def _fng_is_fresh(fng: dict, max_age_days: int = 5, now=None) -> bool:
    """수집이 조용히 죽었을 때 낡은 값을 계속 보여주지 않기 위한 신선도 게이트(§20).

    CNN은 미국 정규장 기준으로 갱신되므로 주말·연휴엔 며칠 묵는 게 정상이다.
    3일 연휴 + 주말을 감안해 5일까지 허용하고, 그보다 오래되면 행을 그리지 않는다.
    """
    if not isinstance(fng.get("score"), (int, float)):
        return False
    asof = fng.get("asof")
    if not asof:
        print("[generate_html] ⚠️ 공포·탐욕 지수에 수집 시각이 없어 표시하지 않습니다.", file=sys.stderr)
        return False
    try:
        ts = datetime.fromisoformat(str(asof).replace("Z", "+00:00"))
    except ValueError:
        print(f"[generate_html] ⚠️ 공포·탐욕 지수 시각 파싱 실패: {asof}", file=sys.stderr)
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ref = now or datetime.now(timezone.utc)
    age_days = (ref - ts).total_seconds() / 86400.0
    if age_days > max_age_days:
        print(f"[generate_html] ⚠️ 공포·탐욕 지수가 {age_days:.1f}일 지났습니다 — 표시 생략.",
              file=sys.stderr)
        return False
    return True


def build_analyst_quotes(data: dict) -> dict:
    """월가 애널리스트 발언 섹션 컨텍스트 빌더.

    url(grounding에서 리졸브된 원본 기사 링크)이 없는 항목은 표시하지 않는다.
    구글 검색 폴백 링크는 실제 발언 근거를 확인할 수 없다는 뜻이라, 검증 안 된
    멘트를 노출하는 셈이 된다 — 차라리 그 항목만 조용히 제외한다(섹션 자체는
    나머지 검증된 발언이 있으면 유지).
    """
    quotes_path = BASE_DIR / "data" / "analyst_quotes.json"
    if quotes_path.exists():
        with open(quotes_path, encoding="utf-8") as f:
            raw_quotes = json.load(f)
    else:
        raw_quotes = []
    analyst_quotes = []
    for q in raw_quotes:
        if not q.get("url"):
            continue
        q["search_url"] = q["url"]
        analyst_quotes.append(q)
    return {"analyst_quotes": analyst_quotes}


def build_accuracy(internal_type: str) -> dict:
    bpath = DATA_DIR / "briefings.json"
    if not bpath.exists():
        return {}
    # 코스피는 시초가 기준 기록만 센다(§57). 표본 5건 미만이면 상자를 그리지 않는다 —
    # 전환 직후 "1건 중 1건 100%"처럼 뜻 없는 숫자를 내보내지 않는다.
    data = stats_rows(load_json(bpath).get("briefings", []))
    src = SRC_TYPE.get(internal_type, internal_type)
    typed = [b for b in data if b.get("type") in (internal_type, src) and b.get("is_correct") is not None]
    if not typed or (internal_type == "kospi" and len(typed) < 5):
        return {}
    r30, r7 = typed[-30:], typed[-7:]

    def pct(lst):
        return round(sum(1 for b in lst if b["is_correct"]) / len(lst) * 100) if lst else 0

    hit = sum(1 for b in r30 if b["is_correct"])
    miss = len(r30) - hit
    pending = sum(1 for b in data if b.get("type") in (internal_type, src) and b.get("is_correct") is None)
    total = max(hit + miss + pending, 1)
    return {
        "acc_7d_pct": pct(r7), "acc_30d_pct": pct(r30),
        "hit": hit, "miss": miss, "pending": pending,
        "hit_pct": round(hit / total * 100), "miss_pct": round(miss / total * 100),
        "pending_pct": round(pending / total * 100),
    }


def _baseline_pct(rows: list) -> int:
    """구간 내 실제 상승일 비율(%). '매일 상승이라고만 답하는 예측기'의 적중률이다.

    우리 적중률과 반드시 같은 표본이어야 비교가 성립하므로, 미채점 항목은
    여기서도 직접 걸러낸다(호출자 필터링에 의존하지 않는다).
    상승 판정은 채점 로직(check_accuracy)이 기록한 actual_direction을 그대로 쓴다."""
    scored = [b for b in rows if b.get("is_correct") is not None]
    if not scored:
        return 0
    up = sum(1 for b in scored if b.get("actual_direction") == "상승")
    return round(up / len(scored) * 100)


def _edge_cls(edge: int) -> str:
    """우위 폭(%p) → 게이지 채움 색. ±10%p를 경계로 둔다.

    최근 15건 기준 1건이 6.7%p라 한 자릿수 차이는 표본 노이즈다. 경계를 0에 두면
    +3%p 같은 사실상 무차이를 초록으로 칠해 없는 우위를 주장하게 된다."""
    if edge >= 10:
        return "good"
    if edge <= -10:
        return "bad"
    return "flat"


def _legacy_close_summary(all_rows: list, internal_type: str) -> dict:
    """전환 이전 종가 기준 코스피 기록의 건수·적중률. 코스피가 아니거나 기록이 없으면 빈 dict."""
    if internal_type != "kospi":
        return {}
    legacy = [b for b in legacy_kospi_rows(all_rows) if b.get("is_correct") is not None]
    if not legacy:
        return {}
    hit = sum(1 for b in legacy if b["is_correct"])
    return {"sc_legacy_count": len(legacy), "sc_legacy_pct": round(hit / len(legacy) * 100),
            "sc_legacy_until": max(b["date"] for b in legacy)}


def build_scorecard(internal_type: str) -> dict:
    """예측 성적표(카드+더보기 모달) 컨텍스트. briefings.json의 실측 채점값(is_correct)만 사용.
    월별 적중률·최근 결과는 모두 실데이터 집계 — 사후 '복기 사유' 서술은 저장돼 있지 않으므로
    생성하지 않고 사실(예측→실제)만 표시한다(데이터 정합성 철칙)."""
    bpath = DATA_DIR / "briefings.json"
    if not bpath.exists():
        return {}
    all_rows = load_json(bpath).get("briefings", [])
    rows = stats_rows(all_rows)               # 코스피는 시초가 기준 기록만(§57)
    src = SRC_TYPE.get(internal_type, internal_type)
    typed = [b for b in rows if b.get("type") in (internal_type, src)]
    scored = [b for b in typed if b.get("is_correct") is not None]
    if len(scored) < 5:                       # 표본이 너무 적으면 카드 생략
        return {}

    def pct(lst):
        return round(sum(1 for b in lst if b["is_correct"]) / len(lst) * 100) if lst else 0

    def cls(p):                               # accuracy.html의 acc_cls와 동일 규칙
        return "good" if p >= 70 else ("mid" if p >= 50 else "bad")

    r15 = scored[-15:]
    r15_pct = pct(r15)
    cum_pct = pct(scored)
    r15_base = _baseline_pct(r15)
    cum_base = _baseline_pct(scored)
    # 우위는 원본 실수 차이가 아니라 화면에 뜬 반올림값끼리의 차이로 구한다 —
    # 사용자가 73 − 53을 암산했을 때 표시된 +20%p와 어긋나면 안 된다.
    r15_edge = r15_pct - r15_base
    cum_edge = cum_pct - cum_base
    hits = [b for b in scored if b["is_correct"]]
    hit_avg = (sum(abs(outcome_pct(b) or 0) for b in hits) / len(hits)) if hits else 0

    # 최근 30건 기준 적중/오류/미결 막대
    r30 = scored[-30:]
    hit30 = sum(1 for b in r30 if b["is_correct"])
    miss30 = len(r30) - hit30
    pending = sum(1 for b in typed if b.get("is_correct") is None)
    total = max(hit30 + miss30 + pending, 1)

    # 월별 적중률 (최근 5개월) — 같은 달 기준선을 함께 실어 진 달이 드러나게 한다
    from collections import defaultdict
    mon = defaultdict(list)
    for b in scored:
        mon[b["date"][:7]].append(b)
    monthly = []
    for mkey in sorted(mon)[-5:]:
        rows_m = mon[mkey]
        p = pct(rows_m)
        monthly.append({
            "label": f"{int(mkey[5:7])}월",
            "pct": p,
            "cls": cls(p),
            "base_pct": _baseline_pct(rows_m),
        })

    # 최근 결과 (맞은 날·틀린 날 그대로, 사실만)
    dows = ["월", "화", "수", "목", "금", "토", "일"]
    recent = []
    for b in reversed(scored[-6:]):
        try:
            dt = datetime.strptime(b["date"], "%Y-%m-%d")
            dlabel = f"{dt.month}/{dt.day} ({dows[dt.weekday()]})"
        except Exception:
            dlabel = b.get("date", "")
        d = b.get("predicted_direction", "")
        pred_word = "상승 예측" if "상승" in d else ("하락 예측" if "하락" in d else "중립 예측")
        chg = outcome_pct(b)
        chg_str = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "—"
        recent.append({
            "date_label": dlabel,
            "pred_word": pred_word,
            "actual": chg_str,
            "ok": bool(b["is_correct"]),
        })

    return {
        # 채점이 15건이 되기 전엔 '최근 15건'이 누적과 같은 표본이라 숨긴다(2026-10-26 — 9건인데 '최근 15건'으로 표시됐다)
        "sc_show_recent15": len(scored) >= 15,
        "sc_recent15_pct": r15_pct,
        "sc_recent15_cls": cls(r15_pct),
        "sc_cum_pct": cum_pct,
        "sc_cum_cls": cls(cum_pct),
        "sc_cum_count": len(scored),
        # 전환 이전 종가 기준 기록 — 통계엔 안 넣고 모달에 사실만 적는다(§57)
        **_legacy_close_summary(all_rows, internal_type),
        # 기준선 = 매일 '상승'이라고만 답했을 때의 적중률
        "sc_recent15_base": r15_base,
        "sc_recent15_edge": r15_edge,
        "sc_recent15_gcls": _edge_cls(r15_edge),
        "sc_cum_base": cum_base,
        "sc_cum_edge": cum_edge,
        "sc_cum_gcls": _edge_cls(cum_edge),
        "sc_hit_avg": f"{hit_avg:.1f}%",
        "sc_hit": hit30, "sc_miss": miss30, "sc_pending": pending,
        "sc_hit_pct": round(hit30 / total * 100),
        "sc_miss_pct": round(miss30 / total * 100),
        "sc_pending_pct": round(pending / total * 100),
        "sc_monthly": monthly,
        "sc_recent": recent,
    }
