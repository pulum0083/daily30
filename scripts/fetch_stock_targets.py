# 네이버 증권사 리포트에서 종목별 목표주가·투자의견을 수집해 컨센서스를 계산하는 스크립트
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pytz

KST = pytz.timezone("Asia/Seoul")

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
# 2026-09-11 네이버가 리서치 게시판(finance.naver.com/research/company_list.naver)을
# stock.naver.com(Next.js, 클라이언트 렌더)으로 옮기면서 옛 URL은 302로 새 페이지에 넘어가고
# itemCode 필터까지 떨어졌다. HTML 표 파서가 0행을 읽어 3종목 모두 리포트 0건이 됐다
# (SERVICE_RULES §47). 새 페이지가 쓰는 JSON API로 바꿨다 — 목표가·투자의견이 구조화 필드로 온다.
LIST_URL = "https://m.stock.naver.com/api/research/stock/{code}?page={page}&pageSize=20"
DETAIL_URL = "https://m.stock.naver.com/api/research/company/{nid}"


def fetch_json(url):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))


def parse_report_list(items, code):
    """목록 JSON에서 (증권사, 날짜, nid)를 뽑는다. 목표가는 목록에 없다.

    다른 종목 리포트는 버린다. 같은 계열의 /api/research/company는 itemCode를 조용히 무시하고
    전 종목 목록을 돌려줬다 — 필터가 풀리면 남의 목표가가 컨센서스에 섞인다.
    날짜는 기존 소비처(컨센서스·상세 페이지·허브 위젯)가 쓰는 'YY.MM.DD'로 맞춘다.
    """
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or str(it.get("itemCode")) != code or not it.get("researchId") or not it.get("brokerName"):
            continue
        try:
            d = datetime.strptime(str(it.get("writeDate")), "%Y-%m-%d").strftime("%y.%m.%d")
        except ValueError:
            continue
        out.append({"firm": it["brokerName"], "date": d, "nid": str(it["researchId"])})
    return out


def parse_report_detail(data):
    """상세 JSON에서 목표가·투자의견을 뽑는다. 목표가가 없는 리포트는 None."""
    rc = (data or {}).get("researchContent") or {}
    raw = str(rc.get("goalPrice") or "").replace(",", "").strip()
    target = int(raw) if raw.isdigit() and int(raw) > 0 else None
    opinion = str(rc.get("opinion") or "").strip() or None
    # 목표가 없는 리포트는 투자의견도 '없음'으로 온다 — 실제 의견이 아니므로 버린다.
    if opinion == "없음":
        opinion = None
    return {"target_price": target, "opinion": opinion}


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
MAX_DETAIL_FAILURE_RATIO = 0.3  # 상세 조회가 이 비율을 넘게 실패하면 컨센서스를 못 믿는다


def _write_atomic(path, text):
    """같은 디렉터리 임시 파일에 쓴 뒤 교체한다.

    web/data/stock-targets.json은 브라우저에 그대로 서빙되므로
    읽는 쪽이 절반만 쓰인 파일을 관측하면 안 된다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_history(path):
    """히스토리 파일을 읽는다. 깨져 있으면 빈 dict로 되돌린다.

    이전 실행이 쓰다 죽어 파일이 깨졌을 때 그대로 예외를 올리면
    이후 모든 실행이 영구히 막힌다 — 경고만 남기고 다음 쓰기에서 스스로 복구시킨다.
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        print(f"⚠️ 히스토리 파일이 손상돼 초기화합니다 ({path}): {e}", file=sys.stderr)
        return {}


def append_history(path, code, value, date_str):
    """컨센서스를 하루 1점만 누적한다. 같은 날 재실행은 덮어쓴다."""
    data = _read_history(path)
    if value is None:
        # 컨센서스를 못 구한 날은 점을 남기지 않는다 — 파일도 건드리지 않는다.
        return data.get(code, [])
    points = [p for p in data.get(code, []) if p["date"] != date_str]
    points.append({"date": date_str, "value": value})
    points.sort(key=lambda p: p["date"])
    data[code] = points[-MAX_HISTORY_POINTS:]
    _write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
    return data[code]


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
    """종목 하나의 리포트를 수집해 목표가·투자의견까지 채운다.

    (리포트 목록, 상세 조회 실패 건수, 목록 행 수)를 돌려준다. 실패 건수를 같이 내보내야
    호출부가 '살아남은 소수로 낸 평균'인지 판별할 수 있다. 목록 행 수는 원천 구조가
    바뀌어 목록 자체를 못 읽는 상황을 가려내는 데 쓴다.
    목표가가 '없음'인 리포트는 정상 데이터지 실패가 아니다 — 여기서 세지 않는다.
    """
    reports = []
    failed = 0
    listed = 0
    for page in range(1, pages + 1):
        try:
            rows = parse_report_list(fetch_json(LIST_URL.format(code=code, page=page)), code)
        except Exception as e:
            print(f"⚠️ {code} 목록 페이지 {page} 수집 실패: {e}", file=sys.stderr)
            continue
        listed += len(rows)
        for row in rows:
            try:
                detail = parse_report_detail(fetch_json(DETAIL_URL.format(nid=row["nid"])))
            except Exception as e:
                print(f"⚠️ {code} 리포트 nid={row['nid']} 상세 수집 실패: {e}", file=sys.stderr)
                failed += 1
                continue
            reports.append({**row, **detail})
    return reports, failed, listed


