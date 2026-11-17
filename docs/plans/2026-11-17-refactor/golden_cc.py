# call_claude의 결정론 부분(시스템 프롬프트·데이터 지시문·텔레그램 메시지·기록 힌트)을 스냅샷으로 다시 만들어 남기는 골든 재생기
"""사용법: python3 golden_cc.py <worktree 경로> <출력 폴더> — Claude API는 부르지 않는다. 네트워크도 막는다."""
import json
import socket
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
if (root / ".git").is_dir():
    sys.exit("진짜 저장소에서는 돌리지 않는다")


def _blocked(*a, **k):
    raise OSError("golden: network blocked")


socket.socket.connect = _blocked
socket.create_connection = _blocked
sys.path.insert(0, str(root / "scripts"))
import os  # noqa: E402

os.chdir(root)
import call_claude as cc  # noqa: E402

out.mkdir(parents=True, exist_ok=True)
rec = {}
for k in ("FORMAT_POOL", "FORMAT_WEIGHTS", "FORMAT_POOL_CLOSE", "FORMAT_WEIGHTS_CLOSE", "SECTOR_POOL",
          "HEADLINE_CRAFT", "KOSPI_SYSTEM_PROMPT", "US_SYSTEM_PROMPT", "KOSPI_CLOSE_SYSTEM_PROMPT"):
    rec[k] = getattr(cc, k)
rec["officeholder"] = cc._officeholder_directive()
for bt in ("kospi", "us", "kospi-close"):
    for fn in ("load_signal_history", "load_sector_history"):
        try:
            rec[f"{fn}:{bt}"] = getattr(cc, fn)(bt)
        except Exception as e:
            rec[f"{fn}:{bt}"] = repr(e)
    try:
        rec[f"calibration:{bt}"] = cc.build_calibration_hint(bt)
    except Exception as e:
        rec[f"calibration:{bt}"] = repr(e)
(out / "constants.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

md = {}
for bt in ("kospi", "us", "kospi-close"):
    p = root / "data" / f"latest_{bt.replace('-', '_')}.json"
    md[bt] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
types = {"kospi": "kospi", "us": "us", "close": "kospi-close"}
for ddir in sorted((root / "web" / "briefings").iterdir()):
    d = ddir.name
    for k, bt in types.items():
        snap = ddir / k / "analysis_snapshot.json"
        if not snap.exists():
            continue
        a = json.loads(snap.read_text(encoding="utf-8"))
        res = {}
        for name, call in (
            ("news_session", lambda: cc._us_news_session_directive(d, a)),
            ("session_label", lambda: cc._session_label_directive(d, bt)),
            ("index_position", lambda: cc._index_position_directive(md[bt])),
            ("session_log", lambda: cc._us_session_log_directive(d, md[bt])),
            ("calendar_tense", lambda: cc._calendar_tense_directive(md[bt])),
            ("event_when", lambda: cc._event_when_directive(d, md[bt])),
            ("investor_eok", lambda: cc._investor_to_eok(md[bt].get("investor_trading") or {})),
        ):
            try:
                res[name] = call()
            except Exception as e:
                res[name] = f"ERROR {type(e).__name__}: {e}"
        tg = root / "data" / f"telegram_message_{bt.replace('-', '_')}.txt"
        if tg.exists():
            tg.unlink()
        try:
            if k == "close":
                cc.save_closing_telegram_message(d, json.loads(json.dumps(a)), md[bt])
            else:
                cc.save_telegram_message(bt, d, json.loads(json.dumps(a)))
            res["telegram"] = tg.read_text(encoding="utf-8") if tg.exists() else None
        except Exception as e:
            res["telegram"] = f"ERROR {type(e).__name__}: {e}"
        (out / f"{d}_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print("golden cc done:", out)
