# 장중 이슈가 '어제 장 요약' 기사를 발행하는 것을 막는 두 게이트 테스트 (2026-07-30 실사고).
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news_live as fnl  # noqa: E402


def _a(title, pub_time):
    return {"title": title, "pub_time": pub_time, "date": "2026-07-30", "source": "", "desc": ""}


# ── A. 장 개시 시각 게이트 ────────────────────────────────────────────────────

def test_drops_pre_open_articles():
    """개장 전(새벽) 발행 기사는 오늘 날짜여도 어제 장 요약이므로 제외한다."""
    out = fnl.filter_after_market_open([
        _a("코스피·코스닥 또 동반 급락…사상 첫 이틀 연속 서킷브레이커 발동", "07:48"),
        _a("장중 외국인 순매수 전환", "09:21"),
    ])
    assert [a["title"] for a in out] == ["장중 외국인 순매수 전환"]


def test_keeps_exactly_at_open():
    """09:00 정각 발행분은 장 개시 시점이므로 남긴다."""
    assert len(fnl.filter_after_market_open([_a("개장 코멘트", "09:00")])) == 1


def test_missing_pub_time_is_dropped():
    """pub_time을 못 읽은 기사는 발행 시각 검증이 불가하므로 제외한다(정합성 우선)."""
    assert fnl.filter_after_market_open([{"title": "시각 없음"}]) == []


def test_real_incident_leaves_nothing_at_0900():
    """실사고 리플레이 — 09:00 실행 시 잡힌 두 기사가 모두 개장 전 발행이라 빈손이 된다."""
    incident = [
        _a("코스피·코스닥 또 동반 급락…사상 첫 이틀 연속 서킷브레이커 발동", "08:11"),
        _a('노무라 "코스피 급락 배경은 외국인 대규모 매도와 국민연금 매수세 약화"', "07:48"),
    ]
    assert fnl.filter_after_market_open(incident) == []


# ── B. 어제 발행분 중복 판정 ──────────────────────────────────────────────────

def _write_prev(tmp_path, payload):
    (tmp_path / "kospi-news-2026-07-29.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_loads_yesterday_titles(tmp_path):
    _write_prev(tmp_path, {
        "date": "2026-07-29",
        "seen_titles": ["SK하이닉스 실적에도 무너진 증시…코스피 5,400선까지 추락"],
        "latest": {"market": {"title": "코스피·코스닥 이틀째 동반 서킷브레이커…국내 증시 '패닉 장세'"}},
        "history": [{"market": {"title": "코스피·코스닥 이틀째 동반 서킷브레이커…국내 증시 '패닉 장세'"},
                     "stock": {"title": '노무라 "코스피 급락 배경, 외인 대규모 매도·국민연금발 수급공백"'}}],
    })
    titles = fnl.load_prev_day_titles("2026-07-30", tmp_path)
    assert len(titles) == 3  # 중복 없이 합쳐진다
    assert any("서킷브레이커" in t for t in titles)
    assert any("노무라" in t for t in titles)


def test_no_prev_file_returns_empty(tmp_path):
    assert fnl.load_prev_day_titles("2026-07-30", tmp_path) == []


def test_corrupt_prev_file_returns_empty(tmp_path):
    (tmp_path / "kospi-news-2026-07-29.json").write_text("{not json", encoding="utf-8")
    assert fnl.load_prev_day_titles("2026-07-30", tmp_path) == []


def test_yesterday_titles_block_reworded_repost(tmp_path):
    """실사고 리플레이 — 어제 타이틀을 dedup에 넣으면 제목만 바꾼 재발행이 사전 제거된다."""
    _write_prev(tmp_path, {
        "date": "2026-07-29",
        "seen_titles": [
            "코스피·코스닥 이틀째 동반 서킷브레이커…국내 증시 '패닉 장세'",
            '노무라 "코스피 급락 배경, 외인 대규모 매도·국민연금발 수급공백"',
        ],
    })
    prev = fnl.load_prev_day_titles("2026-07-30", tmp_path)
    incident = [
        _a("코스피·코스닥 또 동반 급락…사상 첫 이틀 연속 서킷브레이커 발동", "09:30"),
        _a('노무라 "코스피 급락 배경은 외국인 대규모 매도와 국민연금 매수세 약화"', "09:31"),
        _a("삼성전자 장중 반등…외국인 순매수 전환", "09:32"),
    ]
    kept = [a["title"] for a in fnl._filter_seen_articles(incident, prev)]
    assert kept == ["삼성전자 장중 반등…외국인 순매수 전환"]


# ── C. 한국어 재작성 중복 판정 (문자 2-gram) ─────────────────────────────────

def test_reworded_korean_titles_are_duplicates():
    """조사·어미만 바꾼 재작성은 어절 겹침이 낮아도 같은 이슈로 판정한다."""
    assert fnl._is_dup_title(
        "코스피·코스닥 이틀째 동반 서킷브레이커…국내 증시 '패닉 장세'",
        "코스피·코스닥 또 동반 급락…사상 첫 이틀 연속 서킷브레이커 발동")
    assert fnl._is_dup_title(
        '노무라 "코스피 급락 배경, 외인 대규모 매도·국민연금발 수급공백"',
        '노무라 "코스피 급락 배경은 외국인 대규모 매도와 국민연금 매수세 약화"')


def test_distinct_issues_are_not_duplicates():
    """서로 다른 이슈는 오제거하지 않는다."""
    assert not fnl._is_dup_title(
        "코스피·코스닥 이틀째 동반 서킷브레이커…국내 증시 '패닉 장세'",
        "삼성전자 장중 반등…외국인 순매수 전환")
    assert not fnl._is_dup_title(
        "코스피 외국인 순매도 이어져", "코스피 기관 순매수 전환에 지수 반등")
    assert not fnl._is_dup_title(
        "SK하이닉스 실적에도 무너진 증시…코스피 5,400선까지 추락",
        "한화오션 수주 소식에 조선주 강세")


def test_result_level_duplicate_against_yesterday(tmp_path):
    """사후 검사(_find_duplicate)도 어제 타이틀로 재발행을 잡아낸다."""
    prev = ["코스피·코스닥 이틀째 동반 서킷브레이커…국내 증시 '패닉 장세'"]
    result = {"market": {"title": "코스피·코스닥 또 동반 급락…사상 첫 이틀 연속 서킷브레이커 발동"},
              "stock": {"title": "삼성전자 장중 반등"}}
    assert fnl._find_duplicate(result, prev)
