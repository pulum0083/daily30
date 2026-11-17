# 테스트에서 브리핑 생성기 모듈 전체의 같은 이름을 한 번에 바꿔치는 도우미
"""generate_html을 역할별 모듈(html_common·sections_*·site_index …)로 나눈 뒤로는 경로 상수·함수가
여러 모듈에 따로 묶여 있다. monkeypatch.setattr(generate_html, "DATA_DIR", …)는 generate_html 한 곳만
바꾸므로, 옮겨 간 함수가 진짜 data/ · web/ 를 읽거나 쓰게 된다. 이 도우미는 그 이름을 가진 모든
생성기 모듈에서 함께 바꾼다."""
import importlib

GEN_MODULES = ("generate_html", "html_common", "briefing_meta", "sections_shared", "sections_kospi",
               "sections_us", "sections_close", "standalone_pages", "sector_pages", "site_index")


def gen_patch(monkeypatch, name, value):
    hit = False
    for m in GEN_MODULES:
        mod = importlib.import_module(m)
        if name in vars(mod):
            monkeypatch.setattr(mod, name, value)
            hit = True
    assert hit, f"생성기 모듈에 없는 이름: {name}"