def _alert_collection_dead(detail):
    try:
        from send_telegram import send_admin_alert
        send_admin_alert(
            "[Double-Shot] 증권사 목표주가 수집 실패 — 3종목 모두 리포트 목록 0건\n"
            f"{detail}\n"
            "원천(네이버 리서치) 구조 변경을 의심하세요. 직전 stock-targets.json을 유지합니다.\n"
            "확인: python3 scripts/fetch_stock_targets.py"
        )
    except Exception as e:
        print(f"⚠️ 관리자 알림 실패: {e}", file=sys.stderr)


def main():
    # datetime.now()는 GHA 러너(UTC) 기준이라 KST 07:2x 아침 실행 시 하루 전 날짜로 찍힌다
    # (2026-07-27 실사고: 07:29 KST 실행이 "2026-07-26"로 기록돼 consensus_history에
    # 존재하지 않는 휴장일 항목이 남았다). 반드시 KST로 명시한다.
    today = datetime.now(KST)
    today_str = today.strftime("%y.%m.%d")
    collected = {}
    for code, name in STOCKS.items():
        print(f"수집 중: {name} ({code})")
        collected[code] = collect(code)

    # 대형주 3종목이 동시에 리포트 0건일 수는 없다 — 원천 구조가 바뀌어 목록을 못 읽은 것이다.
    # 2026-09-11엔 이 상태로 좋은 파일을 빈 값으로 덮어써, 수집이 죽은 걸 화면이 비고 나서야 알았다.
    # 덮어쓰지 않으면 updated_at이 멈춰 generate_html의 신선도 게이트(§20)가 5일 뒤 섹션을 내린다.
    if all(listed == 0 for _, _, listed in collected.values()):
        msg = "리포트 목록이 3종목 모두 0건 — 기존 파일을 유지하고 종료합니다."
        print(f"❌ {msg}", file=sys.stderr)
        _alert_collection_dead(msg)
        sys.exit(1)

    stocks_out = {}
    for code, name in STOCKS.items():
        reports, failed, _ = collected[code]
        consensus = compute_consensus(reports, today=today_str)
        close_price = fetch_close_price(code)

        # 상세 조회가 대량 실패하면 살아남은 소수로 낸 평균은 신뢰할 수 없다.
        # 1개사 평균이 정상 데이터와 구조적으로 똑같이 렌더되는 조용한 오염을 막는다(운영규칙 0).
        attempted = len(reports) + failed
        unreliable = attempted > 0 and failed / attempted > MAX_DETAIL_FAILURE_RATIO
        if unreliable:
            print(
                f"⚠️ {name}({code}) 상세 조회 {attempted}건 중 {failed}건 실패 — "
                f"컨센서스를 표시하지 않습니다.",
                file=sys.stderr,
            )
            # 오염된 평균으로 추이를 더럽히지 않는다 — 이 종목은 히스토리를 건너뛴다.
            points = _read_history(HISTORY_JSON).get(code, [])
        else:
            points = append_history(HISTORY_JSON, code, consensus["consensus"], today.strftime("%Y-%m-%d"))
        history = points if len(points) >= MIN_HISTORY_POINTS else []

        stocks_out[code] = {
            "name": name,
            "consensus": None if unreliable else consensus["consensus"],
            "firm_count": 0 if unreliable else consensus["firm_count"],
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

    _write_atomic(
        OUT_JSON,
        json.dumps(
            {"updated_at": today.strftime("%Y-%m-%d"), "stocks": stocks_out},
            ensure_ascii=False,
            indent=2,
        ),
    )
    print(f"✅ {OUT_JSON} 저장 완료 ({len(stocks_out)}개 종목)")


if __name__ == "__main__":
    main()
