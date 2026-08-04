# RSS 기사 목록 기반 뉴스 선별 테스트 — LLM이 목록에 없는 사실을 못 쓰게 막는지 검증.
# 2단계 전환의 핵심 불변식: 날짜·사건·수치·URL은 전부 실제 기사에서만 나온다.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn

ART = [
    {"title": "뉴욕증시, 美이란공격 취소·기술주 강세에 상승…나스닥 2%↑",
     "desc": "미국이 이란 공격을 취소했다는 소식에 위험선호가 회복되며 나스닥이 2.13% 올랐다.",
     "pub_time": "05:10", "date": "2026-08-04", "source": "연합뉴스",
     "link": "https://news.google.com/rss/articles/AAA"},
    {"title": "반도체, 피크아웃 공포 완화·엔비디아 급등에 강세",
     "desc": "반도체 업황 피크아웃 우려가 완화되며 엔비디아(NVDA)가 급등했다.",
     "pub_time": "05:02", "date": "2026-08-04", "source": "미디어펜",
     "link": "https://news.google.com/rss/articles/BBB"},
]


# ─── 중복 묶기: 같은 사건 여러 매체 → 대표 1건 ───

def test_dedupe_groups_same_event():
    arts = [
        {"title": "뉴욕증시, 美이란공격 취소·기술주 강세에 상승…나스닥 2%↑", "pub_time": "05:10",
         "desc": "", "source": "연합뉴스", "link": "a"},
        {"title": "뉴욕증시, 미국의 이란 공격 취소·기술주 강세에 상승‥나스닥 2%↑", "pub_time": "05:47",
         "desc": "", "source": "MBC", "link": "b"},
        {"title": "반도체, 피크아웃 공포 완화·엔비디아 급등에 강세", "pub_time": "05:02",
         "desc": "", "source": "미디어펜", "link": "c"},
    ]
    out = fn._dedupe_articles(arts)
    assert len(out) == 2, [a["title"] for a in out]


def test_dedupe_keeps_earliest_and_counts_sources():
    arts = [
        {"title": "뉴욕증시, 美이란공격 취소·기술주 강세에 상승…나스닥 2%↑", "pub_time": "05:10",
         "desc": "", "source": "연합뉴스", "link": "a"},
        {"title": "뉴욕증시, 미국의 이란 공격 취소·기술주 강세에 상승‥나스닥 2%↑", "pub_time": "05:47",
         "desc": "", "source": "MBC", "link": "b"},
    ]
    rep = fn._dedupe_articles(arts)[0]
    assert rep["pub_time"] == "05:10"          # 가장 이른 발행 기사를 대표로
    assert rep["source_count"] == 2            # 보도 매체 수는 신뢰도 신호(사실 여부 아님)


def test_dedupe_empty():
    assert fn._dedupe_articles([]) == []


# ─── 인덱스 검증: 목록 밖 항목은 존재할 수 없다 ───

def test_selection_rejects_out_of_range_index():
    sel = [{"idx": 9, "text": "무언가 → 영향"}]
    assert fn._resolve_selection(sel, ART) == []


def test_selection_rejects_missing_index():
    sel = [{"text": "인덱스 없는 항목 → 영향"}]
    assert fn._resolve_selection(sel, ART) == []


def test_selection_attaches_source_article():
    sel = [{"idx": 1, "text": "미국의 이란 공격 취소 → 위험선호 회복", "ticker": ""}]
    out = fn._resolve_selection(sel, ART)
    assert len(out) == 1
    assert out[0]["article"]["source"] == "연합뉴스"
    assert out[0]["date"] == "2026-08-04"      # 날짜는 기사에서 온다(LLM이 못 만든다)


# ─── 핵심 게이트: 기사에 없는 수치·기업을 쓰면 폐기 ───

def test_unsourced_number_is_rejected():
    """기사에 없는 등락률을 지어내면 그 항목을 버린다."""
    sel = [{"idx": 1, "text": "이란 공격 취소 → 나스닥 7.5% 급등", "ticker": ""}]
    assert fn._resolve_selection(sel, ART) == []


def test_sourced_number_survives():
    sel = [{"idx": 1, "text": "이란 공격 취소 → 나스닥 2.13% 상승", "ticker": ""}]
    assert len(fn._resolve_selection(sel, ART)) == 1


def test_unsourced_company_is_rejected():
    """기사에 없는 기업(마이크론)을 끌어오면 버린다 — §31 날조의 형태."""
    sel = [{"idx": 2, "text": "마이크론 실적 서프라이즈 → 반도체 강세", "ticker": "MU"}]
    assert fn._resolve_selection(sel, ART) == []


def test_sourced_company_survives():
    sel = [{"idx": 2, "text": "엔비디아 급등 → 반도체 섹터 강세", "ticker": "NVDA"}]
    assert len(fn._resolve_selection(sel, ART)) == 1


def test_unsourced_ticker_is_rejected():
    sel = [{"idx": 1, "text": "이란 리스크 완화 → TSLA 강세", "ticker": "TSLA"}]
    assert fn._resolve_selection(sel, ART) == []


def test_generic_words_not_treated_as_claims():
    """AI·CPI 같은 범용 대문자어는 기사에 없어도 트집잡지 않는다."""
    sel = [{"idx": 2, "text": "반도체 피크아웃 우려 완화 → AI 관련주 투자심리 개선", "ticker": ""}]
    assert len(fn._resolve_selection(sel, ART)) == 1


# ─── §31 실사고 리플레이 ───

def test_incident_replay_micron_cannot_be_produced():
    """8/4 기사 목록에 마이크론 실적 기사가 없으므로, 그 서사는 구조적으로 나올 수 없다."""
    sel = [
        {"idx": 1, "text": "마이크론(MU)의 3분기 실적 예상치 상회 → 반도체 관련주 강세", "ticker": "MU"},
        {"idx": 2, "text": "엔비디아 급등 → 반도체 섹터 강세", "ticker": "NVDA"},
    ]
    out = fn._resolve_selection(sel, ART)
    assert [o["text"] for o in out] == ["엔비디아 급등 → 반도체 섹터 강세"]


# ─── 프롬프트 블록 ───

def test_prompt_block_numbers_articles_from_one():
    block = fn._articles_prompt_block(ART)
    assert block.startswith("1.")
    assert "2." in block
    assert "연합뉴스" in block and "05:10" in block


def test_prompt_block_empty():
    assert fn._articles_prompt_block([]) == ""


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, f in sorted(globals().items()):
        if name.startswith("test_") and callable(f):
            try:
                f()
                print(f"  ✓ {name}")
            except Exception:
                fails += 1
                print(f"  ✗ {name}")
                traceback.print_exc()
    print(f"\n{'FAILED' if fails else 'ALL PASS'} ({fails} failures)")
    sys.exit(1 if fails else 0)
