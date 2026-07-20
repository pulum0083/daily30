# 교차일 recap 게이트(_is_cross_day_recap·_load_stale_catalysts·_append_catalyst_history) 검증.
# 자기보고 날짜를 못 믿는 상황에서 2일+ 전 catalyst 재탕을 하드 제외하는지 확인.
# 2026-07-15~20 실사고: 7/15 ASML 실적이 날짜만 오늘로 바뀐 채 매일 재등장.
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn

# 실제 git 이력의 ASML 변형
ASML_15 = "ASML, 2분기 실적 및 수주 호조 발표 → 프리마켓에서 반도체 장비주(램리서치, 어플라이드머티리얼즈 등) 강세 전망"
ASML_20 = "ASML의 호실적 발표 → 프리마켓에서 반도체 장비주 강세 견인"
NVDA_OLD = "엔비디아(NVDA)의 AI 칩 수요 지속 전망 → 프리마켓에서 NVDA 주가 1.5% 상승"
NVDA_NEW = "엔비디아(NVDA), 신규 블랙웰 데이터센터 GPU 양산 발표 → 클라우드 인프라주 동반 강세"
MS = "모건스탠리(MS)의 예상치 상회하는 2분기 실적 발표 → MS 주가 2% 상승"
OIL = "중동 지역 지정학적 긴장 고조 → 국제 유가(WTI) 1% 상승 및 에너지 관련주 강세"


# ── 유사도·엔티티 ────────────────────────────────────────────────
def test_distinctive_entities_excludes_generic():
    assert fn._distinctive_entities("엔비디아(NVDA)의 AI 칩 수요") == {"NVDA"}
    assert fn._distinctive_entities("6월 CPI·WTI·VIX 안정") == set()


# ── recap 판정 ──────────────────────────────────────────────────
def test_asml_variant_is_recap():
    assert fn._is_cross_day_recap(ASML_20, [ASML_15]) is True


def test_same_entity_different_news_is_not_recap():
    # NVDA라는 같은 엔티티라도 실제 다른 뉴스면 유지돼야 한다(오탐 방지 핵심)
    assert fn._is_cross_day_recap(NVDA_NEW, [NVDA_OLD]) is False


def test_different_events_not_recap():
    assert fn._is_cross_day_recap(MS, [ASML_15]) is False
    assert fn._is_cross_day_recap(OIL, [ASML_15, NVDA_OLD]) is False


def test_no_stale_means_keep_all():
    assert fn._drop_cross_day_recaps([ASML_20, OIL], []) == [ASML_20, OIL]


def test_drop_only_the_recap():
    out = fn._drop_cross_day_recaps([ASML_20, OIL, MS], [ASML_15])
    assert out == [OIL, MS]


# ── 히스토리 나이 필터 ────────────────────────────────────────────
def test_load_stale_only_two_plus_days_old(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    (tmp_path / "catalyst_history_us.json").write_text(json.dumps([
        {"date": "2026-07-15", "catalysts": [ASML_15]},   # 5일 전 → stale
        {"date": "2026-07-19", "catalysts": ["어제 사건"]},  # 어제 → 제외
        {"date": "2026-07-20", "catalysts": ["오늘 사건"]},  # 오늘 → 제외
    ], ensure_ascii=False), encoding="utf-8")
    stale = fn._load_stale_catalysts("us", date(2026, 7, 20))
    assert stale == [ASML_15]


def test_load_stale_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    assert fn._load_stale_catalysts("us", date(2026, 7, 20)) == []


# ── 히스토리 기록·정리 ────────────────────────────────────────────
def test_append_creates_and_prunes(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    for i in range(1, 8):  # 7일치 append → 최근 5일만 남아야
        fn._append_catalyst_history("us", date(2026, 7, i), [f"c{i}"])
    hist = json.load(open(tmp_path / "catalyst_history_us.json", encoding="utf-8"))
    assert [e["date"] for e in hist] == [
        "2026-07-03", "2026-07-04", "2026-07-05", "2026-07-06", "2026-07-07",
    ]


def test_append_same_day_replaces(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    fn._append_catalyst_history("us", date(2026, 7, 20), ["원본"])
    fn._append_catalyst_history("us", date(2026, 7, 20), ["정정본"])  # 같은 날 재실행
    hist = json.load(open(tmp_path / "catalyst_history_us.json", encoding="utf-8"))
    assert len(hist) == 1
    assert hist[0]["catalysts"] == ["정정본"]


# ── 통합: 게이트가 실제 ASML 재탕을 걸러내는 end-to-end 시나리오 ──
def test_end_to_end_asml_recap_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)
    fn._append_catalyst_history("us", date(2026, 7, 15), [ASML_15])
    stale = fn._load_stale_catalysts("us", date(2026, 7, 20))
    kept = fn._drop_cross_day_recaps([ASML_20, OIL], stale)
    assert kept == [OIL]
