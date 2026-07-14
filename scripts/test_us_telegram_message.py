# US 이슈 중심 텔레그램 메시지가 예측 대신 오늘의 관점·이슈 제목으로 구성되는지 검증
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc


def test_us_telegram_uses_todays_view_and_issues(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {
        "todays_view": {"view_title": "돈이 SW에서 AI 인프라로", "dek": "..."},
        "issues": [
            {"title": "IBM CEO SW 지출 경고"},
            {"title": "오늘 밤 CPI 발표"},
            {"title": "엔비디아 중국 재개"},
        ],
    }
    cc.save_telegram_message("us", "2026-07-14", analysis)
    msg = (tmp_path / "telegram_message_us.txt").read_text(encoding="utf-8")
    assert "미국 시장 브리핑" in msg
    assert "돈이 SW에서 AI 인프라로" in msg
    assert "IBM CEO SW 지출 경고" in msg
    assert "예측:" not in msg          # 예측 라인이 없어야 함
    assert "신뢰도:" not in msg


def test_kospi_telegram_still_has_prediction(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {
        "prediction": {"direction": "상승 우위", "up_pct": 60, "down_pct": 40, "confidence": 70},
        "reason_title": "왜 오를까",
        "reasons": ["📈 선물 강세예요."],
    }
    cc.save_telegram_message("kospi", "2026-07-14", analysis)
    msg = (tmp_path / "telegram_message_kospi.txt").read_text(encoding="utf-8")
    assert "예측:" in msg
    assert "신뢰도:" in msg
