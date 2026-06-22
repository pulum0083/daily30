# 산문 % 수치 불일치 판정 함수(is_contradicted) 단위 테스트
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from validate_analysis import is_contradicted, _extract_change_claims, validate_prose_against_picks

def test_large_discrepancy_flagged():
    # AVGO 케이스: 실측 -0.49% vs 텍스트 +15.8%
    assert is_contradicted(15.8, -0.49) is True

def test_small_diff_passes():
    # +4.2% 텍스트 vs +4.0% 실측 → 허용 (5%p 이내)
    assert is_contradicted(4.2, 4.0) is False

def test_near_zero_real_uses_diff_only():
    # 실측 0.1% vs 텍스트 +10% → diff=9.9 > 5 → 차단
    assert is_contradicted(10.0, 0.1) is True

def test_near_zero_real_small_diff_passes():
    # 실측 0.1% vs 텍스트 +2% → diff=1.9 < 5 → 허용
    assert is_contradicted(2.0, 0.1) is False

def test_ratio_exactly_5x_flagged():
    # 실측 2% vs 텍스트 10% → ratio=5 → 차단
    assert is_contradicted(10.0, 2.0) is True

def test_ratio_below_5x_passes():
    # 실측 2% vs 텍스트 8% → diff=6>5 but ratio=4<5 → 허용
    assert is_contradicted(8.0, 2.0) is False

def test_sign_flip_flagged():
    # +5% 텍스트 vs -2% 실측 → 방향 반전 → 차단
    assert is_contradicted(5.0, -2.0) is True

def test_real_zero_exact():
    # 실측 정확히 0.0 → ZeroDivisionError 없이 diff만으로 판정
    assert is_contradicted(10.0, 0.0) is True
    assert is_contradicted(3.0, 0.0) is False


def test_change_claim_detects_jeonil():
    # "전일 +X%" 패턴
    text = "전일 <b>+15.80%</b> 폭등하며 20일선 위로 강하게 치솟은 종목이에요."
    claims = _extract_change_claims(text)
    assert claims == [15.80]

def test_change_claim_detects_poldeung():
    # "+X% 폭등" 패턴
    text = "단 하루에 +15.8% 폭등했거든요."
    claims = _extract_change_claims(text)
    assert claims == [15.8]

def test_change_claim_ignores_ma():
    # "MA 대비 +X%" 는 change claim이 아님
    text = "20일선 대비 +11% 이상 상회 중인 종목이에요."
    claims = _extract_change_claims(text)
    assert claims == []

def test_change_claim_ignores_target():
    # "목표 +X%" 는 change claim이 아님
    text = "목표 +8.5% / 손절 -5.2%"
    claims = _extract_change_claims(text)
    assert claims == []

def test_change_claim_detects_geupnak():
    # "-X% 급락" 패턴
    text = "엔비디아(NVDA)는 -3.62% 급락했어요."
    claims = _extract_change_claims(text)
    assert claims == [-3.62]


# ── validate_prose_against_picks 테스트 ──────────────────────────────────────

def _make_pick(ticker, name, change_pct):
    return {"ticker": ticker, "name": name, "change_pct": change_pct,
            "price": "$100", "change": f"{change_pct:+.2f}%",
            "scenario": "", "action_guide": ""}

def test_removes_contradicted_reason():
    analysis = {
        "stock_picks": [_make_pick("AVGO", "AVGO (브로드컴)", -0.49)],
        "reasons": [
            "📈 선물이 약세예요.",
            "💡 브로드컴(AVGO)이 단 하루에 +15.8% 폭등했거든요.",
            "🌏 아시아 증시가 하락했어요.",
        ],
        "watch_items": [],
    }
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    assert len(analysis["reasons"]) == 2
    assert any("AVGO" in c for c in corrections)

def test_keeps_valid_reason():
    analysis = {
        "stock_picks": [_make_pick("META", "META (메타)", 4.24)],
        "reasons": ["META가 +4.2% 상승했어요."],
        "watch_items": [],
    }
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    assert len(analysis["reasons"]) == 1

def test_removes_contradicted_scenario_sentence():
    pick = _make_pick("AVGO", "AVGO (브로드컴)", -0.49)
    pick["scenario"] = "전일 +15.80% 폭등하며 20일선 위로 강하게 치솟은 종목이에요. 반도체 온기가 유입되고 있어요."
    analysis = {"stock_picks": [pick], "reasons": ["a", "b"], "watch_items": []}
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    scenario = analysis["stock_picks"][0]["scenario"]
    assert "+15.80%" not in scenario
    assert "반도체 온기" in scenario

