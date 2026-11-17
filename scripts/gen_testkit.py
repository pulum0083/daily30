# 테스트에서 역할별로 나눈 모듈 묶음 전체의 같은 이름을 한 번에 바꿔치는 도우미
"""generate_html·validate_analysis를 역할별 모듈로 나눈 뒤로는 경로 상수·조회 함수가 여러 모듈에 따로
묶여 있다. monkeypatch.setattr(generate_html, "DATA_DIR", …)는 그 모듈 한 곳만 바꾸므로, 옮겨 간 함수가
진짜 data/ · web/ 를 읽거나 진짜 시세를 조회하게 된다. 이 도우미는 그 이름을 가진 묶음 안의 모든
모듈에서 함께 바꾼다."""
import importlib

GEN_MODULES = ("generate_html", "html_common", "briefing_meta", "sections_shared", "sections_kospi",
               "sections_us", "sections_close", "standalone_pages", "sector_pages", "site_index")
GATE_MODULES = ("validate_analysis", "gate_text", "gate_realdata", "gate_prose", "gate_superlative",
                "gate_events", "gate_close", "gate_format")


def _patch(monkeypatch, modules, name, value):
    hit = False
    for m in modules:
        mod = importlib.import_module(m)
        if name in vars(mod):
            monkeypatch.setattr(mod, name, value)
            hit = True
    assert hit, f"모듈 묶음에 없는 이름: {name}"


def gen_patch(monkeypatch, name, value):
    """브리핑 생성기(generate_html과 나눈 모듈)."""
    _patch(monkeypatch, GEN_MODULES, name, value)


def gate_patch(monkeypatch, name, value):
    """발행 게이트(validate_analysis와 나눈 모듈)."""
    _patch(monkeypatch, GATE_MODULES, name, value)
