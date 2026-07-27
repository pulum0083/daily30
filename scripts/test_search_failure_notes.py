# 검색 실패 보고("…확인되지 않았습니다")가 이슈로 발행되는 것을 막는 게이트 테스트.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_news import _drop_search_failure_notes  # noqa: E402


def test_real_incident_key_indicator():
    """2026-07-27 실제 수집분: 검색 실패 문장이 key_indicators에 그대로 실렸다."""
    items = [
        "2026년 7월 26일 미국 나스닥 지수는 0.5% 하락 마감했습니다.",
        "오늘 코스피 시장 개장에 영향을 줄 외국인 수급 및 ETF 자금 흐름에 대한 "
        "구체적인 최신 뉴스는 현재까지 확인되지 않았습니다.",
    ]
    assert _drop_search_failure_notes(items) == [items[0]]


def test_parenthetical_placeholders():
    """'→ (아직 발표되지 않음)' 류 빈 껍데기 catalyst도 제거한다."""
    items = [
        "간밤 미국 빅테크 실적 발표 결과 → (아직 발표되지 않음)",
        "AI 모델 개발사 이슈(OpenAI, Anthropic 등) → (현재까지 구체적인 신규 이슈 없음)",
    ]
    assert _drop_search_failure_notes(items) == []


def test_real_catalysts_survive():
    """정상 catalyst는 오제거되면 안 된다."""
    items = [
        "엔비디아 주가 하락 → 국내 반도체 관련주에 하방 압력 작용",
        "TSMC 매출 전망 하향 → 국내 반도체 업종 전반의 투자 심리 위축 가능성",
        "미국 증시 전반의 약세 → 코스피 외국인 투자 심리 위축 및 매도세 강화 가능성",
    ]
    assert _drop_search_failure_notes(items) == items


def test_dict_form_catalysts():
    """구조화 catalyst({text:...})도 같은 기준으로 판정한다."""
    items = [
        {"date": "2026-07-27", "text": "관련 최신 뉴스는 확인되지 않았습니다."},
        {"date": "2026-07-27", "text": "삼성전자 신규 수주 → 반도체 섹터 강세"},
    ]
    assert _drop_search_failure_notes(items) == [items[1]]


def test_empty_and_none():
    """빈 입력에서 터지지 않는다."""
    assert _drop_search_failure_notes([]) == []
    assert _drop_search_failure_notes(None) == []


if __name__ == "__main__":
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            fn_()
            print(f"✅ {name}")
    print("모든 테스트 통과")
