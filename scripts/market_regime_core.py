# 국면(주도주 교체/지속/무주도) 판정 순수 계산. 네트워크·파일 IO 없음 — 백테스트가 같은 코드를 리플레이한다.
from __future__ import annotations

from bisect import bisect_right

WINDOW_DAYS = 126
COOL_THRESHOLD = -15.0   # 정점 대비 이만큼 이하면 '식음'
HIGH_THRESHOLD = -3.0    # 정점 대비 이 이내면 '신고점'
HYST_WINDOW = 5          # 히스테리시스 창(영업일)
HYST_MIN = 3             # 창 안에서 이만큼 이상 충족해야 인정
MIN_RUN = 10             # 이보다 짧은 국면은 직전 국면에 흡수


def _price_at(prices: dict, date: str, sorted_dates: list) -> float | None:
    """date의 종가. 없으면 직전 거래일 종가(한국·미국 캘린더 차이 보정).

    선형 스캔을 쓰면 백테스트가 375창 × 126일 × 19티커 × 500날짜로 폭발한다.
    날짜가 정렬돼 있으므로 이분 탐색으로 찾는다.
    """
    p = prices.get(date)
    if p is not None:
        return p
    i = bisect_right(sorted_dates, date)
    return prices[sorted_dates[i - 1]] if i else None


def basket_cum(members: list, closes: dict, dates: list) -> tuple[list | None, int]:
    """바스켓의 창 내 누적수익률(%)과 실제 사용된 종목 수.

    창 시작일에 값이 없는 종목은 통째로 제외한다 — 신규 상장 종목을 섞으면
    그 종목의 '상장 이후 수익률'이 6개월 수익률인 척 평균에 들어간다.
    """
    series = []
    for t in members:
        prices = closes.get(t) or {}
        if not prices:
            continue
        sd = sorted(prices)
        base = _price_at(prices, dates[0], sd)
        if base is None or base == 0:
            continue
        row = []
        for d in dates:
            p = _price_at(prices, d, sd)
            if p is None:
                row = None
                break
            row.append((p / base - 1) * 100)
        if row is not None:
            series.append(row)
    if not series:
        return None, 0
    cum = [round(sum(s[i] for s in series) / len(series), 4) for i in range(len(dates))]
    return cum, len(series)
