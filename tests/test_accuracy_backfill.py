# check_accuracy 백필 대상 선정 로직 단위 테스트 (yfinance는 모킹)
import sys
import json
import pathlib
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
import check_accuracy as ca


def _setup(tmp_path, entries):
    (tmp_path / "briefings.json").write_text(
        json.dumps({"briefings": entries}, ensure_ascii=False), encoding="utf-8"
    )
    ca.DATA_DIR = tmp_path
    # check_accuracy()가 가리키는 파일 경로도 DATA_DIR 기반 — load/save 모두 tmp 사용
    return tmp_path


def test_backfill_selects_only_past_unchecked(tmp_path, monkeypatch):
    today = datetime.now(ca.KST).strftime("%Y-%m-%d")
    entries = [
        {"date": "2026-05-13", "type": "kospi", "predicted_direction": "상승 우위", "is_correct": None},   # 과거·미검증 ✓
        {"date": "2026-05-12", "type": "kospi", "predicted_direction": "상승 우위", "is_correct": True},    # 이미 검증 ✗
        {"date": "2026-05-14", "type": "us",    "predicted_direction": "상승 우위", "is_correct": None},    # 타입 불일치 ✗
        {"date": today,        "type": "kospi", "predicted_direction": "상승 우위", "is_correct": None},    # 오늘 ✗
        {"date": "2026-05-11", "type": "kospi", "predicted_direction": "하락 우위", "is_correct": None},   # 과거·미검증 ✓
    ]
    _setup(tmp_path, entries)

    called = []
    monkeypatch.setattr(ca, "check_accuracy", lambda d, t, force=False: called.append((d, t)))

    ca.backfill("kospi")

    assert called == [("2026-05-11", "kospi"), ("2026-05-13", "kospi")]  # 정렬·과거·미검증·kospi만


def test_backfill_no_targets(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, [
        {"date": "2026-05-13", "type": "kospi", "predicted_direction": "상승 우위", "is_correct": True},
    ])
    monkeypatch.setattr(ca, "check_accuracy", lambda d, t, force=False: (_ for _ in ()).throw(AssertionError("호출되면 안 됨")))
    ca.backfill("kospi")
    assert "백필 대상 없음" in capsys.readouterr().out


# ── NaN 가드: fetch가 NaN change_pct를 반환하면 가짜 '하락'을 기록하지 않는다 ──
def test_nan_change_pct_not_recorded(tmp_path, monkeypatch):
    _setup(tmp_path, [
        {"date": "2026-06-02", "type": "kospi",
         "predicted_direction": "상승 우위", "is_correct": None},
    ])
    # fetch가 NaN change_pct 반환 (yfinance 미수집 행 시뮬레이션)
    monkeypatch.setattr(ca, "get_kospi_close_vs_prev_close",
                        lambda d: (3000.0, 3000.0, float("nan")))
    ca.check_accuracy("2026-06-02", "kospi")

    saved = json.loads((tmp_path / "briefings.json").read_text(encoding="utf-8"))
    entry = saved["briefings"][0]
    # 채점 보류 — actual_direction이 주입되지 않아야 한다 (가짜 '하락' 금지)
    assert entry.get("actual_direction") is None
    assert entry.get("is_correct") is None
