# 텔레그램 메시지를 완결형→유도형으로 바꾼 Phase B 검증 —
# 핵심 시그널 1개 압축 + 브리핑별 사이트 전용 CTA
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc


def test_kospi_compresses_to_one_signal_and_has_cta(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {
        "prediction": {"direction": "상승 우위", "up_pct": 63, "down_pct": 37, "confidence": 72},
        "reason_title": "왜 오를까 — 반도체 강세",
        "telegram_signals": ["📅 오늘 밤 CPI 발표", "💡 DRAM ETF +7% 급등", "📰 반도체 규제 뉴스"],
    }
    cc.save_telegram_message("kospi", "2026-07-17", analysis)
    text = (tmp_path / "telegram_message_kospi.txt").read_text(encoding="utf-8")
    # 시그널 불릿(•)은 정확히 1개
    assert text.count("\n• ") == 1
    # 이슈 우선 정렬로 뉴스·이벤트 계열이 남고 수치 계열(💡)은 밀린다
    assert "📅 오늘 밤 CPI 발표" in text
    assert "💡 DRAM ETF" not in text
    # 사이트 전용 CTA
    assert "🔗 전체 근거·종목 픽·장중 라이브 →" in text
    assert "상세 분석" not in text


def test_close_compresses_to_one_signal_and_has_cta(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {"market_title": "코스닥 테마 폭발", "telegram_signals": ["🚀 코스닥 +4.99%", "💱 원달러 부담"]}
    md = {"indices": {"kospi": {"price": 6820.6, "change_pct": -6.37},
                      "kosdaq": {"price": 791.8, "change_pct": -4.53}}}
    cc.save_closing_telegram_message("2026-07-16", analysis, md)
    text = (tmp_path / "telegram_message_kospi_close.txt").read_text(encoding="utf-8")
    assert text.count("\n• ") == 1
    assert "🔗 수급·시장폭 상세 →" in text
    assert "상세 분석" not in text


def test_us_keeps_two_issues_and_has_cta(tmp_path, monkeypatch):
    # US는 이슈가 브리핑 본체라 2개 유지 — Phase B의 시그널 압축(2→1) 대상이 아니다.
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {
        "prediction": {"up_pct": 62, "down_pct": 38},
        "todays_view": {"view_title": "돈이 SW에서 AI 인프라로"},
        "issues": [{"title": "IBM CEO SW 지출 경고"}, {"title": "오늘 밤 CPI 발표"}, {"title": "엔비디아 중국 재개"}],
    }
    cc.save_telegram_message("us", "2026-07-17", analysis)
    text = (tmp_path / "telegram_message_us.txt").read_text(encoding="utf-8")
    assert "IBM CEO SW 지출 경고" in text
    assert "오늘 밤 CPI 발표" in text
    assert "엔비디아 중국 재개" not in text  # [:2]로 3번째는 제외
    assert "🔗 전체 이슈·종목 픽 →" in text
    assert "상세 분석" not in text
