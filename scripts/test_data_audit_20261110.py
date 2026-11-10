# 2026-11-10 전체 데이터 점검에서 찾은 오류의 회귀 테스트 — 아침 수급 단위·오래된 실적 이슈·'전부' 표현(네트워크 없음)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc  # noqa: E402
import validate_analysis as v  # noqa: E402

LATEST_KOSPI = {"investor_trading": {"foreign": {"net": -689500}, "institution": {"net": 717200}, "individual": {"net": -489100}}}


# ── 코스피 아침 수급 단위(실사고: "외국인 6,895백만원" — 실제 6,895억원) ──

def test_morning_supply_baekman_corrected():
    a = {"generated_at": "2026-11-10T07:28:00+09:00",
         "todays_view": {"recap": [{"text": "전일 코스피는 약세 마감했어요. 외국인은 <b>6,895백만원</b> 순매도했고 기관이 <b>7,172백만원</b> 순매수하며 방어했어요."}]}}
    c, w = [], []
    v.fix_supply_amounts(a, LATEST_KOSPI, c, w, skip=v._SUPPLY_SKIP_MORNING)
    t = a["todays_view"]["recap"][0]["text"]
    assert "6,895억원" in t and "7,172억원" in t and "백만원" not in t


def test_morning_supply_correct_baekman_is_rewritten_to_eok():
    a = {"x": "외국인이 <b>-689,500백만원</b> 순매도했어요."}
    v.fix_supply_amounts(a, LATEST_KOSPI, [], [], skip=v._SUPPLY_SKIP_MORNING)
    assert a["x"] == "외국인이 <b>-6,895억원</b> 순매도했어요."


def test_morning_supply_other_day_untouched():
    a = {"x": "지난주 목요일 외국인은 <b>3조 3,928억원</b>을 팔았어요."}
    v.fix_supply_amounts(a, LATEST_KOSPI, [], [], skip=v._SUPPLY_SKIP_MORNING)
    assert "3조 3,928억원" in a["x"]


def test_kospi_prompt_supply_in_eok():
    out = cc._investor_to_eok(LATEST_KOSPI["investor_trading"])
    assert out["foreign"]["net"] == -6895 and out["_unit"] == "억원"
    assert LATEST_KOSPI["investor_trading"]["foreign"]["net"] == -689500       # 원본은 그대로
    assert "단위: 백만원" not in cc.KOSPI_SYSTEM_PROMPT


# ── 오래된 실적을 지금 일로 쓴 미국 이슈(실사고: 맥도날드 11/4 실적이 11/10 이슈로) ──

def _issue(title, tickers, side="up"):
    return {"kind": "news", "title": title, "body": "", side: {"label": "x", "tickers": tickers}}


def test_stale_earnings_issue_dropped():
    ages = {"MCD": 6, "TTD": 1, "NVDA": 40}
    a = {"generated_at": "2026-11-10T21:17:00+09:00", "issues": [
        _issue("맥도날드 실적 호조로 소비재 안도감 확산", ["MCD"]),
        _issue("트레이드 데스크, 실적 서프라이즈로 급등", ["TTD"]),
        _issue("엔비디아 실적 앞두고 관망", ["NVDA"]),                  # 발표 전 예고는 두다
        _issue("CPI 발표 대기", []),
    ]}
    c = []
    assert v.drop_stale_earnings_issues(a, c, age_fn=lambda t, d: ages.get(t)) == 1
    assert [i["title"] for i in a["issues"]] == ["트레이드 데스크, 실적 서프라이즈로 급등", "엔비디아 실적 앞두고 관망", "CPI 발표 대기"]
    assert "MCD" in c[0]


def test_stale_earnings_unknown_age_kept():
    a = {"generated_at": "2026-11-10T21:17:00+09:00", "issues": [_issue("맥도날드 실적 호조", ["MCD"])]}
    assert v.drop_stale_earnings_issues(a, [], age_fn=lambda t, d: None) == 0
    assert len(a["issues"]) == 1


# ── '전종목·전 섹터' 표현(실사고: 하락 175종목·바이오 −1.69%인 날 "코스피 전종목이 들고 일어나") ──

def test_all_claims_softened_when_not_all():
    a = {"market_title": "코스피 전종목이 들고 일어나 +4.39%", "dek": "전 섹터가 동시에 뛰며 코스피가 올랐어요."}
    lat = {"market_breadth": {"up": 716, "down": 175}, "sectors": [{"name": "전력기기", "change_pct": 10.57}, {"name": "바이오", "change_pct": -1.69}]}
    v.fix_all_claims(a, lat, [])
    assert a["market_title"] == "코스피 대부분 종목이 들고 일어나 +4.39%"
    assert a["dek"].startswith("대부분 섹터가")


def test_all_claims_kept_when_really_all():
    a = {"market_title": "전 섹터 동반 상승"}
    lat = {"market_breadth": {"up": 900, "down": 0}, "sectors": [{"change_pct": 1.0}, {"change_pct": 2.0}]}
    v.fix_all_claims(a, lat, [])
    assert a["market_title"] == "전 섹터 동반 상승"
