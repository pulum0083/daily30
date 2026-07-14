# 텔레그램 핵심 시그널 이슈 우선 정렬 단위 테스트
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc


def test_number_signal_moved_to_end():
    # 💡(반도체 ETF·SOX)는 뒤로, 📰(뉴스 이슈)는 앞으로
    out = cc._issue_first_sort(["💡 DRAM ETF +7%", "📰 삼성 실적 발표"])
    assert out == ["📰 삼성 실적 발표", "💡 DRAM ETF +7%"]


def test_already_issue_first_unchanged():
    out = cc._issue_first_sort(["📰 삼성 실적 발표", "💡 DRAM ETF +7%"])
    assert out == ["📰 삼성 실적 발표", "💡 DRAM ETF +7%"]


def test_foreign_flow_also_treated_as_number():
    # 🇺🇸(EWY 외국인수급)도 수치 계열이라 뒤로
    out = cc._issue_first_sort(["🇺🇸 EWY -2%", "📅 오늘 밤 CPI"])
    assert out == ["📅 오늘 밤 CPI", "🇺🇸 EWY -2%"]


def test_both_number_categories_preserve_relative_order():
    # 둘 다 수치 계열이면 원래 순서 유지 (안정 정렬)
    out = cc._issue_first_sort(["💡 SOX +3%", "🇺🇸 EWY -2%"])
    assert out == ["💡 SOX +3%", "🇺🇸 EWY -2%"]


def test_both_issue_categories_preserve_relative_order():
    out = cc._issue_first_sort(["📅 CPI 발표", "📰 반도체 규제 뉴스"])
    assert out == ["📅 CPI 발표", "📰 반도체 규제 뉴스"]


def test_three_items_issue_bubbles_up():
    out = cc._issue_first_sort(["🇺🇸 EWY -2%", "📅 CPI", "💡 SOX +3%"])
    assert out == ["📅 CPI", "🇺🇸 EWY -2%", "💡 SOX +3%"]


def test_empty_list():
    assert cc._issue_first_sort([]) == []


def test_leading_whitespace_and_bold_tag_after_emoji():
    # 이모지 앞 공백이 있어도 판별, 이모지 뒤 <b> 태그는 판별에 영향 없음
    out = cc._issue_first_sort(["  💡 <b>DRAM</b> 강세", "📰 뉴스"])
    assert out == ["📰 뉴스", "  💡 <b>DRAM</b> 강세"]
