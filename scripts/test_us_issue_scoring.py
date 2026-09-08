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


# ── 실제 움직임 요약 (판정 아님) ─────────────────────────
def _m(name, pct):
    return {"ticker": name, "name": name, "pct": pct}


def test_mood_all_up():
    assert S.mood([_m("MU", 6.1), _m("AMAT", 4.31)]) == "나란히 올랐어요"


def test_mood_all_down():
    assert S.mood([_m("XOM", -1.18), _m("CVX", -0.22)]) == "나란히 내렸어요"


def test_mood_mixed():
    assert S.mood([_m("NVDA", 0.84), _m("MSFT", -2.04)]) == "엇갈렸어요"


def test_mood_single():
    assert S.mood([_m("TSLA", -5.92)]) == "내렸어요"
    assert S.mood([_m("NVDA", 0.84)]) == "올랐어요"


def test_no_verdict_or_hit_fields_anywhere():
    """적중·빗나감을 판정하지 않는다 — 판정 잔재가 데이터에 남으면 안 된다."""
    issues = [_issue("이슈", "up", "빅테크", ["NVDA", "MSFT"])]
    cards = S.build_cards(issues, _measure({"NVDA": 0.84, "MSFT": -2.04}))
    assert "verdict_text" not in cards[0] and "verdict_class" not in cards[0]
    assert all("hit" not in m for s_ in cards[0]["sides"] for m in s_["marks"])


# ── 조사 처리 (받침 유무) ──────────────────────────────────
def test_josa_with_final_consonant():
    assert S.check_line("지수 전반", [_m("S&P500", -0.38)]).startswith("지수 전반은 ")


def test_josa_without_final_consonant():
    """'전기차' 처럼 받침이 없으면 '는'이다 — '전기차은'으로 나가면 안 된다."""
    assert S.check_line("전기차", [_m("TSLA", -5.92)]).startswith("전기차는 ")


def test_check_line_says_only_what_happened():
    """어제 예상과 맞았는지는 말하지 않는다."""
    line = S.check_line("성장주·빅테크", [_m("NVDA", 0.84), _m("MSFT", -2.04), _m("AMZN", -0.15)])
    assert line == "성장주·빅테크는 <b>엇갈렸어요</b>", line
    for banned in ("적중", "빗나", "예상", "반대"):
        assert banned not in line


# ── 제목 시점 교정 ────────────────────────────────────────
def test_retitle_maps_tonight_to_session_label():
    """'오늘 밤'은 그 브리핑이 가리킨 세션 자체라 라벨로 정확히 치환된다."""
    assert S.retitle("오늘 밤 ISM 제조업 PMI 발표", "지난 금요일") == "지난 금요일 ISM 제조업 PMI 발표"
    assert S.retitle("오늘 밤 ISM 제조업 PMI 발표", "간밤") == "간밤 ISM 제조업 PMI 발표"


def test_retitle_drops_unresolvable_time_words():
    """지금 프레임에서 뭘 가리키는지 단정할 수 없는 표현은 지어내지 않고 지운다."""
    assert S.retitle("이번 주 FOMC·PCE 대기 모드 진입", "간밤") == "FOMC·PCE 대기 모드 진입"
    assert S.retitle("오늘 새벽 FOMC 결과 발표 — 매파 신호", "간밤") == "FOMC 결과 발표 — 매파 신호"
    assert S.retitle("국채금리 급락에 나스닥 급등 — 어제 랠리의 배경", "간밤") \
        == "국채금리 급락에 나스닥 급등 — 랠리의 배경"


def test_retitle_handles_multiple_words_and_particles():
    assert S.retitle("내일 밤 고용지표(비농업고용) 대기 — 오늘은 관망 심리도", "간밤") \
        == "고용지표(비농업고용) 대기 — 관망 심리도"


def test_retitle_leaves_clean_titles_alone():
    for t in ("테슬라, 홀로 약세 — 개별 종목 리스크",
              "메모리·반도체 장비주, 프리마켓에서도 강세 지속"):
        assert S.retitle(t, "간밤") == t


def test_retitle_keeps_original_when_stripping_guts_it():
    """시점을 고치려다 제목을 망가뜨리지 않는다."""
    assert S.retitle("오늘의 관망", "간밤") == "오늘의 관망"


def test_retitle_applied_in_build_cards():
    issues = [_issue("오늘 밤 고용지표 3종 세트 — 다음 테스트", "down", "지수 전반", [])]
    cards = S.build_cards(issues, _measure({"^GSPC": -0.38}), "지난 금요일")
    assert cards[0]["title"] == "지난 금요일 고용지표 3종 세트 — 다음 테스트"


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
    """같은 프록시·같은 방향이 두 번 나오면 뒤엣것은 수치를 반복하지 않는다."""
    issues = [
        _issue("고용지표 대기", "down", "지수 전반", []),
        _issue("중동 리스크", "down", "지수 전반", []),
    ]
    cards = S.build_cards(issues, _measure({"^GSPC": 1.06}))
    assert len(cards) == 2
    assert "check_line" in cards[0] and cards[0]["sides"]
    assert cards[1]["duplicate_of"] == 1
    assert cards[1]["sides"] == [] and "check_line" not in cards[1]


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
    assert cards[0]["check_line"] == "에너지는 <b>나란히 내렸어요</b>"
    assert cards[1]["check_line"] == "반도체 장비는 <b>엇갈렸어요</b>"
    assert cards[2]["check_line"] == "지수 전반은 <b>올랐어요</b>"
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

    assert [c["check_line"] for c in cards] == [
        "성장주·빅테크는 <b>엇갈렸어요</b>",
        "메모리·반도체 장비는 <b>나란히 올랐어요</b>",
        "전기차는 <b>내렸어요</b>",
    ]


# ── 미국 휴장일 다음날 섹션 생략 (2026-09-07 노동절 케이스) ──────────
import datetime  # noqa: E402
from session_label import us_session_to_score  # noqa: E402


def test_labor_day_monday_still_scores_friday():
    """월요일이 미국 휴장이어도 그날 코스피 브리핑은 금요일 세션을 처음 채점한다."""
    assert us_session_to_score(datetime.date(2026, 9, 7)) == datetime.date(2026, 9, 4)


def test_day_after_us_holiday_has_nothing_new_to_score():
    """화요일엔 직전 미국장이 여전히 금요일 — 어제 이미 보여준 결과라 섹션을 생략한다."""
    assert us_session_to_score(datetime.date(2026, 9, 8)) is None


def test_normal_weekday_scores_previous_night():
    assert us_session_to_score(datetime.date(2026, 9, 9)) == datetime.date(2026, 9, 8)
    assert us_session_to_score(datetime.date(2026, 9, 4)) == datetime.date(2026, 9, 3)


def test_monday_after_normal_friday_scores_friday():
    """평범한 월요일은 금요일 밤 미국장을 채점한다 — 휴장 규칙이 이걸 막으면 안 된다."""
    assert us_session_to_score(datetime.date(2026, 8, 31)) == datetime.date(2026, 8, 28)
