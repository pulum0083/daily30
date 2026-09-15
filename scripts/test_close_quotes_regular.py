# 마감 잡 시총 상위 10·AI 반도체 국내 종목 회귀 테스트 — 16:25에 애프터장 가격 대신 공식 종가를 쓰는지(§48)
import importlib
import io
import json
import sys
import types
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_closing_kospi as fc  # noqa: E402

KST = fc.KST
# 2026-09-15 16:04 marketValue 실응답(요약) — 애프터장 가격. 공식 종가는 삼성전자 248,500·-0.20%, SK하이닉스 1,690,000·-0.41%.
MARKET_VALUE = {"stocks": [
    {"itemCode": "005930", "stockName": "삼성전자", "closePrice": "248,500", "fluctuationsRatio": "-0.20",
     "compareToPreviousPrice": {"code": "5"}},
    {"itemCode": "000660", "stockName": "SK하이닉스", "closePrice": "1,687,000", "fluctuationsRatio": "-0.59",
     "compareToPreviousPrice": {"code": "5"}},
    {"itemCode": "402340", "stockName": "SK스퀘어", "closePrice": "1,000,000", "fluctuationsRatio": "0.10",
     "compareToPreviousPrice": {"code": "2"}},
]}
QUOTES = {"005930": {"close": 248500.0, "change_pct": -0.2, "volume": 11081515},
          "000660": {"close": 1690000.0, "change_pct": -0.41, "volume": 2547696}}


@pytest.fixture
def official(monkeypatch):
    calls = []

    def fake(code, now=None, fetch=None):
        calls.append(code)
        return QUOTES.get(code)
    for name in ("kr_official_closes", "scripts.kr_official_closes"):
        try:
            monkeypatch.setattr(importlib.import_module(name), "official_today", fake)
        except ImportError:
            pass
    return calls


def _serve(monkeypatch, body):
    monkeypatch.setattr(fc.urllib.request, "urlopen",
                        lambda req, timeout=None: io.BytesIO(json.dumps(body).encode()))


def test_top10_after_close_uses_official_close(monkeypatch, official):
    _serve(monkeypatch, MARKET_VALUE)
    rows = fc.fetch_kospi200_top10(now=datetime(2026, 9, 15, 16, 25, tzinfo=KST))
    assert [(r["name"], r["price"], r["change_pct"]) for r in rows] == [
        ("삼성전자", "248,500", "▼ -0.20%"),
        ("SK하이닉스", "1,690,000", "▼ -0.41%"),      # 목록의 1,687,000·-0.59%가 아니다
    ]                                               # 공식 종가를 못 구한 SK스퀘어는 뺀다


def test_top10_intraday_keeps_list_price(monkeypatch, official):
    _serve(monkeypatch, MARKET_VALUE)
    rows = fc.fetch_kospi200_top10(now=datetime(2026, 9, 15, 14, 0, tzinfo=KST))
    assert rows[1]["price"] == "1,687,000" and len(rows) == 3
    assert official == []


def test_ai_semicon_after_close_does_not_use_pykrx(monkeypatch, official):
    fake_pykrx = types.ModuleType("pykrx")

    class _Stock:
        @staticmethod
        def get_market_ohlcv(*a, **k):
            raise AssertionError("정규장 밖 pykrx 일봉은 애프터장 가격이라 부르면 안 된다")
    fake_pykrx.stock = _Stock
    monkeypatch.setitem(sys.modules, "pykrx", fake_pykrx)
    monkeypatch.setattr(fc, "_yf_history", lambda *a, **k: None)

    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 15, 16, 25, tzinfo=KST)
    monkeypatch.setattr(fc, "datetime", _Now)
    rows = fc.fetch_ai_semicon_stocks()
    assert [(r["name"], r["price"], r["chg_pct"]) for r in rows] == [
        ("삼성전자", "248,500", "▼ 0.20%"),
        ("SK하이닉스", "1,690,000", "▼ 0.41%"),
    ]
