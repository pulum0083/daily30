#!/usr/bin/env python3
# Vercel 소비 추세를 매일 기록하는 스냅샷 — 2026-08-16 fair-use 차단(fluidCpuDuration) 후속 계측
#
# ⚠️ 이 스크립트는 CPU 시간을 측정하지 않는다. 측정할 수 없기 때문이다.
#    Vercel의 /v1/usage는 Pro에서도 어떤 시간 범위를 줘도 invalid_time_range로 거부하고
#    (2026-08-17 확인: 1h·6h·12h·24h·48h·7d·30d·청구주기 전체 모두 실패),
#    billing/usage·observability/usage 계열은 전부 404다. 즉 Fluid Active CPU 누적치를
#    프로그램으로 가져올 방법이 현재 없다. 그 숫자는 대시보드에서 눈으로 읽어야 한다.
#
# 그래서 이 스크립트가 하는 일은 셋이다.
#   ① 회귀 감시 — 폴링 엔드포인트가 no-store로 되돌아갔는지 매일 확인한다.
#      이번 사고의 직접 원인이 no-store였고, 되돌리는 건 한 줄이면 되기 때문에
#      단위 테스트(_cache-headers.test.mjs)만으로는 부족하다. 프로덕션 실응답을 본다.
#   ② 차단 조기 경보 — 팀 softBlock이 다시 생겼는지 확인한다. 이번엔 사이트가 죽고 나서야
#      알았다. 상태를 매일 남겨두면 다음엔 발생 시점이 기록에 남는다.
#   ③ 원장 — 대시보드에서 읽은 CPU 수치를 --cpu-hours로 같은 로그에 날짜와 함께 적어둔다.
#      한 번 찍은 숫자보다 추세가 판단에 쓸모 있다.
#
# 실행:
#   python3 scripts/usage_snapshot.py                      # 자동 수집만
#   python3 scripts/usage_snapshot.py --cpu-hours 1.4      # 대시보드 판독치 함께 기록
#
# 출력: data/vercel-usage-log.json (하루 1행, 같은 날 재실행하면 덮어씀)

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DEFAULT_BASE = "https://doubleshot.space"
DEFAULT_OUT = "data/vercel-usage-log.json"
TEAM_ID = "team_iPwo9taZIskxdoXOJu9assy2"

# 클라이언트가 주기적으로 폴링하는 엔드포인트 — 여기가 Fluid CPU 소비의 전부다.
# board·subscribe·trigger·visitors는 호출 빈도가 낮아 제외한다(감시 대상이 아님).
POLLED_ENDPOINTS = [
    "/api/kospi-live",
    "/api/market",
    "/api/stocks-live?codes=005930",
    "/api/intraday?code=005930",
    "/api/signals",
    "/api/vol-top",
    "/api/hl-night",
    "/api/data?f=briefings-list",
]


def classify_cache(cache_control: str, vercel_cache: str = None) -> str:
    """엣지 캐시가 걸려 있는지 판정한다.

    ⚠️ Cache-Control만 보면 안 된다. Vercel 엣지는 오리진이 설정한 s-maxage를 **소비하고
       클라이언트에게 내보내지 않는다** — 대신 `public, max-age=0, must-revalidate`로
       재작성한다(2026-08-17 프로덕션 실측). 반면 no-store는 그대로 전달된다.
       그래서 x-vercel-cache를 함께 봐야 정상 캐시를 회귀로 오인하지 않는다.

    'ok'        — 엣지가 응답을 재사용한다(폴링이 함수를 깨우지 않는다).
    'no-store'  — 캐시 금지. 폴링 1회 = 함수 실행 1회. 이번 사고의 원인이다.
    'unknown'   — 응답을 못 받았거나 판단 근거가 부족하다. 판정하지 않는다.
    """
    cc = (cache_control or "").lower()
    vc = (vercel_cache or "").upper()

    if "no-store" in cc:
        return "no-store"
    if vc in ("HIT", "STALE"):
        return "ok"
    if "s-maxage=" in cc:
        # 엣지를 우회해 오리진을 직접 부른 경우 — 원본 헤더가 그대로 보인다.
        return "ok"
    if vc and "max-age=0" in cc and "must-revalidate" in cc:
        # 엣지가 s-maxage를 소비하고 재작성한 형태. MISS(캐시 채우는 중)여도 캐시는 걸려 있다.
        return "ok"
    return "unknown"


