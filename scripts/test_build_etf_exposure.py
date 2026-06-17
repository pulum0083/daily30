# build_etf_exposure 순수 함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 scripts/test_build_etf_exposure.py"""
import build_etf_exposure as m


def test_parse_kor_won():
    assert m.parse_kor_won("28조 2,132억") == 28 * 10**12 + 2132 * 10**8
    assert m.parse_kor_won("9,800억") == 9800 * 10**8
    assert m.parse_kor_won("1조 921억") == 10**12 + 921 * 10**8
    assert m.parse_kor_won("16조 6,312억") == 16 * 10**12 + 6312 * 10**8
    assert m.parse_kor_won(123456) == 123456
    assert m.parse_kor_won(None) is None
    assert m.parse_kor_won("") is None


def test_classify_badge():
    # high: dov≥8 AND conc≥10
    assert m.classify_badge(20.2, 15.0) == "high"   # 이오테크닉스
    assert m.classify_badge(12.1, 8.5) == "high"    # 한미반도체
    # mid: dov≥4 AND conc≥5
    assert m.classify_badge(5.3, 6.1) == "mid"      # 에코프로비엠
    # AND 결합 — 한쪽만 높으면 탈락 (오탐 방지)
    assert m.classify_badge(10.4, 1.4) is None      # 주성엔지니어링 (거래 활발)
    assert m.classify_badge(2.3, 5.4) is None       # KB금융 (집중도 낮음)
    assert m.classify_badge(16.8, 3.6) is None      # HPSP (거래일수 미달)
    assert m.classify_badge(None, 9.0) is None
    assert m.classify_badge(9.0, None) is None


def test_composite_score():
    assert m.composite_score(21.0, 15.0, 21.0, 15.0) == 100   # 둘 다 최대
    assert m.composite_score(0, 0, 21.0, 15.0) == 0
    half = m.composite_score(10.5, 7.5, 21.0, 15.0)
    assert half == 50
    assert m.composite_score(5.0, 5.0, 0, 10.0) is None       # max_conc=0 가드
    assert m.composite_score(None, 5.0, 21.0, 15.0) is None


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
