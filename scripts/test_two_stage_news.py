# 2단계 뉴스 수집(검색 → 정형화) 회귀 테스트
#
# 배경(2026-08-26 실측): "검색해서 JSON으로 내라"를 한 번에 시키면 gemini-2.5-flash-lite가
# 검색을 아예 하지 않는다(web_search_queries 0건, 2회 반복 동일). 출력 형식 압박을 걷어낸
# 1단계에서만 출처가 붙는다(3개 타입 × 2회 전부 4~17건). 그래서 검색과 정형화를 나눴다.
#
# 이 테스트가 지키는 것
#  - 출처 판정은 반드시 **1단계** 응답으로 한다. 2단계는 도구가 없어 항상 0건이므로
#    측정 지점이 밀리면 매일 100% 폐기로 되돌아간다.
#  - 2단계에는 검색 도구를 주지 않는다(근거는 1단계가 전부여야 한다).
#  - 1단계가 빈손이면 정형화하지 않고 뉴스 없이 발행한다(§27).
import sys
import types as pytypes
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn


class _Chunk:
    def __init__(self, title): self.web = pytypes.SimpleNamespace(title=title, uri="https://redirect/x")


class _Resp:
    def __init__(self, text, chunks=None, has_gm=True):
        self.text = text
        gm = pytypes.SimpleNamespace(grounding_chunks=[_Chunk(t) for t in (chunks or [])]) if has_gm else None
        self.candidates = [pytypes.SimpleNamespace(grounding_metadata=gm, finish_reason="STOP")]


class _FakeTypes:
    """google.genai.types 스텁 — config에 무엇이 실렸는지만 관찰한다."""
    @staticmethod
    def GenerateContentConfig(**kw): return kw
    @staticmethod
    def Tool(**kw): return ("TOOL", kw)
    @staticmethod
    def GoogleSearch(): return "GOOGLE_SEARCH"


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    @property
    def models(self): return self

    def generate_content(self, model=None, contents=None, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return self._responses.pop(0)


class TestSearchStage(unittest.TestCase):
    def test_1단계는_검색_도구를_받는다(self):
        c = _FakeClient([_Resp("산문 근거", ["mt.co.kr", "newspim.com"])])
        text, chunks, sources = fn._search_stage(c, _FakeTypes, "원래 지침")
        self.assertEqual(text, "산문 근거")
        self.assertEqual(chunks, 2)
        self.assertEqual(sources, ["mt.co.kr", "newspim.com"])
        self.assertIn("tools", c.calls[0]["config"])

    def test_1단계_프롬프트는_출력형식_지시를_무시하라고_말한다(self):
        # 이 문구가 작동 요인이다 — "검색하라"는 지시만으론 0건이었다(실측).
        c = _FakeClient([_Resp("x", ["a"])])
        fn._search_stage(c, _FakeTypes, "원래 지침")
        sent = c.calls[0]["contents"]
        self.assertIn("전부 무시", sent)
        self.assertIn("google_search", sent)
        self.assertTrue(sent.endswith("원래 지침"), "원래 지침이 뒤에 그대로 붙어야 한다")

    def test_출처가_없으면_0건으로_센다(self):
        c = _FakeClient([_Resp("x", [])])
        self.assertEqual(fn._search_stage(c, _FakeTypes, "p")[1], 0)

    def test_grounding_metadata가_없으면_0건이다(self):
        c = _FakeClient([_Resp("x", has_gm=False)])
        self.assertEqual(fn._search_stage(c, _FakeTypes, "p")[1], 0)

    def test_출처_매체명은_중복을_제거한다(self):
        c = _FakeClient([_Resp("x", ["mt.co.kr", "mt.co.kr", "daum.net"])])
        self.assertEqual(fn._search_stage(c, _FakeTypes, "p")[2], ["mt.co.kr", "daum.net"])


class TestStructureStage(unittest.TestCase):
    def test_2단계에는_검색_도구를_주지_않는다(self):
        # 도구가 남아 있으면 정형화 중 새로 검색해, 1단계에서 잰 출처 수와 본문이
        # 서로 다른 것을 가리키게 된다.
        c = _FakeClient([_Resp('{"headlines":[]}')])
        fn._structure_stage(c, _FakeTypes, "지침", "근거 텍스트")
        self.assertNotIn("tools", c.calls[0]["config"])

    def test_1단계_근거를_프롬프트에_싣는다(self):
        c = _FakeClient([_Resp('{"headlines":[]}')])
        fn._structure_stage(c, _FakeTypes, "지침", "코스피 8월 26일 외국인 순매도")
        sent = c.calls[0]["contents"]
        self.assertIn("코스피 8월 26일 외국인 순매도", sent)
        self.assertIn("검색 결과에 없는 내용을 추가", sent)

    def test_빈_응답이면_예외를_올린다(self):
        # main의 재시도 루프가 잡는다 — 조용히 빈 dict를 돌려주면 안 된다.
        c = _FakeClient([_Resp("")])
        with self.assertRaises(RuntimeError):
            fn._structure_stage(c, _FakeTypes, "지침", "근거")


class TestSourceExtraction(unittest.TestCase):
    def test_URI는_저장하지_않는다(self):
        # grounding uri는 만료되는 임시 리다이렉트다 — 저장하면 깨진 링크가 된다(§11).
        srcs = fn._grounding_sources(_Resp("x", ["mt.co.kr"]))
        self.assertEqual(srcs, ["mt.co.kr"])
        self.assertNotIn("redirect", "".join(srcs))

    def test_망가진_응답에도_예외를_내지_않는다(self):
        self.assertEqual(fn._grounding_sources(object()), [])


class TestGatingWiring(unittest.TestCase):
    def test_출처_0건은_단독_폐기_사유다(self):
        # 기존 §31 계약이 그대로 유지되는지 확인 — 2단계로 바꿔도 완화되지 않는다.
        self.assertTrue(fn._is_grounding_failure({"headlines": ["x"]}, None, 0))
        self.assertFalse(fn._is_grounding_failure(
            {"headlines": ["x"], "catalysts": [{"text": "x", "date": "2026-08-26"}]}, None, 5))

    def test_판정은_1단계_측정치를_쓴다(self):
        # 소스에서 직접 확인 — 2단계 응답으로 재면 항상 0이라 매일 폐기된다.
        src = Path(fn.__file__).read_text(encoding="utf-8")
        self.assertIn("evidence, _gchunks, _sources = _search_stage(", src)
        self.assertNotIn("_gchunks = _count_grounding_chunks(response)", src)


if __name__ == "__main__":
    unittest.main()
