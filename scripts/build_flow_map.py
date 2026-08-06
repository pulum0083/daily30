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
            # 하루씩 반올림하므로 합계가 flow와 최대 몇 억 어긋날 수 있다(반올림 노이즈).
            # 테마 daily도 같은 성격 — 정합성 게이트(reconcile)는 이 노이즈와 무관하게
            # 발행본 총합 대조가 목적이라 영향받지 않는다.
            "daily": [round(byd.get(d, 0.0)) for d in dates],
        })
    rest_n = len(rest) + dropped_n
    rest_flow = sum(f["flow_eok"] for f in rest) + dropped_flow
    return rows, rest_n, rest_flow


def dates_of(themes_pub):
    """발행본 테마들의 daily에서 날짜축을 뽑는다(가장 긴 것 기준)."""
    best = []
    for t in themes_pub:
        ds = [x["date"] for x in (t.get("daily") or [])]
        if len(ds) > len(best):
            best = ds
    return best


def market_daily(themes_pub, dates):
    """전 테마 일별 순유입 합계. 날짜 키로 맞춰 더한다(인덱스 위치로 더하지 않는다)."""
    acc = {d: 0 for d in dates}
    for t in themes_pub:
        for x in (t.get("daily") or []):
            if x["date"] in acc:
                acc[x["date"]] += x["eok"]
    return [acc[d] for d in dates]


RECONCILE_TOL_EOK = 2      # 재계산 vs 발행 테마 합계 허용 오차(억). 실측은 0이다.


def reconcile(themes_pub, flows_by_theme, tol=RECONCILE_TOL_EOK):
    """재계산 ETF 합계와 발행 테마 합계를 대조해 어긋난 항목 설명을 돌려준다."""
    bad = []
    for t in themes_pub:
        fs = flows_by_theme.get(t["theme"], [])
        got = sum(f["flow_eok"] for f in fs)
        if abs(got - t["flow_eok"]) > tol:
            bad.append(f"{t['theme']} 합계 {got} vs 발행 {t['flow_eok']}")
        if len(fs) != t["etf_count"]:
            bad.append(f"{t['theme']} ETF수 {len(fs)} vs 발행 {t['etf_count']}")
    return bad


def build(history, published, now_iso, top_n=TOP_ETFS_DETAIL):
    """발행본(테마 합계 정본) + 히스토리(ETF 분해) → 자금 지도 탭 데이터. 워밍업이면 None."""
    themes_pub = published.get("themes") or []
    if not themes_pub:
        return None

    if not history:
        raise RuntimeError(
            "[flow-map] 히스토리 없음 — 발행본엔 테마가 있는데 히스토리가 비어 있다. "
            "두 파일이 같은 시점을 가리키지 않는다(운영규칙 0)."
        )

    today = max(history)
    pub_date = (published.get("generated_at") or "")[:10]
    if pub_date != today:
        raise RuntimeError(
            f"[flow-map] 날짜 불일치 — 히스토리 최신 {today} vs 발행본 {pub_date}. "
            f"어긋난 두 소스를 섞어 발행하지 않는다(운영규칙 0)."
        )

    ctx = rebuild_context(history)
    if ctx is None:
        # themes_pub가 비어있지 않다는 건 발행 당시 기준 스냅샷이 있었다는 뜻 — 날짜도
        # 이미 일치를 확인했다. 그런데도 재구성이 실패하면 히스토리가 그 사이 잘렸거나
        # 초기화된 것이다. 진짜 워밍업(themes_pub 자체가 비어있는 경우)과는 다른
        # 상태이므로 조용히 None을 반환하지 않고 크게 알린다.
        raise RuntimeError(
            f"[flow-map] 히스토리 재구성 실패 — 발행본은 {pub_date} 테마 {len(themes_pub)}개를 "
            f"갖고 있는데 히스토리에서 기준 스냅샷을 복원할 수 없다. 히스토리가 잘렸거나 "
            f"초기화됐을 가능성(운영규칙 0)."
        )

    flows_by_theme = {}
    for f in ctx["flows"]:
        if f["theme"]:
            flows_by_theme.setdefault(f["theme"], []).append(f)

    bad = reconcile(themes_pub, flows_by_theme)
    if bad:
        raise RuntimeError(
            "[flow-map] 정합성 실패 — 재계산이 발행본과 어긋난다: " + " / ".join(bad)
        )

    dates = dates_of(themes_pub)
    per_etf = daily_by_etf(ctx["snapshots"], ctx["today_snap"], ctx["codes"])

    themes = []
    for t in themes_pub:
        rows, rest_n, rest_flow = etf_rows(
            flows_by_theme.get(t["theme"], []),
            ctx["today_snap"], ctx["baseline_snap"], per_etf, dates, top_n,
        )
        by_date = {x["date"]: x["eok"] for x in (t.get("daily") or [])}
        themes.append({
            "theme": t["theme"],
            "flow_eok": t["flow_eok"],
            "gross_eok": t["gross_eok"],
            "etf_count": t["etf_count"],
            "daily": [by_date.get(d, 0) for d in dates],
            "etfs": rows,
            "rest_n": rest_n,
            "rest_flow": rest_flow,
        })

    return {
        "generated_at": now_iso,
        "source_generated_at": published.get("generated_at"),
        "window_days": published.get("window_days"),
        "aum_floor_eok": published.get("aum_floor_eok"),
        "coverage": published.get("coverage"),
        "dates": dates,
        "market_daily": market_daily(themes_pub, dates),
        "themes": themes,
    }


def main():
    now = datetime.now(KST)
    history = base.load_json(HISTORY_PATH, {})

    if not history:
        print("[flow-map] ✗ 히스토리가 비어 있음 — 파일을 건드리지 않고 중단")
        sys.exit(1)

    # base.load_json()은 파일 없음·파싱 실패를 조용히 {}로 죽인다 — 그대로 쓰면 "발행본이
    # 손상됐다"와 "진짜 워밍업(themes: [] 정상 기록)"이 구분되지 않는다. 워밍업 때도
    # build_etf_flows.main()은 항상 유효한 JSON을 쓰므로, 파일 존재·파싱 성공 여부로
    # 두 상태를 가른다.
    if not FLOWS_PATH.exists():
        print(f"[flow-map] ✗ 발행본 없음({FLOWS_PATH}) — 파일을 건드리지 않고 중단")
        sys.exit(1)
    published = base.load_json(FLOWS_PATH, {})
    if not published:
        print(f"[flow-map] ✗ 발행본이 손상됨(JSON 파싱 실패) — 파일을 건드리지 않고 중단")
        sys.exit(1)

    out = build(history, published, now.isoformat())
    if out is None:
        print("[flow-map] ⚠️ 워밍업(발행본 themes 없음) — 파일을 쓰지 않고 종료")
        return

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    etfs = sum(len(t["etfs"]) for t in out["themes"])
    print(f"[flow-map] {out['dates'][0]}~{out['dates'][-1]} · 테마 {len(out['themes'])}개 · "
          f"ETF {etfs}개 노출 · {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
