#!/usr/bin/env python3
# Claude 분석 결과(analysis_*.json)의 수치·본문을 실측·규칙으로 검증·교정하는 발행 게이트
"""
call_claude → [validate_analysis] → generate_html 사이에서 동작.

- 교정 가능: analysis_*.json 제자리 교정 후 저장 (exit 0)
- 치명적/교정 불가: exit 1 + 관리자 텔레그램 알림 (발행 중단)

설계: docs/superpowers/specs/2026-06-02-analysis-validation-gate-design.md
"""
import argparse
import copy
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

LATEST_FILE = {
    "kospi": "latest_kospi.json",
    "us": "latest_us.json",
    "kospi-close": "latest_kospi_close.json",
}

# 본문 스캔: 타입별 스칼라 필드(위반 시 차단) / 리스트 필드(원소 제거)
SCALAR_PROSE = {
    "kospi-close": ["market_summary", "why", "what", "so_what"],
    "kospi": [],
    "us": [],
}
# 헤드라인은 검사 제외
EXCLUDED_FIELDS = {"reason_title", "market_title"}

# 교정 임계치
PRICE_TOLERANCE = 0.05      # 종목 가격 ±5% 초과 이탈 시 교정
FX_MIN, FX_MAX = 1000, 2000  # 원/달러 환율 정상 범위
INDEX_PCT_MAX = 30.0         # 지수 일간 등락률 절대값 상한
REASONS_MIN = 2             # 교정 후 남아야 할 최소 reasons 수

# ── 패턴 ──────────────────────────────────────────────────────────────────────
# 숫자+경 (뒤에 한글 음절이 없을 때만 — '경기/경제/경우' 오탐 방지)
GYEONG_RE = re.compile(r"\d[\d,]*\s*경(?![가-힣])")
HWANYUL_CTX_RE = re.compile(r"(환율|원\s*/\s*달러|원달러)")
WON_NUM_RE = re.compile(r"([\d,]+)\s*원")
INDEX_CTX_RE = re.compile(r"(코스피|코스닥)")
PCT_NUM_RE = re.compile(r"([+-][\d.]+)\s*%")


