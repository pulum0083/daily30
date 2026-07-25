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


def test_close_scalar_prose_all_forbidden_is_emptied_not_blocked():
    """스칼라 본문이 전부 금지 패턴이면 필드를 비우고 warning만 남긴다 — 차단하지 않는다.

    2026-06-04(aa0e4eb3)에 "한 문장 때문에 브리핑 전체를 막는 건 과하다"로 정책이
    바뀌었다. WHY/WHAT/SO가 본문을 이어받고, 템플릿이 빈 값을 가드한다.
    """
    a = {
        "prediction": {"direction": "상승 우위", "up_pct": 55},
        "market_summary": "코스피 시가총액이 6경 원을 돌파했어요.",
        "why": "정상", "what": "정상", "so_what": "정상",
    }
    r = v.validate(a, {}, "kospi-close")
    assert not r["blocks"], "발행을 막아서는 안 된다"
    assert r["analysis"]["market_summary"] == "", "금지 문장은 남지 않아야 한다"
    assert any("market_summary" in w for w in r["warnings"]), "warning으로 알려야 한다"


def test_close_scalar_prose_partial_forbidden_keeps_clean_sentences():
    """일부 문장만 금지 패턴이면 그 문장만 빼고 나머지로 발행한다."""
    a = {
        "prediction": {"direction": "상승 우위", "up_pct": 55},
        "market_summary": "외국인이 순매수로 돌아섰어요. 시가총액이 6경 원을 넘었어요.",
        "why": "정상", "what": "정상", "so_what": "정상",
    }
    r = v.validate(a, {}, "kospi-close")
    assert not r["blocks"]
    ms = r["analysis"]["market_summary"]
    assert "외국인이 순매수로 돌아섰어요." in ms
    assert "경" not in ms, f"금지 단위가 남았다: {ms!r}"
    assert any("market_summary" in c for c in r["corrections"])


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


# ── 픽 종목 티커 해석 ─────────────────────────────────────────────────────────
def test_resolve_ticker_us():
    assert v._resolve_ticker({"name": "NVDA (엔비디아)", "ticker": None}, "us") == "NVDA"
    assert v._resolve_ticker({"name": "BAC (뱅크오브아메리카)"}, "us") == "BAC"
    assert v._resolve_ticker({"ticker": "MSFT", "name": "마이크로소프트"}, "us") == "MSFT"
    # 영문 티커로 해석 불가(한글명만)면 빈 문자열
    assert v._resolve_ticker({"name": "마이크로소프트"}, "us") == ""


def test_resolve_ticker_kospi():
    # KOSPI·KOSDAQ 모두 6자리 코드만 반환 (.KS/.KQ 접미사 금지 — 네이버 일봉용)
    assert v._resolve_ticker({"ticker": "005930", "name": "삼성전자"}, "kospi") == "005930"
    assert v._resolve_ticker({"ticker": "005930.KS", "name": "삼성전자"}, "kospi") == "005930"
    assert v._resolve_ticker({"ticker": "247540", "name": "에코프로비엠"}, "kospi") == "247540"
    # 종목코드 없으면 빈 문자열(이름만으로 추측 금지)
    assert v._resolve_ticker({"name": "삼성전자"}, "kospi") == ""


# ── 픽 실측 주입 (fetch 스텁) ─────────────────────────────────────────────────
def test_enrich_picks_overwrites_and_injects():
    real = {"price": 224.36, "change_pct": 6.26, "ma20_dist_pct": 3.5,
            "ma200_dist_pct": 19.4, "sparkline": [1, 2, 3],
            "ma20_sparkline": [1, 2, 3], "ma200_sparkline": [1, 2, 3]}
    orig = v._fetch_pick_realdata
    v._fetch_pick_realdata = lambda tk, is_us: real
    try:
        analysis = {"stock_picks": [
            {"name": "NVDA (엔비디아)", "ticker": None, "change": "+2.14%",
             "price": "$1.00", "ma200_dist_pct": 99}
        ]}
        latest = {"us_candidates": [
            {"ticker": "NVDA (엔비디아)", "name": "NVDA (엔비디아)", "sparkline": [999]}
        ]}
        cor, warn = [], []
        changed = v.enrich_picks_with_realdata(analysis, latest, "us", cor, warn)
        p = analysis["stock_picks"][0]
        assert changed is True
        assert p["change"] == "+6.26%"
        assert p["change_cls"] == "up"
        assert p["price"] == "$224.36"
        assert p["ma200_dist_pct"] == 19.4
        # candidate는 중복 추가가 아니라 교체, sparkline은 실측
        cands = latest["us_candidates"]
        assert len(cands) == 1
        assert cands[0]["ticker"] == "NVDA"
        assert cands[0]["sparkline"] == [1, 2, 3]
    finally:
        v._fetch_pick_realdata = orig


