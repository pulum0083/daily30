# 미국 이슈 카드 — 'AI 판단' 표기·데이터형 이슈 하루 1개 제한 테스트(2026-10-26 사용자 결정)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh  # noqa: E402
from validate_analysis import limit_data_issues  # noqa: E402


def _render(issues):
    return gh.make_env().get_template("sections/_issues.html").render(**gh.build_issues({"issues": issues}))


def test_ai_label_once_per_card():
    html = _render([
        {"title": "한쪽", "down": {"label": "AI·반도체 전반", "tickers": ["NVDA"]}},
        {"title": "양쪽", "down": {"label": "소프트웨어", "tickers": ["CRM"]}, "up": {"label": "AI 인프라", "tickers": ["NVDA"]}},
        {"title": "영향 없음"},
    ])
    assert html.count('class="imp-ai">AI 판단') == 2                 # 영향 줄이 있는 카드마다 한 번


def test_limit_keeps_news_and_first_data_issue():
    a = {"issues": [{"kind": "news", "title": "실적"}, {"kind": "data", "title": "금리·VIX"},
                    {"kind": "data", "title": "S&P500 20일선"}, {"title": "kind 없음"}]}
    corr = []
    assert limit_data_issues(a, corr) == 1
    assert [i["title"] for i in a["issues"]] == ["실적", "금리·VIX", "kind 없음"] and corr


def test_limit_noop_without_kind():
    a = {"issues": [{"title": "a"}, {"title": "b"}]}
    assert limit_data_issues(a, []) == 0 and len(a["issues"]) == 2
