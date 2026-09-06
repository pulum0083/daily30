# score_us_issues 채점 로직 테스트 — 판정·결과줄·중복 제거·카드 생략·조사 처리(네트워크 없음).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_us_issues as S


def _measure(table):
    """티커→등락률 표를 measure 함수로. 표에 없으면 None(그 세션 봉 없음)."""
    return lambda t: table.get(t)


def _issue(title, side, label, tickers):
    return {"title": title, side: {"label": label, "tickers": tickers}}


# ── 판정 배지 ──────────────────────────────────────────────
def test_verdict_all_single():
    assert S.verdict(1, 1) == ("all", "적중")


def test_verdict_all_multi():
    assert S.verdict(4, 4) == ("all", "4건 전부")


def test_verdict_none():
    assert S.verdict(2, 0) == ("none", "빗나감")


def test_verdict_partial():
    assert S.verdict(4, 2) == ("part", "4중 2 적중")


# ── 조사 처리 (받침 유무) ──────────────────────────────────
def test_josa_with_final_consonant():
    line = S.result_line("지수 전반", False, [{"ticker": "^GSPC", "name": "S&P500", "pct": -0.38, "hit": True}])
    assert line.startswith("지수 전반이 "), line


def test_josa_without_final_consonant():
    """'전기차' 처럼 받침이 없으면 '가'다 — '전기차이'로 나가면 안 된다."""
    line = S.result_line("전기차", False, [{"ticker": "TSLA", "name": "TSLA", "pct": -5.92, "hit": True}])
    assert line.startswith("전기차가 "), line


# ── 결과 한 줄 ────────────────────────────────────────────
def test_result_line_single_miss_says_opposite():
    line = S.result_line("지수 전반", False, [{"ticker": "^GSPC", "name": "S&P500", "pct": 1.06, "hit": False}])
    assert "올랐어요" in line and "예상과 반대예요" in line, line


def test_result_line_single_hit_has_no_opposite_note():
    line = S.result_line("전기차", False, [{"ticker": "TSLA", "name": "TSLA", "pct": -5.92, "hit": True}])
    assert "예상과 반대" not in line, line


def test_result_line_multi_counts_and_average():
    marks = [
        {"ticker": "MU", "name": "MU", "pct": 6.10, "hit": True},
        {"ticker": "AMAT", "name": "AMAT", "pct": 4.31, "hit": True},
        {"ticker": "KLAC", "name": "KLAC", "pct": 7.32, "hit": True},
        {"ticker": "LRCX", "name": "LRCX", "pct": 5.12, "hit": True},
    ]
    line = S.result_line("메모리·반도체 장비", True, marks)
    assert "4종목 중 <b>4종목이 올랐어요</b>" in line, line
    assert "평균 +5.71%" in line, line


# ── 프록시 ────────────────────────────────────────────────
def test_proxy_matches_index_label():
    assert S.proxy_for("지수 전반") == ("^GSPC", "S&P500")


def test_proxy_strips_parenthetical_condition():
    assert S.proxy_for("지수 전반(변동성 하락)") == ("^GSPC", "S&P500")
    assert S.proxy_for("지수 전반 (서프라이즈 시)") == ("^GSPC", "S&P500")


def test_proxy_rejects_mixed_label():
    """섹터가 섞인 라벨은 S&P500 하나로 대표할 수 없으므로 채점하지 않는다."""
    assert S.proxy_for("지수 전반, 특히 성장주") is None
    assert S.proxy_for("원가 민감 소비재·운송") is None


# ── 카드 생략 ─────────────────────────────────────────────
def test_card_dropped_when_no_tickers_and_no_proxy():
    issues = [_issue("금값 급등", "up", "금·귀금속 관련주", [])]
    assert S.build_cards(issues, _measure({})) == []


def test_card_dropped_when_session_bar_missing():
    """그 세션 봉이 없으면 티커를 버리고, 전부 없으면 카드도 없다 — 최신 봉으로 때우지 않는다."""
    issues = [_issue("반도체 약세", "down", "반도체", ["AMAT", "KLAC"])]
    assert S.build_cards(issues, _measure({})) == []


def test_ticker_without_bar_is_excluded_but_card_survives():
    issues = [_issue("반도체 약세", "down", "반도체", ["AMAT", "KLAC"])]
    cards = S.build_cards(issues, _measure({"AMAT": -0.58}))
    assert len(cards) == 1
    assert [m["ticker"] for m in cards[0]["sides"][0]["marks"]] == ["AMAT"]