def test_enrich_picks_down_class():
    orig = v._fetch_pick_realdata
    v._fetch_pick_realdata = lambda tk, is_us: {"price": 51.51, "change_pct": -0.17,
                                                "sparkline": [1], "ma20_sparkline": [1],
                                                "ma200_sparkline": [1]}
    try:
        analysis = {"stock_picks": [{"name": "BAC (뱅크오브아메리카)", "change": "+0.12%"}]}
        latest = {}
        cor, warn = [], []
        v.enrich_picks_with_realdata(analysis, latest, "us", cor, warn)
        p = analysis["stock_picks"][0]
        assert p["change"] == "-0.17%"
        assert p["change_cls"] == "down"
    finally:
        v._fetch_pick_realdata = orig


def test_enrich_picks_kospi_uses_bare_code_and_won():
    """코스피 픽: 6자리 코드로 fetch, price는 원화 포맷, candidate ticker는 코드."""
    captured = {}

    def fake(tk, is_us):
        captured["tk"], captured["is_us"] = tk, is_us
        return {"price": 360500.0, "change_pct": 3.30, "ma200_dist_pct": 5.1,
                "sparkline": [1], "ma20_sparkline": [1], "ma200_sparkline": [1]}

    orig = v._fetch_pick_realdata
    v._fetch_pick_realdata = fake
    try:
        analysis = {"stock_picks": [{"name": "삼성전자", "ticker": "005930", "change": "+9.9%"}]}
        latest = {}
        cor, warn = [], []
        v.enrich_picks_with_realdata(analysis, latest, "kospi", cor, warn)
        p = analysis["stock_picks"][0]
        assert captured["tk"] == "005930"   # .KS 없이 6자리 코드
        assert captured["is_us"] is False
        assert p["change"] == "+3.30%"
        assert p["price"] == "360,500원"
        assert latest["kospi_candidates"][0]["ticker"] == "005930"
    finally:
        v._fetch_pick_realdata = orig


def test_enrich_picks_unresolvable_ticker_warns():
    analysis = {"stock_picks": [{"name": "삼성전자"}]}  # kospi 코드 없음
    latest = {}
    cor, warn = [], []
    changed = v.enrich_picks_with_realdata(analysis, latest, "kospi", cor, warn)
    assert changed is False
    assert any("티커 해석 실패" in w for w in warn)


# ── validate_todays_view_recap ────────────────────────────────────────────────
def test_todays_view_recap_removes_contradicted_stock(monkeypatch):
    def fake_fetch(code):
        return {"change_pct": -1.5, "price": 70000.0} if code == "005930" else {"error": "n/a"}
    monkeypatch.setattr(v, "_fetch_kospi_realdata", fake_fetch)
    analysis = {"todays_view": {"view_title": "t", "recap": [
        {"text": "<b>삼성전자</b>가 급등하며 지수를 끌어올렸어요.", "codes": ["005930"]},
        {"text": "외국인이 순매수로 전환했어요.", "codes": []},
    ], "outlook": []}}
    corrections, warnings = [], []
    v.validate_todays_view_recap(analysis, "kospi", corrections, warnings)
    texts = [r["text"] for r in analysis["todays_view"]["recap"]]
    assert "삼성전자" not in " ".join(texts)
    assert "외국인" in " ".join(texts)
    assert any("todays_view" in c for c in corrections)


def test_todays_view_recap_warns_on_fetch_failure(monkeypatch):
    """실측 실패 종목은 fail-open(항목 유지)하되 경고를 남긴다."""
    monkeypatch.setattr(v, "_fetch_kospi_realdata", lambda code: {"error": "n/a"})
    analysis = {"todays_view": {"view_title": "t", "recap": [
        {"text": "<b>미검증종목</b>이 강세였어요.", "codes": ["123456"]},
    ], "outlook": []}}
    corrections, warnings = [], []
    v.validate_todays_view_recap(analysis, "kospi", corrections, warnings)
    # 실측 실패라 교차검증 불가 → 항목은 유지되고 경고만 남음
    assert len(analysis["todays_view"]["recap"]) == 1
    assert any("123456" in w and "실측 실패" in w for w in warnings)


# ── validate_todays_view_outlook ──────────────────────────────────────────────
def test_todays_view_outlook_drops_ungrounded_event():
    analysis = {"todays_view": {"view_title": "t", "recap": [], "outlook": [
        {"tag": "event", "text": "삼성전자 잠정실적 임박.", "source": "news"},
        {"tag": "event", "text": "FOMC가 오늘 열려요.", "source": None},
        {"tag": "watch", "text": "외국인 순매수 이어질지 보세요.", "source": None},
    ]}}
    corrections, warnings = [], []
    v.validate_todays_view_outlook(analysis, "kospi", corrections, warnings)
    kept = analysis["todays_view"]["outlook"]
    assert any("삼성전자 잠정실적 임박." in o["text"] for o in kept)
    assert all("FOMC" not in o["text"] for o in kept)
    assert any(o["tag"] == "watch" for o in kept)
    assert any("todays_view.outlook" in c for c in corrections)


