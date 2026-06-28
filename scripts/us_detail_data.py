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


def _yf_q_label(date_str):
    """'2026-04-30' → '26Q2'. 월 기준 분기 라벨. 파싱 실패 시 입력 그대로."""
    try:
        yy = date_str[2:4]
        mm = int(date_str[5:7])
        q = (mm - 1) // 3 + 1
        return f"{yy}Q{q}"
    except (ValueError, IndexError, TypeError):
        return date_str


def parse_us_financials(columns, n=5):
    """yfinance 분기실적 컬럼 → 템플릿용 리스트.

    columns: [(date_str, {'rev':float|None, 'op':float|None}), ...] 최신순.
    반환: 최근 n분기를 오래된→최신으로 [{q, rev, op, est:False}]. 둘 다 None이면 제외.
    """
    out = []
    for date_str, vals in columns[:n]:
        rev, op = vals.get("rev"), vals.get("op")
        if rev is None and op is None:
            continue
        out.append({"q": _yf_q_label(date_str), "rev": rev, "op": op, "est": False})
    out.reverse()
    return out
