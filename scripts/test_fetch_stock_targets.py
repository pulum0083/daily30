# 네이버 증권사 리포트 목록·상세 파싱과 컨센서스 계산을 검증하는 테스트
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytz

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


def recent_list_html():
    """리포트 날짜를 실행 시점 기준 상대 날짜로 만든 목록 HTML.

    main()은 오늘 날짜로 컨센서스를 계산하고 compute_consensus는 3개월 이전 리포트를 버린다.
    날짜를 하드코딩하면 그 날짜가 3개월을 지나는 순간, 코드와 무관하게 컨센서스가 None이 되어
    테스트가 달력 때문에 깨진다 — 하드코딩으로 되돌리지 말 것.
    fst.datetime을 참조하므로 테스트가 시계를 바꿔 끼우면 픽스처 날짜도 같이 따라온다.
    """
    now = fst.datetime.now()
    d1 = (now - timedelta(days=2)).strftime("%y.%m.%d")
    d2 = (now - timedelta(days=3)).strftime("%y.%m.%d")
    return f"""
<table><tbody>
<tr><td><a href="/item/main.naver?code=005930">삼성전자</a></td>
<td><a href="company_read.naver?nid=93991&page=1">메모리 이익 체력 확인</a></td>
<td>하나증권</td><td>{d1}</td><td>5527</td></tr>
<tr><td><a href="/item/main.naver?code=005930">삼성전자</a></td>
<td><a href="company_read.naver?nid=93978&page=1">체급의 위력</a></td>
<td>대신증권</td><td>{d2}</td><td>5081</td></tr>
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


def test_append_history_recovers_from_corrupt_file(tmp_path):
    # 이전 실행이 쓰다 죽어 파일이 깨져도 이후 실행이 영구히 막히면 안 된다.
    p = tmp_path / "consensus_history.json"
    p.write_text('{"005930": [{"date": "2026-07-1', encoding="utf-8")
    fst.append_history(p, "005930", 100000, "2026-07-18")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["005930"] == [{"date": "2026-07-18", "value": 100000}]


def test_main_suppresses_consensus_when_most_detail_fetches_fail(monkeypatch, tmp_path):
    # 상세 조회가 대량 실패하면 살아남은 소수로 평균을 내지 않는다.
    # 1개사 평균이 정상 데이터와 똑같이 렌더되면 조용한 오염이다(운영규칙 0).
    history = tmp_path / "consensus_history.json"
    out = tmp_path / "stock-targets.json"
    monkeypatch.setattr(fst, "HISTORY_JSON", history)
    monkeypatch.setattr(fst, "OUT_JSON", out)
    monkeypatch.setattr(fst, "STOCKS", {"005930": "삼성전자"})
    monkeypatch.setattr(fst, "fetch_close_price", lambda code: 255000)

    calls = {"detail": 0}

    def fake_fetch(url):
        if "company_list" in url:
            return recent_list_html()  # 2건짜리 목록이 페이지마다 반환된다
        calls["detail"] += 1
        # 상세 4건 중 3건 실패 (75% > 30% 임계)
        if calls["detail"] % 4 != 0:
            raise OSError("네트워크 오류")
        return DETAIL_HTML

    monkeypatch.setattr(fst, "fetch_euckr", fake_fetch)
    fst.main()

    data = json.loads(out.read_text(encoding="utf-8"))
    stock = data["stocks"]["005930"]
    assert stock["consensus"] is None
    assert stock["firm_count"] == 0
    # 오염된 평균으로 추이를 더럽히지 않는다 — 히스토리 파일 자체가 생기지 않는다
    assert not history.exists()


def test_main_keeps_consensus_when_detail_fetches_succeed(monkeypatch, tmp_path):
    # 대조군 — 실패가 없으면 컨센서스와 히스토리가 정상적으로 나와야 한다.
    history = tmp_path / "consensus_history.json"
    out = tmp_path / "stock-targets.json"
    monkeypatch.setattr(fst, "HISTORY_JSON", history)
    monkeypatch.setattr(fst, "OUT_JSON", out)
    monkeypatch.setattr(fst, "STOCKS", {"005930": "삼성전자"})
    monkeypatch.setattr(fst, "fetch_close_price", lambda code: 255000)
    monkeypatch.setattr(
        fst, "fetch_euckr",
        lambda url: recent_list_html() if "company_list" in url else DETAIL_HTML,
    )
    fst.main()

    stock = json.loads(out.read_text(encoding="utf-8"))["stocks"]["005930"]
    assert stock["consensus"] == 480000
    assert stock["firm_count"] == 2
    assert len(json.loads(history.read_text(encoding="utf-8"))["005930"]) == 1


def test_main_stamps_kst_date_not_utc_date(monkeypatch, tmp_path):
    """2026-07-27 실사고 재현: GHA 러너(UTC)에서 KST 07:2x 아침 실행 시
    datetime.now()가 UTC 날짜(전날)를 돌려줘 updated_at·히스토리가 하루 밀렸다.
    월요일 07:29 KST(=일요일 22:29 UTC) 실행을 재현해 오늘 날짜(월요일)로
    찍히는지 검증한다 — 일요일(비거래일) 날짜가 남으면 회귀."""
    history = tmp_path / "consensus_history.json"
    out = tmp_path / "stock-targets.json"
    monkeypatch.setattr(fst, "HISTORY_JSON", history)
    monkeypatch.setattr(fst, "OUT_JSON", out)
    monkeypatch.setattr(fst, "STOCKS", {"005930": "삼성전자"})
    monkeypatch.setattr(fst, "fetch_close_price", lambda code: 254000)
    monkeypatch.setattr(
        fst, "fetch_euckr",
        lambda url: recent_list_html() if "company_list" in url else DETAIL_HTML,
    )

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            # 2026-07-27(월) 07:29 KST = 2026-07-26(일) 22:29 UTC
            utc_now = datetime(2026, 7, 26, 22, 29, 51, tzinfo=pytz.UTC)
            return utc_now.astimezone(tz) if tz else utc_now

    monkeypatch.setattr(fst, "datetime", FrozenDatetime)
    fst.main()

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["updated_at"] == "2026-07-27"
    hist_dates = [h["date"] for h in json.loads(history.read_text(encoding="utf-8"))["005930"]]
    assert hist_dates == ["2026-07-27"]
    assert "2026-07-26" not in hist_dates  # 실제로 실행되지 않은 일요일 날짜가 남으면 안 된다
