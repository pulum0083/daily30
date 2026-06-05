#!/usr/bin/env python3
# 토스증권 Open API 클라이언트 — 종목 캔들·현재가·환율 조회
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://openapi.tossinvest.com"
BASE_DIR = Path(__file__).resolve().parent.parent

_token_cache = {"token": None, "expires_at": 0.0}


def _load_config() -> dict:
    path = BASE_DIR / "config.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _get_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    cfg = _load_config()
    client_id = os.environ.get("TOSS_CLIENT_ID") or cfg.get("toss", {}).get("client_id", "")
    client_secret = os.environ.get("TOSS_CLIENT_SECRET") or cfg.get("toss", {}).get("client_secret", "")
    if not client_id or not client_secret:
        raise RuntimeError(
            "TOSS_CLIENT_ID / TOSS_CLIENT_SECRET 미설정. "
            "환경변수 또는 config.json toss.client_id·client_secret 에 입력하세요."
        )

    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())

    _token_cache["token"] = result["access_token"]
    _token_cache["expires_at"] = time.time() + result.get("expires_in", 86400)
    return _token_cache["token"]


def _api_get(path: str, params=None) -> dict:
    token = _get_token()
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def get_candles(symbol: str, interval: str = "1d", count: int = 300) -> list:
    """일봉(1d) 또는 1분봉(1m) 캔들 반환. 오래된→최신 순서.

    Toss API는 1회 최대 200개. count > 200이면 nextBefore로 페이지네이션.
    """
    all_candles = []
    before = None
    remaining = count

    while remaining > 0:
        batch = min(remaining, 200)
        params = {"symbol": symbol, "interval": interval, "count": batch}
        if before:
            params["before"] = before
        result = _api_get("/api/v1/candles", params)
        body = result.get("result", result)
        candles = body.get("candles", [])
        if not candles:
            break
        # 응답은 최신→오래된 순이므로 prepend해서 오래된→최신 유지
        all_candles = candles[::-1] + all_candles
        before = body.get("nextBefore")
        remaining -= len(candles)
        if not before:
            break

    return all_candles


def get_prices(symbols: list) -> list:
    """현재가 일괄 조회. 최대 200개."""
    result = _api_get("/api/v1/prices", {"symbols": ",".join(symbols)})
    body = result.get("result", result)
    return body if isinstance(body, list) else body.get("prices", [])


def get_exchange_rate(base: str = "USD", quote: str = "KRW"):
    """환율 조회. USD→KRW midRate 반환."""
    try:
        result = _api_get("/api/v1/exchange-rate", {"baseCurrency": base, "quoteCurrency": quote})
        body = result.get("result", result)
        return float(body["midRate"])
    except Exception:
        return None
