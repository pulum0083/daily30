# 코스피200 종목의 업종 상대 PER 밸류에이션(저평가·고평가)을 산출해 web/data/valuation.json 생성
"""
파이프라인:
  1) 네이버 finance entryJongmok 에서 코스피200 구성종목 실수집 (페이지네이션)
  2) 종목별 m.stock integration 에서 per/cnsPer/pbr/eps/industryCode/시총 실수집
  3) 업종별(industryCode) 유효 PER 중앙값 산출 → 괴리율 계산
  4) 저평가·고평가 랭킹 정렬 후 JSON 저장

방법론:
  - 기준 PER = 선행(cnsPer, 컨센서스 예상) 우선, 없으면 후행(per) 폴백
  - 유효 범위 0 < PER <= 100 (적자 및 100배 초과 턴어라운드·특수상황 제외)
  - 업종 벤치마크 = 같은 industryCode 내 유효 종목들의 중앙값 (유효 종목 3개 이상인 업종만)
  - 괴리율 = (종목 PER - 업종 중앙값) / 업종 중앙값 * 100  (음수=저평가, 양수=고평가)
  - 괴리율 절댓값 200% 초과(업종 대비 3배 넘게 이탈)는 통계적 이상치로 랭킹에서 제외

모든 수치는 생성 시점 실측만 사용한다 (SERVICE_RULES 규칙 0).
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
OUT = Path(__file__).resolve().parent.parent / "web" / "data" / "valuation.json"

PER_MAX = 100.0          # 이 값 초과 PER은 턴어라운드·특수상황으로 보아 제외
MIN_SECTOR_SIZE = 3      # 업종 중앙값 신뢰를 위한 최소 유효 종목 수
MAX_ABS_DISC = 200.0     # 괴리율 절댓값이 이 값 초과면 통계적 이상치로 랭킹에서 제외


def _get(url: str, referer: str, decode: str = "utf-8") -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    raw = urllib.request.urlopen(req, timeout=15).read()
    return raw.decode(decode, "replace")


def fetch_kospi200_codes() -> list:
    """네이버 finance entryJongmok(KPI200) 페이지네이션으로 구성종목 코드 실수집."""
    codes = []
    for pg in range(1, 26):
        url = f"https://finance.naver.com/sise/entryJongmok.naver?type=KPI200&page={pg}"
        try:
            html = _get(url, "https://finance.naver.com/", decode="euc-kr")
        except Exception as e:
            print(f"  entryJongmok page{pg} 실패: {e}", file=sys.stderr)
            break
        page_codes = list(dict.fromkeys(re.findall(r"code=(\d{6})", html)))
        new = [c for c in page_codes if c not in codes]
        if not new:
            break
        codes += new
        time.sleep(0.05)
    return codes


def _num(info: dict, code: str):
    v = info.get(code, {}).get("value", "")
    m = re.search(r"-?[\d,]+\.?\d*", v.replace(",", ""))
    return float(m.group()) if m else None


def fetch_stock(code: str) -> dict | None:
    """m.stock integration 에서 밸류에이션 지표 실수집."""
    url = f"https://m.stock.naver.com/api/stock/{code}/integration"
    try:
        d = json.loads(_get(url, "https://m.stock.naver.com/"))
    except Exception as e:
        print(f"  {code} integration 실패: {e}", file=sys.stderr)
        return None
    ti = {x["code"]: x for x in d.get("totalInfos", [])}
    return {
        "code": code,
        "name": d.get("stockName"),
        "industryCode": d.get("industryCode"),
        "per": _num(ti, "per"),
        "cnsPer": _num(ti, "cnsPer"),
        "pbr": _num(ti, "pbr"),
        "mktcap": ti.get("marketValue", {}).get("value", ""),
    }


def industry_name(code: str, cache: dict) -> str:
    if code in cache:
        return cache[code]
    try:
        d = json.loads(_get(
            f"https://m.stock.naver.com/api/stocks/industry/{code}?page=1&pageSize=1",
            "https://m.stock.naver.com/"))
        name = d.get("groupInfo", {}).get("name") or code
    except Exception:
        name = code
    cache[code] = name
    return name


def eff_per(row: dict):
    """선행(cnsPer) 우선, 없으면 후행(per) 폴백. 0<PER<=200 만 유효."""
    for key, basis in (("cnsPer", "선행"), ("per", "후행")):
        v = row.get(key)
        if v is not None and 0 < v <= PER_MAX:
            return v, basis
    return None, None


def main():
    print("코스피200 구성종목 수집 중…")
    codes = fetch_kospi200_codes()
    print(f"  구성종목 {len(codes)}개")
    if len(codes) < 100:
        print("구성종목 수집 실패(100개 미만) — 발행 중단", file=sys.stderr)
        sys.exit(1)

    print("종목별 밸류에이션 지표 수집 중…")
    rows = []
    for i, c in enumerate(codes):
        r = fetch_stock(c)
        if r:
            r["eff_per"], r["basis"] = eff_per(r)
            rows.append(r)
        time.sleep(0.05)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(codes)}")

    # 업종별 중앙값 (유효 종목 MIN_SECTOR_SIZE 이상)
    by_ind = defaultdict(list)
    for r in rows:
        if r["eff_per"] is not None:
            by_ind[r["industryCode"]].append(r["eff_per"])
    med = {ic: statistics.median(v) for ic, v in by_ind.items() if len(v) >= MIN_SECTOR_SIZE}

    name_cache = {}
    out = []
    for r in rows:
        if r["eff_per"] is None or r["industryCode"] not in med:
            continue
        m = med[r["industryCode"]]
        disc = round((r["eff_per"] - m) / m * 100, 1)
        if abs(disc) > MAX_ABS_DISC:      # 업종 대비 3배 넘게 이탈 → 이상치 제외
            continue
        out.append({
            "code": r["code"],
            "name": r["name"],
            "sector": industry_name(r["industryCode"], name_cache),
            "per": round(r["eff_per"], 2),
            "basis": r["basis"],
            "sectorMed": round(m, 2),
            "disc": disc,
            "pbr": r.get("pbr"),
            "mktcap": r.get("mktcap"),
        })

    undervalued = sorted([o for o in out if o["disc"] < 0], key=lambda x: x["disc"])
    overvalued = sorted([o for o in out if o["disc"] > 0], key=lambda x: -x["disc"])

    payload = {
        "asOf": datetime.now(KST).strftime("%Y-%m-%d"),
        "generatedAt": datetime.now(KST).isoformat(),
        "universe": "코스피200",
        "universeCount": len(rows),
        "evaluatedCount": len(out),
        "undervalued": undervalued,
        "overvalued": overvalued,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"저장: {OUT}")
    print(f"  평가 {len(out)}종목 · 저평가 {len(undervalued)} · 고평가 {len(overvalued)}")


if __name__ == "__main__":
    main()