def test_removes_contradicted_watchpoint():
    analysis = {
        "stock_picks": [_make_pick("AVGO", "AVGO (브로드컴)", -0.49)],
        "reasons": ["a", "b"],
        "watch_items": [
            {"icon": "💡", "label": "AVGO 모멘텀",
             "text": "브로드컴이 단 하루에 +15.8% 폭등했어요."},
            {"icon": "📅", "label": "NFP",
             "text": "내일 발표 예정이에요."},
        ],
    }
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    assert len(analysis["watch_items"]) == 1
    assert analysis["watch_items"][0]["label"] == "NFP"

def test_blocks_when_reasons_below_min():
    analysis = {
        "stock_picks": [_make_pick("AVGO", "AVGO (브로드컴)", -0.49)],
        "reasons": [
            "💡 AVGO 단 하루에 +15.8% 폭등했어요.",
            "🌏 AVGO 하루 만에 +15.8% 급등했어요.",
        ],
        "watch_items": [],
    }
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "us", corrections, warnings, blocks)
    assert len(blocks) > 0

def test_skips_kospi_close():
    analysis = {"reasons": ["테스트"], "watch_items": []}
    corrections, warnings, blocks = [], [], []
    validate_prose_against_picks(analysis, "kospi-close", corrections, warnings, blocks)
    assert corrections == [] and blocks == []


# ── 회귀: 2026-06-22 us — "DRAM ETF가 -1.84% 내려앉아" 환각 산문 ──────────────
# 실제 DRAM ETF 직전 세션(2026-06-18, 6/19 준틴스 휴장)은 +9.66% 상승이었으나
# LLM이 reasons 산문에 -1.84% 하락을 생성. 세 겹의 검증 구멍을 모두 막는다:
#   ① "내려앉" 하락 동사 미등록 → 정량 추출 실패
#   ② "내려앉" 정성 방향 단어 미등록
#   ③ "DRAM"이 _NON_TICKER 제외 목록 → 산문 후보에서 누락
from validate_analysis import (_direction_contradicts, _NON_TICKER,
                               validate_prose_nonpick_stocks)
import validate_analysis as va


def test_naeryeoanja_quantitative_claim_extracted():
    # ① "-1.84% 내려앉아"에서 정량 -1.84 추출되어야 한다
    claims = _extract_change_claims("DRAM ETF가 -1.84% 내려앉아 차별화된 흐름이에요.")
    assert -1.84 in claims


def test_naeryeoanja_direction_contradicts_real_up():
    # ②/① 실측 +9.66% 상승인데 "내려앉아" 하락 서술 → 모순으로 판정
    sent = "다만 DRAM ETF가 <b>-1.84%</b> 내려앉아 메모리 반도체 섹터는 차별화된 흐름이에요."
    assert _direction_contradicts(sent, 9.66) is True


def test_dram_not_in_non_ticker_exclusion():
    # ③ DRAM ETF는 dram_etf 실측값이 있으므로 산문 검증 대상이어야 한다
    assert "DRAM" not in _NON_TICKER


def test_prose_nonpick_removes_hallucinated_dram(monkeypatch):
    # 통합: 실측 +9.66%를 주입하면 -1.84% 내려앉음 문장이 제거되어야 한다
    monkeypatch.setattr(
        va, "_fetch_us_realdata",
        lambda tk: {"change_pct": 9.66} if tk == "DRAM" else {"error": "x"})
    analysis = {
        "stock_picks": [],
        "reasons": [
            "📈 빅테크가 전반적으로 소폭 플러스예요.",
            "💡 다만 DRAM ETF가 <b>-1.84%</b> 내려앉아 메모리 반도체 섹터는 차별화된 흐름이에요.",
        ],
    }
    corrections, warnings = [], []
    validate_prose_nonpick_stocks(analysis, "us", corrections, warnings)
    assert len(analysis["reasons"]) == 1
    assert "DRAM" not in analysis["reasons"][0]


# ── 동일 클래스 확장: SOX·EWY·GLD 산문 방향 검증 ──────────────────────────────
from validate_analysis import _PROSE_FETCH_ALIAS


