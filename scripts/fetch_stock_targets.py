# 네이버 증권사 리포트에서 종목별 목표주가·투자의견을 수집해 컨센서스를 계산하는 스크립트
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
LIST_URL = ("https://finance.naver.com/research/company_list.naver"
            "?searchType=itemCode&itemCode={code}&page={page}")
DETAIL_URL = "https://finance.naver.com/research/company_read.naver?nid={nid}&page=1"

_STRIP = re.compile(r"<[^>]+>")


def _text(html):
    return _STRIP.sub("", html).strip()


def fetch_euckr(url):
    """네이버 금융 리서치 게시판은 EUC-KR로 서빙된다."""
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=20).read().decode("euc-kr", "ignore")


def parse_report_list(html):
    """목록 HTML에서 (증권사, 날짜, nid)를 뽑는다. 목표가는 목록에 없다."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        nid = re.search(r"nid=(\d+)", row)
        cols = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        cols = [c for c in cols if c]
        if not nid or len(cols) < 4:
            continue
        if not re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", cols[3]):
            continue
        out.append({"firm": cols[2], "date": cols[3], "nid": nid.group(1)})
    return out


def parse_report_detail(html):
    """상세 HTML에서 목표가·투자의견을 뽑는다. 목표가가 없는 리포트는 None."""
    tp = re.search(r"목표가[\s\S]{0,40}?([\d][\d,]{2,})", html)
    op = re.search(r"투자의견\s*<em[^>]*>([^<]+)</em>", html)
    opinion = op.group(1).strip() if op else None
    # 목표가 없는 리포트는 네이버가 투자의견에도 '없음'을 렌더한다 — 실제 의견이 아니므로 버린다.
    if opinion == "없음":
        opinion = None
    return {
        "target_price": int(tp.group(1).replace(",", "")) if tp else None,
        "opinion": opinion,
    }


def _to_date(yymmdd):
    """'26.07.08' → date. 네이버는 2자리 연도를 쓴다."""
    return datetime.strptime(yymmdd, "%y.%m.%d").date()


def _try_date(yymmdd):
    """날짜가 깨졌으면 None. 목록 파서는 모양만 보고 유효성은 안 본다."""
    try:
        return _to_date(yymmdd)
    except (ValueError, TypeError):
        return None


def compute_consensus(reports, today, months=3):
    """증권사당 최신 1건만 골라 최근 N개월 목표주가 평균을 낸다.

    유효한 목표가가 하나도 없으면 consensus=None을 반환한다 —
    억지로 0이나 추정치를 만들지 않는다(운영규칙 0).
    """
    cutoff = _to_date(today) - timedelta(days=months * 31)
    latest = {}
    for r in reports:
        if r.get("target_price") is None:
            continue
        d = _try_date(r.get("date"))
        # 한 건이 깨져도 그 건만 빼고 나머지로 컨센서스를 낸다.
        if d is None or d < cutoff:
            continue
        prev = latest.get(r["firm"])
        if prev is None or d > _to_date(prev["date"]):
            latest[r["firm"]] = r
    picked = list(latest.values())
    if not picked:
        return {"consensus": None, "firm_count": 0, "reports": []}
    avg = round(sum(p["target_price"] for p in picked) / len(picked))
    picked.sort(key=lambda p: _to_date(p["date"]), reverse=True)
    return {"consensus": avg, "firm_count": len(picked), "reports": picked}


ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "web" / "data" / "stock-targets.json"
HISTORY_JSON = ROOT / "data" / "consensus_history.json"
STOCKS = {"005930": "삼성전자", "000660": "SK하이닉스", "005380": "현대차"}
MIN_HISTORY_POINTS = 20   # 이 개수 미만이면 프런트에서 추이 그래프를 숨긴다
MAX_HISTORY_POINTS = 120  # 약 6개월치 거래일


def append_history(path, code, value, date_str):
    """컨센서스를 하루 1점만 누적한다. 같은 날 재실행은 덮어쓴다."""
    if value is None:
        return
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {}
    points = [p for p in data.get(code, []) if p["date"] != date_str]
    points.append({"date": date_str, "value": value})
    points.sort(key=lambda p: p["date"])
    data[code] = points[-MAX_HISTORY_POINTS:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_close_price(code):
    """상승여력 계산의 기준가. 정규장 종가 고정 — HL 24h 환산가에 연동하지 않는다.

    환산가는 실제 체결가가 아니라(운영규칙 0), 밤새 상승여력이 흔들리면 안 된다.
    반환 dict의 종가 키는 price다 — close가 아니다.
    """
    try:
        from validate_analysis import _fetch_kospi_realdata
        r = _fetch_kospi_realdata(code)
        if not r or "error" in r or r.get("price") is None:
            return None
        return int(r["price"])
    except Exception as e:
        print(f"⚠️ {code} 종가 조회 실패: {e}", file=sys.stderr)
        return None


def collect(code, pages=2):
    """종목 하나의 리포트를 수집해 목표가·투자의견까지 채운다."""
    reports = []
    for page in range(1, pages + 1):
        try:
            html = fetch_euckr(LIST_URL.format(code=code, page=page))
            rows = parse_report_list(html)
        except Exception as e:
            print(f"⚠️ {code} 목록 페이지 {page} 수집 실패: {e}", file=sys.stderr)
            continue
        for row in rows:
            try:
                detail_html = fetch_euckr(DETAIL_URL.format(nid=row["nid"]))
                detail = parse_report_detail(detail_html)
            except Exception as e:
                print(f"⚠️ {code} 리포트 nid={row['nid']} 상세 수집 실패: {e}", file=sys.stderr)
                continue
            reports.append({**row, **detail})
    return reports


def main():
    today = datetime.now()
    today_str = today.strftime("%y.%m.%d")
    stocks_out = {}
    for code, name in STOCKS.items():
        print(f"수집 중: {name} ({code})")
        reports = collect(code)
        consensus = compute_consensus(reports, today=today_str)
        close_price = fetch_close_price(code)
        append_history(HISTORY_JSON, code, consensus["consensus"], today.strftime("%Y-%m-%d"))

        history_data = json.loads(HISTORY_JSON.read_text(encoding="utf-8")) if HISTORY_JSON.exists() else {}
        points = history_data.get(code, [])
        history = points if len(points) >= MIN_HISTORY_POINTS else []

        stocks_out[code] = {
            "name": name,
            "consensus": consensus["consensus"],
            "firm_count": consensus["firm_count"],
            "close_price": close_price,
            "reports": [
                {
                    "firm": r["firm"],
                    "opinion": r.get("opinion"),
                    "target_price": r.get("target_price"),
                    "date": r["date"],
                }
                for r in consensus["reports"][:10]
            ],
            "history": history,
        }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {"updated_at": today.strftime("%Y-%m-%d"), "stocks": stocks_out},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"✅ {OUT_JSON} 저장 완료 ({len(stocks_out)}개 종목)")


if __name__ == "__main__":
    main()
