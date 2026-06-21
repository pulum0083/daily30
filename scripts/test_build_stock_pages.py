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


def test_stock_section_config():
    cfg = json.loads((CONFIG / "stock.json").read_text(encoding="utf-8"))
    assert cfg["template"] == "stocks/detail.html"
    assert "sections" in cfg and "price_chart" in cfg["sections"]
