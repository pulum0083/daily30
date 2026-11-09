# 미국 브리핑 RSS 뉴스 수집 보강 테스트 — 발행일 먼저 확인·최신성·주소 날짜·선별 수·결제 오류 알림(2026-11-09, 네트워크 없음)
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_news as fn  # noqa: E402
import news_sources as ns  # noqa: E402

BILLING = ("403 PERMISSION_DENIED. {'error': {'code': 403, 'message': 'Your billing account has an outstanding "
           "balance. Make a payment at https://aistudio.google.com/billing to restore service.'}}")


# ── 주소 날짜 ──

@pytest.mark.parametrize("url,day", [
    ("https://www.bloomberg.com/news/articles/2026-11-08/stock-market-today-dow", "2026-11-08"),
    ("https://www.reuters.com/markets/us/futures-rise-nvidia-slides-2026-11-09/", "2026-11-09"),
    ("https://www.cnbc.com/2026/11/09/stocks-making-the-biggest-moves-premarket.html", "2026-11-09"),
    ("https://biz.chosun.com/stock/stock_general/2026/11/09/MY3DMMDDGQ4", "2026-11-09"),
])
def test_published_from_url(url, day):
    dt = ns.published_from_url(url)
    assert dt.date().isoformat() == day and dt.hour == 12 and dt.tzinfo is not None


@pytest.mark.parametrize("url", [
    "https://www.wsj.com/finance/stocks/stock-futures-treasurys-steady-but-nvidia",
    "https://www.newspim.com/news/view/20261106000826",       # 8자리 연속 숫자는 기사 번호와 구분할 수 없다
    "https://example.com/2026-13-45/x",                       # 날짜가 아니다
    "",
])
def test_published_from_url_none(url):
    assert ns.published_from_url(url) is None


def test_verify_falls_back_to_url_date_when_page_blocked(monkeypatch):
    def blocked(*a, **k):
        raise OSError("HTTP Error 401: HTTP Forbidden")
    monkeypatch.setattr(ns.urllib.request, "urlopen", blocked)
    assert ns.verify_real_published_at("https://www.bloomberg.com/news/articles/2026-11-09/x").date().isoformat() == "2026-11-09"
    assert ns.verify_real_published_at("https://www.wsj.com/finance/stocks/x") is None


# ── 최신성 ──

NOW = fn.KST.localize(datetime(2026, 11, 9, 21, 15))


def test_is_recent_window():
    assert fn._is_recent(NOW - timedelta(hours=29), NOW)
    assert not fn._is_recent(NOW - timedelta(hours=31), NOW)          # 구글이 다시 띄운 옛 기사
    assert fn._is_recent(NOW + timedelta(hours=6), NOW)
    assert not fn._is_recent(NOW + timedelta(hours=13), NOW)
    assert fn._is_recent(datetime(2026, 11, 8, 12, tzinfo=timezone.utc), NOW)      # 어제 날짜 주소(정오 UTC)
    assert not fn._is_recent(datetime(2026, 11, 7, 12, tzinfo=timezone.utc), NOW)  # 그저께
    assert fn._is_recent(datetime(2026, 11, 9, 20, 0), NOW)                        # 시간대 없는 값은 KST로 본다


def test_verify_articles_keeps_only_verified_recent(monkeypatch):
    monkeypatch.setattr(fn, "_is_recent", lambda p, now=None: p.year == 2026 and p.month == 11)
    links = {"a": "https://x.com/a", "b": "https://x.com/b", "c": ""}
    pubs = {"https://x.com/a": datetime(2026, 11, 9, 8, tzinfo=timezone.utc),
            "https://x.com/b": datetime(2026, 6, 25, 8, tzinfo=timezone.utc)}
    monkeypatch.setattr(ns, "resolve_gnews_url", lambda link: links[link])
    monkeypatch.setattr(ns, "verify_real_published_at", lambda url, log_prefix="": pubs.get(url))
    arts = [{"title": "새 기사", "link": "a"}, {"title": "옛 기사", "link": "b"}, {"title": "리졸브 실패", "link": "c"}]
    out = fn._verify_articles(arts, workers=2)
    assert [a["title"] for a in out] == ["새 기사"]
    assert out[0]["verified_url"] == "https://x.com/a"


def test_attach_uses_preverified_without_network(monkeypatch):
    monkeypatch.setattr(ns, "resolve_gnews_url", lambda link: pytest.fail("다시 조회하면 안 된다"))
    pub = datetime(2026, 11, 9, 8, tzinfo=timezone.utc)
    c = {"date": "2026-11-09", "text": "엔비디아 하락 → 반도체 약세", "ticker": "NVDA",
         "article": {"link": "g", "source": "WSJ", "verified_url": "https://www.bloomberg.com/x", "verified_published": pub}}
    out = fn._attach_verified_sources([c])
    assert out[0]["url"] == "https://www.bloomberg.com/x" and out[0]["published_at"] == pub.isoformat()


# ── 선별·검색어 ──

def test_select_prompt_asks_for_more_and_company_news():
    p = fn._RSS_SELECT_PROMPT.format(today="2026-11-09", max_n=fn.RSS_SELECT_MAX, articles="")
    assert "최대 7개" in p and "실적·가이던스" in p
    qs = [q for q, _ in fn._US_RSS_QUERIES]
    assert "premarket movers stocks" in qs and len(qs) == 10


# ── 결제·권한 오류 ──

def test_billing_error_is_not_retried():
    e = Exception(BILLING)
    assert fn._is_billing_error(e) and not fn._is_retryable_error(e)
    assert fn._is_retryable_error(Exception("429 RESOURCE_EXHAUSTED")) and not fn._is_billing_error(Exception("429 RESOURCE_EXHAUSTED"))


def test_main_alerts_on_billing_error_and_writes_empty(monkeypatch, tmp_path):
    sent = []
    import send_telegram
    monkeypatch.setattr(send_telegram, "send_admin_alert", lambda m: sent.append(m))
    monkeypatch.setattr(fn, "DATA_DIR", tmp_path)

    def boom(t):
        raise Exception(BILLING)
    monkeypatch.setattr(fn, "fetch_and_summarize_rss", boom)
    import time
    monkeypatch.setattr(time, "sleep", lambda s: pytest.fail("결제 오류는 기다리지 않는다"))
    monkeypatch.setattr(sys, "argv", ["fetch_news.py", "--type", "us", "--source", "rss"])
    fn.main()
    assert len(sent) == 1 and "미국 브리핑을 뉴스 없이" in sent[0] and "aistudio.google.com/billing" in sent[0]
    assert (tmp_path / "news_summary_us.json").exists()
