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


def correct_pick_price(pick, gt, corrections):
    """pick 가격이 실측과 ±5% 초과 이탈하면 price·change·entry/target/stop를 교정."""
    cur = parse_price(pick.get("price"))
    gt_price = gt.get("price")
    if cur is None or not gt_price or cur <= 0:
        return
    if abs(cur - gt_price) / gt_price <= PRICE_TOLERANCE:
        return

    is_us = "$" in (pick.get("price") or "")
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
                correct_pick_price(p, gt, corrections)
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
    if isinstance(sf, dict) and isinstance(sf.get("paragraphs"), list):
        kept, _ = _filter_list_prose(sf["paragraphs"], "sector_focus.paragraphs", corrections)
        sf["paragraphs"] = kept
        if not kept:
            blocks.append("sector_focus.paragraphs 전부 제거됨")

    # 4) 계층 2 — 스칼라 본문 (위반 시 차단)
    for fld in SCALAR_PROSE.get(btype, []):
        if fld in EXCLUDED_FIELDS:
            continue
        bad = find_forbidden(a.get(fld))
        if bad:
            blocks.append(f"본문 '{fld}' 금지 패턴: {bad} (스칼라 — 안전 교정 불가)")

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

    result = validate(analysis, latest, btype)

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
