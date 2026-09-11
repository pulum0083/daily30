# 네이버 증권사 리포트 목록·상세 파싱과 컨센서스 계산을 검증하는 테스트
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytz

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_stock_targets as fst

# 2026-09-11 m.stock.naver.com/api/research/stock/005930 실응답에서 필요한 필드만 옮겼다.
LIST_JSON = [
    {"itemCode": "005930", "itemName": "삼성전자", "researchId": 93991,
     "brokerName": "하나증권", "writeDate": "2026-07-08"},
    {"itemCode": "005930", "itemName": "삼성전자", "researchId": 93978,
     "brokerName": "대신증권", "writeDate": "2026-07-07"},
]

# /api/research/company/93991 실응답(발췌)
DETAIL_JSON = {"researchContent": {
    "itemCode": "005930", "researchId": 93991, "brokerName": "하나증권",
    "writeDate": "2026-07-08", "opinion": "Buy", "goalPrice": "480000",
    "prevGoalPrice": "296000",
}}

DETAIL_NO_TARGET = {"researchContent": {"opinion": "없음", "goalPrice": ""}}


def recent_list_json(code="005930"):
    """리포트 날짜를 실행 시점 기준 상대 날짜로 만든 목록.

    main()은 오늘 날짜로 컨센서스를 계산하고 compute_consensus는 3개월 이전 리포트를 버린다.
    날짜를 하드코딩하면 그 날짜가 3개월을 지나는 순간, 코드와 무관하게 컨센서스가 None이 되어
    테스트가 달력 때문에 깨진다 — 하드코딩으로 되돌리지 말 것.
    fst.datetime을 참조하므로 테스트가 시계를 바꿔 끼우면 픽스처 날짜도 같이 따라온다.
    """
    now = fst.datetime.now()
    return [
        {"itemCode": code, "researchId": 93991, "brokerName": "하나증권",
         "writeDate": (now - timedelta(days=2)).strftime("%Y-%m-%d")},
        {"itemCode": code, "researchId": 93978, "brokerName": "대신증권",
         "writeDate": (now - timedelta(days=3)).strftime("%Y-%m-%d")},
    ]


def fake_api(list_fn=recent_list_json, detail=DETAIL_JSON):
    def _f(url):
        if "/api/research/stock/" in url:
            return list_fn(url.split("/api/research/stock/")[1].split("?")[0])
        return detail
    return _f


def test_parse_report_list_extracts_rows():
    rows = fst.parse_report_list(LIST_JSON, "005930")
    assert len(rows) == 2
    assert rows[0] == {"firm": "하나증권", "date": "26.07.08", "nid": "93991"}
    assert rows[1]["firm"] == "대신증권"


def test_parse_report_list_drops_other_stocks():
    # 같은 계열 /api/research/company는 itemCode를 조용히 무시하고 전 종목을 돌려줬다.
    # 필터가 풀려도 남의 목표가가 컨센서스에 섞이면 안 된다.
    mixed = LIST_JSON + [{"itemCode": "112610", "researchId": 96103,
                          "brokerName": "DS투자증권", "writeDate": "2026-09-11"}]
    assert [r["nid"] for r in fst.parse_report_list(mixed, "005930")] == ["93991", "93978"]


def test_parse_report_list_skips_broken_rows():
    broken = [{"itemCode": "005930", "researchId": 1, "brokerName": "A증권", "writeDate": "2026-13-01"},
              {"itemCode": "005930", "researchId": None, "brokerName": "B증권", "writeDate": "2026-07-01"},
              "광고"]
    assert fst.parse_report_list(broken, "005930") == []
    assert fst.parse_report_list({"error": "x"}, "005930") == []


def test_parse_report_detail_extracts_target_and_opinion():
    assert fst.parse_report_detail(DETAIL_JSON) == {"target_price": 480000, "opinion": "Buy"}


def test_parse_report_detail_returns_none_when_placeholder():
    # 목표가가 없는 리포트는 goalPrice가 비고 투자의견이 '없음'으로 온다.
    # 이걸 그대로 두면 UI에 '없음' 투자의견 뱃지가 뜬다 — 둘 다 None이어야 한다.
    assert fst.parse_report_detail(DETAIL_NO_TARGET) == {"target_price": None, "opinion": None}
    assert fst.parse_report_detail({"researchContent": {"goalPrice": "0"}})["target_price"] is None
    assert fst.parse_report_detail({}) == {"target_price": None, "opinion": None}


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


