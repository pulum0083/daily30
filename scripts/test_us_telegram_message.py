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
    assert "🎯 <b>돈이 SW에서 AI 인프라로</b>" in msg
    assert "👀 오늘 밤 볼 것\nIBM CEO SW 지출 경고" in msg
    assert "오늘 밤 CPI 발표" not in msg   # 오늘 밤 볼 것은 첫 이슈 하나만
    assert "신뢰도" not in msg            # 미국엔 신뢰도가 없다
    assert "우위" not in msg              # 확률이 없으면 방향 줄도 없다


def test_us_telegram_direction_line(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    for (up, dn), want in {(32, 68): "📉 <b>하락 우위 68%</b>", (62, 38): "📈 <b>상승 우위 62%</b>",
                           (50, 50): "📊 <b>중립 50%</b>"}.items():
        cc.save_telegram_message("us", "2026-10-23", {"prediction": {"up_pct": up, "down_pct": dn},
                                                       "todays_view": {"view_title": "제목"}, "issues": []})
        msg = (tmp_path / "telegram_message_us.txt").read_text(encoding="utf-8")
        assert want in msg and "오늘 밤 볼 것" not in msg


def test_kospi_telegram_still_has_prediction(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {
        "prediction": {"direction": "상승 우위", "up_pct": 60, "down_pct": 40, "confidence": 70},
        "reason_title": "왜 오를까",
        "reasons": ["📈 선물 강세예요."],
    }
    cc.save_telegram_message("kospi", "2026-07-14", analysis)
    msg = (tmp_path / "telegram_message_kospi.txt").read_text(encoding="utf-8")
    assert "<b>상승 우위 60%</b>" in msg
    assert "(신뢰도 70%)" in msg
