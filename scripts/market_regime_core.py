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

    NaN은 '없는 데이터'로 취급한다 — None과 달리 비교·산술을 조용히 통과해
    바스켓 평균 전체를 오염시킨다(§0).
    """
    p = prices.get(date)
    if p is not None and p == p:
        return p
    i = bisect_right(sorted_dates, date)
    while i:
        v = prices[sorted_dates[i - 1]]
        if v == v:
            return v
        i -= 1
    return None


def basket_cum(members: list, closes: dict, dates: list) -> tuple[list | None, int]:
    """바스켓의 창 내 누적수익률(%)과 실제 사용된 종목 수.

    창 시작일에 값이 없는 종목은 통째로 제외한다 — 신규 상장 종목을 섞으면
    그 종목의 '상장 이후 수익률'이 6개월 수익률인 척 평균에 들어간다.
    """
    if not dates:
        return None, 0
    series = []
    for t in members:
        prices = closes.get(t) or {}
        if not prices:
            continue
        # 창마다 재정렬한다. 백테스트 전체(바스켓 7개 × 374창)가 0.41초라 하이스팅 이득이 없어
        # 시그니처를 단순하게 유지한다. 창 수가 크게 늘면 호출부에서 정렬본을 넘기는 쪽으로 바꿀 것.
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
