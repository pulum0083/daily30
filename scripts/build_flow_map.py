# 자금 지도 탭용 ETF 단위 분해 데이터 빌더 — 테마 합계는 발행본(etf-flows.json)을 그대로 승계한다
#!/usr/bin/env python3
"""
자금 지도 탭 데이터 빌더.

`web/data/etf-flows.json`(발행본)의 테마 합계·일별 값을 정본으로 승계하고,
`data/etf_flow_history.json`에서 ETF 단위 분해만 재계산해 합친다.
네트워크를 쓰지 않는다 — 커밋된 두 파일만 읽는다.

왜 재계산인가
  히스토리는 좌수·NAV 스냅샷일 뿐 ETF별 흐름이 저장돼 있지 않다. 다만 build_etf_flows가
  파일을 쓴 **뒤에** 히스토리를 롤링하므로, 잡 종료 시점의 히스토리로 발행본을 오차 0으로
  재구성할 수 있다(실측 확인). 분류·환산은 build_etf_flows의 함수를 그대로 import한다 —
  재구현하면 한쪽만 고쳐져도 겉보기엔 둘 다 정상으로 보인다(SERVICE_RULES §30).

산출:
  web/data/flow-map.json

Usage:
  python3 scripts/build_flow_map.py
"""
import json
import sys
from datetime import datetime

import build_etf_flows as base

KST = base.KST
ROOT = base.ROOT
HISTORY_PATH = base.HISTORY_PATH
FLOWS_PATH = base.OUT_PATH                       # web/data/etf-flows.json — 입력이자 정본
OUT_PATH = ROOT / "web" / "data" / "flow-map.json"

TOP_ETFS_DETAIL = 20     # 테마당 노출 ETF 수. 밖으로 밀린 것은 개수·합계를 명시한다(무음 절단 금지)


def daily_by_etf(snapshots, final_snap, codes):
    """연속 스냅샷 쌍의 좌수 차분을 ETF별·날짜별로 낸다. {code: {date: eok(float)}}.

    build_etf_flows.daily_by_theme와 **같은 규약**이다 — 환산은 각 날의 NAV가 아니라 최종
    NAV로 통일하고(telescoping 보장), 중간 스냅샷에 없는 종목은 직전 좌수를 유지한다.
    이 함수의 테마 롤업이 daily_by_theme와 일치하는지는 테스트가 실데이터로 대조한다.

    반올림하지 않고 float로 돌려준다 — 합산 후 한 번만 반올림해야 오차가 누적되지 않는다.
    """
    if len(snapshots) < 2:
        return {}
    prev_shares = {}
    for code in codes:
        b = snapshots[0][1].get(code)
        if b:
            prev_shares[code] = b["shares"]

    out = {}
    for date, snap in snapshots[1:]:
        for code in codes:
            if code not in prev_shares:
                continue
            cur = snap.get(code)
            if not cur:
                continue                 # carry-forward — prev_shares 유지
            fin = final_snap.get(code)
            if not fin:
                continue
            out.setdefault(code, {})[date] = (cur["shares"] - prev_shares[code]) * fin["nav"] / 1e8
            prev_shares[code] = cur["shares"]
    return out


def rebuild_context(history):
    """히스토리에서 발행본과 동일한 계산 컨텍스트를 복원한다.

    build_etf_flows.main()이 파일을 쓴 뒤에 히스토리를 롤링하므로, 잡 종료 시점의
    히스토리에는 오늘 스냅샷이 들어 있고 select_baseline이 고르는 기준일도 그때와 같다.
    반환 dict: today / baseline / window_days / today_snap / baseline_snap /
              snapshots(기준일→오늘) / dates(일별 날짜) / flows / codes
    """
    today = max(history)
    prior = sorted([d for d in history if d < today], reverse=True)
    baseline, window_days = base.select_baseline(prior, base.MAX_WINDOW)
    if not baseline:
        return None                                  # 워밍업 — flow 계산 불가
    today_snap = history[today]
    baseline_snap = history[baseline]
    flows = base.compute_flows(today_snap, baseline_snap)
    window_dates = list(reversed(prior[:window_days]))
    snapshots = [(d, history[d]) for d in window_dates] + [(today, today_snap)]
    return {
        "today": today,
        "baseline": baseline,
        "window_days": window_days,
        "today_snap": today_snap,
        "baseline_snap": baseline_snap,
        "snapshots": snapshots,
        "dates": [d for d, _ in snapshots[1:]],
        "flows": flows,
        "codes": [f["code"] for f in flows],
    }


def rollup_to_theme(per_etf, final_snap, dates):
    """ETF별 일별값을 테마로 합산. daily_by_theme와 같은 형태로 돌려준다(대조 테스트용)."""
    agg = {}
    for code, byd in per_etf.items():
        fin = final_snap.get(code)
        theme = base.classify_theme(fin["name"]) if fin else None
        if not theme:
            continue
        bucket = agg.setdefault(theme, {})
        for d, v in byd.items():
            bucket[d] = bucket.get(d, 0.0) + v
    return {
        theme: [{"date": d, "eok": round(byd.get(d, 0.0))} for d in dates]
        for theme, byd in agg.items()
    }


def etf_rows(flows, today_snap, baseline_snap, per_etf_daily, dates, top_n=TOP_ETFS_DETAIL):
    """테마 하나의 ETF flow 목록 → 화면용 행 + 잘린 나머지 요약.

    반환 (rows, rest_n, rest_flow). rows는 |flow| 내림차순 상위 top_n개.

    pct(덩치 대비 증감률) = (현재좌수 − 기준좌수) / 현재좌수 × 100.
    NAV가 약분되므로 가격 효과 없는 순수 설정/환매 비율이다. 큰 ETF의 큰 금액보다
    작은 ETF가 덩치 대비 크게 움직인 것이 더 드문 신호라서 별도로 낸다.
    """
    ranked = sorted(flows, key=lambda f: -abs(f["flow_eok"]))
    top, rest = ranked[:top_n], ranked[top_n:]

    rows = []
    dropped_n, dropped_flow = 0, 0
    for f in top:
        cur = today_snap.get(f["code"])
        bas = baseline_snap.get(f["code"])
        if not cur or not bas:
            # compute_flows가 걸렀어야 할 상태 — 지어내지 않되, "무음 절단 금지" 약속을
            # 이 함수 스스로 지킨다. rest로 접어 어떤 경로로도 flow_eok가 안 사라지게 한다.
            dropped_n += 1
            dropped_flow += f["flow_eok"]
            continue
        shares = cur["shares"]
        byd = per_etf_daily.get(f["code"], {})
        rows.append({
            "code": f["code"],
            "name": f["name"],
            "flow": f["flow_eok"],
            "aum": round(shares * cur["nav"] / 1e8),
            "pct": round((shares - bas["shares"]) / shares * 100, 1) if shares else None,
            "daily": [round(byd.get(d, 0.0)) for d in dates],
        })
    rest_n = len(rest) + dropped_n
    rest_flow = sum(f["flow_eok"] for f in rest) + dropped_flow
    return rows, rest_n, rest_flow
