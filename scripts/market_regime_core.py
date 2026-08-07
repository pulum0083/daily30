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


def daily_frames(cums: dict) -> list:
    """일자별 {key: {cum, peak, gap, is_cooled, is_high}}.

    peak은 그 시점까지의 러닝 최고다. 창 전체 최고를 쓰면 미래를 보게 된다.

    cums의 각 값은 basket_cum()이 만든, 길이가 같고 NaN이 없는 시계열이어야 한다
    (basket_cum은 _price_at의 NaN 가드 덕에 NaN을 만들지 않는다). 이 계약이 깨지면
    — 길이가 다르거나 NaN이 섞이면 — 조용히 자르거나 통과시키는 대신 즉시 실패한다(§0).
    """
    keys = [k for k, v in cums.items() if v]
    if not keys:
        return []
    n = len(cums[keys[0]])
    for k in keys:
        if len(cums[k]) != n:
            raise ValueError(
                f"daily_frames: 바스켓 '{k}'의 길이({len(cums[k])})가 "
                f"'{keys[0]}'({n})와 다르다 — 같은 dates로 계산된 시계열만 넣을 것.")
        if any(v != v for v in cums[k]):
            raise ValueError(f"daily_frames: 바스켓 '{k}'에 NaN이 섞여 있다.")

    frames = []
    peaks = {k: float("-inf") for k in keys}  # 첫날은 자기 자신이 정점이라 gap=0.0, is_high=True가 항상 성립한다.
    for i in range(n):
        row = {}
        for k in keys:
            v = cums[k][i]
            peaks[k] = max(peaks[k], v)
            # 반올림은 한 번만 한다 — 표시값과 플래그가 서로 다른 정밀도에서 나오면
            # "gap이 -15.0인데 is_cooled가 False"처럼 사람 눈에 모순으로 보인다.
            gap = round(v - peaks[k], 1)
            row[k] = {
                "cum": round(v, 1),
                "peak": round(peaks[k], 1),
                "gap": gap,
                "is_cooled": gap <= COOL_THRESHOLD,
                "is_high": gap >= HIGH_THRESHOLD,
            }
        frames.append(row)
    return frames


def qualifying_sets(frames: list, i: int, allowed: set | None = None) -> tuple[set, set]:
    """i시점에서 '최근 HYST_WINDOW일 중 HYST_MIN일 이상' 조건을 만족한 바스켓 집합.

    히스테리시스를 상태가 아니라 이 입력 집합에 건다. 상태 판정과 문구 생성이
    둘 다 이 반환값만 쓰므로, 상태가 있으면 문구 재료도 반드시 있다.

    i가 범위를 벗어나면(예: i==len(frames), 흔한 off-by-one) 파이썬 슬라이스는
    예외 없이 조용히 잘린 결과를 준다 — i=5(범위 밖)와 i=4(정상 마지막)가 구분 불가능한
    값을 반환해 호출부 버그를 감춘다. daily_frames의 길이·NaN 가드와 같은 이유로 즉시 실패시킨다.
    """
    if not 0 <= i < len(frames):
        raise ValueError(f"qualifying_sets: i={i}가 frames 범위(0~{len(frames)-1})를 벗어났다.")
    lo = max(0, i - HYST_WINDOW + 1)
    window = frames[lo:i + 1]
    need = min(HYST_MIN, len(window))
    cool_n, high_n = {}, {}
    for row in window:
        for k, v in row.items():
            if allowed is not None and k not in allowed:
                continue
            if v["is_cooled"]:
                cool_n[k] = cool_n.get(k, 0) + 1
            if v["is_high"]:
                high_n[k] = high_n.get(k, 0) + 1
    return ({k for k, c in cool_n.items() if c >= need},
            {k for k, c in high_n.items() if c >= need})


def classify(cooled: set, rising: set) -> str:
    """swap = 식은 것과 신고점이 동시에 / lead = 신고점만 / none = 신고점 없음."""
    if cooled and rising:
        return "swap"
    if rising:
        return "lead"
    return "none"


