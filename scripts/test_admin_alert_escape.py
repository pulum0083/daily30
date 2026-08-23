# 관리자 알림이 브리핑 산문을 인용할 때 Telegram HTML 파싱으로 깨지지 않는지 검증 (2026-08-24 실사고)
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_analysis as va  # noqa: E402

# 2026-08-24 실사고 원문 — 부등호가 그대로 들어가 Telegram이 400을 반환했다.
INCIDENT_BLOCK = (
    "지수 최상급 주장이 실측과 모순 "
    "([\"S&P500 '최고' 주장이나 실측 7,674 < 52주 고점 7,799\"]): "
    "S&P500 사상 최고, 근데 선물은 숨 고르기"
)


_ENTITY_RE = re.compile(r"&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);")


def _bare_markup(text: str) -> bool:
    """<b>btype</b> 래퍼를 걷어낸 본문에 날 부등호나 엔티티 아닌 &가 남았는가."""
    body = text.split("</b>", 1)[-1]
    return "<" in body or ">" in body or "&" in _ENTITY_RE.sub("", body)


def test_incident_block_is_escaped():
    msg = va.build_block_alert("kospi", [INCIDENT_BLOCK])
    assert not _bare_markup(msg), f"이스케이프 안 됨: {msg}"
    assert "&lt;" in msg and "&amp;" in msg


def test_prose_html_tags_are_escaped():
    """브리핑 산문은 <b> 강조 태그를 쓴다 — 잘려서 들어오면 파싱이 깨진다."""
    msg = va.build_block_alert("us", ["방향 모순: <b>미국 지수는 좋았지만 선물은"])
    assert "<b>미국" not in msg
    assert "&lt;b&gt;" in msg


def test_btype_stays_bold():
    msg = va.build_block_alert("kospi-close", ["문제"])
    assert "<b>kospi-close</b>" in msg


def test_all_blocks_present():
    msg = va.build_block_alert("kospi", ["첫째 < 문제", "둘째 & 문제"])
    assert "첫째" in msg and "둘째" in msg


def test_send_admin_alert_falls_back_to_plain_on_parse_error():
    """이스케이프를 빠뜨린 미래의 호출부도 알림이 도달해야 한다."""
    calls = []

    class FakeErr(Exception):
        pass

    def fake_urlopen(req, timeout=None):
        calls.append(req.data.decode())
        if len(calls) == 1:
            raise FakeErr("HTTP Error 400: Bad Request")
        return None

    orig = va.urllib.request.urlopen
    va.urllib.request.urlopen = fake_urlopen
    import os
    os.environ["TELEGRAM_BOT_TOKEN"] = "t"
    os.environ["TELEGRAM_ADMIN_CHAT_ID"] = "c"
    try:
        va.send_admin_alert("깨지는 <메시지")
    finally:
        va.urllib.request.urlopen = orig
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_ADMIN_CHAT_ID", None)

    assert len(calls) == 2, f"평문 재시도가 없었다: {calls}"
    assert "parse_mode" in calls[0]
    assert "parse_mode" not in calls[1]
