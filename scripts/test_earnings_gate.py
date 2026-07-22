# 독립 어닝 캘린더 검증(_drop_stale_earnings 등) 테스트.
# yfinance 조회는 age_fn 주입으로 대체해 네트워크 없이 결정적으로 검증한다.
# 2026-07-20 실사고: 마이크론(6/24)·JP모건(7/14) 등 몇 주 된 실적이 '오늘 촉매'로 재소환됨.
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn

TODAY = date(2026, 7, 20)


def test_is_earnings_catalyst():
    assert fn._is_earnings_catalyst("마이크론 2분기 실적 발표 → 반도체 강세")
    assert fn._is_earnings_catalyst("JP모건 순이익 서프라이즈")
    assert not fn._is_earnings_catalyst("중동 지정학 긴장 → 국제 유가 급등, 에너지주 강세")


def test_parse_tickers():
    assert fn._parse_tickers("MU") == ["MU"]
    assert fn._parse_tickers("JPM,GS") == ["JPM", "GS"]
    assert fn._parse_tickers(["NVDA", "AMD"]) == ["NVDA", "AMD"]
    assert fn._parse_tickers("") == []


def _fake_age(mapping):
    return lambda t, today: mapping.get(t)


def test_drops_stale_earnings():
    cats = [{"text": "마이크론(MU) 2분기 실적 발표 → 반도체 강세", "ticker": "MU"}]
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({"MU": 25}))
    assert out == []


def test_keeps_fresh_earnings():
    cats = [{"text": "○○ 실적 서프라이즈 → 강세", "ticker": "XYZ"}]
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({"XYZ": 0}))
    assert out == cats


def test_boundary_keeps_at_max_age():
    cats = [{"text": "○○ 실적 발표", "ticker": "XYZ"}]
    assert fn._drop_stale_earnings(cats, TODAY, max_age_days=2, age_fn=_fake_age({"XYZ": 2})) == cats
    assert fn._drop_stale_earnings(cats, TODAY, max_age_days=2, age_fn=_fake_age({"XYZ": 3})) == []


def test_non_earnings_catalyst_never_verified():
    cats = [{"text": "중동 지정학 긴장 → 유가 급등, 에너지주 강세", "ticker": "XOM"}]
    # XOM 실적은 80일 전이라도, 실적 catalyst가 아니므로 검증하지 않고 유지
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({"XOM": 80}))
    assert out == cats


def test_no_ticker_kept():
    cats = [{"text": "대형 은행 실적 서프라이즈 → 금융주 강세", "ticker": ""}]
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({}))
    assert out == cats


def test_lookup_failure_kept():
    # age_fn이 None(조회 실패) → 과잉 제외 방지 위해 유지
    cats = [{"text": "○○ 실적 발표", "ticker": "XYZ"}]
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({"XYZ": None}))
    assert out == cats


def test_multi_ticker_one_fresh_keeps():
    # JPM(오래됨)·NEW(오늘) 중 하나라도 신선하면 유지
    cats = [{"text": "두 은행 실적 발표 → 금융 섹터", "ticker": "JPM,NEW"}]
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({"JPM": 6, "NEW": 0}))
    assert out == cats


def test_multi_ticker_all_stale_drops():
    cats = [{"text": "두 은행 실적 발표 → 금융 섹터", "ticker": "JPM,GS"}]
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({"JPM": 6, "GS": 6}))
    assert out == []


def test_string_catalyst_without_ticker_kept():
    # dict가 아닌 문자열 형태(하위호환)는 티커가 없어 검증 불가 → 유지
    out = fn._drop_stale_earnings(["○○ 실적 발표 → 강세"], TODAY, age_fn=_fake_age({}))
    assert out == ["○○ 실적 발표 → 강세"]


# ── 텍스트 사명 → 티커 resolve (2026-07-22 '엔비디아 실적 발표' 실사고) ──────────
def test_resolve_company_tickers():
    assert fn._resolve_company_tickers("엔비디아 실적 발표 이후 차익 실현") == ["NVDA"]
    assert fn._resolve_company_tickers("마이크론 2분기 실적") == ["MU"]
    assert "MU" in fn._resolve_company_tickers("micron 실적")
    assert fn._resolve_company_tickers("삼성전자 잠정실적 발표") == []   # 국내주 미등록 → fail-open
    assert fn._resolve_company_tickers("중동 지정학 긴장 → 유가 급등") == []


def test_drops_stale_earnings_from_named_text_no_ticker():
    # 실사고 재현: Gemini 문자열 catalyst(ticker 필드 없음)에 '엔비디아 실적 발표'.
    # NVDA 실제 최근 발표가 55일 전이면 오늘 촉매로 부적합 → 제외.
    cats = ["엔비디아 실적 발표 이후 차익 실현 매물 출회 → 미국 기술주 전반 하락"]
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({"NVDA": 55}))
    assert out == []


def test_keeps_fresh_named_earnings_from_text():
    cats = ["엔비디아 실적 발표 서프라이즈 → 반도체 강세"]
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({"NVDA": 1}))
    assert out == cats


def test_unmapped_korean_name_fail_open():
    # 국내주(맵 미등록)는 resolve 안 됨 → 티커 없음 → 유지(과잉 제외 방지).
    cats = ["삼성전자 잠정실적 발표 → 강세"]
    out = fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age({"005930": 55}))
    assert out == cats
