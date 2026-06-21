# 종목 상세 페이지 생성기 테스트
import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "config"


def test_stocks_config_schema():
    stocks = json.loads((CONFIG / "stocks.json").read_text(encoding="utf-8"))
    assert isinstance(stocks, list) and len(stocks) >= 3
    codes = {s["code"] for s in stocks}
    assert {"005930", "000660", "005380"} <= codes
    for s in stocks:
        assert len(s["code"]) == 6
        for key in ("name", "sector", "market", "peers"):
            assert key in s, f"{s['code']} missing {key}"
        assert isinstance(s["peers"], list)
        for p in s["peers"]:
            assert len(p["code"]) == 6 and p["name"], f"{s['code']} bad peer {p}"


def test_stock_section_config():
    cfg = json.loads((CONFIG / "stock.json").read_text(encoding="utf-8"))
    assert cfg["template"] == "stocks/detail.html"
    assert "sections" in cfg and "price_chart" in cfg["sections"]


import scripts.generate_html as gh


def test_build_stock_page_writes_real_price(tmp_path, monkeypatch):
    fake = {"price": 354000.0, "change_pct": -2.34,
            "sparkline": [350000.0, 354000.0], "error": None,
            "week52_low": 53700.0, "week52_high": 374500.0, "week52_pos_pct": 94.0}
    monkeypatch.setattr(gh, "stock_realdata", lambda code: fake)
    monkeypatch.setattr(gh, "WEB_DIR", tmp_path)  # 출력 루트 격리

    stock = {"code": "005930", "name": "삼성전자", "sector": "반도체",
             "market": "KOSPI", "peers": [{"code": "000660", "name": "SK하이닉스"}]}
    out = gh.build_stock_page(stock, [{"code": "000660", "name": "SK하이닉스", "change_pct": 3.42}])

    html = (tmp_path / "stocks" / "005930" / "index.html").read_text(encoding="utf-8")
    assert "354,000" in html
    assert "53,700" in html and "374,500" in html
    assert "SK하이닉스" in html       # peer 링크
    assert "/assets/stocks.css" in html
    assert "{{" not in html  # 미치환 변수 없음
    assert out.endswith("stocks/005930/index.html")


def test_stock_realdata_adds_52w(monkeypatch):
    fake_closes = [100.0 + i for i in range(300)]  # 오래된→최신

    def fake_kospi(code):
        from scripts.validate_analysis import _closes_to_realdata
        return _closes_to_realdata(fake_closes, ndigits=2)

    monkeypatch.setattr(gh, "_fetch_kospi_realdata", fake_kospi)
    # 52주 범위는 캔들 원본에서 산출되므로 캔들 fetch도 모킹
    monkeypatch.setattr(gh, "_fetch_stock_closes", lambda code: fake_closes)

    rd = gh.stock_realdata("005930")
    assert rd["price"] == 399.0
    assert rd["week52_low"] == 100.0
    assert rd["week52_high"] == 399.0
    assert 0 <= rd["week52_pos_pct"] <= 100
    assert rd["error"] is None
