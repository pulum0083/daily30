# 마감 브리핑 본문의 수급 금액을 15:40 확정 실측으로 교정하는지 — 2026-10-28 실사고 리플레이
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_analysis as va

LATEST = {"investor_trading": {"foreign": {"net": 815700}, "institution": {"net": 960900}, "individual": {"net": -1801600}}}


def _fix(text):
    a, c, w = {"x": text}, [], []
    va.fix_supply_amounts(a, LATEST, c, w)
    return a["x"], c


def test_incident_dek_each_amount():
    out, c = _fix("외국인과 기관이 각각 <b>1조 1,485억원</b>씩 쌍끌이 매수로 화답했어요.")
    assert out == "외국인과 기관이 각각 <b>8,157억원·9,609억원</b> 쌍끌이 매수로 화답했어요."
    assert c


def test_incident_why_two_amounts():
    out, _ = _fix("외국인이 <b>1조 1485억원</b>, 기관이 <b>1조 1519억원</b>을 동시에 순매수했어요.")
    assert out == "외국인이 <b>8,157억원</b>, 기관이 <b>9,609억원</b>을 동시에 순매수했어요."


def test_correct_values_are_kept():
    for s in ["외국인 8,157억원 순매수", "개인은 1조 8,016억원을 팔았어요.", "개인 1.8조 순매도"]:
        assert _fix(s)[0] == s


def test_other_days_periods_and_amounts_are_left_alone():
    for s in ["3일간 외국인이 2조 1,000억원을 사들였어요.", "어제 외국인은 5,929억원을 샀어요.",
              "코스피 거래대금은 19조 8,368억원이었어요.", "SK하이닉스 영업이익은 기관 예상보다 1조 원 많았어요."]:
        assert _fix(s)[0] == s


def test_no_measured_supply_no_change():
    a = {"x": "외국인이 1조 1485억원을 샀어요."}
    assert va.fix_supply_amounts(a, {}, [], []) == 0 and a["x"] == "외국인이 1조 1485억원을 샀어요."
