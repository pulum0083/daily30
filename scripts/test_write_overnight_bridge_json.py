# generate_html.write_overnight_bridge_json 단위 테스트 (네트워크 없음)
"""실행: python3 -m pytest scripts/test_write_overnight_bridge_json.py -v

이 파일이 지키는 것은 web/data/overnight-bridge.json의 발행 계약이다.
클라이언트(/stocks/ 홈)는 이 스키마만 보고 렌더하므로, 키 이름·date 의미·빈 상태가
조용히 바뀌면 화면이 통째로 죽거나 매일 스테일로 오판된다.
"""
import json

import pytest

import generate_html as g


ROW_KEYS = {
    "sector", "us_label", "kr_label",
    "us_change_fmt", "kr_change_fmt", "us_cls", "kr_cls",
    "gap_fmt", "gap_cls", "gap_word",
}


def _row(**overrides):
    row = {
        "sector": "반도체",
        "us_label": "SOXX",
        "us_change": 1.5,
        "kr_label": "삼성전자·SK하이닉스",
        "kr_change": 4.0,
        "gap_pp": 2.5,
        "kr_session_date": "2026-07-31",
    }
    row.update(overrides)
    return row


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "WEB_DIR", tmp_path)
    return tmp_path / "data" / "overnight-bridge.json"


def _write(market_data, date="2026-08-03"):
    g.write_overnight_bridge_json(market_data, date)


# ── date는 발행일이다 — kr_session_date로 바꿔치기하면 안 된다 ──────────────────


def test_date_is_the_briefing_publish_date_not_the_kr_session_date(out_dir):
    """date는 클라이언트가 "이 파일이 오늘 것인가"를 판정하는 유일한 근거다(스테일 게이트).

    비교 대상 한국 세션 날짜(kr_session_date)를 여기에 넣으면 월요일마다 3일 어긋나
    갓 만든 파일을 클라이언트가 매번 스테일로 오판하고 브리지가 통째로 사라진다.
    두 날짜를 일부러 다르게 둬서 바꿔치기가 드러나게 한다.
    """
    _write({"overnight_bridge": [_row(kr_session_date="2026-07-31")]}, date="2026-08-03")
    data = json.loads(out_dir.read_text(encoding="utf-8"))

    assert data["date"] == "2026-08-03"            # 발행일(월요일 가정)
    assert data["kr_session_date"] == "2026-07-31"  # 직전 한국 마감(금요일)
    assert data["date"] != data["kr_session_date"]


def test_generated_at_is_kst_iso(out_dir):
    _write({"overnight_bridge": [_row()]})
    data = json.loads(out_dir.read_text(encoding="utf-8"))

    assert data["generated_at"].endswith("+09:00")


# ── 스키마 계약 ──────────────────────────────────────────────────────────────


def test_toplevel_keys_are_exactly_the_published_contract(out_dir):
    _write({"overnight_bridge": [_row()]})
    data = json.loads(out_dir.read_text(encoding="utf-8"))

    assert set(data) == {"date", "generated_at", "kr_session_date", "rows"}


def test_row_keys_are_exactly_the_display_fields(out_dir):
    _write({"overnight_bridge": [_row()]})
    data = json.loads(out_dir.read_text(encoding="utf-8"))

    assert len(data["rows"]) == 1
    assert set(data["rows"][0]) == ROW_KEYS


def test_rows_carry_baked_strings_not_raw_numbers(out_dir):
    """경계 판정(>= 0 / > 0)을 JS가 다시 구현하지 못하도록 원시 수치는 내보내지 않는다(§30)."""
    _write({"overnight_bridge": [_row()]})
    row = json.loads(out_dir.read_text(encoding="utf-8"))["rows"][0]

    assert "us_change" not in row and "kr_change" not in row and "gap_pp" not in row
    assert row["us_change_fmt"] == "+1.50%"
    assert row["gap_fmt"] == "+2.5%p"
    assert row["gap_word"] == "선반영"
    assert row["gap_cls"] == "up"


# ── 빈 상태는 모호하지 않아야 한다 ────────────────────────────────────────────


def test_empty_state_still_writes_todays_file(out_dir):
    """행이 없어도 오늘 날짜 + 빈 rows로 덮어써야 어제 내용이 남지 않는다."""
    _write({}, date="2026-08-03")
    data = json.loads(out_dir.read_text(encoding="utf-8"))

    assert data["date"] == "2026-08-03"
    assert data["rows"] == []
    assert data["kr_session_date"] == ""


def test_empty_state_overwrites_yesterdays_content(out_dir):
    _write({"overnight_bridge": [_row()]}, date="2026-08-02")
    _write({}, date="2026-08-03")
    data = json.loads(out_dir.read_text(encoding="utf-8"))

    assert data["date"] == "2026-08-03"
    assert data["rows"] == []


