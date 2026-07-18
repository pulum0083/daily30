# 네이버 증권사 리포트 목록·상세 파싱과 컨센서스 계산을 검증하는 테스트
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_stock_targets as fst

LIST_HTML = """
<table><tbody>
<tr><td><a href="/item/main.naver?code=005930">삼성전자</a></td>
<td><a href="company_read.naver?nid=93991&page=1">메모리 이익 체력 확인</a></td>
<td>하나증권</td><td>26.07.08</td><td>5527</td></tr>
<tr><td><a href="/item/main.naver?code=005930">삼성전자</a></td>
<td><a href="company_read.naver?nid=93978&page=1">체급의 위력</a></td>
<td>대신증권</td><td>26.07.07</td><td>5081</td></tr>
<tr><td colspan="5">광고행</td></tr>
</tbody></table>
"""

DETAIL_HTML = """
<div class="view_info">
    <div class="view_info_1">
        목표가 <em class="money"><strong>480,000</strong></em>
    <span class="division">|</span>
    투자의견 <em class="coment">Buy</em>
    </div></div>
"""

DETAIL_NO_TARGET = """
<div class="view_info_1">
    목표가 <em class="money">없음</em>
    <span class="division">|</span>
    투자의견 <em class="coment">없음</em>
    </div>
"""


def test_parse_report_list_extracts_rows():
    rows = fst.parse_report_list(LIST_HTML)
    assert len(rows) == 2
    assert rows[0] == {"firm": "하나증권", "date": "26.07.08", "nid": "93991"}
    assert rows[1]["firm"] == "대신증권"


def test_parse_report_detail_extracts_target_and_opinion():
    assert fst.parse_report_detail(DETAIL_HTML) == {
        "target_price": 480000, "opinion": "Buy"
    }


def test_parse_report_detail_returns_none_when_placeholder():
    # 목표가가 없는 리포트는 네이버가 '없음' 플레이스홀더를 렌더한다.
    # 이걸 그대로 두면 UI에 '없음' 투자의견 뱃지가 뜬다 — 둘 다 None이어야 한다.
    assert fst.parse_report_detail(DETAIL_NO_TARGET) == {
        "target_price": None, "opinion": None
    }


def test_compute_consensus_uses_latest_per_firm():
    # 같은 증권사가 2건을 냈으면 최신 1건만 평균에 들어가야 한다
    reports = [
        {"firm": "하나증권", "date": "26.07.08", "target_price": 100000},
        {"firm": "하나증권", "date": "26.05.02", "target_price": 60000},
        {"firm": "대신증권", "date": "26.07.07", "target_price": 120000},
    ]
    r = fst.compute_consensus(reports, today="26.07.18")
    assert r["firm_count"] == 2
    assert r["consensus"] == 110000  # (100000 + 120000) / 2


def test_compute_consensus_drops_reports_older_than_3_months():
    reports = [
        {"firm": "A증권", "date": "26.07.08", "target_price": 100000},
        {"firm": "B증권", "date": "26.01.05", "target_price": 999999},
    ]
    r = fst.compute_consensus(reports, today="26.07.18")
    assert r["firm_count"] == 1
    assert r["consensus"] == 100000


def test_compute_consensus_skips_malformed_date_instead_of_crashing():
    # 스크랩 글리치로 날짜 한 건이 깨져도 종목 전체 컨센서스가 죽으면 안 된다.
    # 목록 파서는 날짜 모양만 보고 유효성은 안 보므로 여기서 방어한다.
    reports = [
        {"firm": "A증권", "date": "26.07.08", "target_price": 100000},
        {"firm": "B증권", "date": "26.13.01", "target_price": 999999},
    ]
    r = fst.compute_consensus(reports, today="26.07.18")
    assert r["firm_count"] == 1
    assert r["consensus"] == 100000


def test_compute_consensus_returns_none_when_no_valid_reports():
    # 목표가가 전부 없으면 억지로 0을 만들지 않고 None (운영규칙 0)
    reports = [{"firm": "A증권", "date": "26.07.08", "target_price": None}]
    assert fst.compute_consensus(reports, today="26.07.18")["consensus"] is None


def test_append_history_writes_one_point_per_day(tmp_path):
    p = tmp_path / "consensus_history.json"
    fst.append_history(p, "005930", 100000, "2026-07-18")
    fst.append_history(p, "005930", 105000, "2026-07-18")  # 같은 날 두 번째 호출
    data = json.loads(p.read_text(encoding="utf-8"))
    # 하루 1점만 — 두 번째 호출이 덮어쓰되 점 개수는 늘지 않는다
    assert len(data["005930"]) == 1
    assert data["005930"][0] == {"date": "2026-07-18", "value": 105000}


def test_append_history_keeps_separate_days(tmp_path):
    p = tmp_path / "consensus_history.json"
    fst.append_history(p, "005930", 100000, "2026-07-17")
    fst.append_history(p, "005930", 105000, "2026-07-18")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert [d["date"] for d in data["005930"]] == ["2026-07-17", "2026-07-18"]


def test_append_history_ignores_none(tmp_path):
    # 컨센서스를 못 구한 날은 히스토리에 점을 남기지 않는다. 기존 점도 지우면 안 된다.
    p = tmp_path / "consensus_history.json"
    fst.append_history(p, "005930", 100000, "2026-07-17")
    fst.append_history(p, "005930", None, "2026-07-18")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert [d["date"] for d in data["005930"]] == ["2026-07-17"]
