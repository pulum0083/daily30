# google_search 도구를 쓰는 Gemini 호출이 v1beta API를 명시하는지 지키는 회귀 테스트
#
# 배경(2026-11-13 발견): google-genai 3.0.0(2026-11-06 러너에 처음 설치)이 Gemini Developer API의
# 기본 버전을 v1beta → v1로 바꿨다. v1은 google_search 도구를 받지 않아
# "Search as tool is not enabled for api version v1"(400)로 실패한다. requirements.txt가
# google-genai>=1.0.0이라 업그레이드가 그대로 들어왔고, fetch_news는 이를 일시 장애로 보고
# 뉴스 없이 발행해 코스피 아침·마감 브리핑이 11/6부터 뉴스 없이 나갔다.
#
# 그래서 검색 도구를 쓰는 파일의 genai.Client는 api_version="v1beta"를 직접 넘겨야 한다.
# 라이브러리 기본값에 기대지 않는다.
import re
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def _client_calls(src: str) -> list[str]:
    """genai.Client( ... ) 호출의 괄호 안 문자열을 돌려준다(중첩 괄호 포함)."""
    out = []
    for m in re.finditer(r"genai\.Client\(", src):
        i, depth = m.end(), 1
        while depth and i < len(src):
            depth += {"(": 1, ")": -1}.get(src[i], 0)
            i += 1
        out.append(src[m.end():i - 1])
    return out


class TestSearchClientsUseV1beta(unittest.TestCase):
    def test_검색_도구를_쓰는_파일의_Client는_v1beta를_명시한다(self):
        files = [p for p in SCRIPTS.glob("*.py")
                 if not p.name.startswith("test_") and "GoogleSearch(" in p.read_text(encoding="utf-8")]
        self.assertTrue(files, "google_search를 쓰는 스크립트를 찾지 못했다")
        for p in files:
            calls = _client_calls(p.read_text(encoding="utf-8"))
            self.assertTrue(calls, f"{p.name}: genai.Client 호출이 없다")
            for args in calls:
                self.assertRegex(args, r"api_version\s*=\s*['\"]v1beta['\"]",
                                 f"{p.name}: genai.Client({args})에 api_version='v1beta'가 없다")


if __name__ == "__main__":
    unittest.main()
