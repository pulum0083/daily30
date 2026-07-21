# fetch_earnings_calendar의 날짜 필터·정렬·결손 처리를 네트워크 없이 검증
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch_earnings_calendar as M


class TestIsUpcoming(unittest.TestCase):
    TODAY = "2026-07-21"
    HORIZON = "2026-09-19"

    def ok(self, d):
        return M.is_upcoming(d, self.TODAY, self.HORIZON)

    def test_오늘_일정은_포함(self):
        self.assertTrue(self.ok("2026-07-21"))

    def test_미래_일정은_포함(self):
        self.assertTrue(self.ok("2026-07-30"))

    def test_어제_일정은_제외(self):
        self.assertFalse(self.ok("2026-07-20"))

    def test_지평선_밖_일정은_제외(self):
        self.assertFalse(self.ok("2026-09-20"))

    def test_지평선_경계는_포함(self):
        self.assertTrue(self.ok("2026-09-19"))

    def test_깨진_날짜는_제외(self):
        for bad in ["2026-13-01", "26-07-30", "", "2026/07/30", None, 20260730]:
            self.assertFalse(self.ok(bad), bad)


class TestCollect(unittest.TestCase):
    TODAY = "2026-07-21"
    HORIZON = "2026-09-19"

    def setUp(self):
        self._orig = M.fetch_ir_schedule
        self.addCleanup(lambda: setattr(M, "fetch_ir_schedule", self._orig))

    def stub(self, table):
        def _f(code):
            v = table[code]
            if isinstance(v, Exception):
                raise v
            return v
        M.fetch_ir_schedule = _f

    def test_날짜순으로_정렬된다(self):
        self.stub({
            "1": {"code": "1", "name": "나중", "date": "2026-07-30", "title": "t"},
            "2": {"code": "2", "name": "먼저", "date": "2026-07-23", "title": "t"},
        })
        out = M.collect([{"code": "1", "name": "나중"}, {"code": "2", "name": "먼저"}],
                        self.TODAY, self.HORIZON, sleep=0)
        self.assertEqual([e["name"] for e in out], ["먼저", "나중"])

    def test_같은_날짜는_이름순(self):
        self.stub({
            "1": {"code": "1", "name": "나종목", "date": "2026-07-23", "title": "t"},
            "2": {"code": "2", "name": "가종목", "date": "2026-07-23", "title": "t"},
        })
        out = M.collect([{"code": "1", "name": "나종목"}, {"code": "2", "name": "가종목"}],
                        self.TODAY, self.HORIZON, sleep=0)
        self.assertEqual([e["name"] for e in out], ["가종목", "나종목"])

    def test_일정_없는_종목은_건너뛴다(self):
        self.stub({"1": None, "2": {"code": "2", "name": "있음", "date": "2026-07-23", "title": "t"}})
        out = M.collect([{"code": "1", "name": "없음"}, {"code": "2", "name": "있음"}],
                        self.TODAY, self.HORIZON, sleep=0)
        self.assertEqual([e["code"] for e in out], ["2"])

    def test_한_종목이_실패해도_나머지로_만든다(self):
        self.stub({
            "1": RuntimeError("network"),
            "2": {"code": "2", "name": "생존", "date": "2026-07-23", "title": "t"},
        })
        out = M.collect([{"code": "1", "name": "실패"}, {"code": "2", "name": "생존"}],
                        self.TODAY, self.HORIZON, sleep=0)
        self.assertEqual([e["code"] for e in out], ["2"])

    def test_지난_일정은_버린다(self):
        self.stub({"1": {"code": "1", "name": "옛날", "date": "2026-07-01", "title": "t"}})
        out = M.collect([{"code": "1", "name": "옛날"}], self.TODAY, self.HORIZON, sleep=0)
        self.assertEqual(out, [])

    def test_이름이_비면_유니버스_이름으로_채운다(self):
        self.stub({"1": {"code": "1", "name": "", "date": "2026-07-23", "title": "t"}})
        out = M.collect([{"code": "1", "name": "유니버스이름"}], self.TODAY, self.HORIZON, sleep=0)
        self.assertEqual(out[0]["name"], "유니버스이름")

    def test_dday는_저장하지_않는다(self):
        # §20 — 상대 시간 라벨을 저장하면 이후 계속 틀린다. 렌더 시점 계산이 원칙.
        self.stub({"1": {"code": "1", "name": "종목", "date": "2026-07-23", "title": "t"}})
        out = M.collect([{"code": "1", "name": "종목"}], self.TODAY, self.HORIZON, sleep=0)
        self.assertEqual(set(out[0]), {"code", "name", "date", "title"})


class TestLoadUniverse(unittest.TestCase):
    def test_실제_유니버스를_평면화한다(self):
        stocks = M.load_universe()
        self.assertGreater(len(stocks), 30)
        codes = [s["code"] for s in stocks]
        self.assertEqual(len(codes), len(set(codes)), "중복 코드가 있으면 안 된다")
        self.assertTrue(all(len(c) == 6 and c.isdigit() for c in codes))


if __name__ == "__main__":
    unittest.main(verbosity=2)
