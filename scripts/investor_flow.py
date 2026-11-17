# 코스피 투자자별 수급 — 1분 시계열 수집·정규장 마감(15:31~15:40) 값·날짜별 저장

from __future__ import annotations
import json
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from market_common import BASE_DIR, KST


# 코스피 투자자별 순매수 — 2026-09-15 네이버가 sise_index.naver를 stock.naver.com으로 옮겨(302)
# 옛 HTML 정규식이 매일 "pattern not found"로 빈손이 됐다(§51).
# 새 페이지의 JSON(m.stock.naver.com/api/index/KOSPI/trend)은 **애프터장(16:00~20:00) 체결까지 누적한
# 하루 합계**라 마감 잡(16:25)에서 그대로 쓰면 정규장 값이 아니다(9/14 실측: 15:31 개인 +29,722억 →
# 20:00 +30,351억). 그래서 날짜만 JSON에서 받고, 값은 시간대별 자료에서 정규장 마감 직후 행을 쓴다.
#
# 2026-09-18 시간대별 표(finance.naver.com/sise/investorDealTrendTime.naver)가 HTTP 410이 됐다(§56).
# 새 원천은 stock.naver.com/api/domestic/market/trend/time — 1분 단위지만 **오늘 하루치만** 준다
# (bizdate 인자를 무시한다). 그래서 마감 잡이 그날 1분 시계열을 web/data/investor-time/{날짜}.json에
# 저장하고, 지난 날짜(아침 브리핑·대결판의 '어제')는 그 파일을 읽는다.
INVESTOR_TREND_URL = "https://m.stock.naver.com/api/index/KOSPI/trend"
INVESTOR_TIME_URL = ("https://stock.naver.com/api/domestic/market/trend/time"
                     "?tradeType=KRX&marketType=KOSPI&startIdx={p}&pageSize=100")
INVESTOR_TIME_DIR = BASE_DIR / "web" / "data" / "investor-time"
# 15:30 동시호가 체결은 15:31 행에 반영되고, 15:40부터 장후 시간외 종가매매가 값을 다시 움직인다.
# (9/14 실측: 15:30 행 +29,190 → 15:31~15:36 +29,722 → 15:49 +29,745 → 16:06 +29,681)
INVESTOR_REGULAR_FROM = "1531"
INVESTOR_REGULAR_UNTIL = "1540"
# investorGubun → 투자자. 네이버 화면 스크립트와 같게 3100(사모)은 투신, 7000(국가·지자체)은 연기금,
# 9001(기타외국인)은 외국인에 더한다. 9/21 17:49 행으로 검산 — 개인 −31,382 · 외국인 −174 · 기관 +14,977이
# m.stock.naver.com/api/index/KOSPI/trend 하루 합계와 일치했고 네 값의 합은 0이었다.
# marketType은 대문자 KOSPI여야 한다(소문자 kospi는 다른 값을 준다 — 같은 시각 개인 −29,947).
INVESTOR_GUBUN = {"1000": "금융투자", "2000": "보험", "3000": "투신", "3100": "투신", "4000": "은행",
                  "5000": "기타금융", "6000": "연기금", "7000": "연기금", "7100": "기타법인",
                  "8000": "개인", "9000": "외국인", "9001": "외국인"}
INVESTOR_INST_KEYS = ("금융투자", "보험", "투신", "은행", "기타금융", "연기금")


