# validate_analysis.py 단위 테스트 — 픽스처 입력으로 교정/차단 동작 검증
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_analysis as v


# ── parse_price ───────────────────────────────────────────────────────────────
def test_parse_price():
    assert v.parse_price("53,600원") == 53600.0
    assert v.parse_price("$53.60") == 53.60
    assert v.parse_price("1,518원") == 1518.0
    assert v.parse_price(53600) == 53600.0
    assert v.parse_price("없음") is None
    assert v.parse_price(None) is None


# ── find_forbidden: 금지 단위 '경' ────────────────────────────────────────────
def test_gyeong_detected():
    assert v.find_forbidden("코스피 시가총액이 <b>7경 원</b>을 돌파했어요")
    assert v.find_forbidden("시총 6경5000조 규모")


def test_gyeong_no_false_positive():
    # '경기/경제/경우/3경기' 등은 오탐하면 안 됨
    assert v.find_forbidden("3경기 연속 상승하며 경기 회복 기대감이 커졌어요") == []
    assert v.find_forbidden("경제 지표가 개선되고 경쟁이 치열해요") == []


# ── find_forbidden: 환율 범위 ─────────────────────────────────────────────────
def test_fx_range():
    assert v.find_forbidden("원달러 환율이 <b>1,518원</b>으로 안정적") == []   # 정상
    assert v.find_forbidden("환율이 950원까지 급락했어요")                       # 범위 밖
    assert v.find_forbidden("원/달러 환율 2,500원 돌파")                         # 범위 밖
    # 환율 키워드 없는 종목 가격은 건드리지 않음
    assert v.find_forbidden("삼성전자가 95,000원에 거래됐어요") == []


# ── find_forbidden: 지수 등락률 ───────────────────────────────────────────────
def test_index_pct():
    assert v.find_forbidden("코스피가 <b>+2.0%</b> 상승") == []          # 정상
    assert v.find_forbidden("코스피가 <b>+45%</b> 폭등")                  # 비정상
    # 개별 종목 45%는 가능 — 지수 키워드 없으면 통과
    assert v.find_forbidden("삼성전자가 +45% 급등") == []


# ── 계층 1: 가격 교차검증 교정 ────────────────────────────────────────────────
def _base_analysis(picks=None):
    return {
        "prediction": {"direction": "상승 우위", "up_pct": 65, "down_pct": 35},
        "reasons": ["이유1 해요.", "이유2 해요.", "이유3 해요."],
        "stock_picks": picks if picks is not None else [],
    }


def test_price_correction():
    a = _base_analysis([{
        "name": "삼성전자", "price": "70,000원", "change": "+5.00%", "change_cls": "up",
        "entry": "70,000원", "target": "77,000원", "stop": "66,000원",
    }])
    latest = {"kospi_candidates": [{"name": "삼성전자", "ticker": "005930", "price": 53600, "change_pct": -1.47}]}
    r = v.validate(a, latest, "kospi")
    assert not r["blocks"]
    p = r["analysis"]["stock_picks"][0]
    assert p["price"] == "53,600원"            # 실측으로 교정
    assert p["change"] == "-1.47%"
    assert p["change_cls"] == "down"
    # entry/target/stop도 같은 비율(53600/70000)로 스케일
    assert p["entry"] == "53,600원"
    assert v.parse_price(p["target"]) < v.parse_price("77,000원")
    assert any("가격 교정" in c for c in r["corrections"])


def test_price_within_tolerance_no_change():
    a = _base_analysis([{"name": "삼성전자", "price": "53,000원", "change": "-2.0%", "change_cls": "down"}])
    latest = {"kospi_candidates": [{"name": "삼성전자", "ticker": "005930", "price": 53600, "change_pct": -1.47}]}
    r = v.validate(a, latest, "kospi")
    assert r["analysis"]["stock_picks"][0]["price"] == "53,000원"   # ±5% 이내 → 무변경
    assert not any("가격 교정" in c for c in r["corrections"])


def test_us_price_correction_dollar():
    a = _base_analysis([{"name": "NVDA (엔비디아)", "price": "$200.00", "change": "+3.0%", "change_cls": "up"}])
    latest = {"us_candidates": [{"name": "NVDA", "ticker": "NVDA", "price": 145.30, "change_pct": 1.2}]}
    r = v.validate(a, latest, "us")
    assert r["analysis"]["stock_picks"][0]["price"] == "$145.30"


# ── 본문 금지패턴: pick 제거 / reasons 원소 제거 ──────────────────────────────
def test_pick_removed_on_forbidden():
    a = _base_analysis([
        {"name": "정상주", "price": "10,000원", "scenario": "정상 시나리오"},
        {"name": "할루주", "price": "10,000원", "scenario": "시총 6경 돌파 종목"},
    ])
    r = v.validate(a, {}, "kospi")
    names = [p["name"] for p in r["analysis"]["stock_picks"]]
    assert names == ["정상주"]
    assert not r["blocks"]


