# 지수 최상급 표현 프롬프트 지시(_index_position_directive) 회귀 테스트
#
# 2026-08-24·2026-08-26 코스피 아침 브리핑이 S&P500을 "사상 최고"로 서술해 §28 게이트에
# 걸려 발행이 통째로 차단된 사고의 1차 방어. 게이트 임계(52주 고점의 99%)와 이 지시의
# 임계가 어긋나면 프롬프트가 허용한 표현을 게이트가 막는 모순이 생기므로 함께 고정한다.
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.call_claude import _index_position_directive


def _verdicts(out):
    """지수별 판정 줄만 뽑는다 — 맺음말에도 '최상급 표현 금지'라는 문구가 들어가므로
    전체 문자열 검색으로는 판정을 확인할 수 없다."""
    return [ln for ln in out.split("\n") if ln.startswith("- ")]


def _idx(price, hi, lo):
    return {"price": price, "high_52w": hi, "low_52w": lo,
            "pct_from_52w_high": round((price - hi) / hi * 100, 2)}


class TestIndexPositionDirective(unittest.TestCase):
    def test_실사고_리플레이_고점_미달이면_금지로_표기한다(self):
        # 2026-08-26 실측: S&P500 7,677 / 52주 고점 7,799 → -1.6%
        out = _index_position_directive({"index_52w": {"S&P500": _idx(7677.0, 7799.0, 5800.0)}})
        (line,) = _verdicts(out)
        self.assertIn("최상급 표현 금지", line)
        self.assertIn("7,799", line)

    def test_52주_고점권이면_최고_표현을_허용한다(self):
        out = _index_position_directive({"index_52w": {"나스닥": _idx(7790.0, 7799.0, 5800.0)}})
        (line,) = _verdicts(out)
        self.assertIn("최고 표현 가능", line)
        self.assertNotIn("금지", line)

    def test_임계는_게이트와_같은_99퍼센트다(self):
        hi = 1000.0
        # 정확히 99%면 허용, 그보다 낮으면 금지 — validate_analysis의 high_52w*0.99와 동일
        self.assertIn("최고 표현 가능", _verdicts(
            _index_position_directive({"index_52w": {"다우": _idx(990.0, hi, 500.0)}}))[0])
        self.assertIn("최상급 표현 금지", _verdicts(
            _index_position_directive({"index_52w": {"다우": _idx(989.0, hi, 500.0)}}))[0])

    def test_저점권이면_최저_표현을_허용한다(self):
        out = _index_position_directive({"index_52w": {"다우": _idx(505.0, 1000.0, 500.0)}})
        self.assertIn("최저 표현 가능", _verdicts(out)[0])

    def test_데이터가_없으면_지시를_넣지_않는다(self):
        # 없는 값을 지어내지 않는다 — 빈 문자열이면 프롬프트에 아무것도 추가되지 않는다(§0)
        self.assertEqual(_index_position_directive({}), "")
        self.assertEqual(_index_position_directive(None), "")
        self.assertEqual(_index_position_directive({"index_52w": {}}), "")

    def test_필드가_불완전한_지수는_건너뛴다(self):
        out = _index_position_directive({"index_52w": {
            "S&P500": _idx(7677.0, 7799.0, 5800.0),
            "나스닥": {"price": 100.0},          # high/low 없음
            "다우": "문자열",                      # dict 아님
        }})
        self.assertEqual(len(_verdicts(out)), 1)
        self.assertIn("S&P500", _verdicts(out)[0])

    def test_여러_지수를_각각_판정한다(self):
        out = _index_position_directive({"index_52w": {
            "S&P500": _idx(7677.0, 7799.0, 5800.0),      # 금지
            "필라델피아 반도체": _idx(7790.0, 7799.0, 4000.0),  # 허용
        }})
        by = {ln.split(":")[0][2:]: ln for ln in _verdicts(out)}
        self.assertIn("최상급 표현 금지", by["S&P500"])
        self.assertIn("최고 표현 가능", by["필라델피아 반도체"])


if __name__ == "__main__":
    unittest.main()
