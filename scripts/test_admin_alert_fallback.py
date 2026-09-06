# 발행 차단 관리자 알림 회귀 테스트 — 서식 때문에 알림이 사라지지 않는다
#
# 2026-08-24·08-26 코스피 아침 브리핑이 §28 게이트에 걸려 발행이 차단됐는데, 그 사실을
# 알리는 텔레그램이 둘 다 HTTP 400으로 실패했다. 차단 사유에 모델 산문이 그대로 들어가고
# 그 안에 <b> 태그가 잘린 채 섞여 parse_mode=HTML이 거절한 것이다. 결과적으로 "오늘
# 브리핑이 안 나갔다"는 사실을 아무도 모른 채 하루가 지나갔다.
import os
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import validate_analysis as va

ENV = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_ADMIN_CHAT_ID": "c"}


class _Resp:
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _sent(mock_open):
    """호출별 (본문, parse_mode) 목록."""
    out = []
    for call in mock_open.call_args_list:
        from urllib.parse import parse_qs
        q = parse_qs(call.args[0].data.decode())
        out.append((q["text"][0], q.get("parse_mode", [None])[0]))
    return out


class TestAdminAlert(unittest.TestCase):
    def test_HTML이_400이면_평문으로_다시_보낸다(self):
        # 실사고 리플레이 — 잘린 <b> 태그가 섞인 차단 사유
        msg = "🚫 <b>kospi</b> 발행 차단\n• 지수 최상급 주장이 실측과 모순: <b>미국 증시가"
        calls = []

        def fake(req, timeout=None):
            calls.append(req)
            if len(calls) == 1:
                raise HTTPError("u", 400, "Bad Request", None, None)
            return _Resp()

        with mock.patch.dict(os.environ, ENV), \
             mock.patch("urllib.request.urlopen", side_effect=fake) as m:
            va.send_admin_alert(msg)
        self.assertEqual(len(calls), 2, "평문 재시도가 있어야 한다")
        sent = _sent(m)
        self.assertEqual(sent[0][1], "HTML")
        self.assertIsNone(sent[1][1], "재시도는 parse_mode 없이 보낸다")
        self.assertNotIn("<b>", sent[1][0], "재시도 본문에서 태그가 제거돼야 한다")
        self.assertIn("발행 차단", sent[1][0], "핵심 내용은 남아야 한다")

    def test_HTML이_성공하면_한_번만_보낸다(self):
        with mock.patch.dict(os.environ, ENV), \
             mock.patch("urllib.request.urlopen", return_value=_Resp()) as m:
            va.send_admin_alert("🚫 <b>kospi</b> 발행 차단")
        self.assertEqual(m.call_count, 1)

    def test_키가_없으면_보내지_않는다(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("urllib.request.urlopen") as m:
            va.send_admin_alert("x")
        m.assert_not_called()

    def test_두_번_다_실패해도_예외를_올리지_않는다(self):
        # 알림 실패가 원래의 차단 처리를 덮어쓰면 안 된다.
        with mock.patch.dict(os.environ, ENV), \
             mock.patch("urllib.request.urlopen", side_effect=OSError("network")):
            va.send_admin_alert("x")   # 예외가 새어나오면 테스트 실패


class TestBlockMessageEscaping(unittest.TestCase):
    def test_차단_사유의_태그는_이스케이프된다(self):
        # 호출부가 이스케이프하지 않으면 첫 시도가 항상 400이 되어 매번 재시도를 태운다.
        src = Path(va.__file__).read_text(encoding="utf-8")
        self.assertIn('html.escape(str(b))', src)
        self.assertIn('html.escape(btype)', src)


if __name__ == "__main__":
    unittest.main()
