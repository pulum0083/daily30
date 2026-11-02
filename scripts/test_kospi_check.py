# 코스피 체크 계산 테스트(네트워크 없음)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kospi_check as kc  # noqa: E402


def _daily(months):
    """[(YYYY-MM, 월말 종가)] → 일봉. 월 안에 고점이 큰 날을 하나 넣어, 고점이 아니라 종가를 쓰는지 가른다."""
    out = []
    for m, c in months:
        out.append((f"{m}-05", c * 3, c, c))
        out.append((f"{m}-20", c, c, c))
    return out


def _months(n, start_year=2020):
    return [f"{start_year + i // 12}-{i % 12 + 1:02d}" for i in range(n)]


def test_uses_close_not_monthly_high():
    ms = _months(60)
    r = kc.compute(_daily([(m, 100.0) for m in ms]), f"{ms[-1]}-28", 100.0)
    assert r["gap_pct"] == 0.0 and r["ma60"] == 100.0 and r["months"] == 1 and r["since"] == ms[-1]


def test_last_close_overrides_yahoo_and_current_month_counts():
    ms = _months(60)
    daily = _daily([(m, 100.0) for m in ms]) + [(f"{ms[-1]}-28", 500.0, 500.0, 500.0)]
    r = kc.compute(daily, f"{ms[-1]}-28", 200.0)   # 야후 500 대신 네이버 200을 쓴다
    assert r["close"] == 200.0
    assert r["ma60"] == round((100 * 59 + 200) / 60, 1)
    assert r["gap_pct"] == round((200 / ((100 * 59 + 200) / 60) - 1) * 100, 1)


def test_position_above_and_maxes():
    # 2020~2024년 100 → 2025-01 300(지난해 최고) → 2025년 100 → 2026-01 400(올해 최고) → 2026-02 지금 150
    ms = _months(74)
    vals = {m: 100.0 for m in ms}
    vals["2025-01"] = 300.0
    vals["2026-01"] = 400.0
    last = ms[-1]
    assert last == "2026-02"
    r = kc.compute(_daily([(m, vals[m]) for m in ms if m != last]), "2026-02-10", 150.0)
    assert r["asof"] == "2026-02-10" and r["since"] == "2024-12"
    assert r["year_max"]["m"] == "2026-01" and r["prev_max"]["m"] == "2025-01"
    assert r["year_max"]["gap"] > r["prev_max"]["gap"] > r["gap_pct"] > 0
    assert r["above"] == 2                                        # 2025-01·2026-01만 지금보다 높다


def test_first_year_has_no_prev_max():
    ms = _months(60)
    r = kc.compute(_daily([(m, 100.0) for m in ms]), f"{ms[-1]}-28", 100.0)
    assert r["prev_max"] is None


def test_short_history_returns_none():
    ms = _months(30)
    assert kc.compute(_daily([(m, 100.0) for m in ms]), f"{ms[-1]}-28", 100.0) is None


def test_fetch_failure_returns_none(monkeypatch):
    def boom(_):
        raise OSError("down")
    monkeypatch.setattr(kc.nq, "fetch_daily", boom)
    assert kc.fetch("2026-11-02", 5859.08) is None
