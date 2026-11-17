# 원/달러 환율 수집 — 네이버 우선, 실패 시 공개 환율 API로 대신하고 등락은 같은 기준으로 계산

from __future__ import annotations
import json
import sys
import urllib.request


def _fx_change(price: float, prev: float | None) -> dict:
    """전일 종가가 있을 때만 등락률을 만든다.

    prev가 없으면 change_pct를 0.0으로 채우지 않고 None으로 둔다 — 0.0은 '모름'이
    아니라 '보합'이라는 틀린 주장이라, 수집 실패가 화면에서 정상 데이터로 보인다
    (운영 규칙 §0 ②: 데이터가 없으면 비운다, 절대 지어내지 않는다).
    """
    if prev is None or prev == 0:
        return {"price": round(price, 2), "change_pct": None, "change_abs": None}
    return {
        "price": round(price, 2),
        "change_pct": round((price - prev) / prev * 100, 2),
        "change_abs": round(price - prev, 2),
    }


def _fx_from_naver_rows(rows: list) -> dict:
    """네이버 모바일 marketIndex 일별 종가 목록 → 견적.

    등락률을 실측 전일 종가로 만들 수 있는 유일한 소스라 1순위다.
    """
    if not rows:
        return {}
    def _close(r):
        return float(str(r["closePrice"]).replace(",", ""))
    price = _close(rows[0])
    prev = _close(rows[1]) if len(rows) >= 2 else None
    return _fx_change(price, prev)


def _fx_from_manana(rows: list) -> dict:
    """manana.kr 응답 → 견적. 현재 응답은 보통 1건이라 등락률이 안 나온다(None)."""
    if not rows or not isinstance(rows, list) or not rows[0].get("rate"):
        return {}
    price = float(rows[0]["rate"])
    prev = float(rows[1]["rate"]) if len(rows) >= 2 and rows[1].get("rate") else None
    return _fx_change(price, prev)


def _fx_from_fawazahmed0(data: dict) -> dict:
    """fawazahmed0 CDN 응답 → 견적. 현재가만 주므로 등락률은 None."""
    rate = (data.get("usd") or {}).get("krw")
    return _fx_from_price_only(float(rate)) if rate else {}


def _fx_from_price_only(price: float) -> dict:
    """현재가만 아는 소스(토스 /exchange-rate 등) → 등락률 없는 견적.

    토스는 midRate만 주고 전일 종가가 없어 등락률을 만들 수 없다.
    """
    return _fx_change(price, None)


def fetch_naver_usdkrw() -> dict:
    """USD/KRW 현재가·전일 대비 등락률. `change_pct`는 모를 때 None이다.

    소스 순서는 '등락률을 실측으로 만들 수 있는가'로 정한다. 가격만 주는 소스를
    앞에 두면 등락률이 영원히 비고(또는 예전처럼 0.0으로 조작되고), 실제로 등락률을
    계산하는 뒤쪽 소스는 한 번도 실행되지 않는 죽은 폴백이 된다(§26).
    1차: 네이버 모바일 (일별 종가 → 실측 등락률)
    2차: manana.kr (행이 2건 이상일 때만 등락률)
    3차: fawazahmed0 CDN (가격만)
    4차: 토스 Open API (가격만)
    실패 시 빈 dict 반환 → 호출부에서 yfinance 폴백 처리.
    """
    def _fetch_json(url, timeout):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    # 1차: 네이버 모바일 API — 등락률까지 실측으로 나오는 유일한 소스
    try:
        payload = _fetch_json(
            "https://m.stock.naver.com/front-api/marketIndex/prices"
            "?reutersCode=FX_USDKRW&category=exchange&pageSize=10&page=1", 10)
        q = _fx_from_naver_rows(payload.get("result") or [])
        if q.get("change_pct") is not None:
            return q
    except Exception as e:
        print(f"[fetch_data] naver USDKRW failed: {e}", file=sys.stderr)

    # 2차: manana.kr
    try:
        q = _fx_from_manana(_fetch_json("https://api.manana.kr/exchange/rate/KRW/USD.json", 8))
        if q.get("change_pct") is not None:
            return q
    except Exception as e:
        print(f"[fetch_data] manana.kr USDKRW failed: {e}", file=sys.stderr)

    # 3차·4차: 가격만 아는 소스. 등락률 없이 가격만 싣는다(표시 쪽에서 등락 셀을 생략).
    try:
        q = _fx_from_fawazahmed0(_fetch_json(
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest"
            "/v1/currencies/usd.json", 8))
        if q.get("price"):
            print("[fetch_data] USDKRW: 등락률 소스 실패 → 가격만 사용(fawazahmed0)", file=sys.stderr)
            return q
    except Exception as e:
        print(f"[fetch_data] fawazahmed0 USDKRW failed: {e}", file=sys.stderr)

    try:
        try:
            import scripts.toss_client as tc
        except ImportError:
            import toss_client as tc
        price = tc.get_exchange_rate("USD", "KRW")
        if price:
            print("[fetch_data] USDKRW: 등락률 소스 실패 → 가격만 사용(toss)", file=sys.stderr)
            return _fx_from_price_only(price)
    except Exception as e:
        print(f"[fetch_data] Toss USDKRW failed: {e}", file=sys.stderr)

    return {}
