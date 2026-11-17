# 마감 브리핑 수치 게이트 — 지수 레벨 주입·수급 금액 교정·'전종목' 과장·수급 스케일

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_text import _walk_strings, strip_tags


def _fetch_kospi_index_levels():
    """코스피 지수 실측 + 핵심 레벨(지지/저항) 산출.

    네이버 일봉 차트(`/api/kospi-live`와 동일 출처)에서 최근 5거래일 고가/저가를
    뽑아 저항=최근 5일 고가, 지지=최근 5일 저가로 계산한다. 두 값 모두 당일 종가를
    항상 사이에 두므로 현재가가 밴드를 벗어나지 않는다.

    Returns {"price","support","resistance"} or {"error":...}.
    """
    import urllib.request
    from datetime import datetime, timedelta
    try:
        end = datetime.now().strftime("%Y%m%d") + "0000"
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d") + "0000"
        url = (f"https://api.stock.naver.com/chart/domestic/index/KOSPI/day"
               f"?startDateTime={start}&endDateTime={end}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read())
        recent = rows[-5:]
        highs = [float(r["highPrice"]) for r in recent if r.get("highPrice")]
        lows = [float(r["lowPrice"]) for r in recent if r.get("lowPrice")]
        closes = [float(r["closePrice"]) for r in recent if r.get("closePrice")]
        if not highs or not lows or not closes:
            return {"error": "코스피 일봉 행 없음"}
        return {
            "price": closes[-1],
            "support": round(min(lows) / 10) * 10,
            "resistance": round(max(highs) / 10) * 10,
        }
    except Exception as e:
        return {"error": str(e)}


def inject_kospi_index_levels(analysis, corrections, warnings):
    """코스피 '핵심 레벨' watch_item의 지지/저항 num을 실측 지수 기반으로 덮어쓴다.

    LLM은 실제 코스피 지수를 입력받지 못해 학습 기억(현실 지수)으로 levels를
    채우므로, 발행 전 실측값으로 교정한다. (SERVICE_RULES 0번 원칙)
    """
    watch_key = "watch_items" if "watch_items" in analysis else "watchpoints"
    watch = analysis.get(watch_key)
    if not isinstance(watch, list):
        return
    target = next(
        (it for it in watch
         if isinstance(it, dict) and isinstance(it.get("levels"), list) and it["levels"]),
        None,
    )
    if target is None:
        return
    idx = _fetch_kospi_index_levels()
    if "error" in idx:
        warnings.append(f"코스피 핵심 레벨 실측 실패 — LLM 값 유지: {idx['error']}")
        return
    fmt = lambda n: f"{int(round(n)):,}"
    old = {lv.get("label"): lv.get("num") for lv in target["levels"]}
    for lv in target["levels"]:
        if lv.get("cls") == "dn" or lv.get("label") == "지지":
            lv.update(label="지지", num=fmt(idx["support"]), cls="dn")
        elif lv.get("cls") == "up" or lv.get("label") == "저항":
            lv.update(label="저항", num=fmt(idx["resistance"]), cls="up")
    corrections.append(
        f"코스피 핵심 레벨 실측 주입 (지지 {old.get('지지')}→{fmt(idx['support'])}, "
        f"저항 {old.get('저항')}→{fmt(idx['resistance'])}; 현재 지수 {fmt(idx['price'])})"
    )


# ── 수급 수치 스케일 크로스체크 (kospi-close) ────────────────────────────────
def _extract_eok_values(text):
    """본문에서 억원 수치를 추출한다. '6조 5,941억' → 65941, '659억' → 659."""
    t = strip_tags(text or "")
    values = set()
    # N조 M억
    for m in re.finditer(r"([\d,]+)\s*조\s*([\d,]+)\s*억", t):
        jo  = int(m.group(1).replace(",", ""))
        eok = int(m.group(2).replace(",", ""))
        values.add(jo * 10000 + eok)
    # N억 (앞 6자 안에 '조'가 없을 때만)
    for m in re.finditer(r"([\d,]+)\s*억", t):
        ctx = t[max(0, m.start() - 6):m.start()]
        if "조" not in ctx:
            values.add(int(m.group(1).replace(",", "")))
    return values


# ── 수급 금액 교정 (kospi-close, 2026-10-28 실사고) ──────────────────────────
# 10/28 마감 브리핑 요약·WHY가 "외국인 1조 1,485억원, 기관 1조 1,519억원"이라 썼는데, 같은 페이지 수급 표
# (15:40 정규장 확정 실측)는 외국인 +8,157억·기관 +9,609억이었다. 스케일(100배) 검사만 있어 그대로 통과했다.
# 본문에서 주체(외국인·기관·개인) 바로 뒤에 붙은 금액을 실측과 맞춰 고친다. 다른 날·기간 얘기
# ('어제'·'3일간'·'누적' 등)나 다른 금액(거래대금·실적 등)이 끼면 건드리지 않는다.
_SUPPLY_ACTORS = (("외국인", "foreign"), ("외인", "foreign"), ("기관", "institution"), ("개인", "individual"))
# '백만원'도 금액으로 본다(2026-11-10 — 코스피 아침 "외국인 6,895백만원"이 실제 6,895억원이었다).
_SUPPLY_AMOUNT_RE = re.compile(r"(?<![\d.])(?:([\d,]+)\s*조\s*([\d,]+)\s*억|(\d+(?:\.\d+)?)\s*조|([\d,]+)\s*억|([\d,]+)\s*백만)")
_SUPPLY_SKIP = re.compile(r"어제|전일|지난|일간|일째|누적|주간|이번\s*주|연속|거래대금|시가총액|시총|목표|매출|영업이익|순이익|\d+\s*일")
# 코스피 아침 브리핑은 실측 자체가 전 거래일 수급이라 '전일·어제·지난'을 건너뛰면 아무것도 못 고친다.
# 대신 다른 날을 가리키는 말(요일·지난주·날짜)이 끼면 건드리지 않는다 — 그 금액은 실측(전 거래일)과 다른 날 얘기다.
_SUPPLY_SKIP_MORNING = re.compile(r"[월화수목금토일]요일|지난\s*주|지난\s*달|\d+\s*/\s*\d+|일간|일째|누적|주간|이번\s*주|연속|"
                                  r"거래대금|시가총액|시총|목표|매출|영업이익|순이익|\d+\s*일")


def _fmt_eok(v):
    v = abs(int(round(v)))
    return f"{v // 10000}조 {v % 10000:,}억" if v >= 10000 else f"{v:,}억"


def _amount_value(m):
    if m.group(1):
        return int(m.group(1).replace(",", "")) * 10000 + int(m.group(2).replace(",", ""))
    if m.group(3):
        return float(m.group(3)) * 10000
    if m.group(5):
        return int(m.group(5).replace(",", "")) / 100     # 백만원 → 억원
    return int(m.group(4).replace(",", ""))


def fix_supply_amounts(analysis, latest, corrections, warnings, window=24, skip=None):
    skip = skip or _SUPPLY_SKIP
    it = (latest or {}).get("investor_trading") or {}
    actual = {}
    for _, key in _SUPPLY_ACTORS:
        net = (it.get(key) or {}).get("net")
        if isinstance(net, (int, float)):
            actual[key] = net / 100          # 백만원 → 억원(부호 유지)
    if not actual:
        return 0
    fixed = []

    def fix(text):
        out, last = [], 0
        for m in _SUPPLY_AMOUNT_RE.finditer(text):
            seg = strip_tags(text[max(0, m.start() - window):m.start()])
            seg = re.split(r"[.!?]\s", seg)[-1]          # 같은 문장 안만 본다
            hits = [(seg.rfind(w), key) for w, key in _SUPPLY_ACTORS if w in seg]
            # '어제 외국인은 …'·'3일간 외국인이 …'처럼 다른 날·기간 얘기면 건드리지 않는다(주체 앞뒤 모두 본다)
            if not hits or skip.search(seg + strip_tags(text[m.end():m.end() + 8])):
                continue
            hits.sort()
            near = hits[-1][1]
            # 사이에 다른 금액이 있으면 그 주체의 금액이 아니다
            if _SUPPLY_AMOUNT_RE.search(seg[hits[-1][0]:]):
                continue
            if near not in actual:
                continue
            both = "각각" in seg and len({k for _, k in hits}) >= 2
            keys = [k for _, k in hits if k in actual]
            keys = list(dict.fromkeys(keys))[-2:] if both else [near]
            if any(k not in actual for k in keys):
                continue
            v = _amount_value(m)
            ok = all(abs(v - abs(actual[k])) <= max(50, abs(actual[k]) * 0.03) for k in keys)
            if ok and not m.group(5):     # '백만원' 표기는 값이 맞아도 억원으로 바꿔 쓴다
                continue
            new = "·".join(_fmt_eok(actual[k]) + ("원" if both and text[m.end():m.end() + 1] == "원" and i < len(keys) - 1 else "")
                           for i, k in enumerate(keys))
            out.append(text[last:m.start()] + new)
            last = m.end()
            if both:   # '각각 X씩' → '각각 A·B' — 금액이 둘이 되면 '씩'을 뺀다(사이에 </b>가 있어도)
                tail = re.match(r"(원?(?:</b>)?)씩", text[last:])
                if tail:
                    out.append(tail.group(1)); last += tail.end()
            fixed.append(f"{m.group(0)} → {new}")
            near_txt = strip_tags(text[m.end():m.end() + 12])
            for k in keys:
                if (actual[k] > 0 and "순매도" in near_txt) or (actual[k] < 0 and "순매수" in near_txt):
                    warnings.append(f"수급 방향이 실측과 다를 수 있어요({k}): {strip_tags(text)[:60]}")
        out.append(text[last:])
        return "".join(out)

    n = _walk_strings(analysis, fix)
    if fixed:
        corrections.append(f"수급 금액을 정규장 확정 실측으로 교정 {len(fixed)}건: " + ", ".join(fixed[:4]))
    return n


# '전부'라는 말 — 실측이 전부일 때만(2026-11-10 실사고: 마감 타이틀 "코스피 전종목이 들고 일어나"·dek "전 섹터가
# 동시에 뛰며"가 나갔는데 실제로는 하락 175종목, 바이오 −1.69%였다). 문장을 다시 쓰지 않고 '대부분'으로만 바꾼다.
_ALL_STOCKS_RE = re.compile(r"전\s*종목|모든\s*종목")
_ALL_SECTORS_RE = re.compile(r"전\s*섹터|모든\s*섹터|전\s*업종|모든\s*업종")


def fix_all_claims(analysis, latest, corrections) -> int:
    mb = (latest or {}).get("market_breadth") or {}
    secs = [x.get("change_pct") for x in ((latest or {}).get("sectors") or []) if isinstance(x, dict)]
    up, down = mb.get("up"), mb.get("down")
    stocks_not_all = isinstance(up, int) and isinstance(down, int) and up > 0 and down > 0
    sectors_not_all = (any(isinstance(v, (int, float)) and v > 0 for v in secs)
                       and any(isinstance(v, (int, float)) and v < 0 for v in secs))
    if not (stocks_not_all or sectors_not_all):
        return 0
    fixed = []

    def fix(text):
        out = text
        if stocks_not_all:
            out = _ALL_STOCKS_RE.sub("대부분 종목", out)
        if sectors_not_all:
            out = _ALL_SECTORS_RE.sub("대부분 섹터", out)
        if out != text:
            fixed.append(strip_tags(text)[:40])
        return out
    n = _walk_strings(analysis, fix)
    if fixed:
        corrections.append(f"'전종목·전 섹터' 표현을 실측(상승 {up}·하락 {down}) 기준 '대부분'으로 교정 {len(fixed)}건: " + "; ".join(fixed[:3]))
    return n


def _check_supply_scale(analysis, latest, warnings):
    """마감 브리핑 분석 본문의 수급 수치 스케일을 크로스체크한다.

    investor_trading.net(백만원 → 억원 변환값)과 본문 언급 수치를 비교.
    실제 값의 1/100 수준이 언급되고 실제 값은 언급되지 않으면 WARN.
    """
    it = latest.get("investor_trading", {})
    if not it:
        return

    actuals = {}  # actor → 실제 억원(절대값)
    for actor in ("foreign", "institution", "individual"):
        net = (it.get(actor) or {}).get("net")
        if net is not None:
            eok = abs(round(net / 100))
            if eok >= 100:   # 100억 미만은 검사 실익 없음
                actuals[actor] = eok

    if not actuals:
        return

    # 분석 본문 전체에서 억원 숫자 추출
    prose = " ".join(
        analysis.get(f, "") or ""
        for f in ("market_summary", "why", "what", "so_what")
    )
    mentioned = _extract_eok_values(prose)
    if not mentioned:
        return

    LABEL = {"foreign": "외국인", "institution": "기관", "individual": "개인"}

    for actor, actual in actuals.items():
        wrong_scale = actual // 100  # 100배 축소된 잘못된 값

        # 잘못된 스케일(±40%) 언급 & 올바른 스케일(±40%) 미언급
        near_wrong   = any(abs(v - wrong_scale) / wrong_scale <= 0.4 for v in mentioned)
        near_correct = any(abs(v - actual)      / actual       <= 0.4 for v in mentioned)

        if near_wrong and not near_correct:
            fmt_actual = (
                f"{actual // 10000}조 {actual % 10000:,}억"
                if actual >= 10000 else f"{actual:,}억"
            )
            fmt_wrong = f"{wrong_scale:,}억"
            warnings.append(
                f"수급 스케일 불일치 ({LABEL[actor]}): 본문에 {fmt_wrong} 언급, "
                f"실제 {fmt_actual} — 단위 100배 오류 의심"
            )
