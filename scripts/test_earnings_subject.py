# 실적 촉매의 **주어** 기준 stale 판정 테스트 (2026-08-04 실사고).
# 사고: "마이크론(MU)의 3분기 실적 예상치 상회 → 프리마켓에서 반도체 관련주(AMD, QCOM) 강세"
# 의 ticker 필드가 "MU,AMD,QCOM"이었고, 마침 AMD가 그날(0일 전) 실적을 발표해
# "여러 티커 중 하나라도 최근이면 유지" 규칙에 걸려 41일 된 마이크론 실적이 통과했다.
# 같은 날조가 headlines(순수 문자열, ticker 필드 없음)에서는 MU만 잡혀 정상 제외됐다.
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn

TODAY = date(2026, 8, 4)
INCIDENT = "마이크론(MU)의 3분기 실적 예상치 상회 → 프리마켓에서 반도체 관련주(AMD, QCOM) 강세"
# 실측(2026-08-04 기준): MU 41일 전, AMD 당일, QCOM 6일 전
AGES = {"MU": 41, "AMD": 0, "QCOM": 6, "JPM": 1, "GS": 20, "NVDA": 5}


def _fake_age(mapping):
    return lambda t, today: mapping.get(t)


# ─── 주어 추출: "사건 → 영향"의 왼쪽만 본다 ───

def test_subject_is_cause_side_only():
    assert fn._earnings_subject_tickers(INCIDENT, "MU,AMD,QCOM") == ["MU"]


def test_subject_handles_ascii_arrow():
    txt = "마이크론(MU) 실적 서프라이즈 -> 반도체 장비주(AMAT) 동반 강세"
    assert fn._earnings_subject_tickers(txt, "MU,AMAT") == ["MU"]


def test_subject_allows_multiple_real_subjects():
    txt = "JP모건(JPM)·골드만삭스(GS) 실적 발표 → 금융 섹터 전반 강세"
    assert set(fn._earnings_subject_tickers(txt, "JPM,GS")) == {"JPM", "GS"}


def test_subject_falls_back_without_arrow():
    """화살표가 없으면 주어를 특정할 수 없으므로 기존대로 전체 티커를 본다(fail-open)."""
    txt = "엔비디아 실적 발표 이후 반도체 섹터 변동성 확대"
    assert fn._earnings_subject_tickers(txt, "NVDA,AMD") == ["NVDA", "AMD"]


def test_subject_ignores_bystander_named_only_in_effect():
    txt = "마이크론 3분기 실적 상회 → AMD, QCOM 동반 강세"
    assert fn._earnings_subject_tickers(txt, "MU,AMD,QCOM") == ["MU"]


# ─── 실사고 리플레이 ───

def test_incident_stale_subject_dropped_despite_fresh_bystander():
    cats = [{"date": "2026-08-04", "text": INCIDENT, "ticker": "MU,AMD,QCOM"}]
    assert fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age(AGES)) == []


def test_fresh_subject_survives():
    txt = "AMD의 2분기 실적 예상치 상회 → 반도체 섹터 전반 강세"
    cats = [{"date": "2026-08-04", "text": txt, "ticker": "AMD,MU"}]
    assert len(fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age(AGES))) == 1


def test_multi_subject_one_fresh_survives():
    txt = "JP모건(JPM)·골드만삭스(GS) 실적 발표 → 금융 섹터 강세"
    cats = [{"date": "2026-08-04", "text": txt, "ticker": "JPM,GS"}]
    assert len(fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age(AGES))) == 1


def test_non_earnings_catalyst_untouched():
    txt = "중동 긴장 고조 → 국제 유가 급등, 에너지주(XOM) 강세"
    cats = [{"date": "2026-08-04", "text": txt, "ticker": "XOM"}]
    assert len(fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age(AGES))) == 1


def test_unresolvable_subject_kept():
    """조회 실패·미등록 티커는 검증 불가 → 유지(과잉 제외 방지)."""
    txt = "어느 중소형주 실적 발표 → 섹터 강세"
    cats = [{"date": "2026-08-04", "text": txt, "ticker": ""}]
    assert len(fn._drop_stale_earnings(cats, TODAY, age_fn=_fake_age(AGES))) == 1


# ─── 직전 실행 결과 되뱉기(에코) 차단 ───

PREV = [
    "마이크론(MU)의 3분기 실적 예상치 상회 → 프리마켓에서 반도체 관련주(AMD, QCOM) 강세",
    "테슬라(TSLA)의 신규 배터리 기술 발표 → 프리마켓에서 TSLA 3% 상승, 관련 부품주(LMT) 강세",
]


def test_verbatim_echo_of_prev_run_dropped():
    items = [{"date": "2026-08-04", "text": PREV[0], "ticker": "MU"}]
    assert fn._drop_prev_run_echoes(items, PREV) == []


def test_annotated_echo_dropped():
    """모델이 스스로 '직전 브리핑에서 언급된 내용'이라 달아 보낸 형태(2026-08-04 재현 확인)."""
    txt = PREV[1] + ". (참고: 직전 브리핑에서 언급된 내용으로, 오늘 추가적인 후속 움직임이 없다면 우선순위 낮음)"
    assert fn._drop_prev_run_echoes([{"text": txt}], PREV) == []


def test_new_catalyst_survives_echo_gate():
    txt = "브로드컴(AVGO) 신규 AI 가속기 수주 공시 → 프리마켓 강세"
    items = [{"date": "2026-08-04", "text": txt, "ticker": "AVGO"}]
    assert len(fn._drop_prev_run_echoes(items, PREV)) == 1


def test_echo_gate_noop_without_prev():
    items = [{"text": PREV[0]}]
    assert len(fn._drop_prev_run_echoes(items, [])) == 1


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
