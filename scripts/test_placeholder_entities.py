# 익명 플레이스홀더 주어("B사", "C은행")로 날조된 뉴스가 발행되는 것을 막는 게이트 테스트.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_news import _drop_placeholder_entities  # noqa: E402


def test_real_incident_us_catalysts():
    """2026-07-27 실제 수집분: 익명 기업이 주어인 catalyst가 그대로 발행됐다."""
    items = [
        "B사 신규 서비스 출시 지연 발표 → 시간 외 거래에서 주가 7% 이상 급락, 관련 종목 약세",
        "중동 지역 긴장 완화 소식 → 국제유가 하락 (WTI 2%↓, 브렌트유 1.8%↓), 에너지 관련주 약세",
        "C은행, 예상보다 높은 대손충당금 발표 → 금융 섹터 전반에 대한 투자 심리 위축",
        "D사, AI 관련 신규 파트너십 발표 → 관련 기술주 및 반도체 주가 상승 기대감",
    ]
    assert _drop_placeholder_entities(items) == [items[1]]


def test_real_incident_us_headlines():
    """같은 사고의 headlines — 'A사 실적 호조'도 제거 대상이다."""
    items = [
        "미국 증시, 빅테크 실적 발표 앞두고 관망세…S&P 500·나스닥 혼조세",
        "개장 전 A사 실적 호조, 시간 외 급등…증시 상승 모멘텀 제공할까?",
        "B사 서비스 출시 지연 악재, 시간 외 급락…기술주 전반에 대한 우려 확산",
    ]
    assert _drop_placeholder_entities(items) == [items[0]]


def test_bracket_slots_from_prompt():
    """프롬프트 예시의 대괄호 슬롯이 그대로 남아 나오는 형태도 막는다."""
    items = [
        "[기업]의 신제품 발표 → [관련 섹터]에 상승 압력",
        "○○사 실적 서프라이즈 → 반도체 섹터 강세",
        "모 대형 은행의 충당금 확대 → 금융주 약세",
        "익명의 한 기술기업 감원 발표 → 기술주 약세",
    ]
    assert _drop_placeholder_entities(items) == []


def test_real_companies_survive():
    """실명이 들어간 정상 항목은 오제거되면 안 된다."""
    items = [
        "마이크론(MU) 급락 → AMAT·KLAC·LRCX 등 반도체 장비주 동반 약세",
        "애플, 신규 아이폰 출시 준비 소식 → 프리마켓 강세",
        "JP모건·골드만삭스 실적 호조 → 대형 은행주 동반 강세",
        "엔비디아 신규 AI 칩 루머 → AI 밸류체인 관심 확대",
    ]
    assert _drop_placeholder_entities(items) == items


def test_letter_in_real_name_not_false_positive():
    """'S&P500'·'K사'가 아닌 정상 영문 표기를 오탐하지 않는다."""
    items = [
        "S&P500 선물 0.16% 상승, 다우 선물 0.54% 상승",
        "SK하이닉스 HBM 공급 확대 → 메모리 섹터 강세",
        "ETF 자금 유입 확대 → 반도체 섹터 수급 개선",
    ]
    assert _drop_placeholder_entities(items) == items


def test_dict_form_catalysts():
    """구조화 catalyst({text:...})도 같은 기준으로 판정한다."""
    items = [
        {"date": "2026-07-27", "text": "B사 출시 지연 → 기술주 약세", "ticker": ""},
        {"date": "2026-07-27", "text": "마이크론 실적 미스 → 메모리 급락", "ticker": "MU"},
    ]
    assert _drop_placeholder_entities(items) == [items[1]]


def test_empty_and_none():
    """빈 입력에서 터지지 않는다."""
    assert _drop_placeholder_entities([]) == []
    assert _drop_placeholder_entities(None) == []


if __name__ == "__main__":
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            fn_()
            print(f"✅ {name}")
    print("모든 테스트 통과")
