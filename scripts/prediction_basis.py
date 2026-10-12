# 코스피 예측의 채점 기준(시초가/종가)과 통계 집계 대상을 한 곳에서 정하는 모듈
"""
2026-10-13부터 코스피 아침 예측은 '시초가 방향'을 맞힌다(SERVICE_RULES §57).
그 전 예측은 '종가 방향'을 맞힌다고 하고 낸 것이라 다시 채점하지 않고, 통계에서만 뺀다.

기준은 날짜가 아니라 기록에 붙은 `basis` 값으로 가른다 — 옛 날짜를 재생성해도 기준이 바뀌지 않는다.
  · basis == "open"  → 시초가 기준(전일 종가 대비 09:00 개장 지수)
  · basis 없음       → 종가 기준(전환 이전 기록)
"""

OPEN = "open"


def is_open_basis(row: dict) -> bool:
    return (row or {}).get("basis") == OPEN


def stats_rows(rows: list) -> list:
    """적중률·캘리브레이션에 세는 기록만 남긴다. 코스피는 시초가 기준 기록만, 그 외 타입은 그대로."""
    return [b for b in rows if b.get("type") != "kospi" or is_open_basis(b)]


def legacy_kospi_rows(rows: list) -> list:
    """전환 이전(종가 기준) 코스피 기록 — 통계에는 안 넣고 '이전 기록'으로만 보여준다."""
    return [b for b in rows if b.get("type") == "kospi" and not is_open_basis(b)]


def outcome_pct(row: dict):
    """그 기록의 기준에 맞는 실제 결과(%). 시초가 기준이면 갭, 아니면 종가 대비 등락률. 없으면 None."""
    v = row.get("actual_open_pct") if is_open_basis(row) else row.get("actual_change_pct")
    return v if isinstance(v, (int, float)) else None