def _isolate(monkeypatch, tmp_path, close=255000):
    history = tmp_path / "consensus_history.json"
    out = tmp_path / "stock-targets.json"
    monkeypatch.setattr(fst, "HISTORY_JSON", history)
    monkeypatch.setattr(fst, "OUT_JSON", out)
    monkeypatch.setattr(fst, "STOCKS", {"005930": "삼성전자"})
    monkeypatch.setattr(fst, "fetch_close_price", lambda code: close)
    return history, out


def test_main_suppresses_consensus_when_most_detail_fetches_fail(monkeypatch, tmp_path):
    # 상세 조회가 대량 실패하면 살아남은 소수로 평균을 내지 않는다.
    # 1개사 평균이 정상 데이터와 똑같이 렌더되면 조용한 오염이다(운영규칙 0).
    history, out = _isolate(monkeypatch, tmp_path)
    calls = {"detail": 0}

    def fake_fetch(url):
        if "/api/research/stock/" in url:
            return recent_list_json()  # 2건짜리 목록이 페이지마다 반환된다
        calls["detail"] += 1
        # 상세 4건 중 3건 실패 (75% > 30% 임계)
        if calls["detail"] % 4 != 0:
            raise OSError("네트워크 오류")
        return DETAIL_JSON

    monkeypatch.setattr(fst, "fetch_json", fake_fetch)
    fst.main()

    stock = json.loads(out.read_text(encoding="utf-8"))["stocks"]["005930"]
    assert stock["consensus"] is None
    assert stock["firm_count"] == 0
    # 오염된 평균으로 추이를 더럽히지 않는다 — 히스토리 파일 자체가 생기지 않는다
    assert not history.exists()


def test_main_keeps_consensus_when_detail_fetches_succeed(monkeypatch, tmp_path):
    # 대조군 — 실패가 없으면 컨센서스와 히스토리가 정상적으로 나와야 한다.
    history, out = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(fst, "fetch_json", fake_api())
    fst.main()

    stock = json.loads(out.read_text(encoding="utf-8"))["stocks"]["005930"]
    assert stock["consensus"] == 480000
    assert stock["firm_count"] == 2
    assert len(json.loads(history.read_text(encoding="utf-8"))["005930"]) == 1


def test_main_keeps_previous_file_when_every_list_is_empty(monkeypatch, tmp_path):
    """2026-09-11 실사고 재현: 네이버가 리서치 게시판을 옮기자 목록 파서가 3종목 모두 0행을
    읽었고, 수집기가 멀쩡한 파일을 리포트 0건으로 덮어써 허브·상세의 목표주가가 전부 사라졌다.
    전 종목 0건은 '리포트가 없다'가 아니라 '원천을 못 읽었다'이므로 파일을 건드리지 않는다."""
    history, out = _isolate(monkeypatch, tmp_path)
    good = '{"updated_at": "2026-09-10", "stocks": {"005930": {"reports": [1]}}}'
    out.write_text(good, encoding="utf-8")
    alerts = []
    monkeypatch.setattr(fst, "_alert_collection_dead", alerts.append)
    monkeypatch.setattr(fst, "fetch_json", fake_api(list_fn=lambda code: []))

    with pytest.raises(SystemExit) as e:
        fst.main()
    assert e.value.code == 1
    assert out.read_text(encoding="utf-8") == good
    assert not history.exists()
    assert len(alerts) == 1


def test_main_stamps_kst_date_not_utc_date(monkeypatch, tmp_path):
    """2026-07-27 실사고 재현: GHA 러너(UTC)에서 KST 07:2x 아침 실행 시
    datetime.now()가 UTC 날짜(전날)를 돌려줘 updated_at·히스토리가 하루 밀렸다.
    월요일 07:29 KST(=일요일 22:29 UTC) 실행을 재현해 오늘 날짜(월요일)로
    찍히는지 검증한다 — 일요일(비거래일) 날짜가 남으면 회귀."""
    history, out = _isolate(monkeypatch, tmp_path, close=254000)
    monkeypatch.setattr(fst, "fetch_json", fake_api())

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
