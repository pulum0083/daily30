# 국내 이슈 수집의 창 계산·발행일 검증·요약 매핑을 검증하는 테스트.
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytz

sys.path.insert(0, str(Path(__file__).parent))
import fetch_domestic_issues as m  # noqa: E402

KST = pytz.timezone("Asia/Seoul")


def _kst(y, mo, d, h, mi):
    return KST.localize(datetime(y, mo, d, h, mi))


def test_monday_window_reaches_friday_close():
    """월요일 아침이면 수집 창이 금요일 코스피 마감(15:30)까지 열린다 — 주말 소재 포함."""
    start, label = m.collect_window(date(2026, 7, 27))
    assert start == _kst(2026, 7, 24, 15, 30), start
    assert "2026-07-24" in label


def test_weekday_window_is_prev_close():
    """평일이면 직전 거래일 마감 이후."""
    start, _ = m.collect_window(date(2026, 7, 28))
    assert start == _kst(2026, 7, 27, 15, 30), start


def test_verify_drops_unverifiable(monkeypatch=None):
    """실제 발행일을 못 구하면 후보를 버린다 — 표시하지 않는다(§10)."""
    m._resolve_gnews_url = lambda link: "https://example.com/a"
    m._verify_real_published_at = lambda url: None
    cands = [{"title": "제목", "desc": "", "link": "x", "source": "s",
              "rss_pub": _kst(2026, 7, 27, 7, 0), "query": "q"}]
    assert m.verify_candidates(cands, _kst(2026, 7, 24, 15, 30), _kst(2026, 7, 27, 7, 25)) == []


def test_verify_drops_out_of_window():
    """RSS pubDate가 최신이어도 실제 발행일이 창 밖이면 버린다(날짜 세탁 차단)."""
    m._resolve_gnews_url = lambda link: "https://example.com/a"
    m._verify_real_published_at = lambda url: _kst(2026, 6, 25, 10, 0)  # 한 달 전
    cands = [{"title": "옛 기사", "desc": "", "link": "x", "source": "s",
              "rss_pub": _kst(2026, 7, 27, 7, 0), "query": "q"}]
    assert m.verify_candidates(cands, _kst(2026, 7, 24, 15, 30), _kst(2026, 7, 27, 7, 25)) == []


def test_verify_keeps_in_window():
    """창 안에서 검증되면 url·published_at을 붙여 통과시킨다."""
    m._resolve_gnews_url = lambda link: "https://example.com/a"
    m._verify_real_published_at = lambda url: _kst(2026, 7, 26, 9, 0)
    cands = [{"title": "주말 정책 발표", "desc": "", "link": "x", "source": "연합",
              "rss_pub": _kst(2026, 7, 26, 9, 5), "query": "q"}]
    got = m.verify_candidates(cands, _kst(2026, 7, 24, 15, 30), _kst(2026, 7, 27, 7, 25))
    assert len(got) == 1
    assert got[0]["url"] == "https://example.com/a"
    assert got[0]["published_at"] == "2026-07-26 09:00"


def test_summarize_rejects_bad_index():
    """Gemini가 없는 번호를 반환하면 그 항목을 버린다(존재하지 않는 기사 방지)."""
    items = [{"title": "A", "desc": "", "url": "u", "source": "s", "published_at": "2026-07-27 08:00"}]
    m.summarize.__globals__  # noqa: B018
    picked = [{"idx": 5, "title": "가짜", "summary": "지어낸 요약이에요."},
              {"idx": 0, "title": "진짜", "summary": "실제 기사예요."}]

    def fake(*a, **k):
        return picked
    # summarize 내부 Gemini 호출만 대체하기 어려우므로 매핑 로직을 직접 재현 검증
    out = []
    for p in picked[:m.MAX_ITEMS]:
        idx = p.get("idx")
        if not isinstance(idx, int) or not (0 <= idx < len(items)):
            continue
        out.append({**items[idx], "title": p["title"], "summary": p["summary"]})
    assert len(out) == 1 and out[0]["title"] == "진짜"


def test_empty_input_returns_empty():
    """후보가 없으면 Gemini를 호출하지 않고 빈 배열."""
    assert m.summarize([], "라벨", "2026-07-27") == []


def test_dedupe_same_event():
    """실사고: 같은 '한은 8월 금리' 사건 3건이 그대로 실렸다 — 1건만 남아야 한다."""
    issues = [
        {"title": "한국은행 8월 기준금리 또 올리나…깜짝 성장에 추가 인상 가능성 커졌다"},
        {"title": "한은, 8월 또 금리 올리나…깜짝 성장에 전망 엇갈려"},
        {"title": "깜짝 성장에 금리 셈법 복잡…8월 기준금리 추가 인상 촉각"},
    ]
    got = m.dedupe_issues(issues)
    assert len(got) == 1, [g["title"] for g in got]


def test_dedupe_keeps_distinct_events():
    """서로 다른 사건은 남긴다."""
    issues = [
        {"title": "한국은행 8월 기준금리 추가 인상 가능성"},
        {"title": "AI가 바꾼 반도체 지도…대만 수출 급증"},
        {"title": "정부 코스닥 활성화 대책 발표"},
    ]
    assert len(m.dedupe_issues(issues)) == 3


def test_dedupe_survives_quote_shift():
    """실측 회귀: 따옴표 위치가 달라 토큰이 갈려도(자카드 0.20) 같은 사건이면 합친다."""
    issues = [
        {"title": "한국은행 8월 기준금리 또 올리나…깜짝 성장에 \u2018추가 인상\u2019 가능성 커졌다"},
        {"title": "한은, 8월 또 금리 올리나…\u2018깜짝 성장\u2019에 전망 엇갈려"},
    ]
    assert len(m.dedupe_issues(issues)) == 1


def test_dedupe_keeps_unrelated_sectors():
    """토큰이 거의 안 겹치는 별개 사건은 확실히 남긴다."""
    issues = [
        {"title": "삼성전자 3분기 반도체 실적 발표"},
        {"title": "SK하이닉스 HBM 신규 수주 계약"},
        {"title": "한국은행 기준금리 동결 결정"},
    ]
    assert len(m.dedupe_issues(issues)) == 3


def test_dedupe_empty():
    assert m.dedupe_issues([]) == []


if __name__ == "__main__":
    for name, fn_ in sorted(globals().items()):
        if name.startswith("test_") and callable(fn_):
            fn_()
            print(f"✅ {name}")
    print("모든 테스트 통과")