def test_empty_issues_give_empty_cards():
    assert S.build_cards([], _measure({"AAPL": 1.0})) == []
    assert S.build_cards([None, "문자열", {}], _measure({})) == []


# ── 중복 제거 ─────────────────────────────────────────────
def test_duplicate_proxy_same_direction_keeps_title_only():
    """같은 프록시·같은 방향이 두 번 나오면 뒤엣것은 결과를 반복하지 않는다."""
    issues = [
        _issue("고용지표 대기", "down", "지수 전반", []),
        _issue("중동 리스크", "down", "지수 전반", []),
    ]
    cards = S.build_cards(issues, _measure({"^GSPC": 1.06}))
    assert len(cards) == 2
    assert "result_line" in cards[0] and cards[0]["sides"]
    assert cards[1]["duplicate_of"] == 1
    assert cards[1]["sides"] == [] and "result_line" not in cards[1]


def test_same_proxy_opposite_direction_is_not_duplicate():
    issues = [
        _issue("지수 하락 우려", "down", "지수 전반", []),
        _issue("지수 반등 기대", "up", "지수 전반", []),
    ]
    cards = S.build_cards(issues, _measure({"^GSPC": 1.06}))
    assert "duplicate_of" not in cards[1], cards[1]


def test_explicit_tickers_are_never_deduped():
    """같은 종목이 두 이슈에 나오는 건 정상이다 — 프록시 대입 카드만 합친다."""
    issues = [
        _issue("이슈A", "up", "빅테크", ["NVDA"]),
        _issue("이슈B", "up", "AI 인프라", ["NVDA"]),
    ]
    cards = S.build_cards(issues, _measure({"NVDA": 0.84}))
    assert all("duplicate_of" not in c for c in cards), cards


# ── 실사고 리플레이 ────────────────────────────────────────
def test_replay_2026_09_03_session():
    """9/3 미국 브리핑 5건 — 티커 없는 1건 생략, 3건 빗나감, 지수 중복 1건."""
    issues = [
        _issue("금값 급등", "up", "금·귀금속 관련주", []),
        _issue("국제유가 동반 상승", "up", "에너지", ["XOM", "CVX"]),
        _issue("반도체 장비주 약세", "down", "반도체 장비", ["AMAT", "KLAC", "LRCX", "AVGO"]),
        _issue("고용지표 대기", "down", "지수 전반", []),
        _issue("중동 지정학 리스크", "down", "지수 전반", []),
    ]
    real = {"XOM": -1.18, "CVX": -0.22, "AMAT": -0.58, "KLAC": 0.39,
            "LRCX": 1.51, "AVGO": -2.74, "^GSPC": 1.06}
    cards = S.build_cards(issues, _measure(real))

    assert len(cards) == 4, [c["title"] for c in cards]        # 금값 카드는 생략
    assert cards[0]["verdict_text"] == "빗나감"                  # 에너지 0/2
    assert cards[1]["verdict_text"] == "4중 2 적중"              # 장비주 2/4
    assert "평균 −0.36%" in cards[1]["result_line"], cards[1]["result_line"]
    assert cards[2]["verdict_text"] == "빗나감"                  # 지수 전반
    assert cards[3]["duplicate_of"] == 3                        # 같은 지표 반복 안 함


def test_replay_2026_09_04_session():
    """9/4 미국 브리핑 — 장비주 4/4 전부 적중, 빅테크는 3중 1."""
    issues = [
        _issue("국채금리 급락", "up", "성장주·빅테크", ["NVDA", "MSFT", "AMZN"]),
        _issue("메모리·장비주 강세", "up", "메모리·반도체 장비", ["MU", "AMAT", "KLAC", "LRCX"]),
        _issue("테슬라 홀로 약세", "down", "전기차", ["TSLA"]),
    ]
    real = {"NVDA": 0.84, "MSFT": -2.04, "AMZN": -0.15,
            "MU": 6.10, "AMAT": 4.31, "KLAC": 7.32, "LRCX": 5.12, "TSLA": -5.92}
    cards = S.build_cards(issues, _measure(real))

    assert [c["verdict_text"] for c in cards] == ["3중 1 적중", "4건 전부", "적중"]
    assert cards[2]["result_line"].startswith("전기차가 "), cards[2]["result_line"]
