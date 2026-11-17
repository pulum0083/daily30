# 리팩토링 전후 발행 결과를 글자 하나까지 대조하는 골든 렌더러 — 각자 git worktree에서 돌린다.
"""사용법(저장소 루트에서)

    python3 docs/plans/2026-11-17-refactor/golden.py <worktree 경로> <출력 폴더>

- 그 worktree의 scripts/ 를 import해 발행된 모든 브리핑을 스냅샷으로 다시 그리고,
  목록·아카이브·RSS·사이트맵·섹터·기록·장기 페이지 작성기를 돌린 뒤 web/ 를 출력 폴더로 복사한다.
- 네트워크는 막는다(두 번 돌려도 같은 입력이 되도록). 막혀서 실패한 섹션은 양쪽에서 똑같이 빠진다.
- worktree 안의 파일을 고치므로 진짜 저장소에서 돌리지 말 것.
"""
import json
import shutil
import socket
import sys
import traceback
from pathlib import Path

root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
if (root / ".git").is_dir():
    sys.exit("진짜 저장소에서는 돌리지 않는다 — worktree 경로를 넘길 것")


def _blocked(*a, **k):
    raise OSError("golden: network blocked")


socket.socket.connect = _blocked
socket.create_connection = _blocked

sys.path.insert(0, str(root / "scripts"))
import os  # noqa: E402

os.chdir(root)
import generate_html as g  # noqa: E402

if out.exists():
    shutil.rmtree(out)
(out / "render").mkdir(parents=True)
log = []


def market(t):
    p = root / "data" / g.DATA_FILE[t]
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


md = {t: market(t) for t in ("kospi", "close", "us")}
for ddir in sorted(p for p in g.BRIEFINGS_DIR.iterdir() if p.is_dir()):
    for t in ("kospi", "close", "us"):
        if not (ddir / t / "index.html").exists():
            continue
        name = f"{ddir.name}_{t}.html"
        try:
            html, _ = g.render_briefing(t, ddir.name, md[t])
            (out / "render" / name).write_text(html, encoding="utf-8")
        except Exception:
            (out / "render" / name).write_text("ERROR\n" + traceback.format_exc(), encoding="utf-8")


def run(label, fn, *a):
    try:
        r = fn(*a)
        log.append(f"{label}: ok {r!r}"[:300])
    except Exception as e:
        log.append(f"{label}: ERROR {type(e).__name__}: {e}"[:300])


def date_of(name):
    try:
        return json.loads((root / "data" / name).read_text(encoding="utf-8")).get("date") or ""
    except Exception:
        return ""


run("list_json", g.write_briefings_list_json)
run("index", g.write_briefings_index)
run("rss", g.write_briefings_rss)
run("sitemap", g.write_sitemap_xml)
run("recent", g.write_stocks_recent_briefings)
run("sectors", g.build_sector_pages)
run("records", g.write_record_pages)
run("nasdaq_page", g.write_nasdaq_page, date_of("nasdaq_overheat.json"))
run("sp500_page", g.write_sp500_page, date_of("sp500_ma200.json"))
run("midterm_page", g.write_midterm_page, date_of("midterm_2018.json"))

(out / "log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
shutil.copytree(root / "web", out / "web", ignore=shutil.ignore_patterns("*.png", "*.jpg", "*.woff2"))
shutil.copytree(root / "data", out / "data")
print("golden done:", out)
