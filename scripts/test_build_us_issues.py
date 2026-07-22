# build_us_issues(코스피 아침 '간밤 미국 시장 이슈') 필터링 테스트.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as g


def test_keeps_real_issues():
    a = {"us_issues": [
        {"title": "간밤 미 반도체지수 강세", "body": "SOX가 올라 국내 반도체 갭업 기대예요."},
        {"title": "국제 유가 하락", "body": "WTI가 밀리며 정유·화학 원가 부담이 완화돼요."},
    ]}
    out = g.build_us_issues(a)["us_issues"]
    assert len(out) == 2
    assert out[0]["title"] == "간밤 미 반도체지수 강세"


def test_drops_placeholder_no_news():
    # Gemini가 '검색 결과 없음'을 문장으로 반환한 미검색 placeholder는 이슈가 아니므로 제외
    a = {"us_issues": [
        {"title": "AI 모델 이슈", "body": "관련 뉴스는 검색 결과에서 확인되지 않았습니다."},
        {"title": "SK ADR 반응", "body": "구체적인 반응은 확인되지 않았습니다."},
        {"title": "간밤 미 반도체지수 강세", "body": "SOX가 올랐어요."},
    ]}
    out = g.build_us_issues(a)["us_issues"]
    assert len(out) == 1
    assert out[0]["title"] == "간밤 미 반도체지수 강세"


def test_caps_at_two():
    # 실측 이슈가 3개 이상이어도 최대 2개만 노출
    a = {"us_issues": [
        {"title": "이슈1", "body": "본문1"},
        {"title": "이슈2", "body": "본문2"},
        {"title": "이슈3", "body": "본문3"},
    ]}
    out = g.build_us_issues(a)["us_issues"]
    assert len(out) == 2
    assert [o["title"] for o in out] == ["이슈1", "이슈2"]


def test_drops_title_less():
    a = {"us_issues": [
        {"title": "", "body": "제목 없는 항목"},
        {"title": "  ", "body": "공백 제목"},
        {"title": "국제 유가 하락", "body": "WTI 하락."},
    ]}
    out = g.build_us_issues(a)["us_issues"]
    assert len(out) == 1


def test_empty_and_missing():
    assert g.build_us_issues({"us_issues": []})["us_issues"] == []
    assert g.build_us_issues({})["us_issues"] == []
    # 비-dict 항목은 안전하게 무시
    assert g.build_us_issues({"us_issues": ["문자열", None]})["us_issues"] == []


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for fn in fns:
        try:
            fn(); print(f"  ✓ {fn.__name__}"); passed += 1
        except Exception:
            print(f"  ✗ {fn.__name__}"); traceback.print_exc(); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
