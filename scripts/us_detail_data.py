# 미국 종목 상세 페이지용 yfinance 실측 + 순수 포맷 헬퍼
"""미국 반도체 종목(AVGO·NVDA·AMD·MU·ASML·SOXX·SMH) 상세 페이지 데이터.

순수함수(fmt_usd·_yf_q_label·parse_us_financials)는 네트워크 없이 테스트 가능.
시세·52주·MA 계산은 build_stocks_snapshot 의 검증된 순수함수를 재사용한다.
"""
import sys

import build_stocks_snapshot as m


def fmt_usd(v):
    """USD 실수 → '$81.6B'/'$1.23B'/'$543M'/'−$1.2B'. None→''."""
    if v is None:
        return ""
    sign = "−" if v < 0 else ""
    a = abs(v)
    if a >= 1e9:
        return f"{sign}${a/1e9:.1f}B" if a / 1e9 >= 10 else f"{sign}${a/1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a/1e6:.0f}M"
    return f"{sign}${a:,.0f}"
