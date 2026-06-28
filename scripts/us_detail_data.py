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


def fetch_us_realdata(ticker):
    """yfinance 일봉 → 시세·등락률·20일 스파크라인·52주·MA20/200. 실패 시 {'error':..,'price':None}.

    등락률은 직전 완료 세션 종가 기준(close[-1] vs close[-2]) — 한국 페이지와 동일 원칙.
    """
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="300d").dropna(subset=["Close"])
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "price": None}
    closes = [float(x) for x in hist["Close"].tolist()]
    if len(closes) < 2:
        return {"error": "데이터 부족", "price": None}
    price = closes[-1]
    hi, lo = m.wk52_high_low(closes)
    ma20 = round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None
    ma200v = m.ma200(closes)
    idx = hist.index
    return {
        "error": None,
        "price": round(price, 2),
        "change_pct": m.change_pct(closes),
        "sparkline": [round(c, 2) for c in m.sparkline(closes, 20)],
        "sparkline_dates": [d.strftime("%-m/%-d") for d in idx[-20:]],
        "week52_low": round(lo, 2),
        "week52_high": round(hi, 2),
        "week52_pos_pct": round((price - lo) / (hi - lo) * 100, 1) if hi > lo else 0,
        "ma20_dist_pct": round((price / ma20 - 1) * 100, 1) if ma20 else None,
        "ma200_dist_pct": round((price / ma200v - 1) * 100, 1) if ma200v else None,
        "asof": idx[-1].strftime("%Y-%m-%d"),
    }


def fetch_us_financials(ticker):
    """yfinance quarterly_financials → parse_us_financials 입력으로 변환 후 파싱. 실패 시 []."""
    try:
        import yfinance as yf
        qf = yf.Ticker(ticker).quarterly_financials
    except Exception as e:  # noqa: BLE001
        print(f"[us_detail] {ticker} 분기실적 실패: {e}", file=sys.stderr)
        return []
    if qf is None or qf.empty:
        return []

    def _cell(field, col):
        try:
            v = qf.loc[field, col]
        except KeyError:
            return None
        return None if v != v else float(v)  # NaN → None

    columns = []
    for col in qf.columns:
        rev = _cell("Total Revenue", col)
        op = _cell("Operating Income", col)
        if op is None:
            op = _cell("Total Operating Income As Reported", col)
        columns.append((col.strftime("%Y-%m-%d"), {"rev": rev, "op": op}))
    return parse_us_financials(columns)