# ── Critical: 깨진 라벨이 유효하지 않은 JSON을 만들면 안 된다 ─────────────────


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), None, 123, ""])
@pytest.mark.parametrize("key", ["sector", "us_label", "kr_label"])
def test_bad_label_row_is_skipped_and_file_stays_valid_json(out_dir, key, bad):
    """라벨에 NaN이 들어가면 json.dumps가 예외 없이 맨몸 NaN 리터럴을 써서
    파일 전체가 유효하지 않은 JSON이 된다 — 클라이언트 JSON.parse가 통째로 실패한다.
    행 단계에서 걸러 파일이 항상 파싱 가능하도록 고정한다."""
    _write({"overnight_bridge": [_row(**{key: bad})]})

    text = out_dir.read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    data = json.loads(text)  # 표준 JSON으로 파싱되어야 한다
    assert data["rows"] == []


def test_bad_label_row_skipped_but_healthy_row_survives(out_dir):
    bad = _row(sector="자동차", us_label=float("nan"))
    good = _row(sector="반도체")
    _write({"overnight_bridge": [bad, good]})

    data = json.loads(out_dir.read_text(encoding="utf-8"))
    assert [r["sector"] for r in data["rows"]] == ["반도체"]


def test_allow_nan_false_raises_instead_of_writing_invalid_json(out_dir, monkeypatch):
    """행 게이트를 뚫고 비유한 값이 남았을 때의 최종 방어선.

    기본 설정의 json.dumps는 조용히 NaN 리터럴을 쓴다 — allow_nan=False라야
    ValueError로 터지고, 호출부 가드가 잡아 파일을 아예 건드리지 않는다.
    """
    monkeypatch.setattr(g, "build_overnight_bridge", lambda _md: {
        "overnight_bridge": [{"sector": float("nan")}],
        "overnight_bridge_date": "2026-07-31",
    })

    with pytest.raises(ValueError):
        _write({"overnight_bridge": [_row()]})

    assert not out_dir.exists()  # 깨진 파일을 남기지 않는다


def test_serialization_failure_leaves_previous_file_untouched(out_dir, monkeypatch):
    """직전 파일이 낡았을지언정 유효하고 date로 걸러진다 — 깨진 파일로 덮는 것보다 낫다(§0)."""
    _write({"overnight_bridge": [_row()]}, date="2026-08-02")
    before = out_dir.read_text(encoding="utf-8")

    monkeypatch.setattr(g, "build_overnight_bridge", lambda _md: {
        "overnight_bridge": [{"sector": float("inf")}],
        "overnight_bridge_date": "2026-07-31",
    })
    with pytest.raises(ValueError):
        _write({}, date="2026-08-03")

    assert out_dir.read_text(encoding="utf-8") == before


# ── 원자적 쓰기 ──────────────────────────────────────────────────────────────


def test_write_leaves_no_tmp_file_behind(out_dir):
    """브라우저가 직접 fetch하는 파일이라 tmp + os.replace로 쓴다 — 찌꺼기가 남으면 안 된다."""
    _write({"overnight_bridge": [_row()]})

    leftovers = list(out_dir.parent.glob("*.tmp"))
    assert leftovers == []
    assert out_dir.exists()


def test_write_is_atomic_not_truncate_in_place(out_dir, monkeypatch):
    """실제 파일에 직접 쓰지 않고 tmp에 쓴 뒤 교체해야 한다.

    write_text로 제자리 덮어쓰기를 하면 그 순간 파일이 잘렸다가 다시 채워져,
    마침 fetch 중인 브라우저가 절반짜리 파일을 받는다. 교체 단계를 실패시켜
    "그 전까지 원본이 손대지지 않았는지"로 원자성을 확인한다.
    """
    _write({"overnight_bridge": [_row()]}, date="2026-08-02")
    before = out_dir.read_text(encoding="utf-8")

    def _boom(src, dst):
        raise OSError("교체 실패")

    monkeypatch.setattr(g.os, "replace", _boom)
    with pytest.raises(OSError):
        _write({"overnight_bridge": [_row(sector="자동차")]}, date="2026-08-03")

    # 제자리 쓰기였다면 이 시점에 원본이 이미 새 내용으로 바뀌어 있다.
    assert out_dir.read_text(encoding="utf-8") == before
    # 실패해도 tmp 찌꺼기를 남기지 않는다 — 코스피 잡의 git add web/ 이 그대로 커밋한다.
    assert list(out_dir.parent.glob("*.tmp")) == []


def test_nan_sector_is_logged_as_question_mark_not_as_nan(out_dir, capsys):
    """float("nan")은 truthy라 `or "?"` 만으로는 안 걸린다 —
    진단 로그에 섹터명이 'nan'으로 찍히면 사람이 원인을 오해한다."""
    _write({"overnight_bridge": [_row(sector=float("nan"))]})

    err = capsys.readouterr().err
    assert "? 행의 sector" in err
    assert "nan 행의" not in err


# ── 과거 날짜 재생성은 라이브 파일을 건드리지 않는다(§2) ──────────────────────


def test_today_target_is_publishable():
    from datetime import datetime
    today = datetime.now(g.KST).strftime("%Y-%m-%d")

    assert g._bridge_target_is_today(today) is True


def test_past_date_rerender_is_not_publishable():
    """§2 과거 날짜 재생성 시 라이브 JSON을 6월 행으로 덮으면,
    클라이언트 date 게이트가 걸러내 다음 07:25까지 브리지가 조용히 사라진다."""
    assert g._bridge_target_is_today("2026-06-08") is False


def test_future_date_is_not_publishable():
    assert g._bridge_target_is_today("2099-01-01") is False
