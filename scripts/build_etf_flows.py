# 네이버 ETF 목록에서 테마별 순자금흐름(설정/환매)을 집계하는 자금 지도 파이프라인
#!/usr/bin/env python3
"""
ETF 자금 지도 파이프라인 (v1).

네이버 ETF 목록 API로 전 ETF의 AUM·NAV를 수집해 추정 좌수를 매일 스냅샷으로
저장하고, 최대 5거래일 전 스냅샷과 차분해 테마별 순자금흐름(억원)을 낸다.
가격 효과를 벗겨낸 순수 설정/환매 기준이라, "돈이 어디로 몰리나"를 보여준다.

지표:
  shares   ≈ marketSum(억원)×1e8 ÷ nav(원)          — 추정 발행좌수
  flow_eok = (shares_now − shares_prev)×nav ÷ 1e8    — 순자금흐름(억원)
  적응형 윈도우: 가진 스냅샷 만큼, 최대 5거래일 누적

정합성(SERVICE_RULES 운영규칙 0):
  - AUM 300억+ ETF만 집계(소형은 억원 반올림 노이즈가 커 제외)
  - 백필 불가(네이버는 현재 AUM만 제공) → 스냅샷 시작 이전은 계산 안 함
  - 어느 테마에도 안 잡히는 ETF는 지도에서 제외

산출:
  data/etf_flow_history.json   — 좌수 스냅샷(최근 7거래일 롤링, 커밋)
  web/data/etf-flows.json      — 테마별 순유입 + 테마별 상위 ETF (홈 블록용)

Usage:
  python3 scripts/build_etf_flows.py                    # 운영(AUM 300억+)
  python3 scripts/build_etf_flows.py --aum-floor 500    # 500억+
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

ETF_LIST_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"
ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "data" / "etf_flow_history.json"
OUT_PATH = ROOT / "web" / "data" / "etf-flows.json"

MAX_WINDOW = 5      # 최대 누적 거래일
MIN_ETFS = 100      # 정상 수집 최소치 — 이보다 적으면 얇은 응답으로 보고 히스토리 오염 방지
KEEP_DAYS = 7       # 히스토리 보관 거래일(윈도우 + 버퍼)
TOP_ETFS = 5        # 테마별 상위 ETF 노출 수

# 테마 분류 — 순서 중요(먼저 매칭되는 규칙이 이김). 'TOP'·바 '금'/'은' 같은
# 오분류 유발 키워드는 쓰지 않는다(반도체TOP10 → 배당 오분류, 은행 → 금 오분류 방지).
THEME_RULES = [
    ("반도체",          ["반도체", "HBM"]),
    ("2차전지",         ["2차전지", "배터리", "리튬"]),
    ("자동차",          ["자동차", "모빌리티"]),
    ("방산",            ["방산", "우주항공", "K방산"]),
    ("조선",            ["조선"]),
    ("바이오·헬스",      ["바이오", "헬스", "제약", "의료"]),
    ("금융·은행",        ["은행", "금융", "증권", "보험"]),
    ("인터넷·게임",      ["인터넷", "게임", "미디어", "엔터"]),
    ("원자력·전력",      ["원자력", "전력", "태양광", "신재생"]),
    ("미국 나스닥·기술",  ["나스닥", "필라델피아", "미국테크", "미국AI", "미국반도체"]),
    ("미국 S&P·대형",    ["S&P", "미국500", "미국대표", "다우"]),
    ("중국·신흥국",      ["중국", "차이나", "인도", "베트남", "신흥"]),
    ("일본·유럽",        ["일본", "유럽", "니케이"]),
    ("채권",            ["채권", "국고채", "회사채", "통안", "미국채", "CD금리", "KOFR", "단기채"]),
    ("금·원자재",        ["원유", "구리", "원자재", "WTI", "골드", "금현물", "금선물", "은선물"]),
    ("배당·커버드콜",     ["배당", "커버드콜", "인컴", "리츠", "프리미엄", "고배당", "위클리", "데일리"]),
]


def estimate_shares(marketsum_eok, nav):
    """추정 발행좌수. NAV·AUM 결측/0이면 None."""
    if not marketsum_eok or not nav or nav <= 0:
        return None
    return marketsum_eok * 1e8 / nav


def classify_theme(name):
    """ETF 이름 → 테마명. 어느 규칙에도 안 걸리면 None(지도 제외)."""
    if not name:
        return None
    for theme, kws in THEME_RULES:
        for kw in kws:
            if kw in name:
                return theme
    return None


def net_flow_eok(shares_now, shares_prev, nav):
    """순자금흐름(억원, 정수 반올림). 양수 유입 / 음수 유출."""
    return round((shares_now - shares_prev) * nav / 1e8)


def select_baseline(prior_dates_desc, max_window):
    """과거 스냅샷 날짜(내림차순)에서 기준 스냅샷을 고른다.

    가진 만큼 최대 max_window거래일 전을 기준으로. 반환 (baseline_date, window_days).
    스냅샷이 0개면 (None, 0) — 워밍업 첫날, flow 계산 불가.
    """
    p = len(prior_dates_desc)
    if p == 0:
        return (None, 0)
    k = min(max_window, p)
    return (prior_dates_desc[k - 1], k)


def roll_history(history, today, snapshot, keep_days=KEEP_DAYS):
    """오늘 스냅샷을 추가하고 최근 keep_days거래일만 남긴다."""
    out = dict(history)
    out[today] = snapshot
    keep = sorted(out.keys(), reverse=True)[:keep_days]
    return {d: out[d] for d in keep}


def aggregate_by_theme(flows, top_n=TOP_ETFS):
    """ETF별 flow 리스트 → 테마별 집계. None 테마 제외, |합| 내림차순."""
    buckets = {}
    for f in flows:
        theme = f.get("theme")
        if not theme:
            continue
        b = buckets.setdefault(theme, {"theme": theme, "flow_eok": 0, "etfs": []})
        b["flow_eok"] += f["flow_eok"]
        b["etfs"].append(f)
    out = []
    for b in buckets.values():
        top = sorted(b["etfs"], key=lambda x: -abs(x["flow_eok"]))[:top_n]
        out.append({
            "theme": b["theme"],
            "flow_eok": b["flow_eok"],
            "etf_count": len(b["etfs"]),
            "top_etfs": [{"code": e["code"], "name": e["name"], "flow_eok": e["flow_eok"]} for e in top],
        })
    out.sort(key=lambda t: -abs(t["flow_eok"]))
    return out


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def fetch_etf_list():
    """네이버 ETF 목록(cp949) → [{code,name,nav,aum_eok}] (AUM·NAV 유효한 것만)."""
    req = urllib.request.Request(ETF_LIST_URL, headers={
        "User-Agent": UA,
        "Referer": "https://finance.naver.com/",
    })
    raw = urllib.request.urlopen(req, timeout=15).read().decode("cp949", errors="replace")
    items = json.loads(raw)["result"]["etfItemList"]
    out = []
    for e in items:
        code = e.get("itemcode")
        name = e.get("itemname")
        nav = e.get("nav")
        aum = e.get("marketSum")   # 억원
        if not code or not name or not nav or not aum:
            continue
        out.append({
            "code": code,
            "name": name,
            "nav": float(nav),
            "aum_eok": float(aum),
        })
    return out


def build_today_snapshot(etfs, aum_floor):
    """AUM 필터 통과 ETF의 오늘 스냅샷 {code: {shares, nav, name}}."""
    snap = {}
    for e in etfs:
        if e["aum_eok"] < aum_floor:
            continue
        shares = estimate_shares(e["aum_eok"], e["nav"])
        if shares is None:
            continue
        snap[e["code"]] = {"shares": shares, "nav": e["nav"], "name": e["name"]}
    return snap


def compute_flows(today_snap, baseline_snap):
    """오늘 vs 기준 스냅샷 차분 → ETF별 flow 리스트(양쪽에 다 있는 종목만)."""
    flows = []
    for code, cur in today_snap.items():
        base = baseline_snap.get(code)
        if not base:
            continue   # 신규 상장 등 기준에 없는 종목은 제외
        flows.append({
            "code": code,
            "name": cur["name"],
            "theme": classify_theme(cur["name"]),
            "flow_eok": net_flow_eok(cur["shares"], base["shares"], cur["nav"]),
        })
    return flows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aum-floor", type=int, default=300, help="집계 대상 최소 AUM(억원)")
    args = ap.parse_args()

    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")

    etfs = fetch_etf_list()
    today_snap = build_today_snapshot(etfs, args.aum_floor)

    if len(today_snap) < MIN_ETFS:
        print(f"[etf-flows] ✗ ETF 수집 {len(today_snap)}개 — 정상({MIN_ETFS}+) 미달, "
              f"파일을 건드리지 않고 중단(운영규칙 0 — 얇은 응답이 히스토리를 오염시키지 않게).")
        sys.exit(1)

    history = load_json(HISTORY_PATH, {})
    prior_dates = sorted([d for d in history if d < today], reverse=True)
    baseline_date, window_days = select_baseline(prior_dates, MAX_WINDOW)

    themes = []
    if baseline_date:
        themes = aggregate_by_theme(compute_flows(today_snap, history[baseline_date]))

    OUT_PATH.write_text(json.dumps({
        "generated_at": now.isoformat(),
        "window_days": window_days,
        "aum_floor_eok": args.aum_floor,
        "coverage": {"etf_count": len(today_snap), "theme_count": len(themes)},
        "themes": themes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    new_history = roll_history(history, today, today_snap)
    HISTORY_PATH.write_text(json.dumps(new_history, ensure_ascii=False), encoding="utf-8")

    print(f"[etf-flows] {today} · ETF {len(today_snap)}개 · window {window_days}일 · 테마 {len(themes)}개")
    if not baseline_date:
        print("[etf-flows] ⚠️ 스냅샷 부족(워밍업) — themes 비어있음, 블록 숨김 상태")


if __name__ == "__main__":
    main()
