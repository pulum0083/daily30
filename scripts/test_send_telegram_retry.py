# 텔레그램 전송 재시도·관리자 알림 회귀 테스트 (2026-08-05 미발송 사고)
"""2026-08-05 07:32 코스피 브리핑이 read timeout 한 번에 미발송된 사고의 회귀 테스트.

사고 당시 send_message()는 timeout=15 단발 호출이라 일시적 네트워크 요동에 그대로 포기했고,
워크플로우 스텝의 continue-on-error 때문에 잡은 success로 끝나 아무도 알아채지 못했다.
"""

import socket
import sys
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import send_telegram as st


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://api.telegram.org/", code=code, msg="err", hdrs=None,
        fp=mock.Mock(read=lambda: b'{"ok": false}'),
    )


class _Resp:
    """urlopen 컨텍스트 매니저 흉내."""

    def __init__(self, payload: bytes = b'{"ok": true}'):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


@pytest.fixture(autouse=True)
def _no_sleep():
    with mock.patch.object(st.time, "sleep") as slept:
        yield slept


def test_retries_after_read_timeout_then_succeeds():
    """사고 재현 — 첫 시도가 read timeout이어도 재시도해서 결국 발송된다."""
    calls = [socket.timeout("The read operation timed out"), _Resp()]

    def fake(req, timeout=None):
        got = calls.pop(0)
        if isinstance(got, Exception):
            raise got
        return got

    with mock.patch.object(st.urllib.request, "urlopen", side_effect=fake):
        assert st.send_message("tok", "chat", "hi") == {"ok": True}
    assert not calls, "두 번째 시도가 일어나지 않았다"


def test_gives_up_after_max_attempts_and_raises():
    """계속 실패하면 마지막엔 예외를 올린다 — 조용히 성공으로 넘어가면 안 된다."""
    with mock.patch.object(
        st.urllib.request, "urlopen", side_effect=socket.timeout("timed out")
    ) as up:
        with pytest.raises(RuntimeError):
            st.send_message("tok", "chat", "hi")
    assert up.call_count == st.SEND_MAX_ATTEMPTS


def test_retries_on_http_5xx():
    """텔레그램 5xx는 일시적 — 재시도한다."""
    calls = [_http_error(502), _Resp()]

    def fake(req, timeout=None):
        got = calls.pop(0)
        if isinstance(got, Exception):
            raise got
        return got

    with mock.patch.object(st.urllib.request, "urlopen", side_effect=fake):
        assert st.send_message("tok", "chat", "hi") == {"ok": True}
    assert not calls


def test_does_not_retry_on_http_4xx():
    """400/401은 토큰·chat_id 오류라 재시도해도 똑같이 실패한다 — 즉시 포기."""
    with mock.patch.object(
        st.urllib.request, "urlopen", side_effect=_http_error(401)
    ) as up:
        with pytest.raises(RuntimeError):
            st.send_message("tok", "chat", "hi")
    assert up.call_count == 1


def test_admin_alert_sent_when_send_fails(monkeypatch, capsys):
    """최종 실패 시 관리자에게 알린다 — continue-on-error로 묻히지 않게."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_ID", "admin")
    monkeypatch.setattr(sys, "argv", ["send_telegram.py", "--type", "kospi"])
    monkeypatch.setattr(st, "already_sent_today", lambda *a, **k: False)
    monkeypatch.setattr(st, "load_credentials", lambda lang="ko": ("tok", "chat"))
    monkeypatch.setattr(st, "pick_quote", lambda: "")
    monkeypatch.setattr(
        st, "send_message", mock.Mock(side_effect=RuntimeError("The read operation timed out"))
    )
    alert = mock.Mock()
    monkeypatch.setattr(st, "send_admin_alert", alert)

    with pytest.raises(SystemExit) as exc:
        st.main()

    assert exc.value.code == 1
    alert.assert_called_once()
    assert "kospi" in alert.call_args[0][0]


def test_admin_alert_skipped_without_keys(monkeypatch, capsys):
    """알림 키가 없으면 조용히 건너뛴다 — 알림 실패가 원래 오류를 가리면 안 된다."""
    monkeypatch.delenv("TELEGRAM_ADMIN_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    with mock.patch.object(st.urllib.request, "urlopen") as up:
        st.send_admin_alert("boom")
    up.assert_not_called()
