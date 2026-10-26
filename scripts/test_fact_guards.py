# 현직 인물 교정·최근 미국 세션 일지 테스트 — 2026-10-26 코스피 브리핑의 '파월 발언'·'금요일 메타 충격' 재발 방지(§64)
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc  # noqa: E402
import fetch_data as fd  # noqa: E402
import validate_analysis as va  # noqa: E402

TABLE = {"fed_chair": {"role": "연준 의장", "name": "워시", "full_name": "케빈 워시",
                       "since": "2026-05-22", "former": ["파월"]}}


def _fix(text):
    a = {"todays_view": {"outlook": [{"text": text}]}}
    corr, warn = [], []
    va.fix_officeholder_names(a, corr, warn, table=TABLE)
    return a["todays_view"]["outlook"][0]["text"], corr, warn


def test_role_mentions_are_replaced_real_case():
    t, corr, warn = _fix("이번 주 목요일 새벽 FOMC가 예정돼 있어요 — 금리는 동결 전망이지만 파월 발언 톤이 다음 방향을 좌우해요.")
    assert "워시 발언 톤" in t and "파월" not in t
    assert corr and "파월' → '워시'" in corr[0] and warn == []


def test_other_role_forms():
    for src, want in (("파월 기자회견", "워시 기자회견"), ("파월 연준 의장의 입", "워시 연준 의장의 입"),
                      ("파월의 발언", "워시의 발언"), ("파월 의장이", "워시 의장이")):
        assert _fix(src)[0] == want, src


def test_former_without_role_kept_but_warned():
    t, corr, warn = _fix("파월 전 의장은 이사로 남아 있어요.")
    assert t == "파월 전 의장은 이사로 남아 있어요." and corr == [] and warn


def test_officeholder_directive_names_current_chair():
    d = cc._officeholder_directive()
    assert "케빈 워시" in d and "2026-05-22" in d and "파월" in d


def test_recent_sessions_from_daily_closes():
    s = pd.Series([913.67, 856.49, 877.55],
                  index=pd.to_datetime(["2026-10-21", "2026-10-22", "2026-10-23"]))
    assert fd._recent_sessions(s, n=3) == [{"date": "2026-10-22", "pct": -6.26}, {"date": "2026-10-23", "pct": 2.46}]


def test_session_log_marks_previous_session_on_monday():
    data = {"us_recent_sessions": {
        "나스닥": [{"date": "2026-10-21", "pct": 1.05}, {"date": "2026-10-22", "pct": -2.60}, {"date": "2026-10-23", "pct": -0.21}],
        "필라델피아 반도체": [{"date": "2026-10-22", "pct": -6.72}, {"date": "2026-10-23", "pct": 0.44}]}}
    d = cc._us_session_log_directive("2026-10-26", data)
    assert "10/23(금) ← 직전 미국장(지난 금요일): 나스닥 -0.21%, 필라델피아 반도체 +0.44%" in d
    assert "10/22(목): 나스닥 -2.60%, 필라델피아 반도체 -6.72%" in d
    assert d.index("10/23") < d.index("10/22")                    # 최신 날짜가 위
    assert cc._us_session_log_directive("2026-10-26", {}) == ""
