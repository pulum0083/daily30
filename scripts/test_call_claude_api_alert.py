# Claude API 호출 실패 시 관리자 알림 — 2026-08-31 크레딧 소진 무음 실패 방지.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import call_claude as cc  # noqa: E402

REAL_ERR = ("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
            "'message': 'Your credit balance is too low to access the Anthropic API. "
            "Please go to Plans & Billing to upgrade or purchase credits.'}}")


def _capture(monkeypatch):
    sent = []
    import send_telegram
    monkeypatch.setattr(send_telegram, "send_admin_alert", lambda m: sent.append(m))
    return sent


def test_credit_error_gets_billing_hint(monkeypatch):
    """실사고 리플레이 — 크레딧 소진이면 '충전' 안내가 붙어야 한다."""
    sent = _capture(monkeypatch)
    cc.alert_api_failure("kospi-close", "2026-08-31", Exception(REAL_ERR))
    assert len(sent) == 1
    msg = sent[0]
    assert "크레딧 소진" in msg and "Plans & Billing" in msg
    assert "kospi-close / 2026-08-31" in msg
    assert "모든 브리핑이 같은 이유로 실패" in msg


def test_auth_and_rate_limit_hints(monkeypatch):
    sent = _capture(monkeypatch)
    cc.alert_api_failure("us", "2026-08-31", Exception("authentication_error: invalid x-api-key"))
    cc.alert_api_failure("kospi", "2026-08-31", Exception("rate limit exceeded"))
    assert "인증 실패" in sent[0]
    assert "레이트 리밋" in sent[1]


def test_unknown_error_still_alerts(monkeypatch):
    """원인을 몰라도 알림 자체는 나가야 한다 — 무음이 최악이다."""
    sent = _capture(monkeypatch)
    cc.alert_api_failure("kospi", "2026-08-31", Exception("connection reset by peer"))
    assert len(sent) == 1
    assert "connection reset by peer" in sent[0]
    assert "원인:" not in sent[0]


def test_long_error_truncated(monkeypatch):
    sent = _capture(monkeypatch)
    cc.alert_api_failure("us", "2026-08-31", Exception("x" * 5000))
    assert len(sent[0]) < 800


def test_alert_failure_does_not_raise(monkeypatch):
    """알림이 실패해도 원래 오류 처리를 가리면 안 된다."""
    import send_telegram

    def boom(_):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(send_telegram, "send_admin_alert", boom)
    cc.alert_api_failure("kospi", "2026-08-31", Exception(REAL_ERR))   # 예외가 새면 실패


def test_no_telegram_keys_is_silent(monkeypatch):
    """키 미설정 환경(로컬 등)에서도 예외 없이 지나가야 한다."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ADMIN_CHAT_ID", raising=False)
    cc.alert_api_failure("kospi", "2026-08-31", Exception(REAL_ERR))
