# 세션 pin(DS_PIN_SESSION_DATE) 회귀 테스트 — 장 시작 후 재생성 시 당일 값 혼입 차단
#
# 코스피 아침 브리핑은 07:25 KST에 나가고 그때 한국·아시아 시장은 닫혀 있다.
# 09시 이후 수동 재생성하면 같은 코드가 당일 진행 중인(미완성) 일봉을 최신값으로 잡아,
# "직전 종가 대비 예측"이어야 할 자리에 오늘 장중 값이 들어간다(§0·§26).
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import fetch_data as fd
from scripts import validate_analysis as va


class TestPinTargeting(unittest.TestCase):
    def test_pin이_없으면_아무것도_바꾸지_않는다(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DS_PIN_SESSION_DATE", None)
            for t in ("005930.KS", "^KS11", "^GSPC"):
                self.assertIsNone(fd._pin_date_for(t))
            self.assertIsNone(va._pin_session_date())

    def test_한국_아시아_티커에만_적용된다(self):
        with mock.patch.dict(os.environ, {"DS_PIN_SESSION_DATE": "2026-08-26"}):
            for t in ("005930.KS", "000660.KQ", "^KS11", "^KQ11",
                      "^N225", "^HSI", "^TWII", "000001.SS"):
                self.assertEqual(fd._pin_date_for(t), date(2026, 8, 26), t)
            # 미국·선물·환율은 07:25 KST에도 이미 열려 있었으므로 되돌리지 않는다.
            for t in ("^GSPC", "^IXIC", "NQ=F", "ES=F", "CL=F", "USDKRW=X", "AAPL", "EWY"):
                self.assertIsNone(fd._pin_date_for(t), t)

    def test_형식이_틀리면_무시하고_계속한다(self):
        # 오타 하나로 브리핑 생성이 죽으면 안 된다 — 경고만 남기고 평소대로 동작한다.
        with mock.patch.dict(os.environ, {"DS_PIN_SESSION_DATE": "2026/08/26"}):
            self.assertIsNone(fd._pin_date_for("005930.KS"))
            self.assertIsNone(va._pin_session_date())


class TestPinTruncation(unittest.TestCase):
    def _rows(self):
        return [
            {"timestamp": "2026-08-24T00:00:00.000+09:00", "closePrice": "256000"},
            {"timestamp": "2026-08-25T00:00:00.000+09:00", "closePrice": "261000"},
            {"timestamp": "2026-08-26T00:00:00.000+09:00", "closePrice": "259000"},  # 당일 미완성
        ]

    def test_토스_당일_캔들을_잘라낸다(self):
        with mock.patch.dict(os.environ, {"DS_PIN_SESSION_DATE": "2026-08-26"}):
            kept = va._drop_rows_at_pin(self._rows(), va._toss_candle_date)
        self.assertEqual([r["closePrice"] for r in kept], ["256000", "261000"])

    def test_네이버_당일_행을_잘라낸다(self):
        rows = [{"localDate": "20260825", "closePrice": 257000.0},
                {"localDate": "20260826", "closePrice": 259500.0}]
        with mock.patch.dict(os.environ, {"DS_PIN_SESSION_DATE": "2026-08-26"}):
            kept = va._drop_rows_at_pin(rows, va._naver_row_date)
        self.assertEqual([r["closePrice"] for r in kept], [257000.0])

    def test_pin이_없으면_전부_남긴다(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DS_PIN_SESSION_DATE", None)
            self.assertEqual(len(va._drop_rows_at_pin(self._rows(), va._toss_candle_date)), 3)

    def test_날짜를_못_읽는_행은_버리지_않는다(self):
        # 파싱 실패를 '오늘'로 단정해 버리면 정상 과거 캔들이 통째로 사라진다(fail-open).
        rows = [{"timestamp": "깨진값", "closePrice": "1"},
                {"timestamp": "2026-08-26T00:00:00.000+09:00", "closePrice": "2"}]
        with mock.patch.dict(os.environ, {"DS_PIN_SESSION_DATE": "2026-08-26"}):
            kept = va._drop_rows_at_pin(rows, va._toss_candle_date)
        self.assertEqual([r["closePrice"] for r in kept], ["1"])


if __name__ == "__main__":
    unittest.main()