def parse_price(s):
    """'53,600원' / '$53.60' / 53600 → float. 파싱 불가 시 None."""
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    m = re.search(r"[-+]?[\d,]*\.?\d+", s.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def strip_tags(text):
    """<b> 등 HTML 태그 제거 (패턴 스캔 시 태그 경계로 인한 누락 방지)."""
    return re.sub(r"<[^>]+>", "", text or "")


def find_forbidden(text):
    """본문 문자열에서 금지 패턴을 찾아 사유 리스트를 반환한다 (없으면 빈 리스트)."""
    if not isinstance(text, str) or not text:
        return []
    t = strip_tags(text)
    reasons = []

    if GYEONG_RE.search(t):
        reasons.append("금지 단위 '경'(시총/금액)")

    # 환율: 환율 키워드 인근(뒤 20자) 원-숫자가 정상 범위 밖
    for m in HWANYUL_CTX_RE.finditer(t):
        win = t[m.end():m.end() + 20]
        wn = WON_NUM_RE.search(win)
        if wn:
            val = parse_price(wn.group(1))
            if val is not None and not (FX_MIN <= val <= FX_MAX):
                reasons.append(f"환율 범위 이탈({val:.0f}원)")
            break

    # 지수 등락률: 코스피/코스닥 인근(앞뒤 25자) % 절대값 30 초과
    for m in INDEX_CTX_RE.finditer(t):
        win = t[max(0, m.start() - 25):m.end() + 25]
        for pm in PCT_NUM_RE.finditer(win):
            val = parse_price(pm.group(1))
            if val is not None and abs(val) > INDEX_PCT_MAX:
                reasons.append(f"지수 등락률 비정상({val:+.1f}%)")
        if reasons and reasons[-1].startswith("지수"):
            break

    return reasons


# ── 종목 후보(실측) 수집·매칭 ──────────────────────────────────────────────────
def collect_candidates(latest, btype):
    """latest_*.json에서 {name/ticker → {price, change_pct}} 매칭용 리스트를 모은다."""
    out = []
    keys = ["kospi_candidates"] if btype == "kospi" else (["us_candidates"] if btype == "us" else [])
    for k in keys:
        out.extend(latest.get(k, []) or [])
    # 섹터 대표 종목 (kospi 모닝)
    for sec in (latest.get("sector_stocks") or {}).values():
        out.extend(sec.get("stocks", []) or [])
    return out


def match_candidate(pick, candidates):
    """pick.name/ticker가 후보의 name/ticker를 포함하면 매칭(실측 dict 반환)."""
    name = pick.get("name", "") or ""
    tk = pick.get("ticker", "") or ""
    for c in candidates:
        cn, ct = c.get("name", "") or "", c.get("ticker", "") or ""
        if (cn and (cn in name or cn == tk)) or (ct and (ct in name or ct == tk)):
            if c.get("price") is not None:
                return c
    return None


def _fmt_chg(v):
    return f"{'+' if v >= 0 else ''}{v:.2f}%"


# ── 픽 종목 실측 주입 (yfinance 직접 fetch) ───────────────────────────────────
# Claude는 후보 풀과 무관하게 종목을 자유 선택하므로, 사전 수집된 candidate가
# 대부분 비어 있다. 픽된 종목의 ticker를 직접 fetch해 price·change·MA·sparkline을
# 실측으로 덮어쓰고, generate_html이 읽는 candidate 리스트에도 주입한다.

def _resolve_ticker(pick, btype):
    """pick → 조회용 식별자. 해석 불가 시 빈 문자열.

    - us: 영문 티커(예: NVDA) — yfinance용.
    - kospi: 6자리 종목코드(예: 005930) — 네이버 일봉용. .KS/.KQ 접미사는 붙이지
      않는다. yfinance에 .KS를 붙이면 KOSDAQ 종목이 유령 데이터(하루 stale·오价)를
      반환해 잘못된 가격이 주입되기 때문. 네이버는 코드만으로 시장을 정확히 식별한다.
    """
    tk = (pick.get("ticker") or "").strip()
    name = pick.get("name") or ""
    if btype == "us":
        sym = tk or (name.split("(")[0].strip().split()[0] if name else "")
        # 미국 티커: 영문 대문자 1~5자
        return sym if re.fullmatch(r"[A-Z]{1,5}", sym or "") else ""
    # kospi / kospi-close: 6자리 종목코드 (접미사 없음)
    code = (tk.split(".")[0] if tk else "").strip()
    return code if code.isdigit() and len(code) == 6 else ""


def _inject_candidate(cands, clean_ticker, name, data):
    """generate_html sparkline 매칭용 candidate 항목을 주입/갱신한다."""
    entry = {
        "ticker": clean_ticker,
        "name": name,
        "price": data["price"],
        "change_pct": data["change_pct"],
        "ma20_dist_pct": data.get("ma20_dist_pct"),
        "ma200_dist_pct": data.get("ma200_dist_pct"),
        "sparkline": data.get("sparkline", []),
        "ma20_sparkline": data.get("ma20_sparkline", []),
        "ma200_sparkline": data.get("ma200_sparkline", []),
    }
    for i, c in enumerate(cands):
        if c.get("ticker") == clean_ticker or c.get("name") == name:
            cands[i] = entry
            return
    cands.append(entry)


def _closes_to_realdata(closes, ndigits):
    """일봉 종가 리스트(오래된→최신)로 실측 dict를 만든다.
    '전일 등락률' = close[-1] vs close[-2] (실시간 장중가 아님).
    """
    if len(closes) < 2:
        return {"error": "insufficient data"}
    price, prev = closes[-1], closes[-2]
    r = (lambda v: round(v, ndigits))
    out = {
        "price": r(price),
        "change_pct": round((price - prev) / prev * 100, 4),
        "sparkline": [r(x) for x in closes[-20:]],
    }

    def _ma_series(window):
        # 마지막 20개 지점의 이동평균(데이터 부족 시 윈도우 clamp)
        return [sum(closes[max(0, i - window + 1):i + 1]) / len(closes[max(0, i - window + 1):i + 1])
                for i in range(len(closes) - 20, len(closes))]

    if len(closes) >= 20:
        ma20 = _ma_series(20)
        out["ma20_dist_pct"] = round((price - ma20[-1]) / ma20[-1] * 100, 2)
        out["ma20_sparkline"] = [r(v) for v in ma20]
    if len(closes) >= 200:
        ma200 = _ma_series(200)
        out["ma200_dist_pct"] = round((price - ma200[-1]) / ma200[-1] * 100, 2)
        out["ma200_sparkline"] = [r(v) for v in ma200]
    return out


def _fetch_us_realdata(ticker):
    """yfinance 일봉으로 미국 종목 실측을 계산한다."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="300d").dropna(subset=["Close"])
        closes = [float(x) for x in hist["Close"].tolist()]
        return _closes_to_realdata(closes, ndigits=4)
    except Exception as e:
        return {"error": str(e)}


def _fetch_kospi_realdata(code):
    """네이버 일봉으로 한국 종목 실측을 계산한다 (6자리 코드만으로 시장 자동 식별).
    yfinance .KS/.KQ 추측의 오价·stale 문제를 피하기 위해 네이버를 단일 소스로 쓴다.
    """
    import urllib.request
    from datetime import datetime, timedelta
    try:
        end = datetime.now().strftime("%Y%m%d") + "0000"
        start = (datetime.now() - timedelta(days=420)).strftime("%Y%m%d") + "0000"
        url = (f"https://api.stock.naver.com/chart/domestic/item/{code}/day"
               f"?startDateTime={start}&endDateTime={end}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read())
        closes = [float(rw["closePrice"]) for rw in rows if rw.get("closePrice")]
        return _closes_to_realdata(closes, ndigits=2)
    except Exception as e:
        return {"error": str(e)}


def _fetch_pick_realdata(ticker, is_us):
    """픽 종목 실측 fetch. 미국=yfinance, 한국=네이버 일봉."""
    return _fetch_us_realdata(ticker) if is_us else _fetch_kospi_realdata(ticker)


def enrich_picks_with_realdata(analysis, latest, btype, corrections, warnings):
    """픽된 종목의 실측 데이터를 fetch해 analysis·latest(candidate)에 주입한다.
    Returns: latest가 변경됐는지(bool).
    """
    picks = analysis.get("stock_picks")
    if not isinstance(picks, list) or not picks:
        return False
    if btype not in ("kospi", "us"):
        return False

    is_us = btype == "us"
    cand_key = "us_candidates" if is_us else "kospi_candidates"
    cands = latest.setdefault(cand_key, [])
    changed = False

    for p in picks:
        tk = _resolve_ticker(p, btype)
        if not tk:
            warnings.append(f"종목 '{p.get('name')}' 티커 해석 실패 — 실측 주입 생략")
            continue
        data = _fetch_pick_realdata(tk, is_us)
        if "error" in data or data.get("price") is None:
            warnings.append(f"종목 '{p.get('name')}'({tk}) 실측 fetch 실패: {data.get('error', 'no price')}")
            continue

        price, chg = data["price"], data["change_pct"]
        old_chg = p.get("change")
        p["price"] = f"${price:,.2f}" if is_us else f"{int(round(price)):,}원"
        p["change"] = _fmt_chg(chg)
        p["change_cls"] = "up" if chg >= 0 else "down"
        if data.get("ma200_dist_pct") is not None:
            p["ma200_dist_pct"] = data["ma200_dist_pct"]
        if data.get("ma20_dist_pct") is not None:
            p["ma20_dist_pct"] = data["ma20_dist_pct"]

        _inject_candidate(cands, tk, p.get("name", ""), data)
        changed = True
        corrections.append(
            f"종목 '{p.get('name')}'({tk}) 실측 주입: change {old_chg} → {p['change']}, price {p['price']}"
        )

    return changed


def correct_pick_price(pick, gt, corrections, is_us=False):
    """pick 가격이 실측과 ±5% 초과 이탈하면 price·change·entry/target/stop를 교정.

    is_us는 btype에서 직접 전달받는다. Claude 원본 가격 문자열('$' 유무)로
    판정하면 '$' 없는 미국 가격 형식("130달러" 등)에서 오판할 수 있다.
    """
    cur = parse_price(pick.get("price"))
    gt_price = gt.get("price")
    if cur is None or not gt_price or cur <= 0:
        return
    if abs(cur - gt_price) / gt_price <= PRICE_TOLERANCE:
        return

    new_price = f"${gt_price:,.2f}" if is_us else f"{int(round(gt_price)):,}원"
    ratio = gt_price / cur

    old = pick.get("price")
    pick["price"] = new_price
    chg = gt.get("change_pct")
    if chg is not None:
        pick["change"] = _fmt_chg(chg)
        pick["change_cls"] = "up" if chg >= 0 else "down"

    # 진입/목표/손절: 같은 비율로 스케일 (파싱 가능할 때만)
    for fld in ("entry", "target", "stop"):
        raw = pick.get(fld)
        v = parse_price(raw)
        if v is not None and isinstance(raw, str):
            scaled = v * ratio
            pick[fld] = f"${scaled:,.2f}" if is_us else f"{int(round(scaled)):,}원"

    corrections.append(f"종목 '{pick.get('name')}' 가격 교정: {old} → {new_price} (실측 대비 교차검증)")


def forbidden_in_pick(pick):
    """stock_pick의 서술형 본문(scenario·action_guide)에서 금지 패턴 탐지."""
    bad = []
    for fld in ("scenario", "action_guide"):
        bad.extend(find_forbidden(pick.get(fld)))
    return bad


def _filter_list_prose(items, label, corrections):
    """리스트형 본문 원소 중 금지 패턴이 있는 것을 제거하고, 남은 리스트를 반환."""
    if not isinstance(items, list):
        return items, 0
    kept, removed = [], 0
    for it in items:
        text = it if isinstance(it, str) else (it.get("text", "") if isinstance(it, dict) else "")
        bad = find_forbidden(text)
        if bad:
            corrections.append(f"{label} 원소 제거: {bad}")
            removed += 1
            continue
        kept.append(it)
    return kept, removed


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


# ── 검증 본체 ─────────────────────────────────────────────────────────────────
def validate(analysis, latest, btype):
    """analysis를 검증·교정한다.

    Returns dict: {analysis(교정본), corrections[], warnings[], blocks[]}
    blocks 비어있지 않으면 발행 차단.
    """
    a = copy.deepcopy(analysis)
    corrections, warnings, blocks = [], [], []

    # 1) 구조 필드 — 예측형 브리핑(kospi/us)만. 마감(kospi-close)은 예측 필드가 없는 시황 요약이라 제외.
    if btype in ("kospi", "us"):
        pred = a.get("prediction") or {}
        up = pred.get("up_pct")
        if not isinstance(up, (int, float)) or isinstance(up, bool) or not (0 <= up <= 100):
            blocks.append(f"prediction.up_pct 비정상: {up!r}")
        if not pred.get("direction"):
            blocks.append("prediction.direction 누락")

    # 2) 계층 1 + stock_picks 본문
    picks = a.get("stock_picks")
    is_us = btype == "us"
    if isinstance(picks, list) and picks:
        cands = collect_candidates(latest, btype)
        kept = []
        for p in picks:
            bad = forbidden_in_pick(p)
            if bad:
                corrections.append(f"종목 '{p.get('name')}' 제거: {bad}")
                continue
            gt = match_candidate(p, cands)
            if gt:
                correct_pick_price(p, gt, corrections, is_us=is_us)
            else:
                warnings.append(f"종목 '{p.get('name')}' 실측 매칭 실패 — 가격 교차검증 생략")
            kept.append(p)
        if not kept:
            blocks.append("stock_picks 전부 제거됨 (브리핑 빈약)")
        a["stock_picks"] = kept

    # 3) 계층 2 — 리스트형 본문
    if isinstance(a.get("reasons"), list):
        kept, _ = _filter_list_prose(a["reasons"], "reasons", corrections)
        a["reasons"] = kept
        if len(kept) < REASONS_MIN:
            blocks.append(f"reasons가 {len(kept)}개로 과소 (최소 {REASONS_MIN})")
    if isinstance(a.get("watch_items"), list):
        a["watch_items"], _ = _filter_list_prose(a["watch_items"], "watch_items", corrections)
    sf = a.get("sector_focus")
    if isinstance(sf, dict):
        if isinstance(sf.get("paragraphs"), list):
            kept, _ = _filter_list_prose(sf["paragraphs"], "sector_focus.paragraphs", corrections)
            sf["paragraphs"] = kept
            if not kept:
                blocks.append("sector_focus.paragraphs 전부 제거됨")
        # signal 필드: 30자 이내 한 문장 — 금지 패턴 감지 시 경고만(필수 필드라 제거 불가)
        if isinstance(sf.get("signal"), str):
            bad = find_forbidden(sf["signal"])
            if bad:
                warnings.append(f"sector_focus.signal 금지 패턴 감지 (수동 확인 필요): {bad}")

    # sector_semicon (us 전용) — paragraphs·signal 검증
    ss = a.get("sector_semicon")
    if isinstance(ss, dict):
        if isinstance(ss.get("paragraphs"), list):
            kept, _ = _filter_list_prose(ss["paragraphs"], "sector_semicon.paragraphs", corrections)
            ss["paragraphs"] = kept
        if isinstance(ss.get("signal"), str):
            bad = find_forbidden(ss["signal"])
            if bad:
                warnings.append(f"sector_semicon.signal 금지 패턴 감지 (수동 확인 필요): {bad}")

    # 3-b) telegram_signals — 텔레그램 직송 문자열이므로 모든 타입에서 검증
    if isinstance(a.get("telegram_signals"), list):
        a["telegram_signals"], _ = _filter_list_prose(
            a["telegram_signals"], "telegram_signals", corrections
        )

    # 4) 계층 2 — 스칼라 본문 (금지 문장 제거 후 계속 발행)
    for fld in SCALAR_PROSE.get(btype, []):
        if fld in EXCLUDED_FIELDS:
            continue
        text = a.get(fld)
        if not isinstance(text, str) or not text:
            continue
        bad = find_forbidden(text)
        if not bad:
            continue
        # 금지 패턴을 포함한 문장만 제거
        import re as _re
        sentences = _re.split(r'(?<=[.!?요])\s+', text)
        kept = [s for s in sentences if not find_forbidden(s)]
        if kept:
            a[fld] = " ".join(kept)
            corrections.append(f"본문 '{fld}' 금지 문장 제거: {bad}")
        else:
            # 전체가 금지 패턴인 경우 필드 삭제
            a[fld] = ""
            warnings.append(f"본문 '{fld}' 전체 제거 (금지 패턴 {bad})")

    # 5) 수급 수치 스케일 크로스체크 (kospi-close only)
    if btype == "kospi-close":
        _check_supply_scale(a, latest, warnings)

    return {"analysis": a, "corrections": corrections, "warnings": warnings, "blocks": blocks}


# ── 관리자 알림 ───────────────────────────────────────────────────────────────
def send_admin_alert(message):
    """차단 시 관리자 텔레그램으로 알림. 키 미설정이면 조용히 건너뜀(차단은 유지)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if not token or not chat_id:
        print("[validate] 관리자 알림 키 미설정 — 알림 건너뜀 (차단은 유지)", file=sys.stderr)
        return
    try:
        data = urllib.parse.urlencode({
            "chat_id": chat_id, "text": message, "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=10)
        print("[validate] 관리자 알림 발송 완료", file=sys.stderr)
    except Exception as e:
        print(f"[validate] 관리자 알림 실패: {e}", file=sys.stderr)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="분석 결과 검증·교정 게이트")
    parser.add_argument("--type", choices=["kospi", "us", "kospi-close"], required=True)
    args = parser.parse_args()
    btype = args.type

    analysis_path = DATA_DIR / f"analysis_{btype}.json"
    latest_path = DATA_DIR / LATEST_FILE[btype]

    if not analysis_path.exists():
        print(f"[validate] {analysis_path} 없음 — 검증 건너뜀", file=sys.stderr)
        return 0
    analysis = load_json(analysis_path)
    latest = load_json(latest_path) if latest_path.exists() else {}

    # 0) 픽 종목 실측 주입 (yfinance 직접 fetch — 깨진/빈약한 candidate 풀 우회)
    pre_corrections, pre_warnings = [], []
    latest_changed = enrich_picks_with_realdata(
        analysis, latest, btype, pre_corrections, pre_warnings
    )
    if latest_changed and latest_path.exists():
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(latest, f, ensure_ascii=False, indent=2)
        print(f"[validate] ✓ candidate 실측 주입 후 저장 → {latest_path}")

    result = validate(analysis, latest, btype)
    result["corrections"] = pre_corrections + result["corrections"]
    result["warnings"] = pre_warnings + result["warnings"]

    for w in result["warnings"]:
        print(f"[validate] ⚠️  {w}")
    for c in result["corrections"]:
        print(f"[validate] 🔧 교정: {c}")

    if result["blocks"]:
        summary = "\n".join(f"  • {b}" for b in result["blocks"])
        print(f"[validate] 🚫 발행 차단 — 치명적 오류:\n{summary}", file=sys.stderr)
        send_admin_alert(
            f"🚫 <b>{btype}</b> 브리핑 발행 차단\n"
            + "\n".join(f"• {b}" for b in result["blocks"])
        )
        return 1

    # 교정본 저장 (교정 사항이 있을 때만 덮어씀)
    if result["corrections"]:
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(result["analysis"], f, ensure_ascii=False, indent=2)
        print(f"[validate] ✓ {len(result['corrections'])}건 교정 후 저장 → {analysis_path}")
    else:
        print("[validate] ✓ 검증 통과 — 교정 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