def test_reasons_element_removed():
    a = _base_analysis()
    a["reasons"] = ["정상 이유1.", "코스피 시총이 7경 원이에요.", "정상 이유2.", "정상 이유3."]
    r = v.validate(a, {}, "kospi")
    assert "코스피 시총이 7경 원이에요." not in r["analysis"]["reasons"]
    assert len(r["analysis"]["reasons"]) == 3
    assert not r["blocks"]


# ── 차단 케이스 ───────────────────────────────────────────────────────────────
def test_block_up_pct_out_of_range():
    a = _base_analysis()
    a["prediction"]["up_pct"] = 650
    r = v.validate(a, {}, "kospi")
    assert any("up_pct" in b for b in r["blocks"])


def test_block_reasons_gutted():
    a = _base_analysis()
    a["reasons"] = ["정상 이유.", "7경 원 시총.", "또 6경 원."]
    r = v.validate(a, {}, "kospi")
    assert any("reasons" in b for b in r["blocks"])   # 1개만 남아 최소 2 미만


def test_block_close_scalar_prose():
    a = {
        "prediction": {"direction": "상승 우위", "up_pct": 55},
        "market_summary": "코스피 시가총액이 6경 원을 돌파했어요.",
        "why": "정상", "what": "정상", "so_what": "정상",
    }
    r = v.validate(a, {}, "kospi-close")
    assert any("market_summary" in b for b in r["blocks"])


def test_clean_analysis_passes():
    a = _base_analysis([{"name": "삼성전자", "price": "53,500원", "change": "-1.5%", "change_cls": "down"}])
    latest = {"kospi_candidates": [{"name": "삼성전자", "ticker": "005930", "price": 53600, "change_pct": -1.47}]}
    r = v.validate(a, latest, "kospi")
    assert not r["blocks"]
    assert not r["corrections"]   # 가격 ±5% 이내, 본문 정상


def test_close_without_prediction_passes():
    # 마감 분석은 prediction 필드가 없음 — 구조 검사로 오차단하면 안 됨
    a = {
        "market_title": "외국인 순매도 속 코스닥 강세",
        "market_summary": "코스피 +0.4% 마감.", "why": "정상", "what": "정상", "so_what": "정상",
        "telegram_signals": [],
    }
    r = v.validate(a, {}, "kospi-close")
    assert not r["blocks"], r["blocks"]


def test_close_headline_excluded():
    # market_title(헤드라인)은 검사 제외 — '경'이 있어도 차단 안 됨
    a = {
        "prediction": {"direction": "상승 우위", "up_pct": 55},
        "market_title": "어쩌고 3경기 연속 상승",
        "market_summary": "정상", "why": "정상", "what": "정상", "so_what": "정상",
    }
    r = v.validate(a, {}, "kospi-close")
    assert not r["blocks"]


# ── 수급 스케일 크로스체크 ────────────────────────────────────────────────────
_SUPPLY_LATEST = {
    "investor_trading": {
        "foreign":     {"net": -6_594_100},   # 백만원 → 억원 -65,941
        "institution": {"net":    240_900},    # 억원 +2,409
        "individual":  {"net":  6_348_900},    # 억원 +63,489
    }
}


def test_supply_scale_warns_on_100x_undercount():
    # 분석 본문에 659억 언급(실제 65,941억) → 경고 발생
    a = {
        "market_summary": "", "why": "외국인이 <b>659억원</b> 순매도했어요.",
        "what": "", "so_what": "",
    }
    r = v.validate(a, _SUPPLY_LATEST, "kospi-close")
    assert any("외국인" in w and "스케일" in w for w in r["warnings"]), r["warnings"]


def test_supply_scale_clean_on_correct_value():
    # 올바른 수치(6조 5,941억) 언급 → 스케일 경고 없어야 함
    a = {
        "market_summary": "", "why": "외국인이 <b>6조 5,941억원</b> 순매도했어요.",
        "what": "", "so_what": "",
    }
    r = v.validate(a, _SUPPLY_LATEST, "kospi-close")
    assert not any("스케일" in w for w in r["warnings"]), r["warnings"]


def test_supply_scale_skipped_for_kospi():
    # kospi 브리핑은 수급 스케일 체크 비대상
    a = {
        "prediction": {"direction": "상승 우위", "up_pct": 60},
        "reasons": ["이유1", "이유2"],
        "why": "외국인이 659억 순매도.", "what": "", "so_what": "",
    }
    r = v.validate(a, _SUPPLY_LATEST, "kospi")
    assert not any("스케일" in w for w in r["warnings"]), r["warnings"]


if __name__ == "__main__":
    import traceback
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_") and callable(g)]
    passed = failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  ✗ {fn.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
