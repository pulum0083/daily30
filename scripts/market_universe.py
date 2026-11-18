# 시장 데이터 수집 대상 목록 — 섹터 집중 종목·미국 후보·사이드바 티커

from __future__ import annotations


# 섹터 로테이션 대표 종목·ETF (sector_focus 브리핑용 실시간 데이터 수집)
SECTOR_FOCUS_STOCKS = {
    "semicon": {
        "etfs": [("SOX", "^SOX"), ("DRAM", "DRAM")],
        "ko":   [("005930.KS", "삼성전자"), ("000660.KS", "SK하이닉스"), ("042700.KS", "한미반도체")],
    },
    "power": {
        "etfs": [],
        "ko":   [("267260.KS", "HD현대일렉트릭"), ("010120.KS", "LS일렉트릭"), ("298040.KS", "효성중공업")],
    },
    "defense": {
        "etfs": [("ITA", "ITA")],
        "ko":   [("012450.KS", "한화에어로스페이스"), ("079550.KS", "LIG넥스원"), ("064350.KS", "현대로템")],
    },
    "ship": {
        "etfs": [],
        "ko":   [("329180.KS", "HD현대중공업"), ("042660.KS", "한화오션"), ("010140.KS", "삼성중공업")],
    },
    "battery": {
        "etfs": [("LIT", "LIT")],
        "ko":   [("373220.KS", "LG에너지솔루션"), ("247540.KS", "에코프로비엠"), ("006400.KS", "삼성SDI")],
    },
    "auto": {
        "etfs": [],
        "ko":   [("005380.KS", "현대차"), ("000270.KS", "기아"), ("012330.KS", "현대모비스")],
    },
    "bio": {
        "etfs": [("XBI", "XBI")],
        "ko":   [("207940.KS", "삼성바이오로직스"), ("068270.KS", "셀트리온"), ("000100.KS", "유한양행")],
    },
    "finance": {
        "etfs": [],
        "ko":   [("105560.KS", "KB금융"), ("055550.KS", "신한지주"), ("138040.KS", "메리츠금융지주")],
    },
}

# US stock candidates for Kellogg strategy screening
US_CANDIDATES = [
    "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA",
    "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC",
    "JPM", "BAC", "GS", "MS",
    "XOM", "CVX",
]

# Sidebar ticker mapping: key → yfinance ticker
SIDEBAR_TICKERS_KOSPI = {
    "kospi":  "^KS11",
    "kosdaq": "^KQ11",
    "nasdaq": "^IXIC",
    "nq":     "NQ=F",
    "dji":    "^DJI",
    "sox":    "^SOX",
    "oil":    "CL=F",
    "usd":    "USDKRW=X",
    "dxy":    "DX-Y.NYB",
}

SIDEBAR_TICKERS_US = {
    "kospi":  "^KS11",
    "kosdaq": "^KQ11",
    "nasdaq": "^IXIC",
    "nq":     "NQ=F",
    "dji":    "^DJI",
    "sox":    "^SOX",
    "oil":    "CL=F",
    "usd":    "USDKRW=X",
    "dxy":    "DX-Y.NYB",
}


# 코스피 아침이 장 마감 뒤 움직임·실적 후보를 보는 미국 종목(2026-11-18) — 빅테크 AI 투자와 AI 반도체·서버·전력.
# 삼성전자·SK하이닉스 HBM 수요와 직결된다. 바꾸면 prompt_directives._AFTER_HOURS_NAMES도 함께 바꾼다.
BIGTECH_TICKERS = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"]
AI_INFRA_TICKERS = ["MU", "AVGO", "TSM", "AMD", "ORCL", "DELL", "VRT"]
