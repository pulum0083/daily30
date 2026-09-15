# 밸류에이션 PER 회귀 테스트 — 장 마감 뒤 PER이 애프터장 가격이 아니라 정규장 공식 종가 ÷ EPS인지(§48)
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_valuation as fv  # noqa: E402
import kr_official_closes as koc  # noqa: E402

KST = koc.KST

# 2026-09-15 16:40 integration 실측 — SK하이닉스 PER 7.53(애프터장 가격 기반), EPS 224,313, 추정 EPS 349,573.
# 그날 15:30 공식 종가 1,690,000.
SKH = {"code": "000660", "per": 7.53, "cnsPer": 4.83, "eps": 224313.0, "cnsEps": 349573.0}


def test_per_rebased_on_official_close():
    r = fv.rebase_per_on_close(SKH, 1690000.0)
    assert r["per"] == round(1690000 / 224313, 2) == 7.53
    assert r["cnsPer"] == round(1690000 / 349573, 2) == 4.83
    # 삼성전자 — 반올림된 EPS로도 원천 PER이 재현된다(248,500 / 22,292 = 11.15)
    assert fv.rebase_per_on_close({"per": 11.2, "cnsPer": None, "eps": 22292.0, "cnsEps": None},
                                  248500.0)["per"] == 11.15


def test_missing_close_empties_per_instead_of_keeping_aftermarket_value():
    r = fv.rebase_per_on_close(SKH, None)
    assert r["per"] is None and r["cnsPer"] is None


def test_na_per_stays_none():
    r = fv.rebase_per_on_close({"per": 95.28, "cnsPer": None, "eps": 2330.0, "cnsEps": None}, 222500.0)
    assert r["per"] == round(222500 / 2330, 2)
    assert r["cnsPer"] is None                    # 한미반도체 추정 PER N/A는 만들지 않는다


def test_regular_session_window():
    at = lambda hhmm: datetime.strptime("20260915" + hhmm, "%Y%m%d%H%M").replace(tzinfo=KST)
    assert fv.regular_session_open(at("1000")) and fv.regular_session_open(at("1530"))
    assert not fv.regular_session_open(at("1625")) and not fv.regular_session_open(at("0830"))


def test_last_closed_session():
    at = lambda d, hhmm: datetime.strptime(d + hhmm, "%Y%m%d%H%M").replace(tzinfo=KST)
    assert koc.last_closed_session(at("20260915", "1625")) == "20260915"   # 마감 잡
    assert koc.last_closed_session(at("20260915", "1400")) == "20260914"   # 장중 → 전 거래일
    assert koc.last_closed_session(at("20260914", "0830")) == "20260911"   # 월요일 아침 → 금요일
    assert koc.last_closed_session(at("20260928", "1000")) == "20260923"   # 추석 연휴 뒤
