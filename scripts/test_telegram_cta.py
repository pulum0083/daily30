# 텔레그램 메시지를 완결형→유도형으로 바꾼 Phase B 검증 —
# 핵심 시그널 1개 압축 + 브리핑별 사이트 전용 CTA
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc


def test_kospi_headline_and_one_watch_line(tmp_path, monkeypatch):
    # 코스피는 방향·확률(신뢰도) → 헤드라인 → 개장 후 볼 것 한 줄(2026-10-25). 지난 예측 배지·시그널 목록은 없다.
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {
        "prediction": {"direction": "하락 우위", "up_pct": 7, "down_pct": 93, "confidence": 82, "basis": "open"},
        "reason_title": "긴급 점검: 반도체 쇼크",
        "todays_view": {
            "view_title": "어제 <b>-3.52%</b> 맞았는데 또? 메타發 반도체 2차 충격",
            "outlook": [{"tag": "watch", "text": "반도체 갭다운 폭을 <b>얼마나</b> 키울지 지켜보세요."},
                        {"tag": "watch", "text": "기관 매도가 이어질지 보세요."}],
        },
        "telegram_signals": ["📅 오늘 밤 CPI 발표"],
    }
    cc.save_telegram_message("kospi", "2026-10-23", analysis)
    text = (tmp_path / "telegram_message_kospi.txt").read_text(encoding="utf-8")
    assert text.startswith("🇰🇷 코스피 시초가 예측 | 2026.10.23")
    assert "📉 <b>하락 우위 93%</b> (신뢰도 82%)" in text
    assert "🎯 <b>어제 -3.52% 맞았는데 또? 메타發 반도체 2차 충격</b>" in text
    assert "👀 개장 후 볼 것\n반도체 갭다운 폭을 얼마나 키울지 지켜보세요." in text
    assert "기관 매도" not in text          # 개장 후 볼 것은 한 문장만
    assert "지난 예측" not in text and "핵심 시그널" not in text and "CPI" not in text
    assert "🔗 전체 근거·이슈 점검 → " in text and text.rstrip().endswith("/briefings/2026-10-23/kospi/")


def test_kospi_falls_back_to_reason_title_and_skips_empty_outlook(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {"prediction": {"direction": "상승 우위", "up_pct": 63, "down_pct": 37, "confidence": 72},
                "reason_title": "왜 오를까 — 반도체 강세", "todays_view": {}}
    cc.save_telegram_message("kospi", "2026-07-17", analysis)
    text = (tmp_path / "telegram_message_kospi.txt").read_text(encoding="utf-8")
    assert "🇰🇷 코스피 예측 브리핑" in text          # 종가 기준 기록은 '시초가' 라벨을 달지 않는다
    assert "🎯 <b>왜 오를까 — 반도체 강세</b>" in text
    assert "개장 후 볼 것" not in text


def test_close_title_and_one_dek_line(tmp_path, monkeypatch):
    # 마감: 지수 → 🎯 타이틀 → 서브 한 문장(2026-10-25). scenario 형식은 reason_title을 쓴다.
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {"analysis_format": "scenario", "reason_title": "-4%까지 빠졌는데 플러스 마감?",
                "dek": "기관이 <b>8,726억원</b>을 사들였어요.", "telegram_signals": ["🚀 옛 시그널"]}
    md = {"indices": {"kospi": {"price": 5550.3, "change_pct": 0.30},
                      "kosdaq": {"price": 751.69, "change_pct": -1.62}}}
    cc.save_closing_telegram_message("2026-10-23", analysis, md)
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "📊 KOSPI <b>5,550.30</b>  ▲ +0.30%" in text
    assert "🎯 <b>-4%까지 빠졌는데 플러스 마감?</b>\n기관이 8,726억원을 사들였어요." in text
    assert "핵심 시그널" not in text and "옛 시그널" not in text
    assert "🔗 수급·시장폭 상세 →" in text


def test_close_prefers_market_title_and_skips_missing_dek(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    cc.save_closing_telegram_message("2026-07-16", {"market_title": "코스닥 테마 폭발", "reason_title": "다른 제목"},
                                     {"indices": {}})
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert "🎯 <b>코스닥 테마 폭발</b>\n────" in text and "다른 제목" not in text


def test_us_first_issue_and_has_cta(tmp_path, monkeypatch):
    # 미국도 코스피처럼 첫 이슈 하나만 "오늘 밤 볼 것"으로 싣는다(2026-10-25).
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {
        "prediction": {"up_pct": 62, "down_pct": 38},
        "todays_view": {"view_title": "돈이 SW에서 AI 인프라로"},
        "issues": [{"title": "IBM CEO SW 지출 경고"}, {"title": "오늘 밤 CPI 발표"}, {"title": "엔비디아 중국 재개"}],
    }
    cc.save_telegram_message("us", "2026-07-17", analysis)
    text = (tmp_path / "telegram_message_us.txt").read_text(encoding="utf-8")
    assert "IBM CEO SW 지출 경고" in text
    assert "오늘 밤 CPI 발표" not in text   # 오늘 밤 볼 것은 첫 이슈 하나만(2026-10-25)
    assert "🔗 전체 이슈·종목 픽 →" in text
    assert "상세 분석" not in text


def _ma5_item():
    from test_monthly_ma5_render import item
    return item()


def test_kospi_adds_ma5_block_when_page_shows_it(tmp_path, monkeypatch):
    # 월봉 5개월선 종목이 페이지에 보이는 날만 텔레그램에도 싣고, 매매 신호가 아니라는 문장을 함께 붙인다
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {"prediction": {"direction": "하락 우위", "up_pct": 7, "down_pct": 93, "confidence": 82},
                "todays_view": {"view_title": "제목"},
                "monthly_ma5": {"date": "2026-10-26", "items": [_ma5_item()]}}
    cc.save_telegram_message("kospi", "2026-10-26", analysis)
    text = (tmp_path / "telegram_message_kospi.txt").read_text(encoding="utf-8")
    assert "📊 월봉 5개월선 안착 종목\n• 메리츠금융지주 — 3개월째 5개월선 위 (지금 이격 +5.5%)" in text
    assert "매매 신호가 아니에요" in text
    assert text.index("📊 월봉") < text.index("🔗 전체 근거")


def test_kospi_skips_ma5_block_when_no_items_or_no_backtest(tmp_path, monkeypatch):
    import generate_html as gh
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    base = {"prediction": {"direction": "상승 우위", "up_pct": 60, "down_pct": 40, "confidence": 70}}
    cc.save_telegram_message("kospi", "2026-10-26", {**base, "monthly_ma5": {"date": "2026-10-26", "items": []}})
    assert "월봉" not in (tmp_path / "telegram_message_kospi.txt").read_text(encoding="utf-8")
    monkeypatch.setattr(gh, "MA5_BACKTEST_PATH", tmp_path / "none.json")
    cc.save_telegram_message("kospi", "2026-10-26", {**base, "monthly_ma5": {"date": "2026-10-26", "items": [_ma5_item()]}})
    assert "월봉" not in (tmp_path / "telegram_message_kospi.txt").read_text(encoding="utf-8")