def _get_text(url: str, encoding: str = "utf-8", timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(encoding, errors="ignore")


def parse_investor_time_json(payload: dict) -> list[dict]:
    """시간대별 투자자 순매수 한 페이지 → [{date, t: "HH:MM", 개인, 외국인, 기관, 기타법인, inst}] (억원, 원본 순서).

    개인+외국인+기관계+기타법인은 0이어야 하므로 ±5억을 벗어나면 코드가 바뀐 것으로 보고 그 행을 버린다.
    기관 세부 코드가 빠진 칸은 0이 아니라 None으로 둔다(§0).
    """
    import re
    rows = []
    for it in (payload or {}).get("content") or []:
        t = str(it.get("time") or "")
        d = str(it.get("bizdate") or "")
        if not re.fullmatch(r"\d{6}", t) or not re.fullmatch(r"\d{8}", d):
            continue
        acc = {}
        try:
            for a in it.get("netAmounts") or []:
                k = INVESTOR_GUBUN.get(str(a.get("investorGubun")))
                if k:
                    acc[k] = acc.get(k, 0) + int(str(a.get("diffValue")))
        except (TypeError, ValueError):
            continue
        if any(k not in acc for k in ("개인", "외국인", "기타법인")) or not any(k in acc for k in INVESTOR_INST_KEYS):
            continue
        inst_raw = sum(acc.get(k, 0) for k in INVESTOR_INST_KEYS)
        if abs(acc["개인"] + acc["외국인"] + inst_raw + acc["기타법인"]) > 5 * 10**8:
            continue
        rows.append({
            "date": d, "t": t[:2] + ":" + t[2:4],
            "개인": round(acc["개인"] / 1e8), "외국인": round(acc["외국인"] / 1e8),
            "기관": round(inst_raw / 1e8), "기타법인": round(acc["기타법인"] / 1e8),
            "inst": {k: (round(acc[k] / 1e8) if k in acc else None) for k in INVESTOR_INST_KEYS},
        })
    return rows


def fetch_investor_time_rows(fetch_json=None, max_pages: int = 10) -> list[dict]:
    """오늘 하루치 1분 시계열(최신순). 한 페이지라도 깨지면 전부 버린다 — 부분 시계열을 온전한 것처럼 쓰지 않는다."""
    fetch_json = fetch_json or (lambda url: json.loads(_get_text(url)))
    rows = []
    for p in range(max_pages):
        d = fetch_json(INVESTOR_TIME_URL.format(p=p)) or {}
        content = d.get("content") or []
        page = parse_investor_time_json(d)
        if content and len(page) != len(content):
            return []
        rows += page
        if not content or str(d.get("last")).lower() == "true":
            break
    return rows


def save_investor_time(bizdate: str, rows: list[dict], out_dir: Path = None) -> Path | None:
    """그날 1분 시계열을 web/data/investor-time/{날짜}.json에 오래된→최신 순으로 저장한다(마감 잡 전용, §18)."""
    rows = [r for r in rows if r.get("date") == bizdate]
    if not rows:
        return None
    out_dir = out_dir or INVESTOR_TIME_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    body = {"date": bizdate, "source": "stock.naver.com/api/domestic/market/trend/time (KOSPI, KRX)",
            "unit": "억원", "rows": sorted(({k: v for k, v in r.items() if k != "date"} for r in rows),
                                         key=lambda r: r["t"])}
    path = out_dir / f"{bizdate}.json"
    path.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def load_investor_time(bizdate: str, out_dir: Path = None) -> list[dict]:
    """저장해 둔 그날 시계열(최신순). 없으면 []."""
    path = (out_dir or INVESTOR_TIME_DIR) / f"{bizdate}.json"
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    if body.get("date") != bizdate:
        return []
    return sorted(({**r, "date": bizdate} for r in body.get("rows") or []), key=lambda r: r["t"], reverse=True)


def regular_session_investor(bizdate: str, fetch_json=None, out_dir: Path = None, save: bool = True) -> dict:
    """그날 정규장 마감 직후(15:31~15:40) 코스피 투자자별 순매수. 없으면 {}.

    원천은 오늘치만 주므로, 원천의 날짜가 요청 날짜와 같으면 그걸 읽고 저장하며(마감 잡),
    다르면 저장해 둔 파일을 읽는다(아침 브리핑의 전 거래일). 15:40 이하 마지막 행이 15:31보다 이르면
    (정규장이 아직 안 끝났거나 자료가 잘린 것) 쓰지 않는다 — 장중 값을 마감 값으로 싣지 않는다.
    """
    live = []
    try:
        live = [r for r in fetch_investor_time_rows(fetch_json) if r["date"] == bizdate]
    except Exception as e:
        print(f"[fetch_data] investor time 조회 실패: {e}", file=sys.stderr)
    if live:
        if save:
            save_investor_time(bizdate, live, out_dir)
        rows = live
    else:
        rows = load_investor_time(bizdate, out_dir)
    found = next((r for r in rows if r["t"].replace(":", "") <= INVESTOR_REGULAR_UNTIL), None)
    if not found or found["t"].replace(":", "") < INVESTOR_REGULAR_FROM:
        return {}
    return {
        "date": bizdate,
        "asof": found["t"].replace(":", ""),
        # 억원 → 백만원 (×100). 다운스트림(supply_history·generate_html)이 기대하는 단위.
        "foreign":     {"net": found["외국인"] * 100},
        "institution": {"net": found["기관"] * 100},
        "individual":  {"net": found["개인"] * 100},
    }


def latest_investor_bizdate(fetch_json=None) -> str | None:
    """네이버가 수급을 집계 중인 가장 최근 거래일(YYYYMMDD). 실패 시 None."""
    try:
        if fetch_json is None:
            d = json.loads(_get_text(INVESTOR_TREND_URL))
        else:
            d = fetch_json(INVESTOR_TREND_URL)
        bizdate = str((d or {}).get("bizdate") or "")
        return bizdate if len(bizdate) == 8 and bizdate.isdigit() else None
    except Exception as e:
        print(f"[fetch_data] investor bizdate 조회 실패: {e}", file=sys.stderr)
        return None


def fetch_investor_trading_kospi(date_str: str = None, now=None, fetch_json=None, out_dir: Path = None) -> dict:
    """코스피 투자자별 순매수(정규장 마감 기준)를 가져온다.

    date_str를 주면 그날을, 없으면 마감이 끝난 직전 거래일을 쓴다(아침 브리핑).

    Returns:
        {
          "date": "YYYYMMDD",
          "asof": "HHMM",               # 값을 읽은 1분 시계열의 행 시각
          "foreign":     {"net": int},  # 외국인 순매수 (단위: 백만원)
          "institution": {"net": int},  # 기관합계 순매수
          "individual":  {"net": int},  # 개인 순매수
        }
    """
    now = now or datetime.now(KST)
    today = now.strftime("%Y%m%d")
    if date_str is None:
        # 네이버가 집계 중인 날짜가 오늘이면(장 시작 뒤 재실행 등) 아직 끝난 세션이 아니다 — 전 평일로.
        bizdate = latest_investor_bizdate(fetch_json)
        if bizdate and bizdate < today:
            date_str = bizdate
        else:
            target = now - timedelta(days=1)
            while target.weekday() >= 5:  # 5=Sat, 6=Sun
                target -= timedelta(days=1)
            date_str = target.strftime("%Y%m%d")
    try:
        result = regular_session_investor(date_str, fetch_json, out_dir)
    except Exception as e:
        print(f"[fetch_data] Investor trading error: {e}", file=sys.stderr)
        return {}
    if not result:
        print(f"[fetch_data] Investor trading ({date_str}): 정규장 마감 행(15:31~15:40)을 찾지 못함 — 비운다", file=sys.stderr)
        return {}
    print(f"[fetch_data] Investor trading ({date_str} {result['asof']}): "
          f"foreign={result['foreign']['net']:+,}, institution={result['institution']['net']:+,}, "
          f"individual={result['individual']['net']:+,} (백만원)")
    return result
