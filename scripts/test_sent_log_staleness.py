# 발송 기록 신선도 경고 회귀 테스트 (2026-07-02 ~ 08-05 가드 무음 사망)
"""중복 발송 가드(telegram_sent_log.json)가 죽었는지 스스로 알리게 하는 테스트.

2026-07-02 커밋 b257bdc9가 텔레그램 스텝을 커밋 스텝 뒤로 옮기면서, mark_sent_today()가
쓴 기록이 더는 커밋되지 않게 됐다. 가드는 fail-open이라 아무것도 막지 않은 채
한 달간 조용히 죽어 있었다 — §20의 _targets_data_is_stale()과 같은 처방을 둔다.
"""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import send_telegram as st


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "DATA_DIR", tmp_path)
    monkeypatch.setattr(st, "SENT_LOG_FILE", tmp_path / "telegram_sent_log.json")
    return tmp_path / "telegram_sent_log.json"


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_warns_when_log_is_stale(log_file, capsys):
    """기록이 오래 멈춰 있으면 — 가드가 죽었다는 뜻이므로 경고한다."""
    _write(log_file, {"kospi": {"ko": "2026-07-02"}})

    with mock.patch.object(st, "_today_kst", return_value="2026-08-05"):
        assert st.already_sent_today("kospi", "ko") is False

    err = capsys.readouterr().err
    assert "중복 발송 가드" in err
    assert "2026-07-02" in err


def test_no_warning_when_log_is_fresh(log_file, capsys):
    """정상 갱신 중이면 조용하다 — 매일 뜨는 경고는 아무도 안 읽는다."""
    _write(log_file, {"kospi": {"ko": "2026-08-04"}, "us": {"ko": "2026-08-04"}})

    with mock.patch.object(st, "_today_kst", return_value="2026-08-05"):
        assert st.already_sent_today("kospi", "ko") is False

    assert "중복 발송 가드" not in capsys.readouterr().err


def test_blocks_when_already_sent_today(log_file, capsys):
    """오늘 이미 보냈으면 막는다 — 가드 본래 기능."""
    _write(log_file, {"kospi": {"ko": "2026-08-05"}})

    with mock.patch.object(st, "_today_kst", return_value="2026-08-05"):
        assert st.already_sent_today("kospi", "ko") is True

    assert "중복 발송 가드" not in capsys.readouterr().err


def test_warns_when_log_missing(log_file, capsys):
    """파일 자체가 없으면 기록이 유실된 것 — 경고한다."""
    with mock.patch.object(st, "_today_kst", return_value="2026-08-05"):
        assert st.already_sent_today("kospi", "ko") is False

    assert "중복 발송 가드" in capsys.readouterr().err


def test_stale_guard_never_blocks(log_file, capsys):
    """경고는 하되 발송은 막지 않는다 — fail-open 유지(경고 때문에 브리핑이 끊기면 안 됨)."""
    _write(log_file, {"kospi": {"ko": "2020-01-01"}})

    with mock.patch.object(st, "_today_kst", return_value="2026-08-05"):
        assert st.already_sent_today("kospi", "ko") is False


def test_mark_sent_today_refreshes_log(log_file):
    """발송 성공 기록이 남아야 다음 실행에서 가드가 작동한다."""
    with mock.patch.object(st, "_today_kst", return_value="2026-08-05"):
        st.mark_sent_today("kospi", "ko")
        assert st.already_sent_today("kospi", "ko") is True

    assert json.loads(log_file.read_text())["kospi"]["ko"] == "2026-08-05"
