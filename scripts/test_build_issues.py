# build_issues: 이슈 정규화 + title·body 숫자 가드 검증
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh


def test_two_sided_issue_normalized():
    analysis = {"issues": [{
        "title": "IBM SW 경고",
        "body": "SaaS가 흔들려요.",
        "down": {"label": "소프트웨어", "tickers": ["CRM", "NOW"]},
        "up": {"label": "AI 인프라", "tickers": ["NVDA"]},
    }]}
    out = gh.build_issues(analysis)["issues"]
    assert len(out) == 1
    assert out[0]["down"]["tickers"] == ["CRM", "NOW"]
    assert out[0]["up"]["label"] == "AI 인프라"


def test_single_sided_issue_keeps_one_side():
    analysis = {"issues": [{"title": "CPI 발표", "body": "부담이에요.",
                            "down": {"label": "지수 전반", "tickers": []}}]}
    out = gh.build_issues(analysis)["issues"]
    assert "up" not in out[0]
    assert out[0]["down"]["label"] == "지수 전반"


def test_numbers_stripped_from_title_and_body():
    analysis = {"issues": [{
        "title": "CRM -4% 급락, 지수 5,431 이탈",
        "body": "엔비디아가 $168까지 올랐어요. 반도체가 +2.3% 강세예요.",
        "up": {"label": "반도체", "tickers": ["NVDA"]},
    }]}
    out = gh.build_issues(analysis)["issues"][0]
    for token in ["-4%", "5,431", "$168", "+2.3%"]:
        assert token not in out["title"] + out["body"], f"{token} 가 남아있음"
    # 티커 필드는 영향받지 않음
    assert out["up"]["tickers"] == ["NVDA"]


def test_empty_or_titleless_issues_dropped():
    analysis = {"issues": [{"title": "", "body": "x"}, {"body": "no title"}]}
    assert gh.build_issues(analysis)["issues"] == []


def test_no_issues_key():
    assert gh.build_issues({})["issues"] == []