def probe(base_url: str, path: str, timeout: int = 20) -> dict:
    """엔드포인트 1건을 호출해 캐시 관련 헤더만 기록한다. 본문은 읽지 않는다."""
    url = f"{base_url.rstrip('/')}{path}"
    started = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": "doubleshot-usage-snapshot/1.0"})
    status, headers = None, {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            headers = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        status = e.code
        headers = {k.lower(): v for k, v in (e.headers or {}).items()}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"path": path, "status": None, "error": str(e), "cache": "unknown"}

    cache_control = headers.get("cache-control", "")
    vercel_cache = headers.get("x-vercel-cache")
    return {
        "path": path,
        "status": status,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "cache_control": cache_control,
        "vercel_cache": vercel_cache,
        "age": headers.get("age"),
        "cache": classify_cache(cache_control, vercel_cache),
    }


def fetch_team_state(token: str, team_id: str = TEAM_ID, timeout: int = 20):
    """팀의 차단 상태·플랜을 조회한다. 토큰이 없거나 실패하면 None을 돌려준다(판정하지 않는다)."""
    if not token:
        return None
    url = f"https://api.vercel.com/v2/teams/{team_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None
    billing = data.get("billing") or {}
    return {
        "plan": billing.get("plan"),
        "soft_block": data.get("softBlock"),
        "blocked": data.get("blocked"),
    }


def summarize(probes: list) -> dict:
    """하루치 판정 요약 — 회귀(no-store 복귀)와 장애(비200)를 눈에 띄게 만든다."""
    regressed = sorted(p["path"] for p in probes if p.get("cache") == "no-store")
    failed = sorted(p["path"] for p in probes if p.get("status") != 200)
    return {
        "cacheable": sum(1 for p in probes if p.get("cache") == "ok"),
        "total": len(probes),
        "regressed": regressed,
        "failed": failed,
    }


def upsert_row(rows: list, row: dict) -> list:
    """같은 날짜 행이 있으면 교체하고, 없으면 추가한 뒤 날짜순으로 돌려준다.

    하루에 여러 번 실행해도 로그가 부풀지 않게 한다 — 재실행(예: --cpu-hours를
    나중에 덧붙일 때)이 정상 사용 패턴이기 때문이다.
    """
    kept = [r for r in rows if r.get("date") != row.get("date")]
    kept.append(row)
    return sorted(kept, key=lambda r: r.get("date") or "")


def load_rows(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    rows = data.get("rows") if isinstance(data, dict) else data
    return rows if isinstance(rows, list) else []


def main() -> int:
    ap = argparse.ArgumentParser(description="Vercel 소비 추세 일일 스냅샷")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--cpu-hours", type=float, default=None,
                    help="대시보드에서 읽은 Fluid Active CPU 누적(시간). API로는 못 가져온다.")
    ap.add_argument("--note", default=None, help="그날의 특이사항(배포·이벤트 등)")
    args = ap.parse_args()

    now = datetime.now(KST)
    probes = [probe(args.base_url, p) for p in POLLED_ENDPOINTS]
    summary = summarize(probes)

    row = {
        "date": now.strftime("%Y-%m-%d"),
        "checked_at": now.isoformat(timespec="seconds"),
        "summary": summary,
        "endpoints": probes,
    }
    team = fetch_team_state(os.environ.get("VERCEL_TOKEN", ""))
    if team:
        row["team"] = team
    if args.cpu_hours is not None:
        row["cpu_hours_dashboard"] = args.cpu_hours
    if args.note:
        row["note"] = args.note

    rows = upsert_row(load_rows(args.out), row)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"updated_at": now.isoformat(timespec="seconds"), "rows": rows},
                  f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"📊 {row['date']} — 캐시 가능 {summary['cacheable']}/{summary['total']}")
    if team:
        print(f"   플랜={team['plan']} softBlock={team['soft_block']}")
    if summary["regressed"]:
        print(f"⚠️  no-store로 되돌아간 엔드포인트: {', '.join(summary['regressed'])}", file=sys.stderr)
    if summary["failed"]:
        print(f"⚠️  200이 아닌 엔드포인트: {', '.join(summary['failed'])}", file=sys.stderr)
    print(f"   → {args.out}")
    # 회귀·장애가 있어도 exit 0 — 기록이 목적이지 파이프라인을 막는 게 아니다.
    return 0


if __name__ == "__main__":
    sys.exit(main())
