# 발행 게이트(validate_analysis.validate)를 모든 스냅샷에 다시 돌려 교정·경고·차단 결과를 남기는 골든 재생기
"""사용법: python3 golden_validate.py <worktree 경로> <출력 폴더> — 네트워크를 막아 두 번 돌려도 같은 결과가 나온다."""
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
import validate_analysis as va  # noqa: E402

out.mkdir(parents=True, exist_ok=True)
types = {"kospi": "kospi", "us": "us", "close": "kospi-close"}
latest = {}
for k, bt in types.items():
    p = root / "data" / va.LATEST_FILE[bt]
    latest[bt] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
for ddir in sorted((root / "web" / "briefings").iterdir()):
    for k, bt in types.items():
        snap = ddir / k / "analysis_snapshot.json"
        if not snap.exists():
            continue
        a = json.loads(snap.read_text(encoding="utf-8"))
        try:
            r = va.validate(a, latest[bt], bt)
            res = {"corrections": r["corrections"], "warnings": r["warnings"], "blocks": r["blocks"], "analysis": r["analysis"]}
        except Exception as e:
            res = {"error": f"{type(e).__name__}: {e}"}
        (out / f"{ddir.name}_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print("golden validate done:", out)
