# 종목 상세 히어로의 야간 추정가 스트립 렌더 조건 회귀 테스트 (네트워크 없이 템플릿만 렌더)
"""하이퍼리퀴드에 상장된 3종목에만 스트립이 나가야 한다. 나머지 43종목에 빈 컨테이너가 나가면
'곧 생길 기능'처럼 보이고, JS가 채우지 못해 영구히 빈 자리로 남는다(운영 규칙 0 — 섹션 생략).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as g  # noqa: E402

_RD = {
    "price": 259000, "change_pct": 6.15, "min": 60400,
    "sparkline": [244000, 259000], "sparkline_dates": ["7/20", "7/21"],
    "ma20_dist_pct": -5.0, "ma200_dist_pct": 31.2,
    "week52_high": 362500, "week52_low": 60400, "week52_pos_pct": 60.9,
}


def _render(code):
    stock = {"code": code, "name": "테스트종목", "sector": "반도체",
             "sector_key": "semicon", "market": "KOSPI"}
    ctx = {
        "stock": stock, "rd": _RD, "peers": [], "generated_label": "07-21 종가",
        "chips_ticker": "", "bellwether": None, "foreign_rate": None,
        "foreign_spark": None, "supply5": None, "financials": None,
        "picks": [], "broker_targets": None, "acc": None, "today_str": "2026-07-21",
        "hl_night": code in g.HL_NIGHT_CODES,
    }
    ctx.update(g._stock_seo(stock, ctx))
    return g.make_env().get_template("stocks/detail.html").render(**ctx)


@pytest.mark.parametrize("code", sorted(g.HL_NIGHT_CODES))
def test_hl_codes_get_night_strip(code):
    html = _render(code)
    assert 'id="night-px"' in html
    assert f'data-code="{code}"' in html
    # 등락률을 종가 대비로 계산하려면 실측 종가가 마크업에 실려야 한다
    assert 'data-close="259000"' in html
    assert "실제 체결가 아님" in html, "참고값 고지 문구 누락"


def test_non_hl_code_has_no_night_strip():
    assert 'id="night-px"' not in _render("035420")   # NAVER — HL 미상장


def test_hl_codes_mirror_api_symbol_map():
    """api/hl-night.mjs의 SYM2CODE와 어긋나면 화면과 데이터가 갈라진다."""
    src = (Path(__file__).resolve().parent.parent / "api" / "hl-night.mjs").read_text(encoding="utf-8")
    line = [l for l in src.splitlines() if l.startswith("const SYM2CODE")][0]
    codes = set(__import__("re").findall(r"'(\d{6})'", line))
    assert codes == g.HL_NIGHT_CODES, f"api/hl-night.mjs={codes} vs generate_html={g.HL_NIGHT_CODES}"


def test_night_strip_hidden_by_default():
    """값을 받기 전엔 보이면 안 된다 — 빈 배지가 먼저 뜨는 것을 막는다."""
    html = _render("005930")
    strip = html.split('id="night-px"')[1].split(">")[0]
    assert "display:none" in strip