# ── validate() wiring ─────────────────────────────────────────────────────────
def test_validate_wires_todays_view(monkeypatch):
    def fake_fetch(code):
        return {"change_pct": -1.5, "price": 70000.0} if code == "005930" else {"error": "n/a"}
    monkeypatch.setattr(v, "_fetch_kospi_realdata", fake_fetch)
    analysis = {
        "prediction": {"direction": "상승 우위", "up_pct": 55},
        "todays_view": {"view_title": "t", "recap": [
            {"text": "<b>삼성전자</b>가 급등하며 지수를 끌어올렸어요.", "codes": ["005930"]},
        ], "outlook": [
            {"tag": "event", "text": "FOMC가 오늘 열려요.", "source": None},
        ]},
    }
    r = v.validate(analysis, {}, "kospi")
    assert any("todays_view.recap" in c for c in r["corrections"])
    assert any("todays_view.outlook" in c for c in r["corrections"])


# ── validate_key_drivers: codes 없는 US 지수·ETF 검증 (2026-07-22 실사고) ──────
def test_us_figure_stale_catches_adjacent_session():
    # EWY '+6.18%'(전 세션 값) vs 실측 '+1.72%' → diff 4.46%p. tol 2%p 초과 → stale.
    assert v._us_figure_stale("EWY가 <b>+6.18%</b> 폭등했어요.", 1.72) is True
    # 같은 세션 값 인용 → 통과.
    assert v._us_figure_stale("EWY가 <b>+1.72%</b> 올랐어요.", 1.72) is False
    # 반올림 오차 수준 → 통과.
    assert v._us_figure_stale("SOX가 <b>+5.20%</b> 급등했어요.", 5.23) is False


def test_is_contradicted_misses_adjacent_session():
    # 왜 별도 타이트 임계치가 필요한지 문서화: 기존 게이트는 이 stale을 못 잡는다.
    assert v.is_contradicted(6.18, 1.72) is False


def test_key_drivers_removes_stale_us_figure(monkeypatch):
    # 실사고 재현: 직전 세션 EWY 실측이 +1.72%인데 브리핑은 +6.18%(전 세션)를 인용.
    monkeypatch.setattr(v, "_fetch_us_realdata",
                        lambda t: {"change_pct": 1.72} if t == "EWY" else {"error": "n/a"})
    analysis = {"key_drivers": [
        {"text": "<b>외국인 자금이 유입되고 있어요.</b> EWY가 <b>+6.18%</b> 폭등했어요.", "codes": []},
        {"text": "<b>수급이 개선됐어요.</b> 기관이 순매수로 전환했어요.", "codes": []},
    ]}
    corrections, warnings = [], []
    v.validate_key_drivers(analysis, "kospi", corrections, warnings)
    texts = " ".join(d["text"] for d in analysis["key_drivers"])
    assert "EWY" not in texts          # stale 항목 제거
    assert "기관" in texts             # 정상 항목 유지
    assert any("EWY" in c for c in corrections)


def test_key_drivers_keeps_fresh_us_figure(monkeypatch):
    monkeypatch.setattr(v, "_fetch_us_realdata",
                        lambda t: {"change_pct": 1.72} if t == "EWY" else {"error": "n/a"})
    analysis = {"key_drivers": [
        {"text": "<b>외국인 자금이 유입되고 있어요.</b> EWY가 <b>+1.72%</b> 올랐어요.", "codes": []},
    ]}
    corrections, warnings = [], []
    v.validate_key_drivers(analysis, "kospi", corrections, warnings)
    assert len(analysis["key_drivers"]) == 1   # 실측과 일치 → 유지


def test_key_drivers_us_fetch_failure_fail_open(monkeypatch):
    # 실측 실패 시 정상 항목을 오제거하지 않는다(fail-open).
    monkeypatch.setattr(v, "_fetch_us_realdata", lambda t: {"error": "n/a"})
    analysis = {"key_drivers": [
        {"text": "<b>반도체 강세예요.</b> SOX가 <b>+5.21%</b> 급등했어요.", "codes": []},
    ]}
    corrections, warnings = [], []
    v.validate_key_drivers(analysis, "kospi", corrections, warnings)
    assert len(analysis["key_drivers"]) == 1


if __name__ == "__main__":
    # monkeypatch 등 pytest 픽스처를 받는 테스트는 이 러너가 인자를 줄 수 없어 건너뛴다.
    # (예전엔 인자 없이 호출해 TypeError를 '실패'로 세서, 코드가 정상인데도 항상
    #  7건 실패로 보였다.) 전체 검증은 pytest로 돌릴 것.
    import inspect
    import traceback

    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_") and callable(g)]
    passed = failed = 0
    needs_fixture = []
    for fn in fns:
        if inspect.signature(fn).parameters:
            needs_fixture.append(fn.__name__)
            continue
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  ✗ {fn.__name__}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    if needs_fixture:
        print(f"픽스처 필요로 건너뜀 {len(needs_fixture)}건 — 전체는 "
              f"'python3 -m pytest {Path(__file__).name}'로 돌리세요:")
        for n in needs_fixture:
            print(f"  · {n}")
    sys.exit(1 if failed else 0)