def test_sox_ewy_gld_not_in_non_ticker_exclusion():
    for sym in ("SOX", "EWY", "GLD"):
        assert sym not in _NON_TICKER


def test_sox_fetch_uses_caret_alias(monkeypatch):
    # 산문 "SOX"는 ^SOX 심볼로 실측 조회되어야 한다
    called = []
    monkeypatch.setattr(va, "_fetch_us_realdata",
                        lambda tk: called.append(tk) or {"change_pct": 6.42})
    analysis = {"stock_picks": [],
                "reasons": ["SOX가 강세를 보였어요."]}
    validate_prose_nonpick_stocks(analysis, "us", [], [])
    assert "^SOX" in called


def test_prose_nonpick_removes_hallucinated_sox(monkeypatch):
    # 실측 SOX +6.42% 인데 "빠졌다" 하락 서술 → 제거
    monkeypatch.setattr(
        va, "_fetch_us_realdata",
        lambda tk: {"change_pct": 6.42} if tk == "^SOX" else {"error": "x"})
    analysis = {"stock_picks": [],
                "reasons": ["📈 좋아요.", "💡 다만 SOX가 -2.1% 빠졌어요."]}
    validate_prose_nonpick_stocks(analysis, "us", [], [])
    assert len(analysis["reasons"]) == 1
    assert "SOX" not in analysis["reasons"][0]


# ── 후속 확장: 거래 가능한 지수/섹터 ETF도 산문 방향 검증 ──────────────────────
def test_index_etfs_not_in_non_ticker_exclusion():
    for sym in ("SPY", "QQQ", "IWM", "XLK", "XLF", "SOXX", "SOXL", "TQQQ"):
        assert sym not in _NON_TICKER


def test_prose_nonpick_removes_hallucinated_qqq(monkeypatch):
    # 실측 QQQ +1.5% 인데 "급락" 서술 → 제거
    monkeypatch.setattr(
        va, "_fetch_us_realdata",
        lambda tk: {"change_pct": 1.5} if tk == "QQQ" else {"error": "x"})
    analysis = {"stock_picks": [],
                "reasons": ["📈 좋아요.", "💡 QQQ가 -3.2% 급락했어요."]}
    validate_prose_nonpick_stocks(analysis, "us", [], [])
    assert len(analysis["reasons"]) == 1
    assert "QQQ" not in analysis["reasons"][0]


def test_prose_nonpick_keeps_correct_spy(monkeypatch):
    # 실측 SPY +0.8% 상승, 산문도 상승 → 유지 (오탐 방지)
    monkeypatch.setattr(
        va, "_fetch_us_realdata",
        lambda tk: {"change_pct": 0.8} if tk == "SPY" else {"error": "x"})
    analysis = {"stock_picks": [],
                "reasons": ["💡 SPY가 +0.8% 상승하며 견조했어요."]}
    validate_prose_nonpick_stocks(analysis, "us", [], [])
    assert len(analysis["reasons"]) == 1


# ── 후속 확장: VIX(^VIX 매핑)도 산문 방향 검증 ────────────────────────────────
def test_vix_not_in_non_ticker_exclusion():
    assert "VIX" not in _NON_TICKER


def test_vix_fetch_uses_caret_alias(monkeypatch):
    # 산문 "VIX"는 ^VIX 심볼로 실측 조회되어야 한다
    called = []
    monkeypatch.setattr(va, "_fetch_us_realdata",
                        lambda tk: called.append(tk) or {"change_pct": 12.0})
    analysis = {"stock_picks": [], "reasons": ["VIX가 급등했어요."]}
    validate_prose_nonpick_stocks(analysis, "us", [], [])
    assert "^VIX" in called


def test_prose_nonpick_removes_hallucinated_vix(monkeypatch):
    # 실측 VIX +12% 급등(공포 확대)인데 "급락" 서술 → 제거
    monkeypatch.setattr(
        va, "_fetch_us_realdata",
        lambda tk: {"change_pct": 12.0} if tk == "^VIX" else {"error": "x"})
    analysis = {"stock_picks": [],
                "reasons": ["📈 좋아요.", "💡 VIX가 -8% 급락하며 안정됐어요."]}
    validate_prose_nonpick_stocks(analysis, "us", [], [])
    assert len(analysis["reasons"]) == 1
    assert "VIX" not in analysis["reasons"][0]
