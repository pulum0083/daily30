# 산문 % 수치 불일치 판정 함수(is_contradicted) 단위 테스트
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from validate_analysis import is_contradicted, _extract_change_claims

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