def absorb_short_runs(states: list) -> list:
    """MIN_RUN보다 짧은 구간을 직전 국면에 흡수한다 — 카드가 깜빡이는 것을 막는다.

    첫 구간은 흡수 대상이 아니다(직전이 없다).
    """
    out = list(states)
    i = 0
    while i < len(out):
        j = i
        while j + 1 < len(out) and out[j + 1] == out[i]:
            j += 1
        if (j - i + 1) < MIN_RUN and i > 0:
            fill = out[i - 1]
            for t in range(i, j + 1):
                out[t] = fill
        i = j + 1
    return out


def josa(word: str) -> str:
    """받침에 따라 '으로/로'. 종성이 없거나 ㄹ이면 '로'."""
    ch = word.strip()[-1]
    code = ord(ch)
    if not (0xAC00 <= code <= 0xD7A3):
        return "로"
    jong = (code - 0xAC00) % 28
    return "로" if jong in (0, 8) else "으로"


def headline(state, cooled, rising, cum, gap, names, order):
    """상태별 문구. 재료가 없으면 None — 억지로 만들지 않는다(§0).

    A = cooled 중 gap 오름차순 1개, B = rising 중 cum 내림차순 최대 2개,
    C = rising 중 cum 내림차순 1개. 동점은 order(선언 순서)로 깬다.
    """
    def rank(keys, metric, reverse):
        return sorted(keys, key=lambda k: (-metric[k] if reverse else metric[k],
                                           order.index(k) if k in order else 999))

    for k in cooled | rising:
        if not (names.get(k) or "").strip():
            raise ValueError(f"headline: 바스켓 '{k}'의 이름이 비어있다 — "
                              "설정 파일(regime_baskets.json)의 name 필드를 확인할 것.")

    if state == "none":
        return "뚜렷한 주도주가 없어요"
    if state == "lead":
        if not rising:
            return None
        top = rank(rising, cum, True)[0]
        return f"{names[top]} 주도가 이어지고 있어요"
    if state == "swap":
        if not cooled or not rising:
            return None
        frm = names[rank(cooled, gap, False)[0]]
        tos = [names[k] for k in rank(rising, cum, True)[:2]]
        joined = ", ".join(tos)
        return f"주도주가 {frm}에서 {joined}{josa(joined)} 넘어가는 중이에요"
    return None


def resolve_regimes(frames: list, names: dict, order: list, allowed: set) -> list:
    """일자별 [{state, headline, regime_index}].

    문구는 국면 단위로 한 번 확정한다 — 같은 국면 안에서 문장이 매일 미묘하게
    달라지면 '국면'이라는 개념 자체가 흐려진다. 그 국면에서 재료가 유효한 가장
    최근 값으로 만들어 국면 내내 유지한다.
    """
    raw = []
    for i in range(len(frames)):
        cooled, rising = qualifying_sets(frames, i, allowed)
        raw.append((classify(cooled, rising), cooled, rising))
    states = absorb_short_runs([r[0] for r in raw])

    out = [None] * len(frames)
    i = 0
    regime_index = 0
    while i < len(states):
        j = i
        while j + 1 < len(states) and states[j + 1] == states[i]:
            j += 1
        text = None
        for t in range(j, i - 1, -1):        # 국면 안에서 가장 최근 유효 재료
            _, cooled, rising = raw[t]        # 위 raw 루프에서 이미 구한 값 재사용
            cum = {k: v["cum"] for k, v in frames[t].items()}
            gap = {k: v["gap"] for k, v in frames[t].items()}
            text = headline(states[i], cooled, rising, cum, gap, names, order)
            if text:
                break
        for t in range(i, j + 1):
            out[t] = {"state": states[i], "headline": text, "regime_index": regime_index}
        regime_index += 1
        i = j + 1
    return out
